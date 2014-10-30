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

import shlex
import subprocess


class Command:
    def __init__(self, cmdstr):
        self.cmd = shlex.split(cmdstr)

    def __repr__(self):
        return "{klass}('{command}')".format(
            klass=self.__class__.__name__,
            command=subprocess.list2cmdline(self.cmd))

    def __str__(self):
        return subprocess.list2cmdline(self.cmd)
