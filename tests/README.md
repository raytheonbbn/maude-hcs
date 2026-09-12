# How to use the new test framework

The framework currently only supports regression (snapshot) tests, normal tests are almost ready.

## Updating environment

Reinstall `maude-hcs` (including the test dependencies group!), since there have been changes to `pyproject.toml`:

`pip install -e ".[test]"`

## Create a context

A context directory controls the filesystem context for a test, i.e. it determines which files will be present alongside the test.maude file actually being tested.
Many different tests can share the same context, that just means they require the same supporting files. Before each test, the framework initializes a new temporary directory
with the files from the given context. *Contexts should only include files that are likely to be different for different tests*, otherwise it makes more sense to just
have those files under maude_hcs/lib, which test.maude still links to using absolute paths.

In practice, the context will mostly consist of action models defined in json files, and yaml configurations.

Each context directory must be placed under tests/contexts. The name of the context directory will become part of the name of the test.

## Create a config

A test config file defines an individual test to run, using JSON. For a given context directory named `ctx`, the corresponding config files are found under `ctx/test_cfgs`.

Each config must define four top-level attributes: `name`, `runner`, `regression`, and `args`. `name` is just the name of the test. Currently, `runner` should always be set to `"maude_runner"` and `regression` should always be set to `true`.

`args` defines the arguments passed to the selected `runner`. For `maude_runner`, you must define these arguments:

- `markov_dirs` is a list of objects, each of which identifies a directory of markov model JSON files that need to be converted to maude. Each object must have a `path` attribute that identifies the directory relative to the context directory root, and a `proto` key defining which protocol the markov models are for.
- `gen_args` is an object defining the arguments to be passed to the maude model generation script.
- `test` is the maude expression that should be evaluated, and the result compared against the known snapshot (or saved if there is no snapshot yet)

## Run pytest

Just run `pytest` from the repo root.

Remember to manually inspect the test results the first time, and make sure they look like what you expect! Snapshots will then make sure they don't change in the future.

If the expected behavior of a test has changed, you can force pytest to replace the snapshot by running it with the `--force-regen` flag.