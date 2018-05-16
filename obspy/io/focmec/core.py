#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FOCMEC file format support for ObsPy

:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (https://www.gnu.org/copyleft/lesser.html)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA @UnusedWildImport

from obspy import UTCDateTime, Catalog, __version__
from obspy.core.event import (
    Event, FocalMechanism, NodalPlanes, NodalPlane, Comment, CreationInfo)


# XXX some current PR was doing similar, should be merged to
# XXX core/utcdatetime.py eventually..
months = {
    'jan': 1,
    'feb': 2,
    'mar': 3,
    'apr': 4,
    'may': 5,
    'jun': 6,
    'jul': 7,
    'aug': 8,
    'sep': 9,
    'oct': 10,
    'nov': 11,
    'dec': 12}


def _is_focmec(filename):
    """
    Checks that a file is actually a FOCMEC output data file
    """
    try:
        with open(filename, 'rb') as fh:
            line = fh.readline()
    except Exception:
        return False
    # first line should be ASCII only, something like:
    #   Fri Sep  8 14:54:58 2017 for program Focmec
    try:
        line = line.decode('ASCII')
    except:
        return False
    line = line.split()
    # program name 'focmec' at the end is written slightly differently
    # depending on how focmec was compiled, sometimes all lower case sometimes
    # capitalized..
    line[-1] = line[-1].lower()
    if line[-3:] == ['for', 'program', 'focmec']:
        return True
    return False


def _read_focmec(filename, **kwargs):
    """
    Reads a FOCMEC '.lst' or '.out' file to a
    :class:`~obspy.core.event.Catalog` object.

    .. warning::
        This function should NOT be called directly, it registers via the
        ObsPy :func:`~obspy.core.event.catalog.read_events()` function, call
        this instead.

    :param filename: File or file-like object in text mode.
    :rtype: :class:`~obspy.core.event.Catalog`
    """
    if not hasattr(filename, "read"):
        # Check if it exists, otherwise assume its a string.
        try:
            with open(filename, "rb") as fh:
                data = fh.read()
            data = data.decode("UTF-8")
        except Exception:
            try:
                data = filename.decode("UTF-8")
            except Exception:
                data = str(filename)
            data = data.strip()
    else:
        data = filename.read()
        if hasattr(data, "decode"):
            data = data.decode("UTF-8")

    # split lines
    lines = [line for line in data.splitlines()]

    # line 6 in 'lst' format should look like this:
    # " Statn  Azimuth    TOA   Key  Log10 Ratio  NumPol  DenTOA  Comment"
    if lines[5].split() == [
            'Statn', 'Azimuth', 'TOA', 'Key', 'Log10', 'Ratio', 'NumPol',
            'DenTOA', 'Comment']:
        event = _read_focmec_lst(lines)
    # line 16 in 'out' format should look like this:
    # "    Dip   Strike   Rake    Pol: P     SV    SH  AccR/TotR  RMS RErr..."
    # But on older program version output, it's instead line number 14, so it
    # might depend on input data (polarities and/or amplitude ratios) and thus
    # what the program outputs as info (different settings available depending
    # on input data)
    else:
        for line in lines[4:30]:
            if line.split() == [
                    'Dip', 'Strike', 'Rake', 'Pol:', 'P', 'SV', 'SH',
                    'AccR/TotR', 'RMS', 'RErr', 'AbsMaxDiff']:
                event = _read_focmec_out(lines)
                break
        else:
            msg = ("Input was not recognized as either FOCMEC 'lst' or "
                   "'out' file format. Please contact developers if input "
                   "indeed is one of these two file types.")
            raise ValueError(msg)

    cat = Catalog(events=[event])
    cat.creation_info.creation_time = UTCDateTime()
    cat.creation_info.version = "ObsPy %s" % __version__
    return cat


def _is_lst_block_start(line):
    if line.strip().startswith('+' * 20):
        return True
    return False


def _go_to_next_lst_block(lines):
    while lines and not _is_lst_block_start(lines[0]):
        lines.pop(0)
    return lines


def _read_focmec_lst(lines):
    """
    Read given data into an :class:`~obspy.core.event.Event` object.

    :type lines: list
    :param lines: List of decoded unicode strings with data from a FOCMEC lst
        file.
    """
    event, lines = _read_common_header(lines)
    while lines:
        lines = _go_to_next_lst_block(lines)
        focmec, lines = _read_focmec_lst_one_block(lines)
        if focmec is None:
            break
        event.focal_mechanisms.append(focmec)
    return event


def _read_focmec_lst_one_block(lines):
    while lines and not lines[0].lstrip().startswith('Dip,Strike,Rake'):
        lines.pop(0)
    # the last block does not contain a focmec but only a short comment how
    # many solutions there were overall, so we hit a block that will not have
    # the above line and we exhaust the lines list
    if not lines:
        return None, []
    dip, strike, rake = [float(x) for x in lines[0].split()[1:4]]
    plane1 = NodalPlane(strike=strike, dip=dip, rake=rake)
    lines.pop(0)
    dip, strike, rake = [float(x) for x in lines[0].split()[1:4]]
    plane2 = NodalPlane(strike=strike, dip=dip, rake=rake)
    planes = NodalPlanes(nodal_plane_1=plane1, nodal_plane_2=plane2,
                         preferred_plane=1)
    focmec = FocalMechanism(nodal_planes=planes)
    return focmec, lines


def _read_focmec_out(lines):
    """
    Read given data into an :class:`~obspy.core.event.Event` object.

    :type lines: list
    :param lines: List of decoded unicode strings with data from a FOCMEC out
        file.
    """
    event, lines = _read_common_header(lines)
    # now move to first line with a focal mechanism
    while lines and lines[0].split()[:3] != ['Dip', 'Strike', 'Rake']:
        lines.pop(0)
    for line in lines[1:]:
        # allow for empty lines (maybe they can happen at the end sometimes..)
        if not line.strip():
            continue
        dip, strike, rake = [float(x) for x in line.split()[:3]]
        plane = NodalPlane(strike=strike, dip=dip, rake=rake)
        planes = NodalPlanes(nodal_plane_1=plane, preferred_plane=1)
        # XXX ideally should compute the auxilliary plane..
        focmec = FocalMechanism(nodal_planes=planes)
        event.focal_mechanisms.append(focmec)
    return event


def _read_common_header(lines):
    """
    Read given data into an :class:`~obspy.core.event.Event` object.

    Parses the first few common header lines and sets creation time and some
    other basic info.

    :type lines: list
    :param lines: List of decoded unicode strings with data from a FOCMEC out
        file.
    """
    event = Event()
    # parse time.. too much bother to mess around with switching locales, so do
    # it manually.. example:
    # "  Fri Sep  8 14:54:58 2017 for program Focmec"
    month, day, time_of_day, year = lines[0].split()[1:5]
    year = int(year)
    day = int(day)
    month = int(months[month.lower()])
    hour, minute, second = [int(x) for x in time_of_day.split(':')]
    event.creation_info = CreationInfo()
    event.creation_info.creation_time = UTCDateTime(
        year, month, day, hour, minute, second)
    # parse comments given in the next lines
    text = '\n'.join([l.strip() for l in lines[1:4]])
    event.comments.append(Comment(text=text))
    # get rid of those common lines already parsed
    lines = lines[4:]
    return event, lines


if __name__ == '__main__':
    import doctest
    doctest.testmod(exclude_empty=True)
