import os
import tempfile
import asyncio


from .execution import Remote


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
        self.remote = Remote(self)

    @property
    def path(self):
        if self.__path is None:
            opj = os.path.join
            target_path = opj(self.local_session_dir, 'targets', self.target.identifier)

            path = {
                'local': {
                    'cache': self.local_session_dir,
                    'explorer': opj(self.local_session_dir, 'conf', 'explorer'),
                    'type': opj(self.local_session_dir, 'conf', 'type'),
                },
                'remote': {
                    'cache': self.remote_session_dir,
                    'copy': opj(target_path, self.target.remote_copy),
                    'exec': opj(target_path, self.target.remote_exec),
                    'explorer': opj(self.remote_session_dir, 'conf', 'explorer'),
                    'type': opj(self.remote_session_dir, 'conf', 'type'),
                },
            }
            self.__path = path
        return self.__path

    @property
    def environ(self):
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
        explorer = os.path.join(self.path['remote']['explorer'], name)
        result = yield from self.remote.check_output([explorer])
        return result

    @asyncio.coroutine
    def run_global_explorers(self):
        """Run all global explorers and save their output in the session.
        """
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

    @asyncio.coroutine
    def run_type_explorer(self, cdist_object, explorer_name):
        """Run the given type explorer for the given object and return it's output.
        """

    @asyncio.coroutine
    def run_type_explorers(self, cdist_object):
        """Run all type explorers for the given object save their output in the
        target.
        """

    @asyncio.coroutine
    def transfer_type_explorers(self, cdist_type):
        """Transfer the type explorers for the given type to the target.
        """

    @asyncio.coroutine
    def transfer_object_parameters(self, cdist_object):
        """Transfer the parameters for the given object to the target.
        """

