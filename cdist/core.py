# -*- coding: utf-8 -*-
#
# 2015 Steven Armstrong (steven-cdist at armstrong.cc)
#
# This file is part of cdist.
#
# cdist is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cdist is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cdist. If not, see <http://www.gnu.org/licenses/>.
#
#

import os

import cconfig


from . import exceptions


class CdistType(dict):
    """Represents a cdist type.
    """

    @classmethod
    def from_dir(cls, path, name=None):
        """Load a cdist type from the given directory.

        If no explicit name is given assume the last segment of the given path
        to be the name of the type.
        """
        type_name = name or os.path.split(path)[1]
        obj = cls(type_name)
        return cconfig.from_dir(path, obj=obj, schema=obj.schema)

    schema_decl = (
        # path, type, subschema
        ('explorer', 'listdir'),
        ('install', bool),
        ('parameter', dict, (
            ('required', list),
            ('required_multiple', list),
            ('optional', list),
            ('optional_multiple', list),
            ('boolean', list),
            ('default', dict),
        )),
        ('singleton', bool),
    )

    schema = cconfig.Schema(schema_decl)

    def __init__(self, name):
        super().__init__(cconfig.from_schema(self.schema))
        self.name = name
        self.__object_schema = None

    @property
    def object_schema(self):
        if self.__object_schema is None:
            parameters = []
            # use proper cconfig type for each parameter
            for parameter_type, values in self['parameter'].items():
                if parameter_type == 'default':
                    continue
                if parameter_type == 'boolean':
                    _type = bool
                elif parameter_type in ('required_multiple', 'optional_multiple'):
                    _type = list
                else:
                    _type = str
                for name in values:
                    parameters.append((name, _type))
            schema_decl = (
                # path, type, subschema
                ('autorequire', list),
                ('changed', bool),
                ('code-local', str),
                ('code-remote', str),
                ('explorer', dict, ((name, str) for name in self['explorer'])),
                ('object-id', str),
                ('parameter', dict, tuple(parameters)),
                ('require', list),
                ('source', list),
                ('state', str),
                ('tags', dict, (
                    ('if', list),
                    ('not-if', list),
                )),
                ('type', str),
            )
            self.__object_schema = cconfig.Schema(schema_decl)
        return self.__object_schema

    def __call__(self, object_id=None, parameters=None, tags=None):
        """Create and return a new cdist object. This can be thought of as
        being an instance of this cdist type.
        """
        _object = CdistObject(self.object_schema, type_name=self.name, object_id=object_id)
        if parameters:
            _object['parameter'].update(parameters)
        if tags:
            _object['tags'].update(tags)
        return _object

    def object_from_dir(self, path):
        """Load a cdist object instance from an existing directory.
        """
        _object = CdistObject.from_dir(self.object_schema, path)
        return _object

    def __repr__(self):
        return '<CdistType %s>' % self.name

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.name == other.name

    def __lt__(self, other):
        return isinstance(other, self.__class__) and self.name < other.name


class CdistObject(dict):
    """Represents a cdist object.
    """

    @classmethod
    def from_dir(cls, schema, path):
        """Load a cdist object instance from the given directory.
        """
        obj = cls(schema)
        return cconfig.from_dir(path, obj=obj, schema=obj.schema)

    def to_dir(self, path, keys=None):
        """Store this cdist object instance in the given directory.
        """
        cconfig.to_dir(path, self, schema=self.schema, keys=keys)

    def __init__(self, schema, type_name=None, object_id=None):
        self.schema = schema
        super().__init__(cconfig.from_schema(self.schema))
        self['type'] = type_name
        self['object-id'] = object_id

    @property
    def name(self):
        if self['object-id']:
            return os.path.join(self['type'], self['object-id'])
        else:
            return self['type']

    def __repr__(self):
        return '<CdistObject %s>' % self.name

#    def __eq__(self, other):
#        """define equality as 'name is the same'"""
#        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def __lt__(self, other):
        return isinstance(other, self.__class__) and self.name < other.name

    @staticmethod
    def split_name(object_name):
        """split_name('__type_name/the/object_id') -> ('__type_name', 'the/object_id')

        Split the given object name into it's type and object_id parts.

        """
        type_name = object_name.split(os.sep)[0]
        object_id = os.sep.join(object_name.split(os.sep)[1:])
        return type_name, object_id

    @staticmethod
    def join_name(type_name, object_id):
        """join_name('__type_name', 'the/object_id') -> '__type_name/the/object_id'

        Join the given type name and object id into a object name.

        """
        parts = [type_name]
        if object_id:
            parts.append(object_id)
        return os.sep.join(parts)

    @staticmethod
    def sanitise_object_id(object_id):
        """Remove a single leading and trailing slash.
        """

        # Allow empty object id for singletons
        if object_id:
            # Remove leading slash
            if object_id[0] == '/':
                object_id = object_id[1:]

            # Remove trailing slash
            if object_id[-1] == '/':
                object_id = object_id[:-1]
        return object_id

    @staticmethod
    def validate_object_id(object_id):
        """Validate the given object_id and raise IllegalObjectIdError if it's not valid.
        """
        if object_id:
            if '//' in object_id:
                raise exceptions.IllegalObjectIdError(object_id, 'object_id may not contain //')
            if object_id == '.':
                raise exceptions.IllegalObjectIdError(object_id, 'object_id may not be a .')

    @staticmethod
    def sanitise_object_name(object_name):
        """Remove a single leading and trailing slash.
        """
        type_name,object_id = CdistObject.split_name(object_name)

        # Allow empty object id for singletons
        if object_id:
            # Remove leading slash
            if object_id[0] == '/':
                object_id = object_id[1:]

            # Remove trailing slash
            if object_id[-1] == '/':
                object_id = object_id[:-1]
        return CdistObject.join_name(type_name, object_id)

    @staticmethod
    def validate_object_name(object_name):
        """Validate the given object_name and raise IllegalObjectIdError if it's not valid.
        """
        type_name,object_id = CdistObject.split_name(object_name)
        CdistObject.validate_object_id(object_id)

