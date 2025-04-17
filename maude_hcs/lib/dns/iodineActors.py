from Maude.attack_exploration.src.conversion_utils import address_to_maude, name_to_maude, rtype_to_maude
from .utils import packetlist_to_maude
from Maude.attack_exploration.src.actors import Nameserver

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
        res += f'    lastFragment: false,\n'
        res += f'    conf: ({strNS}) >'
        return res


class SendApp:
    def __init__(self, address, toAddress, packets_to_send, start : float = -1):
        self.address = address
        self.toAddress = toAddress
        self.packets = packets_to_send
        self.start = start

    def __str__(self) -> str:
        return f'< {self.address} : SendApp | Attrs >'

    def to_maude(self) -> str:
        res = f'< {address_to_maude(self.address)} : SendApp |\n'
        res += f'    toAddr: ({address_to_maude(self.toAddress)}),\n'
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


