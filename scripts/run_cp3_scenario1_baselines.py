#!/usr/bin/env python3
"""
Script to generate and run parallel baseline experiments for scenario1,
run multiple trials with distinct random seeds per combination,
combine the results into a single BL equation, and populate
pwnd_cp3_scenario_1-baseline-eq-temp.maude.
"""

import os
import sys
import argparse
import subprocess
import time
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from collections import defaultdict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCENARIO_DIR = os.path.join(REPO_ROOT, "use-cases", "challenge-problem-3", "cp3_scenarios", "scenario1")
YAML_PATH = os.path.join(SCENARIO_DIR, "pwnd_cp3_scenario_1.yaml")
GEN_SCRIPT = os.path.join(REPO_ROOT, "scripts", "generate_cp3_v3.py")
BASELINES_DIR = os.path.join(SCENARIO_DIR, "baselines")
LOGS_DIR = os.path.join(BASELINES_DIR, "logs")
TMP_TEMPLATE_PATH = os.path.join(SCENARIO_DIR, "pwnd_cp3_scenario_1-baseline-eq-tmp.maude")
TEMP_OUT_PATH = os.path.join(SCENARIO_DIR, "pwnd_cp3_scenario_1-baseline-eq-temp.maude")
OUT_MAUDE_FILE = os.path.join(SCENARIO_DIR, "pwnd_cp3_scenario_1-baseline-eq.maude")

sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "cp3_glue"))
from parse_baseline import parse_baseline, Bl, Baseline


def run_maude_task(maude_file, log_file, cwd):
    """Executes a single Maude file, writing stdout/stderr to a log file."""
    try:
        with open(log_file, "w") as f:
            subprocess.run(
                ["maude", os.path.basename(maude_file)],
                stdout=f,
                stderr=subprocess.STDOUT,
                check=False,
                cwd=cwd
            )
        return True, maude_file, None
    except Exception as e:
        return False, maude_file, str(e)


def generate_baselines(baseline_time=10800.0):
    """Step 1: Generate parallel baseline Maude files for all VP and feature combos."""
    print(f"\n[1/3] Generating parallel baseline files for scenario1 (baselineTime={baseline_time})...", flush=True)
    res_gen = subprocess.run([
        sys.executable,
        GEN_SCRIPT,
        YAML_PATH,
        "--parallelizeBaseline",
        "--quatex",
        f"--baselineTime={baseline_time}"
    ], capture_output=True, text=True)

    if res_gen.returncode != 0:
        print(f"Error generating parallel baseline files:\n{res_gen.stderr}", flush=True)
        return False
    print(f"      Baseline files successfully generated in {BASELINES_DIR}", flush=True)
    return True


def run_baseline_trials(num_trials=10, max_workers=None):
    """Step 2: Create trial files with distinct seeds and run them in parallel."""
    print(f"\n[2/3] Setting up and executing {num_trials} trials per baseline in parallel...", flush=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    # Find base maude files (excluding any trial files)
    base_files = [
        f for f in os.listdir(BASELINES_DIR)
        if f.endswith(".maude") and "_trial" not in f
    ]

    if not base_files:
        print(f"Error: No base .maude files found in {BASELINES_DIR}!", flush=True)
        return False

    print(f"      Found {len(base_files)} baseline combinations. Creating {len(base_files) * num_trials} trial files...", flush=True)

    tasks = []
    trial_files = []

    for base_file in base_files:
        base_path = os.path.join(BASELINES_DIR, base_file)
        with open(base_path, "r") as f:
            base_content = f.read()

        base_stem = base_file[:-6]  # strip '.maude'

        for trial_idx in range(1, num_trials + 1):
            seed = trial_idx
            trial_filename = f"{base_stem}_trial{trial_idx}.maude"
            trial_path = os.path.join(BASELINES_DIR, trial_filename)
            log_filename = f"{trial_filename}.log"
            log_path = os.path.join(LOGS_DIR, log_filename)

            # Replace initState(counter) with initState(seed)
            trial_content = base_content.replace("initState(counter)", f"initState({seed})")
            with open(trial_path, "w") as f:
                f.write(trial_content)

            trial_files.append(trial_path)
            tasks.append((trial_path, log_path, BASELINES_DIR))

    print(f"      Running {len(tasks)} trial tasks with ProcessPoolExecutor (max_workers={max_workers})...", flush=True)
    t0 = time.time()
    completed_count = 0
    failed_count = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_maude_task, m_p, l_p, cwd) for (m_p, l_p, cwd) in tasks]
        for future in futures:
            success, m_p, err = future.result()
            if success:
                completed_count += 1
            else:
                failed_count += 1
                print(f"      [FAILED] {os.path.basename(m_p)}: {err}", flush=True)

    t1 = time.time()
    print(f"      Completed {completed_count}/{len(tasks)} runs in {t1 - t0:.2f}s ({failed_count} failed).", flush=True)
    return failed_count == 0


