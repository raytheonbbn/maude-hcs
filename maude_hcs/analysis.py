import json
import logging
from maude_hcs.lib.dns.known_networks import KnownUNetworks

logger = logging.getLogger(__name__)

class HCSAnalysis:
    def __init__(self, args):
        self.args = args

    def generate(self):
        # step 1. generate the network configuration 
        self.conf = self.generate_network()
        return self.conf

    def run(self):
        pass
        

    def generate_network(self):
        conf = KnownUNetworks().create(self.args)
        return conf


