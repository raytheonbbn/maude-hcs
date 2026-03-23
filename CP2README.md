# Running CP2
This document outlines how to run Maude-HCS specifically for the CP2 scenarios.

Before running Maude commands, the reader should set up a Maude and Python environement to build and run experiment files.

# Setting up environment
Refer to README.md Requirements to install the necessary environment.

# Generating user models
User Models are Markov models intended to mimic real-world use of applications, protocols, and their components.
For more information, please see README.md Auto generate user models.

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

# Generating batched configurations of CP2
For batched configurations like the ones in CP2, convert multiple YML files to Maude scenario files:
```shell
 ./scripts/generate_cp2_maude.sh [scenario_dir]
```
Where `scenario_dir` is optional (defaults to `../pwnd_cp2`)

# Running Maude
## Standalone run with Maude

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

## Statistical Model Checking (SMC)
SMC is available by means of the `scheck` subcommand.
For CP2, each scenario can be run as:

```shell
maude-hcs scheck --test ./use-cases/challenge-problem-2/cp2_scenarios/cp2_scenario_1.maude --query ./smc/cp2_eval_cp2_scenario_1.quatex -j 0 -n 30-120
```

For SMC output, please refere to README.md Statistical Model Checking.

To automate running all scenarios in CP2, type
```shell
./scripts/runcp2.sh
```
