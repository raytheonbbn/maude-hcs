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
maude-hcs scheck --test ./use-cases/challenge-problem-2/cp2_scenarios_final/results-initconf/cp2_scenario_1.maude --query ./smc/cp2_eval_cp2_scenario_1.quatex -j 0 -n 30-120
```

You should see the model's statistical guarantees for all the 
properties printed at the end of the console similar to this output.
If the output is similar, warnings can be safely ignored.

```bash
Number of simulations = 120
Query 1 (./smc/cp2_eval_cp2_scenario_1.quatex:12:1)
  μ = 203.07319783411302        σ = 17.695717823627948        r = 3.198634801115041
Query 2 (./smc/cp2_eval_cp2_scenario_1.quatex:13:1)
  μ = 540.333243246286          σ = 48.29469848968358         r = 8.72963192779875
Query 3 (./smc/cp2_eval_cp2_scenario_1.quatex:22:1)
  μ = 5.733333333333333         σ = 0.7849152527649013        r = 0.2930921722174493
Query 4 (./smc/cp2_eval_cp2_scenario_1.quatex:28:1) (53 simulations)
  μ = 9.275                     σ = 1.0374401434695155        r = 0.33178945427671425
  where 50 executions out of 103 (48.54%) have been discarded
Query 5 (./smc/cp2_eval_cp2_scenario_1.quatex:31:1)
  μ = 2.3333333333333335        σ = 0.6064784348631225        r = 0.22646276938933754
Query 6 (./smc/cp2_eval_cp2_scenario_1.quatex:39:1)
  μ = 126.25094189535513        σ = 8.902630389864715         r = 1.6092177593645356
Query 7 (./smc/cp2_eval_cp2_scenario_1.quatex:45:1) (53 simulations)
  μ = 209.05335071610008        σ = 23.97517525477567         r = 6.6083767357176875
  where 67 executions out of 120 (55.83%) have been discarded
Query 8 (./smc/cp2_eval_cp2_scenario_1.quatex:48:1)
  μ = 56.416615700181204        σ = 5.468903497570906         r = 0.9885456597817559
Query 9 (./smc/cp2_eval_cp2_scenario_1.quatex:54:1)
  μ = 1.0                       σ = 0.0                       r = 0.0
Query 10 (./smc/cp2_eval_cp2_scenario_1.quatex:55:1)
  μ = 0.4                       σ = 0.4982728791224398        r = 0.18605815084444596
Query 11 (./smc/cp2_eval_cp2_scenario_1.quatex:56:1)
  μ = 1.0                       σ = 0.0                       r = 0.0
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

#### Main Result 1: Privacy-Performance Trade-off Analysis 

We quantify undetectability–performance tradeoffs across three
representative scenarios (Scenarios 1, 4, and 7), which differ in
network loss and background traffic intensity (Table 1 in the paper)
and show the KL-divergence results in Figure 3 of the paper.

x-axis in Figure 3 is goodput while y-axis is KL-divergence lower bound.
As goodput increases we see a trend where undetectability decreases i.e. 
KL divergence lower bound increases. 

To generate the statistical guarantees along with the samples for
scenarios 1,4,and 7 as in the paper, with min number of simulations 30
and max number of simulations 120, run
```bash
cd $MAUDEHCSHOME/scripts
python run_cp2_demo.py ../use-cases/challenge-problem-2/cp2_scenarios/ ../results-popets/ 1 300 300
python run_cp2_demo.py ../use-cases/challenge-problem-2/cp2_scenarios/ ../results-popets/ 4 300 300
python run_cp2_demo.py ../use-cases/challenge-problem-2/cp2_scenarios/ ../results-popets/ 7 300 300
```
The results are under the `../results-popets` directory.
The .json file per scenario has the statistical guarantees.
The raw samples are also included per scenario, one file per thread.
We combine these samples to generate the CDF.

To generate the scalability results of Figure 3,
```bash
cd $MAUDEHCSHOME
python scripts/scalability_popets.py ../use-cases/challenge-problem-2/
python scripts/scalability_popets_slimit.py ../use-cases/challenge-problem-2/
```

You can modify the number of simulations to `300-300` in the scalability_popets.py scripts
to increase confidence (to reproduce the paper results). And you can specify which set 
scenarios of scenarios to run 
```python
#NSIMS = "30-30" # min-max number of monte carlo samples
NSIMS = "300-300"

run_scenario= { 1,4,7,10 } 
#run_scenario= { 1} 
```

This generates the raw data for scenario 1,4,7,10 as in the paper.
Then to generate the main Figure 3,
```bash
cd $MAUDEHCSHOME
mkdir results-popets-tradeoff/
cp results-popets/*_cli_wait*.json results-popets-tradeoff/
python scripts/plot_pets_tradeoff.py results-popets-tradeoff/
```
The results will be saved in `results-popets-tradeoff/plotsv2/`

NOTE: if `sed` commands fail, modify the commands to remove the empty string
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