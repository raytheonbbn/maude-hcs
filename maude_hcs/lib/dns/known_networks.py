from .corporate import corporate

class KnownUNetworks:
    def __init__(self):        
        self.constructors = {
            'corporate-base': self._fixed_network(corporate)
        }
    
    def create(self, run_args):
        args = run_args["underlying_network"].get(run_args["underlying_network"]["config"], {})
        conf = self.constructors[run_args["underlying_network"]["config"]](args)
        return conf
    
    def _fixed_network(self, Cls):
        def make(run_args):
            conf = Cls(run_args)
            return conf
        return make
    

