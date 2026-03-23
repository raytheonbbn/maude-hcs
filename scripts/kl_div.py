from pathlib import Path
import numpy as np
from scipy.stats import entropy
import sys
import os
import re
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import json

TOPLEVELDIR = Path(os.path.dirname(__file__))

output_dir = "./results/"

bin = [20, 40, 60, 80, 100]

col = [0, 1, 5, 6, 7]
#col = [5, 7] # tgenonly generates mu=0 and sigma=0 for latency, goodput, opc8 
label_map = {
	0: "Latency",
	1: "Goodput",
  5: "OpDurationC2",
  6: "OpDurationC8",
  7: "OpDurationMA1"
}

epsilon = 1e-10

def kl_div_smc(mu_p, sigma_p, mu_q, sigma_q):
  sigma_p = max(sigma_p, epsilon)
  sigma_q = max(sigma_q, epsilon)
  return (np.log(sigma_q / sigma_p) + ((sigma_p**2 + ((mu_p - mu_q)**2)) / (2 * (sigma_q**2))) - 0.5)

def kl_div(data_p_fn:str, data_q_fn:str, col=0, bin=100):
  # Load data from .dat file (assuming whitespace separation)
  data = np.genfromtxt(data_p_fn, delimiter=" ", missing_values=["None"], filling_values=np.nan)
  data_p = data[:, col]
  data_tgen = np.genfromtxt(data_q_fn, delimiter=" ", missing_values=["None"], filling_values=np.nan)
  data_q = data_tgen[:, col]

  min_val = min(np.min(data_p), np.min(data_q))
  max_val = max(np.max(data_p), np.max(data_q))
  bins = np.linspace(min_val, max_val, num=bin) 

  counts_p, _ = np.histogram(data_p, bins=bins, density=False)
  counts_q, _ = np.histogram(data_q, bins=bins, density=False)
    
  # Convert counts to probabilities (normalize to sum to 1)
  p = (counts_p + epsilon) / np.sum(counts_p + epsilon)
  q = (counts_q + epsilon) / np.sum(counts_q + epsilon)

  kl_div_pq = entropy(p, qk=q) # D_KL(P || Q)
  kl_div_qp = entropy(q, qk=p) # D_KL(Q || P)

  return kl_div_pq, kl_div_qp

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
  if len(args) != 4:
    print(
      f'Expecting three arguments:\n(1) path to SMC results of P (both .dat and _cdf.json)\n(2) path to SMC results of Q (both .dat and _cdf.json)\n(3) scenario index (e.g. "10") or range (e.g. "1-3")\n')
    sys.exit(1)

  use_case_path = TOPLEVELDIR.joinpath(sys.argv[1])
  baseline_path = TOPLEVELDIR.joinpath(sys.argv[2])
  selection_arg = sys.argv[3]

  # Parse the selection argument
  selected_indices = parse_selection(selection_arg)

  print(f'Loading scenarios from {use_case_path}')

  if not os.path.exists(use_case_path):
    print(f"Error: Directory {use_case_path} does not exist.")
    sys.exit(1)

  # Filter files based on pattern "cp2_scenario_<n>.dat" and the selected indices
  all_files = os.listdir(use_case_path)
  pattern = re.compile(r'^cp2_scenario_(\d+)\.dat$')

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
    p_path = Path(os.path.join(use_case_path, file))
    print(f'Processing {p_path.resolve()}')
    q_path = Path(os.path.join(baseline_path, file))
    print(f'Processing {q_path.resolve()}')
		
    fig, (ax1, ax2) = plt.subplots(2,1, sharex=True)

    for c in col:
      kl_pq, kl_qp = zip(*(kl_div(p_path,q_path,c,b) for b in bin)) 
      ax1.plot(bin, kl_pq, marker='o', label=label_map[c])
      ax2.plot(bin, kl_qp, marker='o', label=label_map[c])

    fig.suptitle("KL Divergence: " + os.path.splitext(file)[0]) # + "\n(p=with HCS, q=without HCS)")
    ax1.set_ylabel(r"$D_{KL}(p \,\|\, q)$ (nats)")
    ax2.set_ylabel(r"$D_{KL}(q \,\|\, p)$ (nats)")
    ax2.set_xlabel("num of bins")
    ax1.xaxis.set_major_locator(MultipleLocator(20))
    ax1.legend()
    ax2.legend()
    ax1.grid(True)
    ax2.grid(True)
    plt.savefig(output_dir + os.path.splitext(file)[0] + "_kl_div")
    plt.close('all')

  for file in files:
    json_file = os.path.splitext(file)[0] + "_cdf.json"
    p_path = Path(os.path.join(use_case_path, json_file))
    with open(p_path, "r") as pf:
      p_result = json.load(pf)
      print("Processing", p_path)

    q_path = Path(os.path.join(baseline_path, json_file))
    with open(q_path, "r") as qf:
      q_result = json.load(qf)
      print("Processing", q_path)

    for c in col:
      for k, v in p_result.items():
        query = v["smc"]["queries"][c]
        mu_p = query["mean"]
        sigma_p = query["std"]

      for k, v in q_result.items():
        query = v["smc"]["queries"][c]
        mu_q = query["mean"]
        sigma_q = query["std"]

      smc_pq = kl_div_smc(mu_p, sigma_p, mu_q, sigma_q) 
      print(f"{label_map[c]} D_KL(P||Q): {smc_pq:.8f} nats")

      smc_qp = kl_div_smc(mu_q, sigma_q, mu_p, sigma_p) 
      print(f"{label_map[c]} D_KL(Q||P): {smc_qp:.8f} nats")

if __name__ == "__main__":
  main()
