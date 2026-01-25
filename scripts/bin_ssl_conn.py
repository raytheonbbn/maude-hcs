import json
import argparse
import sys
from math import floor
from datetime import datetime


def analyze_ssl_log(file_path, bin_size, offset):
    """
    Parses a log file, filters for specific SSL connections,
    and groups them into time bins relative to an offset.
    """

    # specific filter criteria
    TARGET_IP = "10.20.3.9"
    TARGET_PORT = 443
    TARGET_PROTO = "tcp"
    TARGET_SERVICE = "ssl"

    filtered_records = []

    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)

                    # Extract fields with safe defaults to avoid KeyErrors
                    r_ip = record.get("id.resp_h")
                    r_port = record.get("id.resp_p")
                    proto = record.get("proto")
                    service = record.get("service")
                    ts = record.get("ts")

                    # Apply Filters
                    if (r_ip == TARGET_IP and
                            r_port == TARGET_PORT and
                            proto == TARGET_PROTO and
                            service == TARGET_SERVICE and
                            ts is not None):
                        filtered_records.append(record)

                except json.JSONDecodeError:
                    print(f"Warning: Could not parse JSON on line {line_num}", file=sys.stderr)
                    continue

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

    # 1. Sort by timestamp
    if not filtered_records:
        print("No matching SSL connections found.")
        return

    filtered_records.sort(key=lambda x: x['ts'])

    # 2. Determine reference time (Earliest + Offset)
    earliest_ts = filtered_records[0]['ts']
    reference_time = earliest_ts + offset

    # 3. Bin the data
    # Dictionary to map bin_number -> count
    bins = {}

    # Initialize min/max bin tracking
    # We calculate the bin of the first record to initialize properly
    first_record_bin = floor((filtered_records[0]['ts'] - reference_time) / bin_size)
    min_bin = first_record_bin
    max_bin = first_record_bin

    for record in filtered_records:
        current_ts = record['ts']

        # Calculate time elapsed relative to the reference time
        elapsed = current_ts - reference_time

        # Determine bin number (can be negative if record is before offset)
        bin_num = floor(elapsed / bin_size)

        if bin_num > max_bin:
            max_bin = bin_num
        if bin_num < min_bin:
            min_bin = bin_num

        bins[bin_num] = bins.get(bin_num, 0) + 1

    # 4. Generate Table
    print(f"\nAnalysis Report for {file_path}")
    print(f"Filter: {TARGET_IP}:{TARGET_PORT} ({TARGET_PROTO}/{TARGET_SERVICE})")
    print(f"Bin Size: {bin_size} seconds")
    print(f"Offset: {offset} seconds (0s = Earliest Time + Offset)")
    print(f"Earliest Log Time: {datetime.fromtimestamp(earliest_ts)}")
    print(f"Reference Time (0s): {datetime.fromtimestamp(reference_time)}")
    print("-" * 55)
    print(f"{'Bin #':<10} | {'Rel. Time Range (s)':<25} | {'Count':<10}")
    print("-" * 55)

    # Loop from min_bin to max_bin to show full range
    total_connections = 0
    for i in range(min_bin, max_bin + 1):
        count = bins.get(i, 0)
        total_connections += count

        range_start = i * bin_size
        range_end = (i + 1) * bin_size
        range_str = f"{range_start} to {range_end}s"

        print(f"{i:<10} | {range_str:<25} | {count:<10}")

    print("-" * 55)
    print(f"{'Total':<38} | {total_connections:<10}")


if __name__ == "__main__":
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Analyze SSL connections in a log file.")
    parser.add_argument("filename", help="Path to the log file (e.g., conn.log)")
    parser.add_argument("--bin-size", type=int, default=10, help="Size of time bins in seconds (default: 10)")
    parser.add_argument("--offset", type=float, default=0.0,
                        help="Offset from earliest timestamp in seconds (default: 5.0)")

    args = parser.parse_args()

    analyze_ssl_log(args.filename, args.bin_size, args.offset)