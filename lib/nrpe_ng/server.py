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

import argparse
import logging
import nrpe_ng
import re
import sys

from nrpe_ng.commands import Command
from nrpe_ng.config import NrpeConfigParser
from nrpe_ng.defaults import CONFIG_DEFAULTS
from nrpe_ng.http import NrpeHTTPServer
from nrpe_ng.syslog import SyslogHandler, facility as syslog_facility

# TODO:
# forking (and pid_file)
# ch{u,g}id (nrpe_user, nrpe_group)
# simple ACLs (allowed_hosts)
# command arguments (dont_blame_nrpe)
# command prefix (command_prefix)
# command timeout (command_timeout)
# networking timeout (connection_timeout)

log = nrpe_ng.log


class Server:
    """nrpe-ng: the next generation Nagios Remote Plugin Executor"""

    def __init__(self):
        epilog = """
        Copyright (C) 2014  Chris Boot <bootc@bootc.net>
        """
        parser = argparse.ArgumentParser(
            prog='nrpe-ng-server', description=self.__doc__, epilog=epilog)
        parser.add_argument('-c', dest='config_file', required=True,
                            help='use the given configuration file')
        parser.add_argument('-d', action='store_true', dest='daemon',
                            default=True,
                            help='run as a standalone daemon (default)')
        parser.add_argument('-f', action='store_false', dest='daemon',
                            help='do not fork into the background')
        parser.add_argument('--debug', action='store_true',
                            help='print verbose debugging information')
        parser.add_argument('--version', action='version',
                            version=nrpe_ng.VERSION)

        self.argparser = parser

    def parse_args(self):
        self.argparser.parse_args(namespace=self)

    # Regular expression for parsing command name options from the config file
    CMD_RE = re.compile(r'^command\[(?P<cmd>[^]]+)\]$')

    def parse_config(self, config_file):
        """
        Parse the given config file as a pseudo-ini file. Options that have
        default values in nrpe_ng.defaults.CONFIG_DEFAULTS are copied in as
        attributes of this object, keeping their type intact.

        Additionally, NRPE command[] options are also parsed, and
        nrpe_ng.commands.Command objects are created for each found command.
        """
        config = NrpeConfigParser(CONFIG_DEFAULTS)
        secname = config.main_section  # default ini "section" for all config

        try:
            with open(config_file) as fp:
                config.readfp(fp, config_file)
        except IOError:
            log.exception(
                "config file '{}' contained errors, aborting".format(
                    config_file))
            sys.exit(1)

        # Set local attributes based on configuration values in a type-aware
        # fashion, based on the type of the value in CONFIG_DEFAULTS
        for key in CONFIG_DEFAULTS:
            # Skip already-set attributes
            if hasattr(self, key):
                continue

            dt = type(CONFIG_DEFAULTS[key])

            if dt is bool:  # is it a bool?
                # handle boolean defaults; getboolean() fails if the value is
                # already boolean (e.g. straight from defaults, not overridden)
                value = config.get(secname, key)
                if type(value) is not bool:
                    value = config.getboolean(secname, key)
            elif dt is int:  # is it an int?
                value = config.getint(secname, key)
            else:  # everything else is a string
                value = str(config.get(secname, key))

            setattr(self, key, value)

        # Parse the list of commands
        commands = {}
        for key in config.options(secname):
            mo = self.CMD_RE.match(key)
            if not mo:
                continue

            name = mo.group('cmd')
            value = config.get(secname, key)
            cmd = Command(value)
            commands[name] = cmd

        self.commands = commands

    def setup_logging(self):
        # Add a syslog handler with default values
        syslog = SyslogHandler(ident=nrpe_ng.PROG,
                               facility=syslog_facility('daemon'))
        log.addHandler(syslog)
        self.log_syslog = syslog

        # Add a console handler
        console = logging.StreamHandler()
        log.addHandler(console)

    def setup(self):
        # Update the syslog facility from the config file
        self.log_syslog.facility = syslog_facility(self.log_facility)

        # In debug mode:
        # - don't send output to syslog
        # - set the log level to DEBUG
        # - don't fork by default
        if self.debug:
            log.removeHandler(self.log_syslog)
            log.setLevel(logging.DEBUG)
            self.daemon = False

        # We don't allow bash-style command substitution at all, it's bad
        if self.allow_bash_command_substitution:
            log.error('bash-style command substitution is not supported, '
                      'aborting.')
            sys.exit(1)

    def run(self):
        self.parse_args()
        self.setup_logging()
        self.parse_config(self.config_file)
        self.setup()

        if self.debug:
            import pprint
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(self.__dict__)

        httpd = NrpeHTTPServer(self)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()
