import sys
import os
import tempfile

import click

from cdist import session
from cdist.cli.utils import comma_delimited_string_to_set


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
    if not include_tag.isdisjoint(exclude_tag):
        ctx.fail('Options \'include-tag\' and \'exclude-tag\' have conflicting values: %s vs %s' % (include_tag, exclude_tag))

    _session = session.Session()
    _session.add_conf_dir(os.path.expanduser('~/.cdist'))
    _session.add_conf_dir(os.path.expanduser('~/vcs/cdist-ng/conf'))
    #url = 'ssh+sudo+chroot://root@netboot-dev.ethz.ch/local/nfsroot/preos'
    for url in target:
        # TODO: test and normalize into valid url that urllib understands
        _session.add_target(url)

    _session_dir = tempfile.mkdtemp(prefix='cdist-session-')
    print(_session_dir)
    _session.to_dir(_session_dir)
