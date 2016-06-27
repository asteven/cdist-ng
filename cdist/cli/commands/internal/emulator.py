import sys
import os
import tempfile

import click

import cdist
from cdist import session
from cdist import target
from cdist import exceptions
from cdist import runtime
from cdist import dependency
from cdist.core import CdistObject
from cdist.cli import utils


__get_env_default = '__something_a_user_will_never_use__'
def get_env(name, default=__get_env_default):
    """Return the value of the given environment variable or raise
    a `MissingRequiredEnvironmentVariableError` if it is not defined.
    """
    try:
        return os.environ[name]
    except KeyError as e:
        if default is not __get_env_default:
            return default
        raise exceptions.MissingRequiredEnvironmentVariableError(e.args[0])


class EmulatorCommand(click.Command):
    def __init__(self, log, runtime, type_name, stdin=sys.stdin.buffer):
        self.log = log
        self._runtime = runtime
        self._type_name = type_name
        self._stdin = stdin
        self._type = runtime.get_type(self._type_name)
        super().__init__(type_name, callback=self.run, params=self.get_type_params())
        self.__dpm = None

    @property
    def dependency(self):
        """Lazy initialized dependency manager.
        """
        if self.__dpm is None:
            self.__dpm = dependency.DependencyManager(os.path.join(
                self._runtime.path['local']['target'],
                'dependency'
            ))
        return self.__dpm

    def get_type_params(self):
        params = []

        # tags
        params.append(click.Option(('--if-tag',), multiple=True,
            callback=utils.comma_delimited_string_to_set,
            help='only apply this object if cdist is run with this tag'))
        params.append(click.Option(('--not-if-tag',), multiple=True,
            callback=utils.comma_delimited_string_to_set,
            help='do not apply this object if cdist is run with this tag'))

        # dependencies
        params.append(click.Option(('--require',), multiple=True,
            callback=utils.space_delimited_string_to_set,
            envvar='__cdist_require',
            help='require the given object to be fully realised before running this object'))
        params.append(click.Option(('--after',), multiple=True,
            callback=utils.space_delimited_string_to_set,
            envvar='__cdist_after',
            help='realize this object after the given one'))
        params.append(click.Option(('--before',), multiple=True,
            callback=utils.space_delimited_string_to_set,
            envvar='__cdist_before',
            help='realize this object before the given one'))

        # type specific parameters
        defaults = self._type['parameter']['default']
        for param_name in self._type['parameter']['required']:
            params.append(click.Option(('--'+ param_name,), required=True, default=defaults.get(param_name, None)))
        for param_name in self._type['parameter']['required_multiple']:
            params.append(click.Option(('--'+ param_name,), required=True, multiple=True, default=defaults.get(param_name, None)))
        for param_name in self._type['parameter']['optional']:
            params.append(click.Option(('--'+ param_name,), default=defaults.get(param_name, None)))
        for param_name in self._type['parameter']['optional_multiple']:
            params.append(click.Option(('--'+ param_name,), multiple=True, default=defaults.get(param_name, None)))
        for param_name in self._type['parameter']['boolean']:
            params.append(click.Option(('--'+ param_name,), is_flag=True))

        if not self._type['singleton']:
            params.append(click.Argument(('object_id',), nargs=1))
        return params

    chunk_size = 65536
    def _read_stdin(self):
        return self._stdin.read(self.chunk_size)

    def save_stdin(self, cdist_object):
        """If something is written to stdin, save it in the object as
        $__object/stdin so it can be accessed in manifest and gencode-*
        scripts.
        """
        if not self._stdin.isatty():
            try:
                # go directly to file instead of using CdistObject's api
                # as that does not support streaming
                path = self._runtime.get_object_path(cdist_object, 'local', 'stdin')
                with open(path, 'wb') as fd:
                    chunk = self._read_stdin()
                    while chunk:
                        fd.write(chunk)
                        chunk = self._read_stdin()
            except EnvironmentError as e:
                raise exceptions.CdistError('Failed to read from stdin: %s' % e)

    def run(self, *args, **kwargs):
        self.log.debug('args: %s', args)
        self.log.debug('kwargs: %s', kwargs)
        self.log.debug('type: %s', self._type)

        # Validate options
        if_tag = kwargs.pop('if_tag')
        not_if_tag = kwargs.pop('not_if_tag')
        if not if_tag.isdisjoint(not_if_tag):
            raise exceptions.ConflictingTagsError('Options \'if-tag\' and \'not-if-tag\' have conflicting values: %s vs %s' % (if_tag, not_if_tag))

        # Take dependencies out of kwargs for later processing
        deps = {
            'require': kwargs.pop('require'),
            'after': kwargs.pop('after'),
            'before': kwargs.pop('before'),
        }

        # Validate object id
        object_id = None
        if not self._type['singleton']:
            object_id = kwargs.pop('object_id')
            object_id = CdistObject.sanitise_object_id(object_id)
            CdistObject.validate_object_id(object_id)


        _object_name = CdistObject.join_name(self._type.name, object_id)

        # Check if object exists with conflicting parameters
        if self._runtime.object_exists(_object_name):
            self.log.info('object exists: %s', _object_name)
            #print('object exists: %s' %  _object_name)
            _object = self._runtime.get_object(_object_name)
            if _object['parameter'] != kwargs:
                self.log.error('%s : %s', _object['parameter'], kwargs)
                # TODO: more infos in error message
                raise exceptions.CdistError('Object %s already exists with conflicting parameters' % _object)

        else:
            # Instantiate new object
            _object = self._type(object_id=object_id, parameters=kwargs)
            # Create object on disk
            self._runtime.create_object(_object)

        self.log.debug('object: %s', _object)

        # Remember in which manifest the object was defined
        _source = get_env('__cdist_manifest')
        _object['source'].append(_source)

        # Save stdin if any
        self.save_stdin(_object)

        # Register dependencies
        for name in deps['require']:
            self.dependency.require(_object.name, name)
        for name in deps['before']:
            self.dependency.before(_object.name, name)
        for name in deps['after']:
            self.dependency.after(_object.name, name)
        __object_name = get_env('__object_name', None)
        if __object_name:
            self.dependency.auto(__object_name, _object.name)

        self._runtime.blocking_sync_object(_object)


@click.command(name='emulator', add_help_option=False, context_settings=dict(
    ignore_unknown_options=True,
))
@click.pass_context
@click.argument('type_name', nargs=1)
@click.argument('type_args', nargs=-1, type=click.UNPROCESSED)
def main(ctx, type_name, type_args):
    """Type emulator
    """
    log = ctx.obj['log']
    log.debug('ctx.args: %s', ctx.args)
    log.debug('ctx.params: %s', ctx.params)
    log.debug('type_name: %s', type_name)
    log.debug('type_args: %s', type_args)

    local_session_dir = get_env('__cdist_local_session')
    remote_session_dir = get_env('__cdist_remote_session')
    _target = target.Target.from_dir(get_env('__cdist_local_target'))
    _runtime = runtime.Runtime(_target, local_session_dir, remote_session_dir, logger=log)

    exit_code = 0
    try:
        cmd = EmulatorCommand(log, _runtime, type_name)
        cmd(args=type_args, prog_name=type_name)
    except KeyboardInterrupt:
        exit_code = 2
    except exceptions.CdistError as e:
        log.error(e)
        exit_code = 1

    ctx.exit(exit_code)
