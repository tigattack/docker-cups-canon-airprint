#!/bin/bash
set -e

### Enable debug if debug flag is true ###
[ "yes" = "${CUPS_ENV_DEBUG}" ] && set -x

### variable defaults
CUPS_IP=${CUPS_IP:-$(hostname -i)}
CUPS_HOSTNAME=${CUPS_HOSTNAME:-$(hostname -f)}
CUPS_ADMIN_USER=${CUPS_ADMIN_USER:-"admin"}
CUPS_ADMIN_PASSWORD=${CUPS_ADMIN_PASSWORD:-"secr3t"}
CUPS_WEBINTERFACE=${CUPS_WEBINTERFACE:-"yes"}
CUPS_SHARE_PRINTERS=${CUPS_SHARE_PRINTERS:-"yes"}
CUPS_REMOTE_ADMIN=${CUPS_REMOTE_ADMIN:-"yes"}
CUPS_ACCESS_LOGLEVEL=${CUPS_ACCESS_LOGLEVEL:-"config"}
CUPS_LOGLEVEL=${CUPS_LOGLEVEL:-"warn"}
CUPS_NO_FORCE_SSL=${CUPS_NO_FORCE_SSL:-""}
CUPS_SSL_CERT=${CUPS_SSL_CERT:-""}
CUPS_SSL_KEY=${CUPS_SSL_KEY:-""}
AVAHI_INTERFACES=${AVAHI_INTERFACES:=""}
AVAHI_FRIENDLY_DESC=${AVAHI_FRIENDLY_DESC=:-"no"}
AVAHI_IPV6=${AVAHI_IPV6:="no"}
AVAHI_REFLECTOR=${AVAHI_REFLECTOR:="no"}
AVAHI_REFLECT_IPV=${AVAHI_REFLECT_IPV:="no"}
PRE_INIT_HOOK=${PRE_INIT_HOOK:="/root/pre-init-script.sh"} 
[ "yes" = "${CUPS_ENV_DEBUG}" ] && export -n

### check for valid input
if printf '%s' "${CUPS_ADMIN_PASSWORD}" | LC_ALL=C grep -q '[^ -~]\+'; then
  RETURN=1; REASON="CUPS password contain illegal non-ASCII characters, aborting!"; exit;
fi

### create admin user if it does not exist
if [ $(grep -ci ${CUPS_ADMIN_USER} /etc/shadow) -eq 0 ]; then
  echo "-->  Creating CUPS admin user '${CUPS_ADMIN_USER}'..."
  useradd ${CUPS_ADMIN_USER} --system -g lpadmin --no-create-home --password $(mkpasswd ${CUPS_ADMIN_PASSWORD})
  if [[ ${?} -ne 0 ]]; then RETURN=${?}; REASON="Failed to set password ${CUPS_ADMIN_PASSWORD} for user root, aborting!"; exit; fi
fi

### prepare cups configuration: log everything to stdout/stderr
echo -e "\n-->  Patching CUPS configs..."
sed -i 's/^.*AccessLog .*/AccessLog stdout/' /etc/cups/cups-files.conf
sed -i 's/^.*ErrorLog .*/ErrorLog stderr/' /etc/cups/cups-files.conf
sed -i 's/^.*PageLog .*/PageLog stdout/' /etc/cups/cups-files.conf
if [ "yes" = "${CUPS_REMOTE_ADMIN}" -a -z "$(grep "^Listen \*:631" /etc/cups/cupsd.conf)" ]; then
  [ -z "$(grep "^Listen localhost:631" /etc/cups/cupsd.conf)" ] &&
    echo "Listen *:631" >> /etc/cups/cupsd.conf ||
    sed -i 's/Listen localhost:631/Listen *:631/' /etc/cups/cupsd.conf

    if grep -q 'ServerAlias' /etc/cups/cupsd.conf; then
      sed -i 's/^.*ServerAlias.*/ServerAlias */' /etc/cups/cupsd.conf
    else
      echo "ServerAlias *" >> /etc/cups/cupsd.conf
    fi
fi
if [ "true" = "${CUPS_NO_FORCE_SSL}" ]; then
  if grep -q 'DefaultEncryption' /etc/cups/cupsd.conf; then
    sed -i 's/^.*DefaultEncryption.*/DefaultEncryption Never/' /etc/cups/cupsd.conf
  else
    echo "DefaultEncryption Never" >> /etc/cups/cupsd.conf
  fi
fi
# own SSL cert:
# CreateSelfSignedCerts no
# host.name.crt & host.name.key -> /etc/cups/ssl/
if [ -n "${CUPS_SSL_CERT}" -a -n "${CUPS_SSL_KEY}" ]; then
  [ -z "$(grep CreateSelfSignedCerts /etc/cups/cups-files.conf)" ] && 
    echo "CreateSelfSignedCerts no" >> /etc/cups/cups-files.conf || 
    sed -i 's/^.*CreateSelfSignedCerts.*/CreateSelfSignedCerts no/' /etc/cups/cups-files.conf
  echo -e "${CUPS_SSL_CERT}" > /etc/cups/ssl/${CUPS_HOSTNAME}.crt
  echo -e "${CUPS_SSL_KEY}" > /etc/cups/ssl/${CUPS_HOSTNAME}.key
