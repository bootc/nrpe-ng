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

import nrpe_ng
import re
import socket
import ssl
import sys
import urlparse

from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from httplib import HTTPSConnection
from SocketServer import ThreadingMixIn


log = nrpe_ng.log


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
            mo = self.IPV4_MAPPED_IPV6_RE.match(host)
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

        mo = self.CMD_URI_RE.match(self.path)
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

            self.send_response(200)
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', len(stdout))
            self.send_header('Content-Type', 'text/plain')
            self.send_header('X-NRPE-Result', returncode)
            self.end_headers()

            self.wfile.write(stdout)
        except:
            self.send_error(502, nrpe_ng.PROG +
                            ': unexpected error executing command')
            log.exception('Unexpected error running {}'.format(cmd))

    def do_POST(self):
        content_len = int(self.headers.getheader('content-length', 0))
        post_body = self.rfile.read(content_len)

        if not self.cfg.dont_blame_nrpe:
            self.send_error(401, nrpe_ng.PROG +
                            ': command arguments are disabled')
            log.warning('rejecting request: command arguments disabled')
            return

        cmd = self.get_command()
        if not cmd:
            return

        # Parse the application/x-www-form-urlencoded into a dictionary
        # we don't use parse_qs because we don't want the values ending up as
        # arrays
        args = dict(urlparse.parse_qsl(post_body, keep_blank_values=True))

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
            self.send_error(502, nrpe_ng.PROG +
                            ': unexpected error executing command')
            log.exception('Unexpected error running {}'.format(cmd))

    def version_string(self):
        return '{prog}/{ver}'.format(prog=nrpe_ng.PROG, ver=nrpe_ng.VERSION)


class NrpeHTTPServer(ThreadingMixIn, HTTPServer):
    def __init__(self, cfg, RequestHandlerClass=NrpeHandler):
        self.cfg = cfg

        # Check we have a certificate and key defines
        if not cfg.ssl_cert_file or not cfg.ssl_key_file:
            log.error('a valid ssl_cert_file and ssl_key_file are required, '
                      'aborting')
            sys.exit(1)

        # Figure out the arguments we need to pass to socket.socket()
        address = None
        try:
            for res in socket.getaddrinfo(
                    cfg.server_address, cfg.server_port,
                    socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                    socket.AI_PASSIVE):

                af, socktype, proto, canonname, sa = res

                if af in [socket.AF_INET, socket.AF_INET6]:
                    self.address_family = af
                    address = sa
                    break
        except socket.gaierror:
            pass  # let the condition below take care of the error

        if not address:
            log.error('failed to find a suitable socket for host {host} '
                      'port {port}, aborting'.format(
                          host=cfg.server_address,
                          port=cfg.server_port))
            sys.exit(1)

        # Set up the HTTPServer instance, creating a a listening socket
        HTTPServer.__init__(self, address, RequestHandlerClass,
                            bind_and_activate=False)

        try:
            self.server_bind()
        except socket.error, e:
            log.error('failed to bind socket: {}'.format(e.args[1]))
            sys.exit(1)

        # Set up the SSL context
        try:
            ssl_context = ssl.create_default_context(
                purpose=ssl.Purpose.CLIENT_AUTH,
                cafile=cfg.ssl_ca_file)
        except IOError, e:
            log.error('cannot read ssl_ca_file: {}'.format(e.args[1]))
            sys.exit(1)
        self.ssl_context = ssl_context

        # Enable client certificate verification if wanted
        if cfg.ssl_verify_client:
            ssl_context.verify_mode = ssl.CERT_REQUIRED

        # Load our own certificate into the server
        try:
            ssl_context.load_cert_chain(
                certfile=cfg.ssl_cert_file,
                keyfile=cfg.ssl_key_file)
        except IOError, e:
            log.error('cannot read ssl_cert_file or ssl_key_file: {}'
                      .format(e.args[1]))
            sys.exit(1)

        # Wrap the socket
        self.raw_socket = self.socket
        self.socket = ssl_context.wrap_socket(self.raw_socket,
                                              server_side=True)

        # Now start listening
        self.server_activate()

    def update_config(self, cfg):
        self.cfg = cfg

        # TODO: Can we update any of the SSL options?


class HTTPSClientAuthConnection(HTTPSConnection):
    """
    Class to make an HTTPS connection, with support for full client-based
    SSL Authentication
    """

    def __init__(self, host, port=None, ca_file=None, key_file=None,
                 cert_file=None, strict=None,
                 timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
        HTTPSConnection.__init__(self, host, port, key_file=key_file,
                                 cert_file=cert_file, strict=strict,
                                 timeout=timeout,
                                 source_address=source_address)
        self.ca_file = ca_file

    def connect(self):
        """
        Connect to a host on a given (SSL) port.
        If ca_file is pointing somewhere, use it to check Server Certificate.

        Redefined/copied and extended from httplib.py.
        """
        sock = self._create_connection((self.host, self.port),
                                       self.timeout, self.source_address)

        if self._tunnel_host:
            self.sock = sock
            self._tunnel()

        if self.ca_file:
            context = ssl.create_default_context(
                purpose=ssl.Purpose.SERVER_AUTH,
                cafile=self.ca_file)
        else:
            context = ssl.create_default_context(
                purpose=ssl.Purpose.SERVER_AUTH)

        if self.key_file or self.cert_file:
            context.load_cert_chain(certfile=self.cert_file,
                                    keyfile=self.key_file)

        self.sock = context.wrap_socket(sock, server_side=False,
                                        server_hostname=self.host)
