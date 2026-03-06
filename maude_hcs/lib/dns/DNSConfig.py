# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# Maude-HCS Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# The computer software and computer software documentation are licensed
# under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. A copy of the License
# is provided in the LICENSE file, but you may obtain a copy of the
# License at:  https://www.apache.org/licenses/LICENSE-2.0
#
# The computer software and computer software documentation are based
# upon work supported by the Defense Advanced Research Projects Agency (DARPA)
# under Agreement No. HR00l 12590083.
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
# contained herein. Refer to the provided NOTICE file.
#
# MAUDE_HCS: end

from pathlib import Path
import os
from maude_hcs.lib import GLOBALS, flatten
from Maude.attack_exploration.src.config import Config
from Maude.attack_exploration.src.conversion_utils import address_to_maude
from .cache import ResolverCache

TOPLEVELDIR = Path(os.path.dirname(__file__)).parent.parent
DNS_MAUDE_ROOT = Path("deps/dns_formalization/Maude")
WEIRD_DNS_MAUDE_ROOT = Path(os.path.dirname(__file__)).joinpath(Path("maude/"))

CWD = Path.cwd()

class DNSConfig(Config):
    def __init__(self, clients, resolvers, nameservers, root_nameservers, network, output_dir) -> None:
        self.nondet_params = {}
        self.prob_params = {}
        self.model_type = GLOBALS.MODEL_TYPES[0]
        self.path = str(TOPLEVELDIR.joinpath(DNS_MAUDE_ROOT)) + os.path.sep
        self.weirdpath = str(WEIRD_DNS_MAUDE_ROOT)
        self.preamble = None
        self.output_dir = output_dir
        super().__init__(clients, resolvers, nameservers, root_nameservers, network)

    def set_params(self, nondet_params : dict, prob_params : dict):
        self.nondet_params = nondet_params
        self.prob_params = prob_params
    
    def set_model_type(self, type):
        if not type in GLOBALS.MODEL_TYPES:
            raise Exception(f'Type {type} must be in {GLOBALS.MODEL_TYPES}')
        self.model_type = type

    def set_preamble(self, L: list[str] = []):
        self.preamble = L

    def _to_maude_common_definitions(self, param_dict) -> str:
        res = 'eq monitorQueryLog? = true .\n\n'

        for param, val in param_dict.items():
            if isinstance(val, str):
                res += f'eq {param} = {val} .\n'
            else:
                res += f'eq {param} = {str(val).lower()} .\n'

        res += '\n'

        res += self._get_addr_ops() + '\n'
        res += self._get_sbelt() + '\n'
        res += self._to_maude_zones()
        return res

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

    def _maude_loads(self, path, model):
        if model == 'nondet':
            return '\n'.join((
                '--- This maude file has been created automatically from the Python representation ---\n',
                f'load {self.weirdpath}/nondet/iodine_dns',
                # f'load {path}src/nondet-model/dns',
                f'load {path}test/nondet-model/test_helpers'
            ))
        elif model == 'prob':
            res = '--- This maude file has been created automatically from the Python representation ---\n'
            res += '\n'.join((
                f'load {self.weirdpath}/probabilistic/iodine_dns',
                f'load {self.weirdpath}/probabilistic/paced-client\n'
                f'load {path}test/probabilistic-model/test_helpers\n',
            ))
            return res
        return None

    def _maude_includes(self, param_dict, path, model) -> str:
        if model == 'nondet':
            return 'inc IODINE_DNS + TEST-HELPERS .\n\n'
        elif model == 'prob':
            return 'inc IODINE_DNS + PACED-CLIENT + TEST-HELPERS .\n\n'


    # override update the modules imported
    def to_maude_nondet(self, param_dict, path) -> str:
        res = self._maude_loads(path, 'nondet')
        # add preamble 
        res += '\n'
        res += '\n'.join([pr for pr in self.preamble])
        res += '\n\n'
        
        # define module
        res += f'mod {GLOBALS.MODULE_NAME} is\n'
        # define includes
        res += self._maude_includes(param_dict, path, 'nondet')

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
        res = self._maude_loads(path, 'prob')
        res += '\n'

        # add preamble 
        res += '\n'
        res += '\n'.join([pr for pr in self.preamble])
        res += '\n\n'

        # define module
        res += f'mod {GLOBALS.MODULE_NAME} is\n'
        # define includes
        res += self._maude_includes(param_dict, path, 'prob')

        res += self._to_maude_common_definitions(flatten(param_dict))
        res += self._to_maude_caches()
        res += '--- Initial configuration\n'
        res += 'op initState : -> Config .\n'
        res += 'eq initState =\n'
        res += '  --- Client start messages\n'
        for client in self.clients:            
            res += f'  [id, (to {client.address} : start), 0]\n'
        res += self._to_maude_actors()
        res += '  .\n\n'
        
        res += self.network.to_maude_network()
        res += '\n'
        res += 'op initConfig : -> Config .\n'
        res += 'eq initConfig = run({0.0 | nil} initState,slimit) .\n'
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

        
