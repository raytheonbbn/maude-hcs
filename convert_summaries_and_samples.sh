#!/bin/bash

# Run this from repo root

set -euo pipefail

root_dir=/Users/jkhoury/Documents/Research/BBN/weirdnets/code/maude-hcs-fresh
scenario_dir=$root_dir/use-cases/challenge-problem-3/cp3_scenarios/scenario2

tne_output_dir=$scenario_dir/scenario2_full_perf_formatted
raw_results_dir=$scenario_dir/scenario2_full_perf_raw
dump_dir=$raw_results_dir/dumplogs

scenario1_mapping=$(cat << 'EOF'
{
"wtCl1IrcAddr": "alice_1",
"wtCl2IrcAddr": "alice_2",
"skyCl3IrcAddr": "alice_3",
"skyCl4IrcAddr": "alice_4",
"obfsCl5IrcAddr": "alice_5",
"obfsCl6IrcAddr": "alice_6",
"iodCl7IrcAddr": "alice_7",
"iodCl8IrcAddr": "alice_8",
"masCl9IrcAddr": "alice_9"
}
EOF
)

scenario2_mapping=$(cat << 'EOF'
{
"wtCl1IrcAddr": "alice_1",
"skyCl2IrcAddr": "alice_2",
"obfsCl3IrcAddr": "alice_3",
"masCl4IrcAddr": "alice_4"
}
EOF
)

mkdir -p $tne_output_dir

# Concatenate dump files
cat $dump_dir/dump.log.* > $dump_dir/combined_dump.log

# All the json arguments below can be changed as well to adjust where the tne-formatted results go,
# these arguments have them all getting dumped in the tne output directory
python3 ./scripts/cp3_glue/format_for_tne_v2.py \
    --json-smc-results-file $raw_results_dir/smc.log \
    --quatex-file $raw_results_dir/pwnd_cp3_scenario_2-quatex.maude \
    --perf-output-file $tne_output_dir/perf.json \
    --adv-output-file $tne_output_dir/adv.json \
    --perf-stats-output-file $tne_output_dir/perf_stats.json \
    --adv-stats-output-file $tne_output_dir/adv_stats.json \
    --dump-file $dump_dir/combined_dump.log \
    --sample-output-dir $tne_output_dir \
    --mapping "$scenario2_mapping" \
    --scenario "scenario2-full"

