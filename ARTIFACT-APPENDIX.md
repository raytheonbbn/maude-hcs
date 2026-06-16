# Artifact Appendix

Paper title: Maude-HCs: Model Checking the Undetectability-Performance Tradeoffs of Hidden Communication Systems

Requested Badge(s):
  - [x] **Available**
  - [x] **Functional**
  - [x] **Reproduced**


## Description

### Paper title 
Maude-HCs: Model Checking the Undetectability-Performance Tradeoffs of Hidden Communication Systems

### Authors and Affiliations:

 * Dr. Joud Khoury (RTX BBN Technologies) <joud.khoury@rtx.com>
 * Dr. Minyoung Kim (SRI International) <minyoung.kim@sri.com>
 * Dr. Christophe Merlin (RTX BBN Technologies) <christophe.merlin@rtx.com>
 * Dr. Jose Meseguer (University of Illinois at Urbana-Champaign) <meseguer@illinois.edu>
 * Dr. Zachary Ratliff (Harvard University) <zacharyratliff@g.harvard.edu>
 * Dr. Carolyn Talcott (SRI International) <carolyn.talcott@sri.com>

### Description 

Reproduce all quantitative results in the paper.

### Distribution Statement

DISTRIBUTION STATEMENT A: Approved for public release; distribution is unlimited.
This document does not contain technology or technical data controlled under either the U.S. International Traffic in Arms Regulations or the U.S. Export Administration Regulations.
This material is based upon work supported by the Defense Advanced Research Projects Agency
(DARPA) under Agreement No. HR00112590083

### Security/Privacy Issues and Ethical Concerns

None

## Basic Requirements

### Hardware Requirements

Can run on a laptop (No special hardware requirements)

### Software Requirements (Required for Functional and Reproduced badges)

1. OS: Any OS with a python interpreter. Tested on Ubuntu 22.04, and OSX
2. Packages: Conda with python interpreter
3. Artifact packaging: Python environment (venv or conda)
4. Interpreter: Python >=3.12.4
5. Dependencies: refer to pyproject.toml for python package versions
6. Machine Learning Models: N/A
7. Datasets: included in artifact

### Estimated Time and Storage Consumption 

Compute time: 1 hr

Disk space: 100 MB

## Environment

### Accessibility

Maude-HCS repo: https://github.com/raytheonbbn/maude-hcs/tree/cp2.eval.paper

DNS Formalization repo: https://github.com/raytheonbbn/dns-formalization-maude/tree/pwnd.43.rb1

### Set up the environment

Setup instructions provided below.
these are directly extracted from the main [./README.md](README).
You can replace conda with other virtual environments if you choose.

```bash
conda create --name popets python=3.12.4
conda activate popets
git clone -b cp2.eval.paper https://github.com/raytheonbbn/maude-hcs
cd maude-hcs
mkdir -p maude_hcs/deps
git submodule add -b pwnd.43.rb1 -f git@github.com:raytheonbbn/dns-formalization-maude.git maude_hcs/deps/dns_formalization
cd maude_hcs/deps/dns_formalization
git sparse-checkout init --cone
git sparse-checkout set "Maude/dns" "Maude/common" "Maude/test" "Maude/attack_exploration"
cd ../../../
git reset .gitmodules
git reset maude_hcs/deps/dns_formalization
```
Now that we have all the sources, install in the current env
```bash
cd maude_hcs/deps/dns_formalization
pip install -e .
cd ../../../
pip install -e .
```

Set MAUDEHCSHOME to the home directory where maude-hcs is installed
```bash
export MAUDEHCSHOME=$(pwd)
```

### Testing the Environment

To test your configuration, run a scenario (scenario 1 in this example)

```bash
maude-hcs scheck --test ./use-cases/challenge-problem-2/cp2_scenarios/cp2_scenario_1.maude --query ./smc/cp2_eval_cp2_scenario_1.quatex -j 0 -n 30-120
```

You should see the model's statistical guarantees for all the 
properties printed at the end of the console similar to this output.
If the output is similar, warnings can be safely ignored.

