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
import urllib.parse
import sys

from http.server import BaseHTTPRequestHandler

from ..version import __version__

log = logging.getLogger(__name__)


class NrpeHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.cfg = self.server.cfg
        BaseHTTPRequestHandler.setup(self)

    # Regular expression for dealing with IPv4-mapped IPv6
    IPV4_MAPPED_IPV6_RE = re.compile(r'^::ffff:(?P<ipv4>\d+\.\d+\.\d+\.\d+)$')

    def parse_request(self):
        result = BaseHTTPRequestHandler.parse_request(self)
        if not result:
            return False

        if self.cfg.allowed_hosts:
            host = self.client_address[0]

            # Handle IPv4-mapped IPv6 as IPv4
            mo = self.IPV4_MAPPED_IPV6_RE.search(host)
            if mo:
                host = mo.group('ipv4')

            # Check whether the host is listed in allowed_hosts
            if host not in self.cfg.allowed_hosts:
                self.send_error(401, "Not in allowed_hosts: {}".format(host))
                return False

        return True

    # Regular expression for extracting the command to run
    CMD_URI_RE = re.compile(r'^/v1/check/(?P<cmd>[^/]+)$')

    def get_command(self):
        command = None

        mo = self.CMD_URI_RE.search(self.path)
        if mo:
            cmd = mo.group('cmd')
            command = self.cfg.commands.get(cmd)
            if command:
                return command

            self.send_error(404, "Unknown command: {}".format(cmd))
            log.warning("unknown comand: {}".format(cmd))
            return None

        self.send_error(404, "Invalid request URI")
        log.warning("invalid request URI: {}".format(self.path))
        return None

    def do_HEAD(self):
        cmd = self.get_command()
        if not cmd:
            return

        self.send_response(200)
        self.send_header('Connection', 'close')
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()

    def do_GET(self):
        cmd = self.get_command()
        if not cmd:
            return

        try:
            (returncode, stdout, stderr) = cmd.execute()
        except:
            self.send_error(502, 'Unexpected error executing command')
            log.exception('Unexpected error {e} running {c}'.format(
                e=sys.exc_info()[0], c=cmd))
        else:
            self.send_response(200)
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', len(stdout))
            self.send_header('Content-Type', 'text/plain')
            self.send_header('X-NRPE-Result', returncode)
            self.end_headers()

            self.wfile.write(stdout)

    def do_POST(self):
        content_len = int(self.headers.get('content-length', 0))
        post_body = self.rfile.read(content_len).decode()

        if not self.cfg.dont_blame_nrpe:
            self.send_error(401, 'Command arguments are disabled')
            log.warning('rejecting request: command arguments disabled')
            return

        cmd = self.get_command()
        if not cmd:
            return

        # Parse the application/x-www-form-urlencoded into a dictionary
        # we don't use parse_qs because we don't want the values ending up as
        # arrays
        args = dict(urllib.parse.parse_qsl(post_body, keep_blank_values=True))

        try:
            (returncode, stdout, stderr) = cmd.execute(args)

            self.send_response(200)
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', len(stdout))
            self.send_header('Content-Type', 'text/plain')
            self.send_header('X-NRPE-Result', returncode)
            self.end_headers()

            self.wfile.write(stdout)
        except:
            self.send_error(502, 'Unexpected error executing command')
            log.exception('Unexpected error running {}'.format(cmd))

    def version_string(self):
        return '{prog}/{ver}'.format(
            prog=__name__, ver=__version__)
