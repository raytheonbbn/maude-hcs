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

from Maude.attack_exploration.src.conversion_utils import address_to_maude, name_to_maude, rtype_to_maude
from Maude.attack_exploration.src.actors import Nameserver, Resolver
from .utils import packetlist_to_maude
from .cache import ResolverCache, CacheEntry

class ReceiveApp:
    def __init__(self, address):
        self.address = address

    def __str__(self) -> str:
        return f'< {self.address} : RcvApp | Attrs >'

    def to_maude(self) -> str:
        res = f'< {address_to_maude(self.address)} : RcvApp |\n'
        res += f'    rcvd: mtpl >'
        return res


class IodineServer:

    def __init__(self, address, nameServer : Nameserver) -> None:
        self.address = address        
        self.nameServer = nameServer

    def __str__(self) -> str:
        return f'< {self.address} : WNameserver | Attrs >'

    def to_maude(self) -> str:        
        strNS = "" if self.nameServer == None else self.nameServer.to_maude()
        res = f'< {address_to_maude(self.address)} : WNameserver |\n'        
        res += f'    pendingFragments: mtfl,\n'
        res += f"    currentSeqNo: 0,\n"
        res += f"    currentFragment: 0,\n"
        res += f'    lastFragment: false,\n'
        res += f'    conf: ({strNS}) >'
        return res


class SendApp:
    def __init__(self, address, file_dest_address, toAddress, packets_to_send, overwrite_queue : bool, start : float = -1):
        """
        Constructor, builds a SendApp.

        address:  The address of the send app.
        file_dest_address: The address of the file transfer's destination.
        toAddress: The address of the IodineClient or file transfer's destination.
                   TODO: Figure out which one, when.
        packets_to_send: The list of packets to send, unless it is to be overwritten.
        overwrite_queue: The boolean to overwrite the packet list provided here.
                         (Will be computed at Alice start time.)
        """
        self.address = address
        self.file_dest_address = file_dest_address
        self.toAddress = toAddress
        self.overwrite_queue = overwrite_queue
        self.packets = packets_to_send
        self.start = start

    def __str__(self) -> str:
        return f'< {self.address} : SendApp | Attrs >'

    def to_maude(self) -> str:
        res = f'< {address_to_maude(self.address)} : SendApp |\n'
        res += f'    fileDestAddr: {address_to_maude(self.file_dest_address)},\n'
        res += f'    toAddr: ({address_to_maude(self.toAddress)}),\n'
        res += f'    queuePopulated: false,\n'
        res += f'    queue: ({packetlist_to_maude(self.packets)}),\n'
        res += '    numAdmittedPkts: 1,\n'
        res += '    wclientReady: true,\n'
        res += f'    sent: mtpl > '        
        return res

class IodineClient:

    def __init__(self, address, wDomName, wQueryType, resolverAddress) -> None:
        self.address = address
        self.wDomName = wDomName
        self.wQueryType = wQueryType
        self.resolverAddress = resolverAddress

    def __str__(self) -> str:
        return f'< {self.address} : WClient | Attrs >'

    def to_maude(self) -> str:        
        res = f'< {address_to_maude(self.address)} : WClient |\n'
        res += f'    resv: {address_to_maude(self.resolverAddress)},\n'
        res += f'    wDom: {name_to_maude(self.wDomName)},\n'
        res += f'    weirdQType: {rtype_to_maude(self.wQueryType)},\n'
        res += f'    queryCtr: 0,\n'
        res += f'    seqCtr: 0,\n'
        res += f'    fragments: mtfl,\n'
        res += f'    fragmentsSize: 0,\n'
        res += f'    currFragment: 0,\n'
        res += f'    appAddrMap: mtIdAddr,\n'        
        res += f'    numAttempts: 0 >'
        return res
    
'''
  --- monitor
  < mAddr : WMonitor |
    querySent: nilQueryTimestamp,
    queryRcvd: nilQueryTimestamp,
    pktSent: nilPacketTimestamp,
    pktRcvd: nilPacketTimestamp
  >
'''
class WMonitor:
    def __init__(self, address) -> None:
        self.address = address
    
    def __str__(self) -> str:
        return f'< {self.address} : WMonitor | Attrs >'

    def to_maude(self) -> str:        
        res = f'< {address_to_maude(self.address)} : WMonitor |\n'
        res += '    querySent: nilQueryTimestamp,\n'
        res += '    queryRcvd: nilQueryTimestamp,\n'
        res += '    pktSent: nilPacketTimestamp,\n'
        res += '    pktRcvd: nilPacketTimestamp >'        
        return res

class PacedClient:
    def __init__(self, address, resolverAddress, NAME, N, TOP, TOQ) -> None:
        self.address = address
        self.resolverAddress = resolverAddress
        self.NAME = NAME
        self.N = N
        self.TOP = TOP
        self.TOQ = TOQ

    def __str__(self) -> str:
            return f'< {self.address} : PacedClient | Attrs >'

    def to_maude(self) -> str:
            res = f'mkPacedClient({self.address},{self.resolverAddress}, {name_to_maude(self.NAME)}, {self.N},{self.TOP},{self.TOQ})'
            return res

class IResolver(Resolver):

    def __init__(self, address, cache : ResolverCache = None) -> None:
        self.cache = cache
        super().__init__(address)
    
    def to_maude(self) -> str:
        strCache = "nilCache"
        if self.cache:
            strCache = self.cache.name
        res = f'< {address_to_maude(self.address)} : Resolver |\n'
        res += f'    cache: {strCache},\n'
        res += f'    nxdomainCache: nilNxdomainCache,\n'
        res += f'    nodataCache: nilNodataCache,\n'
        res += f'    sbelt: sb,\n'  # TODO: where is sb defined?
        res += f'    workBudget: emptyIN,\n'
        res += f'    blockedQueries: eptQSS,\n'
        res += f'    sentQueries: eptQSS >'
        return res
