import os
import asyncio
import logging


from .execution import Local, Remote
from .core import CdistType, CdistObject


# FIXME: replace with dynamic marker inside the runtime
OBJECT_MARKER = '.cdist'


class Runtime(object):
    """The cdist runtime implements the core low level primitives for
    interacting with a target.
    """

    def __init__(self, session, target, local_session_dir):
        self.session = session
        self.target = target
        self.local_session_dir = local_session_dir
        self.remote_session_dir = self.session['remote-cache-dir']
        self.__path = None
        self.__environ = None
        self._type_explorers_transferred = []
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
                'local': {
                    'cache': self.local_session_dir,
                    'explorer': opj(self.local_session_dir, 'conf', 'explorer'),
                    'object': opj(target_path, 'object'),
                    'type': opj(self.local_session_dir, 'conf', 'type'),
                },
                'remote': {
                    'cache': self.remote_session_dir,
                    'copy': opj(target_path, self.target.remote_copy),
                    'exec': opj(target_path, self.target.remote_exec),
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
                '__target_url': self.target['url'],
                'CDIST_INTERNAL': 'yes',
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

    def sync_object(self, cdist_object):
        """Sync changes to the cdist object to disk.
        """
        object_path = self.get_object_path(cdist_object.name)
        cdist_object.to_dir(object_path)

    def get_type(self, type_name):
        """Get a type instance by name.
        """
        type_path = os.path.join(self.path['local']['type'], type_name)
        _type = CdistType.from_dir(type_path)
        return _type

    def get_object_path(self, object_name):
        """Get the absolute path to an object.
        """
        return os.path.join(
            self.path['local']['object'],
            object_name,
            OBJECT_MARKER
        )

    def get_object(self, object_name):
        """Get a object instance by name.
        """
        type_name, object_id = CdistObject.split_name(object_name)
        _type = self.get_type(type_name)
        object_path = self.get_object_path(object_name)
        _object = _type.object_from_dir(object_path)
        return _object

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
        env = self.environ.copy()
        env.update({
            '__explorer': self.path['remote']['explorer'],

        })
        explorer = os.path.join(self.path['remote']['explorer'], name)
        result = yield from self.remote.check_output([explorer], env=env)
        return result

    @asyncio.coroutine
    def run_global_explorers(self):
        """Run all global explorers and save their output in the session.
        """
        logging.debug('Running global explorers')
        yield from self.transfer_global_explorers()
        # execute explorers in parallel
        tasks = []
        for name in self.session['conf']['explorer']:
            task = asyncio.async(self.run_global_explorer(name))
            task.name = name
            tasks.append(task)
        if tasks:
            done, pending = yield from asyncio.wait(tasks)
            assert not pending

            for t in done:
                result = t.result()
                value = result.decode('ascii').rstrip()
                self.target['explorer'][t.name] = value
            self.sync_target()

    @asyncio.coroutine
    def run_type_explorer(self, cdist_object, explorer_name):
        """Run the given type explorer for the given object and return it's output.
        """
        cdist_type = self.get_type(cdist_object['type'])
        remote_explorer_path = os.path.join(self.path['remote']['type'], cdist_type.path['explorer'])

        env = self.environ.copy()
        env.update({
            '__object': os.path.join(
                self.path['remote']['object'],
                cdist_object.name,
                OBJECT_MARKER
            ),
            '__object_id': cdist_object['object-id'],
            '__object_name': cdist_object.name,
            '__type_explorer': remote_explorer_path,
            '__explorer': self.path['remote']['explorer'],
        })

        logging.debug("Running type explorer '%s' for object %s", explorer_name, cdist_object)
        explorer = os.path.join(remote_explorer_path, explorer_name)
        result = yield from self.remote.check_output([explorer], env=env)
        return result

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
            done, pending = yield from asyncio.wait(tasks)
            assert not pending

            for t in done:
                result = t.result()
                value = result.decode('ascii').rstrip()
                cdist_object['explorer'][t.name] = value
            self.sync_object(cdist_object)

    @asyncio.coroutine
    def transfer_type_explorers(self, cdist_type):
        """Transfer the type explorers for the given type to the target.
        """
        if cdist_type['explorer']:
            if cdist_type.name in self._type_explorers_transferred:
                logging.debug('Skipping retransfer of type explorers for: %s', cdist_type)
            else:
                logging.debug("Transfering type explorers for type: %s", cdist_type)
                source = os.path.join(self.path['local']['type'], cdist_type.path['explorer'])
                destination = os.path.join(self.path['remote']['type'], cdist_type.path['explorer'])
                yield from self.remote.transfer(source, destination)
                yield from self.remote.check_call(
                    ['chmod', '0700', '%s/*' % destination])
                self._type_explorers_transferred.append(cdist_type.name)

    @asyncio.coroutine
    def transfer_object_parameters(self, cdist_object):
        """Transfer the parameters for the given object to the target.
        """
        if cdist_object['parameter']:
            logging.debug("Transfering object parameters for object: %s", cdist_object)
            source = os.path.join(
                self.path['local']['object'],
                cdist_object.name,
                OBJECT_MARKER,
                'parameter'
            )
            destination = os.path.join(
                self.path['remote']['object'],
                cdist_object.name,
                OBJECT_MARKER,
                'parameter'
            )
            yield from self.remote.transfer(source, destination)

    def list_object_names(self):
        """Return a list of object names"""
        object_base_path = self.path['local']['object']
        for path, dirs, files in os.walk(object_base_path):
            if OBJECT_MARKER in dirs:
                yield os.path.relpath(path, object_base_path)

    def list_objects(self):
        """Return a list of object instances"""
        object_base_path = self.path['local']['object']
        type_base_path = self.path['local']['type']
        for object_name in self.list_object_names():
            type_name, object_id = CdistObject.split_name(object_name)
            type_path = os.path.join(type_base_path, type_name)
            _type = CdistType.from_dir(type_path)
            object_path = os.path.join(object_base_path, object_name, OBJECT_MARKER)
            yield _type.object_from_dir(object_path)
