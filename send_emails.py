#!/usr/bin/env python3
"""Phase 3 — Gmail SMTP sender for pre-generated outreach emails.

Supports input from:
  - .csv files (standard CSV with headers)
  - .numbers files (Apple Numbers spreadsheets)
"""

import argparse
import csv
import logging
import os
import random
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = PROJECT_DIR / "phase3_email_Test.numbers"
SEND_LOG = PROJECT_DIR / "send_log.csv"

# Gmail SMTP config
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def load_credentials() -> tuple[str, str]:
    """Load Gmail credentials from environment variables."""
    address = os.getenv("GMAIL_ADDRESS", "")
    password = os.getenv("GMAIL_APP_PASSWORD", "")
    if not address or not password:
        log.error(
            "Missing credentials. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD environment variables.\n"
            "  export GMAIL_ADDRESS='you@gmail.com'\n"
            "  export GMAIL_APP_PASSWORD='xxxx xxxx xxxx xxxx'"
        )
        sys.exit(1)
    return address, password


def _read_numbers_file(filepath: Path) -> list[dict]:
    """Read an Apple Numbers file and return rows as list of dicts."""
    from numbers_parser import Document

    doc = Document(str(filepath))
    sheet = doc.sheets[0]
    table = sheet.tables[0]

    # First row is headers
    headers = []
    for col_idx in range(table.num_cols):
        cell = table.cell(0, col_idx)
        headers.append(str(cell.value).strip() if cell.value is not None else f"col_{col_idx}")

    rows = []
    for row_idx in range(1, table.num_rows):
        row_data = {}
        for col_idx, header in enumerate(headers):
            cell = table.cell(row_idx, col_idx)
            val = cell.value
            if val is None:
                row_data[header] = ""
            elif isinstance(val, float) and val == int(val):
                row_data[header] = str(int(val))
            else:
                row_data[header] = str(val).strip()
        rows.append(row_data)
    return rows


def _read_csv_file(filepath: Path) -> list[dict]:
    """Read a CSV file and return rows as list of dicts."""
    rows = []
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_emails(input_path: Path, max_send: int = 0) -> list[dict]:
    """Load email drafts from CSV or Numbers file."""
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)

    # Read based on file extension
    suffix = input_path.suffix.lower()
    if suffix == ".numbers":
        log.info("Reading Apple Numbers file: %s", input_path.name)
        all_rows = _read_numbers_file(input_path)
    elif suffix in (".csv", ".tsv"):
        all_rows = _read_csv_file(input_path)
    else:
        log.error("Unsupported file type: %s (use .csv or .numbers)", suffix)
        sys.exit(1)

    # Filter to valid, sendable rows
    rows = []
    for row in all_rows:
        addr = row.get("email_address", "").strip()
        subject = row.get("subject_line", "").strip()
        body = row.get("email_body", "").strip()
        status = row.get("status", "").strip()

        # Skip rows without valid email or that errored/skipped
        if not addr or "@" not in addr:
            continue
        if status and status not in ("completed",):
            continue
        if not subject or not body:
            continue

        rows.append(row)
        if max_send > 0 and len(rows) >= max_send:
            break

    return rows


