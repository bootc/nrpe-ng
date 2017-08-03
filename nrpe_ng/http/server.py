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

from tornado import web
from tornado.httpserver import HTTPServer
from tornado.netutil import bind_sockets

from .handler import NrpeHandler

log = logging.getLogger(__name__)


class NrpeHTTPServer(HTTPServer):
    def initialize(self, cfg):
        self.cfg = cfg

        # Check we have a certificate and key defines
        if not cfg.ssl_cert_file or not cfg.ssl_key_file:
            log.error('a valid ssl_cert_file and ssl_key_file are required, '
                      'aborting')
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

        app = web.Application([
            (r'/v1/check/(?P<cmd>[^/]+)$', NrpeHandler, {'cfg': cfg}),
        ])

        # Set up the HTTPServer instance
        super(NrpeHTTPServer, self).initialize(
            app, no_keep_alive=True, ssl_options=ssl_context,
            idle_connection_timeout=cfg.connection_timeout,
            body_timeout=cfg.connection_timeout)

        # Because Tornado unconditionally sets IPV6_V6ONLY on IPv6 sockets, we
        # need a means to preserve old behaviour. This should only be an issue
        # when listening to '::' for IPv6 any-address. Tornado will listen both
        # the IPv4 and IPv6 any-address when the bind address is blank, so just
        # set the address to be empty if we encounter '::'.
        if cfg.server_address == '::':
            cfg.server_address = ''

        try:
            self.sockets = bind_sockets(port=cfg.server_port,
                                        address=cfg.server_address)
        except socket.error as e:
            log.error('failed to bind socket: {}'.format(e.args[1]))
            sys.exit(1)

        # Prevent tornado from logging HTTP requests
        if not self.cfg.debug:
            logging.getLogger('tornado.access').disabled = True

    def start(self):
        # We can't do the add_sockets() until after we have forked, otherwise
        # Tornado's eventfd is closed during the fork (and there's no sane way
        # of preserving it).
        self.add_sockets(self.sockets)

    def update_config(self, cfg):
        self.cfg = cfg

        # TODO: What options can we update dynamically?
