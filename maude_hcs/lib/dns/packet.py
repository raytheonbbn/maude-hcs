from Maude.attack_exploration.src.conversion_utils import address_to_maude

class Packet:
    #   ----        AliceAddr Packet# DataLenBytes  
    #   op packet : Address Nat Nat -> Packet .
    def __init__(self, address, sequenceNum : int, lenBytes : int) -> None:
        self.address = address
        self.seqNum = sequenceNum
        self.lenBytes = lenBytes

    def __str__(self) -> str:
        return f'packet({self.address}, {self.seqNum}, {self.lenBytes})'

    def to_maude(self) -> str:
        return f'packet({address_to_maude(self.address)}, {self.seqNum}, {self.lenBytes})'