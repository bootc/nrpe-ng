#!/usr/bin/python

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

from setuptools import setup

setup(
    name='nrpe-ng',
    version='0.0.4-dev1',
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
    packages=['nrpe_ng'],
    install_requires=[
        'lockfile',
        'python-daemon',
        'setuptools',
    ],
    entry_points={
        'console_scripts': [
            'check_nrpe_ng = nrpe_ng.client:main',
            'nrpe-ng = nrpe_ng.server:main',
        ],
    },
)
