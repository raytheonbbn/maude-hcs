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

    def to_maude(self):
        return self.to_maude_nondet(self.params, self.path)

        
