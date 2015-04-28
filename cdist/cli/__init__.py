import os
import sys
import logging

import click
from click.utils import make_str


commands_folder = os.path.join(os.path.dirname(__file__), 'commands')
internal_commands_folder = os.path.join(os.path.dirname(__file__), 'commands', 'internal')


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


@click.command(cls=SubfolderMultiCommand)
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
