import sys
import subprocess
from pathlib import Path

HOME_DIR = Path.home()

# Should point to root of pwnd-cp3 T&E code drop
PWND_CP3_DIR = HOME_DIR / "Documents" / "pwnd2" / "pwnd-cp3"

# Should point to root of maude-hcs github repo
MAUDE_HCS_DIR = HOME_DIR / "Documents" / "pwnd2" / "maude-hcs"

OUTPUT_DIR = MAUDE_HCS_DIR / "scripts" / "gen_cp3" / "output"
MASTODON_ACTIONS_DIR = PWND_CP3_DIR / "src" / "static" / "mastodon_actions"
SKYHOOK_ACTIONS_DIR = PWND_CP3_DIR / "src" / "static" / "skyhook_actions"
LOSS_SPECS_DIR = PWND_CP3_DIR / "src" / "static" / "tc_profiles"

def gen_markov(json_dir, out_dir):
    """Generate action files from all json files in json_dir"""

    subprocess.run([
        "maude-hcs", "--verbose",
        "markov",
        "--protocol=mastodon",
        f"--json-dir={json_dir}",
        f"--maude-dir={out_dir}",
    ])

def gen_config(cfg_file, out_dir, out_name):
    """Produce maude initial state file from yaml cfg_file"""

    subprocess.run([
        "maude-hcs", "--verbose", 
        "generate",
        "--model=prob",
        f"--yml-filename={cfg_file}",
        f"--loss-specs-dir={LOSS_SPECS_DIR}",
        f"--output-dir={out_dir}",
        "--filename=out",
    ])

def main():

    gen_config(
        HOME_DIR / "Documents" / "pwnd_cp3_spot_check_1.yaml", # path to cp3 config yaml to ingest
        OUTPUT_DIR, # path to directory where we should dump maude result
        "out"
    )

if __name__ == "__main__":
    main()