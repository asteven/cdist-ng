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

import sys
import os
import urllib
import time
import socket
import logging
log = logging.getLogger(__name__)

import cconfig

import cdist.target


class ListOfSymlinkTargets(cconfig.schema.CconfigType):
    _type = 'list-of-symlink-targets'

    def from_schema(self):
        return []

    def from_path(self, path):
        _list = []
        try:
            for item in os.listdir(path):
                _list.append(os.readlink(item))
        except EnvironmentError:
            pass
        finally:
            return _list

    def to_path(self, path, _list):
        cwd = os.getcwd()
        if not os.path.isdir(path):
            os.mkdir(path)
        os.chdir(path)
        for source in _list:
            destination = os.path.basename(source)
            os.symlink(source, destination)
        os.chdir(cwd)


class MappingOfSymlinkTargets(cconfig.schema.CconfigType):
    _type = 'mapping-of-symlink-targets'

    def from_schema(self):
        return {}

    def from_path(self, path):
        cwd = os.getcwd()
        mapping = {}
        try:
            os.chdir(path)
            for key in os.listdir(path):
                mapping[key] = os.readlink(key)
        except EnvironmentError:
            pass
        finally:
            os.chdir(cwd)
            return mapping

    def to_path(self, path, mapping):
        cwd = os.getcwd()
        if not os.path.isdir(path):
            os.mkdir(path)
        os.chdir(path)
        for key, link in mapping.items():
            if os.path.islink(key):
                os.unlink(key)
            os.symlink(link, key)
        os.chdir(cwd)


class Session(dict):
    schema_decl = (
        # path, type, subschema
        ('bin', 'mapping-of-symlink-targets'),
        ('conf', 'mapping', (
            ('explorer', 'mapping-of-symlink-targets'),
            ('file', 'mapping-of-symlink-targets'),
            ('manifest', 'mapping-of-symlink-targets'),
            ('transport', 'mapping-of-symlink-targets'),
            ('type', 'mapping-of-symlink-targets'),
        )),
        ('conf-dirs', list),
        ('exec-path', str),
        ('remote-cache-dir', str),
        ('session-id', str),
    )
    schema = cconfig.Schema(schema_decl)

    @classmethod
    def from_dir(cls, path):
        """Creates a cdist session instance from an existing
        directory.
        """
        obj = cls()
        obj = cconfig.from_dir(path, obj=obj, schema=obj.schema)

        # assume nested targets directory
        targets_base_path = os.path.join(path, 'targets')
        for identifier in os.listdir(targets_base_path):
            target_path = os.path.join(targets_base_path, identifier)
            target = cdist.target.Target.from_dir(target_path)
            obj.targets.append(target)

        return obj

    def to_dir(self, path):
        """Store this session instance in a directory for use by shell scripts.
        """
        cconfig.to_dir(path, self, schema=self.schema)

        targets_base_path = os.path.join(path, 'targets')
        if not os.path.isdir(targets_base_path):
            os.mkdir(targets_base_path)
        for target in self.targets:
            target_path = os.path.join(targets_base_path, target.identifier)
            target.to_dir(target_path)

    def __init__(self, targets=None, exec_path=None):
        super().__init__(cconfig.from_schema(self.schema))
        self['session-id'] = time.strftime('%Y-%m-%d-%H:%M:%S-{0}-{1}'.format(
            socket.getfqdn(), os.getpid())
        )
        self['exec-path'] = exec_path or sys.argv[0]
        self['remote-cache-dir'] = os.path.join('/var/cache/cdist', self['session-id'])
        self.targets = targets or []

    def add_conf_dir(self, conf_dir):
        """Add a conf dir to this session.

        Merges the explorer, manifest, type and other sub directories in the
        given conf_dir with the allready known ones.
        """
        if conf_dir in self['conf-dirs']:
            return
        self['conf-dirs'].append(conf_dir)

        # Collect and merge conf dirs
        for sub_dir in self.schema['conf'].schema.keys():
            current_dir = os.path.join(conf_dir, sub_dir)
            # Allow conf dirs to contain only partial content
            if not os.path.exists(current_dir):
                continue
            for entry in os.listdir(current_dir):
                source = os.path.abspath(os.path.join(conf_dir, sub_dir, entry))
                self['conf'].setdefault(sub_dir, {})
                self['conf'][sub_dir][entry] = source

        # Link emulator to types
        source = os.path.abspath(self['exec-path'])
        for _type_name in self['conf']['type'].keys():
            self['bin'][_type_name] = source

    def add_target(self, target_url):
        """Add a target which will be processed as part of this session.
        """
        target = cdist.target.Target(self['conf']['transport'], target_url)
        self.targets.append(target)
