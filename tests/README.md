# How to use the new test framework

## Updating environment

Reinstall `maude-hcs` (including the test dependencies group!), since there have been changes to `pyproject.toml`:

`pip install -e ".[test]"`

If this doesn't work, there may be an issue with dependency resolution. Try deleting your environment or creating a new one, and reinstalling from scratch.
Don't forget to install the dependencies for `maude_hcs/deps/dns_formalization` as well!

## Create a context (or use an existing context)

A context directory controls the (static) filesystem context for a test, i.e. it determines which files will always be present in the test environment.
Additional files will be added during the build step of a test. The context directory also stores the tests to be executed in that context, 
and build configurations for the tests.  *Contexts should only include files that are test-specific, or likely to be different for different tests*, 
otherwise it makes more sense to just have those files under maude_hcs/lib, which tests can still link to using absolute paths.

Before each test, the framework initializes a new temporary directory with the files from the given context.
Then, depending on the test runner, it will run a build step that adds additional files to the environment.

~~*BUILDS ARE CACHED, so running a second test with the same build configuration will reuse the built environment from the first test. This means it's critical that
tests do not alter their environment in any way that could affect future tests*.~~ (This caching is disabled while I work out a bug)

In practice, the context will mostly consist of json action models, yaml configurations, test definitions, and build configurations.

Each context directory must be placed under tests/contexts. The name of the context directory will become part of the name of the test.

For the rest of this README, I'll refer to the context directory you're working in as `ctx`.

## Create a build (or use an existing build)

Within `ctx`, builds are json files placed in the `build_cfgs` directory. There are three parts to a build config:

- `markov_v1_dirs` is a list of pairs of strings, where the first string in each pair is a subdirectory under `ctx` that contains JSON files representing v1 markov models, and the second string is the name of the protocol that the markov model belongs to. During the build step, all of these directories will have their JSON files converted to Maude.
- `markov_v2_dirs` is the same thing, but for directories of v2 markov model JSON files. They go through a different converter.
- `gen_args` is an object that holds all the arguments that should be passed to the CP3 Maude generator. For info on these arguments, check the `main.py` file.

## Create a test

The tests for `ctx` are found under the `tests` subdirectory, grouped into files by which function they use to execute.

For example, `ctx/tests/maude.json`, if present, must contain a list of tests that run using the standard `maude_runner` function, while `ctx/tests/smc.json` would use the `smc_runner` function.

Regardless of the test runner, every test object has the same attributes:

- `name`: The name for this test
- `desc`: A description of the purpose and implementation of this test
- `expected`: The expected result for this test. If absent, this is a regression test that requires an approved snapshot; creating one requires an explicit regeneration flag
- `build_cfg`: Which JSON file from `ctx/build_cfgs` to use as a source of arguments to the markov_json_to_maude converter and the test.maude generator. Setting this to `foo` selects the build config `ctx/build_cfgs/foo.json`.
- `arg`: An arbitrary JSON expression to be passed to the test runner function. This generally includes a predicate or expression to be evaluated as part of the test, with the result compared to `expected`.
    - for Maude tests, this is a Maude expression that will be rewritten in the test environment, with the final result taken for comparison to the expected value or stored snapshot.
    - For SMC tests, this is an object containing arguments for running `scheck`. The results and comparisons are then done automatically.

## Run pytest

Just run `pytest` from the repo root.

Remember to manually inspect the test results the first time, and make sure they look like what you expect! Snapshots will then make sure they don't change in the future.

If the expected behavior of a test has changed, you can force pytest to replace the snapshot by running it with the `--force-regen` flag.

To run the tests faster in parallel,
``` shell
pytest -n auto 
```

## Useful flags

### pytest flags

`-k EXPR`: only run tests whose names contain `EXPR`

`--trace`: start Python Debugger at start of every test

`--pdb`: start Python Debugger on every failure

`-s`: disable output capturing

`--log-level=LEVEL`: minimum level of messages to display on failures

`--log-cli-level=LEVEL`: minimum level of logs to stream to console (happens even without test failures)

### pytest-regressions flags

`--force-regen`: When a test fails, replace the old snapshot with the new result

`--regen-all`: Replace all snapshots with the new results from this test run

### Custom flags

`--build`: Just run the build commands for each test, don't actually execute them. Execution is reported as skipped.

`--persist`: don't delete the temporary build directory when test suite completes

