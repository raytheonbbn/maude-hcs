#!/bin/bash

# YOU MUST RUN THIS FROM THE REPO ROOT

set -uxo pipefail

# Initialize conda for this script, otherwise conda commands are likely to fail
# For interactive terminals this is done through .bashrc or .bashprofile, but that doesn't work in scripts.
eval "$(conda shell.bash hook)"

# Keep deactivating until we're back out of any conda environment.
while [ ! -z "$CONDA_PREFIX" ]; do conda deactivate; done

conda env remove --name maude-hcs
conda create --name maude-hcs python=3.14.7
conda activate maude-hcs
conda update pip

pushd maude_hcs/deps/dns_formalization
pip install -e .

popd
pip install -r requirements.txt

