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
import socket
import ssl
import sys

from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn


log = nrpe_ng.log


class NrpeHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

        self.wfile.write('you asked for {}'.format(self.path) + "\r\n")
        return

    def do_POST(self):
        pass


class NrpeHTTPServer(ThreadingMixIn, HTTPServer):
    def __init__(self, nrpe_server, RequestHandlerClass=NrpeHandler):
        # Check we have a certificate and key defines
        if not nrpe_server.ssl_cert_file or not nrpe_server.ssl_key_file:
            log.error('a valid ssl_cert_file and ssl_key_file are required, '
                      'aborting')
            sys.exit(1)

        # Figure out the arguments we need to pass to socket.socket()
        address = None
        for res in socket.getaddrinfo(
                nrpe_server.server_address, nrpe_server.server_port,
                socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                socket.AI_PASSIVE):

            af, socktype, proto, canonname, sa = res

            if af in [socket.AF_INET, socket.AF_INET6]:
                self.address_family = af
                address = sa
                break

        if not address:
            log.error('failed to find a suitable socket for host %(host)s '
                      'port %(port), aborting',
                      host=nrpe_server.server_address,
                      port=nrpe_server.server_port)
            sys.exit(1)

        # Set up the HTTPServer instance, creating a a listening socket
        HTTPServer.__init__(self, address, RequestHandlerClass,
                            bind_and_activate=False)
        self.server_bind()

        # Set up the SSL context
        ssl_context = ssl.create_default_context(
            purpose=ssl.Purpose.CLIENT_AUTH,
            cafile=nrpe_server.ssl_ca_file)
        self.ssl_context = ssl_context

        # Enable client certificate verification if wanted
        if nrpe_server.ssl_verify_client:
            ssl_context.verify_mode = ssl.CERT_REQUIRED

        # Load our own certificate into the server
        ssl_context.load_cert_chain(certfile=nrpe_server.ssl_cert_file,
                                    keyfile=nrpe_server.ssl_key_file)

        # Wrap the socket
        self.raw_socket = self.socket
        self.socket = ssl_context.wrap_socket(self.raw_socket, server_side=True)

        # Now start listening
        self.server_activate()
