# This file is part of nrpe-ng.
# Copyright (C) 2014-17  Chris Boot <bootc@bootc.net>
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
import os.path
import requests
import sys
import urllib.parse
import warnings

try:
    from requests.packages.urllib3.exceptions import SubjectAltNameWarning
except ImportError:
    SubjectAltNameWarning = None

from .config import NrpeConfig, ConfigError
from .defaults import CLIENT_CONFIG, CLIENT_CONFIG_PATH
from .syslog import SyslogFormatter
from .version import __version__

log = logging.getLogger(__name__)
rootlog = logging.getLogger()


NAGIOS_OK = 0
NAGIOS_WARNING = 1
NAGIOS_CRITICAL = 2
NAGIOS_UNKNOWN = 3


class Client:
    """nrpe-ng: the next generation Nagios Remote Plugin Executor"""

    def __init__(self):
        epilog = """
        Copyright (C) 2014-17  Chris Boot <bootc@bootc.net>
        """
        parser = argparse.ArgumentParser(description=self.__doc__,
                                         epilog=epilog)
        parser.add_argument('--version', action='version',
                            version=__version__)
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
        parser.add_argument('-c', dest='command', default=None,
                            help='the command to run run on the remote host')
        parser.add_argument('-a', dest='args', nargs='+', action='append',
                            help='arguments that should be passed to the '
                            'command')

        self.argparser = parser

    def setup_logging(self):
        # Add a console handler
        console = logging.StreamHandler()
        self.console_log = console
        rootlog.addHandler(console)

    def parse_args(self):
        args = self.argparser.parse_args()

        # Re-process args to flatten the list
        if args.args:
            args.args = [item for sublist in args.args for item in sublist]

        self.args = args

    def reload_config(self):
        config_file = self.args.config_file

        # If the user has not specified a configuration file, but a file exists
        # in the standard location, use it.
        if config_file is None and os.path.lexists(CLIENT_CONFIG_PATH):
            config_file = CLIENT_CONFIG_PATH

        cfg = NrpeConfig(CLIENT_CONFIG, self.args, config_file)

        # In debug mode, set the log level to DEBUG
        if cfg.debug:
            rootlog.setLevel(logging.DEBUG)
        else:
            # Silence the requests library as we catch its exceptions and
            # output our own summary messages
            logging.getLogger('requests').setLevel(logging.CRITICAL)

            # Don't output exception stack traces
            self.console_log.formatter = SyslogFormatter()

        self.cfg = cfg

    def make_request(self):
        if self.cfg.command:
            command = urllib.parse.quote_plus(self.cfg.command)
            url = "https://{host}:{port}/v1/check/{command}".format(
                host=self.cfg.host, port=self.cfg.port, command=command)
        else:
            url = "https://{host}:{port}/v1/version".format(
                host=self.cfg.host, port=self.cfg.port)

        req = {
            'url': url,
            'headers': {
                'User-Agent': "{prog}/{ver}".format(
                    prog=self.argparser.prog,
                    ver=__version__),
            },
            'timeout': self.cfg.timeout,
            'allow_redirects': False,
        }

        if self.cfg.args:
            # Convert the array of arguments into a dict of key=value pairs
            # Arguments of the form key=value are simply split up, but
            # arguments with no '=' are assigned to ARGx keys like NRPE does
            args = {}
            argn = 1
            for arg in self.cfg.args:
                kv = arg.split('=', 2)
                if len(kv) == 1:
                    key = 'ARG{}'.format(argn)
                    args[key] = kv[0]
                    argn = argn + 1  # increment ARGx argument counter
                else:
                    key = kv[0]
                    args[key] = kv[1]

            req['method'] = 'POST'
            req['data'] = args
        else:
            req['method'] = 'GET'

        # Configure SSL server certificate verification
        if self.cfg.ssl_verify_server:
            if self.cfg.ssl_ca_file:
                req['verify'] = self.cfg.ssl_ca_file
            else:
                req['verify'] = True
        else:
            # Do not verify server certificates
            req['verify'] = False

        # Configure SSL client certificates
        if self.cfg.ssl_key_file and self.cfg.ssl_cert_file:
            req['cert'] = (self.cfg.ssl_cert_file, self.cfg.ssl_key_file)

        return requests.request(**req)

    def run(self):
        self.setup_logging()
        self.parse_args()

        try:
            self.reload_config()
        except ConfigError as e:
            log.error(e.args[0])
            log.error("config file '{}' contained errors, aborting".format(
                self.args.config_file))
            sys.exit(1)

        if self.cfg.debug:
            import pprint
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(self.cfg._get_kwargs())

        try:
            with warnings.catch_warnings():
                # Ignore urllib3's (embedded into requests) subjectAltName
                # warning unconditionally. It is highly likely that the
                # certificates used with nrpe-ng lack a subjectAltName so just
                # allow them to keep working silently; if/when requests or
                # urllib3 makes this fail, people will realise quickly enough.
                if SubjectAltNameWarning:
                    warnings.simplefilter('ignore',
                                          category=SubjectAltNameWarning)

                r = self.make_request()

        except requests.exceptions.Timeout:
            log.error("{host}: Request timed out".format(
                host=self.cfg.host))

            if self.cfg.timeout_unknown:
                sys.exit(NAGIOS_UNKNOWN)
            else:
                sys.exit(NAGIOS_CRITICAL)
        except requests.exceptions.RequestException as e:
            # Why do I have to do this?! Such insanity should not be necessary
            # to obtain the actual underlying exception that caused the request
            # to fail.
            wrapped = e
            while wrapped.__cause__ or wrapped.__context__:
                wrapped = wrapped.__cause__ or wrapped.__context__

            # This additional insanity is now needed to get a nice textual
            # error that's presentable to a user.
            message = str(wrapped)
            if isinstance(wrapped, OSError):
                message = wrapped.strerror

            log.error("{host}: {err}".format(
                host=self.cfg.host, err=message), exc_info=True)
            sys.exit(NAGIOS_UNKNOWN)

        # When no command is requested, this is a version request.
        if self.cfg.command is None:
            if r.status_code == 200:
                # nrpe-ng 0.2 has a version endpoint
                print(r.text)
                sys.exit(NAGIOS_OK)

            try:
                # older versions don't, but they set the Server header. This
                # might also be helpful if the request fails.
                print(r.headers['Server'])
                sys.exit(NAGIOS_OK)
            except KeyError:
                print("unknown version: {}".format(r.reason))
                sys.exit(NAGIOS_WARNING)

        if r.status_code != 200:
            print(r.reason)
            sys.exit(NAGIOS_UNKNOWN)

        try:
            result = int(r.headers['X-NRPE-Result'])
        except:
            result = NAGIOS_UNKNOWN

        sys.stdout.write(r.text)
        sys.exit(result)


def main():
    return Client().run()


if __name__ == "__main__":
    main()
