import os
import asyncio
import contextlib
import tempfile
import shutil
import logging


from .execution import Local, Remote
from .core import CdistType, CdistObject


class Runtime(object):
    """The cdist runtime implements the core low level primitives for
    interacting with a target.
    """

    def __init__(self, session, target, local_session_dir):
        self.log = logging.getLogger('cdist')
        self.session = session
        self.target = target
        self.local_session_dir = local_session_dir
        self.remote_session_dir = self.session['remote-cache-dir']
        self.__path = None
        self.__environ = None
        self._type_explorers_transferred = []
        self.copy_semaphore = asyncio.Semaphore(20)
        self.exec_semaphore = asyncio.Semaphore(50)
        self.local = Local(self)
        self.remote = Remote(self)

    @property
    def path(self):
        """Dictionary holding absolute paths to various local and remote folders.
        """
        if self.__path is None:
            opj = os.path.join
            target_path = opj(self.local_session_dir, 'targets', self.target.identifier)

            path = {
                'target': {
                    'copy': opj(target_path, self.target.remote_copy),
                    'exec': opj(target_path, self.target.remote_exec),
                    'explorer': opj(target_path, 'explorer'),
                    'object': opj(target_path, 'object'),
                    'messages': opj(target_path, 'messages'),
                },
                'local': {
                    'bin': opj(self.local_session_dir, 'bin'),
                    'cache': self.local_session_dir,
                    'explorer': opj(self.local_session_dir, 'conf', 'explorer'),
                    'global': target_path,
                    'manifest': opj(self.local_session_dir, 'conf', 'manifest'),
                    'object': opj(target_path, 'object'),
                    'session': self.local_session_dir,
                    'target': target_path,
                    'type': opj(self.local_session_dir, 'conf', 'type'),
                },
                'remote': {
                    'cache': self.remote_session_dir,
                    'explorer': opj(self.remote_session_dir, 'conf', 'explorer'),
                    'object': opj(self.remote_session_dir, 'object'),
                    'type': opj(self.remote_session_dir, 'conf', 'type'),
                },
            }
            self.__path = path
        return self.__path

    @property
    def environ(self):
        """Dictionary of common environment variables.
        """
        if self.__environ is None:
            environ = {
                '__cdist_object_marker': self.target['object-marker'],
                '__cdist_log_level': logging.getLevelName(self.log.getEffectiveLevel()),
                '__target_url': self.target['url'],
            }
            for key,value in self.target['target'].items():
                if value:
                    environ['__target_'+ key] = value
            self.__environ = environ
        return self.__environ

    def sync_target(self):
        """Sync changes to the target to disk.
        """
        target_path = os.path.join(self.local_session_dir, 'targets', self.target.identifier)
        self.target.to_dir(target_path)

    def create_object(self, cdist_object):
        """Create new object on disk.
        """
        object_path = self.get_object_path(cdist_object, 'local')
        os.makedirs(object_path)
        cdist_object.to_dir(object_path)

    def sync_object(self, cdist_object):
        """Sync changes to the cdist object to disk.
        """
        object_path = self.get_object_path(cdist_object, 'local')
        cdist_object.to_dir(object_path)

    def get_type_path(self, type_or_name, context, component=None):
        """Get the absolute path to an type by name or instance.
        """
        if isinstance(type_or_name, CdistType):
            type_name = type_or_name.name
        else:
            type_name = type_or_name
        parts = [self.path[context]['type'], type_name]
        if component:
            parts.append(component)
        return os.path.join(*parts)

    def get_type(self, type_name):
        """Get a type instance by name.
        """
        type_path = self.get_type_path(type_name, 'local')
        _type = CdistType.from_dir(type_path)
        return _type

    def get_object_path(self, object_or_name, context, component=None):
        """Get the absolute path to an object by name or instance.
        """
        if isinstance(object_or_name, CdistObject):
            object_name = object_or_name.name
        else:
            object_name = object_or_name
        parts = [self.path[context]['object'], object_name, self.target['object-marker']]
        if component:
            parts.append(component)
        return os.path.join(*parts)

    def get_object(self, object_name):
        """Get a object instance by name.
        """
        type_name, object_id = CdistObject.split_name(object_name)
        object_path = self.get_object_path(object_name, 'local')
        _type = self.get_type(type_name)
        _object = _type.object_from_dir(object_path)
        return _object

    def list_object_names(self):
        """Return a list of object names"""
        object_base_path = self.path['local']['object']
        for path, dirs, files in os.walk(object_base_path):
            if self.target['object-marker'] in dirs:
                yield os.path.relpath(path, object_base_path)

    def list_objects(self):
        """Return a list of object instances"""
        for object_name in self.list_object_names():
            _object = self.get_object(object_name)
            yield _object

    @asyncio.coroutine
    def transfer_global_explorers(self):
        """Transfer the global explorers to the target.
        """
        yield from self.remote.transfer(
            self.path['local']['explorer'],
            self.path['remote']['explorer']
        )
        yield from self.remote.check_call(
            ['chmod', '0700', '%s/*' % self.path['remote']['explorer']])

    @asyncio.coroutine
    def run_global_explorer(self, name):
        """Run the given global explorer and return it's output.
        """
        env = {
            '__explorer': self.path['remote']['explorer'],

        }
        explorer = os.path.join(self.path['remote']['explorer'], name)
        result = yield from self.remote.check_output([explorer], env=env)
        return result.decode('ascii').rstrip()

    @asyncio.coroutine
    def run_global_explorers(self):
        """Run all global explorers and save their output in the session.
        """
        self.log.debug('Running global explorers')
        yield from self.transfer_global_explorers()
        # execute explorers in parallel
        tasks = []
        for name in self.session['conf']['explorer']:
            task = asyncio.async(self.run_global_explorer(name))
            task.name = name
            tasks.append(task)
        if tasks:
            results = yield from asyncio.gather(*tasks)
            for index,name in enumerate(self.session['conf']['explorer']):
                self.target['explorer'][name] = results[index]
            self.sync_target()

    @asyncio.coroutine
    def run_type_explorer(self, cdist_object, explorer_name):
        """Run the given type explorer for the given object and return it's output.
        """
        remote_explorer_path = self.get_type_path(cdist_object['type'], 'remote', 'explorer')

        env = {
            '__object': self.get_object_path(cdist_object, 'remote'),
            '__object_id': cdist_object['object-id'],
            '__object_name': cdist_object.name,
            '__type_explorer': remote_explorer_path,
            '__explorer': self.path['remote']['explorer'],
        }

        self.log.debug("Running type explorer '%s' for object %s", explorer_name, cdist_object)
        explorer = os.path.join(remote_explorer_path, explorer_name)
        result = yield from self.remote.check_output([explorer], env=env)
        return result.decode('ascii').rstrip()

    @asyncio.coroutine
    def run_type_explorers(self, cdist_object):
        """Run all type explorers for the given object and save their output in
        the target.
        """
        cdist_type = self.get_type(cdist_object['type'])
        yield from self.transfer_type_explorers(cdist_type)
        yield from self.transfer_object_parameters(cdist_object)

        # execute explorers in parallel
        tasks = []
        for name in cdist_object['explorer']:
            task = asyncio.async(self.run_type_explorer(cdist_object, name))
            task.name = name
            tasks.append(task)
        if tasks:
            results = yield from asyncio.gather(*tasks)
            for index,name in enumerate(cdist_object['explorer']):
                cdist_object['explorer'][name] = results[index]
            self.sync_object(cdist_object)

    @asyncio.coroutine
    def transfer_type_explorers(self, cdist_type):
        """Transfer the type explorers for the given type to the target.
        """
        if cdist_type['explorer']:
            if cdist_type.name in self._type_explorers_transferred:
                self.log.debug('Skipping retransfer of type explorers for: %s', cdist_type)
            else:
                self.log.debug("Transfering type explorers for type: %s", cdist_type)
                source = self.get_type_path(cdist_type, 'local', 'explorer')
                destination = self.get_type_path(cdist_type, 'remote', 'explorer')
                yield from self.remote.transfer(source, destination)
                yield from self.remote.check_call(
                    ['chmod', '0700', '%s/*' % destination])
                self._type_explorers_transferred.append(cdist_type.name)

    @asyncio.coroutine
    def transfer_object_parameters(self, cdist_object):
        """Transfer the parameters for the given object to the target.
        """
        if cdist_object['parameter']:
            self.log.debug("Transfering object parameters for object: %s", cdist_object)
            source = self.get_object_path(cdist_object, 'local', 'parameter')
            destination = self.get_object_path(cdist_object, 'remote', 'parameter')
            yield from self.remote.transfer(source, destination)

    @contextlib.contextmanager
    def messages(self, prefix, env):
        """Support messaging between types.
        """
        # create temporary files for new messages
        in_fd, messages_in = tempfile.mkstemp(prefix='cdist-message-in-')
        out_fd, messages_out = tempfile.mkstemp(prefix='cdist-message-out-')
        os.close(in_fd)
        os.close(out_fd)

        # give the client a copy of the global messages file to work with
        shutil.copyfile(self.path['target']['messages'], messages_in)

        # set environment variables for clients to use
        env['__messages_in'] = messages_in
        env['__messages_out'] = messages_out

        try:
            # give control back to our caller
            yield
        finally:
            # merge new messages back into our global list if any
            with open(messages_out, 'r') as fd:
                new_messages = False
                for line in fd:
                    message = line.strip('\n')
                    if message:
                        new_messages = True
                        self.target['messages'].append('%s:%s' % (prefix, message))
                if new_messages:
                    # write changes to disk
                    # FIXME: does this belong here? or better in the caller? elsewhere?
                    self.sync_target()
            # remove temporary files
            if os.path.exists(messages_in):
                os.remove(messages_in)
            if os.path.exists(messages_out):
                os.remove(messages_out)

    @asyncio.coroutine
    def run_initial_manifest(self, initial_manifest=None):
        manifest = os.path.join(self.path['local']['manifest'], 'init')

        env = {
            'PATH': "%s:%s" % (self.path['local']['bin'], os.environ['PATH']),
            '__global': self.path['local']['global'],
            '__cdist_manifest': manifest,
            '__manifest': self.path['local']['manifest'],
            '__explorer': self.path['target']['explorer'],
        }

        self.log.debug('Running initial manifest: %s', manifest)
        yield from self.local.check_call([manifest], env=env)

    @asyncio.coroutine
    def run_type_manifest(self, cdist_object):
        """Run the type manifest for the given object.
        """
        manifest = self.get_type_path(cdist_object['type'], 'local', 'manifest')

        if not os.path.isfile(manifest):
            return

        env = {
            'PATH': "%s:%s" % (self.path['local']['bin'], os.environ['PATH']),
            '__global': self.path['local']['global'],
            '__cdist_manifest': manifest,
            '__manifest': self.path['local']['manifest'],
            '__explorer': self.path['target']['explorer'],
            '__object': self.get_object_path(cdist_object, 'local'),
            '__object_id': cdist_object['object-id'],
            '__object_name': cdist_object.name,
            '__type': self.get_type_path(cdist_object['type'], 'local'),
        }

        self.log.debug("Running type manifest for object %s", cdist_object)
        message_prefix = cdist_object.name
        with self.messages(message_prefix, env):
            yield from self.local.check_call([manifest], env=env)

    @asyncio.coroutine
    def _run_gencode(self, cdist_object, context):
        """Run the gencode-* script for the given object.
        """
        script = self.get_type_path(cdist_object['type'], 'local', 'gencode-%s' % context)

        if not os.path.isfile(script):
            return

        env = {
            '__global': self.path['local']['global'],
            '__object': self.get_object_path(cdist_object, 'local'),
            '__object_id': cdist_object['object-id'],
            '__object_name': cdist_object.name,
            '__type': self.get_type_path(cdist_object['type'], 'local'),
        }

        self.log.debug("Running gencode-%s for object %s", context, cdist_object)
        message_prefix = cdist_object.name
        with self.messages(message_prefix, env):
            result = yield from self.local.check_output([script], env=env)
            return result.decode('ascii').rstrip()

    @asyncio.coroutine
    def run_gencode_local(self, cdist_object):
        """Run the gencode-local script for the given object.
        """
        return self._run_gencode(cdist_object, 'local')

    @asyncio.coroutine
    def run_gencode_remote(self, cdist_object):
        """Run the gencode-remote script for the given object.
        """
        return self._run_gencode(cdist_object, 'remote')

    @asyncio.coroutine
    def transfer_code_remote(self, cdist_object):
        """Transfer the code_remote script for the given object to the target.
        """
        source = self.get_object_path(cdist_object, 'local', 'code-remote')
        destination = self.get_object_path(cdist_object, 'remote', 'code-remote')
        yield from self.remote.transfer(source, destination)
        yield from self.remote.check_call(['chmod', '0700', destination])

    @asyncio.coroutine
    def _run_code(self, cdist_object, context):
        """Run the code-* script for the given object.
        """
        script = self.get_object_path(cdist_object, context, 'code-%s' % context)

        if not os.path.isfile(script):
            return

        env = {
            '__object': self.get_object_path(cdist_object, context),
            '__object_id': cdist_object['object-id'],
            '__object_name': cdist_object.name,
        }
        self.log.debug("Running code-%s for object %s", context, cdist_object)
        _context = getattr(self, context)
        yield from _context.check_call([script], env=env, shell=True)

    @asyncio.coroutine
    def run_code_local(self, cdist_object):
        """Run the code-local script for the given object.
        """
        return self._run_code(cdist_object, 'local')

    @asyncio.coroutine
    def run_code_remote(self, cdist_object):
        """Run the code-remote script for the given object on the target.
        """
        return self._run_code(cdist_object, 'remote')

