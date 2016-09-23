import logging
import sys
import time
import shlex
import asyncio
import asyncio.subprocess

import click


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


async def run(mode, count, code):
    tasks = [asyncio.ensure_future(run_code(mode, code)) for i in range(0, count)]
    print('tasks: {0}'.format(tasks))
    try:
        while tasks:
            done, pending = await asyncio.wait(
                tasks, timeout=1, return_when=asyncio.FIRST_COMPLETED
            )
            print('done: {0}'.format(done))
            print('pending: {0}'.format(pending))
            if not done:
                break
            for t in done:
                print('t: {0}'.format(t))
                tasks.remove(t)
                result = t.result()
                print(result.decode('ascii').rstrip())
    except Exception as e:
        print('got exception:', e, flush=True)


@click.command(name='run')
@click.option('--mode', type=click.Choice(['exec', 'shell']), default='shell')
@click.option('--count', type=int, default=1)
#@click.argument('code', nargs=1)
@click.argument('code', nargs=-1)
@click.pass_context
def main(ctx, mode, count, code):
    '''I'll run the given executable or shell code
    '''
    print(code)
    time_start = time.time()
    loop = asyncio.get_event_loop()
    #for i in range(0, count):
    #    asyncio.async(run_code(mode, code))
#    loop.run_until_complete(asyncio.wait(
#        [run_code(mode, code) for i in range(0, count)]
#    ))
    loop.run_until_complete(run(mode, count, code))
    time_end = time.time()
    print('total processing time %s' % (time_end - time_start))
    loop.close()
