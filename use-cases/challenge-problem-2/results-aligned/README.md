```bash
# To generate the comparison plots per query across scenarios 
python scripts/plotfinal.py use-cases/challenge-problem-2/results-aligned/ use-cases/challenge-problem-2/cp2_scenarios_tne/cp2_te_results/ smc/ 
# To generate the CDF plots 
python scripts/gather_samples.py use-cases/challenge-problem-2/results-aligned/samples/ use-cases/challenge-problem-2/results-aligned/cdfs use-cases/challenge-problem-2/cp2_scenarios_tne/cp2_te_results/
```