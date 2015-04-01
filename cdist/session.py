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
import urllib
import time
import socket
import logging
log = logging.getLogger(__name__)

import cconfig

import cdist.runtime
import cdist.target


class CdistRuntimeType(cconfig.schema.CconfigType):
    _type = 'cdist-runtime'

    def from_path(self, path):
        return cdist.runtime.Runtime.from_dir(path)

    def to_path(self, path, runtime):
        runtime.to_dir(path)


class Session(dict):
    schema_decl = (
        # path, type, subschema
        ('conf-dirs', list),
        ('session-id', str),
    )
    schema = cconfig.Schema(schema_decl)

    @classmethod
    def from_dir(cls, path):
        """Creates a cdist session instance from an existing
        directory.
        """
        # assume nested runtime directory
        runtime_path = os.path.join(path, 'runtime')
        runtime = cdist.runtime.Runtime.from_dir(runtime_path)

        obj = cls(runtime)
        obj = cconfig.from_dir(path, obj=obj, schema=obj.schema)

        # assume nested targets directory
        targets_base_path = os.path.join(path, 'targets')
        for identifier in os.listdir(targets_base_path):
            target_path = os.path.join(targets_base_path, identifier)
            target = cdist.target.Target.from_dir(runtime, target_path)
            obj.targets.append(target)

        return obj

    def to_dir(self, path):
        """Store this session instance in a directory for use by shell scripts.
        """
        cconfig.to_dir(path, self, schema=self.schema)
        runtime_path = os.path.join(path, 'runtime')
        self.runtime.to_dir(runtime_path)
        # TODO: save targets to dir
        # TODO: what to use as target name for creating the folder
        #   hostname will not work for chroot or local folders
        targets_base_path = os.path.join(path, 'targets')
        os.mkdir(targets_base_path)
        for target in self.targets:
            target_path = os.path.join(targets_base_path, target.identifier)
            target.to_dir(target_path)

    def __init__(self, runtime=None, targets=None):
        super().__init__(cconfig.from_schema(self.schema))
        self['session-id'] = time.strftime('%Y-%m-%d-%H:%M:%S-{0}-{1}'.format(
            socket.getfqdn(), os.getpid())
        )
        self['exec-path'] = '/path/to/bin/cdist'
        remote_cache_dir = os.path.join('/var/cache/cdist', self['session-id'])
        self.runtime = runtime or cdist.runtime.Runtime(remote_cache_dir=remote_cache_dir, exec_path=self['exec-path'])
        self.targets = targets or []

    def add_conf_dir(self, conf_dir):
        """Add a conf dir to this sessions runtime environment.
        """
        if conf_dir in self['conf-dirs']:
            return
        self['conf-dirs'].append(conf_dir)
        self.runtime.add_conf_dir(conf_dir)

    def add_target(self, target_url):
        """Add a target which will be processed as part of this session.
        """
        target = cdist.target.Target(self.runtime, target_url)
        self.targets.append(target)
