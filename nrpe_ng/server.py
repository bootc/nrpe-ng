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
from nrpe_ng.config import NrpeConfig, ConfigError
from nrpe_ng.defaults import SERVER_CONFIG
from nrpe_ng.http import NrpeHTTPServer
from nrpe_ng.syslog import SyslogHandler, facility as syslog_facility


log = nrpe_ng.log


class ServerConfig(NrpeConfig):
    # Regular expression for parsing command name options from the config file
    CMD_RE = re.compile(r'^command\[(?P<cmd>[^]]+)\]$')

    def read_extra_config(self, config, parsed):
        secname = config.main_section  # default ini "section" for all config

        # Parse the list of commands
        commands = {}
        for key in config.options(secname):
            mo = self.CMD_RE.match(key)
            if not mo:
                continue

            name = mo.group('cmd')
            value = config.get(secname, key)
            cmd = Command(self, value)
            commands[name] = cmd

        parsed.commands = commands


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
        self.cfg = None

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

    def parse_args(self):
        self.args = self.argparser.parse_args()

    def reload_config(self):
        immutable = [
            'nrpe_group',
            'nrpe_user',
            'pid_file',
            'server_address',
            'server_port',
            # FIXME: it would be nice if we _could_ change these:
            'ssl_ca_file',
            'ssl_cert_file',
            'ssl_key_file',
            'ssl_verify_client',
        ]

        cfg = ServerConfig(SERVER_CONFIG, self.args, self.args.config_file)

        # We don't allow bash-style command substitution at all, it's bad
        if cfg.allow_bash_command_substitution:
            raise ConfigError(
                'bash-style command substitution is not supported')

        # Update the syslog facility from the config file
        try:
            log_facility = syslog_facility(cfg.log_facility)
        except ValueError:
            raise ConfigError(
                'invalid log_facility: {}'.format(cfg.log_facility))

        # Check for changes to variables we can't reload
        if self.cfg:
            for key in immutable:
                if getattr(self.cfg, key) == getattr(cfg, key):
                    continue
                log.warning('value of {key} changed, but needs a restart to '
                            'take effect'.format(key=key))

        # !!! IMPORTANT: Beyond this point, no ConfigErrors should be raised

        self.cfg = cfg

        # Is the value of 'debug' changing?
        if not self.cfg or self.cfg.debug != cfg.debug:
            # In debug mode:
            # - don't send output to syslog
            # - set the log level to DEBUG if we're not daemonising
            if cfg.debug:
                log.setLevel(logging.DEBUG)
                if not cfg.daemon:
                    log.removeHandler(self.log_syslog)
            else:
                log.setLevel(logging.INFO)
                if not cfg.daemon:
                    log.addHandler(syslog)

        # Update the syslog facility from the config file
        self.log_syslog.facility = log_facility

    def handle_sighup(self, signal_number, stack_frame):
        log.info('received SIGHUP, reloading configuration...')

        try:
            self.reload_config()
            self.httpd.update_config(self.cfg)
            log.info('configuration updated')
        except ConfigError, e:
            log.error(e.args[0])
            log.error("config file '{}' contained errors, not updated".format(
                self.args.config_file))

        if self.cfg.debug:
            import pprint
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(self.cfg._get_kwargs())

    def handle_sigterm(self, signal_number, stack_frame):
        log.info('received SIGTERM, shutting down...')
        sys.exit(0)

    def setup(self):
        # Determine the uid and gid to change to
        try:
            nrpe_uid = pwd.getpwnam(self.cfg.nrpe_user).pw_uid
        except KeyError:
            log.error('invalid nrpe_user: {}'.format(self.nrpe_user))
            sys.exit(1)
        try:
            nrpe_gid = grp.getgrnam(self.cfg.nrpe_group).gr_gid
        except KeyError:
            log.error('invalid nrpe_group: {}'.format(self.nrpe_group))
            sys.exit(1)

        # Prepare PID file
        pidfile = daemon.runner.make_pidlockfile(self.cfg.pid_file, 0)
        if daemon.runner.is_pidfile_stale(pidfile):
            pidfile.break_lock()

        # Prepare Daemon Context
        dctx = daemon.DaemonContext(
            pidfile=pidfile,
            detach_process=self.cfg.daemon,
            uid=nrpe_uid, gid=nrpe_gid,
        )
        dctx.signal_map.update({
            signal.SIGHUP: self.handle_sighup,
            signal.SIGTERM: self.handle_sigterm,
        })
        self.daemon_context = dctx

        # If we are not daemonising, don't redirect stdout or stderr
        if not self.cfg.daemon:
            dctx.stdout = sys.stdout
            dctx.stderr = sys.stderr

    def run(self):
        self.setup_logging()
        self.parse_args()

        try:
            self.reload_config()
            self.setup()
        except ConfigError, e:
            log.error(e.args[0])
            log.error("config file '{}' contained errors, aborting".format(
                self.args.config_file))
            sys.exit(1)

        if self.cfg.debug:
            import pprint
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(self.cfg._get_kwargs())

        httpd = NrpeHTTPServer(self.cfg)
        self.httpd = httpd

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

if __name__ == "__main__":
    main()
