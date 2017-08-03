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

import logging
import re
import sys

from tornado import gen, web
from tornado.escape import native_str

from ..commands import CommandTimedOutError
from ..version import __version__

log = logging.getLogger(__name__)


class NrpeHandler(web.RequestHandler):
    def initialize(self, cfg):
        self.cfg = cfg

    # Regular expression for dealing with IPv4-mapped IPv6
    IPV4_MAPPED_IPV6_RE = re.compile(r'^::ffff:(?P<ipv4>\d+\.\d+\.\d+\.\d+)$')

    def prepare(self):
        # Check request against allowed hosts list
        if self.cfg.allowed_hosts:
            host = self.request.remote_ip

            # Handle IPv4-mapped IPv6 as IPv4
            mo = self.IPV4_MAPPED_IPV6_RE.search(host)
            if mo:
                host = mo.group('ipv4')

            # Check whether the host is listed in allowed_hosts
            if host not in self.cfg.allowed_hosts:
                self.send_error(
                    403, reason="Not in allowed_hosts: {}".format(host))
                return

        # Find the command in the configuration
        cmd = self.path_kwargs['cmd']
        command = self.cfg.commands.get(cmd)

        if command:
            self.cmd_name = cmd
            self.command = command
        else:
            self.send_error(404, reason="Unknown command: {}".format(cmd))

    @gen.coroutine
    def _execute_check(self, args={}):
        try:
            (returncode, stdout) = yield self.command.execute(args)
        except CommandTimedOutError:
            self.send_error(504, reason='Command execution timed out')
            log.error('Command timed out: {}'.format(self.cmd_name))
        except:
            self.send_error(500, reason='Internal command execution error')
            log.exception('Unexpected error {e} running {c}'.format(
                e=sys.exc_info()[0], c=self.cmd_name))
        else:
            self.set_header('Content-Type', 'text/plain')
            self.set_header('X-NRPE-Result', returncode)
            self.write(stdout)

    @gen.coroutine
    def head(self, cmd):
        self.set_header('Content-Type', 'text/plain')

    @gen.coroutine
    def get(self, cmd):
        yield self._execute_check()

    @gen.coroutine
    def post(self, cmd):
        if not self.cfg.dont_blame_nrpe:
            self.send_error(405, reason='Command arguments are disabled')
            log.warning('rejecting request: command arguments disabled')
            return

        # Convert the POST arguments into a simple hash of strings. The
        # body_arguments are otherwise a hash of lists of byte strings.
        body_args = self.request.body_arguments
        args = {k: native_str(body_args[k][0]) for k in body_args}

        yield self._execute_check(args)

    def set_default_headers(self):
        self.set_header('Server', "{prog}/{ver}".format(
            prog=__name__, ver=__version__))
