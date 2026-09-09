import maude
import logging
import json

from pathlib import Path
from ..utils.setups import Setup
from maude_hcs.main import handle_command
from argparse import Namespace

logger = logging.getLogger(__name__)

def batch_convert_dir(dir: Path, proto: str):
    markov_args = Namespace(
        verbose=False,
        command='markov',
        markov_command='batch',
        protocol=proto,
        input_dir=str(dir),
        output_dir=str(dir),
    )
    handle_command(markov_args.command, None, markov_args)

def maude_runner(setup: Setup, **kwargs):
    filename: str = kwargs['file']
    path = (setup.directory / filename).resolve()

    # if 'markov_input_dir' in kwargs:
    # else:



    batch_convert_dir(setup.directory / 'irc_user_models', 'irc')
    batch_convert_dir(setup.directory / 'mastodon_action_models', 'mastodon')
    batch_convert_dir(setup.directory / 'skyhook_action_models', 'skyhook')

    batch_convert_dir(setup.directory / 'tgen_user_models' / 'dns', 'dns')
    batch_convert_dir(setup.directory / 'tgen_user_models' / 'ftp', 'ftp')
    batch_convert_dir(setup.directory / 'tgen_user_models' / 'gorilla', 'gorilla')
    batch_convert_dir(setup.directory / 'tgen_user_models' / 'irc', 'irc')
    batch_convert_dir(setup.directory / 'tgen_user_models' / 'mastodon', 'mastodon')
    batch_convert_dir(setup.directory / 'tgen_user_models' / 'mastodon_monitor', 'mastodon_monitor')
    batch_convert_dir(setup.directory / 'tgen_user_models' / 'minio', 'minio')
    batch_convert_dir(setup.directory / 'tgen_user_models' / 'minio_monitor', 'minio_monitor')
    batch_convert_dir(setup.directory / 'tgen_user_models' / 'tls', 'tls')

    gen_args = Namespace(
        verbose=False,
        command='generate',
        yaml_file=str(setup.directory / 'only_obfs.yaml'),
        quatex=True,
        baselineTime=100,
        runTime=100,
        hcsDelay=10,
        tgenDelay=10,
        outDir=str(setup.directory),
        scenarioName='test',
        notgens=False,
        filterVpFeatCombos=True,
        filterVpFeatCombos2=False,
        filterVpFeatTop25=False,
        filterVpFeatCombo4x5=False,
        filterVpFeatIxp=False,
        confidentiality=False,
        parallelizeBaseline=False,
        perf=False,
    )
    handle_command(gen_args.command, None, gen_args)

    maude.load(str(setup.directory / 'test.maude'))
    m: maude.Module = maude.getModule("HCS_TEST")
    t = m.parseTerm("initConfig")
    t.rewrite()
    d = {"term": str(t)}
    return json.dumps(d, indent=4)

#     generate_maude()
#     run_maude()


# def generate_maude():
#     args = Namespace()
#     handle_command("markov", args, None)

# def run_maude(filename):