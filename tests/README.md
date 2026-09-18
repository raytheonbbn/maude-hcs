# How to use the new test framework

## Updating environment

Reinstall `maude-hcs` (including the test dependencies group!), since there have been changes to `pyproject.toml`:

`pip install -e ".[test]"`

If this doesn't work, there may be an issue with dependency resolution. Try deleting your environment or creating a new one, and reinstalling from scratch.
Don't forget to install the dependencies for `maude_hcs/deps/dns_formalization` as well!

## Create a context

A context directory controls the (static) filesystem context for a test, i.e. it determines which files will always be present in the test environment.
Additional files will be added during the build step of a test. The context directory also stores the tests to be executed in that context, 
and build configurations for the tests.  *Contexts should only include files that are test-specific, or likely to be different for different tests*, 
otherwise it makes more sense to just have those files under maude_hcs/lib, which files can still link to using absolute paths.

Before each test, the framework initializes a new temporary directory with the files from the given context.
Then, depending on the test runner, it will run a build step that adds additional files to the environment.

*BUILDS ARE CACHED, so running a second test with the same build configuration will reuse the built environment from the first test. This means it's critical that
tests do not alter their environment in any way that could affect future tests*.

In practice, the context will mostly consist of json action models, yaml configurations, test definitions, and build configurations.

Each context directory must be placed under tests/contexts. The name of the context directory will become part of the name of the test.

## Create a test

For a given context directory named `ctx`, the tests to run in that context are found under `ctx/tests`, grouped into files by which function they use to execute.

For example, `ctx/tests/maude.json`, if present, must contain a list of tests that run using the standard `maude_runner` function, while `ctx/tests/smc.json` would use the `smc_runner` function.

Regardless of the test runner, every test object has the same attributes:

- `name`: The name for this test
- `desc`: A description of the purpose and implementation of this test
- `expected`: The expected result for this test. If absent, this is a regression test that will create a snapshot the first time it is run
- `build_cfg`: Which JSON file from `ctx/build_cfgs` to use as a source of arguments to the markov_json_to_maude converter and the test.maude generator. Setting this to `foo` selects the build config `ctx/build_cfgs/foo.json`.
- `arg`: An arbitrary JSON expression to be passed to the test runner function. This generally includes a predicate or expression to be evaluated as part of the test, with the result compared to `expected`.

## Run pytest

Just run `pytest` from the repo root.

Remember to manually inspect the test results the first time, and make sure they look like what you expect! Snapshots will then make sure they don't change in the future.

If the expected behavior of a test has changed, you can force pytest to replace the snapshot by running it with the `--force-regen` flag.