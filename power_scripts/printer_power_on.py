#!/usr/bin/python3

import http.client
import json
import logging
import os
import socket
import sys
import time
from urllib.parse import urlparse

log_level = os.getenv("PRINTER_POWERON_LOGLEVEL", "INFO")
try:
    log_level = getattr(logging, log_level.upper())
except AttributeError:
    print(f"Invalid log level: {log_level} - Defaulting to INFO")
    log_level = logging.INFO

logging.basicConfig(level=log_level)
log = logging.getLogger("printer_webhook_monitor")


def send_webhook(webhook_url: str, printer_name: str):
    webhook_scheme = urlparse(webhook_url, "http").scheme
    webhook_host = urlparse(webhook_url).hostname
    webhook_path = urlparse(webhook_url).path

    if webhook_scheme == "https":
        conn = http.client.HTTPSConnection(webhook_host)
    else:
        conn = http.client.HTTPConnection(webhook_host)

    try:
        log.info("Triggering webhook...")
        conn.request(
            "POST",
            webhook_path,
            json.dumps({"power_on": printer_name}),
            {"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        log.debug("Webhook responded: %s %s", response.status, response.reason)
    except Exception as e:
        log.error("Error sending webhook: %s", e)
    finally:
        conn.close()


def wait_for_printer(
    printer_host: str, printer_name: str, port: int = 631, timeout: int = 60
):
    log.info("Waiting for %s to become available for printing...", printer_name)
    start_time = time.time()
    while time.time() - start_time < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            if sock.connect_ex((printer_host, port)) == 0:
                log.info("%s is online", printer_name)
                return True
        log.debug("Printer not available yet, retrying...")
        time.sleep(1)
    log.error(
        "Timeout reached: %s did not become available within %d seconds",
        printer_name,
        timeout,
    )
    return False


def main():
    webhook_url = os.getenv("PRINTER_POWERON_WEBHOOK_URL")
    printer_host = os.getenv("PRINTER_POWERON_HOST")
    printer_name = os.getenv("PRINTER_POWERON_NAME", "Printer")
    wait_timeout = int(os.getenv("PRINTER_POWERON_WAIT_TIMEOUT", 120))

    if not webhook_url:
        log.error("PRINTER_POWERON_WEBHOOK_URL environment variable is not set.")
        return

    if not printer_host:
        log.error("PRINTER_POWERON_HOST environment variable is not set.")
        return

    send_webhook(webhook_url, printer_name)
    printer_alive = wait_for_printer(printer_host, printer_name, timeout=wait_timeout)

    if not printer_alive:
        sys.exit(-1)


if __name__ == "__main__":
    main()
