# CP4 reference architecture

This directory contains the reference architecture YAML and the five JSON user
models it references, copied from the CP4 testbed's
`src/reference-architecture/` directory. The generator and its tests use these
files without requiring the external testbed checkout or Docker containers.

From the repository root, generate the Maude experiment with:

```sh
python3 -m maude_hcs.generate_cp4 \
  use-cases/challenge-problem-4/reference_architecture_config.yaml \
  --out-dir results/cp4-reference \
  --scenario-name cp4_reference
```

The configuration defines four IRC servers, six IRC clients, one Obfs4 server
link, two Skyhook server links, and Mastodon, Iodine, Obfs4, and Racetunnel client
connections. `obfs` and `racetunnel` are testbed names; the parser normalizes them
to the Maude library names `obfs4` and `webtunnel`.

The external testbed generates Python-seeded timelines and message CSVs before
execution. A Maude run using the converted stochastic user models has the same
profile inputs, but its random draws and message times need not match those CSVs.
The testbed's `max_start_delay` is a shared pause after all clients join their
rooms and before synchronized traffic begins. It is not a separate delay for
each message or client.
