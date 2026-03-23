#!/usr/bin/env python3
"""
count_by_10s.py

Counts lines that start with a Unix timestamp in 10‑second intervals.

Usage:
    python count_by_10s.py logfile.txt            # prints to stdout
    python count_by_10s.py logfile.txt -o out.txt  # writes to file

The script assumes that a line that *should* start with a timestamp
contains only whitespace followed by an integer (the epoch seconds).
If the first token cannot be converted to an int, the line is ignored.

Author:  ChatGPT
"""

import argparse
from collections import defaultdict
import os
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
# Utility functions
# --------------------------------------------------------------------------- #
class Bucketter:
  def __init__(self, initial_delay: float):
    self.initial_delay  = initial_delay
    self.bucket_start = 0
    self.bucket_index = -1
    self.file_start   = 0
    self.count_start_time = 0

  def _first_token_as_int(line: str) -> Optional[float]:
      """
      Return the integer value of the first whitespace‑separated token
      if it can be parsed as an int; otherwise, return None.
      """
      parts = line.strip().split(',', 1)  # split on any whitespace, at most once
      ts  = float(parts[0].split(':')[1])
      if not ts:
          return None
      try:
          return ts
      except ValueError:
          return None

  def _bucket_start(ts: float) -> float:
      """
      Return the start of the 10‑second interval that contains *ts*.
      Example:  1234567890 -> 1234567890  (already a multiple of 10)
               1234567895 -> 1234567890
      """
      return (ts // 10) * 10

  def _current_bucket(self, ts: float) -> int:
    if self.file_start == 0:
      self.file_start = ts
    if (self.bucket_start == 0) and (ts >= self.file_start + self.initial_delay):
      self.bucket_start  = ts
      self.bucket_index  = 0
      self.count_start_time = ts
    if self.bucket_start > 0 and ts > self.bucket_start + 10.:
      self.bucket_start  += 10.
      self.bucket_index  += 1

    return self.bucket_index


# --------------------------------------------------------------------------- #
# Main logic
# --------------------------------------------------------------------------- #

def count_10s_intervals(file_path: Path, args):
    """
    Scan *file_path* and return a dictionary mapping interval start
    to the number of lines whose first token is a timestamp falling
    into that interval.
    """
    initial_delay = args.delay_start
    counts = defaultdict(int)
    buckets= defaultdict(float)
    bucketter = Bucketter(initial_delay)
    bucket_index = 0
    old_bucket_index  = -1
    alert_count = 0
    alert_ts    = 0

    # Read the file line by line; this is memory‑efficient even for huge logs.
    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            ts = Bucketter._first_token_as_int(line)
            if ts is not None:
                bucket = Bucketter._bucket_start(ts)
                #counts[bucket] += 1
                bucket_index = bucketter._current_bucket(ts)
                counts[bucket_index] += 1
                if old_bucket_index != bucket_index:
                   buckets[bucket_index] = ts
                   old_bucket_index = bucket_index
                if bucket_index == -1:
                  continue
                alert_count += 1
                if alert_count == args.alert_query:
                  alert_ts = ts - bucketter.count_start_time
                  print(f"Found {args.alert_query} query at {alert_ts} ({ts}).")

    return (counts, buckets, alert_ts)


def moving_average(counts):
    counts_list = list(counts.values())
    i = 0
    averages_per_bin  = {}
    rate_per_bin      = {}
    while i + 6 < len(counts_list):
      sum_queries = sum(counts_list[i:i+6])
      averages_per_bin[i+6] = sum_queries 
      rate_per_bin[i+6] = sum_queries / 60.
      i += 1

    print(f"Moving sum per bin: {averages_per_bin}")
    print(f"Rate per bin: {rate_per_bin}qps")
    return averages_per_bin, rate_per_bin


# --------------------------------------------------------------------------- #
# CLI interface
# --------------------------------------------------------------------------- #

def main(args) -> None:
    subdirs = sorted(d for d in os.listdir(args.scenario)
                      if os.path.isdir(os.path.join(args.scenario, d)))
    print(f"Found subdirs {subdirs}.")

    if len(subdirs) <= 2:
        print("Not enough sub-directories to process.")
        return

    subdirs_to_process  = subdirs[1:-1]

    alert_ts_sum = 0
    experiment_count  = 0
    
    for subdir in subdirs_to_process:
      archive_path = os.path.join(args.scenario, subdir, "archive", "zeek", "logs", "dns.log")

      if args.verbose:
          print(f"[+] Counting timestamps in {archive_path} …")

      experiment_count += 1
      (counts, buckets, alert_ts) = count_10s_intervals(archive_path, args)
      total = sum(counts.values())
      moving_average(counts)
      alert_ts_sum += alert_ts

      # Sort by interval start for a chronological listing
      sorted_intervals = sorted(counts)

      output_lines = [f"{interval}\t{counts[interval]}" for interval in sorted_intervals]
      output_lines += [f"Total: {total}"]
      if args.verbose:
        output_lines += [f"{interval}\t{buckets[interval]}" for interval in sorted_intervals]

      if args.output:
          if args.verbose:
              print(f"[+] Writing results to {args.output}")
          with args.output.open("w", encoding="utf-8") as out:
              out.write("\n".join(output_lines))
      else:
          print("\n".join(output_lines))

    print(f"Average {args.alert_query}th query timestamp: {alert_ts_sum / experiment_count}s.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Count lines starting with a Unix timestamp in 10‑second intervals."
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default="target_folder",
        help="Root folder containing subdirectories (default: target_folder)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Optional output file.  If omitted, the result is printed to stdout.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show progress information (useful for very large files).",
    )
    parser.add_argument(
        "-q", "--alert_query",
        type=int,
        default=101,
        help="The number of the alert query for which to find the time."
    )
    parser.add_argument(
        "-d", "--delay_start",
        type=float,
        default=5.,
        help="Delay after which Zeek starts counting."
    )

    args = parser.parse_args()

    main(args)


