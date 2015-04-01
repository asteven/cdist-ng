import logging
import sys
import subprocess

import click


@click.command(name='log')
@click.argument('level', nargs=1)
@click.argument('message', nargs=-1)
@click.pass_context
def main(ctx, level, message):
    '''Log the given MESSAGE at the given LEVEL
    '''
    log = ctx.obj['log']
    getattr(log, level)(' '.join(message))
