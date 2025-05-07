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

from Maude.attack_exploration.src.config import Config

class MaudeHCSMaudeEncoder(object):

    def __init__(self) -> None:
        pass

    def encode(self, o):
        if not isinstance(o, Config):
            raise Exception(f'can only encode Config objects in Maude. got {type(o)} instead')
        return self.generate_maude(o)
    
    def generate_maude(self, o):
        return o.to_maude()


class MaudeHCSEncoder(object):
    def __init__(self, format='maude'):
        self.format = format        
        if format == 'maude':
            self.encoder = MaudeHCSMaudeEncoder()
        else:
            raise Exception(f'Unknown serialization format {format}')


    def encode(self, o):
        return self.encoder.encode(o)
