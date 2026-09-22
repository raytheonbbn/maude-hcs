#!/bin/bash

set -uxo pipefail

source /opt/anaconda3/etc/profile.d/conda.sh

conda deactivate
conda env remove --name maude-hcs
conda create --name maude-hcs python=3.12.4
conda activate maude-hcs
conda install pip

pushd maude_hcs/deps/dns_formalization
pip install -e .

popd
pip install -e ".[test]"
