from Maude.attack_exploration.src.conversion_utils import address_to_maude

class Packet:
    #   ----        AliceAddr BobAddr Packet# DataLenBytes
    def __init__(self, fromAddress, toAddress, sequenceNum : int, lenBytes : int, lastPacket : bool) -> None:
        self.address = fromAddress
        self.toAddress = toAddress
        self.seqNum = sequenceNum
        self.lenBytes = lenBytes
        # Indicates if this is the last packet of a file transfer.
        self.lastPacket = lastPacket

    def __str__(self) -> str:
        return f'packet({self.address}, {self.toAddress}, {self.seqNum}, {self.lenBytes}, {self.lastPacket})'

    def to_maude(self) -> str:
        return f'packet({address_to_maude(self.address)}, {address_to_maude(self.toAddress)}, {self.seqNum}, {self.lenBytes}, {str(self.lastPacket).lower()})'
