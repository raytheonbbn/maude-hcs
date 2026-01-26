#!/bin/bash
# Loop from 1 to 12 for each scenario
for i in {1..12}
do
    echo "Annotating scenario $i results..."

    python annotateResults.py \
      "../results/cp2_scenario_${i}_cdf.json" \
       "../smc/"

    echo "Finished scenario $i."
    echo "-----------------------------------"
done