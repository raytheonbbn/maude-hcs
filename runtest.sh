#!/bin/bash

set -euo pipefail
rootdir=/Users/lwest/Documents/pwnd2/playground-maude-hcs

python3 ./scripts/cp3_glue/generate_quatex.py test.quatex
dumpdir=$(python3 ./scripts/cp3_glue/mk_dump_dir.py dumps/dump)
# dumpdir=./dumps/dump2026-08-11_13-56-04

maude-hcs scheck \
    --file $rootdir/maude_hcs/lib/smc/smc_cp3.maude \
    --test $rootdir/use-cases/challenge-problem-3/cp3_scenarios/scenario1/scenario1.maude \
    --query $rootdir/test.quatex \
    --dump $dumpdir/dump.txt \
    -j 1 -n 1 \
    | tee log.txt

cat $dumpdir/dump.txt.* > $dumpdir/combined_dump.txt
rm $dumpdir/dump.txt.*

python3 ./scripts/cp3_glue/format_for_tne_v2.py \
    --smc-results-file log.txt \
    --quatex-file test.quatex \
    --perf-output-file perf.json \
    --adv-output-file adv.json \
    --perf-stats-output-file perf_stats.json \
    --adv-stats-output-file adv_stats.json \
    --dump-file $dumpdir/combined_dump.txt \
    --sample-output-dir samples \
