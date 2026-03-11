import json
from pathlib import Path
import subprocess
import time
import sys
import os
import re

import numpy as np
import matplotlib.pyplot as plt
from plotfinal import MAPPING, REVERSE_MAPPING, QUERY_KEYS

TOPLEVELDIR = Path(os.path.dirname(__file__))

cdfGeneration = False

def get_cdf_filename(col: int) -> str:
    """
    Takes a column index (0-43) and returns the corresponding query key
    formatted as a PDF filename (e.g., '_latency.pdf').
    """
    # Lookup table of all 44 column names extracted from the queries.
    # Converted to lowercase to match your _latency and _goodput examples.


    # Check if the column ID is within the valid range
    if 0 <= col < len(QUERY_KEYS):
        cdf_fn = f"_{QUERY_KEYS[col]}.pdf"
        return cdf_fn
    else:
        raise ValueError(f"Column ID {col} is out of bounds. Must be between 0 and 43.")

def cdf_gen(data_fn: str, prefix: str = None, output_dir: str = None, emp_data: dict = None):
    """
    Computes and plots the CDF for samples from a file, optionally overlaying empirical data.
    """
    if not prefix:
        prefix = re.sub(r"\..*$", "", data_fn)

    raw_data = np.genfromtxt(data_fn, delimiter=" ", missing_values=["None"], filling_values=np.nan)

    if len(raw_data.shape) < 2:
        print(f'******++++Skipping scenario {prefix} input .dat {data_fn} empty++++********')
        return

    num_col = raw_data.shape[1]
    N = raw_data.shape[0]

    # Increase base font size for readability
    plt.rcParams.update({'font.size': 14})

    for col in range(num_col):
        data = raw_data[:, col]
        filtered_data = data[~np.isnan(data)]
        sorted_data = np.sort(np.array(filtered_data, dtype=float))

        if len(sorted_data) == 0:
            print(f'******Skipping scenario {prefix} col {col}, no data********')
            continue

        cdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)

        # Renamed min/max to avoid shadowing built-in functions
        min_val = np.min(sorted_data)
        max_val = np.max(sorted_data)
        avg_val = np.mean(sorted_data)
        min_y = cdf[np.argmin(sorted_data)]
        max_y = cdf[np.argmax(sorted_data)]
        avg_y = cdf[(np.abs(sorted_data - avg_val)).argmin()]

        plt.figure(figsize=(8, 5))

        # Plot raw data (SMC)
        plt.step(sorted_data, cdf, where="post", label="SMC", linewidth=2)

        # Plot empirical data (T&E) if provided
        N_emp_str = ''
        if emp_data is not None:
            query_key = QUERY_KEYS[col]
            # Get the correct empirical key from the reverse mapping, fallback to the query_key if not found
            emp_key = REVERSE_MAPPING.get(query_key, query_key)

            if emp_key in emp_data:
                emp_entry = emp_data[emp_key]

                # Check if it's structured as a dict ({"samples": [], "nsims": X}) or just the list directly
                if isinstance(emp_entry, dict) and "samples" in emp_entry:
                    emp_samples = emp_entry["samples"]
                else:
                    emp_samples = emp_entry

                if len(emp_samples) > 0:
                    sorted_emp = np.sort(np.array(emp_samples, dtype=float))
                    cdf_emp = np.arange(1, len(sorted_emp) + 1) / len(sorted_emp)
                    N_emp_str = f'(N_tne={len(emp_samples)})'
                    plt.step(sorted_emp, cdf_emp, where="post", label="T&E", linestyle="--", linewidth=2)
                    min_emp_val = np.min(sorted_emp)
                    max_emp_val = np.max(sorted_emp)
                    avg_emp_val = np.mean(sorted_emp)
                    min_emp_y = cdf_emp[np.argmin(sorted_emp)]
                    max_emp_y = cdf_emp[np.argmax(sorted_emp)]
                    avg_emp_y = cdf_emp[(np.abs(sorted_emp - avg_emp_val)).argmin()]
                    plt.plot(min_emp_val, min_emp_y, "g+", markersize=8, label=f"T&E Min = {min_emp_val:.3f}")
                    plt.plot(max_emp_val, max_emp_y, "b+", markersize=8, label=f"T&E Max = {max_emp_val:.3f}")
                    plt.plot(avg_emp_val, avg_emp_y, "r+", markersize=8, label=f"T&E Avg = {avg_emp_val:.3f}")



        plt.xlabel("Value", fontsize=16)
        plt.ylabel("CDF", fontsize=16)
        plt.grid(True)

        # Add markers for SMC stats
        plt.plot(min_val, min_y, "go", markersize=8, label=f"SMC Min = {min_val:.3f}")
        plt.plot(max_val, max_y, "bo", markersize=8, label=f"SMC Max = {max_val:.3f}")
        plt.plot(avg_val, avg_y, "ro", markersize=8, label=f"SMC Avg = {avg_val:.3f}")

        plt.legend(fontsize=12, loc='best')

        cdf_fn = prefix + get_cdf_filename(col)

        plt.title(f'{Path(cdf_fn).stem} (SMC N={N}) {N_emp_str}', fontsize=16)

        # Make the plot tight to ensure labels fit cleanly
        plt.tight_layout()

        if output_dir:
            plt.savefig(Path(output_dir).joinpath(cdf_fn))
        else:
            plt.savefig(Path(data_fn).parent.joinpath(cdf_fn))
        plt.close('all')

