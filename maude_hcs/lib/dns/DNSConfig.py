from pathlib import Path
import os

from Maude.attack_exploration.src.config import Config

TOPLEVELDIR = Path(os.path.dirname(__file__)).parent.parent
DNS_MAUDE_ROOT = Path("deps/dns_formalization/Maude")
CWD = Path.cwd()

class DNSConfig(Config):
    def __init__(self, clients, resolvers, nameservers, root_nameservers) -> None:
        self.params = {}
        self.path = str(TOPLEVELDIR.joinpath(DNS_MAUDE_ROOT)) + os.path.sep
        super().__init__(clients, resolvers, nameservers, root_nameservers)

    def set_params(self, params : dict):
        self.params = params

    # Override to not exclude the monitor
    def _to_maude_actors(self) -> str:
        res = '  --- Clients\n'
        for client in self.clients:
            res += '  ' + client.to_maude() + '\n'

        res += '  --- Resolvers\n'
        for resolver in self.resolvers:
            res += '  ' + resolver.to_maude() + '\n'

        res += '  --- Nameservers\n'
        for nameserver in self.nameservers:
            res += '  ' + nameserver.to_maude() + '\n'
        return res


    def to_maude(self):
        return self.to_maude_nondet(self.params, self.path)

        
