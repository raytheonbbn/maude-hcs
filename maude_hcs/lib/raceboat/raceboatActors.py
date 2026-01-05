from maude_hcs.lib.mastodon.mastodonActors import MastodonClient
from maude_hcs.parsers.ymlconf import Destini
from Maude.attack_exploration.src.conversion_utils import address_to_maude, name_to_maude, rtype_to_maude

class RaceboatClient:
    """
    *** Make a Raceboat client.
    --- mastodon client first
    makeMastodonClient(mastodon-client,
                     mastodon-server,
                     clientContentMgr)
    *** Make a Raceboat client.
    op makeRbClient : Address Address Address Address -> Config .
    eq makeRbClient(userModel:Address,
                    contentMgr:Address,
                    destini:Address,
                    masClient:Address) =
    mkUMactor(userModel:Address, mas-ma, contentMgr:Address)
    mkCMClient(contentMgr:Address, destini:Address, masClient:Address, 3, mas-ma)
    makeDestiniActor(destini:Address, Imlc)
    ---             Destini ContentMgr NumHashtags  Model
    op mkCMClient : Address Address Address    Nat         MAModel -> Actor .
    eq mkCMClient(cmcAddr, edAddr, mcAddr, l, mamodel) =
    ---
    op makeDestiniActor : Address ByteSeqL -> Actor .
    eq makeDestiniActor(destiniAddr, coverImages:ByteSeqL) =
    < destiniAddr : ED |
    """

    def __init__(self, addressPrefix:str, profile: str, destiniObj: Destini, images_identifier:str, mastodon_server: str, X:bool) -> None:
        self.userModelAddress = address_to_maude(f'{addressPrefix}-UM')
        self.profile = profile
        self.contentManagerAddress = address_to_maude(f'{addressPrefix}-content-manager')
        self.destiniAddress = address_to_maude(f'{addressPrefix}-destini')
        self.destiniObj = destiniObj
        self.masClientAddress = address_to_maude(f'{addressPrefix}-mas-client')
        self.mastodon_server = mastodon_server
        self.images_identifier = images_identifier
        self.X = X
        self.address = self.contentManagerAddress # DO NOT MODIFY

    def to_maude_defs(self):
        s = self.destiniObj.to_maude(self.images_identifier)
        return s

    def to_maude_usermodel(self):
        return f'mkUMactor({address_to_maude(self.userModelAddress)},{address_to_maude(self.profile)}-ma, {address_to_maude(self.contentManagerAddress)})'

    def to_maude_mas_client(self):
        mc = MastodonClient(self.masClientAddress, self.mastodon_server, self.contentManagerAddress)
        return mc.to_maude()

    def to_maude_destini(self):
        s = f'makeDestiniActor({self.destiniAddress}, {self.images_identifier})\n'
        return s

    def to_maude_content_manager(self):
        return f'mkCMClient({address_to_maude(self.contentManagerAddress)}, {address_to_maude(self.destiniAddress)}, {address_to_maude(self.masClientAddress)}, 3, {address_to_maude(self.profile)}-ma)\n'

    def to_maude(self) -> str:
        str = '---- raceboat client ----\n'
        str += f'{self.to_maude_usermodel()}\n'
        str += f'{self.to_maude_content_manager()}'
        str += f'{self.to_maude_destini()}'
        str += f'{self.to_maude_mas_client()}'
        return str
