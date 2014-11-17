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
import socket
import ssl
import sys

from http.server import HTTPServer
from socketserver import ThreadingMixIn

from .handler import NrpeHandler

log = logging.getLogger(__name__)


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
        except socket.error as e:
            log.error('failed to bind socket: {}'.format(e.args[1]))
            sys.exit(1)

        # Set up the SSL context
        try:
            ssl_context = ssl.create_default_context(
                purpose=ssl.Purpose.CLIENT_AUTH,
                cafile=cfg.ssl_ca_file)
        except IOError as e:
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
        except IOError as e:
            log.error('cannot read ssl_cert_file or ssl_key_file: {}'
                      .format(e.args[1]))
            sys.exit(1)

        # Wrap the socket
        self.raw_socket = self.socket
        self.socket = ssl_context.wrap_socket(
            self.raw_socket, server_side=True, do_handshake_on_connect=False)

        # Now start listening
        self.server_activate()

    def update_config(self, cfg):
        self.cfg = cfg

        # Update the timeout on the socket
        self.socket.settimeout(cfg.connection_timeout)

        # TODO: Can we update any of the SSL options?

    def get_request(self):
        sock, addr = super(NrpeHTTPServer, self).get_request()

        # In Python3 for some reason the socket comes out non-blocking, which
        # wreaks havoc with the SSL layer. Set it to blocking here and then
        # start the handshake.
        sock.setblocking(1)
        sock.do_handshake()

        return sock, addr
