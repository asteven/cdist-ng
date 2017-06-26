import sys
import os
import tempfile
import shutil
import asyncio
import asyncio.subprocess
import glob
import json

import click

from cdist import exceptions
from cdist import session
from cdist import runtime

from cdist.cli.utils import comma_delimited_string_to_set



class LocalRuntime(runtime.Runtime):
    """A Runtime that runs global explorers locally using sh instead of ssh.
    """

    async def run_global_explorer(self, name):
        """Run the given global explorer and return it's output.
        """
        env = {
            '__explorer': self.path['local']['explorer'],

        }
        explorer = os.path.join(self.path['local']['explorer'], name)
        result = await self.local.check_output([explorer], env=env)
        return result.decode('ascii').rstrip()

    async def run_global_explorers(self, explorer_names=None):
        """Run all global explorers and save their output in the session.
        """
        self.log.debug('Running global explorers locally')
        # execute explorers in parallel
        tasks = []
        if not explorer_names:
            explorer_names = glob.glob1(self.path['local']['explorer'], '*')
        for name in explorer_names:
            task = self.loop.create_task(self.run_global_explorer(name))
            task.name = name
            tasks.append(task)
        if tasks:
            results = await asyncio.gather(*tasks)
            for index,name in enumerate(explorer_names):
                self.target['explorer'][name] = results[index]
            await self.sync_target('explorer')


@click.command(name='explore')
@click.option('-e', '--explorer', multiple=True, callback=comma_delimited_string_to_set,
    help='Run the given explorers instead of all of them.')
@click.option('-j', '--json', 'json_output', is_flag=True, help='Output result as json instead of text.')
@click.argument('target', nargs=1, default='__local__')
@click.pass_context
def main(ctx, explorer, json_output, target):
    """Explore the given target.

    TARGET is expected to be the hostname of the target to work on.
    If no TARGET is given the target is set to be localhost.

    The --explorer option can be given multiple times. Additionally each
    of the values of this option can be a comma seperated string.
    """
    log = ctx.obj['log']
    log.debug('ctx.args: {0}'.format(ctx.args))
    log.debug('ctx.params: {0}'.format(ctx.params))

    log.debug('target: {0}'.format(target))

    # Validate options
    _session = session.Session()
    _session.add_conf_dir(os.path.expanduser('~/vcs/cdist/cdist/conf'))
    _session.add_conf_dir(os.path.expanduser('~/.cdist'))
    _session.add_conf_dir(os.path.expanduser('~/vcs/cdist-ng/conf'))

    local_session_dir = tempfile.mkdtemp(prefix='cdist-session-')

    _session.add_target(target)
    _session.to_dir(local_session_dir)
    _target = _session.targets[0]
    remote_session_dir = _session['remote-session-dir']

    loop = asyncio.get_event_loop()

    try:
        if target is not '__local__':
            _runtime = runtime.Runtime(_target, local_session_dir, remote_session_dir, loop=loop)
            loop.run_until_complete(_runtime.initialize())
        else:
            _runtime = LocalRuntime(_target, local_session_dir, remote_session_dir, loop=loop)
        loop.run_until_complete(_runtime.run_global_explorers(explorer_names=explorer))
        if json_output:
            click.echo(json.dumps(_target['explorer']))
        else:
            for name,value in _target['explorer'].items():
                for line in value.split('\n'):
                    click.echo('{0}: {1}'.format(name, line))
    except exceptions.CdistError as e:
        log.error(str(e))
        raise
        ctx.exit(1)
    finally:
        loop.close()
