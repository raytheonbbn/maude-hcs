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

from dataclasses import asdict

# prevents circular import
if TYPE_CHECKING:
    from ..utils.context import TestConfig, RunConfig

from maude_hcs.main import capture_scheck
from maude_hcs.lib import GLOBALS

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

def smc_runner(test_cfg: "TestConfig", build_dir: Path, run_cfg: "RunConfig", logger: logging.Logger) -> dict:
    # Have to initialize maude even though umaudemc does it again, because we need to pre-load
    # test file so umaudemc will see it as most recent
    maude.init()

    arg = test_cfg.arg

    if arg.get("baseline", False):
        run_file = f"test-baseline.maude"
    else:
        run_file = f"test-run.maude"

    dump_dir = build_dir / "dumps"
    os.mkdir(dump_dir)

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
    if err.strip(): logger.warning(err)

    concat_dumps(dump_dir)

    smc_format_json = json.loads(out)
    smc_format_queries_json: list = smc_format_json["queries"]
    n_sims = smc_format_json["nsims"]

    queries = parse_quatex((build_dir / "test.quatex").read_text())
    n_queries = len(queries)

    assert n_queries == len(smc_format_queries_json)

    # If query results arrive out of order that's a disaster
    line_key = lambda q: q["line"]
    line_numbers = list(map(line_key, smc_format_queries_json))
    assert sorted(line_numbers) == line_numbers
    smc_format_queries_json.sort(key=line_key)

    dump_str = (dump_dir / "all_dumps").read_text()
    query_samples = parse_dump(dump_str, n_sims=n_sims, n_queries=n_queries) # query_samples[i] is all results of query[i] across all sims
    assert len(query_samples) == n_queries
    assert len(query_samples[0]) == n_sims

    mk_feat_result = lambda query, stats, ecdf: (query.to_name(), FeatResult(query, stats["mean"], stats["std"], ecdf))
    results = map(mk_feat_result, queries, smc_format_queries_json, query_samples)

    gen_args = test_cfg.build_cfg.gen_args

    sim_result = SimResult(
        gen_args.yaml_file,
        gen_args.baseline_time,
        gen_args.run_time,
        gen_args.hcs_delay,
        gen_args.tgen_delay,
        gen_args.no_tgens,
        dict(results)
    )

    return asdict(sim_result)