def smc_cdf(scenario_path:Path, result_path:Path, smc_path:Path, nsims:int, nsims_max:int):
  result = {}
  scenario_name = scenario_path.stem
  #queries = [f"cp2_eval_performance.quatex"]
  queries = [f"cp2_eval_{scenario_name}.quatex"]
  for query in queries:
    result[query] = {}            
    dat_fn = str(result_path.resolve()) + ".dat"
    scheck_cmd = ["maude-hcs", "scheck", "--test=" + str(scenario_path.resolve()), f"--query={str(Path.joinpath(smc_path, query).resolve())}", "--format", "json", "-j", "1", "-n", f"{nsims}-{nsims_max}", "--dump", dat_fn]
    result[query]['scheck cmd'] = ' '.join([x for x in scheck_cmd])
    print(f'{result[query]['scheck cmd']}')
    start = time.perf_counter()
    scheck_output = subprocess.run(scheck_cmd, capture_output=True, text=True, check=True)
    end = time.perf_counter()
    T = end - start            
    new_result = json.loads(scheck_output.stdout)
    result[query]['smc'] = new_result
    result[query]['time'] = f'{T:.2f} seconds'
    print(f"time ({query}): {result[query]['time']}")
    cdf_gen(dat_fn)            

  return result

def smc(scenario_path:Path, result_path:Path, smc_path:Path, nsims:int, nsims_max:int):
  result = {}
  scenario_name = scenario_path.stem
  queries = [f"cp2_eval_{scenario_name}.quatex"]
  for query in queries:
    result[query] = {}            
    scheck_cmd = ["maude-hcs", "scheck", "--test=" + str(scenario_path.resolve()), f"--query={str(Path.joinpath(smc_path, query).resolve())}", "--format", "json", "-j", "0", "-n", f"{nsims}-{nsims_max}", "--dump", str(result_path.resolve())]
    result[query]['scheck cmd'] = ' '.join([x for x in scheck_cmd])
    print(f'{result[query]['scheck cmd']}')
    start = time.perf_counter()
    scheck_output = subprocess.run(scheck_cmd, capture_output=True, text=True, check=True)
    end = time.perf_counter()
    T = end - start            
    new_result = json.loads(scheck_output.stdout)
    result[query]['smc'] = new_result
    result[query]['time'] = f'{T:.2f} seconds'
    print(f"time ({query}): {result[query]['time']}")
      
  return result


def parse_selection(selection_str):
    """
    Parses a string like '10' or '1-3' into a set of integers.
    """
    selected_indices = set()
    try:
        if '-' in selection_str:
            parts = selection_str.split('-')
            if len(parts) == 2:
                start, end = map(int, parts)
                # Assuming inclusive range
                selected_indices.update(range(start, end + 1))
            else:
                raise ValueError("Invalid range format")
        else:
            selected_indices.add(int(selection_str))
    except ValueError:
        print(f"Error: Argument '{selection_str}' must be an integer (e.g., '10') or a range (e.g., '1-3').")
        sys.exit(1)

    return selected_indices

def main():
    args = sys.argv
    # Expecting 4 items: [script_name, use_case_dir, results_dir, selection]
    if len(args) != 6:
        print(
            f'Expecting three arguments:\n(1) path of the directory with maude scenario files\n(2) path of results directory\n(3) scenario index (e.g. "10") or range (e.g. "1-3")\n (4) nsims (5) nsims_max')
        sys.exit(1)

    use_case_path = TOPLEVELDIR.joinpath(sys.argv[1])
    result_path = TOPLEVELDIR.joinpath(sys.argv[2])
    selection_arg = sys.argv[3]
    nsims = int(sys.argv[4])
    nsims_max = int(sys.argv[5])

    # Parse the selection argument
    selected_indices = parse_selection(selection_arg)

    smc_path = TOPLEVELDIR.parent.joinpath('smc')
    print(f"Results Directory: {result_path}")

    if not os.path.exists(result_path):
        os.mkdir(result_path)

    print(f'Loading scenarios from {use_case_path}')

    if not os.path.exists(use_case_path):
        print(f"Error: Directory {use_case_path} does not exist.")
        sys.exit(1)

    # Filter files based on pattern "cp2_scenario_<n>.maude" and the selected indices
    all_files = os.listdir(use_case_path)
    pattern = re.compile(r'^cp2_scenario_(\d+)\.maude$')

    filtered_files = []
    for filename in all_files:
        match = pattern.match(filename)
        if match:
            file_index = int(match.group(1))
            if file_index in selected_indices:
                filtered_files.append(filename)

    files = sorted(filtered_files)

    if not files:
        print(f"No files matched the selection '{selection_arg}' in {use_case_path}.")
        # We don't exit here, just loop 0 times, but printing a warning is helpful.


    for file in files:
        path = Path(os.path.join(use_case_path, file))
        print(f'Processing {path.resolve()}')
        if cdfGeneration == True:
          result = smc_cdf(path, Path.joinpath(result_path, f'{path.stem}'), smc_path, nsims, nsims_max)
          result_file = result_path.joinpath(f'{path.stem}_cdf.json')
        else:
          result = smc(path, Path.joinpath(result_path, f'{path.stem}'), smc_path, nsims, nsims_max)
          result_file = result_path.joinpath(f'{path.stem}.json')
        print(f'Writing result to {str(result_file.resolve())} nsims {nsims}')
        with open(result_file, "w") as f:
          json.dump(result, f, indent=2)

if __name__ == "__main__":
  main()
