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
