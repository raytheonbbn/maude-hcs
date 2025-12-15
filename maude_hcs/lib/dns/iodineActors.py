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

from Maude.attack_exploration.src.conversion_utils import address_to_maude, name_to_maude, rtype_to_maude
from Maude.attack_exploration.src.actors import Nameserver, Resolver
from .utils import packetlist_to_maude
from .cache import ResolverCache, CacheEntry


class Router:

    def __init__(self, address) -> None:
        self.address = address

    def __str__(self) -> str:
        return f'< {self.address} : Router | Attrs >'

    def to_maude(self) -> str:
        return f'mkRouter({address_to_maude(self.address)})'

class ReceiveApp:
    def __init__(self, address, file_dest_address, toAddress, fromAddress, start:float = 0.0):
        self.address = address
        self.file_dest_address = file_dest_address
        self.toAddress = toAddress
        self.fromAddress = fromAddress
        self.start = start

    def __str__(self) -> str:
        return f'< {self.address} : RcvApp | Attrs >'

    def to_maude(self) -> str:
        return f'mkRcvApp({address_to_maude(self.address)}, {address_to_maude(self.file_dest_address)}, {address_to_maude(self.fromAddress)}, {address_to_maude(self.toAddress)})'

    def to_maude_full(self) -> str:
        res = f'< {address_to_maude(self.address)} : RcvApp |\n'
        res += f'    rcvd: mtpl,\n'
        res += f'    fileDestAddr: {address_to_maude(self.fromAddress)},\n'
        res += f'    fileSrcAddr: {address_to_maude(self.file_dest_address)},\n'
        res += f'    toAddr: {address_to_maude(self.toAddress)},\n'
        res += f'    queuePopulated: false,\n'
        res += f'    queue: (mtpl),\n'
        res += f'    numAdmittedPkts: 1,\n'
        res += f'    iodineReady: true,\n'
        res += f'    sent: mtpl >'
        return res


class IodineServer:

    def __init__(self, address, zones: list, severWResponseTTL: float) -> None:
        self.address = address        
        self.zones = zones
        self.severWResponseTTL = severWResponseTTL

    def __str__(self) -> str:
        return f'< {self.address} : WNameserver | Attrs >'

    def to_maude(self) -> str:
        return f'makeWNameServer({address_to_maude(self.address)}, {self.severWResponseTTL}, ({" ".join(list(map(lambda z: z.maude_name(), self.zones)))}))'

    def to_maude_full(self) -> str:
        NS = Nameserver(self.address, self.zones)
        strNS = "" if not self.zones else NS.to_maude_full()
        res = f'< {address_to_maude(self.address)} : WNameserver |\n'        
        res += f'    fragmentsReceived: mtfl,\n'
        res += f"    inSeqNo: 0,\n"
        res += f"    inFragNo: 0,\n"
        res += f'    lastFragment: false,\n'
        res += f'    severWResponseTTL: {self.severWResponseTTL},\n' # {:.2f}'.format()
        res += f'    conf: ({strNS}),\n'
        res += f'    outSeqNo: 0,\n'
        res += f'    fragmentsToSend: mtfl,\n'
        res += f'    fragmentsSize: 0,\n'
        res += f'    outFragNo: 0,\n'
        res += f'    numAttempts: 0 >'
        return res


class SendApp:
    #def __init__(self, address, file_dest_address, toAddress, fromAddress, packets_to_send, overwrite_queue : bool, start : float = -1):
    def __init__(self, address, file_dest_address, toAddress, fromAddress, start:float = 0.0):
        """
        Constructor, builds a SendApp.

        address:  The address of the send app.
        file_dest_address: The address of the file transfer's destination.
        toAddress: The address of the IodineClient or file transfer's destination.
        fromAddress: alice app
        """
        self.address = address
        self.file_dest_address = file_dest_address
        self.toAddress = toAddress
        self.fromAddress = fromAddress
        # self.overwrite_queue = overwrite_queue
        # self.packets = packets_to_send
        self.start = start

    def __str__(self) -> str:
        return f'< {self.address} : SendApp | Attrs >'

    def to_maude(self) -> str:
        return f'mkSendApp({address_to_maude(self.address)}, {address_to_maude(self.file_dest_address)}, {address_to_maude(self.fromAddress)}, {address_to_maude(self.toAddress)})'

    def to_maude_full(self) -> str:
        res = f'< {address_to_maude(self.address)} : SendApp |\n'
        res += f'    fileDestAddr: {address_to_maude(self.file_dest_address)},\n'
        res += f'    toAddr: ({address_to_maude(self.toAddress)}),\n'
        res += f'    fromAddr: ({address_to_maude(self.fromAddress)}),\n'
        res += f'    queuePopulated: false,\n'
        res += f'    queue: ({packetlist_to_maude(self.packets)}),\n'
        res += '    numAdmittedPkts: 1,\n'
        res += '    iodineReady: true,\n'
        res += f'    sent: mtpl,\n'
        res += f'    rcvd: mtpl > '        
        return res

