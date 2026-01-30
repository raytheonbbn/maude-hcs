import json
import os
import sys
import re
import glob


def parse_measure_name(measure_str):
    """
    Extracts a cleaner measure name from the raw query string.
    Example: 'eval E[Latency()] with delta = 2 ;' -> 'Latency'
    """
    # Regex looks for content between 'E[' and the next '(' or ']'
    # Matches 'Latency' in 'E[Latency()]' or 'E[Latency]'
    match = re.search(r'E\[(.*?)[(\]]', measure_str)
    if match:
        return match.group(1).strip()
    return measure_str


def get_scenario_id(filename):
    """
    Extracts the scenario number from the filename.
    Example: 'cp2_scenario_1_annotated.json' -> 1
    """
    match = re.search(r'cp2_scenario_(\d+)_annotated\.json', filename)
    if match:
        return int(match.group(1))
    return None


def process_directory(input_dir):
    # dictionary to hold data: results[measure_name][scenario_id] = stats_string
    results_map = {}
    scenario_ids = set()

    # Construct the search pattern for the specific file naming convention
    search_pattern = os.path.join(input_dir, "cp2_scenario_*_annotated.json")
    files = glob.glob(search_pattern)

    if not files:
        print(f"No files found matching pattern: {search_pattern}")
        return

    print(f"Found {len(files)} files. Processing...")

    for filepath in files:
        filename = os.path.basename(filepath)
        s_id = get_scenario_id(filename)

        if s_id is None:
            print(f"Skipping file with unexpected name format: {filename}")
            continue

        scenario_ids.add(s_id)

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

                # The root key is dynamic (e.g., "cp2_eval_cp2_scenario_1.quatex")
                # We take the first value found.
                root_val = next(iter(data.values()))

                if 'smc' in root_val and 'queries' in root_val['smc']:
                    queries = root_val['smc']['queries']

                    for q in queries:
                        measure_raw = q.get('measure', 'Unknown')
                        measure_name = parse_measure_name(measure_raw)

                        mean_val = q.get('mean', 0.0)
                        std_val = q.get('std', 0.0)
                        pod_val = q.get('PoD', 0.0)

                        # Create a formatted string for the cell
                        # Format: Mean (Std) [PoD]
                        # Example: 201.83 (17.38) [1.00]
                        cell_str = f"{mean_val:.2f} ({std_val:.2f}) [{pod_val:.2f}]"

                        if measure_name not in results_map:
                            results_map[measure_name] = {}

                        results_map[measure_name][s_id] = cell_str

        except Exception as e:
            print(f"Error processing {filename}: {e}")

    # Sort scenario IDs numerically
    sorted_s_ids = sorted(list(scenario_ids))

    # Sort measures alphabetically
    sorted_measures = sorted(list(results_map.keys()))

    # --- Generate Table ---

    # 1. Determine column widths
    # Measure column width
    max_measure_len = len("Measure")
    for m in sorted_measures:
        max_measure_len = max(max_measure_len, len(m))

    col_width_measure = max_measure_len + 2  # padding

    # Scenario columns width
    # We need to check the data length in every cell to find the max width required
    col_widths = {}
    for s_id in sorted_s_ids:
        header_str = f"Scenario {s_id}"
        max_len = len(header_str)
        for m in sorted_measures:
            cell_data = results_map.get(m, {}).get(s_id, "-")
            max_len = max(max_len, len(cell_data))
        col_widths[s_id] = max_len + 2  # padding

    # 2. Build Table String
    lines = []

    # Header Row
    header = f"{'Measure':<{col_width_measure}}"
    for s_id in sorted_s_ids:
        header += f"{f'Scenario {s_id}':<{col_widths[s_id]}}"
    lines.append(header)

    # Separator Line
    lines.append("-" * len(header))

    # Data Rows
    for m in sorted_measures:
        row = f"{m:<{col_width_measure}}"
        for s_id in sorted_s_ids:
            cell_data = results_map.get(m, {}).get(s_id, "-")
            row += f"{cell_data:<{col_widths[s_id]}}"
        lines.append(row)

    output_content = "\n".join(lines)

    # Write to file
    output_path = os.path.join(input_dir, "summary.txt")
    try:
        with open(output_path, 'w') as f:
            f.write(output_content)
        print(f"Summary table written to: {output_path}")
        print("Format used: Mean (Std) [PoD]")
    except Exception as e:
        print(f"Error writing output file: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <input_directory>")
        sys.exit(1)

    input_directory = sys.argv[1]

    if not os.path.isdir(input_directory):
        print(f"Error: Directory not found: {input_directory}")
        sys.exit(1)

    process_directory(input_directory)