def build_message(
    sender: str, recipient: str, subject: str, body: str, sender_name: str = ""
) -> MIMEMultipart:
    """Build a plain-text email message."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Reply-To"] = sender

    # Plain text body
    msg.attach(MIMEText(body, "plain", "utf-8"))

    return msg


def load_already_sent(log_path: Path) -> set[str]:
    """Load email addresses already sent from send log."""
    sent = set()
    if log_path.exists():
        with open(log_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == "sent":
                    sent.add(row.get("email_address", "").strip().lower())
    return sent


def append_log(
    log_path: Path, row: dict, status: str, error: str = "", timestamp: str = ""
):
    """Append a send result to the log CSV."""
    write_header = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        fields = [
            "timestamp", "prospect_id", "first_name", "last_name",
            "email_address", "subject_line", "status", "error",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "timestamp": timestamp or datetime.now().isoformat(),
            "prospect_id": row.get("prospect_id", ""),
            "first_name": row.get("first_name", ""),
            "last_name": row.get("last_name", ""),
            "email_address": row.get("email_address", ""),
            "subject_line": row.get("subject_line", ""),
            "status": status,
            "error": error,
        })


def send_emails(
    rows: list[dict],
    sender: str,
    password: str,
    sender_name: str,
    delay_range: tuple[int, int],
    dry_run: bool = False,
):
    """Connect to Gmail SMTP and send all emails with pacing."""
    already_sent = load_already_sent(SEND_LOG)
    pending = [r for r in rows if r["email_address"].strip().lower() not in already_sent]

    if not pending:
        log.info("All emails already sent (check %s). Nothing to do.", SEND_LOG)
        return

    skipped = len(rows) - len(pending)
    if skipped:
        log.info("Skipping %d already-sent emails.", skipped)

    log.info(
        "%s %d emails via %s (delay: %d-%ds between sends)",
        "DRY RUN previewing" if dry_run else "Sending",
        len(pending),
        sender,
        delay_range[0],
        delay_range[1],
    )

    if dry_run:
        for i, row in enumerate(pending, 1):
            name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
            log.info(
                "[DRY RUN %d/%d] To: %s (%s) | Subject: %s",
                i, len(pending), row["email_address"], name, row["subject_line"],
            )
        log.info("Dry run complete. No emails sent.")
        return

    # Connect to Gmail SMTP
    server = None
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender, password)
        log.info("Connected to Gmail SMTP.")
    except Exception as e:
        log.error("Failed to connect to Gmail SMTP: %s", e)
        sys.exit(1)

    sent_count = 0
    error_count = 0

    for i, row in enumerate(pending, 1):
        recipient = row["email_address"].strip()
        subject = row["subject_line"].strip()
        body = row["email_body"].strip()
        name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()

        try:
            msg = build_message(sender, recipient, subject, body, sender_name)
            server.sendmail(sender, recipient, msg.as_string())
            sent_count += 1
            append_log(SEND_LOG, row, "sent")
            log.info(
                "[%d/%d] Sent to %s (%s)", i, len(pending), recipient, name,
            )
        except smtplib.SMTPRecipientsRefused as e:
            error_count += 1
            err_msg = str(e)[:200]
            append_log(SEND_LOG, row, "failed", error=err_msg)
            log.warning("[%d/%d] Refused: %s - %s", i, len(pending), recipient, err_msg)
        except smtplib.SMTPException as e:
            error_count += 1
            err_msg = str(e)[:200]
            append_log(SEND_LOG, row, "failed", error=err_msg)
            log.warning("[%d/%d] SMTP error: %s - %s", i, len(pending), recipient, err_msg)
            # Reconnect on server errors
            try:
                server.quit()
            except Exception:
                pass
            try:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender, password)
                log.info("Reconnected to SMTP after error.")
            except Exception as reconnect_err:
                log.error("Failed to reconnect: %s. Aborting.", reconnect_err)
                break

        # Pace sends (skip delay after last email)
        if i < len(pending):
            delay = random.randint(delay_range[0], delay_range[1])
            log.info("  Waiting %ds before next send...", delay)
            time.sleep(delay)

    # Disconnect
    try:
        server.quit()
    except Exception:
        pass

    log.info("")
    log.info("=" * 50)
    log.info("SEND COMPLETE")
    log.info("=" * 50)
    log.info("  Sent:   %d", sent_count)
    log.info("  Failed: %d", error_count)
    log.info("  Log:    %s", SEND_LOG)
    log.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Send Phase 3 outreach emails via Gmail SMTP",
    )
    parser.add_argument(
        "--input", type=str, default=str(DEFAULT_INPUT),
        help="Input CSV with email drafts (default: phase3_email_drafts.csv)",
    )
    parser.add_argument(
        "--max", type=int, default=0,
        help="Max emails to send (0 = all)",
    )
    parser.add_argument(
        "--delay-min", type=int, default=30,
        help="Min seconds between sends (default: 30)",
    )
    parser.add_argument(
        "--delay-max", type=int, default=60,
        help="Max seconds between sends (default: 60)",
    )
    parser.add_argument(
        "--sender-name", type=str, default="The SYH Membership Team",
        help="Display name for sender (default: 'The SYH Membership Team')",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be sent without actually sending",
    )
    args = parser.parse_args()

    rows = load_emails(Path(args.input), max_send=args.max)

    if not rows:
        log.info("No valid emails to send from %s", args.input)
        sys.exit(0)

    log.info("Loaded %d email(s) from %s", len(rows), args.input)

    # Dry run doesn't need credentials
    if args.dry_run:
        sender = os.getenv("GMAIL_ADDRESS", "dry-run@example.com")
    else:
        sender = ""

    sender, password = (sender, "") if args.dry_run else load_credentials()

    send_emails(
        rows=rows,
        sender=sender,
        password=password,
        sender_name=args.sender_name,
        delay_range=(args.delay_min, args.delay_max),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