`--runner=RUNNER`: only run tests from the selected runner. Note: ALWAYS use the equals sign for this flag, DO NOT try to pass it as `--runner RUNNER`.

`--regression`: only run regression tests

`--expected`: only run expected-value tests (not regression tests)

`--copy`: copy the path to the temporary build directory to system clipboard, for faster debugging

## Correctness assertions and snapshot review

Correctness cases should declare `"expected": "true"` (a string, matching the
Maude runner output). Use the two-step form:

```json
{
  "name": "delivery",
  "desc": "Check the final configuration",
  "build_cfg": "obfs_isolated",
  "arg": {
    "initial": "initConfig",
    "predicate": "getTotalBytesSent(FINAL:Config) == 168448"
  },
  "expected": "true"
}
```

The runner finishes rewriting `initial`, substitutes its result for
`FINAL:Config`, then reduces the predicate. Embedding `initConfig` directly in a
Boolean equality can evaluate the equality before the execution is complete.
String `arg` remains supported for arbitrary-term regression tests.

The previous five correctness snapshots recorded `"false"`. These cases now
assert true; failures must be investigated, not accepted by regenerating a false
reference. No model-level byte-count expectations were changed.

## SMC comparison policies

Every SMC regression explicitly selects a policy:

```json
"arg": {"nsims": "1-1", "seed": 0, "jobs": 1},
"comparison": {"mode": "smoke"}
```

Smoke tests require exact fixed-seed results, including joint sample rows. They
are fast quantitative regression checks, not evidence of distributional
agreement. The existing isolated-channel SMC cases use this mode.

A distributional test can instead declare:

```json
"arg": {"nsims": "20000-20000", "seed": 0, "jobs": 1},
"comparison": {"mode": "distribution", "delta": 0.05,
               "alpha": 0.05, "min_samples": 20000}
```

The checker uses the empirical KS distance plus two one-sample DKW error bounds,
allocating alpha across all queries. It passes only when the upper bound is below
delta. Insufficient evidence fails with the query name, distance, bound, and
sample sizes; it never interprets a large p-value as equivalence. Counts in the
example are illustrative: the required sample budget depends on query count,
tolerance and observed distance. This is a fixed-look comparison of independent
simulation runs, not a sequential stopping rule. Query marginals do not certify
temporal or cross-feature dependence.

Schema 2 snapshots include model/library/dependency/query hashes, effective
build and SMC settings, tool versions, complete query identities, raw joint rows,
and worker-file/row run identifiers. Those identifiers preserve within-run
pairing; they are not independent per-run random seeds. The existing sorted
`parse_dump` API is unchanged; new joint analyses use `parse_dump_rows`.
Per-client and per-vantage query names now include the client/vantage so results
cannot silently overwrite each other. In the inspected Obfs case this preserves
all 600 queries where the old result dictionary retained only 480.

Legacy SMC snapshots fail before simulation with a migration message. Review the
new output and use `--force-regen` or `--regen-all` deliberately; neither missing
nor old references are silently approved. The historical references have not
been rewritten as part of the framework fixes.

## Diagnostics and fast framework tests

```shell
pytest tests/test_framework.py
pytest tests/test_maudehcs.py --expected --runner=maude --timeout=300
pytest tests/test_maudehcs.py --regression --runner=smc -m smoke
pytest tests/test_maudehcs.py -m statistical
```

`--timeout` bounds each model execution (default 300 seconds), including child
shutdown. It does not bound scenario generation. Worker crashes and Python
exceptions fail with diagnostics. On POSIX, timeout/interruption cleanup also
terminates the worker's process group, including SMC descendants.

Failed sessions automatically retain builds and logs and print their location;
`--persist` also retains successful builds. Each build has `logs/stdout.log`,
`logs/stderr.log`, and `logs/runner.log`. `--tempdir` creates a unique subdirectory
under the supplied directory, including when using pytest-xdist.

Unknown generation/test/runner arguments are errors. Obsolete `filter_vp_*`
settings, which were not forwarded to the current generator, have been removed
from the five correctness build definitions; use supported `feats`/`vpts` fields.

The fast harness tests cover worker success/crash/timeout, native diagnostics,
Maude final-state evaluation, sample merging/validation, query identity, joint
samples, comparison policies, collection filtering, provenance, and missing or
legacy references. They do not run the large CP3 scenarios. Broader baseline,
confidentiality, interaction, and scalability scenarios remain separate coverage
work; no new performance or decomposition guarantee is claimed here.
