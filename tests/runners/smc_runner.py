import logging
import json
import maude
import os

from typing import TYPE_CHECKING
from pathlib import Path
from argparse import Namespace

from maude_hcs.parse_dump import parse_dump
from maude_hcs.query import parse_quatex, Query, IntegrityQuery, ConfidentialityQuery
from maude_hcs.result import SimResult, FeatResult

# prevents circular import
if TYPE_CHECKING:
    from ..utils.context import TestConfig, RunConfig

# fix generate_cp3 to always look in correct spot for all model imports

from maude_hcs.main import capture_scheck
from maude_hcs.lib import GLOBALS

logger = logging.getLogger(__name__)

def concat_dumps(dump_dir: Path):
    """No guaranteed ordering BETWEEN LINES of resulting dump file.
    Individual features on a single line are still ordered left-to-right."""

    filenames = os.listdir(dump_dir)
    paths = map(lambda x: dump_dir / x, filenames)

    with open(dump_dir / "all_dumps", "w") as f:
        for path in paths:
            dump_str = path.read_text().strip()
            f.write(dump_str)
        f.flush()

    for path in paths:
        os.remove(path)

def smc_runner(test_cfg: "TestConfig", build_dir: Path, run_cfg: "RunConfig") -> dict:
    # Have to initialize maude even though umaudemc does it again, because we need to pre-load
    # test file so umaudemc will see it as most recent
    maude.init()

    run_file = f"test-run-{test_cfg.build_cfg.gen_args.run_time}.maude"

    dump_dir = build_dir / "dumps"
    os.mkdir(dump_dir)

    arg = test_cfg.arg

    args = Namespace(

        # Configurable by test
        file=str((GLOBALS.TOP_LEVEL_DIR / arg.get("file", "maude_hcs/lib/smc/smc_cp3.maude")).resolve()),
        nsims=arg.get("nsims", "1-1"),
        seed=arg.get("seed", 0),
        jobs=arg.get("jobs", 1),
        D=arg.get("D", None),
        assign=arg.get("assign", "pmaude"),
        alpha=arg.get("alpha", 0.05),
        delta=arg.get("delta", 0.5),
        block=arg.get("block", 30),
        distribute=arg.get("distribute", False),

        # Configurable, but I think it's unlikely we'd want to
        advise=arg.get("advise", True),
        module=arg.get("module", None),
        metamodule=arg.get("metamodule", None),
        strategy=arg.get("strategy", None),
        opaque=arg.get("opaque", ""),
        full_matchrew=arg.get("full_matchrew", None),

        # Not configurable, either no real reason to configure or doing so would break framework
        dump=str(dump_dir / "dump"),
        test=str(build_dir / run_file),
        query=str(build_dir / "test.quatex"),
        initial="initConfig",
        format="json",
        plot=False,
        verbose=False,
    )

    (out, err) = capture_scheck(args)
    logger.info(out)
    logger.warning(err)

    concat_dumps(dump_dir)

    smc_format_json = json.loads(out)["queries"]
    # assert smc_format_json is sorted by line number

    dump = parse_dump((dump_dir / "all_dumps").read_text())
    queries = parse_quatex((build_dir / "test.quatex").read_text())

    def mk_result(stats: dict, query: Query, ecdf: list[float]) -> tuple[str, dict]:
        result = {
            "type": query.typ,
            "feat": query.name,
            "start": query.start,
            "end": query.end
        }

        if isinstance(query, IntegrityQuery):
            result["client"] = query.client
        if isinstance(query, ConfidentialityQuery):
            result["vantage"] = query.vantage

        result["mean"] = stats["mean"]
        result["stddev"] = stats["std"]
        result["samples"] = ecdf

        return query.to_name(), result 

    results = map(mk_result, smc_format_json, queries, dump)

    gen_args = test_cfg.build_cfg.gen_args

    result_json = {
        "yaml_filename": gen_args.yaml_file,
        "baseline_time": gen_args.baseline_time,
        "run_time": gen_args.run_time,
        "hcs_delay": gen_args.hcs_delay,
        "tgen_delay": gen_args.tgen_delay,
        "no_tgens": gen_args.no_tgens,
        "results": {name: result for name, result in results}
    }
    return result_json