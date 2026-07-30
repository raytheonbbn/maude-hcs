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

from maude_hcs.parsers.hcsconfig import HCSConfig
from maude_hcs.serialize import MaudeHCSEncoder
import logging
import sys
import os
from pathlib import Path

logger = logging.getLogger(__name__)

TOPLEVELDIR = Path(os.path.dirname(__file__))

def _legalize_name(name):
    name = name.replace('(', '.')
    name = name.replace('=', '')
    name = name.replace(',', '.')
    name = name.replace(')', '')
    return name

def name_object(name, ending='json'):
    return f'{_legalize_name(name)}.{ending}'

def write_file_to_directory(contents, output_dir, filename, force, parser):
    output_dir = os.path.join('.', output_dir)
    logger.debug(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    output_file = os.path.join(output_dir, filename)
    print(output_file)
    if os.path.exists(output_file):
        if os.path.isdir(output_file):
            parser.error(f'error: output path is a directory', file=sys.stderr)
        if force:
            print(f'Overwriting {output_file}')
        else:
            parser.error(f'file already exists, use -f/--force to overwrite {output_file}', file=sys.stderr)


    with open(output_file, 'w') as f:
        f.write(contents)

    logger.info(f'Wrote to {output_file}')