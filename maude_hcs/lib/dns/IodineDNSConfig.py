from .DNSConfig import DNSConfig


class IodineDNSConfig(DNSConfig):
    def __init__(self, application, tunnel, clients, resolvers, nameservers, root_nameservers) -> None:        
        self.application = application
        self.tunnel = tunnel
        super().__init__(clients, resolvers, nameservers, root_nameservers)
