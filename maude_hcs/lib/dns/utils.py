from .packet import Packet

def packetlist_to_maude(packets) -> str:
    if not packets:
        return 'mtpl'
    else:
        return ' ; '.join(map(lambda p: p.to_maude(), packets))
    
def makePackets(address, sizeList : list, startSeqNum = 0) -> list:    
    indeces = list(range(startSeqNum, startSeqNum + len(sizeList)))
    isLastList = [False for index in indeces]
    isLastList[-1] = True
    return [Packet(address, index, L, isLast) for L, index, isLast in zip(sizeList, indeces, isLastList)]
