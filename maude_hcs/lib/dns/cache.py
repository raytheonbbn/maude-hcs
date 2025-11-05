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
        
