import logging
import json
import maude
import os

from typing import TYPE_CHECKING
from pathlib import Path
from argparse import Namespace

from maude_hcs.parse_dump import parse_dump, parse_dump_rows
from ..utils.provenance import provenance
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

    # Restrict inputs to worker dumps, excluding the aggregate on repeated calls.
    paths = sorted(path for path in dump_dir.glob("dump*") if path.is_file())
    if not paths:
        raise ValueError(f"No worker dumps found in {dump_dir}")
    rows, run_ids = [], []
    for path in paths:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip():
                rows.append(line.strip())
                run_ids.append(f"{path.name}:{number}")
    if not rows:
        raise ValueError("Worker dumps contain no samples")
    (dump_dir / "all_dumps").write_text("\n".join(rows) + "\n")
    # Preserve source dumps for debugging and stable worker/row identifiers.
    return run_ids


def smc_runner(test_cfg: "TestConfig", build_dir: Path, run_cfg: "RunConfig", logger: logging.Logger) -> dict:
    # Have to initialize maude even though umaudemc does it again, because we need to pre-load
    # test file so umaudemc will see it as most recent
    maude.init()

    arg = test_cfg.arg
    supported = {"baseline", "file", "nsims", "seed", "jobs", "D", "assign", "alpha", "delta", "block", "distribute", "advise", "module", "metamodule", "strategy", "opaque", "full_matchrew"}
    if not isinstance(arg, dict) or set(arg) - supported:
        raise ValueError(f"Unsupported SMC runner arguments: {arg}")

    if arg.get("baseline", False):
        # The generator normally includes the baseline duration in its filename.
        legacy = build_dir / "test-baseline.maude"
        run_file = legacy.name if legacy.is_file() else f"test-baseline-{test_cfg.build_cfg.gen_args.baseline_time}.maude"
    else:
        run_file = f"test-run.maude"

    if not (build_dir / run_file).is_file():
        raise FileNotFoundError(f"Generated SMC input is missing: {build_dir / run_file}")
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

    # Validate query identities before paying for simulation, rather than
    # discovering after a long run that dict(results) would drop observations.
    queries = parse_quatex((build_dir / "test.quatex").read_text())
    names = [query.to_name() for query in queries]
    if not names or len(set(names)) != len(names):
        raise ValueError("Empty or duplicate query names would lose SMC results")

    (out, err) = capture_scheck(args)
    if err.strip(): logger.warning(err)

    run_ids = concat_dumps(dump_dir)

    smc_format_json = json.loads(out)
    smc_format_queries_json: list = smc_format_json["queries"]
    n_sims = smc_format_json["nsims"]

    n_queries = len(queries)

    assert n_queries == len(smc_format_queries_json)

    # If query results arrive out of order that's a disaster
    line_key = lambda q: q["line"]
    line_numbers = list(map(line_key, smc_format_queries_json))
    assert sorted(line_numbers) == line_numbers
    smc_format_queries_json.sort(key=line_key)

    dump_str = (dump_dir / "all_dumps").read_text()
    sample_rows = parse_dump_rows(dump_str, n_sims=n_sims, n_queries=n_queries)
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

    result = asdict(sim_result)
    result.update(schema_version=2, provenance=provenance(test_cfg, build_dir, args),
                  sample_rows=sample_rows, run_ids=run_ids, query_order=names)
    return result
