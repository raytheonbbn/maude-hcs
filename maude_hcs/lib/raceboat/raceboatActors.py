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
    def __init__(self, userModelAddress, profile:str, contentManagerAddress, masClientAddress, destiniAddress, destiniObj:Destini) -> None:
        self.userModelAddress = userModelAddress
        self.profile = profile
        self.contentManagerAddress = contentManagerAddress
        self.destiniAddress = destiniAddress
        self.destiniObj = destiniObj
        self.masClientAddress = masClientAddress

    def to_maude_usermodel(self):
        return f'mkUMactor({address_to_maude(self.userModelAddress)},{address_to_maude(self.profile)}-ma, {address_to_maude(self.contentManagerAddress)})\n'

    def to_maude(self) -> str:
        str = '---- raceboat client ----\n'
        str += self.to_maude_usermodel()
        str += self.to_maude_content_manager()
        str += self.make_destini()
        str += self.to_maude_mas_cleint()
        return str
