# Generate CP4 IRC/HCS experiments

`generate-cp4` reads the CP4 reference architecture YAML and builds an executable
Maude experiment with IRC clients, primary/backup connections, and the configured
server tree. Both client connections and server-to-server links carry their IRC
traffic through the selected HCS model.

From the repository root, generate the included reference architecture:

```sh
python3 -m maude_hcs.generate_cp4 \
  use-cases/challenge-problem-4/reference_architecture_config.yaml \
  --out-dir results/cp4-reference \
  --scenario-name cp4_reference
maude results/cp4-reference/cp4_reference_run.maude
```

The installed command accepts the same arguments:

```sh
maude-hcs generate-cp4 \
  use-cases/challenge-problem-4/reference_architecture_config.yaml \
  --out-dir results/cp4-reference \
  --scenario-name cp4_reference
```

To use an external testbed checkout, pass its
`src/reference-architecture/reference_architecture_config.yaml`. User models are
resolved from `user_models/<channel>/` beside that YAML. `--user-models-dir`
overrides this directory. Generation does not require Docker or start the
external testbed. Running the generated file requires the repository's Maude
libraries and dependencies.

## Generated files

The output directory contains:

- `<scenario>.maude`: the topology, HCS actors, workload, and `initConfig` term.
- `<scenario>_run.maude`: loads the experiment, rewrites `initConfig`, and exits.
- `<scenario>_manifest.json`: source configuration, actor/connection mappings,
  selected parameters, workload timing, and modeling assumptions.
- `models/`: converted Maude user models and their JSON inputs.

The generated scenario names actors by their role, such as `ircClient1Actor`,
`ircServer1Actor`, `peer2SkyhookClientContentManagerActor`, and
`client1PrimaryMastodonClientUserModelActor`. Each alias expands to its configured
actor, keeping the initial state readable. Source mapping comments connect the
declarations to the YAML clients, servers, and links; runtime addresses and
endpoint names remain the identifiers used by the manifest and fault events.

Converted models also retain readable source names, such as
`cp4-irc-irc-13-ma-v2` and `cp4-mastodon-client-mastodon-bidi-ma`. Comments at model
imports and user-model actor definitions identify the source profile. The
manifest's `user_models` table is keyed by model operator and records each
model's `source`, `module`, `operator`, and `generated_file`. Each client's
`user_model` binding records its workload actor, address, model, and target;
it is `null` for imported CSV workloads. Each connection's `user_models`
records the client/server HCS user-model bindings when that channel uses them.

The scenario name defaults to the YAML filename without its extension. The
output directory defaults to the YAML's directory. Generated files load the
repository libraries by absolute path, so keep the same checkout available when
running them.

## Topology and channels

The included reference has four servers, six clients, and three server links:
Obfs4 between servers 1–2, Skyhook between 1–3, and Skyhook between 2–4. Client
primary and backup connections use Mastodon, Iodine, Obfs4, or Racetunnel.

Each connection gets independent IRC endpoints and HCS actors, including its
queues, polling state, and transport state. Public S3 and Mastodon services are
shared. Configured buckets, object streams, and Mastodon hashtags determine
which public content an endpoint can receive. The generator uses the existing
protocol models for these operations.

| YAML channel | Maude model | Configuration behavior |
| --- | --- | --- |
| `obfs` or `obfs4` | Obfs4 | `iat_mode: 0` is supported; other modes are rejected. |
| `racetunnel` or `webtunnel` | Webtunnel | Uses the TLS name and upgrade path; port is metadata. |
| `iodine` | Iodine DNS | Query and response bounds configure abstract DNS fragment sizes. |
| `skyhook` | Skyhook over S3 | Uses both user models, bucket names, and separate object streams. |
| `mastodon` | Bidirectional Mastodon | Uses both user models and the configured send/receive hashtags; username is metadata. |
| `direct` | IRC session/link transport | Provides a direct connection for comparison scenarios. |

Skyhook's opaque UUID seeds map deterministically to distinct decimal generation
namespaces, which the existing model advances by integer succession. This
preserves the configured streams without implementing the testbed's object-ID
cryptography.

Mastodon `username` and Webtunnel `port` are retained in the connection manifest.
They do not create account authentication or port-level routing behavior in the
current models. Unknown channel parameters are rejected so spelling mistakes
do not silently select defaults.

Server links must be acyclic; disconnected components are allowed. A client
connection must reference an existing server and a compatible client-facing
channel. Multiple clients are numbered in YAML insertion order. Profile
fractions are assigned using largest remainders, with ties resolved by profile
order. The external runner currently selects only the first network/profile
when producing IRC inputs for a node group; its default reference configuration
has one client and one profile per group.

## Workload and timing

