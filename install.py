#
#    Copyright (c) 2019 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
"""Installer for the XDR service"""

try:
    # Python 2
    from StringIO import StringIO
except ImportError:
    # Python 3
    from io import StringIO

import configobj
from weecfg.extension import ExtensionInstaller

xdr_config = """
[XDR]
    # The port where the NMEA source is located. Default is '/dev/ttyACM0'
    port = /dev/ttyACM0
    # Its baudrate. Default is '9600'.
    baudrate = 9600
    # How long to wait for an XDR packet before giving up. Default is 5 seconds.
    timeout = 5
    # Max number of NMEA packets to process during a LOOP event. Default is 5 packets
    max_packets = 5

    # Map from weewx names to sensor names. Only these types will be processed.
    # Typical sensor map:
    [[sensor_map]]
        pressure = P    # Raw, station pressure
        outTemp = C     # Temperature
"""

xdr_dict = configobj.ConfigObj(StringIO(xdr_config))


def loader():
    return XDRInstaller()


class XDRInstaller(ExtensionInstaller):
    def __init__(self):
        super(XDRInstaller, self).__init__(
            version="0.10",
            name='xdr',
            description='Augment WeeWX records with data NMEA0183 XDR sentences.',
            author="Thomas Keffer",
            author_email="tkeffer@gmail.com",
            data_services='user.nmea-xdr.XDR',
            config=xdr_dict,
            files=[('bin/user', ['bin/user/nmea-xdr.py'])]
            )
