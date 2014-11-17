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

import re
import shlex
import subprocess
import threading

from .defaults import EXEC_PATH
from . import log


class Command:
    # Regular expression to match argument placeholders
    ARG_RE = re.compile(r'\$(?P<arg>\w+)\$')

    def __init__(self, cfg, cmdstr):
        self.cfg = cfg
        self.cmd = shlex.split(cmdstr)

    def execute(self, args={}):
        env = {
            'PATH': EXEC_PATH,
        }

        # Initialise the arguments list with the split up command prefix
        run_args = shlex.split(self.cfg.command_prefix)

        # Add the actual command and its arguments
        for arg in self.cmd:
            mo = self.ARG_RE.search(arg)
            if not mo:
                run_args.append(arg)
                continue

            var = mo.group('arg')
            run_args.append(args.get(var, ''))

        log.debug('Executing: {}'.format(subprocess.list2cmdline(run_args)))

        ipc = {}

        def runit():
            proc = subprocess.Popen(
                run_args, stdout=subprocess.PIPE, close_fds=True, env=env)
            ipc['proc'] = proc

            stdout, stderr = proc.communicate()
            ipc.update({
                'exit': proc.returncode,
                'stdout': stdout,
                'stderr': stderr,
            })

        thread = threading.Thread(target=runit)
        thread.start()

        thread.join(self.cfg.command_timeout)
        if thread.is_alive():
            ipc['proc'].terminate()
            thread.join(self.cfg.command_timeout)
            if thread.is_alive():
                ipc['proc'].kill()
                thread.join()

        if ipc['exit'] < 0 and not ipc['stdout']:
            ipc['stdout'] = "Terminated by signal {}\n".format(-ipc['exit'])

        return (ipc['exit'], ipc['stdout'], ipc['stderr'])

    def __repr__(self):
        return "{klass}('{command}')".format(
            klass=self.__class__.__name__,
            command=subprocess.list2cmdline(self.cmd))

    def __str__(self):
        return subprocess.list2cmdline(self.cmd)
