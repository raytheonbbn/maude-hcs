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
import json
import os
import matplotlib.pyplot as plt
import numpy as np
import re
import subprocess
from datetime import datetime, timedelta
from plot_loss_model import parse_data
from plot_loss_model import data_series_1, data_series_2, data_series_3

# Regular expression that matches a line that starts with
# a date in the format YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2}.\d{3})?)")
DATE_TGEN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{6})")

# Helper that converts the date string captured by DATE_RE
# into a datetime object.  If the time part is missing, midnight is assumed.
def parse_date(date_str: str) -> datetime:
    """Parse a date string of the form YYYY-MM-DD or YYYY-MM-DD HH:MM:SS."""
    date_str = date_str.replace('T', ' ')
    if " " in date_str:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")
    else:
        return datetime.strptime(date_str, "%Y-%m-%d")

def parse_file_size(line: str) -> int:
    return int(line.replace('}', '').split(" ")[-1])

def parse_num_actions(line: str) -> int:
  return int(line.split(" ")[-4])

def parse_num_downloads(line: str) -> int:
  return int(line.split(" ")[-7])

def parse_download_size(line: str) -> int:
  return int(line.replace(',', '').split()[-5])

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

def process_fetches(path: str, sizes_B, durations_s):
  try:
    with open(path, 'r') as f:
      current_state = "start"
      previous_event_time = 0
      for line in f:
        m = DATE_RE.match(line)
        if not m:
          continue

        try:
          ts = parse_date(m.group(1))
        except ValueError:
          continue
      
        line = line.lower()
        if "calling downlaod" in line:
          current_state = "fetching"
          previous_event_time = ts
        if "downloaded image" in line:
          download_delta = ts - previous_event_time
          download_duration_s = download_delta.seconds + download_delta.microseconds / 1e6
          download_size = parse_file_size(line)
          previous_event_time = ts
          durations_s.append(download_duration_s)
          sizes_B.append(download_size)
  except FileNotFoundError:
    return None

  return sizes_B, durations_s

def process_posts(path: str, sizes_B, durations_s):

  #subprocess.run(['dos2unix', path])
  try:
    with open(path, 'r') as f:
      current_state = "start"
      previous_event_time = 0
      upload_size_B = 0
      for line in f:
        m = DATE_RE.match(line)
        if not m:
          if "content-length:" in line and current_state != "sized":
            upload_size_B = parse_file_size(line)
            current_state = "sized"
          continue

        try:
          ts = parse_date(m.group(1))
        except ValueError:
          printf("parse error")
          continue
      
        line = line.lower()
        if "action has" in line:
          current_state = "posting"
          previous_event_time = ts
        if "uploaded and fine" in line and current_state == "sized":
          current_state = "uploaded"
          upload_delta = ts - previous_event_time
          upload_duration_s = upload_delta.seconds + upload_delta.microseconds / 1e6
          previous_event_time = ts
          durations_s.append(upload_duration_s)
          sizes_B.append(upload_size_B)
          upload_size_B = 0
  except FileNotFoundError:
    return None

  return sizes_B, durations_s


def process_tgen_fetches(file_path, sizes_B, durations_s):
  previous_event_time = 0
  try:
    with open(file_path, 'r') as f:
      for line in f:
        m = DATE_TGEN_RE.match(line)
        if not m:
          continue

        try:
          ts = parse_date(m.group(1))
        except ValueError:
          print(f"Parse error {m}.")
          continue

        if "Downloading" in line:
          num_downloads = parse_num_downloads(line)
          previous_event_time = ts

        if "Downloaded" in line:
          download_delta = ts - previous_event_time
          download_duration_s = download_delta.seconds + download_delta.microseconds / 1e6
          previous_event_time = ts
          download_size_B = parse_download_size(line)
          sizes_B.append(download_size_B)
          durations_s.append(download_duration_s)

  except FileNotFoundError:
    return None, None

  return sizes_B, durations_s

def process_tgen_posts(file_path, sizes_B, durations_s):
  previous_event_time = 0
  try:
    with open(file_path, 'r') as f:
      for line in f:
        m = DATE_TGEN_RE.match(line)
        if not m:
          continue

        try:
          ts = parse_date(m.group(1))
        except ValueError:
          print(f"Parse error {m}.")
          continue
      
        if "Starting request" in line:
          previous_event_time = ts

        if "media media_post FILE_INFO" in line or "monitor media_post STATS" in line:
          upload_delta = ts - previous_event_time
          upload_duration_s = upload_delta.seconds + upload_delta.microseconds / 1e6
          previous_event_time = ts
          upload_size_B = parse_file_size(line)
          sizes_B.append(upload_size_B)
          durations_s.append(upload_duration_s)

  except FileNotFoundError:
    return None, None

  return sizes_B, durations_s


