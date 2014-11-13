#!/usr/bin/python3

# This file is part of nrpe-ng.
# Copyright (C) 2014  Chris Boot <bootc@bootc.net>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import sys
from distutils.util import convert_path
from setuptools import setup, find_packages

# Check that we are running on Python 3.2 or higher. This is required for
# argparse, ssl.SSLContext and probably a few other things.
if sys.version_info < (3, 2):
    print('This program requires Python 3.2.')
    sys.exit(1)

# Read the version number from nrpe_ng/version.py. This avoids needing to
# query setuptools for the version at run-time.
main_ns = {}
ver_path = convert_path('nrpe_ng/version.py')
with open(ver_path) as ver_file:
    exec(ver_file.read(), main_ns)

setup(
    name='nrpe-ng',
    version=main_ns['__version__'],
    description='Next-generation Nagios remote plugin agent',
    author='Chris Boot',
    author_email='bootc@bootc.net',
    license='GPL-2+',
    url='https://github.com/bootc/nrpe-ng/',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 or later '
            '(GPLv2+)',
        'Topic :: System :: Systems Administration',
    ],
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'check_nrpe_ng = nrpe_ng.client:main',
            'nrpe-ng = nrpe_ng.server:main',
        ],
    },
)
