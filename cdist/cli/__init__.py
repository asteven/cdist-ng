import os
import sys
import logging

import click


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


@click.command(cls=SubfolderMultiCommand)
@click.option('--verbose', '-v', is_flag=True, help='set log level to info')
@click.option('--debug', '-d', is_flag=True, help='set log level to debug')
@click.pass_context
def main(ctx, verbose, debug):
    '''Your system management swiss army knife.'''
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s', stream=sys.stderr)
    log = logging.getLogger('chaos')
    if verbose:
        log.setLevel(logging.INFO)
    if debug:
        log.setLevel(logging.DEBUG)
    #if not foo:
    #    ctx.fail('You must give at least one FOO to operate on.')
    setattr(ctx, 'obj', {})
    ctx.obj['log'] = log
    log.debug('ctx.args: {0}'.format(ctx.args))
    log.debug('ctx.params: {0}'.format(ctx.params))


if __name__ == '__main__':
    main()
