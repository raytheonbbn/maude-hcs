from .packet import Packet

def packetlist_to_maude(packets) -> str:
    if not packets:
        return 'mtpl'
    else:
        return ' ; '.join(map(lambda p: p.to_maude(), packets))
    
def makePackets(address, sizeList : list, startSeqNum = 0) -> list:    
    indeces = list(range(startSeqNum, startSeqNum + len(sizeList)))
    return [Packet(address, index, L) for L, index in zip(sizeList, indeces)]