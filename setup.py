from setuptools import setup, find_packages

name = 'cdist-ng'

setup(
    name=name,
    version='0.1',
    author='Steven Armstrong',
    author_email='steven-%s@armstrong.cc' % name,
    description='cdist next generation',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Click',
        'click-plugins',
        'cconfig',
    ],
    entry_points={
        'console_scripts': [
            'cdng = cdist.cli:main'
        ],
        'cdist.cli.commands': [
            'config = cdist.cli.commands.config:main',
            'explore = cdist.cli.commands.explore:main',
            'run = cdist.cli.commands.run:main',
        ],
        'cdist.cli.internal_commands': [
            'emulator = cdist.cli.commands.internal.emulator:main',
            'log = cdist.cli.commands.internal.log:main',
        ],
    },
)

