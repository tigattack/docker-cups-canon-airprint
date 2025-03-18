#!/usr/bin/env bash

PRINTER_IDLE_CHECK_INTERVAL=${PRINTER_IDLE_CHECK_INTERVAL:-60}

echo "Printer idle check script started with interval ${PRINTER_IDLE_CHECK_INTERVAL}s"

# Sleep for interval to allow time for CUPS to start
sleep $PRINTER_IDLE_CHECK_INTERVAL

# Check loop
while true; do
    if [[ -z "$PRINTER_IDLE_LOGLEVEL" || "INFO DEBUG TRACE" =~ $PRINTER_IDLE_LOGLEVEL ]]; then
        echo "Checking printer idle status..."
    fi
    /opt/power_scripts/printer_idle.py
    sleep $PRINTER_IDLE_CHECK_INTERVAL
done
