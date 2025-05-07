# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# PWNDD Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# Contract No: HR00112590083
# Contractor Name: RTX BBN Technologies Inc.
# Contractor Address: 10 Moulton Street, Cambridge, Massachusetts 02138
#
# The U.S. Government's rights to use, modify, reproduce, release, perform,
# display, or disclose these technical data and software are defined in the
# Article VII: Data Rights clause of the OTA.
#
# This document does not contain technology or technical data controlled under
# either the U.S. International Traffic in Arms Regulations or the U.S. Export
# Administration Regulations.
#
# DISTRIBUTION STATEMENT A: Approved for public release; distribution is
# unlimited.
#
# Notice: Markings. Any reproduction of this computer software, computer
# software documentation, or portions thereof must also reproduce the markings
# contained herein.
#
# MAUDE_HCS: end

from pathlib import Path
import os
from maude_hcs.lib import GLOBALS
from Maude.attack_exploration.src.config import Config
from .cache import ResolverCache

TOPLEVELDIR = Path(os.path.dirname(__file__)).parent.parent
DNS_MAUDE_ROOT = Path("deps/dns_formalization/Maude")
WEIRD_DNS_MAUDE_ROOT = Path(os.path.dirname(__file__)).joinpath(Path("maude/"))
CWD = Path.cwd()

class DNSConfig(Config):
    def __init__(self, clients, resolvers, nameservers, root_nameservers) -> None:
        self.nondet_params = {}
        self.prob_params = {}
        self.model_type = GLOBALS.MODEL_TYPES[0]
        self.path = str(TOPLEVELDIR.joinpath(DNS_MAUDE_ROOT)) + os.path.sep
        self.weirdpath = str(WEIRD_DNS_MAUDE_ROOT)
        super().__init__(clients, resolvers, nameservers, root_nameservers)

    def set_params(self, nondet_params : dict, prob_params : dict):
        self.nondet_params = nondet_params
        self.prob_params = prob_params
    
    def set_model_type(self, type):
        if not type in GLOBALS.MODEL_TYPES:
            raise Exception(f'Type {type} must be in {GLOBALS.MODEL_TYPES}')
        self.model_type = type

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
    
    def _to_maude_caches(self) -> str:
        res = '--- Caches\n'
        for resolver in self.resolvers:
            if resolver.cache:
                res += resolver.cache.to_maude() + '\n'
        return res
   
    # override update the modules imported
    def to_maude_nondet(self, param_dict, path) -> str:
        res = '\n'.join((
                f'load {self.weirdpath}/nondet/iodine_dns',
                #f'load {path}src/nondet-model/dns',
                f'load {path}test/nondet-model/test_helpers',

                '\n--- This maude file has been created automatically from the Python representation.\n',

                'mod IODINE_TEST is\n',
                'inc IODINE_DNS + TEST-HELPERS .\n\n'
        ))

        res += self._to_maude_common_definitions(param_dict)
        res += self._to_maude_caches()

        res += '--- Initial configuration\n'
        res += 'op initConfig : -> Config .\n'
        res += 'eq initConfig =\n'
        res += '  --- Client start messages\n'
        for client in self.clients:            
            res += f'  (to {client.address} : start)\n'
            
        res += self._to_maude_actors()
        res += '  .\n\n'
        
        res += 'endm\n'        
        return res        

    def to_maude_prob(self, param_dict, path) -> str:
        res = '\n'.join((
                f'load {self.weirdpath}/probabilistic/iodine_dns',                
                f'load {path}test/probabilistic-model/test_helpers',

                '\n--- This maude file has been created automatically from the Python representation.\n',

                'mod IODINE_TEST is\n',
                'inc IODINE_DNS + TEST-HELPERS .\n\n'
        ))

        res += self._to_maude_common_definitions(param_dict)
        res += self._to_maude_caches()
        res += '--- Initial configuration\n'
        res += 'op initState : -> Config .\n'
        res += 'eq initState =\n'
        res += '  --- Client start messages\n'
        for client in self.clients:            
            res += f'  [id, (to {client.address} : start), 0]\n'
        res += self._to_maude_actors()
        res += '  .\n\n'
        
        res += '\n'
        res += 'op initConfig : -> Config .\n'
        res += 'eq initConfig = run({0.0 | nil} initState,limit) .\n'
        res += 'endm\n'
        return res       

    def to_maude(self):
        if self.model_type == 'nondet':
            return self.to_maude_nondet(self.nondet_params, self.path)
        if self.model_type == 'prob':
            params = self.nondet_params.copy()
            params.update(self.prob_params)
            return self.to_maude_prob(params, self.path)
        raise Exception(f"Illegal model type {self.model_type}. Can either be nondet or prob.")

        
