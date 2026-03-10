import os
import json
import argparse
import re
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Mapping of TNE metric keys to SMC metric keys
MAPPING = {
    "latency": "latency",
    "goodput_bytes_per_second": "goodput",
    "C1_time_elapsed": "OpDurationC1",
    "C1_file_count": "ExfilFilesC1",
    "C2_time_elapsed": "OpDurationC2",
    "C2_file_count": "ExfilFilesC2",
    "C3_time_elapsed": "OpDurationC3",
    "C3_file_count": "ExfilFilesC3",
    "C4_time_elapsed": "OpDurationC4",
    "C4_file_count": "ExfilFilesC4",
    "C5_time_elapsed": "OpDurationC5",
    "C5_file_count": "ExfilFilesC5",
    "C6_time_elapsed": "OpDurationC6",
    "C6_file_count": "ExfilFilesC6",
    "C7_time_elapsed": "OpDurationC7",
    "C7_file_count": "ExfilFilesC7",
    "C8_time_elapsed": "OpDurationC8",
    "C8_file_count": "ExfilFilesC8",
    "C9_time_elapsed": "OpDurationC9",
    "C9_file_count": "ExfilFilesC9",
    "C10_time_elapsed": "OpDurationC10",
    "C10_file_count": "ExfilFilesC10",
    "MA1_time_elapsed": "OpDurationMA1",
    "MA1_file_count": "ExfilFilesMA1",
    "MA2_time_elapsed": "OpDurationMA2",
    "MA2_file_count": "ExfilFilesMA2",
    "MA3_time_elapsed": "OpDurationMA3",
    "MA3_file_count": "ExfilFilesMA3",
    "MA4_time_elapsed": "OpDurationMA4",
    "MA4_file_count": "ExfilFilesMA4"
}

