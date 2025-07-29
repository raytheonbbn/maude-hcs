# Maude-HCS

Formal Analysis of Hidden Communications Systems at Scale

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

## VIRTUALENV
```bash
python -m venv venv
source venv/bin/activate
```

## Install: from git source
We structured the repo source code so that 
we import dns-formalization-maude as a dependency (a submodule).
We created a fork of this dependency so that we can track our changes 
to it. The main initial changes we did are structural so that we can
import the dependency as a module especially for some relevant python
source code, and use it.
We will also use sparse-checkout to avoid needing to checkout all the source of the 
dependency which includes many irrelevant files (such as Testbed).

First setup a new conda environment and activate it.

Clone the main repo
```shell
git clone git@github.com:jkhourybbn/maude-hcs.git
```

Setup the dns submodule using our clone of the code so we can track changes 
made to the original source, use sparse-checkout to keep only relevant sources
```shell
cd maude-hcs
mkdir -p maude_hcs/deps
git submodule add -b pwnd -f git@github.com:jkhourybbn/dns-formalization-maude.git maude_hcs/deps/dns_formalization
cd maude_hcs/deps/dns_formalization
git sparse-checkout init --cone
git sparse-checkout set "Maude/src" "Maude/test" "Maude/attack_exploration"
cd ../../../
git reset .gitmodules
git reset maude_hcs/deps/dns_formalization
```

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

# Auto generate configurations

For now we can generate initial configurations using `generate` command.
HCS Configurations can be directly passed in json using HCS configuration parameters, 
or using a Shadow experiment configuration. Each of these is described next. 

## Using HCS json Configuration 
Pass a maude-hcs json configuration file as follows,

To generate a probabilistic DNS model config with iodine and specify the output filename,
```shell
maude-hcs --verbose --run-args=./use-cases/corporate-iodine-conf.json --model=prob --protocol=dns --filename=generated_test_aa generate
```
And set `--model=nondet` to generate a nondeterministic version.

See example [corporate-iodine-conf.json](./use-cases/corporate-iodine-conf.json) configuration file, and refer to [HCSParamsGuide](./HCSParamsGuide.md) for a description of the parameters.
Note that probabilistic model will combine the nondeterministic params as well as the 
probabilistic params (whic override the nondeterministic ones).


## Using Shadow yaml configuration
To generate a model that uses characteristics defined in a shadow file, specify:
```shell
--shadow-filename <path_to_shadow_file.yaml>
```
The shadow yaml file specifies the network, host, and process configurations.

Assuming the shadow network config is located in directory `../pwnd-cp1`, run
```shell
maude-hcs --verbose --shadow-filename=../pwnd-cp1/shadow_files/examples/cp1_sim_config.yaml --model=prob --protocol=dns --filename=generated_test_shadow generate
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
```

An examplar SMC run for the file generated by the command above for a shadow file configration is:
```shell
maude-hcs --verbose scheck --test ./results/generated_test_shadow.maude -j 0
```

The probabilistic DNS model with iodine and its initial configuration should be specified in Maude and provided via the ``--test TEST`` option (default: ``results/generated_test.maude``).  The Maude execution starts from the initial term provided via the ``--initail INITIAL`` option (default: ``initConfig`` specified in ``TEST``) and rewrites to the final configuration.  From the final configuration, the observables are extracted using the monitor actor specified in the Maude source file for the model checking problem, provided via ``--file FILE`` option, or by the ``--protocol PR`` option. For example ``--protocol dns`` refers to a model checking file created specifically for the dns protocol under `lib/`.

Quantitative properties such as the expected value of the average latency can be specified using a QuaTEx formula and provided via ``--query QUERY`` option (default: ``smc/query.quatex``).  Our latency example (in ``smc/latency.quatex``) can be expressed with a QuaTEx formula of the following form:  

```shell
Latency() = if (s.rval("isDone(C)") == 1) then s.rval("getLatency(getMonitor(C))") else #Latency() fi;
eval E[Latency()];
```
where the expression ``#Latency()`` in the else branch says evaluate at the next step, so eventually ``Latency()`` is computed at the end (``isDone(C)``).
The next operator ``#`` evaluates the function in the next step of the simulation, and ``s.rval`` reduces
the given string as a Maude term of sorts Int, Float, Integer, Real, or Bool and returns the result
as a floating‑point number, where true and false are respectively converted to 1 and 0.

The ``getLatency()`` operator (specified in ``smc/smc.maude``), for example, calculates the latency by taking the timestamp ``T’`` when the last packet is received (pattern matched by ``last? == true``) and subtracting the timestamp ``T`` when the first packet was sent (pattern matched by ``id == 0``).  

```shell
op isDone : Config -> Bool .
eq isDone ({ F:Float | nil } AC < monAddr : WMonitor | pktRcvd: (PTL ; packetTimestamp(packet(Alice, Bob, id, len, true), T) ; PTL'), attrs >) = true .
eq isDone (c:Config) = false [owise] .	

op getMonitor : Config -> Actor .
eq getMonitor (C < monAddr : WMonitor | attrs >) = < monAddr : WMonitor | attrs > .

op getLatency : Actor -> Float .
eq getLatency (< monAddr : WMonitor | pktSent: (PTL ; packetTimestamp(packet(Alice, Bob, 0, len, last?), T) ; PTL'), pktRcvd: (PTL'' ; packetTimestamp(packet(Alice, Bob, id, len', true), T') ; PTL'''), attrs >) = T' - T .
```

The sampling continues until all queries are answered, given the significance level. In the example below, the first query has been answered after 540 samples, using the defalut values alpha=0.05 and delta=0.5.  
The output includes: 
- mu: the sample mean (expected value)
- sigma: the sample standard deviation
- r (confidence radius): the error margin around mu for the given alpha, i.e., mu ± radius with confidence 1-alpha
```shell
step=30 μ=4.239755686933099 9.503953803793227σ=6.234431955277789 9.636148900965297 r=2.3279751513015263 3.598197134335262
step=60 μ=3.382780227277642 7.602787049026596 σ=4.644635229137601 7.475853814951423 r=1.199836507883676 1.931217822770907
...
step=510 μ=4.338036135949193 8.917610858544654 σ=5.913970994929576 8.605279626649583 r=0.5144890076422401 0.7486208132225801
step=540 μ=4.2768458443172275 8.871405618373508 σ=5.820471565190272 8.56874261695837 r=0.49202331401761434 0.7243435677229358
...
step=1050 μ=4.37470604567949 8.692609313911868 σ=5.797909133367788 8.361216167524594 r=0.3510962786100331 0.5063190563262162
step=1080 μ=4.357164241918655 8.640346715005759 σ=5.741867532339669 8.286648801516955 r=0.3428284179680576 0.49476911177074157

Number of simulations = 1080
Query 1 (line 6:1)
  μ = 4.357164241918655         σ = 5.741867532339669         r = 0.3428284179680576
Query 2 (line 6:20)
  μ = 8.640346715005759         σ = 8.286648801516955         r = 0.49476911177074157
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

# Plan and paper

Current plan 
https://docs.google.com/spreadsheets/d/1VNd7eNqDvlZrCXnjC-y772eVDkgggKh-jcNATgiM5Hc/edit?usp=sharing

Overlead paper
https://www.overleaf.com/3267687712qvzjxzjmxjjr#81eb69

# mailing list

bbn-pwnd2@rlist.app.ray.com
