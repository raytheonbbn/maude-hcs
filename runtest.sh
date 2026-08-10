#!/bin/bash

set -euo pipefail
rootdir=/Users/lwest/Documents/pwnd2/playground-maude-hcs

maude-hcs scheck \
    --file $rootdir/maude_hcs/lib/smc/smc_cp3.maude \
    --test $rootdir/use-cases/challenge-problem-3/cp3_scenarios/scenario1/scenario1.maude \
    --query $rootdir/test.quatex \
    --dump $rootdir/dump.txt \
    --format json \
    -j 1 -n 1-1 \

    # --test $rootdir/use-cases/challenge-problem-3/cp3_scenarios/scenario1/only_webtunnel.maude \
