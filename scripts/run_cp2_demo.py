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

cdfGeneration = False 

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

def smc_cdf(scenario_path:Path, result_path:Path, smc_path:Path):
  result = {}
  scenario_name = scenario_path.stem
  queries = [f"cp2_eval_performance.quatex"]
  for query in queries:
    result[query] = {}            
    dat_fn = str(result_path.resolve()) + ".dat"
    scheck_cmd = ["maude-hcs", "scheck", "--test=" + str(scenario_path.resolve()), f"--query={str(Path.joinpath(smc_path, query).resolve())}", "--format", "json", "-j", "1", "-n", "30-30", "--dump", dat_fn]
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

def smc(scenario_path:Path, result_path:Path, smc_path:Path):
  result = {}
  scenario_name = scenario_path.stem
  queries = [f"cp2_eval_{scenario_name}.quatex"]
  for query in queries:
    result[query] = {}            
    scheck_cmd = ["maude-hcs", "scheck", "--test=" + str(scenario_path.resolve()), f"--query={str(Path.joinpath(smc_path, query).resolve())}", "--format", "json", "-j", "0", "-n", "30-30"]
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

def main():    
  args = sys.argv
  if len(args) != 3:
    print(f'Expecting two arguments (1) the path of the directory with maude scenario files, and (2) path of results directory')
    sys.exit(1)
  use_case_path = TOPLEVELDIR.joinpath(sys.argv[1])
  result_path = TOPLEVELDIR.joinpath(sys.argv[2])
  smc_path = TOPLEVELDIR.parent.joinpath('smc')
  print(result_path)
  if not os.path.exists(result_path):
    os.mkdir(result_path)
  print(f'Loading scenarios from {use_case_path}')
  files = sorted(list(filter(lambda x: x.endswith('maude'), os.listdir(use_case_path))))

  for file in files:
    path = Path(os.path.join(use_case_path, file))
    print(f'Processing {path.resolve()}')
    if cdfGeneration == True:
      result = smc_cdf(path, Path.joinpath(result_path, f'{path.stem}'), smc_path)
      result_file = result_path.joinpath(f'{path.stem}_cdf.json')
    else:
      result = smc(path, Path.joinpath(result_path, f'{path.stem}'), smc_path)
      result_file = result_path.joinpath(f'{path.stem}.json')
    print(f'Writing result to {str(result_file.resolve())}')
    with open(result_file, "w") as f:
      json.dump(result, f, indent=2)

if __name__ == "__main__":
  main()
