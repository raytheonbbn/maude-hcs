import math
from enum import Enum
from typing import List, Dict, Any

from maude_hcs.deps.dns_formalization.Maude.attack_exploration.src.conversion_utils import address_to_maude

"""
local actor sends to external actor, corp side 
  pat("X","addr") .
messages from external actor to corporate actor postNat
  pat("Z","addr")  
local actor sends to external actor, ext side  
  pat("addr","Z") .
messages from external actor to corporate actor preNat
  pat("addr","X")
 

"""
from Maude.attack_exploration.src.query import Query

class Msg:
    def __init__(self, to_addr: str, from_addr: str, query: Query):
        self.to_addr = to_addr
        self.from_addr = from_addr
        self.query = query
    def copy(self):
        return Msg(self.to_addr, self.from_addr, Query(self.query.id, self.query.qname, self.query.qtype))

    def to_maude(self) -> str:
        s = self.query.to_maude()
        return f"to {self.to_addr} from {self.from_addr} : {self.query.to_maude()}"


class TimeMsg:
    def __init__(self, time: float, msg: Msg):
        self.time = time
        self.msg = msg

    def to_maude(self) -> str:
        return f"tm({self.time}, {self.msg.to_maude()})"


class TimeMsgList:
    def __init__(self, msgs: List[TimeMsg]):
        self.msgs = msgs

    def to_maude(self) -> str:
        if not self.msgs:
            return "nilTML"
        return " ; ".join([m.to_maude() for m in self.msgs])

class ObservationPattern(Enum):
    LocalToExtPreNat = 'pat("X","addr")'
    ExtToLocalPostNat = 'pat("Z","addr")'
    LocalToExtPostNat = 'pat("addr","Z")'
    ExtToLocalPreNat = 'pat("addr","X")'

class AdversaryActor:
    def __init__(self, address, patternsSent:list[ObservationPattern], patternsReceived:list[ObservationPattern],  baselineBins: TimeMsgList):
        self.address = address
        self.patternsSent = patternsSent
        self.patternsReceived = patternsReceived
        self.baselineBins = baselineBins

    def to_maude(self):
        return f'mkAdversary({address_to_maude(self.address)}, {" ".join([x.value for x in self.patternsSent])}, {" ".join([x.value for x in self.patternsReceived])}, {self.baselineBins.to_maude()})'

def generateBaselineBins(baselineBins: Dict[str, Any], measure: str, binSize: float, maxWindowSize: float, msg:Msg, xform) -> TimeMsgList:
    """
    Generates a TimeMsgList of messages based on the baseline bins for a given measure.

    Args:
        measure: The key to look up in baselineBins (e.g. 'dns_request')
        binSize: The size of each time bin in seconds
        maxWindowSize: The total duration to cover in seconds

    Returns:
        TimeMsgList containing the generated messages
    """
    num_bins = int(maxWindowSize / binSize)
    msgs = []

    # Get the bins data for the measure
    measure_bins = baselineBins.get('bins', {}).get(measure, [])
    measure_bytes_bins = baselineBins.get('bins', {}).get(f'{measure}_bytes', [])
    if measure_bytes_bins:
        assert len(measure_bytes_bins) == len(measure_bins), f'{measure} array has different size than {measure}_bytes array in baseline data, {len(measure_bytes_bins)} != {len(measure_bins)}'
    # if we have more bins only keep the last nbins
    if len(measure_bins) > num_bins:
        measure_bins = measure_bins[-num_bins:]
        measure_bytes_bins = measure_bytes_bins[-num_bins:]
    # Convert list of lists [[idx, val], ...] to dict for easier lookup
    # bin_data = {item[0]: item[1] for item in measure_bins}
    # Iterate backwards from the last bin
    for i in range(num_bins - 1, -1, -1):
        # count = bin_data.get(i, 0)
        idx = measure_bins[i][0]
        count = measure_bins[i][1]
        per_msg_bytes = 0
        if measure_bytes_bins and count > 0:
            per_msg_bytes = math.ceil(measure_bytes_bins[i][1] / count)

        T_i = i * binSize

        # Generate N messages for this bin
        for m in range(count - 1, -1, -1):
            # Calculate time: T_i + (binSize / 2) + c*m
            t = T_i + (binSize / 2.0) + (0.001 * m)
            tm = TimeMsg(t, xform(msg, per_msg_bytes))
            msgs.insert(0, tm)

    return TimeMsgList(msgs)