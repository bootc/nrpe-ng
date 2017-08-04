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
import grp
import logging
import pwd
import signal
import socket
import sys

from daemon.daemon import DaemonContext
from daemon.pidfile import TimeoutPIDLockFile
from lockfile import AlreadyLocked
from tornado.ioloop import IOLoop

from .config import ServerConfig

from ..config import ConfigError
from ..defaults import SERVER_CONFIG
from ..http import NrpeHTTPServer
from ..syslog import SyslogHandler, facility as syslog_facility
from ..version import __version__

log = logging.getLogger(__name__)
rootlog = logging.getLogger()


class Server:
    """nrpe-ng: the next generation Nagios Remote Plugin Executor"""

    def __init__(self):
        epilog = """
        Copyright (C) 2014  Chris Boot <bootc@bootc.net>
        """
        parser = argparse.ArgumentParser(description=self.__doc__,
                                         epilog=epilog)
        parser.add_argument('--version', action='version',
                            version=__version__)
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
        rootlog.setLevel(logging.INFO)

        # Add a syslog handler with default values
        syslog = SyslogHandler(ident=self.argparser.prog,
                               facility=syslog_facility('daemon'),
                               formatter=logging.Formatter)
        rootlog.addHandler(syslog)
        self.log_syslog = syslog

        # Add a console handler
        console = logging.StreamHandler()
        rootlog.addHandler(console)

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

        # Is the value of 'debug' changing?
        if not self.cfg or self.cfg.debug != cfg.debug:
            # In debug mode:
            # - don't send output to syslog
            # - set the log level to DEBUG if we're not daemonising
            if cfg.debug:
                rootlog.setLevel(logging.DEBUG)
                if not cfg.daemon:
                    rootlog.removeHandler(self.log_syslog)
            else:
                rootlog.setLevel(logging.INFO)
                if not cfg.daemon:
                    rootlog.addHandler(self.log_syslog)

        self.cfg = cfg

        # Update the syslog facility from the config file
        self.log_syslog.facility = log_facility

        # Set the default timeout on sockets
        socket.setdefaulttimeout(cfg.connection_timeout)

    def handle_sighup(self, signal_number, stack_frame):
        log.info('received SIGHUP, reloading configuration...')

        try:
            self.reload_config()
            self.httpd.update_config(self.cfg)
            log.info('configuration updated')
        except ConfigError as e:
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

        # Prepare Daemon Context
        dctx = DaemonContext(
            detach_process=self.cfg.daemon,
            files_preserve=[],
        )
        dctx.signal_map.update({
            signal.SIGHUP: self.handle_sighup,
            signal.SIGTERM: self.handle_sigterm,
        })
        self.daemon_context = dctx

        # Only change UID/GID if we're daemonising
        if self.cfg.daemon:
            dctx.uid = nrpe_uid
            dctx.gid = nrpe_gid
            dctx.initgroups = True

        # Prepare PID file
        if self.cfg.daemon:
            dctx.pidfile = TimeoutPIDLockFile(self.cfg.pid_file)

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
        except ConfigError as e:
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

        for sock in httpd.sockets:
            self.daemon_context.files_preserve.append(sock.fileno())
            sn = sock.getsockname()
            log.info('server listening on {addr} port {port}'.format(
                addr=sn[0], port=sn[1]))

        try:
            with self.daemon_context:
                log.info('listening for connections')

                # don't wire the server sockets into the IOLoop until after the
                # fork to avoid the eventfd socket getting closed during
                # forking
                httpd.start()
                IOLoop.current().start()
        except AlreadyLocked:
            log.error('there is already another process running (PID {})'
                      .format(self.daemon_context.pidfile.read_pid()))
            sys.exit(1)
        except KeyboardInterrupt:
            pass
        except SystemExit:
            raise
        except:
            log.exception('unhandled exception, %s', sys.exc_info())
        finally:
            log.warning('shutting down')
            httpd.stop()
            self.daemon_context.close()
