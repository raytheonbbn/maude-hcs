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

from Maude.attack_exploration.src.zone import Record

class ResolverCache:

    def __init__(self, name, entries) -> None:
        self.name = name        
        self.entries = entries    

    # op rsvCache : -> Cache .
    def to_maude(self):
        assert self.entries, "Cache has no records"
        
        res = f'op {self.name} : -> Cache .\n'
        res += f'eq {self.name} ='
        for record in self.entries:
            res += f'\n  {record.to_maude()}'
        res += ' .'
        return res
    
class CacheEntry():
    def __init__(self, record : Record, cred : int = 1):
        self.record = record
        self.cred = cred
    
    # cacheEntry(< 'com . root, ns, testTTL, 'ns . 'com . root >, 1)
    def to_maude(self):
        return f"cacheEntry({self.record.to_maude()}, {self.cred})"
        
