# nmea-xdr
WeeWX service that decodes NMEA 0183 "XDR" sentences and adds values
to the WeeWX data stream.

## Installation instructions

1. Download and install the extension

    ```shell
    cd /home/weewx
    wget https://github.com/tkeffer/weewx-nmea-xdr/archive/nmea-xdr-0.1.0.tar.gz
    wee_extension --install=nmea-xdr-0.1.0.tar.gz
    ```

2. Edit the new stanza `[XDR]` to reflect your situation. Here's an example:

   ```ini
    [XDR]
        port = /dev/ttyUSB0
    
        # Map from weewx names to sensor names. Only these types will be processed.
        # Typical sensor map:
        [[sensor_map]]
            pressure = P    # Raw, station pressure
    ```
    This example most relies on the defaults, although it adds an explicity device
    port where the NMEA device can be found (`/dev/ttyUSB0`).

   It maps only one observation type, `pressure`, to the incoming XDR data, `P`.

3. Restart WeeWX. For example:

   ```shell
   sudo systemctl stop weewx
   sudo systemctl start weewx
   ```

4. With every LOOP packet, the queue of NMEA sentences will be drained. All data listed
in the sensor map will be parsed and added to the LOOP packet.


## Manual installation instructions



1. Include a stanza in your weewx.conf configuration file:

    ```ini
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
    ```

2. Add the XDR service to the list of data_services to be run:

    ```ini
    [Engine]
      [[Services]]
        ...
        data_services = nmea-xdr.XDR
    ```

2. Put this file (nmea-xdr.py) in your WeeWX user subdirectory.
For example, if you installed using setup.py,

    ```shell
    cp nmea-xdr.py /home/weewx/bin/user
   ```
    
4. Restart WeeWX. For example:

   ```shell
   sudo systemctl stop weewx
   sudo systemctl start weewx
   ```

5. With every LOOP packet, the queue of NMEA sentences will be drained. All data listed
in the sensor map will be parsed and added to the LOOP packet.
 


