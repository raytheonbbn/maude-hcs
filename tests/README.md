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
- `expected`: The expected result for this test. If absent, this is a regression test that will create a snapshot the first time it is run
- `build_cfg`: Which JSON file from `ctx/build_cfgs` to use as a source of arguments to the markov_json_to_maude converter and the test.maude generator. Setting this to `foo` selects the build config `ctx/build_cfgs/foo.json`.
- `arg`: An arbitrary JSON expression to be passed to the test runner function. This generally includes a predicate or expression to be evaluated as part of the test, with the result compared to `expected`.
    - for Maude tests, this is a Maude expression that will be rewritten in the test environment, with the final result taken for comparison to the expected value or stored snapshot.
    - For SMC tests, this is an object containing arguments for running `scheck`. The results and comparisons are then done automatically.

## Run pytest

Just run `pytest` from the repo root.

Remember to manually inspect the test results the first time, and make sure they look like what you expect! Snapshots will then make sure they don't change in the future.

If the expected behavior of a test has changed, you can force pytest to replace the snapshot by running it with the `--force-regen` flag.

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

`--build`: Just run the build commands for each test, don't actually execute them. Will fail every test.

`--persist`: don't delete the temporary build directory when test suite completes

`--runner=RUNNER`: only run tests from the selected runner. Note: ALWAYS use the equals sign for this flag, DO NOT try to pass it as `--runner RUNNER`.

`--regression`: only run regression tests

`--expected`: only run expected-value tests (not regression tests)

`--copy`: copy the path to the temporary build directory to system clipboard, for faster debugging