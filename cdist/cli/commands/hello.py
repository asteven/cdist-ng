import logging
import sys
import subprocess

import click


@click.group(name='hello')
@click.pass_context
def main(ctx):
    '''I'll say something
    '''


@main.command()
@click.pass_context
def world(ctx):
    '''I'll say hello world
    '''
    print('hello world')

@main.command()
@click.pass_context
def moon(ctx):
    '''I'll say hello moon
    '''
    print('hello moon')

@main.command()
@click.argument('name', nargs=1)
@click.pass_context
def name(ctx, name):
    '''I'll say hello to you
    '''
    print('hello '+ name)
