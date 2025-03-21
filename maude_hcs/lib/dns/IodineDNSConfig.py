from .DNSConfig import DNSConfig
from .iodineActors import IodineServer

class IodineDNSConfig(DNSConfig):
    def __init__(self, applications, weird_networks, clients, resolvers, nameservers, root_nameservers) -> None:        
        self.applications = applications
        self.tunnels = weird_networks
        super().__init__(clients, resolvers, nameservers, root_nameservers)

    def _get_zones(self):        
        zones = super()._get_zones()
        """
        Also include zones from any weird name servers
        return set([zone for zonelist in map(lambda ns: ns.zones, self.nameservers) for zone in zonelist])
        """        
        for actor in self.tunnels:
            if isinstance(actor, IodineServer):
                zones = zones.union(set(actor.nameServer.zones))
        return zones
    
    # Override to add tunnels and applications to conf
    def _to_maude_actors(self) -> str:        
        res = super()._to_maude_actors()        
        res += '  --- tunnels\n'
        for tunnel in self.tunnels:
            res += '  ' + tunnel.to_maude() + '\n'
        
        res += '  --- applications\n'
        for application in self.applications:
            res += '  ' + application.to_maude() + '\n'
        return res
