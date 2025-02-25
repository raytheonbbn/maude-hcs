# Maude-HCS

Formal Analysis of Hidden Communications Systems at Scale

## Install
We will install the dependencies (such as DNS formalization) as submodules
where we use sparse checkout to avoid needing to checkout the massive repositories
and only get the directories we need.

Clone the main repo
```shell
git clone git@github.com:jkhourybbn/maude-hcs.git
```

Setup the submodule, use sparse checkout
```shell
cd maude-hcs
git submodule add https://gitlab.ethz.ch/netsec/dns-formalization-maude.git maude_hcs/deps/dns_formalization
cd maude_hcs/deps/dns_formalization
git sparse-checkout init --cone
git sparse-checkout set "Maude/src" "Maude/test"
```
This should create a new file named sparse-checkout under .git/modules/maude_hcs/deps/dns_formalization/info/


# References

DNS model
https://gitlab.ethz.ch/netsec/dns-formalization-maude/-/tree/main/Testbed?ref_type=heads

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
