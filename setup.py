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
    ],
    entry_points='''
        [console_scripts]
        cdng=cdist.cli:main
    ''',
)

