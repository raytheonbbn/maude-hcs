#!/bin/bash
# Loop from 1 to 12 for each scenario
for i in {1..12}
do
    echo "Annotating scenario $i results..."

    python annotateResults.py \
      "../use-cases/challenge-problem-2/cp2_scenarios_noloss_remote/results/scenario_$i.json" \
       "../smc/"

    echo "Finished scenario $i."
    echo "-----------------------------------"
done