def process_tgen_resolves(file_path, resolve_durations_s):
  with open(file_path, 'r') as f:
    for line in f:
      m = DATE_RE.match(line)
      if not m:
        continue

      if "STATS=" in line and "resolve_a" in line:
        json_str = line.split("STATS=")[1]
        data = json.loads(json_str)
        num_resolves = data["num_to_resolve"] if "num_to_resolve" in data else 1
        i = num_resolves
        while i > 0:
          resolve_durations_s.append(data["elapsed_time"] / num_resolves)
          i -= 1

  return resolve_durations_s



def process_tcp(target):
  if "noloss" in target:
    return parse_data(data_series_3)
  else:
    return parse_data(data_series_1)


def analyze_raceboat(target, subdirs):
    latencies = []
    goodputs  = []
    total_payload_bytes = 0

    fetch_sizes_B = []
    fetch_durations_s = []
    post_sizes_B = []
    post_durations_s  = []
    path_preamble = ""
    for sub in subdirs:
        nonarchive_path = os.path.join(target, sub, "app_client.log")
        if os.path.exists(nonarchive_path):
          archive_path = nonarchive_path
        else:
          path_preamble = "archive/"
        archive_path = os.path.join(target, sub, path_preamble + "app_client.log")
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
        archive_path = os.path.join(target, sub, path_preamble + "raceboat_server.log")
        process_fetches(archive_path, fetch_sizes_B, fetch_durations_s)
        archive_path = os.path.join(target, sub, path_preamble + "raceboat_client.log")
        process_posts(archive_path, post_sizes_B, post_durations_s)
    print(f"Average latency = {sum(latencies) / len(latencies)}s.")
    print(f"Total payload size = {total_payload_bytes}B.")
    print(f"Average goodput = {sum(goodputs) / len(goodputs)}bps.")
    throughputs = [a / b for a,b in zip(fetch_sizes_B, fetch_durations_s)]
    print(f"Fetch throughput = {8 * sum(throughputs) / len(throughputs)}bps")
    throughputs = [a / b for a,b in zip(post_sizes_B, post_durations_s)]
    print(f"Post throughput = {8 * sum(throughputs) / len(throughputs)}bps")
    print(f"Average fetch = {sum(fetch_durations_s) / len(fetch_durations_s):.3f}s")

    return fetch_sizes_B, fetch_durations_s, post_sizes_B, post_durations_s


def plot_transfers(target, fetch_sizes_B, fetch_durations_s, post_sizes_B, post_durations_s):
    sizes_B, means_s, mins_s, maxs_s = process_tcp(target)
    if "noloss" in target:
      figure_offset = 10
    else:
      figure_offset = 0

    size_bins = np.arange(0, 300000, 15000)
    duration_bins = np.arange(0., 20, 1)
    fetch_pairs = zip(fetch_sizes_B, fetch_durations_s)
    sorted_fetch_pairs = sorted(fetch_pairs)
    sorted_fetch_sizes_B, sorted_fetch_durations_s = zip(*sorted_fetch_pairs)
    sorted_fetch_sizes_B  = list(sorted_fetch_sizes_B)
    sorted_fetch_durations_s  = list(sorted_fetch_durations_s)
    plt.figure(1 + figure_offset)
    plt.scatter(sorted_fetch_sizes_B, sorted_fetch_durations_s)
#    plt.scatter(sizes_B, means_s)
#    plt.legend([target, "TCP benchmark"])
    plt.title(f"Fetch duration vs fetch size ({target})")
    plt.xlabel("Fetch Size (B)")
    plt.ylabel("Fetch Duration (s)")

    plt.figure(2 + figure_offset)
    plt.hist(sorted_fetch_durations_s, duration_bins)
    plt.title(f"Fetch distribution ({target})")
    plt.xlabel("Fetch Duration (s)")

    post_pairs = zip(post_sizes_B, post_durations_s)
    sorted_post_pairs = sorted(post_pairs)
    sorted_post_sizes_B, sorted_post_durations_s = zip(*sorted_post_pairs)
    sorted_post_sizes_B  = list(sorted_post_sizes_B)
    sorted_post_durations_s  = list(sorted_post_durations_s)
    plt.figure(3 + figure_offset)
    plt.scatter(sorted_post_sizes_B, sorted_post_durations_s)
#    plt.scatter(sizes_B, means_s)
#    plt.legend([target, "TCP benchmark"])
    plt.title(f"Post duration vs post size ({target})")
    plt.xlabel("Post Size (B)")
    plt.ylabel("Post Duration (s)")

    plt.figure(4 + figure_offset)
    plt.hist(sorted_post_durations_s, duration_bins)
    plt.title(f"Post latency distribution ({target})")
    plt.xlabel("Post Duration (s)")

    plt.figure(5 + figure_offset)
    plt.hist(sorted_post_sizes_B, size_bins)
    plt.title(f"Post size distribution ({target})")
    plt.xlabel("Post Size (B)")
    plt.show() 