fi

### prepare avahi-daemon configuration (dbus disabled by default)
echo -e "\n-->  Patching avahi config..."
if [ -n "${AVAHI_INTERFACES}" ]; then
  sed -i "s/^.*allow-interfaces=.*/allow-interfaces=${AVAHI_INTERFACES}/" /etc/avahi/avahi-daemon.conf
fi
sed -i "s/^.*use-ipv6=.*/use-ipv6=${AVAHI_IPV6}/" /etc/avahi/avahi-daemon.conf
sed -i "s/^.*publish-aaaa-on-ipv4=.*/publish-aaaa-on-ipv4=${AVAHI_IPV6}/" /etc/avahi/avahi-daemon.conf
sed -i "s/^.*enable\-reflector=.*/enable\-reflector\=${AVAHI_REFLECTOR}/" /etc/avahi/avahi-daemon.conf
sed -i "s/^.*reflect\-ipv=.*/reflect\-ipv\=${AVAHI_REFLECT_IPV}/" /etc/avahi/avahi-daemon.conf
sed -i 's/^.*enable-dbus=.*/enable-dbus=no/' /etc/avahi/avahi-daemon.conf

# Run custom user code before starting any service
# Check if PRE_INIT_HOOK is a file path
if [ -f "$PRE_INIT_HOOK" ]; then
    echo "Executing script at $PRE_INIT_HOOK"
    /bin/bash "$PRE_INIT_HOOK"
else # or a command
    echo "Executing command: $PRE_INIT_HOOK"
    /bin/bash -c "$PRE_INIT_HOOK"
fi

# start automatic printer refresh for avahi
echo -e "\n-->  Launching avahi-generate watch script..."
/opt/airprint/printer-update.sh &

# ensure avahi is running in background (but not as daemon as this implies syslog)
echo -e "\n-->  Launching avahi-daemon..."
(
while (true); do
  /usr/sbin/avahi-daemon -c || { /usr/sbin/avahi-daemon & }
  sleep 5
done
) &
sleep 1

# start printer idle check script
echo -e "\n-->  Launching printer idle check script..."
/opt/power_scripts/printer_idle_check.sh &
sleep 1

### configure CUPS (background subshell, wait till cups http is running...)
echo -e "\n-->  Configuring CUPS..."
(
until cupsctl -h localhost:631 --share-printers > /dev/null 2>&1; do echo -n "."; sleep 1; done;
until cupsctl --debug-logging > /dev/null 2>&1; do echo -n "."; sleep 1; done;
echo -e "\n-->  CUPS ready"
[ "yes" = "${CUPS_ENV_DEBUG}" ] && cupsctl --debug-logging || cupsctl --no-debug-logging
[ "yes" = "${CUPS_REMOTE_ADMIN}" ] && cupsctl --remote-admin --remote-any || cupsctl --no-remote-admin
[ "yes" = "${CUPS_SHARE_PRINTERS}" ] && cupsctl --share-printers || cupsctl --no-share-printers
[ "yes" = "${CUPS_WEBINTERFACE}" ] && cupsctl WebInterface=yes || cupsctl WebInterface=No
cupsctl ServerName=${CUPS_HOSTNAME}
cupsctl LogLevel=${CUPS_LOGLEVEL}
cupsctl AccessLogLevel=${CUPS_ACCESS_LOGLEVEL}
# setup printers (run each CUPS_LPADMIN_PRINTER* command)
echo -e "\n-->  Adding printers"
for v in $(set |grep ^CUPS_LPADMIN_PRINTER |sed -e 's/^\(CUPS_LPADMIN_PRINTER[^=]*\).*/\1/' |sort |tr '\n' ' '); do
  echo "$v = $(eval echo "\$$v")"
  eval $(eval echo "\$$v")
done
echo -e "\n-->  CUPS configured"
) &

echo -e "\n-->  Patching Tea4CUPS config..."
sed -i "s/PRINTER_NAME_PLACEHOLDER/"${PRINTER_POWERON_NAME}"/" /etc/cups/tea4cups.conf

(sleep 2;
cat <<EOF
===========================================================
The CUPS instance is now ready for use!
The web interface is available here:
URL:       http://${CUPS_IP}:631/ or http://${CUPS_HOSTNAME}:631/
Username:  ${CUPS_ADMIN_USER}
Password:  ${CUPS_ADMIN_PASSWORD}

===========================================================
EOF
) &

### Start CUPS instance ###
/usr/sbin/cupsd -f
