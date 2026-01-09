from enum import Enum

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

class ObservationPattern(Enum):
    LocalToExtPreNat = 'pat("X","addr")'
    ExtToLocalPostNat = 'pat("Z","addr")'
    LocalToExtPostNat = 'pat("addr","Z")'
    ExtToLocalPreNat = 'pat("addr","X")'

class Adversary:
    def __init__(self, address, patternsSent:list[ObservationPattern], patternsReceived:list[ObservationPattern]):
        self.address = address
        self.patternsSent = patternsSent
        self.patternsReceived = patternsReceived

    def to_maude(self):
        return f'mkAdversary({address_to_maude(self.address)}, {" ".join([x.value for x in self.patternsSent])}, {" ".join([x.value for x in self.patternsReceived])})'