def analyze_tgen(target, subdirs):
  download_sizes_B = []
  download_durations_s = []
  upload_sizes_B = []
  upload_durations_s = []
  for sub in subdirs:
    nonarchive_dir = os.path.join(target, sub, "tgen_logs")
    if os.path.exists(nonarchive_dir):
      tgen_dir = nonarchive_dir
    else:
      tgen_dir = os.path.join(target, sub, "archive", "tgen_logs")
    mastodon_subdirs  = sorted(
        d for d in os.listdir(tgen_dir)
        if os.path.isdir(os.path.join(tgen_dir, d)) and "mastodon" in d
    )
    print(f"Found tgen subdirs {mastodon_subdirs}")

    for mastodon_dir in mastodon_subdirs:
      mastodon_dir = os.path.join(tgen_dir, mastodon_dir, "logs")
      user_files = sorted(
        f for f in os.listdir(mastodon_dir)
        if os.path.isfile(os.path.join(mastodon_dir, f)) and "user" in f
      )

      for user_file in user_files:
        file_path = os.path.join(mastodon_dir, user_file)
        print(f"Processing {file_path}...")
        download_sizes_B, download_durations_s = process_tgen_fetches(file_path, download_sizes_B, download_durations_s)
        upload_sizes_B, upload_durations_s = process_tgen_posts(file_path, upload_sizes_B, upload_durations_s)
  throughputs = [a / b for a,b in zip(download_sizes_B, download_durations_s)]
  print(f"Fetch Throughput = {8 * sum(throughputs) / len(throughputs)}bps")
  throughputs = [a / b for a,b in zip(upload_sizes_B, upload_durations_s)]
  print(f"Post Throughput = {8 * sum(throughputs) / len(throughputs)}bps")

  return download_sizes_B, download_durations_s, upload_sizes_B, upload_durations_s


def analyze_dns_tgen(target, subdirs):
  resolve_durations_s = []
  for sub in subdirs:
    nonarchive_dir = os.path.join(target, sub, "tgen_logs")
    if os.path.exists(nonarchive_dir):
      tgen_dir = nonarchive_dir
    else:
      tgen_dir = os.path.join(target, sub, "archive", "tgen_logs")
    dns_subdirs  = sorted(
        d for d in os.listdir(tgen_dir)
        if os.path.isdir(os.path.join(tgen_dir, d)) and "dns" in d
    )
    print(f"Found tgen subdirs {dns_subdirs}")

    for dns_dir in dns_subdirs:
      dns_dir = os.path.join(tgen_dir, dns_dir, "logs")
      user_files = sorted(
        f for f in os.listdir(dns_dir)
        if os.path.isfile(os.path.join(dns_dir, f)) and "user" in f
      )

    for user_file in user_files:
      file_path = os.path.join(dns_dir, user_file)
      print(f"Processing {file_path}...")
      resolve_durations_s = process_tgen_resolves(file_path, resolve_durations_s)

  print(f"resolves {resolve_durations_s}")
  print(f"DNS resolves = {sum(resolve_durations_s) / len(resolve_durations_s):.6}s")
     

def main(args):
    target = args.scenario
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

    if args.mastodon:
      if args.raceboat:
        fetch_sizes_B, fetch_durations_s, post_sizes_B, post_durations_s = analyze_raceboat(target, to_process)
        plot_transfers(target+"_rb", fetch_sizes_B, fetch_durations_s, post_sizes_B, post_durations_s)

      if args.tgen:
        fetch_sizes_B, fetch_durations_s, post_sizes_B, post_durations_s = analyze_tgen(target, to_process)
        plot_transfers(target+"_tgen", fetch_sizes_B, fetch_durations_s, post_sizes_B, post_durations_s)

    if args.dns_resolve:
        analyze_dns_tgen(target, to_process)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute time differences in archive.txt files.")
    parser.add_argument(
        "scenario",
        nargs = "?",
        default = "target_folder",
        help = "Root folder containing subdirectories (default: target_folder)",
    )
    parser.add_argument(
        "-m", "--mastodon",
        action = "store_true",
        default = False,
        help = "Grab mastodon fetch and post latencies"
        )
    parser.add_argument(
        "-d", "--dns_resolve",
        action = "store_true",
        default = False,
        help = "Grab dns resolve latencies"
        )
    parser.add_argument(
        "-r", "--raceboat",
        action = "store_true",
        default = False,
        help = "Grab raceboat latencies"
        )
    parser.add_argument(
        "-t", "--tgen",
        action = "store_true",
        default = False,
        help = "Grab tgen latencies"
        )
    args = parser.parse_args()
    main(args)

