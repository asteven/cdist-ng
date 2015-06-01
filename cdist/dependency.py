import logging
import os
import hashlib
import json
import itertools
import fnmatch
import pprint

from cdist import exceptions


log = logging.getLogger(__name__)


class DependencyManager(object):
    def __init__(self, base_path):
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        self.__cache = {}

    def reset_cache(self):
        self.__cache.clear()

    def __getitem__(self, key):
        """Return a dependency database for the given key"""
        try:
            return self.__cache[key]
        except KeyError:
            db = DependencyDatabase(self.base_path, key)
            self.__cache[key] = db
            return db

    def __contains__(self, key):
        db_name = hashlib.md5(key.encode()).hexdigest()
        db_file = os.path.join(self.base_path, db_name)
        return os.path.isfile(db_file)

    def __call__(self, object_name):
        """For use as an context manager"""
        return DependencyDatabase(self.base_path, object_name)

    def require(self, me, other):
        """Record a require dependency
        __me --require __other
        """
        with DependencyDatabase(self.base_path, me) as db:
            _list = db['require']
            if not other in _list:
                _list.append(other)

    def after(self, me, other):
        """Record an after dependency
        __me --after __other
        """
        with DependencyDatabase(self.base_path, me) as db:
            _list = db['after']
            if not other in _list:
                _list.append(other)

    def before(self, me, other):
        """Record a before dependency
        __me --before __other
        """
        with DependencyDatabase(self.base_path, other) as db:
            _list = db['after']
            if not me in _list:
                _list.append(me)

    def auto(self, parent, child):
        """Record a auto dependency"""
        child_db = DependencyDatabase(self.base_path, child)
        if not parent in child_db.get('after', []):
            with DependencyDatabase(self.base_path, parent) as db:
                _list = db['auto']
                _list.append(child)


class DependencyDatabase(dict):
    def __init__(self, base_path, name):
        self.base_path = base_path
        self.name = name
        self.db_name = hashlib.md5(self.name.encode()).hexdigest()
        self.db_file = os.path.join(self.base_path, self.db_name)
        self.load()

    def reset(self):
        dict.clear(self)
        self['object'] = self.name
        self['after'] = []
        self['require'] = []
        self['auto'] = []

    def load(self):
        """Load database from disk"""
        self.reset()
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r') as fp:
                self.update(json.load(fp))
        log.debug('load: {0!r}'.format(self))
    reload = load

    def save(self):
        """Save database to disk"""
        log.debug('save: {0!r}'.format(self))
        if self:
            with open(self.db_file, 'w') as fp:
                json.dump(self, fp)

    def __repr__(self):
        return '<{0.name} require:{0[require]} after:{0[after]} auto:{0[auto]}>'.format(self)

    # context manager interface
    def __enter__(self):
        self.load()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.save()
        # we don't handle errors ourself
        return False


