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
