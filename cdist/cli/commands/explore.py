import sys
import os
import tempfile
import shutil
import asyncio
import asyncio.subprocess

import click

from cdist import exceptions
from cdist import session
from cdist import runtime

from cdist.cli.utils import comma_delimited_string_to_set


async def run_code(mode, code):
    if mode == 'exec':
        process = await asyncio.create_subprocess_exec(*code, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        return stdout
    elif mode == 'shell':
        cmd = ' '.join(code)
        process = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        return stdout


async def run(tasks, timeout=10):
    try:
        while tasks:
            done, pending = await asyncio.wait(
                tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                break
            for t in done:
                tasks.remove(t)
                result = t.result()
                value = result.decode('ascii').rstrip()
                for line in value.split('\n'):
                    print('{0}: {1}'.format(t.name, line))
    except Exception as e:
        print('got exception:', e, flush=True)


@click.command(name='explore')
@click.option('-e', '--explorer', multiple=True, callback=comma_delimited_string_to_set,
    help='Run the given explorers instead of all of them.')
@click.argument('target', nargs=1, default='__local__')
@click.pass_context
def main(ctx, explorer, target):
    """Explore the given target.

    TARGET is expected to be the hostname of the target to work on.
    If no TARGET is given the target is set to be localhost.

    The --explorer option can be given multiple times. Additionally each
    of the values of this option can be a comma seperated string.
    """
    log = ctx.obj['log']
    log.debug('ctx.args: {0}'.format(ctx.args))
    log.debug('ctx.params: {0}'.format(ctx.params))

    #if not target:
    #    target = []
    #    log.debug('no target given, nothing to do, fail gracefully')
    #    sys.exit(0)
    log.debug('target: {0}'.format(target))

    # Validate options
    _session = session.Session()
    _session.add_conf_dir(os.path.expanduser('~/vcs/cdist/cdist/conf'))
    _session.add_conf_dir(os.path.expanduser('~/.cdist'))
    _session.add_conf_dir(os.path.expanduser('~/vcs/cdist-ng/conf'))

    local_session_dir = tempfile.mkdtemp(prefix='cdist-session-')

    loop = asyncio.get_event_loop()

    if target is not '__local__':
        _session.add_target(target)
        _session.to_dir(local_session_dir)
        _target = _session.targets[0]
        remote_session_dir = _session['remote-session-dir']
        _runtime = runtime.Runtime(_target, local_session_dir, remote_session_dir, loop=loop)
        try:
            loop.run_until_complete(_runtime.initialize())
            loop.run_until_complete(_runtime.run_global_explorers(explorer_names=explorer))
            for name,value in _target['explorer'].items():
                for line in value.split('\n'):
                    click.echo('{0}: {1}'.format(name, line))
        except exceptions.CdistError as e:
            log.error(str(e))
            raise
            ctx.exit(1)
        finally:
            loop.close()
    else:
        # run explorers on the local machine without going though ssh
        _session_dir = tempfile.mkdtemp(prefix='cdist-session-')
        log.debug('session_dir: {0}'.format(_session_dir))
        _session.to_dir(_session_dir)

        explorer_path = os.path.join(_session_dir, 'conf/explorer')
        os.environ['__explorer'] = explorer_path

        mode = 'shell'
        tasks = []
        for name,executable in _session['conf']['explorer'].items():
            if explorer and name not in explorer:
                continue
            task = asyncio.async(run_code(mode,[executable]))
            task.name = name
            tasks.append(task)
        loop.run_until_complete(run(tasks))
        loop.close()
        #shutil.rmtree(_session_dir)
