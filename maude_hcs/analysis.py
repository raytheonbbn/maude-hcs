# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# Maude-HCS Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# The computer software and computer software documentation are licensed
# under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. A copy of the License
# is provided in the LICENSE file, but you may obtain a copy of the
# License at:  https://www.apache.org/licenses/LICENSE-2.0
#
# The computer software and computer software documentation are based
# upon work supported by the Defense Advanced Research Projects Agency (DARPA)
# under Agreement No. HR00l 12590083.
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
# contained herein. Refer to the provided NOTICE file.
#
# MAUDE_HCS: end

import json
import logging
from maude_hcs.lib.dns.known_networks import KnownUNetworks
from maude_hcs.parsers.hcsconfig import HCSConfig

logger = logging.getLogger(__name__)

class HCSAnalysis:
    def __init__(self, args, hcsconf:HCSConfig):
        self.args = args
        self.hcsconf = hcsconf        

    def generate(self):
        # step 1. generate the network configuration 
        self.conf = self.generate_network()
        return self.conf

    def run(self):
        pass        

    def generate_network(self):
        conf = KnownUNetworks().create(self.args, self.hcsconf)
        return conf


