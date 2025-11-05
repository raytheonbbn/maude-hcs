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

from .common import save_output
from maude_hcs.analysis import HCSAnalysis
from maude_hcs.lib import GLOBALS
from maude_hcs.parsers.configfactory import buildHCSConfig

import logging
from pathlib import Path

from umaudemc.command.scheck import scheck
import importlib.util
import maude

logger = logging.getLogger(__name__)

GENERATE_NAME = 'generate'
SCHECK_NAME = 'scheck'

def handle_command(command, parser, args):
    handlers = {
        GENERATE_NAME: handle_generate,
        SCHECK_NAME: handle_scheck
    }

    if command in handlers:
        handlers[command](args, parser)

    else:
        parser.error("Unknown command: {}".format(command))

def handle_generate(args, parser):
    logger.debug("Handle maude generation")
    if args.run_args and args.shadow_filename:
        raise Exception('Either specify a json HCS config with --run-args OR a shadow config, but not both.')
    # get the configuration object    
    hcsconfig = buildHCSConfig(args)
    # instantiate the analysis and generate
    result = HCSAnalysis(args, hcsconfig).generate()
    # save the output
    filename = args.filename
    if filename == None:
        filename = f'generated_{hcsconfig.name}_{args.model}'
    save_output(parser, hcsconfig, result, filename)    

def handle_scheck(args, parser):
    logger.debug("Handle umaudemc scheck")

    if not args.file:        
        args.file = str(GLOBALS.TOPLEVELDIR.joinpath(Path(f"maude_hcs/lib/smc/smc.maude")))
    logger.debug(f"Loaded SMC file {args.file}")

    has_umaudemc = importlib.util.find_spec('umaudemc')
    if not has_umaudemc:
        logger.error('The umaudemc Python package is not available. It can be installed with "pip install umaudemc".')
    maude.init(advise=args.advise)
    maude.load(args.test)
    result = scheck(args)