class DependencyResolver(object):
    """Cdist's dependency resolver.

    Usage:
    >> manager = DependencyManager('/path/to/db')
    >> resolver = DependencyResolver(list_of_objects, manager)
    # Easy access to the objects we are working with
    >> resolver.objects['__some_type/object_id']
    <CdistObject __some_type/object_id>
    # Easy access to a specific objects dependencies
    >> resolver.dependencies['__some_type/object_id']
    [<CdistObject __other_type/dependency>, <CdistObject __some_type/object_id>]
    # Pretty print the dependency graph
    >> from pprint import pprint
    >> pprint(resolver.dependencies)
    # Iterate over all existing objects in the correct order
    >> for cdist_object in resolver:
    >>     do_something_with(cdist_object)
    """
    def __init__(self, objects, manager, logger=None):
        self.objects = dict((o.name, o) for o in objects)
        self.manager = manager
        self._dependencies = None
        self.log = logger or log

    @property
    def dependencies(self):
        """Build the dependency graph.

        Returns a dict where the keys are the object names and the values are
        lists of all dependencies including the key object itself.
        """
        if self._dependencies is None:
            self.log.info("Resolving dependencies...")
            self._dependencies = {}
            self._preprocess_requirements()
            for name,cdist_object in self.objects.items():
                resolved = []
                unresolved = []
                self._resolve_object_dependencies(cdist_object, resolved, unresolved)
                self._dependencies[name] = resolved
            self.log.debug(self._dependencies)
        return self._dependencies

    def find_requirements_by_name(self, requirements):
        """Takes a list of requirement patterns and returns a list of matching object instances.

        Patterns are expected to be Unix shell-style wildcards for use with fnmatch.filter.

        find_requirements_by_name(['__type/object_id', '__other_type/*']) ->
            [<Object __type/object_id>, <Object __other_type/any>, <Object __other_type/match>]
        """
        object_names = self.objects.keys()
        for pattern in requirements:
            found = False
            for requirement in fnmatch.filter(object_names, pattern):
                found = True
                yield self.objects[requirement]
            if not found:
                raise exceptions.RequirementNotFoundError(pattern)

    def _preprocess_requirements(self):
        """Find all autorequire dependencies and merge them to be just requirements
        for further processing.
        """
        for cdist_object in self.objects.values():
            deps = self.manager[cdist_object.name]
            if deps['auto']:
                # The objects (children) that this cdist_object (parent) defined
                # in it's type manifest shall inherit all explicit requirements
                # that the parent has so that user defined requirements are
                # fullfilled and processed in the expected order.
                for auto_requirement in self.find_requirements_by_name(deps['auto']):
                    auto_requirement_deps = self.manager[auto_requirement.name]
                    for requirement in self.find_requirements_by_name(deps['after']):
                        requirement_deps = self.manager[requirement.name]
                        requirement_object_all_requirements = requirement_deps['after'] + requirement_deps['auto']
                        if (requirement.name not in auto_requirement_deps['after']
                            and auto_requirement.name not in requirement_object_all_requirements):
                            self.log.debug('Adding %s to %s requirements', requirement.name, auto_requirement)
                            auto_requirement_deps['after'].append(requirement.name)
                # On the other hand the parent shall depend on all the children
                # it created so that the user can setup dependencies on it as a
                # whole without having to know anything about the parents
                # internals.
                deps['after'].extend(deps['auto'])

    def _resolve_object_dependencies(self, cdist_object, resolved, unresolved):
        """Resolve all dependencies for the given cdist_object and store them
        in the list which is passed as the 'resolved' arguments.

        e.g.
        resolved = []
        unresolved = []
        resolve_object_dependencies(some_object, resolved, unresolved)
        print("Dependencies for %s: %s" % (some_object, resolved))
        """
        self.log.debug('Resolving dependencies for: %s' % cdist_object.name)
        try:
            unresolved.append(cdist_object)
            deps = self.manager[cdist_object.name]
            for required_object in self.find_requirements_by_name(deps['after']):
                self.log.debug("Object %s requires %s", cdist_object, required_object)
                if required_object not in resolved:
                    if required_object in unresolved:
                        error = exceptions.CircularReferenceError(cdist_object, required_object)
                        self.log.error('%s: %s', error, pprint.pformat(self._dependencies))
                        raise error
                    self._resolve_object_dependencies(required_object, resolved, unresolved)
            resolved.append(cdist_object)
            unresolved.remove(cdist_object)
        except exceptions.RequirementNotFoundError as e:
            raise exceptions.CdistObjectError(cdist_object, "requires non-existing " + e.requirement)

    def __iter__(self):
        """Iterate over all unique objects and yield them in the correct order.
        """
        iterable = itertools.chain(*self.dependencies.values())
        # Keep record of objects that have already been seen
        seen = set()
        seen_add = seen.add
        for cdist_object in itertools.filterfalse(seen.__contains__, iterable):
            seen_add(cdist_object)
            yield cdist_object


if __name__ == '__main__':
    dpm = DependencyManager('/tmp/dpm')
    dpm.after('__file/tmp/bar/file', '__directory/tmp/bar')
    dpm.before('__directory/tmp/foo', '__file/tmp/foo/file')
    with dpm('__file/tmp/bar/file') as db:
        print(db)
    with dpm('__directory/tmp/foo') as db:
        print(db)

