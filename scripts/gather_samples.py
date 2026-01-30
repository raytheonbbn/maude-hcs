import os
import sys
import argparse
import re
import shutil
from run_cp2_demo import cdf_gen
from annotateResults import annotate_results

def process_scenarios(input_dir, output_dir, smc_dir):
    """
    Combines sample files for scenarios and copies non-sample files.
    """

    # Ensure output directory exists
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except OSError as e:
            print(f"Error creating output directory: {e}")
            sys.exit(1)

    # Regex to parse filenames
    # Looks for: [ScenarioName].[RunID]-[Index]
    # ^(.*)     : Capture Group 1 - The Scenario Name (Greedy, captures everything up to the last dot block)
    # \.        : A literal dot separator
    # ([^.]+)   : Capture Group 2 - The RunID/Timestamp (Everything not a dot)
    # -         : A literal hyphen
    # (\d+)$    : Capture Group 3 - The Index (Digits at the end of the line)
    filename_pattern = re.compile(r"^(.*)\.([^.]+)-(\d+)$")

    scenarios = {}  # Key: ScenarioName, Value: List of (index, filepath)
    non_sample_files = []

    print(f"Scanning directory: {input_dir}")

    try:
        files = os.listdir(input_dir)
    except FileNotFoundError:
        print(f"Error: Input directory '{input_dir}' not found.")
        sys.exit(1)

    for filename in files:
        filepath = os.path.join(input_dir, filename)

        # Skip directories, process only files
        if not os.path.isfile(filepath):
            continue

        match = filename_pattern.match(filename)

        if match:
            # It's a sample file (ends in -Index)
            scenario_name = match.group(1)
            # run_id = match.group(2) # We don't need the timestamp for grouping, just the name
            index = int(match.group(3))  # Convert to int for proper sorting (0, 1, 2... 10)

            if scenario_name not in scenarios:
                scenarios[scenario_name] = []

            scenarios[scenario_name].append((index, filepath))
        else:
            # It's a non-sample file (e.g., .json)
            non_sample_files.append(filename)

    # 1. Process and Combine Sample Files
    for scenario_name, file_list in scenarios.items():
        # Sort files based on the index (element 0 of the tuple)
        file_list.sort(key=lambda x: x[0])

        output_filename = f"{scenario_name}_samples.dat"
        output_filepath = os.path.join(output_dir, output_filename)

        print(f"Processing '{scenario_name}': Combining {len(file_list)} files into {output_filename}...")

        try:
            with open(output_filepath, 'wb') as outfile:
                for _, infile_path in file_list:
                    with open(infile_path, 'rb') as infile:
                        shutil.copyfileobj(infile, outfile)

                        # Optional: Ensure newline separation between files if the source
                        # files don't end with one. If strict binary concatenation is
                        # preferred, remove the lines below.
                        # infile.seek(0, os.SEEK_END)
                        # if infile.tell() > 0:
                        #     infile.seek(-1, os.SEEK_END)
                        #     last_char = infile.read(1)
                        #     if last_char != b'\n':
                        #         outfile.write(b'\n')

        except IOError as e:
            print(f"Error writing to {output_filepath}: {e}")

        print('generating CDFs')
        cdf_gen(output_filepath, scenario_name)

    # 2. Copy Non-Sample Files
    for filename in non_sample_files:
        src = os.path.join(input_dir, filename)
        dst = os.path.join(output_dir, filename)
        print(f"Copying non-sample file: {filename}")
        try:
            shutil.copy2(src, dst)
        except IOError as e:
            print(f"Error copying {filename}: {e}")

        # if file is a json file, annorate
        if dst.endswith('.json'):
            print(f'Annotating {filename}... using quatex in {smc_dir}')
            annotate_results(dst, smc_dir)

    print("\nProcessing complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Combine distributed scenario result files into single sample files."
    )

    parser.add_argument("input_dir", help="Path to the directory containing results")
    parser.add_argument("output_dir", help="Path to the directory where output will be saved")
    parser.add_argument("smc_dir", help="Path to the directory where smc quatex formula is")

    args = parser.parse_args()

    process_scenarios(args.input_dir, args.output_dir, args.smc_dir)