def annotate_results(query_results_file, query_def_path_str):
    """
    Reads a query results JSON file, looks up the query definition from source files
    in a specified directory, and creates a verbose output file.
    """

    results_path = Path(query_results_file)
    query_def_path = Path(query_def_path_str)

    if not results_path.exists():
        print(f"Error: Results file '{results_path}' not found.")
        return

    if not query_def_path.exists():
        print(f"Error: Query definition directory '{query_def_path}' not found.")
        return

    # Load the results JSON
    try:
        with open(results_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON file: {e}")
        return

    # simple cache to avoid re-reading the same definition files
    file_cache = {}
    key = list(data.keys())[0]
    smc = data[key].get('smc', {})
    queries = smc.get('queries', [])
    T = data[key].get('time')
    data[key].pop('time', None)
    data[key]['serial'] = T

    print(f"Processing {len(queries)} queries...")

    for query in queries:
        # Extract file info
        # The path in the json might be relative like "./smc/file.quatex"
        # We only want the filename "file.quatex"
        raw_file_path = query.get('file')
        line_num = query.get('line')
        discarded = query.get('discarded')
        nsims = query.get('nsims')

        if raw_file_path is None or line_num is None:
            continue

        filename = Path(raw_file_path).name
        match_def_file = query_def_path / filename

        # Read the file if not in cache
        if filename not in file_cache:
            if match_def_file.exists():
                try:
                    with open(match_def_file, 'r') as f:
                        file_cache[filename] = f.readlines()
                except Exception as e:
                    print(f"Warning: Could not read definition file {match_def_file}: {e}")
                    file_cache[filename] = None
            else:
                print(f"Warning: Definition file not found: {match_def_file}")
                file_cache[filename] = None

        # Extract the line content
        lines = file_cache.get(filename)
        query_description = "N/A"

        if lines and 0 < line_num <= len(lines):
            # Line numbers are usually 1-based, list is 0-based
            query_description = lines[line_num - 1].strip()

        # Modify the query dictionary
        # Remove old keys
        query.pop('file', None)
        query.pop('line', None)
        query.pop('column', None)

        # Add new key
        query['measure'] = query_description
        query['PoD'] = float(nsims / (discarded + nsims))

    # Construct output filename
    # e.g., input.json -> input_verbose.json
    output_filename = f"{results_path.stem}_annotated{results_path.suffix}"
    output_path = results_path.parent / output_filename

    # Write output
    try:
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Successfully wrote annotated results to: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error writing output file: {e}")
        return


def extract_scenario_id(filename):
    """Extract the integer scenario ID from the filename."""
    match = re.search(r'scenario_(\d+)', filename)
    if match:
        return int(match.group(1))
    return None


def extract_smc_key(measure_str):
    """Extract the metric key from the SMC measure string."""
    # Look for the core identifier inside the E[...] block
    match = re.search(r'E\[([a-zA-Z0-9_]+)\(\)\]', measure_str)
    if match:
        key = match.group(1)
        # Normalize specific keys to match the user's mapping expectations
        if key.lower() == 'latency':
            return 'latency'
        elif key.lower() == 'goodput':
            return 'goodput'
        return key
    return measure_str


def find_smc_queries(d):
    """Recursively search for the 'queries' list inside the nested SMC JSON."""
    if isinstance(d, dict):
        if 'queries' in d and isinstance(d['queries'], list):
            return d['queries']
        for v in d.values():
            res = find_smc_queries(v)
            if res is not None:
                return res
    return None


def parse_smc_directory(directory, quatex_directory):
    """Parse Step 1: Extract SMC query statistics grouped by scenario."""
    smc_data = {}
    path = Path(directory)

    for filepath in path.glob("*.json"):
        if str(filepath).endswith('_annotated.json'):
            continue
        scenario_id = extract_scenario_id(filepath.name)
        if scenario_id is None:
            continue
        # annotate the json with query ids
        print(f"Annotating {filepath.name}")
        outfile = annotate_results(filepath, quatex_directory)

        with open(outfile, 'r') as f:
            data = json.load(f)

        queries = find_smc_queries(data)
        if not queries:
            print(f"Warning: No 'queries' list found in {outfile.name}")
            continue

        if scenario_id not in smc_data:
            smc_data[scenario_id] = {}

        for q in queries:
            if "measure" in q:
                key = extract_smc_key(q["measure"])
                # Extract and store requested statistics
                smc_data[scenario_id][key] = {
                    "mean": q.get("mean", np.nan),
                    "std": q.get("std", np.nan),
                    "radius": q.get("radius", np.nan),
                    "nsims": q.get("nsims", np.nan),
                    "PoD": q.get("PoD", np.nan)
                }

    return smc_data


def parse_tne_directory(directory):
    """Parse Step 2: Extract TNE sample results and generate summary stats."""
    tne_data = {}
    path = Path(directory)

    for filepath in path.glob("*.json"):
        scenario_id = extract_scenario_id(filepath.name)
        if scenario_id is None:
            continue

        with open(filepath, 'r') as f:
            data = json.load(f)

        if scenario_id not in tne_data:
            tne_data[scenario_id] = {}

        for key, samples in data.items():
            if isinstance(samples, list) and len(samples) > 0:
                # Generate summary statistics (mean, std, min, max)
                tne_data[scenario_id][key] = {
                    "mean": np.mean(samples),
                    "std": np.std(samples, ddof=1) if len(samples) > 1 else 0.0,
                    "min": np.min(samples),
                    "max": np.max(samples)
                }

    return tne_data


def plot_comparisons(smc_data, tne_data, output_dir="comparison_plots"):
    """Parse Step 3: Generate comparison plots for matched queries."""
    os.makedirs(output_dir, exist_ok=True)

    # Gather all unique scenario IDs across both datasets and sort them
    all_scenarios = sorted(list(set(smc_data.keys()).union(set(tne_data.keys()))))

    if not all_scenarios:
        print("No scenario data found. Please check your directories.")
        return

    # Loop through our predefined mapping dictionary
    for tne_key, smc_key in MAPPING.items():
        smc_means = []
        smc_stds = []
        tne_means = []
        tne_stds = []

        # Collect data aligned by scenario ID
        for s_id in all_scenarios:
            # Get SMC stats
            smc_stats = smc_data.get(s_id, {}).get(smc_key, {})
            smc_means.append(smc_stats.get("mean", np.nan))
            smc_stds.append(smc_stats.get("std", np.nan))

            # Get TNE stats
            tne_stats = tne_data.get(s_id, {}).get(tne_key, {})
            tne_means.append(tne_stats.get("mean", np.nan))
            tne_stds.append(tne_stats.get("std", np.nan))

        # Check if we have any valid data to plot before creating figure
        if np.isnan(smc_means).all() and np.isnan(tne_means).all():
            print(f"Skipping {smc_key}: No data found in either dataset.")
            continue

        # Generate Plot
        plt.figure(figsize=(10, 6))

        # Plot SMC Error bars
        plt.errorbar(
            all_scenarios, smc_means, yerr=smc_stds,
            label="SMC", fmt='-o', capsize=5, capthick=2, markersize=8, linewidth=2
        )

        # Plot TNE Error bars
        plt.errorbar(
            all_scenarios, tne_means, yerr=tne_stds,
            label="TNE", fmt='-s', capsize=5, capthick=2, markersize=8, linewidth=2
        )

        # Formatting titles and labels with larger fonts
        plt.title(smc_key, fontsize=18, fontweight='bold')
        plt.xlabel("scenario", fontsize=16)
        plt.ylabel("Mean with 1 Std Dev", fontsize=16)

        # Customizing ticks
        plt.xticks(all_scenarios, fontsize=14)
        plt.yticks(fontsize=14)

        # Add legend and grid
        plt.legend(fontsize=14)
        plt.grid(True, linestyle='--', alpha=0.7)

        # Tight layout to ensure everything fits
        plt.tight_layout()

        # Save figure
        save_path = os.path.join(output_dir, f"{smc_key}_comparison.png")
        plt.savefig(save_path, dpi=300)
        plt.close()

        print(f"Generated plot: {save_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate Comparison Plots for SMC vs TNE scenario results.")
    parser.add_argument("smc_directory", type=str, help="Path to the SMC directory")
    parser.add_argument("tne_directory", type=str, help="Path to the TNE directory")
    parser.add_argument("quatex_directory", type=str, help="Path to the Quatex directory where the eval files are located")
    args = parser.parse_args()

    print(f"Parsing SMC directory: {args.smc_directory}")
    smc_data = parse_smc_directory(args.smc_directory, args.quatex_directory)

    print(f"Parsing TNE directory: {args.tne_directory}")
    tne_data = parse_tne_directory(args.tne_directory)

    print("\nGenerating comparison plots...")
    plot_comparisons(smc_data, tne_data, output_dir=Path(args.smc_directory).joinpath("comparison_plots"))
    print("\nDone!")


if __name__ == "__main__":
    main()