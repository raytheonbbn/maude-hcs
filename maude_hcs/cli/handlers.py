from .common import save_output
from maude_hcs.analysis import HCSAnalysis
import logging
import json

logger = logging.getLogger(__name__)

GENERATE_NAME = 'generate'

def handle_command(command, parser, args):
    handlers = {
        GENERATE_NAME: handle_generate
    }

    if command in handlers:
        handlers[command](args, parser)

    else:
        parser.error("Unknown command: {}".format(command))

def handle_generate(args, parser):
    logger.debug("Handle maude generation")
    run_args = json.load(args.run_args)
    result = HCSAnalysis(run_args).generate()
    filename = f'generated_{run_args.get("name", "unknown")}_{args.generator}'
    save_output(parser, run_args, result, filename)


    

    
    