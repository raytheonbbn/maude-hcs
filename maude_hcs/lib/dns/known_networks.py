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

from .corporate import corporate
from .corporate_iodine import corporate_iodine

class KnownUNetworks:
    def __init__(self):        
        self.constructors = {
            'corporate_base': self._fixed_network(corporate),
            'corporate_iodine': self._fixed_network(corporate_iodine)
        }
    
    def create(self, args, run_args):        
        conf = self.constructors[run_args["name"]](args, run_args)
        return conf
    
    def _fixed_network(self, Cls):
        def make(args, run_args):
            conf = Cls(args, run_args)
            return conf
        return make
    

