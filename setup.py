import io
from os import getcwd
from os.path import abspath, dirname, join
from setuptools import setup, find_packages

here = abspath(dirname(__file__))
with io.open(join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

with io.open(join(getcwd(), 'requirements', 'base.txt'), encoding='utf-8') as f:
    requirements = f.read().splitlines()

setup(
    name='moler',
    version='4.13.1',
    description='Moler is a library for working with terminals, mainly for automated tests',  # Required
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/nokia/moler',
    author='Nokia',
    license='BSD 3-Clause',
    classifiers=[
        'Development Status :: 5 - Production/Stable',

        'Environment :: Console',

        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Telecommunications Industry',
        'Topic :: Software Development :: Build Tools',

        'License :: OSI Approved :: BSD License',

        'Operating System :: POSIX',
        'Operating System :: Unix',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',

        'Topic :: Software Development',
        'Topic :: Software Development :: Testing',
        'Topic :: System :: Networking'
    ],
    keywords='testing development',
    packages=find_packages(exclude=['docs', 'examples', 'images', 'test', 'test.*']),
    install_requires=requirements,
    python_requires='>=3.8',
    project_urls={
        'Bug Reports': 'https://github.com/nokia/moler/issues',
        'Source': 'https://github.com/nokia/moler',
    },
)
