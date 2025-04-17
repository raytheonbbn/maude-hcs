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
Pass a use case config file as follows,

To geenrate a vanilla DNS config (without iodine),
```shell
maude-hcs --verbose --run-args=./use-cases/corporate-base.json generate nondet
```

To generate a nondeterministic DNS model config with iodine,
```shell
maude-hcs --verbose --run-args=./use-cases/corporate-iodine.json --model=nondet  generate
```
And set `--model=prob` to generate a probabilistic version.

Look at the `corporate-iodine.json` file above to see the configuration parameters.
The probabilistic model will combine the nondeterministic params as well as the 
probabilistic params (whic override the nondeterministic ones).

# Run configurations

In progress ...

# References

DNS model
https://gitlab.ethz.ch/netsec/dns-formalization-maude

DNS Corporate use case (visualize with exalidraw) `docs/corporate-base.exalidraw`

Iodine source code
https://github.com/yarrick/iodine
Iodine client and server flowcharts under docs/figures

Actors2PMaude tool
https://zenodo.org/records/7071693

# Plan and paper

Current plan 
https://docs.google.com/spreadsheets/d/1VNd7eNqDvlZrCXnjC-y772eVDkgggKh-jcNATgiM5Hc/edit?usp=sharing

Overlead paper
https://www.overleaf.com/3267687712qvzjxzjmxjjr#81eb69

# mailing list

bbn-pwnd2@rlist.app.ray.com
