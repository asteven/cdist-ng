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
        # FIXME: disabled caching due to concurrent access issues
        return DependencyDatabase(self.base_path, key)
        #try:
        #    return self.__cache[key]
        #except KeyError:
        #    db = DependencyDatabase(self.base_path, key)
        #    self.__cache[key] = db
        #    return db

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
        with DependencyDatabase(self.base_path, me) as db:
            _list = db['before']
            if not other in _list:
                _list.append(other)

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
        self['require'] = []
        self['after'] = []
        self['before'] = []
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
        return '<{0.name} require:{0[require]} after:{0[after]} before:{0[before]} auto:{0[auto]}>'.format(self)

    # context manager interface
    def __enter__(self):
        self.load()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.save()
        # we don't handle errors ourself
        return False


if __name__ == '__main__':
    dpm = DependencyManager('/tmp/dpm')
    dpm.after('__file/tmp/bar/file', '__directory/tmp/bar')
    dpm.before('__directory/tmp/foo', '__file/tmp/foo/file')
    with dpm('__file/tmp/bar/file') as db:
        print(db)
    with dpm('__directory/tmp/foo') as db:
        print(db)
