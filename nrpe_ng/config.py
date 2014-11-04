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

import nrpe_ng
import os

from argparse import Namespace
from ConfigParser import RawConfigParser, NoOptionError, ParsingError, \
    _default_dict


class NrpeConfigParser(RawConfigParser):
    def __init__(self, defaults=None, dict_type=_default_dict,
                 allow_no_value=False):
        RawConfigParser.__init__(self, defaults, dict_type, allow_no_value)
        self.main_section = nrpe_ng.PROG

    def __getattr__(self, name):
        try:
            return self.get(self.main_section, self.main_section, name)
        except NoOptionError, e:
            raise AttributeError

    def _read(self, fp, fpname):
        """Parse a sectioned setup file.

        The sections in setup file contains a title line at the top,
        indicated by a name in square brackets (`[]'), plus key/value
        options lines, indicated by `name: value' format lines.
        Continuations are represented by an embedded newline then
        leading whitespace.  Blank lines, lines beginning with a '#',
        and just about everything else are ignored.
        """
        if self.main_section in self._sections:
            cursect = self._sections[self.main_section]
        else:
            cursect = self._dict()
            cursect['__name__'] = self.main_section
            self._sections[self.main_section] = cursect

        optname = None
        lineno = 0
        e = None                              # None, or an exception
        while True:
            line = fp.readline()
            if not line:
                break
            lineno = lineno + 1
            # comment or blank line?
            if line.strip() == '' or line[0] in '#;':
                continue
            if line.split(None, 1)[0].lower() == 'rem' and line[0] in "rR":
                # no leading whitespace
                continue
            # continuation line?
            if line[0].isspace() and optname:
                value = line.strip()
                if value:
                    cursect[optname].append(value)
            # an option line?
            else:
                mo = self._optcre.match(line)
                if mo:
                    optname, vi, optval = mo.group('option', 'vi', 'value')
                    optname = self.optionxform(optname.rstrip())
                    # This check is fine because the OPTCRE cannot
                    # match if it would set optval to None
                    if optval is not None:
                        if vi in ('=', ':') and ';' in optval:
                            # ';' is a comment delimiter only if it follows
                            # a spacing character
                            pos = optval.find(';')
                            if pos != -1 and optval[pos-1].isspace():
                                optval = optval[:pos]
                        optval = optval.strip()
                        # allow empty values
                        if optval == '""':
                            optval = ''
                        self._handle_set_option(cursect, optname, optval)
                    else:
                        # valueless option handling
                        cursect[optname] = optval
                else:
                    # a non-fatal parsing error occurred.  set up the
                    # exception but keep going. the exception will be
                    # raised at the end of the file and will contain a
                    # list of all bogus lines
                    if not e:
                        e = ParsingError(fpname)
                    e.append(lineno, repr(line))
        # if any parsing errors occurred, raise an exception
        if e:
            raise e

        # join the multi-line values collected while reading
        all_sections = [self._defaults]
        all_sections.extend(self._sections.values())
        for options in all_sections:
            for name, val in options.items():
                if isinstance(val, list):
                    options[name] = '\n'.join(val)

    def _handle_set_option(self, cursect, optname, optval):
        if optname == 'include':
            self._handle_include(optval)
        elif optname == 'include_dir':
            self._handle_include_dir(optval)
        else:
            cursect[optname] = [optval]

    def _handle_include(self, path):
        self.read(path)

    def _handle_include_dir(self, path):
        for subdir, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.cfg'):
                    self.read(os.path.join(subdir, file))


class ConfigError(Exception):
    def __init__(self, message, exception):
        super(ConfigError, self).__init__(message)
        self.exception = exception


class NrpeConfig(Namespace):
    def __init__(self, defaults={}, args=Namespace(), config_file=None):
        self.__defaults = defaults
        self.__args = args
        self.__config_file = config_file

        self.reload()

    def _get_kwargs(self):
        return sorted((k, v) for k, v in self.__dict__.iteritems()
                      if not k.startswith('_'))

    def merge_into(self, ns):
        for key, value in vars(ns).iteritems():
            setattr(self, key, value)

    def get_defaults(self):
        defaults = Namespace()

        for key, value in self.__defaults.iteritems():
            setattr(defaults, key, value)

        return defaults

    def get_args(self):
        return self.__args

    def read_config_file(self):
        f = self.__config_file
        config = NrpeConfigParser()
        parsed = Namespace()
        secname = config.main_section  # default ini "section" for all config

        # If there isn't a config file to read, stop now
        if not f:
            return parsed

        # Attempt to read the config file
        try:
            with open(f) as fp:
                config.readfp(fp, f)
        except IOError, e:
            raise ConfigError(
                "{f}: failed to read file: {err}".format(
                    f=f, err=e.strerror), e)

        # Look for each key in __defaults, and transfer it to 'parsed'
        for key in self.__defaults:
            # Skip keys that aren't defined in the config file
            if not config.has_option(secname, key):
                continue

            dt = type(self.__defaults[key])
            value = config.get(secname, key)

            if dt is bool:  # is it a bool?
                try:
                    value = config.getboolean(secname, key)
                except ValueError, e:
                    raise ConfigError(
                        "{f}: {key}: expected a boolean but got '{value}'"
                        .format(f=f, key=key, value=value), e)
            elif dt is int:  # is int an integer?
                try:
                    value = config.getint(secname, key)
                except ValueError, e:
                    raise ConfigError(
                        "{f}: {key}: expected an integer but got '{value}'"
                        .format(f=f, key=key, value=value), e)
            elif dt is list:
                # Split into words separated by ','
                value = [x.strip() for x in value.split(',')]

            setattr(parsed, key, value)

        # To allow a sub-class to parse extra things
        self.read_extra_config(config, parsed)

        return parsed

    def read_extra_config(self, config, parsed):
        pass

    def reload(self):
        self.merge_into(self.get_defaults())
        self.merge_into(self.read_config_file())
        self.merge_into(self.get_args())
