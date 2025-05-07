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