The YAML selects two different kinds of user model. IRC workload profiles come
from `nodes.<node>.client_per_network.<network>.profiles`; they control rooms,
message sizes, and chat timing. HCS profiles come from the channel configuration
and control cover-traffic actions such as posting and fetching. An IRC server
does not run an IRC chat workload merely because its HCS endpoint has a user
model.

For Mastodon and Skyhook, an initiating channel's `user_model_client` selects
its client-side HCS profile, with `user_model` as the fallback. A per-connection
`user_model_server` overrides the receiving server's client-channel default
(`user_model_server`, falling back to `user_model`). Server-to-server links
specify their two profiles with `user_model_client` and `user_model_server`.
Primary and backup connections each
have separate HCS user-model actor state. Clients using the same IRC profile
also have separate workload actor state; only the converted model definition is
shared.

By default, the generator converts each IRC v2 JSON profile into a stochastic
Maude user model. Inputs enter the CP4 client's send queue so registration,
connection failure, failover, and rejoining rooms remain part of the model.
`input_seed` seeds the experiment; `--seed` overrides it and accepts zero or a
positive integer. Python testbed timelines and Maude stochastic profiles use
different random draw sequences, so their individual messages and timestamps
need not coincide.

For imported input schedules, provide `--workload-dir` with one CSV per client,
named `alice1.csv`, `alice2.csv`, and so on. The first row lists the channels to
join; subsequent rows contain relative time in seconds, channel, and payload:

```csv
#general,#random
0.5,#general,first message
2.0,#random,second message
```

```sh
python3 -m maude_hcs.generate_cp4 architecture.yaml \
  --out-dir results/cp4-replay \
  --workload-dir recorded-inputs \
  --workload-start 30 \
  --run-time 120
```

Imported CSVs preserve their payloads and relative input times. Delivery times
still depend on the simulated transport, queues, and failures. CSVs must have
nondecreasing, nonnegative times and reference channels declared on the first
row. Inputs after the requested conversation duration are excluded.

Client registration starts at simulation second 1. The default common workload
start is `10 + Random(input_seed).uniform(0, max_start_delay)` seconds;
`--workload-start` sets an explicit absolute start. The run ends at that start
plus `conversation_duration`, or plus `--run-time` when supplied. This is a
reproducible simulation schedule: the testbed instead staggers process startup,
waits for all rooms to be joined, pauses for a shared random delay, and
synchronizes traffic to a minute boundary.

Generated sessions use a 120-second server idle threshold followed by a
120-second pong deadline, matching the current testbed's `ngircd.conf`. The
older baseline replay retains its separate 10/20-second calibration. These are
liveness timers, not immediate detection of a lost connection; buffered writes
and failover proceed according to the client's observed session state.

## Add endpoint failures to an experiment

The CLI does not import the testbed's separate fault-action YAML. To explore a
client failover manually, place a new runner beside the generated experiment
and add reachability events to its initial state:

```maude
sload "cp4_reference.maude"
rew run({0.0 | nil} initState(1234)
  mkDisconnect(120.0, client1PrimaryLeftEp, client1PrimaryRightEp)
  mkReconnect(420.0, client1PrimaryLeftEp, client1PrimaryRightEp), limit) .
quit
```

Use the endpoint names from the manifest and keep event times within the run's
limit. `mkDisconnect` and `mkReconnect` change both endpoints. For a change to
only one endpoint, add an event such as
`[120.0, (to client1PrimaryLeftEp from client1PrimaryLeftEp : SetLinkState(false)), 0]`.
Repair restores reachability; it does not reopen an expired session or replay
dropped traffic.

These events control IRC endpoint reachability. The HCS's polling and public
service traffic can continue during the partition. Protocol-level network
loss or resets require events in the network/adversary model instead.

## Network and analysis scope

Network latency uses the source network's upstream delay and the destination
network's downstream delay, converting `latency_ms` to seconds. The analytical
TCP and DNS models determine transport behavior. Iodine also includes the DNS
network's upstream and downstream delays as a collapsed forwarding hop between
the client and authority. Resolver caches and root/TLD exchanges are not
instantiated; TCP connection setup uses a local authoritative lookup.
Public S3/Mastodon services
add no configured router delay unless `minio_net`/`mastodon_net` is supplied.
Network labels and `nat` settings are retained in the manifest; the generator
does not instantiate container routing or NAT rules.

`one_way_availability` and `analysis_window_size` are retained as analysis
metadata. They do not automatically run an availability validator or create a
QuaTEx query. Nonempty `tgen` and `adversary` sections are rejected, as are
unsupported network parameters. The architecture YAML does not contain the
testbed runner's separate disconnect/reconnect action file; generating an
architecture alone does not apply those fault actions.