class IodineClient:

    def __init__(self, address, wDomName, wQueryType, resolverAddress, wTTL:float=0.0) -> None:
        self.address = address
        self.wDomName = wDomName
        self.wQueryType = wQueryType
        self.resolverAddress = resolverAddress
        self.wTTL = wTTL

    def __str__(self) -> str:
        return f'< {self.address} : WClient | Attrs >'

    def to_maude(self) -> str:
        return f'makeWClient({address_to_maude(self.address)}, {address_to_maude(self.resolverAddress)}, {name_to_maude(self.wDomName)}, {rtype_to_maude(self.wQueryType)}, {self.wTTL})'
    
    def to_maude_full(self) -> str:
        res = f'< {address_to_maude(self.address)} : WClient |\n'
        res += f'    resv: {address_to_maude(self.resolverAddress)},\n'
        res += f'    wDom: {name_to_maude(self.wDomName)},\n'
        res += f'    weirdQType: {rtype_to_maude(self.wQueryType)},\n'
        res += f'    queryCtr: 0,\n'
        res += f'    outSeqNo: 0,\n'
        res += f'    fragmentsToSend: mtfl,\n'
        res += f'    fragmentsSize: 0,\n'
        res += f'    outFragNo: 0,\n'
        res += f'    appAddrMap: mtIdAddr,\n'        
        res += f'    numAttempts: 0,\n'
        res += f'    fragmentsReceived: mtfl,\n'
        res += f'    inSeqNo: 0,\n'
        res += f'    inFragNo: 0,\n'
        res += f'    lastFragment: false,\n'
        res += f'    severWResponseTTL: {self.wTTL} >'
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
        return f'makeMonitor({address_to_maude(self.address)})'

    def to_maude_full(self) -> str:
        res = f'< {address_to_maude(self.address)} : WMonitor |\n'
        res += '    querySent: nilQueryTimestamp,\n'
        res += '    queryRcvd: nilQueryTimestamp,\n'
        res += '    pktSent: nilPacketTimestamp,\n'
        res += '    pktRcvd: nilPacketTimestamp >'        
        return res

class PacedClient:
    def __init__(self, address, resolverAddress, NAME, N, TOP, TOQ, start = False) -> None:
        self.address = address
        self.resolverAddress = resolverAddress
        self.NAME = NAME
        self.N = N
        self.TOP = TOP
        self.TOQ = TOQ
        self.start = start

    def __str__(self) -> str:
            return f'< {self.address} : PacedClient | Attrs >'

    def to_maude(self) -> str:
            res = f'mkPacedClient({self.address},{self.resolverAddress}, {name_to_maude(self.NAME)}, {self.N},{self.TOP},{self.TOQ})'
            return res

class TGenClient:
    def __init__(self, address : str, resolverAddress : str, nameDBSize : int, retryTO : float, numRetries : int, profile, startTime: float, start = False) -> None:
        self.address = address
        self.resolverAddress = resolverAddress
        self.nameDBSize = nameDBSize
        self.retryTO = retryTO
        self.numRetries = numRetries
        self.profile = profile
        self.startTime = startTime
        self.start = start

    def to_maude(self) -> str:
        # **** umActor
        #   mkUMactor(umADDR,dnsMA,dnsTADDR)
        # **** dnsTActor
        #   mkDnsTgenA(dnsTADDR,local-dns,dnameDb, 5.0, 2)
        #   [0.0, (to umADDR from umADDR : actionR("")), 0]
        tgAddr = address_to_maude(self.address)
        tgUMAddr = tgAddr + '-UM'
        res  = f'mkDnsTgenA({tgAddr},{address_to_maude(self.resolverAddress)},{self.nameDBSize}, {self.retryTO}, {self.numRetries})\n'
        res += f'mkUMactor({tgUMAddr},{address_to_maude(self.profile)},{tgAddr})\n'
        res += f'[{self.startTime}, (to {tgUMAddr} from {tgUMAddr} : actionR("")), 0]'
        return res





class IResolver(Resolver):

    def __init__(self, address, cache : ResolverCache = None) -> None:
        self.cache = cache
        super().__init__(address)
    
    def to_maude(self) -> str:
        strCache = "nilCache"
        if self.cache:
            strCache = self.cache.name
        return f'mkResolver({address_to_maude(self.address)}, {strCache}, sb)'

    def to_maude_full(self) -> str:
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
