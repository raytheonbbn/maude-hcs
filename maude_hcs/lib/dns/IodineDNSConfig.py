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

from Maude.attack_exploration.src.conversion_utils import address_to_maude
from .DNSConfig import DNSConfig
from .iodineActors import IodineServer, SendApp, PacedClient

class IodineDNSConfig(DNSConfig):
    def __init__(self, monitor, applications, weird_networks, clients, paced_clients, resolvers, nameservers, root_nameservers, network) -> None:
        self.monitor = monitor
        self.paced_clients = paced_clients
        self.applications = applications
        self.tunnels = weird_networks
        super().__init__(clients, resolvers, nameservers, root_nameservers, network)

    def _get_actor_addresses(self):
        addresses = super()._get_actor_addresses()
        addresses.append(self.monitor.address)
        for client in self.paced_clients:        
            addresses.append(client.address)
        for app in self.applications:
            addresses.append(app.address)
        for actor in self.tunnels:
            addresses.append(actor.address)
            if isinstance(actor, IodineServer):
                addresses.append(actor.nameServer.address)
        return sorted(set(addresses))
    
    def _get_zones(self):        
        zones = super()._get_zones()
        """
        Also include zones from any weird name servers
        return set([zone for zonelist in map(lambda ns: ns.zones, self.nameservers) for zone in zonelist])
        """        
        for actor in self.tunnels:
            if isinstance(actor, IodineServer):
                zones = zones.union(set(actor.nameServer.zones))
        return zones
    
    # Override to add tunnels and applications to conf
    def _to_maude_actors(self) -> str:
        res = super()._to_maude_actors()        
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
            for client in self.paced_clients:
                res += '  ' + client.to_maude() + '\n'
                res += f'  [genRandom(0.0, 0.0001), to {address_to_maude(client.address)} : start, 0]\n'
            res += '  --- App start messages\n'
            for app in self.applications:
                if isinstance(app, SendApp) and app.start >= 0:
                    res += f'  [{str(app.start)}, (to {address_to_maude(app.address)} : start), 0] \n'
        elif self.model_type == 'nondet':
            res += '  --- App start messages\n'
            for app in self.applications:
                if isinstance(app, SendApp):
                    res += f'  (to {address_to_maude(app.address)} : start) \n'
        
        return res
