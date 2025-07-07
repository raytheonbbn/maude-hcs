# MAUDE_HCS: maude_hcs
# Software Markings (UNCLASS)
# PWNDD Software
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
# Contract No: HR00112590083
# Contractor Name: RTX BBN Technologies Inc.
# Contractor Address: 10 Moulton Street, Cambridge, Massachusetts 02138
# 
# The U.S. Government's rights to use, modify, reproduce, release, perform, 
# display, or disclose these technical data and software are defined in the 
# Article VII: Data Rights clause of the OTA.
# 
# This document does not contain technology or technical data controlled under 
# either the U.S. International Traffic in Arms Regulations or the U.S. Export 
# Administration Regulations.
# 
# DISTRIBUTION STATEMENT A: Approved for public release; distribution is 
# unlimited.
# 
# Notice: Markings. Any reproduction of this computer software, computer 
# software documentation, or portions thereof must also reproduce the markings 
# contained herein.
# MAUDE_HCS: end

#!/bin/bash

# TODO: Parse and integrate into command line.
help_doc() {
    cat << EOF
Usage: $(basename "$0") <yaml_filename> [quatex]

This is a brief description of what your script does.

Options:
  -quatex               One of latency, goodput, throughput, all

Examples:
  $(basename "$0") path/to/cp1_sim_config.yaml
  $(basename "$0") path/to/cp1_sim_config.yaml all
EOF
}

SIM_FULL_FILENAME=$1
METRIC_NAME=$2

quatex_command=""
case "$METRIC_NAME" in
  "goodput")
    quatex_command="goodput"
    ;;
  "throughput")
    quatex_command="throughput"
    ;;
  "all")
    quatex_command="all"
    ;;
  *)
    quatex_command="latency"
    ;;
esac
    
# Get the filename with extension
SIM_FILENAME=$(basename "$SIM_FULL_FILENAME")

# Remove the extension using parameter expansion
SIM_FILENAME="${SIM_FILENAME%.*}"

GENERATED_FILENAME="generated_$SIM_FILENAME"
echo "Writing generated file $GENERATED_FILENAME, running $quatex_command quatex"

maude-hcs --verbose --shadow-filename=$SIM_FULL_FILENAME --model=prob --protocol=dns --filename=$GENERATED_FILENAME generate
maude-hcs --verbose scheck --test ./results/$GENERATED_FILENAME.maude --query ./smc/$quatex_command.quatex -j 0
