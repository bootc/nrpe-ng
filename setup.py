#!/usr/bin/python

from distutils.core import setup

setup(
    name='nrpe-ng',
    version='0.1',
    description='Next-generation Nagios remote plugin agent',
    author='Chris Boot',
    author_email='bootc@bootc.net',
    url='https://github.com/bootc/nrpe-ng/',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Topic :: System :: Systems Administration',
    ],
    package_dir={'': 'lib'},
    packages=['nrpe_ng'],
    scripts=['bin/check_nrpe_ng', 'bin/nrpe_ng'],
)
