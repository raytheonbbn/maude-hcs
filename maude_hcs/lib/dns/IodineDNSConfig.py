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
import logging
import traceback

from Maude.attack_exploration.src.conversion_utils import address_to_maude
from numpy.f2py.cfuncs import includes

from .DNSConfig import DNSConfig
from .iodineActors import IodineServer, SendApp, PacedClient, ReceiveApp, TGenClient, DNSTGenClient
from pathlib import Path

from .. import GLOBALS
from ..common.commonActors import AdversaryActor
from ..mastodon.mastodonActors import MASTGenClient
from ..raceboat.raceboatActors import RaceboatClient, RaceboatServer, RbSendApp
from ...parsers.markovJsonToMaudeParser import find_recursively
logger = logging.getLogger(__name__)

class IodineDNSConfig(DNSConfig):
    def __init__(self, standaloneActors, monitor, applications, weird_networks, clients, paced_clients, resolvers, nameservers, root_nameservers, network) -> None:
        self.standaloneActors = standaloneActors
        self.monitor = monitor
        self.paced_clients = paced_clients
        self.applications = applications
        self.tunnels = weird_networks
        super().__init__(clients, resolvers, nameservers, root_nameservers, network)
        self.common_path = Path(self.weirdpath).parent.parent.joinpath('common').joinpath('maude')

    def _get_actor_addresses(self):
        addresses = super()._get_actor_addresses()
        addresses.append(self.monitor.address)
        for router in self.standaloneActors:
            if router.address:
                addresses.append(router.address)
        for client in self.paced_clients:
            addresses.append(client.address)
            if isinstance(client, TGenClient):
                addresses += client.getAddresses()
        for app in self.applications:
            addresses.append(app.address)
        for actor in self.tunnels:
            addresses.append(actor.address)
            if isinstance(actor, RaceboatClient) or isinstance(actor, RaceboatServer):
                addresses.append(actor.userModelAddress)
                addresses.append(actor.contentManagerAddress)
                addresses.append(actor.destiniAddress)
                addresses.append(actor.masClientAddress)
        return sorted(set(addresses))
    
    def _get_zones(self):        
        zones = super()._get_zones()
        """
        Also include zones from any weird name servers
        return set([zone for zonelist in map(lambda ns: ns.zones, self.nameservers) for zone in zonelist])
        """        
        for actor in self.tunnels:
            if isinstance(actor, IodineServer):
                zones = zones.union(set(actor.zones))
        return zones

    def _to_maude_common_definitions(self, param_dict) -> str:
        defs = super()._to_maude_common_definitions(param_dict)
        # Tgen actors and raceboat/destini have image list defs, include here
        new_defs = set()
        for client in sorted(self.paced_clients, key=lambda x: x.address):
            if isinstance(client, MASTGenClient):
                _d = client.to_maude_defs()
                if _d.strip():
                    new_defs.add(_d)
        for tun in sorted(self.tunnels, key=lambda x: x.address):
            if isinstance(tun, RaceboatClient):
                _d = tun.to_maude_defs()
                if _d.strip():
                    new_defs.add(_d)
        for app in sorted(self.applications, key=lambda x: x.address):
            if isinstance(app, RbSendApp):
                _d = app.to_maude_defs()
                if _d.strip():
                    new_defs.add(_d)
        for actr in self.standaloneActors:
            if isinstance(actr, AdversaryActor):
                _d = actr.to_maude_defs()
                if _d.strip():
                    new_defs.add(_d)
        defs += '\n'.join(sorted(new_defs))
        defs += '\n'
        return defs

    # Override
    def _maude_loads(self, path, model):
        # sload ../../../mastodon/maude/probabilistic/mastodon
        # sload ../../../app/maude/probabilistic

        if model == 'prob':
            res = '--- This maude file has been created automatically from the Python representation ---\n'
            res += '\n'.join([
                f'sload {self.weirdpath}/probabilistic/iodine_dns',
                f'sload {Path(self.weirdpath).parent.parent.joinpath('tgen').joinpath('maude').joinpath('dnsTgen-actor-uniqueId')}\n'
                # f'sload {path}test/probabilistic-model/test_helpers',
                f'sload {self.common_path}/user-action-actor\n'
                f'sload {Path(self.weirdpath).parent.parent.joinpath('tgen').joinpath('maude').joinpath('masTGen.maude')}\n'
                f'sload {Path(self.weirdpath).parent.parent.joinpath('mastodon').joinpath('maude').joinpath('probabilistic').joinpath('mastodon')}',
                f'sload {Path(self.weirdpath).parent.parent.joinpath('app').joinpath('maude').joinpath('probabilistic-no-rb')}',
                f'sload {Path(self.weirdpath).parent.parent.joinpath('raceboat').joinpath('rb-cm-client-hash')}',
                f'sload {Path(self.weirdpath).parent.parent.joinpath('raceboat').joinpath('rb-cm-server')}',
                f'sload {Path(self.weirdpath).parent.parent.joinpath('raceboat').joinpath('enc-dec-actor')}',
                f'sload {Path(self.weirdpath).parent.parent.joinpath('common').joinpath('maude').joinpath('http-overhead')}',
                f'sload {self.common_path}/router',
                f'sload {self.common_path}/adversary-observer'
            ])
            tgen_loads = set()
            for tc in self.paced_clients:
                if isinstance(tc, TGenClient):
                    # we change the mmodel file when we create the maude name so change it back
                    mod = '_'.join(tc.profile.replace('-', '_').split('_')[1:])
                    key = None # since dns and mastodon profiles can use same names, key is used to distinguish
                    if isinstance(tc, MASTGenClient):
                        key = 'mastodonprofiles'
                    elif isinstance(tc, DNSTGenClient):
                        key = 'dnsprofiles'
                    file = find_recursively(GLOBALS.TOPLEVELDIR, f'{mod}.maude', key=key)
                    tgen_loads.add(f'sload {file}')
            rb_loads = set()
            for actor in self.tunnels:
                if isinstance(actor, RaceboatClient) or isinstance(actor, RaceboatServer):
                    mod = '_'.join(actor.profile.replace('-', '_').split('_')[1:])
                    try:
                        file = find_recursively(GLOBALS.TOPLEVELDIR, f'{mod}.maude')
                        rb_loads.add(f'sload {file}')
                    except:
                        logger.warning(f'Could not find {mod}.maude. Exception {traceback.format_exc()}')

            if tgen_loads:
                res += '\n ---- tgen models\n'
                res += '\n'.join(sorted(tgen_loads))
            if rb_loads:
                res += '\n ---- raceboat models\n'
                res += '\n'.join(sorted(rb_loads))

            return res

    # override
    def _maude_includes(self, params, path, model):
        #           'inc MASTODON .',
        #           'inc MAS-TGEN .',
        #           'inc CP2_APP .',

        includes = [
          ' inc DNS .',
          ' inc USER-ACTION-ACTOR .',
          ' inc DNS-TGEN .',
          ' inc IODINE_DNS . --- + TEST-HELPERS .',
          ' inc ROUTER .',
          ' inc MASTODON .',
          ' inc MAS-TGEN .',
          ' inc ADVERSARY-OBSERVER .',
          ' inc CP2_APP .',
            'inc ENC-DEC .',
            'inc CONTENT-MANAGER-CLIENT .',
            'inc CONTENT-MANAGER-SERVER .',
            'inc HTTP-OVERHEAD .'

        ]
        if model == 'prob':
            res = '\n'.join(includes)
            # TGEN models
            tgen_incs = set()
            for tc in self.paced_clients:
                if isinstance(tc, TGenClient):
                    tgen_incs.add(f' inc {tc.profile.upper()}-MAMODEL .')
            if tgen_incs:
                res += '\n ---- tgen model includes\n'
                res += '\n'.join(sorted(tgen_incs))
                # res += '\n'
            # Raceboat models
            rb_incs = set()
            for actor in self.tunnels:
                if isinstance(actor, RaceboatClient) or isinstance(actor, RaceboatServer):
                    rb_incs.add(f' inc {actor.profile.upper()}-MAMODEL .')
            if rb_incs:
                res += '\n ---- raceboat model includes\n'
                res += '\n'.join(sorted(rb_incs))
                res += '\n'
            return res

    # Override to add tunnels and applications to conf
    def _to_maude_actors(self) -> str:
        res = super()._to_maude_actors()
        res += '  --- standalone actors\n'
        for router in self.standaloneActors:
            res += '  ' + router.to_maude() + '\n'
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
            res += '  --- tgens \n'
            for client in self.paced_clients:
                res += '  ' + client.to_maude() + '\n'
                if client.start:
                    res += f'  [genRandom(0.0, 0.0001), to {address_to_maude(client.address)} : start, 0]\n'
            res += '  --- App start messages\n'
            for app in self.applications:
                if isinstance(app, SendApp) and app.start >= 0:
                    res += f'  [{str(app.start)}, (to {address_to_maude(app.address)} : start), 0] \n'
                if isinstance(app, ReceiveApp) and app.start >= 0: # TODO: testing for Bob also add start messages for RecvApp
                    res += f'  [1.0, (to {address_to_maude(app.address)} : start), 0] \n'
        elif self.model_type == 'nondet':
            res += '  --- App start messages\n'
            for app in self.applications:
                if isinstance(app, SendApp):
                    res += f'  (to {address_to_maude(app.address)} : start) \n'
        
        return res
