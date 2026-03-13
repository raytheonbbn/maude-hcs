# Maude-HCS

Maude-HCS is one of the first generalized and modular toolchains for specifying 
and reasoning about Hidden Communication Systems (HCS) at real-world scales. 
The Maude-HCS toolchain, comprised of a Domain Specific Language (DSL) and analysis toolkit, 
enables network designers to explore alternative HCS designs quickly and effectively 
and provides provable privacy-performance guarantees needed to trust the design — 
a necessary step for HCS users to ultimately trust the system, especially when operating 
in high threat environments where detection of illicit communication has dire consequences.

# Requirements
Requires python version `3.12.4`

If you use pyenv:

```bash
pyenv install 3.12.4
pyenv local 3.12.4
```

# Installation

Create your preferred environment:

## Conda
Create a conda env
```bash
conda create --name pwnd2 python=3.12.4
conda activate pwnd2
```

Then, install
``` bash
pip install -e .
```

## VIRTUALENV
```bash
python -m venv venv
source venv/bin/activate
```

## Install: from git source
We structured the repo source code so that 
we import dns-formalization-maude as a dependency (a submodule).
We created a fork of this dependency so that we can track our changes 
to it. 
We use sparse-checkout to avoid needing to checkout all the source of the 
dependency which includes many irrelevant files (such as Testbed).

First setup a new conda environment and activate it.

Clone the main repo
```shell
git clone git@github.com:raytheonbbn/maude-hcs.git
```
The main branch has the latest (possibly unstable) source.
Older branches/tags such as `pwnd.cp1` refer to stable snapshots used to produce results during evaluations (e.g., `pwnd.cp1` used for challenge problem 1, and similarly `pwnd.cp2`).
To use an older snapshot, checkout the specific branch (eg `pwnd.cp1`).

Setup the dns submodule using our clone of the code so we can track changes 
made to the original source, use sparse-checkout to keep only relevant sources
```shell
cd maude-hcs
mkdir -p maude_hcs/deps
git submodule add -b <branch> -f git@github.com:raytheonbbn/dns-formalization-maude.git maude_hcs/deps/dns_formalization
cd maude_hcs/deps/dns_formalization
git sparse-checkout init --cone
git sparse-checkout set "Maude/dns" "Maude/common" "Maude/test" "Maude/attack_exploration"
cd ../../../
git reset .gitmodules
git reset maude_hcs/deps/dns_formalization
```
In the command above set `<branch>` either to `pwnd.cp1` to reproduce challenge problem 1 results, 
or to `pwnd` for the latest version. 

The above should create a new file named sparse-checkout under .git/modules/maude_hcs/deps/dns_formalization/info/ 
and tell it to only include certain directories such as `Maude/src`.

At this point `git status` should show a clean start.

To install, first install the dependency as a package called dns, we import as `Maude.*`
then install the `maude_hcs` as a package (with dependency on dns).

```shell
cd maude_hcs/deps/dns_formalization
pip install -e .
cd ../../../
pip install -e .
```

# Auto generate user models

User models are markov models intended to represent how users behave.
These are given in json format. 
The first step is to convert these to formal maude representations.

To do so, specify the 
 - protocol: dns or mastodon 
 - input directory containing all the json models that you want to convert
 - output directory that will contain all the maude versions of the json models

For example,
```shell
# convert dns tgen user models
 maude-hcs --verbose \ 
    --protocol=dns markov \
    --json-dir=../pwnd-cp2/src/static/tgen_models/dns/ \ 
    --maude-dir=./maude_hcs/lib/tgen/maude/dnsprofiles/markov/
    
# convert mastodon tgen models
maude-hcs --verbose \
    --protocol=mastodon markov \
    --json-dir=../pwnd-cp2/src/static/tgen_models/mastodon \
    --maude-dir=./maude_hcs/lib/tgen/maude/mastodonprofiles/markov/
```

# Auto generate configurations

For now we can generate initial configurations using `generate` command.
HCS Configurations can be directly passed in json using HCS configuration parameters, 
or using a Shadow experiment configuration. Each of these is described next. 

## Using HCS json Configuration 
Pass a maude-hcs json configuration file as follows,

To generate a probabilistic DNS model config with iodine and specify the output filename,
```shell
 maude-hcs --verbose  generate --run-args=./results/generated_test_yml-hcsconfig.json     --model=prob --filename=generated_test_yml_2
```
Set `--model=nondet` to generate a nondeterministic version.

This produces the executable maude file (and the corresponding HCS config json) in the results/ directory.

