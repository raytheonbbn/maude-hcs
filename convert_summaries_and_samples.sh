#!/bin/bash

# Run this from repo root

set -euox pipefail

dumpdir="FILL THIS IN WITH WHERE SMC PUT DUMP FILES"
tne_output_dir="FILL THIS IN WITH A DIR WHERE YOU WANT THE T&E FORMATTED FILES TO GO" \

# Concatenate dump files
cat $dumpdir/dump.txt.* > $dumpdir/combined_dump.txt

# All the json arguments below can be changed as well to adjust where the tne-formatted results go,
# these arguments have them all getting dumped in the tne output directory
python3 ./scripts/cp3_glue/format_for_tne_v2.py \
    --smc-results-file "FILL THIS IN WITH WHERE YOU PIPED SMC LOG" \
    --quatex-file "FILL THIS IN WITH QUATEX FILE THE SMC RUN USED" \
    --perf-output-file $tne_output_dir/perf.json \
    --adv-output-file $tne_output_dir/adv.json \
    --perf-stats-output-file $tne_output_dir/perf_stats.json \
    --adv-stats-output-file $tne_output_dir/adv_stats.json \
    --dump-file $dumpdir/combined_dump.txt \
    --sample-output-dir $tne_output_dir
