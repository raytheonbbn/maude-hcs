import argparse
import json
import os
import glob
import re
import csv
import math
import statistics

# The specific keys we want to analyze
INTERESTING_KEYS = [
    "latency",
    "goodput_bytes_per_second",
    "C2_time_elapsed",
    "C2_file_count",
    "C8_time_elapsed",
    "C8_file_count",
    "MA1_time_elapsed",
    "MA1_file_count"
]

def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse metric JSON files and generate summary statistics."
    )
    parser.add_argument(
        "directory", 
        help="Path to the directory containing the JSON scenario files."
    )
    parser.add_argument(
        "--output", 
        default="metrics_summary.csv", 
        help="Path for the output CSV file (default: metrics_summary.csv)."
    )
    return parser.parse_args()

def extract_scenario_id(filename):
    """
    Attempts to extract a scenario ID from the filename.
    Assumes patterns like 'scenario_X.json' or 'listed_metrics_scenario_X.json'.
    Returns the filename stem if no pattern matches.
    """
    # Try to find 'scenario_' followed by some characters until a non-word char or dot
    match = re.search(r'scenario_([a-zA-Z0-9]+)', filename)
    if match:
        return match.group(1)
    
    # Fallback: just return the filename without extension
    return os.path.splitext(filename)[0]

def calculate_stats(values):
    """
    Calculates Mean, StdDev, Min, and Max for a list of numbers.
    """
    if not values or len(values) == 0:
        return None

    try:
        # Convert to float to ensure math operations work
        cleaned_values = [float(v) for v in values if v is not None]
        
        if not cleaned_values:
            return None

        stats_dict = {
            "mean": statistics.mean(cleaned_values),
            "min": min(cleaned_values),
            "max": max(cleaned_values),
            "count": len(cleaned_values)
        }

        # Std dev requires at least two data points
        if len(cleaned_values) > 1:
            stats_dict["std"] = statistics.stdev(cleaned_values)
        else:
            stats_dict["std"] = 0.0
            
        return stats_dict

    except (ValueError, TypeError) as e:
        print(f"  Warning: Error calculating stats (possible non-numeric data): {e}")
        return None

def process_directory(directory_path):
    results = []
    
    # Look for all .json files in the directory
    search_path = os.path.join(directory_path, "*.json")
    files = glob.glob(search_path)
    
    if not files:
        print(f"No JSON files found in {directory_path}")
        return results

    print(f"Found {len(files)} files. Processing...")

    for file_path in files:
        filename = os.path.basename(file_path)
        scenario_id = extract_scenario_id(filename)
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            for key in INTERESTING_KEYS:
                if key in data:
                    stats = calculate_stats(data[key])
                    if stats:
                        results.append({
                            "scenario_id": scenario_id,
                            "filename": filename,
                            "metric": key,
                            "mean": stats["mean"],
                            "std": stats["std"],
                            "min": stats["min"],
                            "max": stats["max"],
                            "sample_count": stats["count"]
                        })
                # If key is missing, we simply skip it (or you could log a warning)
                
        except json.JSONDecodeError:
            print(f"Error: Could not parse JSON in file: {filename}")
        except Exception as e:
            print(f"Error processing file {filename}: {e}")
            
    return results

def main():
    args = parse_args()
    
    if not os.path.isdir(args.directory):
        print(f"Error: Directory '{args.directory}' does not exist.")
        return

    results = process_directory(args.directory)
    
    if not results:
        print("No metrics extracted.")
        return

    # Sort results by scenario_id, then metric for cleaner output
    # We try to convert scenario_id to int for sorting if possible, otherwise string sort
    try:
        results.sort(key=lambda x: (int(x['scenario_id']) if x['scenario_id'].isdigit() else x['scenario_id'], x['metric']))
    except:
        results.sort(key=lambda x: (x['scenario_id'], x['metric']))

    # Print to Console
    print("\n" + "="*85)
    print(f"{'Scenario':<10} | {'Metric':<25} | {'Mean':<10} | {'Std Dev':<10} | {'Min':<10} | {'Max':<10}")
    print("-" * 85)
    for row in results:
        print(f"{row['scenario_id']:<10} | {row['metric']:<25} | {row['mean']:<10.2f} | {row['std']:<10.2f} | {row['min']:<10.2f} | {row['max']:<10.2f}")
    print("="*85 + "\n")

    # Write to CSV
    try:
        with open(args.output, 'w', newline='') as csvfile:
            fieldnames = ['scenario_id', 'filename', 'metric', 'mean', 'std', 'min', 'max', 'sample_count']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for row in results:
                writer.writerow(row)
        print(f"Successfully wrote summary to '{args.output}'")
    except IOError as e:
        print(f"Error writing to CSV: {e}")

if __name__ == "__main__":
    main()
