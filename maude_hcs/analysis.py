# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# PWNDD Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
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
#
# MAUDE_HCS: end

import json
import logging
from maude_hcs.lib.dns.known_networks import KnownUNetworks

logger = logging.getLogger(__name__)

class HCSAnalysis:
    def __init__(self, args, run_args):
        self.args = args
        self.run_args = run_args

    def generate(self):
        # step 1. generate the network configuration 
        self.conf = self.generate_network()
        return self.conf

    def run(self):
        pass
        

    def generate_network(self):
        conf = KnownUNetworks().create(self.args, self.run_args)
        return conf


