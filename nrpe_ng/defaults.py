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

PORT = 59546
EXEC_PATH = '/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin'
CLIENT_CONFIG_PATH = '/etc/nagios/check_nrpe_ng.cfg'

CLIENT_CONFIG = {
    'port': PORT,
    'timeout': 10,
    'ssl_verify_server': True,
    'ssl_ca_file': '',
    'ssl_cert_file': '',
    'ssl_key_file': '',
}

SERVER_CONFIG = {
    'allow_bash_command_substitution': False,
    'allowed_hosts': [],
    'command_prefix': '',
    'command_timeout': 60,
    'connection_timeout': 300,
    'debug': False,
    'dont_blame_nrpe': False,
    'log_facility': 'daemon',
    'nrpe_group': 'nagios',
    'nrpe_user': 'nagios',
    'pid_file': '/run/nagios/nrpe-ng.pid',
    'server_address': '::',
    'server_port': PORT,
    'ssl_verify_client': False,
    'ssl_ca_file': '',
    'ssl_cert_file': '',
    'ssl_key_file': '',
}