def combine_trials_and_build_equation():
    """Step 3: Parse baseline trial logs, combine distributions across trials, and write equation files."""
    print(f"\n[3/3] Parsing trial outputs and combining distributions...", flush=True)

    if not os.path.exists(LOGS_DIR):
        print(f"Error: Logs directory {LOGS_DIR} does not exist!", flush=True)
        return False

    log_files = [f for f in os.listdir(LOGS_DIR) if f.endswith(".log") and not f.startswith(".")]
    if not log_files:
        print(f"Error: No log files found in {LOGS_DIR}!", flush=True)
        return False

    print(f"      Parsing {len(log_files)} log files...", flush=True)
    combo_bls = defaultdict(list)
    parsed_params = None

    for fn in log_files:
        log_path = os.path.join(LOGS_DIR, fn)
        with open(log_path, "r") as f:
            log_content = f.read()

        try:
            bl_obj = parse_baseline(log_content)
            if parsed_params is None:
                parsed_params = bl_obj.params
            for b in bl_obj.bls:
                combo_bls[(b.vantage, b.feat)].append(b)
        except Exception as e:
            print(f"      Warning: could not parse {fn}: {e}", flush=True)

    if not combo_bls:
        print("Error: No baseline entries could be parsed from logs!", flush=True)
        return False

    # Combine distributions for each (vantage, feat) combination
    combined_bl_list = []
    for (vantage, feat), bl_list in sorted(combo_bls.items()):
        # Average the k value across all trials for this combo
        avg_k = sum(b.k for b in bl_list) / len(bl_list)

        # Merge and sort all empirical CDF values across trials
        merged_ecdf = sorted([val for b in bl_list for val in b.ecdf])

        combined_bl_list.append(Bl(feat=feat, vantage=vantage, k=avg_k, ecdf=merged_ecdf))

    # Format the combined baseline equation
    bl_str = " :; ".join(map(str, combined_bl_list))
    equation_str = f"eq BL = ( {bl_str} ) ."

    # Read template file
    template_path = TMP_TEMPLATE_PATH if os.path.exists(TMP_TEMPLATE_PATH) else TEMP_OUT_PATH
    if not os.path.exists(template_path):
        # Fallback template if neither exists
        tmpl_data = (
            "sload ../../../../maude_hcs/lib/smc/smc-baseline-shared\n\n\n"
            "mod PWND-CP3-SCENARIO-1-BASELINE-EQ is\n"
            "  inc SMC-BASELINE-SHARED .\n"
            "  \n"
            "  ---- insert baseline output here ---\n"
            "  eq BL = nilBaseLine .\n\n"
            "endm\neof\n"
        )
    else:
        with open(template_path, "r") as f:
            tmpl_data = f.read()

    new_data = tmpl_data.replace("eq BL = nilBaseLine .", equation_str)

    # Write to pwnd_cp3_scenario_1-baseline-eq-temp.maude
    with open(TEMP_OUT_PATH, "w") as f:
        f.write(new_data)
    print(f"      Wrote combined BL equation to {TEMP_OUT_PATH} ({len(combined_bl_list)} combinations, {len(new_data.splitlines())} lines).", flush=True)

    # Also write to standard pwnd_cp3_scenario_1-baseline-eq.maude
    with open(OUT_MAUDE_FILE, "w") as f:
        f.write(new_data)
    print(f"      Wrote combined BL equation to {OUT_MAUDE_FILE}.", flush=True)

    return True


def main():
    parser = argparse.ArgumentParser(description="Generate and run Scenario 1 baselines with multiple trials.")
    parser.add_argument("--baselineTime", type=float, default=10800.0, help="Baseline time duration (default: 10800.0)")
    parser.add_argument("--numTrials", type=int, default=10, help="Number of trials per baseline combo (default: 10)")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel worker processes (default: CPU count)")
    parser.add_argument("--skipGen", action="store_true", help="Skip baseline generation step")
    parser.add_argument("--skipRun", action="store_true", help="Skip running trials (only re-combine logs)")
    args = parser.parse_args()

    print(f"==================================================", flush=True)
    print(f" Scenario 1 Parallel Baseline Pipeline", flush=True)
    print(f" Directory: {SCENARIO_DIR}", flush=True)
    print(f" Trials: {args.numTrials} | Duration: {args.baselineTime}s", flush=True)
    print(f"==================================================", flush=True)

    # 1. Generate parallel baselines
    if not args.skipGen:
        if not generate_baselines(baseline_time=args.baselineTime):
            sys.exit(1)
    else:
        print("[1/3] Skipping baseline generation (--skipGen set).", flush=True)

    # 2. Run trials
    if not args.skipRun:
        if not run_baseline_trials(num_trials=args.numTrials, max_workers=args.workers):
            print("Warning: One or more baseline trial runs failed.", flush=True)
    else:
        print("[2/3] Skipping baseline trial execution (--skipRun set).", flush=True)

    # 3. Combine and generate BL equation
    if not combine_trials_and_build_equation():
        sys.exit(1)

    print(f"\n==================================================", flush=True)
    print(f" Scenario 1 Baselines Successfully Generated & Combined!", flush=True)
    print(f" Output equation file: {TEMP_OUT_PATH}", flush=True)
    print(f"==================================================", flush=True)


if __name__ == "__main__":
    main()
