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

import re

from ..config import NrpeConfig
from ..commands import Command


class ServerConfig(NrpeConfig):
    # Regular expression for parsing command name options from the config file
    CMD_RE = re.compile(r'^command\[(?P<cmd>[^]]+)\]$')

    def read_extra_config(self, config, parsed):
        secname = config.main_section  # default ini "section" for all config

        # Parse the list of commands
        commands = {}
        for key in config.options(secname):
            mo = self.CMD_RE.search(key)
            if not mo:
                continue

            name = mo.group('cmd')
            value = config.get(secname, key)
            cmd = Command(self, value)
            commands[name] = cmd

        parsed.commands = commands
