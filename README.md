nrpe-ng: The next generation Nagios Remote Plugin Executor
==========================================================

This is a rewrite from the ground up of NRPE. This set of programs allows you
to run Nagios check scripts on a remote host.

FEATURES
--------

  * Real, proper SSL (TLS, actually). The server/executor component needs a key
    and certificate, and can optionally validate clients against a provided SSL
    certificate authority (or the system one). The client also validates the
    server name given in certificates and can validate the certificate against
    the system CA list or a provided CA.

  * Safe command-line argument passing. Arguments are passed without any
    interpolation to the check script. Missing arguments are simply passed as
    empty arguments. Quoting within the configuration file is respected.

  * Named arguments are supported. If you had trouble working out what $ARG7$
    in your check script was for, you can now call it something sensible
    instead.

WHY? IS NRPE NOT GOOD ENOUGH?
-----------------------------

No. It has several weaknesses and issues that make it unsuitable:

  1. Its SSL mode does very little for security. It does not use certificates
     or keys. It simply does a plain DH Key Exchange using a well-known
     "secret", and cannot validate that the client or server it is talking to
     is correctly authorised. It prevents passive snooping of the connection,
     but does not help against man-in-the-middle attacks.

  2. Its command-line argument passing capability is riddled with security
     holes. All commands are run by passing them to a shell, which exposes a
     great number of attacks using shell expansion characters.

Why now? The command-line execution mode of NRPE was disabled in the packages
currently (as of this writing) in Debian Jessie in response to CVE-2014-2913
(Debian bug #745272). I felt I really needed this functionality, but the bugs
are too severe to fix properly. I felt that re-implementing it from the ground
up with the features that I want was a good thing to do.

DISCLAIMER
----------

This project is not endorsed nor authorised by Nagios Enterprises, LLC. I just
picked the name as it seemed to be a good name to describe an improved
re-implementation of NRPE.

LICENSE
-------
Copyright (C) 2014-17  Chris Boot <bootc@bootc.net>

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
