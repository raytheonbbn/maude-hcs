These scripts are glue code for generating quatex queries, running SMC on a maude scenario
using those queries, and formatting the results to be consistent with what the T&E team is expecting.

This directory also includes parse_baseline.py, which is not as directly involved in the above pipeline.

# How to use

## Step 1: Copy in constants to generate_quatex.py

`generate_quatex.py` uses several constants when generating queries:

    ```
    WINDOW_SIZE
    SLIDING_WINDOW_SIZE
    BIN_SIZE
    HCS_DELAY
    MAX_WIN
    VANTAGES
    CLIENTS
    FEATS
    ```

These should be the same constants used in the scenario, so they should be copied and pasted in from the relevant maude files.

In particular:
- `VANTAGES` should include all the `NetId`s in the `visibilityMap` from `visibilityMap.maude`, as well as `ixpN`.
- `CLIENTS` should include all the addresses assigned to `allClientsAddr` in the scenario file, paired with what T&E call that client (`CLIENTS` is a dictionary)
- `FEATS` should include all features you want to measure in the scenario, paired with what T&E call that feature (`FEATS` is a dictionary)

Additionally, if you want to adjust how clients are named in perf json outputs, add the desired mappings to `CLIENT_MAP`.

For example, if you want to rename `wtCl2IrcAddr` to `alice_1`, then you should add `"wtCl2IrcAddr": "alice_1"` to `CLIENT_MAP`.

## Step 1.5: Turn off printing

If printing is enabled, it can slow down the SMC or mess with the log, so make sure `set print attribute on .` is commented out.

## Step 2: Generate quatex file

Just run the `generate_quatex.py` script with the desired path of the quatex file as an argument.

## Step 3: Set up dump directory

All the dump files from an SMC run need their own directory for the formatter to work, so make a directory to hold them.

For convenience, `mk_dump_dir.py` will automatically create a dump directory matching its argument, but with a timestamp appended
to avoid clobbering previous runs.

## Step 4: Run `maude-hcs scheck` and capture log

Make sure to pass it the quatex query file you just generated and the dump directory you just made.

I recommend using `| tee log.txt` so you can see the log being captured.

## Step 5: Concatenate dump files

The formatter expects a single dump file, but if you run SMC with multiple threads it will output one dump file per thread.

Concatenate them all into a single dump file.

## Step 5: Run the formatter

The formatter takes a lot of arguments:
    
> `smc-results-file` is the SMC log that you captured
> `quatex-file` is the file containing generated quatex queries
> `perf-output-file` is the desired filename for the performance json output
> `adv-output-file` is the same, but for adversary features
> `perf-stats-output-file` is similar to `perf-output-file`, but the result will additionally contain a radius and standard deviation
> `adv-stats-output-file` is similar, but for adversary
> `dump-file` is where the concatenated SMC dumped samples were stored
> `sample-output-dir` is where you want to store the json sample files extracted from the dump file.

## All together

See the script below for an example of running the whole pipeline in sequence.

``` bash
#!/bin/bash

set -euo pipefail
rootdir=/Users/lwest/Documents/pwnd2/playground-maude-hcs

python3 ./scripts/cp3_glue/generate_quatex.py test.quatex
dumpdir=$(python3 ./scripts/cp3_glue/mk_dump_dir.py dumps/dump)

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
```

# How to use `parse_baseline.py`

`python3 parse_baseline.py BASELINE_PATH OUTPUT_DIRECTORY [--maude-output-file FILE] [--scenario STRING]`

If `BASELINE_PATH` points to a directory, all the files inside that directory will be parsed as baseline logs and combined.
