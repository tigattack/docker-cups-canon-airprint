# docker-cups-canon-airprint

## Purpose

A Docker image with:
* CUPS
* Avahi (mDNS/Bonjour) for network autodiscovery of printer(s)
* Canon IJ (cnijfilter2) drivers
* Printer power management features:
  * Script to send printer idle status to a webhook
  * Script to send power-on request to a webhook

> [!NOTE]
> This fork is modified & maintained for my own personal use cases.
> As such, I am unlikely to address feature requests or bug reports that don't affect my own usage.

## Run It
```shell
docker run -d --rm --network host --name cups ghcr.io/tigattack/cups-canon-airprint
```

### Variables overview
Important! Docker environment variables only support single line without double quotes!
```shell script
CUPS_ADMIN_USER=${CUPS_ADMIN_USER:-"admin"}
CUPS_ADMIN_PASSWORD=${CUPS_ADMIN_PASSWORD:-"secr3t"}
CUPS_WEBINTERFACE=${CUPS_WEBINTERFACE:-"yes"}
CUPS_SHARE_PRINTERS=${CUPS_SHARE_PRINTERS:-"yes"}
CUPS_REMOTE_ADMIN=${CUPS_REMOTE_ADMIN:-"yes"} # allow admin from non local source
CUPS_ACCESS_LOGLEVEL=${CUPS_ACCESS_LOGLEVEL:-"config"} # all, access, config, see `man cupsd.conf`
CUPS_LOGLEVEL=${CUPS_LOGLEVEL:-"warn"} # error, warn, info, debug, debug2 see `man cupsd.conf`
CUPS_ENV_DEBUG=${CUPS_ENV_DEBUG:-"no"} # debug startup script and activate CUPS debug logging
CUPS_IP=${CUPS_IP:-$(hostname -i)} # no need to set this usually
CUPS_HOSTNAME=${CUPS_HOSTNAME:-$(hostname -f)} # no need to set this usually -> allows accessing cups via name: https://cups.domain:631/
# pass the server cert/key via env in one line each, i.e. CUPS_SSL_CERT=---- BEGIN CERT ...\none\nline\nseparated\nby\nbackslash\nnewline
CUPS_SSL_CERT=${CUPS_SSL_CERT:-""}
CUPS_SSL_KEY=${CUPS_SSL_KEY:-""}
# avahi configuration options
AVAHI_INTERFACES=${AVAHI_INTERFACES:=""}
AVAHI_IPV6=${AVAHI_IPV6:="no"}
AVAHI_REFLECTOR=${AVAHI_REFLECTOR:="no"}
AVAHI_REFLECT_IPV=${AVAHI_REFLECT_IPV:="no"}
PRE_INIT_HOOK=${PRE_INIT_HOOK:="/root/pre-init-script.sh"} # A path to a script OR a command. This offers the possibility to execute a custom script before the printer gets installed and before CUPS starts.
```

### Power Scripts

There are two scripts packaged with this image. See below for a description of each and how they can be configured.

#### `printer_idle.py`

[This script](power_scripts/printer_idle.py) POST's the idle status of your printer(s) to the defined webhook URL.

This POSTed data can be used by e.g. Home Assistant to determine when the printer is idle and power off a smart plug.

Here's a sample of the webhook body: `{"printer": "MyPrinter", "idle": true, "idle_time": 43680}`

**Variables:**

* `PRINTER_IDLE_PRINTERS` (default: null): Comma-seperated list of printer names as set in CUPS. Only required if multiple printers are available.
* `PRINTER_IDLE_THRESHOLD` (default: `3600`): Seconds since last job to consider printer idle.
* `PRINTER_IDLE_WEBHOOK_URL` (default: null): Webhook URL to send idle printer information to.
* `PRINTER_IDLE_CHECK_INTERVAL` (default: `60`): Idle check/send interval in seconds.
* `PRINTER_IDLE_LOGLEVEL` (default: `INFO`): Can be any valid Python logging level. Likely `DEBUG` is the only other useful option here, though.

#### `printer_power_on.py`

[This script](power_scripts/printer_power_on.py) POST's to a webhook URL to request the printer be powered on (e.g. by Home Assistant).

