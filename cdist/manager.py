import fnmatch
import asyncio
import pprint

from cdist import exceptions


class ObjectManager(object):

    def __init__(self, runtime, tags=None):
        self.runtime = runtime
        self.tags = tags
        self.log = runtime.log
        self.queue = asyncio.Queue()
        self.pending_objects = set()
        self.realized_objects = set()
        self.objects = {}
        self.events = {
            'prepare': {},
            'apply': {},
        }
        self.dependencies = {}
        self.unresolved_dependencies = {}
        #self.collector = asyncio.ensure_future(self._collect_new_objects())

    async def collect_new_objects(self):
        # TODO: make this event based
        # TODO: use unix socket or zmq or something for cdist <-> emulator communication
        for _object in (await self.runtime.loop.run_in_executor(None, self.runtime.list_objects)):
            if _object.name not in self.objects:
                self.add(_object)

    def add(self, _object):
        self.log.info('add: %s', _object)
        self.objects[_object.name] = _object
        self.events['prepare'][_object.name] = asyncio.Event()
        self.events['apply'][_object.name] = asyncio.Event()
        self.queue.put_nowait(_object)

    def resolve_dependencies(self, _object):
        self.dependencies.setdefault(_object.name, set())
        self.unresolved_dependencies.setdefault(_object.name, set())
        deps = self.runtime.get_dependencies(_object)
        self.log.info('resolve_dependencies: %s', pprint.pformat(deps))

        if deps['auto']:
            # The objects (children) that this cdist_object (parent) defined
            # in it's type manifest shall inherit all explicit requirements
            # that the parent has so that user defined requirements are
            # fullfilled and processed in the expected order.
            for auto_requirement in self.find_requirements_by_name(deps['auto']):
                auto_requirement_deps = self.runtime.get_dependencies(auto_requirement)
                for requirement in self.find_requirements_by_name(deps['after']):
                    requirement_deps = self.runtime.get_dependencies(requirement)
                    requirement_object_all_requirements = requirement_deps['after'] + requirement_deps['auto']
                    if (requirement not in auto_requirement_deps['after']
                        and auto_requirement not in requirement_object_all_requirements):
                        self.log.debug('Adding %s to %s requirements', requirement, auto_requirement)
                        auto_requirement_deps['after'].append(requirement)
            # On the other hand the parent shall depend on all the children
            # it created so that the user can setup dependencies on it as a
            # whole without having to know anything about the parents
            # internals.
            #deps['after'].extend(deps['auto'])

        dependencies = set(self.find_requirements_by_name(deps['require'] + deps['after'] + deps['auto']))
        unresolved_dependencies = dependencies.difference(self.realized_objects)
        # Objects without any unresolved dependencies can be prepared and applied
        if len(unresolved_dependencies) == 0:
            self.events['prepare'][_object.name].set()
            self.events['apply'][_object.name].set()
        else:
            if not deps['require']:
                # Objects without 'require' dependencies can be prepared
                self.events['prepare'][_object.name].set()
            else:
                self.events['prepare'][_object.name].clear()
            self.events['apply'][_object.name].clear()
        self.dependencies[_object.name] = dependencies
        self.unresolved_dependencies[_object.name] = unresolved_dependencies


    def find_requirements_by_name(self, requirements):
        """Takes a list of requirement patterns and returns a list of matching object names.

        Patterns are expected to be Unix shell-style wildcards for use with fnmatch.filter.

        find_requirements_by_name(['__type/object_id', '__other_type/*']) ->
            ['__type/object_id', '__other_type/any', '__other_type/match']
        """
        object_names = self.objects.keys()
        for pattern in requirements:
            found = False
            for requirement in fnmatch.filter(object_names, pattern):
                found = True
                yield requirement
            if not found:
                raise exceptions.RequirementNotFoundError(pattern)

    async def prepare(self, event, _object):
        self.resolve_dependencies(_object)
        await event.wait()
        self.log.info('prepare: %s', _object)
        await self.runtime.run_type_explorers(_object)
        await self.runtime.run_type_manifest(_object)
        await self.collect_new_objects()

    async def apply(self, event, _object):
        self.resolve_dependencies(_object)
        await event.wait()
        self.log.info('apply: %s', _object)
        _object['code-local'] = await self.runtime.run_gencode_local(_object)
        _object['code-remote'] = await self.runtime.run_gencode_remote(_object)
        await self.runtime.sync_object(_object, 'code-local', 'code-remote')
        if _object['code-local']:
            self.log.info('apply code-local: %s', _object)
            await self.runtime.run_code_local(_object)
        if _object['code-remote']:
            self.log.info('apply code-remote: %s', _object)
            await self.runtime.transfer_code_remote(_object)
            await self.runtime.run_code_remote(_object)
        self.finish(_object)

    def finish(self, _object):
        self.log.info('finish: %s', _object)
        for object_name, dependencies in self.unresolved_dependencies.items():
            if _object.name in dependencies:
                dependencies.remove(_object.name)
                if len(dependencies) == 0:
                    self.events['prepare'][object_name].set()
                    self.events['apply'][object_name].set()
        self.queue.task_done()
        self.pending_objects.remove(_object.name)
        self.realized_objects.add(_object.name)

    async def realize(self, _object):
        self.log.info('realize: %s', _object)
        self.pending_objects.add(_object.name)
        await self.prepare(
            self.events['prepare'][_object.name],
            _object,
        )
        await self.apply(
            self.events['apply'][_object.name],
            _object,
        )

    async def print_info(self):
        while True:
            print('### queue: %s' % self.queue, flush=True)
            print('### pending_objects: %s' % self.pending_objects, flush=True)
            print('### realized_objects: %s' % self.realized_objects, flush=True)
            unresolved_dependencies = {}
            for n, d in self.unresolved_dependencies.items():
                if d:
                    unresolved_dependencies[n] = d
            import pprint
            print('### unresolved_dependencies:')
            pprint.pprint(unresolved_dependencies)
            #print('### unresolved_dependencies: %s' % unresolved_dependencies, flush=True)
            await asyncio.sleep(3)

    async def realize_objects(self):
        tasks = []
        while True:
            _object = await self.queue.get()
            task = asyncio.ensure_future(self.realize(_object))
            tasks.append(task)

    async def process(self):
        _print_info_task = None
        #_print_info_task = asyncio.ensure_future(self.print_info())
        await self.collect_new_objects()
        realize_task = asyncio.ensure_future(self.realize_objects())
        await self.queue.join()
        realize_task.cancel()
        if _print_info_task:
            _print_info_task.cancel()
