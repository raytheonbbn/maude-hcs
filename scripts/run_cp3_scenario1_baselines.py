#!/usr/bin/env python3
"""
Script to generate and run baseline experiments for CP3 scenario 1 or 2,
run multiple trials with distinct random seeds,
and combine the results into a single BL equation.
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
GEN_SCRIPT = os.path.join(REPO_ROOT, "scripts", "generate_cp3_v3.py")
DEFAULT_ECDF_SIZE_LIMIT = 10_000


def configure_scenario(scenario_number, combo=None):
    """Configure paths and file stems for the selected CP3 scenario."""
    global SCENARIO_NUMBER, SCENARIO_DIR, YAML_PATH, BASELINES_DIR, LOGS_DIR
    global TMP_TEMPLATE_PATH, TEMP_OUT_PATH, OUT_MAUDE_FILE, BASELINE_STEM, TRIAL_STEM

    SCENARIO_NUMBER = scenario_number
    scenario_name = f"scenario{scenario_number}"
    file_stem = f"pwnd_cp3_scenario_{scenario_number}"
    SCENARIO_DIR = os.path.join(
        REPO_ROOT, "use-cases", "challenge-problem-3", "cp3_scenarios", scenario_name
    )
    YAML_PATH = os.path.join(SCENARIO_DIR, f"{file_stem}.yaml")
    BASELINES_DIR = os.path.join(SCENARIO_DIR, "baselines")
    LOGS_DIR = os.path.join(BASELINES_DIR, "logs")
    TMP_TEMPLATE_PATH = os.path.join(SCENARIO_DIR, f"{file_stem}-baseline-eq-tmp.maude")
    combo_suffix = f"-{combo}" if combo else ""
    TEMP_OUT_PATH = os.path.join(SCENARIO_DIR, f"{file_stem}-baseline-eq{combo_suffix}-temp.maude")
    OUT_MAUDE_FILE = os.path.join(SCENARIO_DIR, f"{file_stem}-baseline-eq{combo_suffix}.maude")
    BASELINE_STEM = f"{file_stem}-baseline"
    TRIAL_STEM = f"{BASELINE_STEM}{combo_suffix}"


configure_scenario(1)

sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "cp3_glue"))
from parse_baseline import parse_baseline, Bl, Baseline


def systematic_quantile_extraction(sorted_values, size_limit=DEFAULT_ECDF_SIZE_LIMIT):
    """Downsample sorted values at evenly spaced quantile ranks.

    When the limit is at least two, the first and last observations are
    retained. Intermediate observations are selected at the nearest evenly
    spaced rank. Values at or below the limit are returned unchanged.
    """
    if size_limit <= 0:
        raise ValueError("eCDF size limit must be greater than zero")

    num_values = len(sorted_values)
    if num_values <= size_limit:
        return list(sorted_values)
    if size_limit == 1:
        return [sorted_values[(num_values - 1) // 2]]

    source_span = num_values - 1
    target_span = size_limit - 1
    indices = [
        (i * source_span + target_span // 2) // target_span
        for i in range(size_limit)
    ]
    return [sorted_values[index] for index in indices]


def run_maude_task(maude_file, log_file, cwd, random_seed):
    """Execute one Maude trial with an explicit random seed."""
    try:
        maude_file = os.path.abspath(maude_file)
        if not os.path.isfile(maude_file):
            raise FileNotFoundError(f"Maude input file does not exist: {maude_file}")

        with open(log_file, "w") as f:
            result = subprocess.run(
                ["maude", f"-random-seed={random_seed}", maude_file],
                stdout=f,
                stderr=subprocess.STDOUT,
                check=False,
                cwd=cwd
            )
        if result.returncode != 0:
            return False, maude_file, f"Maude exited with status {result.returncode}"
        with open(log_file, "r") as f:
            log_content = f.read()
        load_error_markers = (
            "unable to locate file:",
            "contains one or more errors that could not be patched up",
            "is unusable due to unpatchable errors",
        )
        if any(marker in log_content for marker in load_error_markers):
            return False, maude_file, "Maude reported a file-load or module error; see the trial log"
        return True, maude_file, None
    except Exception as e:
        return False, maude_file, str(e)


def generate_baselines(baseline_time=10800.0, combo=None):
    """Step 1: Generate one baseline Maude file containing all VP/feature pairs."""
    print(
        f"\n[1/3] Generating the combined baseline file for scenario {SCENARIO_NUMBER} "
        f"(baselineTime={baseline_time})...",
        flush=True,
    )
    command = [
        sys.executable,
        GEN_SCRIPT,
        YAML_PATH,
        "--quatex",
        f"--baselineTime={baseline_time}"
    ]
    combo_flags = {
        "combo1": "--filterVpFeatCombos",
        "combo2": "--filterVpFeatCombos2",
        "top25": "--filterVpFeatTop25",
    }
    if combo:
        command.append(combo_flags[combo])
    res_gen = subprocess.run(command, capture_output=True, text=True)

    if res_gen.returncode != 0:
        print(f"Error generating combined baseline file:\n{res_gen.stderr}", flush=True)
        return False
    print(f"      Combined baseline file successfully generated in {SCENARIO_DIR}", flush=True)
    return True


def run_baseline_trials(baseline_time=10800.0, num_trials=10, max_workers=None):
    """Step 2: Run the combined VP/feature baseline once per trial."""
    print(f"\n[2/3] Setting up and executing {num_trials} combined baseline trials in parallel...", flush=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    base_filename = f"{BASELINE_STEM}-{baseline_time}.maude"
    base_path = os.path.join(SCENARIO_DIR, base_filename)
    if not os.path.isfile(base_path):
        print(f"Error: Combined baseline file not found: {base_path}", flush=True)
        return False

    with open(base_path, "r") as f:
        base_content = f.read()

    print(f"      Creating {num_trials} trial files; each trial contains every requested vantage point and feature...", flush=True)
    tasks = []
    for trial_idx in range(1, num_trials + 1):
        trial_filename = f"{TRIAL_STEM}-{baseline_time}_trial{trial_idx}.maude"
        trial_path = os.path.join(BASELINES_DIR, trial_filename)
        log_path = os.path.join(LOGS_DIR, f"{trial_filename}.log")

        # Trial files live one directory below the generated combined baseline.
        # Maude resolves sload paths relative to the file containing each sload,
        # so prepend ../ to paths copied from the scenario directory.
        relocated_lines = []
        for line in base_content.splitlines(keepends=True):
            stripped = line.lstrip()
            if stripped.startswith("sload "):
                indent = line[:len(line) - len(stripped)]
                line = f"{indent}sload ../{stripped[len('sload '):]}"
            relocated_lines.append(line)
        relocated_content = "".join(relocated_lines)
        trial_content = relocated_content.replace("initState(counter)", f"initState({trial_idx})")
        with open(trial_path, "w") as f:
            f.write(trial_content)

        # The combined file's sload paths are relative to SCENARIO_DIR.
        tasks.append((trial_path, log_path, SCENARIO_DIR, trial_idx))

    print(f"      Running {len(tasks)} trial tasks with ProcessPoolExecutor (max_workers={max_workers})...", flush=True)
    t0 = time.time()
    completed_count = 0
    failed_count = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(run_maude_task, maude_path, log_path, cwd, random_seed)
            for maude_path, log_path, cwd, random_seed in tasks
        ]
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


def combine_trials_and_build_equation(
    baseline_time=10800.0,
    num_trials=10,
    ecdf_size_limit=DEFAULT_ECDF_SIZE_LIMIT,
):
    """Step 3: Parse baseline trial logs, combine distributions across trials, and write equation files."""
    print(f"\n[3/3] Parsing trial outputs and combining distributions...", flush=True)

    if not os.path.exists(LOGS_DIR):
        print(f"Error: Logs directory {LOGS_DIR} does not exist!", flush=True)
        return False

    base_stem = f"{TRIAL_STEM}-{baseline_time}"
    log_files = [f"{base_stem}_trial{i}.maude.log" for i in range(1, num_trials + 1)]
    missing_logs = [f for f in log_files if not os.path.isfile(os.path.join(LOGS_DIR, f))]
    if missing_logs:
        print(f"Error: Missing {len(missing_logs)} expected combined-trial log(s) in {LOGS_DIR}!", flush=True)
        for fn in missing_logs[:5]:
            print(f"      Missing: {fn}", flush=True)
        return False

    print(f"      Parsing {len(log_files)} log files...", flush=True)
    combo_bls = defaultdict(list)
    parsed_params = None
    expected_combo_keys = None

    for fn in log_files:
        log_path = os.path.join(LOGS_DIR, fn)
        with open(log_path, "r") as f:
            log_content = f.read()

        try:
            bl_obj = parse_baseline(log_content)
        except Exception as e:
            print(f"      Error: could not parse {fn}: {e}", flush=True)
            return False

        combo_keys = {(b.vantage, b.feat) for b in bl_obj.bls}
        if expected_combo_keys is None:
            expected_combo_keys = combo_keys
            parsed_params = bl_obj.params
        else:
            if combo_keys != expected_combo_keys:
                missing = sorted(expected_combo_keys - combo_keys)
                unexpected = sorted(combo_keys - expected_combo_keys)
                print(f"      Error: {fn} does not contain the same feature/vantage combinations as the first trial.", flush=True)
                if missing:
                    print(f"      Missing combinations: {missing[:5]}", flush=True)
                if unexpected:
                    print(f"      Unexpected combinations: {unexpected[:5]}", flush=True)
                return False
            if bl_obj.params != parsed_params:
                print(f"      Error: {fn} has baseline parameters that differ from the first trial.", flush=True)
                return False

        for b in bl_obj.bls:
            combo_bls[(b.vantage, b.feat)].append(b)

    if not combo_bls:
        print("Error: No baseline entries could be parsed from logs!", flush=True)
        return False

    # Combine distributions for each (vantage, feat) combination
    combined_bl_list = []
    for (vantage, feat), bl_list in sorted(combo_bls.items()):
        if len(bl_list) != num_trials:
            print(
                f"Error: ({vantage}, {feat}) has {len(bl_list)} baseline results; "
                f"expected {num_trials}.",
                flush=True,
            )
            return False

        # Average the k value across all trials for this combo
        avg_k = sum(b.k for b in bl_list) / len(bl_list)

        # Merge and sort all empirical CDF values across trials, then retain
        # evenly spaced quantiles if the merged distribution exceeds the cap.
        merged_ecdf = sorted([val for b in bl_list for val in b.ecdf])
        combined_ecdf = systematic_quantile_extraction(merged_ecdf, ecdf_size_limit)

        combined_bl_list.append(Bl(feat=feat, vantage=vantage, k=avg_k, ecdf=combined_ecdf))

    # Format the combined baseline equation
    bl_str = " :; ".join(map(str, combined_bl_list))
    equation_str = f"eq BL = ( {bl_str} ) ."

    # Read template file
    template_path = TMP_TEMPLATE_PATH if os.path.exists(TMP_TEMPLATE_PATH) else TEMP_OUT_PATH
    if not os.path.exists(template_path):
        # Fallback template if neither exists
        tmpl_data = (
            "sload ../../../../maude_hcs/lib/smc/smc-baseline-shared\n\n\n"
            f"mod PWND-CP3-SCENARIO-{SCENARIO_NUMBER}-BASELINE-EQ is\n"
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

    # Write the selected scenario's temporary baseline equation.
    with open(TEMP_OUT_PATH, "w") as f:
        f.write(new_data)
    print(f"      Wrote combined BL equation to {TEMP_OUT_PATH} ({len(combined_bl_list)} combinations, {len(new_data.splitlines())} lines).", flush=True)

    # Also write the selected scenario's standard baseline equation.
    with open(OUT_MAUDE_FILE, "w") as f:
        f.write(new_data)
    print(f"      Wrote combined BL equation to {OUT_MAUDE_FILE}.", flush=True)

    return True


def main():
    parser = argparse.ArgumentParser(description="Generate and run CP3 Scenario 1 or 2 baselines with multiple trials.")
    scenario_group = parser.add_mutually_exclusive_group()
    scenario_group.add_argument(
        "--scenario1", "--secnario1", dest="scenario", action="store_const", const=1,
        help="Run the Scenario 1 experiment (default)",
    )
    scenario_group.add_argument(
        "--scenario2", "--scenarion2", dest="scenario", action="store_const", const=2,
        help="Run the Scenario 2 experiment",
    )
    parser.set_defaults(scenario=1)
    parser.add_argument(
        "--combo", choices=("combo1", "combo2", "top25"), default=None,
        help="Vantage-point/feature combination filter to apply during generation",
    )
    parser.add_argument("--baselineTime", type=float, default=10800.0, help="Baseline time duration (default: 10800.0)")
    parser.add_argument(
        "--trials", "--trails", "--numTrials", dest="num_trials", type=int, default=10,
        help="Number of combined baseline trials (default: 10)",
    )
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel worker processes (default: CPU count)")
    parser.add_argument(
        "--ecdfSizeLimit", type=int, default=DEFAULT_ECDF_SIZE_LIMIT,
        help=f"Maximum merged eCDF elements per feature/vantage pair (default: {DEFAULT_ECDF_SIZE_LIMIT})",
    )
    parser.add_argument("--skipGen", action="store_true", help="Skip baseline generation step")
    parser.add_argument("--skipRun", action="store_true", help="Skip running trials (only re-combine logs)")
    args = parser.parse_args()
    if args.num_trials <= 0:
        parser.error("--trials must be greater than zero")
    if args.ecdfSizeLimit <= 0:
        parser.error("--ecdfSizeLimit must be greater than zero")
    configure_scenario(args.scenario, args.combo)

    print(f"==================================================", flush=True)
    print(f" Scenario {SCENARIO_NUMBER} Parallel Baseline Pipeline", flush=True)
    print(f" Directory: {SCENARIO_DIR}", flush=True)
    print(f" Combo: {args.combo or 'all'}", flush=True)
    print(f" Trials: {args.num_trials} | Duration: {args.baselineTime}s", flush=True)
    print(f"==================================================", flush=True)

    # 1. Generate the combined baseline
    if not args.skipGen:
        if not generate_baselines(baseline_time=args.baselineTime, combo=args.combo):
            sys.exit(1)
    else:
        print("[1/3] Skipping baseline generation (--skipGen set).", flush=True)

    # 2. Run trials
    if not args.skipRun:
        if not run_baseline_trials(baseline_time=args.baselineTime, num_trials=args.num_trials, max_workers=args.workers):
            print("Error: One or more baseline trial runs failed; baseline logs will not be combined.", flush=True)
            sys.exit(1)
    else:
        print("[2/3] Skipping baseline trial execution (--skipRun set).", flush=True)

    # 3. Combine and generate BL equation
    if not combine_trials_and_build_equation(
        baseline_time=args.baselineTime,
        num_trials=args.num_trials,
        ecdf_size_limit=args.ecdfSizeLimit,
    ):
        sys.exit(1)

    print(f"\n==================================================", flush=True)
    print(f" Scenario {SCENARIO_NUMBER} Baselines Successfully Generated & Combined!", flush=True)
    print(f" Output equation file: {TEMP_OUT_PATH}", flush=True)
    print(f"==================================================", flush=True)


if __name__ == "__main__":
    main()
