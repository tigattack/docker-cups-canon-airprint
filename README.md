# docker-cups-canon-airprint

> [!NOTE]
> This fork is modified & maintained for my own personal use cases.
> As such, I have no plans to address feature requests or bugs that don't affect my own usage.

## Purpose

Run a container with CUPS, Avahi (mDNS/Bonjour), and Canon IJ (cnijfilter2) drivers so that local Canon printers can be exposed via AirPrint.

## Requirements
* must run on a linux host (could not yet figure out a way to run `macvlan` on macOS: https://github.com/docker/for-mac/issues/3447)
* the container must (really, really should) have its own, dedicated IP so it does not interfere
with other services listen on the ports required
(macOS: already runs CUPS and mdns, Linux: mostly also already runs CUPS and/or Avahi)
* you must have CUPS drivers available for your printer.

## Play with it
-> NOT WORKING on macOS! (https://docs.docker.com/docker-for-mac/networking/#per-container-ip-addressing-is-not-possible)
```shell script
docker run -d --rm -e CUPS_WEBINTERFACE="yes" -e CUPS_REMOTE_ADMIN="yes" --hostname mycups --name cups-setup drpsychick/airprint-bridge

# Important: administration will only be possible if hostname/ip match! (no portforwarding etc.)
# CUPS error if hostname mismatches: `Request from "172.17.42.1" using invalid Host: field "localhost:6310"`
echo "http://$(docker inspect --format '{{ .NetworkSettings.Networks.bridge.IPAddress }}' cups-setup):631"
# -> go to http://$IP:631/ and configure your printer(s)

# save printers.conf (to get the right device ID etc)
docker cp cups-setup:/etc/cups/printers.conf ./
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

### Add printer through ENV
Set any number of variables which start with `CUPS_LPADMIN_PRINTER`. These will be executed at startup to setup printers through `lpadmin`.
```shell script
CUPS_LPADMIN_PRINTER1=lpadmin -p test -D 'Test printer' -m raw -v ipp://myhost/printer
CUPS_LPADMIN_PRINTER2=lpadmin -p second -D 'another' -m everywhere -v ipp://myhost/second
CUPS_LPADMIN_PRINTER3_ENABLE=cupsenable third
```

### Configure AirPrint
Nothing to do, it will work out of the box (once you've added printers)

### Configure Google Cloud Print
*Update*: This is no longer supported since end of 2020! https://github.com/google/cloud-print-connector Support has been removed from this image.

### You're ready!
Now you have all you need to setup your airprint-bridge configured through ENV.
How to setup a dedicated server in your local subnet is covered in the next section.

## Prepare your dedicated AirPrint container
Create a virtual network bridge to your local network so that a docker container can have its own IP on your subnet AND 
be reachable from the host. As you want clients anywhere on the local network to discover printers, the container must 
have an IP on the local subnet.

**You don't need the macvlan bridge if your host does not need to talk to the container!**

### on a Linux host
All of this only works on a linux docker host.
```shell script
eth=<network interface> # eth0
mac=<network MAC> # AA:AA:AA:AA:AA
mac2=<fake MAC> # AA:AA:AA:AA:AB
# enable promicious mode (multiple MACs)
sudo ifconfig $eth promisc
sudo ip link set $eth address $mac2
sudo ip link add mac0 link $eth address $mac type macvlan mode bridge
# drop & flush DHCP lease on the interface
# start DHCP on new interface and restart resolver
sudo -- bash -c '(
dhclient -r $eth && ip addr flush dev $eth && ip neigh flush all
dhclient mac0 && service resolvconf restart || dhclient $eth
)'
```

Create a docker network for your local subnet. Parent interface is either `mac0` if you followed the above or `ethX`
if you decided you don't need to talk from the host to the container.
```
docker network create --driver macvlan --subnet 192.168.2.0/24 --gateway 192.168.2.1 -o parent=mac0 localnet
```

Now create your cups container with a specific IP on your local subnet
```shell script
cups_ip=192.168.2.100
cups_name=cups.home
docker create --name cups-test --net=localnet --ip=$cups_ip --hostname=$cups_name \
  --memory=100M -p 137:137/udp -p 139:139/tcp -p 445:445/tcp -p 631:631/tcp -p 5353:5353/udp \
  -e CUPS_USER_ADMIN=admin -e CUPS_USER_PASSWORD=secr3t \
  drpsychick/airprint-bridge:latest

# start it
docker start cups-test

# open a shell
docker exec -it cups-test /bin/bash
```

## Adding printers:
**Hint**: When you want to use a local USB printer, use `--volume /dev/bus/usb:/dev/bus/usb` to mount the USB device directly into the container. (see also https://github.com/SickHub/docker-cups-airprint/issues/35)

### Automated through command line
The preferred way to configure your container, but it has limitations.
```shell script
# search for your printer
lpinfo --make-and-model "Epson Stylus Photo RX" -m
lpadmin -p Epson-RX520 -D 'Epson Stylus Photo RX520' -m 'gutenprint.5.3://escp2-rx620/expert' -v ipp://10.1.2.3/
```

Pass `lpadmin` command via environment
```shell script
docker ... -e CUPS_LPADMIN_PRINTER1="lpadmin -p Epson-RX520 -D 'Epson Stylus Photo RX520' -m 'gutenprint.5.3://escp2-rx620/expert' -o PageSize=A4 -v ipp://10.1.2.3/" ...
```

Find and set printer specific options
```shell script
lpoptions -p Epson-RX520 -l
# -> lists all printer options you can pass to `lpadmin` like `-o PageSize=A4`
```

Enable the printer and accept jobs
```shell script
CUPS_LPADMIN_PRINTER1_ENABLE=cupsenable Epson-RX520
CUPS_LPADMIN_PRINTER1_ACCEPT=cupsaccept Epson-RX520
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


## Issues:
https://github.com/SickHub/docker-cups-airprint/issues

## Hints for QNAP
* using `macvlan` is not possible, instead you should use `qnet` driver to create the docker network
```shell script
docker network create --driver=qnet --ipam-driver=qnet --ipam-opt=iface=bond0 --subnet ...
```

# Credits
this is based on awesome work of others
* https://hub.docker.com/r/jstrader/airprint-cloudprint/
* https://github.com/tjfontaine/airprint-generate
* Debian Wiki with notes on limitations of AirPrint support in CUPS: https://wiki.debian.org/CUPSAirPrint

# Contribute
* I'm happy for any feedback! Create issues, dicussions, ... feel free and involve!
* Send me a PR
