#!/bin/bash

set -euo pipefail

rootdir=/Users/lwest/Documents/pwnd2/playground-maude-hcs
sc1_dir=$rootdir/use-cases/challenge-problem-3/cp3_scenarios/scenario1/
maude_out=$sc1_dir/baseline.maude

# Generate small maude baselines, one per vantage point / feature pair
python3 ./scripts/generate_cp3_v3.py $sc1_dir/pwnd_cp3_scenario_1.yaml --parallelizeBaseline --baselineTime=20.0

# Run all the maude baselines
python3 ./scripts/cp3_glue/run_parallel_maudes.py $sc1_dir/baselines 

# combine all the baseline logs to produce vantage/feature jsons and a complete maude baseline actor
python3 ./scripts/cp3_glue/parse_baseline.py $sc1_dir/baselines/logs $sc1_dir/baselines/jsons -m $maude_out
