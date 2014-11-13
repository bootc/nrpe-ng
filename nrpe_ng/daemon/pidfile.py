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

import fcntl
import os

from .. import log


class AlreadyRunningError(Exception):
    pass


class PidFile(object):
    def __init__(self, pidfile):
        super(PidFile, self).__init__()
        self.pidfile = pidfile
        self.fp = None

    def _lock_fp(self, fp, dontblock=True):
        # Obtain an exclusive lockf() / fcntl() lock on a file handle
        op = fcntl.LOCK_EX
        if dontblock:
            op = op | fcntl.LOCK_NB
        fcntl.lockf(fp, op)

    def create(self):
        try:
            # Try to create the PID file. This will fail if it already exists
            # so that we can handle that case specially
            fd = os.open(self.pidfile, os.O_RDWR | os.O_CREAT | os.O_EXCL,
                         int('0644', 8))
            fp = os.fdopen(fd, 'w+')
        except FileExistsError:
            # Open the pre-existing PID so that we can inspect it
            fd = os.open(self.pidfile, os.O_RDWR)
            fp = os.fdopen(fd, 'w+')

            # Try to read a numeric PID from the file
            words = fp.readline().strip().split()
            try:
                fpid = int(words[0])
            except:
                # If anything goes wrong here, assume an invalid PID
                fpid = None

            # Try to obtain a lock on the PID file
            try:
                self._lock_fp(fp)
                locked = True
            except BlockingIOError:
                locked = False

            if not fpid or fpid == os.getpid() or locked:
                # The PID is invalid, or it's for our own process, or we were
                # able to obtain a lock: log a note and carry on
                log.info('removing stale PID file')
            else:
                # Something else holds the lock:
                # PID is valid _and_ it's not our process _and_ we didn't
                # obtain the lock
                raise AlreadyRunningError(fpid)

            # Remove the stale file
            fp.close()
            os.unlink(self.pidfile)

            # Re-create it to ensure it has the correct mode
            fd = os.open(self.pidfile, os.O_RDWR | os.O_CREAT | os.O_EXCL,
                         int('0644', 8))
            fp = os.fdopen(fd, 'w+')

        # Ensure we hold a lock
        self._lock_fp(fp)

        self.fp = fp

    def write(self):
        # Make certain we hold the lock on the file, which may have been
        # dropped if this process has forked
        self._lock_fp(self.fp, False)

        # Write the PID to the file
        self.fp.seek(0)
        self.fp.write("{}\n".format(os.getpid()))
        self.fp.flush()
        self.fp.truncate()

        # Ensure the PID file is closed if we exec another program
        fcntl.fcntl(self.fp, fcntl.F_SETFD, fcntl.FD_CLOEXEC)

    def close(self):
        # If we have an open file handle for the PID file, close it and remove
        # the file.
        if not self.fp:
            return

        self.fp.close()
        self.fp = None
        os.unlink(self.pidfile)

    def __enter__(self):
        self.write()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __del__(self):
        self.close()
