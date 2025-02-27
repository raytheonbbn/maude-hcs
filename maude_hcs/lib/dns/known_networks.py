from maude_hcs.lib.dns.DNSConfig import DNSConfig

from Maude.attack_exploration.src.zone import Record, Zone
from Maude.attack_exploration.src.actors import Resolver, Nameserver
from Maude.attack_exploration.src.conversion_utils import config_to_maude_file

class KnownUNetworks:
    def __init__(self):        
        self.constructors = {
            'corporate-base': self._fixed_network(corporate)
        }
    
    def create(self, run_args):
        conf = self.constructors[run_args["underlying_network"]["config"]](run_args)        
        return conf
    
    def _fixed_network(self, Cls):
        def make(run_args):
            conf = Cls(run_args)
            return conf
        return make
    

def corporate(args) -> DNSConfig:
    
    # root zone
    zoneRoot = Zone('', None,
        [
            # zone apex
            Record('', 'SOA', 3600, '3600'),
            Record('', 'NS', 3600, 'a.root-servers.net.'),

            # delegations and glue
            Record('a.root-servers.net.', 'A', 3600, 'addrNSroot'),
            Record('com.', 'NS', 3600, 'ns.com.'),
            Record('ns.com.', 'A', 3600, 'addrNScom'),
            Record('net.', 'NS', 3600, 'ns.net.'),
            Record('ns.net.', 'A', 3600, 'addrNSnet'),
        ])

    # com zone
    zoneCom = Zone('com.', zoneRoot,
        [
            Record('com.', 'SOA', 3600, '3600'),
            Record('com.', 'NS', 3600, 'ns.com.'),
            Record('ns.com.', 'A', 3600, 'addrNScom'),

            # delegations and glue
            Record('example.com.', 'NS', 3600, 'ns.example.com.'),
            Record('ns.example.com.', 'A', 3600, 'addrNSexample'),
        ])

    zoneNet = Zone('net.', zoneRoot,
        [
            Record('net.', 'SOA', 3600, '3600'),
            Record('net.', 'NS', 3600, 'ns.net.'),
            Record('ns.net.', 'A', 3600, 'addrNSnet'),

            # delegations and glue
            Record('root-servers.net.', 'NS', 3600, 'a.root-servers.net.'),
            Record('a.root-servers.net.', 'A', 3600, 'addrNSroot'),
        ])

    zoneRootServers = Zone('root-servers.net.', zoneNet,
        [
            Record('root-servers.net.', 'SOA', 3600, '3600'),
            Record('root-servers.net.', 'NS', 3600, 'a.root-servers.net.'),
            Record('a.root-servers.net.', 'A', 3600, 'addrNSroot'),
        ])

    # example.com zone
    zoneExample = Zone('example.com.', zoneCom,
        [ 
            Record('example.com.', 'SOA', 3600, '3600'),
            Record('example.com.', 'NS', 3600, 'ns.example.com.'),
            Record('ns.example.com.', 'A', 3600, 'addrNSexample'),
            Record('www.example.com.', 'A', 3600, '1.2.3.4'),
            Record('*.example.com.', 'TXT', 3600, '...'),
        ])

    resolver = Resolver('rAddr')

    nameserverRoot = Nameserver('addrNSroot', [zoneRoot, zoneRootServers])
    nameserverCom = Nameserver('addrNScom', [zoneCom])
    nameserverNet = Nameserver('addrNSnet', [zoneNet])
    nameserverExample = Nameserver('addrNSexample', [zoneExample])

    root_nameservers = {'a.root-servers.net.': 'addrNSroot'}

    return DNSConfig([], [resolver], [nameserverRoot, nameserverCom, nameserverNet, nameserverExample], root_nameservers)