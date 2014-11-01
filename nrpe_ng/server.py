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
import daemon
import daemon.runner
import grp
import lockfile
import logging
import nrpe_ng
import pwd
import re
import signal
import sys

from nrpe_ng.commands import Command
from nrpe_ng.config import NrpeConfigParser
from nrpe_ng.defaults import SERVER_CONFIG
from nrpe_ng.http import NrpeHTTPServer
from nrpe_ng.syslog import SyslogHandler, facility as syslog_facility

# TODO:
# simple ACLs (allowed_hosts)
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
        parser = argparse.ArgumentParser(description=self.__doc__,
                                         epilog=epilog,
                                         version=nrpe_ng.VERSION)
        parser.add_argument('--debug', action='store_true',
                            help='print verbose debugging information')
        parser.add_argument('-c', '--config', dest='config_file',
                            required=True,
                            help='use the given configuration file')
        parser.add_argument('-d', '--daemon', action='store_true',
                            default=True,
                            help='run as a standalone daemon (default)')
        parser.add_argument('-f', action='store_false', dest='daemon',
                            help='do not fork into the background')

        self.argparser = parser

    def parse_args(self):
        self.argparser.parse_args(namespace=self)

    # Regular expression for parsing command name options from the config file
    CMD_RE = re.compile(r'^command\[(?P<cmd>[^]]+)\]$')

    def parse_config(self, config_file):
        """
        Parse the given config file as a pseudo-ini file. Options that have
        default values in nrpe_ng.defaults.SERVER_CONFIG are copied in as
        attributes of this object, keeping their type intact.

        Additionally, NRPE command[] options are also parsed, and
        nrpe_ng.commands.Command objects are created for each found command.
        """
        config = NrpeConfigParser(SERVER_CONFIG)
        secname = config.main_section  # default ini "section" for all config

        try:
            with open(config_file) as fp:
                config.readfp(fp, config_file)
        except IOError:
            log.exception(
                "config file '{}' contained errors, aborting".format(
                    config_file))
            sys.exit(1)

        # Handle the 'debug' specially
        if not self.debug:
            self.debug = config.get(secname, 'debug')
            if type(self.debug) is not bool:
                self.debug = config.getboolean(secname, 'debug')

        # Set local attributes based on configuration values in a type-aware
        # fashion, based on the type of the value in SERVER_CONFIG
        for key in SERVER_CONFIG:
            # Skip already-set attributes
            if hasattr(self, key):
                continue

            dt = type(SERVER_CONFIG[key])

            if dt is bool:  # is it a bool?
                # handle boolean defaults; getboolean() fails if the value is
                # already boolean (e.g. straight from defaults, not overridden)
                value = config.get(secname, key)
                if type(value) is not bool:
                    try:
                        value = config.getboolean(secname, key)
                    except ValueError:
                        log.error("invalid {key}, expected a boolean but got "
                                  "'{val}'".format(key=key, val=value))
                        sys.exit(1)
            elif dt is int:  # is it an int?
                try:
                    value = config.getint(secname, key)
                except ValueError:
                    log.error(
                        "invalid {key}, expected an integer but got '{val}'"
                        .format(key=key, val=config.get(secname, key)))
                    sys.exit(1)
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

    def reload_config(signal_number, stack_frame):
        raise NotImplemented()

    def setup_logging(self):
        log.setLevel(logging.INFO)

        # Add a syslog handler with default values
        syslog = SyslogHandler(ident=nrpe_ng.PROG,
                               facility=syslog_facility('daemon'))
        log.addHandler(syslog)
        self.log_syslog = syslog

        # Add a console handler
        console = logging.StreamHandler()
        log.addHandler(console)

    def setup(self):
        # In debug mode:
        # - don't send output to syslog
        # - set the log level to DEBUG if we're not daemonising
        if self.debug:
            log.setLevel(logging.DEBUG)
            if not self.daemon:
                log.removeHandler(self.log_syslog)

        # Update the syslog facility from the config file
        try:
            self.log_syslog.facility = syslog_facility(self.log_facility)
        except ValueError:
            log.error('invalid log_facility: {}'.format(self.log_facility))
            sys.exit(1)

        # We don't allow bash-style command substitution at all, it's bad
        if self.allow_bash_command_substitution:
            log.error('bash-style command substitution is not supported, '
                      'aborting.')
            sys.exit(1)

        # Determine the uid and gid to change to
        try:
            nrpe_uid = pwd.getpwnam(self.nrpe_user).pw_uid
        except KeyError:
            log.error('invalid nrpe_user: {}'.format(self.nrpe_user))
            sys.exit(1)
        try:
            nrpe_gid = grp.getgrnam(self.nrpe_group).gr_gid
        except KeyError:
            log.error('invalid nrpe_group: {}'.format(self.nrpe_group))
            sys.exit(1)

        # Prepare PID file
        pidfile = daemon.runner.make_pidlockfile(self.pid_file, 0)
        if daemon.runner.is_pidfile_stale(pidfile):
            self.pidfile.break_lock()

        # Prepare Daemon Context
        dctx = daemon.DaemonContext(
            pidfile=pidfile,
            detach_process=self.daemon,
            uid=nrpe_uid, gid=nrpe_gid,
        )
        dctx.signal_map.update({
            signal.SIGHUP: self.reload_config,
        })
        self.daemon_context = dctx

        # If we are not daemonising, don't redirect stdout or stderr
        if not self.daemon:
            dctx.stdout = sys.stdout
            dctx.stderr = sys.stderr

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

        if not self.daemon_context.files_preserve:
            self.daemon_context.files_preserve = []
        self.daemon_context.files_preserve.extend([
            httpd.socket,
        ])

        log.info('server listening on {addr} port {port}'.format(
            addr=httpd.server_address[0],
            port=httpd.server_address[1]))

        try:
            with self.daemon_context:
                log.info('listening for connections')
                httpd.serve_forever()
        except KeyboardInterrupt:
            sys.exit(0)
        except lockfile.AlreadyLocked:
            log.error('there is already another process running (PID {})'
                      .format(self.daemon_context.pidfile.read_pid()))
            sys.exit(1)
        finally:
            log.warning('shutting down')
            httpd.server_close()
            self.daemon_context.close()

def main():
    return Server().run()
