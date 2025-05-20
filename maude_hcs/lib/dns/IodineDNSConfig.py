from Maude.attack_exploration.src.conversion_utils import address_to_maude
from .DNSConfig import DNSConfig
from .iodineActors import IodineServer, SendApp

class IodineDNSConfig(DNSConfig):
    def __init__(self, monitor, applications, weird_networks, clients, resolvers, nameservers, root_nameservers, network) -> None:
        self.monitor = monitor
        self.applications = applications
        self.tunnels = weird_networks
        super().__init__(clients, resolvers, nameservers, root_nameservers, network)

    def _get_actor_addresses(self):
        addresses = super()._get_actor_addresses()
        addresses.append(self.monitor.address)
        for app in self.applications:
            addresses.append(app.address)
        for actor in self.tunnels:
            addresses.append(actor.address)
            if isinstance(actor, IodineServer):
                addresses.append(actor.nameServer.address)
        return sorted(set(addresses))
    
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
        
        # add the start messages if requested
        # include the monitor for the quantitative analysis        
        if self.model_type == 'prob':
            res += '  --- WMonitor\n'
            res += '  ' + self.monitor.to_maude() + '\n'
            res += '  --- App start messages\n'
            for app in self.applications:
                if isinstance(app, SendApp) and app.start >= 0:
                    res += f'  [{str(app.start)}, (to {address_to_maude(app.address)} : start), 0] \n'
        elif self.model_type == 'nondet':
            res += '  --- App start messages\n'
            for app in self.applications:
                if isinstance(app, SendApp):
                    res += f'  (to {address_to_maude(app.address)} : start) \n'
        
        return res