This runs as a print job pre-hook via tea4cups and will wait (up to the configured timeout) for the printer to become available before allowing the job to continue by means of attempting a connection to port 631 (IPP) on the printer.

If the printer does not become available within the wait timeout, the script will give up waiting and the job will be cancelled.

Here's a sample of the webhook body: `{"power_on": "MyPrinter"}`

**Variables:**

* `PRINTER_POWERON_NAME` (default: null): Printer name, as set in CUPS, for which power on requests should be sent.
* `PRINTER_POWERON_HOST` (default: null): Printer IP or hostname to use when waiting for printer to become available.
* `PRINTER_POWERON_WAIT_TIMEOUT` (default: `120`): How long to wait for the printer to become available.
* `PRINTER_POWERON_WEBHOOK_URL` (default: null): Webhook URL to send printer power on request to.
* `PRINTER_POWERON_LOGLEVEL` (default: `INFO`): Can be any valid Python logging level. Likely `DEBUG` is the only other useful option here, though.

### Add printer through ENV
Set any number of variables which start with `CUPS_LPADMIN_PRINTER`. These will be executed at startup to setup printers through `lpadmin`.
```shell script
CUPS_LPADMIN_PRINTER1=lpadmin -p test -D 'Test printer' -m raw -v ipp://myhost/printer
CUPS_LPADMIN_PRINTER2=lpadmin -p second -D 'another' -m everywhere -v ipp://myhost/second
CUPS_LPADMIN_PRINTER3_ENABLE=cupsenable third
```

### Configure AirPrint
Nothing to do, it will work out of the box (once you've added printers)

### You're ready!
Now you have all you need to setup your CUPS server, with AirPrint support, configured through ENV.

## Adding printers:
**Hint**: When you want to use a local USB printer, use `--volume /dev/bus/usb:/dev/bus/usb` to mount the USB device directly into the container. (see also https://github.com/SickHub/docker-cups-airprint/issues/35)

### Automated through command line
The preferred way to configure your container, but it has limitations.
```shell script
# search for your printer
lpinfo --make-and-model "Canon TS7450i" -m
lpadmin -p CanonTS7450i -D 'Canon TS7450i' -E -m canonts7450i.ppd -v ipp://10.52.30.35/
```

Pass `lpadmin` command via environment
```shell script
docker ... -e CUPS_LPADMIN_PRINTER1="lpadmin -p CanonTS7450i -D 'Canon TS7450i' -E -m canonts7450i.ppd -v ipp://10.52.30.35/ -o PageSize=A4 " ...
```

Find and set printer specific options
```shell script
lpoptions -p CanonTS7450i -l
# -> lists all printer options you can pass to `lpadmin` like `-o PageSize=A4`
```

### Manually through web interface
Enable the interface through ENV: `CUPS_WEBINTERFACE="yes"` and `CUPS_REMOTE_ADMIN="yes"`.

**You may want to enable this only temporarily!**

Enable it manually through config:
`cupds.conf`:
```shell script
Listen *:631
WebInterface Yes
<Location />
  Order allow,deny
  Allow from all
</Location>
<Location /admin>
  Order allow,deny
  Allow from all
</Location>
```
Then go to `https://$cups_ip:631/admin` or `https://$cups_name:631`, login and setup your printer(s).

## Test it
1. on any macOS device, add a new printer. You'll find your printer prefixed with `AirPrint` in the `default` tab
2. on the web interface, select `Print Test Page` in the `Maintenance` dropdown
3. on any iOS device, take any file and tap on share -> print -> select printer -> (select a printer from the list)

![Share -> Print](docs/1-share-print.png)
![-> select printer](docs/2-select-printer.png)
![Printer list](docs/3-printer-list.png)
![Print](docs/4-print.png)
![Printer info](docs/5-printer-info.png)


# Credits
this is based on awesome work of others
* https://github.com/SickHub/docker-cups-airprint
* https://hub.docker.com/r/jstrader/airprint-cloudprint/
* https://github.com/tjfontaine/airprint-generate
* Debian Wiki with notes on limitations of AirPrint support in CUPS: https://wiki.debian.org/CUPSAirPrint
* Printer power management:
  * https://github.com/raphis/docker-cups-ha-webhook
  * Some inspiration from https://unixorn.github.io/post/home-assistant-printer-power-management
