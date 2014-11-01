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
import socket
import sys
import urllib

from nrpe_ng.config import NrpeConfigParser
from nrpe_ng.defaults import CLIENT_CONFIG
from nrpe_ng.http import HTTPSClientAuthConnection


NAGIOS_OK = 0
NAGIOS_WARNING = 1
NAGIOS_CRITICAL = 2
NAGIOS_UNKNOWN = 3

log = nrpe_ng.log


class Client:
    """nrpe-ng: the next generation Nagios Remote Plugin Executor"""

    def __init__(self):
        epilog = """
        Copyright (C) 2014  Chris Boot <bootc@bootc.net>
        """
        parser = argparse.ArgumentParser(description=self.__doc__,
                                         epilog=epilog)
        parser.add_argument('--version', action='version',
                            version=nrpe_ng.VERSION)
        parser.add_argument('--debug', action='store_true',
                            help='print verbose debugging information')
        parser.add_argument('-C', dest='config_file',
                            help='use the given configuration file')
        parser.add_argument('-H', dest='host', required=True,
                            help='the address of the host running nrpe-ng')
        parser.add_argument('-p', type=int, dest='port',
                            default=CLIENT_CONFIG['port'],
                            help='the port on which the daemon is listening '
                            '(default: %(default)s)')
        parser.add_argument('-t', type=int, dest='timeout',
                            default=CLIENT_CONFIG['timeout'],
                            help='connection timeout in seconds '
                            '(default: %(default)s)')
        parser.add_argument('-u', action='store_true', dest='timeout_unknown',
                            help='socket timeouts return UNKNOWN state '
                            'instead of CRITICAL')
        parser.add_argument('-c', dest='command', required=True,
                            help='the command to run run on the remote host')
        parser.add_argument('-a', dest='args', nargs='+', action='append',
                            help='arguments that should be passed to the '
                            'command')

        self.argparser = parser

    def parse_args(self):
        self.argparser.parse_args(namespace=self)

    def parse_config(self, config_file):
        """
        Parse the given config file as a pseudo-ini file. Options that have
        default values in CLIENT_CONFIG are copied in as attributes of this
        object, keeping their type intact. Everything else is ignored.
        """
        config = NrpeConfigParser(CLIENT_CONFIG)
        secname = config.main_section  # default ini "section" for all config

        try:
            if config_file:
                with open(config_file) as fp:
                    config.readfp(fp, config_file)
            else:
                config.add_section(secname)
        except IOError:
            log.exception(
                "config file '{}' contained errors, aborting".format(
                    config_file))
            sys.exit(1)

        # Set local attributes based on configuration values in a type-aware
        # fashion, based on the type of the value in CLIENT_CONFIG
        for key in CLIENT_CONFIG:
            # Skip already-set attributes
            if hasattr(self, key):
                continue

            dt = type(CLIENT_CONFIG[key])

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

    def setup_logging(self):
        # Add a console handler
        console = logging.StreamHandler()
        log.addHandler(console)

    def setup(self):
        # In debug mode, set the log level to DEBUG
        # - don't fork by default
        if self.debug:
            log.setLevel(logging.DEBUG)

        # Re-process args to flatten the list
        if self.args:
            self.args = [item for sublist in self.args for item in sublist]

    def format_request(self):
        req = {
            'url': '/v1/check/{}'.format(self.command),
            'headers': {
                'User-Agent': '{prog}/{ver}'.format(
                    prog=self.argparser.prog, ver=nrpe_ng.VERSION),
            }
        }

        if self.args:
            # Convert the array of arguments into a dict of key=value pairs
            # Arguments of the form key=value are simply split up, but
            # arguments with no '=' are assigned to ARGx keys like NRPE does
            args = {}
            argn = 1
            for arg in self.args:
                kv = arg.split('=', 2)
                if len(kv) == 1:
                    key = 'ARG{}'.format(argn)
                    args[key] = kv[0]
                    argn = argn + 1  # increment ARGx argument counter
                else:
                    key = kv[0]
                    args[key] = kv[1]

            req['method'] = 'POST'
            req['body'] = urllib.urlencode(args)
            req['headers']['Content-Length'] = len(req['body'])
            req['headers']['Content-Type'] = \
                'application/x-www-form-urlencoded'
        else:
            req['method'] = 'GET'

        return req

    def run(self):
        self.parse_args()
        self.setup_logging()
        self.parse_config(self.config_file)
        self.setup()

        if self.debug:
            import pprint
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(self.__dict__)

        conn = HTTPSClientAuthConnection(
            self.host, self.port, strict=True, ca_file=self.ssl_ca_file,
            key_file=self.ssl_key_file, cert_file=self.ssl_cert_file)

        req = self.format_request()

        try:
            conn.request(**req)
        except socket.gaierror, e:
            log.error('{host}: {err}'.format(host=self.host, err=e.args[1]))
            sys.exit(NAGIOS_UNKNOWN)

        response = conn.getresponse()
        data = response.read()
        conn.close()

        if response.status != 200:
            print response.reason
            sys.exit(NAGIOS_UNKNOWN)

        result = int(response.getheader('X-NRPE-Result', NAGIOS_UNKNOWN))
        sys.stdout.write(data)
        sys.exit(result)

def main():
    return Client().run()
