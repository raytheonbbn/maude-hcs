import json
import sys
import os
from pathlib import Path


def annotate_results(query_results_file, query_def_path_str):
    """
    Reads a query results JSON file, looks up the query definition from source files
    in a specified directory, and creates a verbose output file.
    """

    results_path = Path(query_results_file)
    query_def_path = Path(query_def_path_str)

    if not results_path.exists():
        print(f"Error: Results file '{results_path}' not found.")
        sys.exit(1)

    if not query_def_path.exists():
        print(f"Error: Query definition directory '{query_def_path}' not found.")
        sys.exit(1)

    # Load the results JSON
    try:
        with open(results_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON file: {e}")
        sys.exit(1)

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
    except Exception as e:
        print(f"Error writing output file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python annotate_results.py <queryResults.json> <queryDefPath>")
        sys.exit(1)

    annotate_results(sys.argv[1], sys.argv[2])