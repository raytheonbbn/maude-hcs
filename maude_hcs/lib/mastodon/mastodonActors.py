from Maude.attack_exploration.src.conversion_utils import address_to_maude, name_to_maude, rtype_to_maude

from maude_hcs.lib.dns.iodineActors import TGenClient
from ...parsers.ymlconf import Destini
from maude_hcs.lib.common import X

class MastodonServer:

    def __init__(self, address) -> None:
        self.address = address_to_maude(address)

    def __str__(self) -> str:
        return f'< {self.address} : MasServer | Attrs >'

    def to_maude(self) -> str:
        return f'makeMastodonServer({self.address})'


class MastodonClient:
    """
     Make a MasClient:   its_addr srver_addr requester_addr
     requester addr is addr of Raceboat / TGEN.
    """
    def __init__(self, address, svrAddress, requestorAddress, X:bool) -> None:
        self.address = address
        self.svrAddress = svrAddress
        self.requestorAddress = requestorAddress
        self.X = X

    def __str__(self) -> str:
        return f'< {self.address} : MasClient | Attrs >'

    def to_maude(self) -> str:
        return f'makeMastodonClient({address_to_maude(self.address)}, {X(address_to_maude(self.svrAddress), self.X)}, {address_to_maude(self.requestorAddress)})'

class MASTGenClient(TGenClient):
    def __init__(self, address : str, profile, startTime: float, start:bool, username:str, hashtags:list, images:Destini, images_id:str, mastodon_server: str, X:bool) -> None:
        super().__init__(address, profile, startTime, start)
        self.hashtags = hashtags
        self.images = images
        self.images_id = images_id
        self.username = username
        self.mastodon_server = mastodon_server
        self.X = X

    def to_maude_defs(self):
        res = ''
        if self.images:
            res += '---- defining the images list \n'
            res += self.images.to_maude(self.images_id)
            res += '\n'
        return res

    def to_maude(self) -> str:
        # **** umActor for masTGEN
        #   mkUMactor(umA,mas-ma,mtgA)
        #   [0.0, (to umA from umA : actionR("")), 0]
        # **** mc for masTgen
        #   makeMastodonClient(mcA, X(mastodonServer), mtgA)
        # **** masTActor
        #   mkMasTGenActor(mtgA, mcA, IM0 :: IM1, mas-ma)
        tgAddr = self.address
        tgUMAddr = self.address_um
        masClAddr = tgAddr + '-client'
        toaddr = address_to_maude(self.mastodon_server)
        res = ''
        mastodonClient = MastodonClient(masClAddr, toaddr, tgAddr, self.X)
        res += f'  {mastodonClient.to_maude()}\n'
        res += f'  mkMasTGenActor({tgAddr}, {masClAddr}, {self.images_id}, {address_to_maude(self.profile)}-ma)\n'
        res += f'  mkUMactor({tgUMAddr},{address_to_maude(self.profile)}-ma,{tgAddr})\n'
        res += f'  [{self.startTime} + genRandom(0.0, 0.0001), (to {tgUMAddr} from {tgUMAddr} : actionR("")), 0]'
        return res