#!/bin/bash

# YOU MUST RUN THIS FROM THE REPO ROOT
# THIS ALSO ASSUMES THAT maude-1.6.1-cp314-cp314-macosx_26_0_arm64.whl (or whatever wheel is appropriate for your OS) IS PRESENT IN THE REPO ROOT

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

# Adjust this line as appropriate for your wheel file
pip install -U maude-1.6.1-cp314-cp314-macosx_26_0_arm64.whl

pushd maude_hcs/deps/dns_formalization
pip install -e .

popd
pip install -e ".[test]"

# If the above line doesn't work, try this, it's hardcoded with exact versions for all the packages I had after a successful install
# pip install -r requirements.txt
