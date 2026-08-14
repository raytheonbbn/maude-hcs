#!/bin/bash

# Run this from repo root

# set -euox pipefail
set -euo pipefail

root_dir=/Users/lwest/Documents/pwnd2/playground-maude-hcs
scenario_dir=$root_dir/use-cases/challenge-problem-3/cp3_scenarios/scenario2

tne_output_dir=$scenario_dir/results_scenario2_7200_notgens_formatted
raw_results_dir=$scenario_dir/results_scenario2_7200_notgens_raw
dump_dir=$raw_results_dir/dumplogs

mkdir -p $tne_output_dir

# Concatenate dump files
cat $dump_dir/dump.log.* > $dump_dir/combined_dump.log

# All the json arguments below can be changed as well to adjust where the tne-formatted results go,
# these arguments have them all getting dumped in the tne output directory
python3 ./scripts/cp3_glue/format_for_tne_v2.py \
    --json-smc-results-file $raw_results_dir/smc.log \
    --quatex-file $raw_results_dir/short_scenario2.quatex \
    --perf-output-file $tne_output_dir/perf.json \
    --adv-output-file $tne_output_dir/adv.json \
    --perf-stats-output-file $tne_output_dir/perf_stats.json \
    --adv-stats-output-file $tne_output_dir/adv_stats.json \
    --dump-file $dump_dir/combined_dump.log \
    --sample-output-dir $tne_output_dir