See example [corporate-iodine-conf.json](./use-cases/corporate-iodine-conf.json) configuration file, and refer to [HCSParamsGuide](./HCSParamsGuide.md) for a description of the parameters.
Note that probabilistic model will combine the nondeterministic params as well as the 
probabilistic params (whic override the nondeterministic ones).

## Using a YML configuration
### Single configurations
A YML configuration contains the full config of the tunnels and undelying networks.
We can generate an HCS config directly from it.
```shell
 maude-hcs --verbose  generate --yml-filename=./use-cases/challenge-problem-2/cp2_setup_example.yml     --model=prob --filename=generated_test_yml
```

### Batched configurations of CP2
For batched configurations like the ones in CP2, convert multiple YML files to Maude scenario files:
```shell
 ./scripts/generate_cp2_maude.sh [scenario_dir]
```
Where `scenario_dir` is optional (defaults to `../pwnd_cp2`)

## Using Shadow yaml configuration
The network configuration can be specified using a shadow file instead of our HCS config json
(See [Shadow](https://github.com/shadow/shadow) simulator for more info on shadow specifications).

To generate a model that uses characteristics defined in a shadow file, specify:
```shell
--shadow-filename <path_to_shadow_file.yaml>
```
The shadow yaml file specifies the network, host, and process configurations.

Assuming the shadow network config is located in directory `../pwnd-cp1`, run
```shell
maude-hcs --verbose --protocol=dns generate --shadow-filename=../pwnd-cp1/shadow_files/examples/cp1_sim_config.yaml --model=prob --filename=generated_test_shadow
```
# Run configurations

## Standalone run with Maude
To run a single configuration, invoke maude with the file name, for instance, in `results`,
```shell
maude generated_corporate_iodine_prob.maude
```

Inside the Maude prompt, type
```shell
rew initConfig .
```
This will execute all rewrites until no more rules are found and no progress can be made in time.

The addition of logging will increase the verbosity of the execution with
```shell
set print attribute on .
```

Execution can also be stepped through with the following commands
```shell
rew[1] initConfig .
cont 1 .
```
## Statistical Model Checking

Statistical model checking is available by means of the scheck subcommand:
```shell
maude-hcs scheck [-h] [--advise] 
                 [--protocol {dns}] [--file FILE] [--test TEST] [--initial INITIAL] [--query QUERY] 
                 [--assign METHOD] [--alpha ALPHA] [--delta DELTA] 
                 [--seed SEED] [--jobs JOBS] [--format {text,json}]

options:
  --help, -h              Show help message and exit
  --advise                Do not suppress debug messages from Maude  
  --protocol PR           The protocol module being analyzed e.g., dns, which points to an smc file specific to that protocol. 
  --file FILE             Maude source file specifying the model-checking problem. If --protocol is specified, this parameter becomes optional, and if specified overrides the protocol smc file.
  --test TEST             Test generated from maude-hcs, default=results/generated_test.maude
  --initial INITIAL       Initial term, default=initConfig
  --query QUERY           QuaTEx query, default=smc/query.quatex
  --assign METHOD         Assign probabilities to the successors according to the given method, default=pmaude
  --alpha ALPHA, -a ALPHA Required significance level for the confidence interval, default=0.05
  --delta DELTA, -d DELTA Maximum admissible radius for the confidence interval around the mean, default=0.5
  --seed SEED, -s SEED    Random seed
  --jobs JOBS, -j JOBS    Number of parallel simulation threads, default=1, -j 0 will start as many jobs as CPU units
  --format {text,json}    Output format for the simulation results, default=text
  --distribute WORKERS    Distribute the computation across multiple machines, specified as a list of workers for the simulation.
  --dump OUTPUTFILE       Dump query evaluations into the given file. Currently, it only works with the sequential version (-j 1).
                          For each simulation, a line is written with the result of all queries separated by space. 
  -D D                    Define a constant to be used in QuaTEx expressions.
```

An examplar SMC run for the file generated by the command above is:
```shell
maude-hcs scheck --test ./use-cases/challenge-problem-2/cp2_scenarios/cp2_scenario_1.maude --query ./smc/cp2_eval_cp2_scenario_1.quatex -j 0 -n 30-120
```

The probabilistic model and its initial configuration should be specified in Maude and provided via the ``--test TEST`` option (default: ``results/generated_test.maude``).  The Maude execution starts from the initial term provided via the ``--initail INITIAL`` option (default: ``initConfig`` specified in ``TEST``) and rewrites to the final configuration.  From the final configuration, the observables are extracted using the monitor and adversary actors specified in the Maude source file for the model checking problem, provided via ``--file FILE`` option, or by the ``--protocol PR`` option. For example ``--protocol dns`` refers to a model checking file created specifically for the dns protocol under `lib/`.

Quantitative properties, such as the expected value of the average latency, can be specified using a QuaTEx formula and provided via ``--query QUERY`` option (default: ``smc/query.quatex``).  Our latency and scalability metrics in terms of exfiltrated files - for example, those defined in ``smc/latency.quatex`` and ``smc/scalability_cp2_scenario_1.quatex``, and imported into ``smc/cp2_eval_cp2_scenario_1.quatex``) - can be expressed with a QuaTEx formula of the following form:  

```shell
Latency() = s.rval("getLatency(getMonitor(C))");
eval E[Latency()] with delta = 2;

ExfilFilesC2() = 
	if (s.rval("getToDCumulativeNQueryPostNAT(C,416)") == 0.0) then 
		discard
  else 
		s.rval("getExfilFiles(getMonitor(C), getToDCumulativeNQueryPostNAT(C,416))") 
	fi;
eval E[ExfilFilesC2()];
```
where the expression ``Latency()`` extracts the latency value from the monitor and evaluates its expection with delta = 2. 
The expression ExfilFilesC2() conditionally evaluates the number of exfiltrated files: If the time of detection based on cumulative number of post-NAT DNS queries is zero - meaning that no detection occurs because the cumulative query count never exceeds its threshold (e.g., 416 in the above example) - the sample is discarded; otherwise, the number of exfiltrated files up to the time of detection is evaluated.   

Sampling continues until either the specified number of samples is reached (i.e., ``-n min-max`` option, such as ``-n 30-300``) or all queries are answered with the desired statistical significance. In the example below, the second query is answered after 30 samples using the defalut values alpha=0.05 and delta=0.5, while the first query is answered after 270 samples using ``with delta = 2``, as specified above.  

The output includes: 
- mu: the sample mean (expected value)
- sigma: the sample standard deviation
- r (confidence radius): the error margin around mu for the given alpha, i.e., mu ± radius with confidence 1-alpha

```shell
  step=30 n=30 30 μ=191.13112908653187 8.066666666666666 σ=20.074331354964382 1.048260737942926 r=7.495878519259243 0.391426992470463
  step=60 n=60 30 μ=191.73987197380484 8.066666666666666 σ=18.784008301748255 1.048260737942926 r=4.852423885397848 0.391426992470463
  step=90 n=90 30 μ=191.0827655561146 8.066666666666666 σ=17.597893935302075 1.048260737942926 r=3.6858075268606814 0.391426992470463
  step=120 n=120 30 μ=191.28516943859958 8.066666666666666 σ=16.712118022094398 1.048260737942926 r=3.0208416995911134 0.391426992470463
  step=150 n=150 30 μ=191.81314662826944 8.066666666666666 σ=16.539151183097196 1.048260737942926 r=2.6684398888965446 0.391426992470463
  step=180 n=180 30 μ=190.8746803932425 8.066666666666666 σ=16.936122821805657 1.048260737942926 r=2.4909903998666914 0.391426992470463
  step=210 n=210 30 μ=191.46358580546917 8.066666666666666 σ=16.52110171477275 1.048260737942926 r=2.24749940416632 0.391426992470463
  step=240 n=240 30 μ=191.56944900796088 8.066666666666666 σ=16.513730454991496 1.048260737942926 r=2.0998701423425232 0.391426992470463
  step=270 n=270 30 μ=191.8095651355114 8.066666666666666 σ=16.62555049424396 1.048260737942926 r=1.9920516750753852 0.391426992470463
Number of simulations = 270
Query 1 (./smc/readme.quatex:5:1)
  μ = 191.8095651355114         σ = 16.62555049424396         r = 1.9920516750753852
Query 2 (./smc/readme.quatex:6:1) (30 simulations)
  μ = 8.066666666666666         σ = 1.048260737942926         r = 0.391426992470463
```

If we modify the threshold value in the QuaTEx formual above to 500, some samples are discarded.  The results are then reported along with the number of discarded samples, and the statistical guarantees are computed using the remaining samples as shown below. 

```shell
Number of simulations = 270
Query 1 (./smc/readme.quatex:7:1)
  μ = 191.80187664851906        σ = 16.429217228790975        r = 1.9685272804723886
Query 2 (./smc/readme.quatex:8:1) (39 simulations)
  μ = 9.76923076923077          σ = 0.48458003855418535       r = 0.1570826767676969
  where 21 executions out of 60 (35.0%) have been discarded
```

To reproduce the same experiments within the same parallelization setting (i.e., the same value of ``-j``), use the ``--seed`` option with the same random seed. By default or when passing ‑1, the current time is used as the seed.
```shell
# maude-hcs scheck --seed 0
Number of simulations = 30
  μ = 1.5301530777180123        σ = 3.9683630959745835e-05    r = 1.481811132921282e-05
# maude-hcs scheck --seed 0
Number of simulations = 30
  μ = 1.5301530777180123        σ = 3.9683630959745835e-05    r = 1.481811132921282e-05
# maude-hcs scheck --seed 0 -j 4
Number of simulations = 30
  μ = 1.5301436629475402        σ = 5.0836982397393854e-05    r = 1.8982841201450367e-05
# maude-hcs scheck --seed 0 -j 4
Number of simulations = 30
  μ = 1.5301436629475402        σ = 5.0836982397393854e-05    r = 1.8982841201450367e-05
```

### Test automation
runexp.sh is an automation script that combines generation and SMC analysis. It takes two required arguments:
```shell
runexp.sh CONFIG_FILENAME METRIC

where 
  CONFIG_FILENAME is the name of the .yaml shadow file defining the experiment
  METRIC is the quatex property and can be latency, throughput, goodput, or all
```

### Run Distributed SMC  

To run the distributed SMC, there should be one or more workers that are started with

    $ umaudemc sworker -a 127.0.0.1 -p 1234
    👂 Listening on 127.0.0.1:1234...

The only options for the new sworker command are the address (-a) and the port (-p). It keeps waiting for connections from the controller.

On the controller side, an ordinary scheck command can be executed with an additional option --distribute <file>. For example,

    $ maude-hcs scheck --distribute workers.json

The file workers.json (it can also be TOML or YAML) specifies the list of workers for the simulation. This file should be a dictionary with a workers key containing a list of values of the form ``{ "workers": [ {"address": "127.0.0.1", "port": 1234} ] }`` or simply ``{ "workers": [ "127.0.0.1:1234" ] }``. Other than that, the options and the output should be the same as in the regular scheck command.

The scheck command will connect to the remote workers, pass them all the information they need, activate them, and process their results until the prescribed confidence level is reached. Instead of manually copying the files to every machine that runs a worker, the files are sent through the connection. Maude inclusions are resolved and a flattened version of the Maude sources is sent.  

### Run QMaude for a standalone test   

QMaude offers Statistical Model Checking (SMC) of the model in the same formalism.
Copy `latency.quatex` and `smc.maude` to your experiment's directory (or keep it in `results`).  Modify the former to load the target (probabilistic) experiment.
Run
```shell
umaudemc --no-advise scheck smc initConfig latency.quatex -a 0.05 --assign pmaude -j 50
```
QMaude returns the expected value for the quatex queries (μ), and the number of Monte Carlo simulations it took to reach that value.

# Tests

To run the tests, first install pytest in your environment.
```
pip install -e .[test]
```

Then run the unit tests
```
python -m pytest
```

## Other utilities

To convert a directory of images to a json metadata file used in the experiment,

For example to generate the images used by mastodon tgen client (similarly cover images for destini)
```shell
 maude-hcs --verbose --protocol dnsmastodon images --image-dir ../pwnd-cp2/src/static/images/ --image-out-dir results/
```

### To generate the comparison plots per quatex query across scenarios between testbed and SMC
Use plotfinal.py with arguments smc\_directory, tne\_directory, quatex\_directory
```shell
python scripts/plotfinal.py use-cases/challenge-problem-2/results-aligned/ use-cases/challenge-problem-2/cp2_scenarios_tne/cp2_te_results/ smc/
```

The same script will generate the CDF plots.
```shell
python scripts/gather\_samples.py use-cases/challenge-problem-2/results-aligned/samples/ use-cases/challenge-problem-2/results-aligned/cdfs use-cases/challenge-problem-2/cp2_scenarios_tne/cp2_te_results/
```

# References

DNS model
https://gitlab.ethz.ch/netsec/dns-formalization-maude

DNS Corporate use case (visualize with exalidraw) `docs/corporate-base.exalidraw`

Iodine source code
https://github.com/yarrick/iodine
Iodine client and server flowcharts under docs/figures

Actors2PMaude tool
https://zenodo.org/records/7071693

Unified Maude model-checking tool 
https://github.com/fadoss/umaudemc
