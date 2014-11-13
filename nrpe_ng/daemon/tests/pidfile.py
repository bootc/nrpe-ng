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

import os
import subprocess
import sys
import tempfile
import unittest

from ..pidfile import *


class PidFileTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def tmpfile(self, path):
        return os.path.join(self.tmpdir.name, path)

    def obtain_out_of_process_lock(self, path):
        # Fire up a different Python interpreter to create and lock the file
        # for us. This needs to be outside this process in order for the
        # lockf()/fcntl() lock to deny this process access. Admittedly doing it
        # this way is a bit nasty but I can't think of a better way at the
        # moment.
        args = [
            sys.executable,
            '-c',
            ("import fcntl, os;"
             "fd = open('{}', 'w+');"
             "fcntl.lockf(fd, fcntl.LOCK_EX|fcntl.LOCK_NB);"
             "fd.write(str(os.getpid()) + '\\n');"
             "fd.flush();"
             "print('locked');"
             "input();"
             ).format(path)
        ]
        self.locked_sub = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)

        # Read the 'locked' line from the program above; now we know the file
        # is there and locked.
        while self.locked_sub.poll() is None:
            value = self.locked_sub.stdout.readline().strip()
            break

        # Did we successfully obtain the lock?
        if value == b'locked':
            return True

        # We failed to obtain the lock; clean up
        self.locked_sub.terminate()
        self.locked_sub.wait()
        self.locked_sub = None
        return False

    def cleanup_out_of_process_lock(self):
        if not self.locked_sub:
            return

        # Kill our locking child and clean up
        self.locked_sub.terminate()
        self.locked_sub.wait()

    def test_constructor_sets_pidfile(self):
        pidfile = self.tmpfile('test.pid')
        pid = PidFile(pidfile)
        self.assertEqual(pid.pidfile, pidfile)

    def test_create_creates_an_empty_pidfile(self):
        pidfile = self.tmpfile('test.pid')
        pid = PidFile(pidfile)
        self.assertFalse(os.path.isfile(pidfile))
        pid.create()
        self.assertTrue(os.path.isfile(pidfile))
        self.assertEquals(os.path.getsize(pidfile), 0)

    def test_create_raises_if_pid_file_already_locked(self):
        # This test checks that the PidFile class aborts correctly if a
        # different process is running and holds the lock. This other process
        # must have writen its PID to the file and maintain a lock on an open
        # file handle.

        # Create a temporary file that we will keep locked out-of-process
        pidfile = self.tmpfile('locked.pid')

        # Create the file correctly out-of-process, simulating another instance
        # of the daemon
        self.obtain_out_of_process_lock(pidfile)

        # Now try to create the PID file, which should fail with an exception
        pid = PidFile(pidfile)
        self.assertRaises(AlreadyRunningError, pid.create)

        self.cleanup_out_of_process_lock()

    def test_create_keeps_pid_file_locked(self):
        pidfile = self.tmpfile('locked.pid')

        # Create the PID file (and keep it locked)
        pid = PidFile(pidfile)
        pid.create()

        # Try to obtain a lock out-of-process, expecting it to fail
        self.assertFalse(self.obtain_out_of_process_lock(pidfile))
        self.cleanup_out_of_process_lock()

    def test_create_recreates_stale_pid_file(self):
        pidfile = self.tmpfile('stale.pid')

        # Create the PID file with valid but 'stale' content
        fd = open(pidfile, 'w')
        fd.write('1\n')
        fd.close()

        # Now use PidFile to overwrite it
        pid = PidFile(pidfile)
        pid.create()

        self.assertTrue(os.path.isfile(pidfile))
        self.assertEquals(os.path.getsize(pidfile), 0)

    def test_create_copes_with_corrupted_pid_file(self):
        # create() has to read the existing PID file to tell what process it
        # points at, so it must be able to cope with garbled PID files

        pidfile = self.tmpfile('stale.pid')

        # Create the PID file with valid but 'stale' content
        fd = open(pidfile, 'w')
        fd.write('\0' * 4096)  # simulate a page full of zeros
        fd.close()

        # Now use PidFile to overwrite it
        pid = PidFile(pidfile)
        pid.create()

        self.assertTrue(os.path.isfile(pidfile))
        self.assertEquals(os.path.getsize(pidfile), 0)

    def test_write_generates_well_formatted_pid(self):
        pidfile = self.tmpfile('correct.pid')

        # Create and write the PID file
        pid = PidFile(pidfile)
        pid.create()
        pid.write()

        # Open and read its contents
        with open(pidfile, 'r') as fd:
            lines = fd.readlines()

        self.assertEqual(lines, [str(os.getpid()) + '\n'])

    def test_close_removes_pid_file(self):
        pidfile = self.tmpfile('correct.pid')

        # Create and write the PID file
        pid = PidFile(pidfile)
        pid.create()
        pid.write()
        pid.close()

        # Now check that it's missing
        self.assertFalse(os.path.exists(pidfile))

    def test_close_multiple_times_is_not_an_error(self):
        pidfile = self.tmpfile('correct.pid')

        # Create and write the PID file
        pid = PidFile(pidfile)
        pid.create()
        pid.write()

        # Close it twice
        pid.close()
        pid.close()

    def test_context_manager(self):
        pidfile = self.tmpfile('context.pid')

        # Create the PID file
        pid = PidFile(pidfile)
        pid.create()

        # Test entering the context
        with pid:
            with open(pidfile, 'r') as fd:
                lines = fd.readlines()

            self.assertEqual(lines, [str(os.getpid()) + '\n'])

        self.assertFalse(os.path.exists(pidfile))
