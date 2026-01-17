#!/bin/bash

# Loop from 1 to 12 for each scenario
for i in {1..12}
do
    echo "Running commands for scenario $i..."
    # Command 1: raceboat Markov generation
    maude-hcs --verbose --protocol=mastodon markov \
        --json-dir="../pwnd-cp2/cp2_scenarios/cp2_scenario_$i/actions/" \
        --maude-dir="./maude_hcs/lib/raceboat/maude/mastodonprofiles/"

    # Command 2: Generate maude init config
    maude-hcs --verbose generate \
        --yml-filename="../pwnd-cp2/cp2_scenarios/cp2_scenario_$i/cp2_scenario_$i.yml" \
        --model=prob \
        --filename="cp2_scenario_$i" \
        --output-dir="./use-cases/challenge-problem-2/cp2_scenarios/"

    echo "Finished scenario $i."
    echo "-----------------------------------"
done