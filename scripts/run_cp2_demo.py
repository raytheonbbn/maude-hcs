import json
from pathlib import Path
import subprocess
import time
import sys
import os
import re

import numpy as np
import matplotlib.pyplot as plt

TOPLEVELDIR = Path(os.path.dirname(__file__))

cdfGeneration = True

def cdf_gen(data_fn:str):
  raw_data = np.loadtxt(data_fn)

  num_col = raw_data.shape[1]

  for col in range(num_col):
    sorted_data = np.sort(np.array(raw_data[:, col], dtype=float))
    cdf = np.arange (1, len(sorted_data) + 1) / len(sorted_data)

    min = np.min(sorted_data)
    max = np.max(sorted_data)
    avg = np.mean(sorted_data)
    min_y = cdf[np.argmin(sorted_data)]
    max_y = cdf[np.argmax(sorted_data)]
    avg_y = cdf[(np.abs(sorted_data - avg)).argmin()]

    plt.figure(figsize=(6,4))
    plt.step(sorted_data, cdf,where="post")
    plt.xlabel("Value")
    plt.ylabel("CDF")
    plt.grid(True)
    plt.plot(min, min_y, "go", label=f"Min = {min:.3f}")
    plt.plot(max, max_y, "bo", label=f"Max = {max:.3f}")
    plt.plot(avg, avg_y, "ro", label=f"Avg = {avg:.3f}")
    plt.legend()

    if col == 0:
      cdf_fn = re.sub(r"\..*$", "", data_fn) + "_latency.pdf"
    elif col == 1:
      cdf_fn = re.sub(r"\..*$", "", data_fn) + "_goodput.pdf"
      
    plt.title(Path(cdf_fn).stem)
    plt.savefig(cdf_fn)

def smc_cdf(scenario_path:Path, result_path:Path, smc_path:Path, nsims:int, nsims_max:int):
  result = {}
  scenario_name = scenario_path.stem
  queries = [f"cp2_eval_performance.quatex"]
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
