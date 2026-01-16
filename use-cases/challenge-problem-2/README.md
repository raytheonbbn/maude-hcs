# Step 1
Generate the markov models for raceboat (make sure to use the new format),
```shell
 maude-hcs --verbose     --protocol=mastodon markov     \
    --json-dir=./use-cases/challenge-problem-2/spot-check-1/actions/ \
    --maude-dir=./maude_hcs/lib/raceboat/maude/mastodonprofiles/
```

# Step 2
Generate the scenario maude models for analysis,
```shell
 maude-hcs --verbose  generate \
   --yml-filename=./use-cases/challenge-problem-2/spot-check-1/spot_check_1.yml  
   --model=prob \
   --filename=spot_check_1
```

# Step 3
Run statistical model checking