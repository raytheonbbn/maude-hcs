# Parse configurations baseline and run 
```bash
python generate_cp3_v3.py ../use-cases/challenge-problem-3/cp3_scenarios/scenario1/pwnd_cp3_scenario_1.yaml --parallelizeBaseline --filterVpFeatCombos --quatex

python generate_cp3_v3.py ../use-cases/challenge-problem-3/cp3_scenarios/scenario2/pwnd_cp3_scenario_2.yaml --parallelizeBaseline --filterVpFeatCombos --quatex

 python generate_cp3_v3.py ../use-cases/challenge-problem-3/cp3_scenarios/scenario1/pwnd_cp3_scenario_1.yaml --parallelizeBaseline --filterVpFeatCombos --quatex --confidentiality --baselineTime=3610
```
For performance only runs we add ` --notgens --perf`, where
    * `--perf` disables baseline actor and adversary collections and only produces perf queries in quatex
    * `--confidentiality` produces confidentiality queries in quatex
    * `--notgens` disables tgens (doesnt start them)

# Run baselines

After generating baselines for certain duration, 
```bash
python run_parallel_maudes.py ../../use-cases/challenge-problem-3/cp3_scenarios/scenario1/baselines/

python run_parallel_maudes.py ../../use-cases/challenge-problem-3/cp3_scenarios/scenario2/baselines/
```


# Parse baseline outputs to produce bl-eq
```bash
python parse_baseline.py ../../use-cases/challenge-problem-3/cp3_scenarios/scenario1/baselines/logs/ ../../use-cases/challenge-problem-3/cp3_scenarios/scenario1/baselines/logs/ -m ../../use-cases/challenge-problem-3/cp3_scenarios/scenario1/baselines/baseline-combined.maude

python parse_baseline.py ../../use-cases/challenge-problem-3/cp3_scenarios/scenario2/baselines/logs/ ../../use-cases/challenge-problem-3/cp3_scenarios/scenario2/baselines/logs/ -m ../../use-cases/challenge-problem-3/cp3_scenarios/scenario2/baselines/baseline-combined.maude
```

# Run SMC
```bash
time maude-hcs --verbose scheck --query=use-cases/challenge-problem-3/cp3_scenarios/scenario1/pwnd_cp3_scenario_1-quatex.maude --file=maude_hcs/lib/smc/smc_cp3.maude  --test=use-cases/challenge-problem-3/cp3_scenarios/scenario1/pwnd_cp3_scenario_1-run.maude -j 0 -n 4-4
```

```bash
time maude-hcs --verbose scheck --query=/home/dylan-l/maude-hcs/use-cases/challenge-problem-3/cp3_scenarios/scenario1/pwnd_cp3_scenario_1-quatex.maude --test=/home/dylan-l/maude-hcs/use-cases/challenge-problem-3/cp3_scenarios/scenario1/pwnd_cp3_scenario_1-run.maude --file=/home/dylan-l/maude-hcs/maude_hcs/lib/smc/smc_cp3.maude -n 250-250 -j 0  --dump=dump.log --format=json &> smc.log && touch Done
```