```bash
Number of simulations = 120
Query 1 (./smc/cp2_eval_cp2_scenario_1.quatex:12:1)
  μ = 202.6437356465193         σ = 17.229579146816842        r = 3.1143767106179787
Query 2 (./smc/cp2_eval_cp2_scenario_1.quatex:13:1)
  μ = 541.1700405553873         σ = 45.69039290200721         r = 8.258884000616208
Query 3 (./smc/cp2_eval_cp2_scenario_1.quatex:22:1)
  μ = 5.966666666666667         σ = 0.9278574999588494        r = 0.34646768452166277
Query 4 (./smc/cp2_eval_cp2_scenario_1.quatex:28:1)
  μ = 3.1666666666666665        σ = 0.9128709291752772        r = 0.34087160702211733
Query 5 (./smc/cp2_eval_cp2_scenario_1.quatex:31:1)
  μ = 2.2666666666666666        σ = 0.5832922809856749        r = 0.21780491724368095
Query 6 (./smc/cp2_eval_cp2_scenario_1.quatex:39:1)
  μ = 125.18704558671165        σ = 9.316476814793546         r = 1.6840236299309668
Query 7 (./smc/cp2_eval_cp2_scenario_1.quatex:45:1)
  μ = 71.82447470969723         σ = 12.089508366235552        r = 2.1852700508695406
Query 8 (./smc/cp2_eval_cp2_scenario_1.quatex:48:1)
  μ = 55.833282337650544        σ = 5.588605607588547         r = 1.0101827212836119
Query 9 (./smc/cp2_eval_cp2_scenario_1.quatex:54:1)
  μ = 1.0                       σ = 0.0                       r = 0.0
Query 10 (./smc/cp2_eval_cp2_scenario_1.quatex:55:1)
  μ = 1.0                       σ = 0.0                       r = 0.0
Query 11 (./smc/cp2_eval_cp2_scenario_1.quatex:56:1)
  μ = 1.0  
```

The 11 statistical queries (properties) are defined in the
quatex file we just ran [./smc/cp2_eval_cp2_scenario_1.quatex](cp2_eval_cp2_scenario_1.quatex).
Maude-HCS provides a statistical guarantee for each of these quantitative 
properties as you see above with expected value, and standard deviation, 
and confidence radius.

## Artifact Evaluation (Required for Functional and Reproduced badges)

### Main Results and Claims

List all your paper's results and claims that are supported by your submitted
artifacts.

#### Main Result 1: Semantic Alignment
The first main result is demonstrating that our model results transfer
to real testbed empirical results attesting to the predictive power
of the Maude-HCS framework and models

To generate the statistical guarantees along with the samples for
scenarios 1 through 9 with min number of simulations 120
and max number of simulations 120, runistory
```bash
cd $MAUDEHCSHOME/scripts
python run_cp2_demo.py ../use-cases/challenge-problem-2/cp2_scenarios/ ../results-popets/ 1-12 120 120
```
alternatively we can generate for each scenario individually, e.g., for scenario 4
```bash
python run_cp2_demo.py ../use-cases/challenge-problem-2/cp2_scenarios/ ../results-popets/ 4 120 120
```
Note that scenarios 3, 6, 9, and 12 take a long time (several hours) because of the large number
of traffic generators involved.
The time taken to run these scenarios depends on the number of samples being generated and is linear 
in the number of cores available on the machine. For example, if you are generating 120 samples 
and the machine has 128 cores, all samples will be generated by SMC in parallel in one shot since 
there are more cores than samples needed. The time to generate a sample (or N samples in parallel) 
is several hours. For scenarios 6/9/12, we expect the sample time to be about 3 hours; for scenario
6 we expect the sample time to be around 8 hours. So if you have 16 cores only, and request 64 samples
from SMC the time will be 64/16=4*(sample time) which in this case would be much larger.
We usually run these experiments on a 256 core (2 AMD EPYC processors) server overnight.

Another important note on Figure 7: in the final submitted version of the paper, we made enhancement 
that achieved better alignment for scenarios 3/6/9/12. These enhancements are on the main branch of 
the repository (as opposed to the cp2.eval.paper branch which dates back to March 1st)
https://github.com/raytheonbbn/maude-hcs

The `annotate_results` script first annotates the statistical estimates produced earlier
in the `results-popets` directory, effectively annotating each of the queries 
```bash
cd $MAUDEHCSHOME
cd scripts
./run_annotate_results.sh 
```
Then summarize the results
```bash
cd $MAUDEHCSHOME
python scripts/summarize_cp2.py results-popets/
```
This generates the summary.txt which is a summary of statistics by scenario.

The results are under the `../results-popets` directory.
The .json file per scenario has the statistical guarantees.
The raw samples are also included per scenario, one file per thread.
These raw samples are combined to generate CDF if needed (not in the paper).

