import sys
import os
import tempfile

import click

from cdist import session
from cdist import target
from cdist import runtime
from cdist.core import CdistObject


class EmulatorCommand(click.Command):
    def __init__(self, log, runtime, type_name):
        self.log = log
        self._runtime = runtime
        self._type_name = type_name
        self._type = runtime.get_type(self._type_name)
        super().__init__(type_name, callback=self.run, params=self.get_type_params())

    def get_type_params(self):
        defaults = self._type['parameter']['default']
        params = []
        for param_name in self._type['parameter']['required']:
            params.append(click.Option(('--'+ param_name,), required=True, default=defaults.get(param_name, None)))
        for param_name in self._type['parameter']['required_multiple']:
            params.append(click.Option(('--'+ param_name,), required=True, multiple=True, default=defaults.get(param_name, None)))
        for param_name in self._type['parameter']['optional']:
            params.append(click.Option(('--'+ param_name,), default=defaults.get(param_name, None)))
        for param_name in self._type['parameter']['optional_multiple']:
            params.append(click.Option(('--'+ param_name,), multiple=True, default=defaults.get(param_name, None)))
        for param_name in self._type['parameter']['boolean']:
            params.append(click.Option(('--'+ param_name,), is_flag=True, default=defaults.get(param_name, None)))

        if not self._type['singleton']:
            params.append(click.Argument(('object_id',), nargs=1))
        return params

    def run(self, *args, **kwargs):
        self.log.debug('args: %s', args)
        self.log.debug('kwargs: %s', kwargs)
        self.log.debug('type: %s', self._type)
        if not self._type['singleton']:
            object_id = kwargs.pop('object_id')
        else:
            object_id = None
        object_id = CdistObject.sanitise_object_id(object_id)
        CdistObject.validate_object_id(object_id)
        _object = self._type(object_id=object_id, parameters=kwargs)
        self.log.debug('object: %s', _object)
        self._runtime.create_object(_object)


@click.command(name='emulator', add_help_option=False, context_settings=dict(
    ignore_unknown_options=True,
))
@click.pass_context
@click.argument('type_name', nargs=1)
@click.argument('type_args', nargs=-1, type=click.UNPROCESSED)
def main(ctx, type_name, type_args):
    '''Type emulator
    '''
    log = ctx.obj['log']
    log.debug('ctx.args: %s', ctx.args)
    log.debug('ctx.params: %s', ctx.params)
    log.debug('type_name: %s', type_name)
    log.debug('type_args: %s', type_args)

    _session = session.Session.from_dir(os.environ['__cdist_local_session'])
    _target = target.Target.from_dir(os.environ['__cdist_local_target'])
    _runtime = runtime.Runtime(_session, _target, os.environ['__cdist_local_session'])
    _type = _runtime.get_type(type_name)
    log.debug('type: %s', _type)

    cmd = EmulatorCommand(log, _runtime, type_name)
    cmd(args=type_args, prog_name=type_name)
