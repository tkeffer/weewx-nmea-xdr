#
#    Copyright (c) 2019-2020 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
"""Service that decodes NMEA 0183 "XDR" sentences and puts the results in the data stream.

To use:

1. Include a stanza in your weewx.conf configuration file:

[XDR]
    port = /dev/ttyACM0         # Default is '/dev/ttyACM0'
    baudrate = 9600             # Default is '9600'
    timeout = 5                 # How long to wait for an XDR packet. Default is 5
    max_packets = 5             # Max number of packets to process during a LOOP event. Default is 5

    # Map from weewx names to sensor names. Only these types will be processed.
    # Typical sensor map:
    [[sensor_map]]
        pressure = P    # Raw, station pressure
        outTemp = C     # Temperature

2. Add the XDR service to the list of data_services to be run:

[Engine]
  [[Services]]
    ...
    data_services = nmea-xdr.XDR

3. Put this file (nmea-xdr.py) in your WeeWX user subdirectory.
For example, if you installed using setup.py,

    cp nmea-xdr.py /home/weewx/bin/user
"""

try:
    import queue
except ImportError:
    import Queue as queue
import operator
import threading
from functools import reduce

import serial

import weewx.engine
import weewx.units
from weeutil.weeutil import to_int

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging

    log = logging.getLogger(__name__)


    def logdbg(msg):
        log.debug(msg)


    def loginf(msg):
        log.info(msg)


    def logerr(msg):
        log.error(msg)

except ImportError:
    # Old-style weewx logging
    import syslog


    def logmsg(level, msg):
        syslog.syslog(level, 'nmea-xdr: %s:' % msg)


    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)


    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)


    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)

VERSION = "0.11"

# Lock used to coordinate access to the "keep_running" variable in the child thread
run_lock = threading.Lock()


class XDR(weewx.engine.StdService):
    """WeeWX service for augmenting a record with data parsed from an NMEA0183 XDR input."""

    def __init__(self, engine, config_dict):
        # Initialize my superclass:
        super(XDR, self).__init__(engine, config_dict)

        # Extract our stanza from the configuration dictionary
        xdr_dict = config_dict.get('XDR', {})

        # Extract stuff out of the resultant dictionary
        port = xdr_dict.get('port', '/dev/ttyACM0')
        baudrate = to_int(xdr_dict.get('baudrate', 9600))
        timeout = to_int(xdr_dict.get('timeout', 5))
        self.max_packets = to_int(xdr_dict.get('max_packets', 5))
        self.sensor_map = xdr_dict.get('sensor_map', {})
        loginf("Sensor map is %s" % self.sensor_map)

        self.queue = queue.Queue()

        self.bind(weewx.STARTUP, self.startup)
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)

        self.thread = XDRThread(self.queue, port, baudrate, timeout)
        self.thread.setDaemon(True)

    def startup(self, _event):
        """Starts the XDRThread just before the main loop is entered."""
        self.thread.start()

    def new_loop_packet(self, event):
        """Add the latest XDR packets to the LOOP data stream"""

        while True:
            # Drain the queue until there are only max_packets left:
            while self.queue.qsize() > self.max_packets:
                self.queue.get_nowait()

            # Process what's left
            try:
                xdr_line = self.queue.get_nowait()
            except queue.Empty:
                return

            if weewx.debug >= 2:
                logdbg("Raw XDR data: %s" % xdr_line)

            parts = xdr_line.split(',')
            # Each sensor in an XDR sentence has four parts. Group the sentence accordingly.
            it = iter(parts[1:])
            sentences = zip(*[it, it, it, it])

            # The variable 'sentences' is a list of 4-way tuples. Handle each tuple separately.
            for transducer_type, data, unit, name in sentences:
                # Ignore sensors with no data by making sure that these three variables are there:
                if transducer_type and data and unit:
                    # Look for this transducer type in the sensor map
                    for obs_type in self.sensor_map:
                        if self.sensor_map[obs_type] == transducer_type:
                            # We found it. Now we need to get the data
                            # and we need it in the correct units
                            try:
                                f_data = float(data)
                            except ValueError:
                                # If we can't convert it to a float, ignore it.
                                continue
                            if unit == 'C':
                                unit = 'degree_C'
                                group = 'group_temperature'
                            elif unit == 'F':
                                unit = 'degree_F'
                                group = 'group_temperature'
                            elif unit == 'B':
                                f_data *= 1000.0
                                unit = 'mbar'
                                group = 'group_pressure'
                            else:
                                if weewx.debug >= 2:
                                    logdbg("Rejected: %s, %f, %s, %s"
                                           % (transducer_type, f_data, unit, name))
                                continue

                            # Form a ValueTuple using the unit and unit group
                            val_t = weewx.units.ValueTuple(f_data, unit, group)
                            # Convert it to the same unit system as the incoming packet
                            target_t = weewx.units.convertStd(val_t, event.packet['usUnits'])
                            # Now update the value in the packet
                            event.packet[obs_type] = target_t.value
                            if weewx.debug >= 2:
                                logdbg("Set type '%s' to %.3f from transducer '%s'"
                                       % (obs_type, event.packet[obs_type], name))

    def shutDown(self):
        global run_lock
        if self.thread:
            log.info("Shutting down XDRThread")
            # Acquire the lock, then shut off the run flag
            with run_lock:
                self.thread.keep_running = False
            # Wait up to 5 seconds for the thread to exit.
            self.thread.join(5.0)
            if self.thread.isAlive():
                log.error("Unable to shut down XDRThread")
            else:
                log.debug("XDRThread has been terminated")
        self.thread = None


class XDRThread(threading.Thread):
    """Read from an NMEA 0183 XDR device."""

    def __init__(self, q, port='/dev/ttyACM0', baudrate=9600, timeout=5):
        threading.Thread.__init__(self, name="XDRThread")
        self.queue = q
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.keep_running = True

    def run(self):
        """Open the port and run."""

        # Open up the port
        with serial.Serial(port=self.port, baudrate=self.baudrate, timeout=self.timeout) as device:

            # Loop indefinitely as long as the keep_running flag is true
            while True:
                with run_lock:
                    if not self.keep_running:
                        return

                # Block, waiting to read a line. It may end with \r\n. Strip it off. Convert from bytes to unicode
                # string
                line = device.readline().strip().decode('ascii')

                # Look for the '$' symbol which marks the start of an NMEA 0183 sentence.
                if line[0] != u'$':
                    # No '$'. Ignore the line.
                    continue

                # Find the start of the checksum. It's marked with an asterisk.
                asterisk = line.rfind(u'*')
                if asterisk == -1:
                    # No asterisk. Ignore the line.
                    continue

                try:
                    # Extract the expected checksum. If there is garbage in there, this may
                    # raise an exception. Be prepared to catch it.
                    expected_cs = int(line[asterisk + 1:], 16)
                except ValueError:
                    # Garbage in expected checksum. On to the next line
                    continue
                # Calculate the actual checksum by XORing everything together between the dollar
                # sign and the asterisk. The following works under both Python 2 and 3.
                actual_cs = reduce(operator.xor, bytearray(line[1:asterisk]), 0)
                # If they don't match, ignore the line
                if expected_cs != actual_cs:
                    continue

                # We are only interested in XDR sentences
                if line[3:6] != u'XDR':
                    continue

                # All looks good. Put the line in the queue, without the checksum:
                self.queue.put_nowait(line[:asterisk])

# q = queue.Queue()
# t = XDRThread(q)
# t.run()