We merge the summary.txt data with the testbed empirical data by hand to create a 
comparison file for plotting and regenerating Figure 7.
The following script auto merges the SMC results and empirical results to generate the
updated `comparison_mergd.csv` under results-popets

```bash
python scripts/cp2_merge_smc_tne.py results-popets/summary.txt use-cases/challenge-problem-2/cp2_scenarios_tne/metrics_summary.csv
```

The `plotfinal2` script compares these statistical estimates against empirical data 
from the testbed that was provided by an independent test and evaluation team.
The comparison plots are written to the local directory reproducing Figure 7.
You can verify the newly generated results in summary.txt match the results in 
this comparison file used by the plotfinalv2 script. 

The CDF generation `gather_samples` script produces CDFs and places then under 
`results-popets/cdfs`.
```bash
# First generate the comparison plots (Figure 7)
cd $MAUDEHCSHOME
python scripts/plotfinal2.py results-popets/ use-cases/challenge-problem-2 cp2_scenarios_tne/cp2_te_results/ smc/
# Generate the CDF plots if needed (not included in the paper)
python scripts/gather_samples.py results-popets/ results-popets/cdfs use-cases/challenge-problem-2/cp2_scenarios_tne/cp2_te_results/
```

#### Main Result 2: Privacy-Performance Trade-off Analysis 

We quantify undetectability–performance tradeoffs across three
representative scenarios (Scenarios 1, 4, and 7), which differ in
network loss and background traffic intensity (Table 1 in the paper)
and show the KL-divergence results in Figure 3 of the paper.

x-axis in Figure 3 is goodput while y-axis is KL-divergence lower bound.
As goodput increases we see a trend where undetectability decreases i.e. 
KL divergence lower bound increases. 

To generate the scalability results of Figure 3,
```bash
cd $MAUDEHCSHOME
python scripts/scalability_popets.py ../use-cases/challenge-problem-2/
python scripts/scalability_popets_c8.py ../use-cases/challenge-problem-2/
```
this places the results under `./results-popets` and `./results-popets-v2-c8-nx4`

You can modify the number of simulations to `300-300` in the scripts
to increase confidence (to reproduce the paper results). And you can specify which set 
scenarios of scenarios to run 
```python
#NSIMS = "30-30" # min-max number of monte carlo samples
NSIMS = "300-300"

run_scenario= { 1,4,7} 
#run_scenario= { 1} 
```

This generates the raw data for scenario 1,4,7 as in the paper.
Then to generate the main Figure 3, Figure 4, and Figure 5
```bash
cd $MAUDEHCSHOME
mkdir results-popets-tradeoff/
cp results-popets-v2-c8-nx4/*_cli_wait*.json results-popets-tradeoff/
python scripts/plot_pets_tradeoff.py results-popets-tradeoff/
cp results-popets/*_ma1_baseline*.json results-popets-tradeoff/
python scripts/plot_pets.py results-popets-tradeoff/ 5
python scripts/plot_pets_wait.py results-popets-tradeoff/
```
The results will be saved in `results-popets-tradeoff/plotsv2/` for per scenario plots
and `results-popets-tradeoff/plots/` and `results-popets-tradeoff/plots_wait/` for 
combined plots.

Specifically, Figure 3 results will be named `plotsv2/cp2_scenario_<x>_cli_wait_plot3_tradeoff.png`
where `<x>` is 1,4, or 7 for each of these experiments.
The shapes of these KL divergence plots will look a little different because they are statistical and depend on the sampling, but the takeaway is the same. 

The plot in Figure 4a is `plots/set2_AlarmMA1_kl.png`.

The plot in Figure 4b is `plots/set1_AlarmMA1.png`.

The plot in Figure 4c is `plots/set1_OpDurMA1.png`.

Figure 5 results are under `plots_wait/` as follows:

Figure 5a is `set2_AlarmC8_kl.png`

Figure 5b `set1_AlarmC8.png`.

Figure 5c is `set1_OpDurC8.png`.





#### Toubleshooting

NOTE: if `sed` commands fail in the scripts, modify the commands to remove the empty string
This is added for osx compatibility. Spoecifically replace
```python
_cmd = ["sed", "-i", "", "/--- applications/,/--- WMonitor/ s/^/--- /", tgenonly_fn]
```
with 
```python
_cmd = ["sed", "-i", "/--- applications/,/--- WMonitor/ s/^/--- /", tgenonly_fn]
```


## Limitations 

None