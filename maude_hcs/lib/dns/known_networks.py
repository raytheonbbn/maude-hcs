from .corporate import corporate

class KnownUNetworks:
    def __init__(self):        
        self.constructors = {
            'corporate_base': self._fixed_network(corporate),
            'corporate_iodine': self._fixed_network(corporate)
        }
    
    def create(self, run_args):        
        conf = self.constructors[run_args["name"]](run_args)
        return conf
    
    def _fixed_network(self, Cls):
        def make(run_args):
            conf = Cls(run_args)
            return conf
        return make
    

