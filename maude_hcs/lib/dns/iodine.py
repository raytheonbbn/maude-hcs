from Maude.attack_exploration.src.conversion_utils import address_to_maude, querylist_to_maude
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

    def __init__(self, address, rcvApp : ReceiveApp, nameServer : Nameserver) -> None:
        self.address = address
        self.rcvApp = rcvApp
        self.nameServer = nameServer

    def __str__(self) -> str:
        return f'< {self.address} : WNameserver | Attrs >'

    def to_maude(self) -> str:
        strRcvApp = "" if self.rcvApp == None else self.rcvApp.to_maude()
        strNS = "" if self.nameServer == None else self.nameServer.to_maude()
        res = f'< {address_to_maude(self.address)} : WNameserver |\n'        
        res += f'    pendingFragments: mtfl,\n'
        res += f'    lastFragment: false,\n'
        res += f'    conf: ({strRcvApp} {strNS}) >'
        return res


class SendApp:
    def __init__(self, address):
        self.address = address

    def __str__(self) -> str:
        return f'< {self.address} : SendApp | Attrs >'

    def to_maude(self) -> str:
        res = f'< {address_to_maude(self.address)} : RcvApp |\n'
        res += f'    rcvd: mtpl >'
        return res
    
#   < addrWClient : WClient |
#     resv: addrWNS,
#     queryCtr: 12,
#     seqCtr: 7,
#     fragments: popFront(makeFragments(packet(addrAlice, 7, 300), 200)),
#     fragmentsSize: 2,
#     currFragment: 2,
#     numAttempts: 1,
#     conf: (makeSendApp(addrAlice))
#   >    