from maude_hcs.lib.mastodon.mastodonActors import MastodonClient
from maude_hcs.parsers.protocolconfig import XFile, files_to_maude
from maude_hcs.parsers.ymlconf import Destini
from Maude.attack_exploration.src.conversion_utils import address_to_maude, name_to_maude, rtype_to_maude
from ...parsers.markovJsonToMaudeParser import JsonToMaudeParser
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

    def __init__(self, addressPrefix:str, northbound_address:str, profile: str, destiniObj: Destini, images_identifier:str, mastodon_server: str, X:bool) -> None:
        self.userModelAddress = address_to_maude(f'{addressPrefix}-UM')
        self.northbound_address = northbound_address
        self.profile = profile
        self.contentManagerAddress = address_to_maude(f'{addressPrefix}-content-manager')
        self.destiniAddress = address_to_maude(f'{addressPrefix}-destini')
        self.destiniObj = destiniObj
        self.masClientAddress = address_to_maude(f'{addressPrefix}-mas-client')
        self.mastodon_server = mastodon_server
        self.images_identifier = images_identifier
        self.X = X
        self.address = self.contentManagerAddress # DO NOT MODIFY
        self.type = 'Client'  # DO NOT MODIFY

    def to_maude_defs(self):
        s = self.destiniObj.to_maude(self.images_identifier)
        return s

    def to_maude_usermodel(self):
        return f'mkUMactor({address_to_maude(self.userModelAddress)},{address_to_maude(self.profile)}-ma, {address_to_maude(self.contentManagerAddress)})'

    def to_maude_mas_client(self):
        mc = MastodonClient(self.masClientAddress, self.mastodon_server, self.contentManagerAddress, self.X)
        return mc.to_maude()

    def to_maude_destini(self):
        s = f'makeDestiniActor({self.destiniAddress}, {self.images_identifier})\n'
        return s

    def to_maude_content_manager(self):
        if self.type == 'Client':
            return f'mkCMClient({address_to_maude(self.contentManagerAddress)}, {address_to_maude(self.destiniAddress)}, {address_to_maude(self.masClientAddress)}, 3, {address_to_maude(self.profile)}-ma)\n'
        return f'mkCMServer({address_to_maude(self.contentManagerAddress)}, {address_to_maude(self.destiniAddress)}, {address_to_maude(self.masClientAddress)}, {address_to_maude(self.northbound_address)}, 3, {address_to_maude(self.profile)}-ma)\n'

    def to_maude(self) -> str:
        str = f'---- raceboat {self.type} ----\n'
        str += f'  {self.to_maude_usermodel()}\n'
        str += f'  {self.to_maude_content_manager()}'
        str += f'  {self.to_maude_destini()}'
        str += f'  {self.to_maude_mas_client()}'
        return str

class RaceboatServer(RaceboatClient):
    """
    makeRbServer(serverUserModel, serverContentMgr, serverDestini, bobMasClient, bob)
    makeMastodonClient(bobMasClient,
                     mastodon-server,
                     serverContentMgr)
    --- where
    op makeRbServer : Address Address Address Address Address -> Config .
    eq makeRbServer(userModel:Address,
                    contentMgr:Address,
                    destini:Address,
                    masClient:Address,
                    bob:Address) =
      mkUMactor(userModel:Address, mas-ma, contentMgr:Address)
      mkCMServer(contentMgr:Address, destini:Address, masClient:Address, bob:Address, 3, mas-ma)
      makeDestiniActor(destini:Address, Imls)
    """

    def __init__(self, addressPrefix: str, northbound_address:str, profile: str, destiniObj: Destini, images_identifier: str,
                 mastodon_server: str, X: bool):
        super().__init__(addressPrefix, northbound_address, profile, destiniObj, images_identifier, mastodon_server, X)
        self.type = 'Server'

class RbSendApp:
    """
        makeTxApp(alice, bob, iodineSendApp, clientUserModel, clientContentMgr, file(0, 50) :: file(1,50))
        ---            This    Dest    Iodine  UserModel ContentMgr Contracts
        op makeTxApp : Address Address Address Address   Address    ByteSeqL -> Actor [ctor] .
        eq makeTxApp(AliceAddr:Address,
                   BobAddr:Address,
                   iodine:Address,
                   userModel:Address,
                   contentMgr:Address,
                   contracts:ByteSeqL) =
        < AliceAddr:Address : TxApp |
            destAddr: BobAddr:Address,
            iodineAddr: iodine:Address,
            rbUserModelAddr: userModel:Address,
            rbContentMgrAddr: contentMgr:Address,
            contractCount: 0,
            queue: contracts:ByteSeqL,
            currentCcFile: nilBytes
        > .
    """
    def __init__(self, address:str, toAddress:str, iodineTunAddress: str, rbUMAddress: str, rbCMAddress: str, hashtags:list[str], xfiles: list[XFile], start:bool = True):
        self.address = address_to_maude(address)
        self.toAddress = toAddress
        self.iodineTunAddress = iodineTunAddress
        self.rbUMAddress = rbUMAddress
        self.rbCMAddress = rbCMAddress
        self.hashtags = hashtags
        self.xfiles = xfiles
        self.start = start

    def to_maude_defs(self):
        return f'eq weirdHashtags = {JsonToMaudeParser(None, None).to_maude_jv(self.hashtags)} .'

    def to_maude(self):
        out = f'makeTxApp({address_to_maude(self.address)}, {address_to_maude(self.toAddress)}, {address_to_maude(self.iodineTunAddress)}, {address_to_maude(self.rbUMAddress)}, {address_to_maude(self.rbCMAddress)}, {files_to_maude(self.xfiles)})'
        if self.start == True:
            out += '\n'
            out += f'delayMsgs((to {address_to_maude(self.address)} : start),null)'
        return out


class RbRcvApp:
    """
        makeRxApp(bobapp, iodineBob, serverUserModel, serverContentMgr)
          ---            This    Iodine    UserModel ContentMgr
          op makeRxApp : Address Address   Address   Address -> Actor [ctor] .
          eq makeRxApp(BobAddr:Address, Iodine:Address, rbUserModel:Address, rbContentMgr:Address) =
            < BobAddr:Address : RxApp |
                iodineAddr: Iodine:Address,
                rbUserModelAddr: rbUserModel:Address,
                rbContentMgrAddr: rbContentMgr:Address,
                currentKey: nilBytes,
                currentHash: nilBytes,
                currentHashTag: nilBytes,
                rcvd: emptyFileList
            > .
    """
    def __init__(self, address:str, toAddress:str, iodineTunAddress: str, rbUMAddress: str, rbCMAddress: str, start:bool = True):
        self.address = address_to_maude(address)
        self.toAddress = toAddress
        self.iodineTunAddress = iodineTunAddress
        self.rbUMAddress = rbUMAddress
        self.rbCMAddress = rbCMAddress
        self.start = start

    def to_maude(self):
        out = f'makeRxApp({address_to_maude(self.address)}, {address_to_maude(self.iodineTunAddress)}, {address_to_maude(self.rbUMAddress)}, {address_to_maude(self.rbCMAddress)})'
        if self.start == True:
            out += '\n'
            out += f'delayMsgs((to {address_to_maude(self.address)} : start),null)'
        return out
