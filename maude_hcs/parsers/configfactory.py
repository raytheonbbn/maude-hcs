#!/usr/bin/env python
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

from enum import Enum
from pathlib import Path

from maude_hcs.parsers.dnshcsconfig import DNSHCSConfig

class Protocol(Enum):
    """An enumeration for network protocols."""
    DNS = "DNS"
    TCP = "TCP"

def buildHCSConfig(args):
    protocol = args.protocol
    if protocol.upper() == Protocol.DNS.value:        
        # build from run args
        if args.run_args:
            return DNSHCSConfig.from_file(Path(args.run_args.name))
        # build from shadow
        elif args.shadow_filename:
            return DNSHCSConfig.from_shadow(Path(args.shadow_filename.name))
    else:
        raise ValueError("Unsupported protocol")


