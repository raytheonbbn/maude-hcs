#!/bin/bash
# Loop from 1 to 12 for each scenario
for i in {1..2}
do
    echo "Running scenario $i..."

    maude-hcs scheck \
        --test="./use-cases/challenge-problem-2/cp2_scenarios_noloss_remote/cp2_scenario_$i.maude" \
        --query="./smc/cp2_eval_cp2_scenario_$i.quatex" \
        --format json -j 0 -n 30-100 > "./results/scenario_$i.json"

    echo "Finished scenario $i."
    echo "-----------------------------------"
done