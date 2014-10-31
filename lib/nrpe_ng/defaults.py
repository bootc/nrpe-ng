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

CONFIG_DEFAULTS = {
    'allow_bash_command_substitution': False,
    'allowed_hosts': '',
    'command_prefix': '',
    'command_timeout': 60,
    'connection_timeout': 300,
    'debug': False,
    'dont_blame_nrpe': False,
    'log_facility': 'daemon',
    'nrpe_group': 'nagios',
    'nrpe_user': 'nagios',
    'pid_file': '/run/nagios/nrpe.pid',
    'server_address': '::',
    'server_port': 5666,
    'ssl_verify_client': False,
    'ssl_ca_file': '',
    'ssl_cert_file': '',
    'ssl_key_file': '',
}
