#!/usr/bin/env python3
"""
Script: compute_time_diff.py

Traverse `target_folder`, skip its first and last sub‑directories,
and for every remaining sub‑directory:

  • Open the file `archive.txt`.
  • Parse lines that begin with a date.
  • Find the last "got file" timestamp and the first "sending file" timestamp.
  • Print the difference (got - sending).

Assumptions
------------
* Sub‑directories are sorted alphabetically.
* The date at the start of each relevant line is either
      YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
* Lines containing the two markers always have a timestamp at the
  beginning of the line.
"""

import argparse
import os
import re
import subprocess
from datetime import datetime, timedelta

# Regular expression that matches a line that starts with
# a date in the format YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?)")

# Helper that converts the date string captured by DATE_RE
# into a datetime object.  If the time part is missing, midnight is assumed.
def parse_date(date_str: str) -> datetime:
    """Parse a date string of the form YYYY-MM-DD or YYYY-MM-DD HH:MM:SS."""
    if " " in date_str:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    else:
        return datetime.strptime(date_str, "%Y-%m-%d")

def parse_file_size(line: str) -> int:
    return int(line.split(" ")[-1])

def process_archive(path: str):
    """
    Read `archive.txt` at `path`, find the timestamps of interest,
    and return the time difference (got - sending).

    If the file is missing or the required markers are not found,
    None is returned.
    """
    got_time: datetime | None = None
    sending_time: datetime | None = None
    total_payload_bytes = 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                m = DATE_RE.match(line)
                if not m:
                    continue  # line does not start with a date

                try:
                    ts = parse_date(m.group(1))
                except ValueError:
                    # In case the date format is different – skip this line
                    continue

                lower = line.lower()
                if "got file" in lower:
                    got_time = ts          # keep the last occurrence
                if "sending file" in lower and sending_time is None:
                    sending_time = ts     # keep the first occurrence
                if "file length: " in lower:
                    total_payload_bytes += parse_file_size(lower)

    except FileNotFoundError:
        return None

    if got_time is None or sending_time is None:
        return None, total_payload_bytes

    return got_time - sending_time, total_payload_bytes

def main(target: str):
    # 1. Find all sub‑directories inside target
    subdirs = sorted(
        d for d in os.listdir(target)
        if os.path.isdir(os.path.join(target, d))
    )
    print(f"Found subdirs {subdirs}.")

    # 2. Skip the first and last one (if there are at least 3)
    if len(subdirs) <= 2:
        print("Not enough sub‑directories to process.")
        return

    to_process = subdirs[1:-1]
    latencies = []
    goodputs  = []
    total_payload_bytes = 0

    for sub in to_process:
        archive_path = os.path.join(target, sub, "archive/app_client.log")
        if not os.path.exists(archive_path):
           print(f"Target: {os.path.join(target, sub)}")
           subprocess.run(['unzip', os.path.join(target, sub,  "*.zip"), "-d", os.path.join(target, sub)])
        print(f"Processing {archive_path}...")
        diff, payload_size_bytes = process_archive(archive_path)
        if diff is None:
            print(f"{sub:30s} → Could not compute a valid difference "
                  "(missing markers or file).")
        else:
            seconds = diff.total_seconds()
            print(f"{sub:30s} → Δ = {diff} ({seconds:.0f} seconds)")
            latencies.append(seconds)
            goodputs.append(payload_size_bytes * 8 / seconds)
            total_payload_bytes += payload_size_bytes
    print(f"Average latency = {sum(latencies) / len(latencies)}s.")
    print(f"Total payload size = {total_payload_bytes}B.")
    print(f"Average goodput = {sum(goodputs) / len(goodputs)}bps.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute time differences in archive.txt files.")
    parser.add_argument(
        "scenario",
        nargs="?",
        default="target_folder",
        help="Root folder containing subdirectories (default: target_folder)",
    )
    args = parser.parse_args()
    main(args.scenario)

