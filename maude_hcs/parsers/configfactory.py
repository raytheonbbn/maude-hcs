#!/usr/bin/env python
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


