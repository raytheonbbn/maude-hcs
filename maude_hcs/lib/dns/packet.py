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

from Maude.attack_exploration.src.conversion_utils import address_to_maude

class Packet:
    #   ----        AliceAddr BobAddr Packet# DataLenBytes
    def __init__(self, fromAddress, toAddress, sequenceNum : int, lenBytes : int, lastPacket : bool) -> None:
        self.address = fromAddress
        self.toAddress = toAddress
        self.seqNum = sequenceNum
        self.lenBytes = lenBytes
        # Indicates if this is the last packet of a file transfer.
        self.lastPacket = lastPacket

    def __str__(self) -> str:
        return f'packet({self.address}, {self.toAddress}, {self.seqNum}, {self.lenBytes}, {self.lastPacket})'

    def to_maude(self) -> str:
        return f'packet({address_to_maude(self.address)}, {address_to_maude(self.toAddress)}, {self.seqNum}, {self.lenBytes}, {str(self.lastPacket).lower()})'
