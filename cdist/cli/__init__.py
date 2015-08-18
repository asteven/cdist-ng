import os
import sys
import itertools
import logging

import pkg_resources

import click
from click.utils import make_str
from click_plugins import with_plugins


def get_profile_path(path):
    profile_path = path
    if os.path.exists(profile_path):
        for suffix in itertools.count(1):
            possible_profile_path = '{0}_{1}'.format(profile_path, suffix)
            if not os.path.exists(possible_profile_path):
                profile_path = possible_profile_path
                break
    return profile_path


def with_cprofile(func):
    import cProfile
    def profiled_func(*args, **kwargs):
        profile_dir = os.path.expanduser('~/tmp/cdist-profile')
        prog_name = make_str(os.path.basename(
                sys.argv and sys.argv[0] or __file__))
        if prog_name.startswith('__'):
            profile_file = [prog_name]
            if len(sys.argv) > 1:
                maybe_object_id = sys.argv[1]
                if not maybe_object_id.startswith('--'):
                    object_id = maybe_object_id
                    profile_file.append(object_id.replace('/', '#'))
            profile_file = '-'.join(profile_file)
        else:
            profile_file = prog_name
        profile_path = get_profile_path(os.path.join(profile_dir, profile_file))
        print('profile_path: '+ profile_path)
        #profile = cProfile.run('runit()', profile_path)
        profile = cProfile.Profile()
        try:
            profile.enable()
            result = func(*args, **kwargs)
            profile.disable()
            return result
        finally:
            #profile.print_stats()
            profile.dump_stats(profile_path)
    return profiled_func


class SubfolderMultiCommand(click.MultiCommand):
    '''Loads subcommands from subfolder.
    '''

    @property
    def command_sources(self):
        _sources = [commands_folder]
        if 'CDIST_INTERNAL' in os.environ:
            _sources.append(internal_commands_folder)
        return _sources

    def list_commands(self, ctx):
        rv = []
        for folder in self.command_sources:
            for filename in os.listdir(folder):
                if filename.endswith('.py'):
                    cmd_name = filename[:-3].replace('_', '-')
                    rv.append(cmd_name)
        rv.sort()
        return rv

    def get_command(self, ctx, cmd_name):
        ns = {}
        name = cmd_name.replace('-', '_')
        for folder in self.command_sources:
            fn = os.path.join(folder, name + '.py')
            if os.path.exists(fn):
                with open(fn) as f:
                    code = compile(f.read(), fn, 'exec')
                    eval(code, ns, ns)
                return ns['main']

    def main(self, **kwargs):
        prog_name = kwargs.get('prog_name', None)
        if prog_name is None:
            prog_name = make_str(os.path.basename(
                sys.argv and sys.argv[0] or __file__))
        if prog_name.startswith('__'):
            # inject `emulator` subcommand to handle cdist object creation
            kwargs['prog_name'] = 'cdist'
            kwargs['args'] = ['emulator', prog_name] + sys.argv[1:]
        return super().main(**kwargs)


def cdist_command(func):
    # Discover and merge commands from entry points
    entry_point_names = ['cdist.cli.commands']
    if 'CDIST_INTERNAL' in os.environ:
        entry_point_names.append('cdist.cli.internal_commands')
    entry_points = []
    for entry_point in entry_point_names:
        entry_points += pkg_resources.iter_entry_points(entry_point)

    # Add decorators
    func = click.group()(func)
    func = with_plugins(entry_points)(func)
    if 'CDIST_PROFILE' in os.environ:
        func = with_cprofile(func)
    return func


@cdist_command
@click.option('--verbose', '-v', 'log_level', flag_value='info', help='set log level to info', envvar='__cdist_log_level')
@click.option('--debug', '-d', 'log_level', flag_value='debug', help='set log level to debug', envvar='__cdist_log_level')
@click.pass_context
#def main(ctx, verbose, debug):
def main(ctx, log_level):
    """Your system management swiss army knife."""
    # configure logger and store it in the context
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s', stream=sys.stderr)
    log = logging.getLogger('cdist')
    if log_level:
        log.setLevel(getattr(logging, log_level.upper()))
    setattr(ctx, 'obj', {})
    ctx.obj['log'] = log
    #log.debug('cdist main ctx.args: {0}'.format(ctx.args))
    #log.debug('cdist main ctx.params: {0}'.format(ctx.params))


if __name__ == '__main__':
    main()
