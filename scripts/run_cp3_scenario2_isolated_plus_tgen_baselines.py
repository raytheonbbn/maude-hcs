#!/usr/bin/env python3
"""
Script to generate and run parallel baseline experiments for scenario2_isolated_plus_tgen protocols,
and parse baseline outputs to generate corresponding only_*-baseline-eq-combo1.maude files.
"""

import os
import sys
import subprocess
import time
import shutil
from pathlib import Path

PROTOCOLS = [
    "only_mastodon",
    "only_obfs",
    "only_skyhook",
    "only_webtunnel"
]

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCENARIO_DIR = os.path.join(REPO_ROOT, "use-cases", "challenge-problem-3", "cp3_scenarios", "scenario2_isolated_plus_tgen")
GEN_SCRIPT = os.path.join(REPO_ROOT, "scripts", "generate_cp3_v3.py")
PARALLEL_RUNNER = os.path.join(REPO_ROOT, "scripts", "cp3_glue", "run_parallel_maudes.py")

sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "cp3_glue"))
from parse_baseline import parse_baseline, Baseline

def process_protocol(proto):
    print(f"\n==========================================", flush=True)
    print(f" Processing baseline for {proto} ...", flush=True)
    print(f"==========================================", flush=True)
    
    yaml_path = os.path.join(SCENARIO_DIR, f"{proto}.yaml")
    baselines_dir = os.path.join(SCENARIO_DIR, "baselines")
    logs_dir = os.path.join(baselines_dir, "logs")
    out_maude_file = os.path.join(SCENARIO_DIR, f"{proto}-baseline-eq-combo1.maude")

    # Clean previous baseline files and logs
    shutil.rmtree(baselines_dir, ignore_errors=True)

    # Step 1: Generate parallel baseline Maude files
    print(f"[1/3] Generating parallel baseline files for {proto}...", flush=True)
    res_gen = subprocess.run([
        sys.executable, GEN_SCRIPT, yaml_path, "--parallelizeBaseline", "--filterVpFeatCombos", "--quatex", "--baselineTime=3600.0"
    ], capture_output=True, text=True)
    if res_gen.returncode != 0:
        print(f"Error generating parallel baseline files:\n{res_gen.stderr}", flush=True)
        return False

    # Step 2: Run all baseline files in parallel
    print(f"[2/3] Executing parallel Maude baseline runs...", flush=True)
    t0 = time.time()
    res_run = subprocess.run([
        sys.executable, PARALLEL_RUNNER, baselines_dir
    ], capture_output=True, text=True)
    t1 = time.time()
    print(f"      Parallel runs completed in {t1 - t0:.2f}s (returncode={res_run.returncode})", flush=True)
    if res_run.returncode != 0:
        print(f"Error executing parallel baseline runs:\n{res_run.stderr}", flush=True)
        return False

    # Step 3: Parse log outputs and write combined baseline eq file
    print(f"[3/3] Combining baseline logs into {out_maude_file}...", flush=True)
    baselines_objs = []
    if os.path.exists(logs_dir):
        for fn in os.listdir(logs_dir):
            if fn.startswith("."): continue
            log_p = os.path.join(logs_dir, fn)
            if os.path.isfile(log_p):
                with open(log_p, "r") as f:
                    baselines_objs.append(parse_baseline(f.read()))

    if baselines_objs:
        combined_bl = Baseline.join(baselines_objs)
        bl_str = " :; ".join(map(str, combined_bl.bls))
    else:
        bl_str = "nilBaseLine"

    tmp_path = os.path.join(SCENARIO_DIR, f"{proto}-baseline-eq-tmp.maude")
    if not os.path.exists(tmp_path):
        print(f"Error: Template file {tmp_path} does not exist!", flush=True)
        return False

    with open(tmp_path, "r") as f:
        tmpl_data = f.read()

    new_data = tmpl_data.replace("eq BL = nilBaseLine .", f"eq BL = {bl_str} .")
    with open(out_maude_file, "w") as f:
        f.write(new_data)

    print(f"SUCCESS: Created {out_maude_file} ({len(new_data.splitlines())} lines)", flush=True)
    return True

def main():
    print(f"Targeting scenario2_isolated_plus_tgen in: {SCENARIO_DIR}", flush=True)
    success_count = 0
    for proto in PROTOCOLS:
        if process_protocol(proto):
            success_count += 1
            
    print(f"\n==========================================", flush=True)
    print(f" Completed {success_count}/{len(PROTOCOLS)} baseline experiments successfully.", flush=True)
    print(f"==========================================", flush=True)

if __name__ == "__main__":
    main()
