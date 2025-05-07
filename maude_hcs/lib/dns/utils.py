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

from .packet import Packet

def packetlist_to_maude(packets) -> str:
    if not packets:
        return 'mtpl'
    else:
        return ' ; '.join(map(lambda p: p.to_maude(), packets))
    
def makePackets(address, toAddress, sizeList : list, startSeqNum = 0) -> list:    
    indeces = list(range(startSeqNum, startSeqNum + len(sizeList)))
    isLastList = [False for index in indeces]
    isLastList[-1] = True
    return [Packet(address, toAddress, index, L, isLast) for L, index, isLast in zip(sizeList, indeces, isLastList)]
