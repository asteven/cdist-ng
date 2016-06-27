import sys
import os
import tempfile
import asyncio
import pprint

import click

from cdist import exceptions
from cdist import session
from cdist import runtime
from cdist import manager

from cdist.cli.utils import comma_delimited_string_to_set


def log(msg):
    print(msg, flush=True)


async def configure_target(_runtime):
    try:
        _runtime.log.info('configure_target')
        log('initialize')
        await _runtime.initialize()
        log('run_global_explorers')
        await _runtime.run_global_explorers()
        log('run_initial_manifest')
        await _runtime.run_initial_manifest()
        log('process_objects')
        await _runtime.process_objects()
        log('finalize')
        await _runtime.finalize()
        log('return')
        return _runtime
    except Exception as e:
        log(str(e))
        raise e


@click.command(name='config')
@click.option('-m', '--manifest', type=click.File('r'),
    help='Path to a cdist manifest or \'-\' to read from stdin.')
@click.option('--only-tag', multiple=True, callback=comma_delimited_string_to_set,
    help='Only apply objects with the given tag.')
@click.option('--include-tag', multiple=True, callback=comma_delimited_string_to_set,
    help='Apply untagged objects and those with the given tag.')
@click.option('--exclude-tag', multiple=True, callback=comma_delimited_string_to_set,
    help='Apply all objects except those with the given tag.')
@click.option('--dry-run', '-n', is_flag=True, default=False, help='Do not execute code.')
@click.option('-s', '--sequential', 'operation_mode', flag_value='sequential',
    default=True, help='Operate on multiple hosts sequentially (default).')
@click.option('-p', '--parallel', 'operation_mode', flag_value='parallel',
    help='Operate on multiple hosts in parallel.')
@click.argument('target', nargs=-1)
@click.pass_context
def main(ctx, manifest, only_tag, include_tag, exclude_tag, dry_run, operation_mode, target):
    '''Configure the given targets.

    A TARGET is expected to be a hostname or url representing the target to work on.

    Each of the --*-tag option can be given multiple times. Additionally each
    of the values of these options can be a comma seperated strings.
    '''
    log = ctx.obj['log']
    log.debug('ctx.args: {0}'.format(ctx.args))
    log.debug('ctx.params: {0}'.format(ctx.params))

    if not target:
        log.debug('no target given, nothing to do, fail gracefully')
        sys.exit(0)


    # Validate options
    if only_tag and include_tag:
        ctx.fail('Use either \'only-tag\' or \'include-tag\' but not both.')
    if not only_tag.isdisjoint(exclude_tag):
        ctx.fail('Options \'only-tag\' and \'exclude-tag\' have conflicting values: %s vs %s' % (only_tag, exclude_tag))
    if not include_tag.isdisjoint(exclude_tag):
        ctx.fail('Options \'include-tag\' and \'exclude-tag\' have conflicting values: %s vs %s' % (include_tag, exclude_tag))


    tags = {
        'exclude': exclude_tag,
        'include': include_tag,
        'only': only_tag,
    }
    log.debug('tags: {0}'.format(tags))

    if manifest is not None:
        manifest_content = manifest.read()
    else:
        manifest_content = None
    _session = session.Session(manifest=manifest_content, tags=tags)
    _session.add_conf_dir(os.path.expanduser('~/vcs/cdist/cdist/conf'))
    _session.add_conf_dir(os.path.expanduser('~/.cdist-hpc'))
    _session.add_conf_dir(os.path.expanduser('~/vcs/cdist-ng/conf'))

    #import pprint
    #pprint.pprint(_session)

    # override remote-session-dir for testing
    #_remote_session_dir = tempfile.mkdtemp(prefix='cdist-remote-')
    #_session['remote-session-dir'] = os.path.join(_remote_session_dir, _session['session-id'])


    #url = 'ssh+sudo+chroot://root@netboot-dev.ethz.ch/local/nfsroot/preos'
    for url in target:
        _session.add_target(url)

    local_session_dir = tempfile.mkdtemp(prefix='cdist-session-')
    print(local_session_dir)
    _session.to_dir(local_session_dir)

    remote_session_dir = _session['remote-session-dir']

    loop = asyncio.get_event_loop()

    # Create a list of asyncio tasks, one for each runtime.
    tasks = []
    for _target in _session.targets:
        _runtime = runtime.Runtime(_target, local_session_dir, remote_session_dir, loop=loop)
        task = loop.create_task(configure_target(_runtime))
        tasks.append(task)

    # Execute the tasks in parallel using asyncio.
    try:
        results = []
        if tasks:
            results = loop.run_until_complete(asyncio.gather(*tasks))
    except exceptions.CdistError as e:
        log.error(str(e))
        raise
        ctx.exit(1)
    finally:
        loop.close()

