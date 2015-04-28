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
import tempfile
import urllib
import time
import base64
import logging
log = logging.getLogger(__name__)

import cconfig


class TransportStackType(cconfig.schema.CconfigType):
    _type = 'transport-stack'

    def from_path(self, base_path):
        _list = []
        try:
            for path, dirs, files in os.walk(base_path):
                if not files:
                    continue
                link = os.path.join(path, files[0])
                source = os.readlink(link)
                target = os.path.split(source)[0]
                _list.append(target)
        except EnvironmentError:
            pass
        finally:
            return _list

    def to_path(self, path, _list):
        cwd = os.getcwd()
        if not os.path.isdir(path):
            os.mkdir(path)
        os.chdir(path)
        for target in _list:
            name = os.path.basename(target)
            if not os.path.isdir(name):
                os.mkdir(name)
            os.chdir(name)
            for child in os.listdir(target):
                source = os.path.join(target, child)
                destination = os.path.basename(source)
                if os.path.islink(destination):
                    os.unlink(destination)
                os.symlink(source, destination)
        os.chdir(cwd)


class Target(dict):
    schema_decl = (
        # path, type, subschema
        ('explorer', dict),
        ('messages', list),
        ('object-marker', str),
        ('remote-state-dir', str),
        ('target', dict, (
            ('scheme', str),
            ('user', str),
            ('host', str),
            ('port', int),
            ('path', str),
            ('query', str),
            ('fragment', str),
        )),
        ('transport', 'transport-stack'),
        ('url', str),
    )
    schema = cconfig.Schema(schema_decl)

    @classmethod
    def from_dir(cls, path):
        """Creates a cdist target instance from an existing directory.
        """
        obj = cls()
        return cconfig.from_dir(path, obj=obj, schema=obj.schema)

    def to_dir(self, path):
        """Store this target instance in a directory for use by shell scripts.
        """
        cconfig.to_dir(path, self, schema=self.schema)

    def __init__(self, transports=None, target=None):
        super().__init__(cconfig.from_schema(self.schema))
        self.available_transports = transports
        self['object-marker'] = tempfile.mktemp(prefix='.cdist-', dir='')
        if target:
            self.set_target(target)

    def set_target(self, target):
        """Set the target we are working on.

        Parses the target uri into it's parts and saves them in the target dict.
        Populate the transport-stack based on the target uri's scheme.
        """
        # TODO: test and normalize into valid url that urllib understands
        # TODO: if it is not a url, if it does not look like a path assume it to be a hostname
        self['url'] = target
        pr = urllib.parse.urlparse(target)
        target = {
            'scheme': pr.scheme,
            # FIXME: make default user configurable
            'user': pr.username or 'root',
            'host': pr.hostname,
            'port': pr.port,
            'path': pr.path,
            'query': pr.query,
            'fragment': pr.fragment,
        }
        if not pr.hostname and not pr.path[0] in ('.', '/'):
            target['host'] = pr.path
            target['path'] = None
        self['target'] = target
        self['transport'] = [self.available_transports[key] for key in self.transports]

    @property
    def identifier(self):
        """Return an identifier for this target which is usable as a folder or
        file name.
        """
        if self['url']:
            return base64.urlsafe_b64encode(self['url'].encode()).decode()
        else:
            return 'anonymous'

    @property
    def transports(self):
        if self['target']['scheme']:
            return self['target']['scheme'].split('+')
        else:
            return ['ssh']

    @property
    def remote_exec(self):
        transports_path = os.path.join('transport', *self.transports)
        return os.path.join(transports_path, 'exec')

    @property
    def remote_copy(self):
        transports_path = os.path.join('transport', *self.transports)
        return os.path.join(transports_path, 'copy')
