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
import glob
import shutil
import asyncio
import subprocess
import logging
log = logging.getLogger(__name__)


class Base(object):

    def __init__(self, runtime):
        self.runtime = runtime

    @asyncio.coroutine
    def call(self, *args, timeout=None, **kwargs):
        """asyncio compatible implementation of subprocess.call
        """
        process = yield from self.exec(*args, **kwargs)
        try:
            if timeout is None:
                returncode = yield from process.wait()
            else:
                task = asyncio.async(process.wait())
                returncode = yield from asyncio.wait_for(task, timeout)
            return returncode
        except:
            process.kill()
            yield from process.wait()
            raise

    @asyncio.coroutine
    def check_call(self, *args, **kwargs):
        """asyncio compatible implementation of subprocess.check_call
        """
        returncode = yield from self.call(*args, **kwargs)
        if returncode:
            command = kwargs.get("args")
            if command is None:
                command = args[0]
            raise subprocess.CalledProcessError(returncode, command)

    @asyncio.coroutine
    def check_output(self, *args, timeout=None, **kwargs):
        """asyncio compatible implementation of subprocess.check_output
        """
        if 'stdout' in kwargs:
            raise ValueError('stdout argument not allowed, it will be overridden.')
        if 'input' in kwargs:
            if 'stdin' in kwargs:
                raise ValueError('stdin and input arguments may not both be used.')
            inputdata = kwargs['input']
            del kwargs['input']
            kwargs['stdin'] = subprocess.PIPE
        else:
            inputdata = None

        process = yield from self.exec(*args, stdout=subprocess.PIPE, **kwargs)
        try:
            if timeout is None:
                output, unused_err = yield from process.communicate(inputdata)
            else:
                task = asyncio.async(process.communicate(inputdata))
                output, unused_err = yield from asyncio.wait_for(task, timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            output, unused_err = yield from process.communicate()
            raise subprocess.TimeoutExpired(process.args, timeout, output=output)
        except:
            process.kill()
            yield from process.wait()
            raise
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command, output=output)
        return output


class Remote(Base):

    @asyncio.coroutine
    def mkdir(self, path):
        """Create directory on the target."""
        log.debug("Remote mkdir: %s", path)
        yield from self.check_call(["mkdir", "-p", path])

    @asyncio.coroutine
    def rmdir(self, path):
        """Remove directory on the target."""
        log.debug("Remote rmdir: %s", path)
        yield from self.check_call(["rm", "-rf",  path])

    @asyncio.coroutine
    def transfer(self, source, destination):
        """Transfer a file or directory to the target."""
        log.debug("Remote transfer: %s -> %s", source, destination)
        yield from self.rmdir(destination)
        if os.path.isdir(source):
            yield from self.mkdir(destination)
            # copy files in parallel
            tasks = []
            for f in glob.glob1(source, '*'):
                source_file = os.path.join(source, f)
                destination_file = os.path.join(destination, f)
                task = asyncio.async(self.copy(source_file, destination_file))
                tasks.append(task)
            if tasks:
                done, pending = yield from asyncio.wait(tasks)
                assert not pending
        else:
            yield from self.copy(source, destination)

    @asyncio.coroutine
    def exec(self, command, **kwargs):
        """Run the given command with the configured remote-exec script.
        """
        with (yield from self.runtime.exec_semaphore):
            log.debug('exec: command=%s, kwargs=%s', command, kwargs)
            _command = [self.runtime.path['remote']['exec']]

            # export target_host for use in remote-{exec,copy} scripts
            os_environ = os.environ.copy()
            os_environ.update(self.runtime.environ)

            # can't pass environment to remote side, so prepend command with
            # variable declarations
            if 'env' in kwargs:
                env = kwargs.pop('env')
                remote_env = ["%s=%s" % item for item in env.items()]
                _command.extend(remote_env)

            _command.extend(command)
            code = ' '.join(_command)
            process = yield from asyncio.create_subprocess_shell(code, env=os_environ, **kwargs)
            return process

    @asyncio.coroutine
    def copy(self, source, destination):
        """Copy the given source to destination using the configured
        remote-copy script.
        """
        with (yield from self.runtime.copy_semaphore):
            log.debug('copy: %s -> %s', source, destination)

            # export target_host for use in remote-{exec,copy} scripts
            os_environ = os.environ.copy()
            os_environ.update(self.runtime.environ)

            code = '%s %s %s' % (self.runtime.path['remote']['copy'], source, destination)
            process = yield from asyncio.create_subprocess_shell(code, stdout=asyncio.subprocess.PIPE, env=os_environ)
            exit_code = yield from process.wait()
            log.debug('copy exit code: %d', exit_code)


class Local(Base):

    @asyncio.coroutine
    def mkdir(self, path):
        """Create directory on the local host."""
        log.debug("Local mkdir: %s", path)
        # Make this a generator for API compability
        yield
        os.makedirs(path, exist_ok=True)

    @asyncio.coroutine
    def rmdir(self, path):
        """Remove directory on the local host."""
        log.debug("Local rmdir: %s", path)
        # Make this a generator for API compability
        yield
        shutil.rmtree(path)

    @asyncio.coroutine
    def exec(self, command, **kwargs):
        """Run the given command locally.
        """
        log.debug('exec: command=%s, kwargs=%s', command, kwargs)

        # export target_host for use in remote-{exec,copy} scripts
        os_environ = os.environ.copy()
        os_environ.update(self.runtime.environ)

        # Add user supplied environment variables if any
        if 'env' in kwargs:
            env = kwargs.pop('env')
            os_environ.update(env)

        code = ' '.join(command)
        process = yield from asyncio.create_subprocess_shell(code, env=os_environ, **kwargs)
        return process
