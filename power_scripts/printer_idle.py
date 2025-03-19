#!/usr/bin/python3

import http.client
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import cups

log_level = os.getenv("PRINTER_IDLE_LOGLEVEL", "INFO")
try:
    log_level = getattr(logging, log_level.upper())
except AttributeError:
    print(f"Invalid log level: {log_level} - Defaulting to INFO")
    log_level = logging.INFO

logging.basicConfig(level=log_level)
log = logging.getLogger("printer_idle")


class PrinterIdle:
    def __init__(self, printer_name: str, idle_threshold: int):
        self.conn = cups.Connection()
        self.printer_name = printer_name
        self.idle_threshold = idle_threshold

        if printer_name == "":
            printers = self.get_printers().keys()
            if len(printers) == 0:
                raise ValueError("Printer name not defined and no printers found.")
            if len(printers) > 1:
                raise ValueError(
                    f"Printer name not defined and multiple printers were found: {list(printers)}"
                )
            self.printer_name = list(printers)[0]

    def get_printers(self) -> dict[str, Any]:
        printers: dict[str, Any] = self.conn.getPrinters()
        return printers

    def check_printer(self):
        printers = self.get_printers()
        if self.printer_name not in printers:
            raise ValueError(f"Printer {self.printer_name} not found")
        return True

    def get_last_job_time(self):
        jobs: dict[int, Any] = self.conn.getJobs(which_jobs="completed")
        for jid, _ in jobs.items():
            job_attrs = self.conn.getJobAttributes(jid)

            printer_uri: str = job_attrs.get("job-printer-uri")
            job_time: str = job_attrs.get("time-at-completed")

            if printer_uri.endswith(self.printer_name) and job_time is not None:
                return datetime.fromtimestamp(job_time)
        return None

    def check_idle(self):
        if self.last_job_time is None:
            log.debug(
                "Idle time undefined for printer %s. Printer must be idle.",
                self.printer_name,
            )
            return True
        idle_time = datetime.now() - self.last_job_time
        return idle_time > timedelta(seconds=self.idle_threshold)

    @property
    def last_job_time(self):
        return self.get_last_job_time()

    @property
    def is_idle(self):
        return self.check_idle()


def send_webhook(
    webhook_url: str,
    printer_name: str,
    is_idle: bool,
    idle_time: int,
    last_job_time: datetime | None,
):
    parsed_url = urlparse(webhook_url)
    webhook_scheme = parsed_url.scheme
    webhook_host = parsed_url.hostname
    webhook_port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)

    if webhook_scheme == "https":
        conn = http.client.HTTPSConnection(webhook_host, webhook_port)
    else:
        conn = http.client.HTTPConnection(webhook_host, webhook_port)

    last_job_timestamp = 0 if last_job_time is None else int(last_job_time.timestamp())
    webhook_body = json.dumps(
        {
            "printer": printer_name,
            "idle": is_idle,
            "idle_time": idle_time,
            "last_job_time": last_job_timestamp,
        }
    )
    log.debug("Sending info to webhook: %s", webhook_body)
    try:
        conn.request(
            "POST",
            webhook_url,
            webhook_body,
            {"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        log.debug("Webhook responded %s %s", response.status, response.reason)
    except Exception as e:
        log.error("Error sending webhook: %s", e)
        response = None
    finally:
        conn.close()
    return response


def main():
    # Comma-seperated list of printer names as set in CUPS. Only required if multiple printers are available.
    printers = os.getenv("PRINTER_IDLE_PRINTERS", "")
    # Seconds since last job to consider printer idle.
    idle_threshold = os.getenv("PRINTER_IDLE_THRESHOLD", 3600)
    # Webhook URL to send idle printer information to.
    webhook_url = os.getenv("PRINTER_IDLE_WEBHOOK_URL")

    printers = printers.split(",")

    for printer_name in printers:
        try:
            printer = PrinterIdle(printer_name, int(idle_threshold))
        except ValueError as exc:
            log.error("An error occured setting up the idle check: %s", exc)
            continue
        except RuntimeError:
            log.warning("Failed to connect to CUPS. The service may not be running.")
            continue

        try:
            printer.check_printer()
        except ValueError as exc:
            log.error("Skipping printer: %s", exc)
            continue

        if not printer_name:
            printer_name = printer.printer_name

        state_path = Path(f"/run/printer_idle_{printer_name.lower()}.state")
        last_state = state_path.read_text().strip() if state_path.exists() else None
        state_path.write_text("idle" if printer.is_idle else "active")

        idle_time = 0
        last_job_time = printer.last_job_time
        if last_job_time is None:
            idle_time_human = "Unknown (no jobs found, must be idle)"
        else:
            idle_time = datetime.now() - last_job_time
            idle_time_human = f"{idle_time.days}d {idle_time.seconds // 3600}h {idle_time.seconds % 3600 // 60}m"

        if printer.is_idle:
            if last_state != "idle":
                log.info(f"Printer {printer_name} has changed to idle state.")
            log.debug(f"Printer {printer_name} has been idle for {idle_time_human}.")
        else:
            idle_time = 0
            if last_state != "active":
                log.info(f"Printer {printer_name} has changed to active state.")
            log.debug(
                f"Printer {printer_name} is not idle. Last job completed {idle_time_human} ago."
            )

        if webhook_url is None:
            log.warning("Skipping webhook - PRINTER_IDLE_WEBHOOK_URL unset.")
            return

        idle_seconds = (
            int(idle_time.total_seconds()) if isinstance(idle_time, timedelta) else 0
        )
        log.debug("Sending webhook for idle printer")
        webhook_response = send_webhook(
            webhook_url,
            printer_name,
            printer.is_idle,
            idle_seconds,
            last_job_time,
        )
        if webhook_response is None:
            log.error("Webhook request failed.")
            return
        elif webhook_response.status != 200:
            log.error("Webhook responded with status %s", webhook_response.status)
            return
        log.debug("Webhook sent successfully")


if __name__ == "__main__":
    main()
