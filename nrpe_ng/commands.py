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

import logging
import re
import shlex
import subprocess
import tornado.process

from datetime import timedelta
from tornado import gen
from tornado.ioloop import IOLoop

from .defaults import EXEC_PATH

log = logging.getLogger(__name__)


@gen.coroutine
def terminate_hard(subproc, attempts=3, interval=1):
    for signal in [subproc.proc.terminate, subproc.proc.kill]:
        for _ in range(attempts):
            try:
                signal()
            except ProcessLookupError:
                pass

            try:
                yield gen.with_timeout(
                    timedelta(seconds=interval),
                    subproc.wait_for_exit(raise_error=False))
            except gen.TimeoutError:
                pass
            else:
                return


class CommandTimedOutError(Exception):
    def __init__(self):
        super(CommandTimedOutError, self).__init__('CommandTimedOutError')


class Command:
    # Regular expression to match argument placeholders
    ARG_RE = re.compile(r'\$(?P<arg>\w+)\$')

    def __init__(self, cfg, cmdstr):
        self.cfg = cfg
        self.cmd = shlex.split(cmdstr)

    @gen.coroutine
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

        proc = tornado.process.Subprocess(
            run_args,
            stdout=tornado.process.Subprocess.STREAM,
            close_fds=True,
            env=env)

        try:
            exit, stdout = yield gen.with_timeout(
                timedelta(seconds=self.cfg.command_timeout),
                [
                    proc.wait_for_exit(raise_error=False),
                    proc.stdout.read_until_close(),
                ])
        except gen.TimeoutError:
            IOLoop.current().add_callback(terminate_hard, proc)
            raise CommandTimedOutError

        if exit < 0 and not stdout:
            stdout = "Terminated by signal {}\n".format(-exit)

        return (exit, stdout)

    def __repr__(self):
        return "{klass}('{command}')".format(
            klass=self.__class__.__name__,
            command=subprocess.list2cmdline(self.cmd))

    def __str__(self):
        return subprocess.list2cmdline(self.cmd)
