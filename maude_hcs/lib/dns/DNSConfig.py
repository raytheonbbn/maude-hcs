from pathlib import Path
import os

from Maude.attack_exploration.src.config import Config

TOPLEVELDIR = Path(os.path.dirname(__file__)).parent.parent
DNS_MAUDE_ROOT = Path("deps/dns_formalization/Maude")
WEIRD_DNS_MAUDE_ROOT = Path(os.path.dirname(__file__)).joinpath(Path("maude/"))
CWD = Path.cwd()

class DNSConfig(Config):
    def __init__(self, clients, resolvers, nameservers, root_nameservers) -> None:
        self.params = {}
        self.path = str(TOPLEVELDIR.joinpath(DNS_MAUDE_ROOT)) + os.path.sep
        self.weirdpath = str(WEIRD_DNS_MAUDE_ROOT)
        super().__init__(clients, resolvers, nameservers, root_nameservers)

    def set_params(self, params : dict):
        self.params = params

    # Override to exclude the monitor
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

    # override update the modules imported
    def to_maude_nondet(self, param_dict, path) -> str:
        res = '\n'.join((
                f'load {self.weirdpath}/iodine_dns',
                #f'load {path}src/nondet-model/dns',
                f'load {path}test/nondet-model/test_helpers',

                '\n--- This maude file has been created automatically from the Python representation.\n',

                'mod IODINE_TEST is\n',
                'inc IODINE_DNS + TEST-HELPERS .\n\n'
        ))

        res += self._to_maude_common_definitions(param_dict)

        res += '--- Initial configuration\n'
        res += 'op initConfig : -> Config .\n'
        res += 'eq initConfig =\n'
        res += '  --- Start messages\n'
        for client in self.clients:
            res += f'  (to {client.address} : start)\n'
        res += self._to_maude_actors()
        res += '  .\n\n'

        res += 'endm\n'
        
        return res        

    def to_maude(self):
        return self.to_maude_nondet(self.params, self.path)

        
