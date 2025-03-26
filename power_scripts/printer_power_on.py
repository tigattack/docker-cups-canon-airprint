#!/usr/bin/python3
# https://github.com/tigattack/docker-cups-canon-airprint
# https://gist.github.com/tigattack/3d54b842d6c842b6fa40618ff6279a1a

import http.client
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

WEBHOOK_URL_SECRETS_FILE = Path("/run/secrets/tea4cups-poweron-webhook-url")
PRINTER_HOST_SECRETS_FILE = Path("/run/secrets/tea4cups-poweron-host")

log_level = os.getenv("PRINTER_POWERON_LOGLEVEL", "INFO")
try:
    log_level = getattr(logging, log_level.upper())
except AttributeError:
    print(f"Invalid log level: {log_level} - Defaulting to INFO")
    log_level = logging.INFO

logging.basicConfig(level=log_level)
log = logging.getLogger("printer_webhook_monitor")


def send_webhook(webhook_url: str, printer_name: str):
    parsed_url = urlparse(webhook_url)
    webhook_scheme = parsed_url.scheme
    webhook_host = parsed_url.hostname
    webhook_port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)

    webhook_path = parsed_url.path

    if webhook_scheme == "https":
        conn = http.client.HTTPSConnection(webhook_host, webhook_port)
    else:
        conn = http.client.HTTPConnection(webhook_host, webhook_port)

    try:
        log.info("Triggering webhook...")
        conn.request(
            "POST",
            webhook_path,
            json.dumps(
                {
                    "power_on": printer_name,
                    "source": "cups",
                }
            ),
            {"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        log.debug("Webhook responded: %s %s", response.status, response.reason)
    except Exception as e:
        log.error("Error sending webhook: %s", e)
    finally:
        conn.close()


def is_printer_available(printer_host: str, port: int = 631) -> bool:
    try:
        with socket.create_connection((printer_host, port), timeout=5):
            return True
    except (socket.timeout, ConnectionRefusedError):
        return False


def wait_for_printer(
    printer_host: str, printer_name: str, port: int = 631, timeout: int = 60
):
    log.info("Waiting for %s to become available for printing...", printer_name)
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_printer_available(printer_host, port):
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


def get_printer_host():
    """
    Attempt to read & parse the printer URI from the tea4cups environment.
    If that fails, read the printer host from the secrets file.
    """
    printer_uri = os.getenv("DEVICE_URI")
    if not printer_uri:
        log.warning("Failed to discover printer URI from tea4cups environment.")
        return None

    printer_host = urlparse(printer_uri).hostname
    if printer_host:
        return printer_host
    log.warning(
        "Failed to parse hostname from printer URI: %s. Attempting to read from environment via secrets file",
        printer_uri,
    )

    try:
        printer_host = PRINTER_HOST_SECRETS_FILE.read_text().strip()
    except FileNotFoundError:
        log.error("Secrets file /run/secrets/tea4cups-poweron-host not found.")
        return None

    if not printer_host:
        log.error("The printer host secrets file seems to be empty.")
        return None
    if printer_host == "undef":
        log.error("PRINTER_POWERON_HOST environment variable is not set.")
        return None

    return printer_host


def main():
    printer_name = os.getenv("TEAPRINTERNAME")
    wait_timeout = int(os.getenv("PRINTER_POWERON_WAIT_TIMEOUT", 120))

    try:
        webhook_url = WEBHOOK_URL_SECRETS_FILE.read_text().strip()
        if not webhook_url:
            log.error("The webhook URL secrets file seems to be empty.")
            sys.exit(-1)
        if webhook_url == "undef":
            log.error("PRINTER_POWERON_WEBHOOK_URL environment variable is not set.")
            sys.exit(-1)
    except FileNotFoundError:
        log.error("Secrets file /run/secrets/tea4cups-poweron-webhook-url not found.")
        sys.exit(-1)

    if not printer_name:
        log.error("Failed to get printer name from tea4cups environment.")
        sys.exit(-1)

    printer_uri = get_printer_host()
    if not printer_uri:
        log.error("Failed to get printer host.")
        sys.exit(-1)

    if is_printer_available(printer_uri):
        log.info("Printer %s is already online", printer_name)
        return

    send_webhook(webhook_url, printer_name)
    printer_available = wait_for_printer(
        printer_uri, printer_name, timeout=wait_timeout
    )

    if not printer_available:
        sys.exit(-1)


if __name__ == "__main__":
    main()
