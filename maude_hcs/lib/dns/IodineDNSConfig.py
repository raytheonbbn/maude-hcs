from .DNSConfig import DNSConfig


class IodineDNSConfig(DNSConfig):
    def __init__(self, applications, weird_networks, clients, resolvers, nameservers, root_nameservers) -> None:        
        self.applications = applications
        self.tunnels = weird_networks
        super().__init__(clients, resolvers, nameservers, root_nameservers)

    # Override to add tunnels and applications to conf
    def _to_maude_actors(self) -> str:
        res = super()._to_maude_actors()
        
        res = '  --- tunnels\n'
        for tunnel in self.tunnels:
            res += '  ' + tunnel.to_maude() + '\n'
        
        res = '  --- applications\n'
        for application in self.applications:
            res += '  ' + application.to_maude() + '\n'
