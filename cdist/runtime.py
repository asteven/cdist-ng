import os
import asyncio


from .execution import Remote


class Runtime(object):
    """The cdist runtime implements the core low level primitives for
    interacting with a target.
    """

    def __init__(self, context):
        self.context = context
        self.remote = Remote(context)

    @asyncio.coroutine
    def transfer_global_explorers(self):
        """Transfer the global explorers to the target.
        """
        yield from self.remote.mkdir(self.context['remote']['explorer'])
        yield from self.remote.transfer(
            self.context['local']['explorer'],
            self.context['remote']['explorer']
        )
        yield from self.remote.exec(
            ['chmod', '0700', '%s/*' % self.context['remote']['explorer']])


    @asyncio.coroutine
    def run_global_explorer(self, name):
        """Run the given global explorer and return it's output.
        """
        explorer = os.path.join(self.context['remote']['explorer'], name)
        yield from self.remote.exec([explorer])

    @asyncio.coroutine
    def run_global_explorers(self):
        """Run all global explorers and save their output in the session.
        """
        # copy files in parallel
        tasks = []
        for name in self.context.session['conf']['explorer']:
            task = asyncio.async(self.run_global_explorer(name))
            tasks.append(task)
        if tasks:
            done, pending = yield from asyncio.wait(tasks)
            assert not pending

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

