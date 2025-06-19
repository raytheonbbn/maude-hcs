# DNS HCS Configuration Parameters 

| parameter | description |
|---|---|
|**topology**| specification of nodes and links consistent with the [Shadow graph specification](https://shadow.github.io/docs/guide/network_graph_spec.html). |
|**underlying_network**||
| `underlying_network.module` | `dns` |
| `underlying_network.root_name` | `root-dns` |
| `underlying_network.tld_name` | The top level domain actor name e.g., `tld-dns` |
| `underlying_network.tld_domain` | The domain name for the TLD which contains the TLD zone file. e.g., `com.` |
| `underlying_network.resolver_name` | The actor name of the public DNS recursive resolver e.g., `public-dns` |
| `underlying_network.corporate_name` | The actor name of the corporate resolver (this is a name server that simply forwards queries to another actor such as the resolver) e.g., `local-dns` |
| `underlying_network.corporate_domain` | The domain name of the corporate domain which contains the corporate zone file `corporate.com.` |
| `underlying_network.everythingelse_name` | The actor name of the internet authoritative domain server; all background traffic flows to this server e.g., `internet-dns` |
| `underlying_network.everythingelse_domain` | The domain name of the zone served by the internet DNS server e.g., `internet.com.` |
| `underlying_network.everythingelse_num_records` | The number of sample A records to pre-populate into the zone file e.g., `2`. this will create names `tmp0.<domain_name>` and `tmp1.<domain_name>` records |
| `underlying_network.pwnd2_name` | Name of pwnd2 iodine server actor e.g., `application-server` |
| `underlying_network.pwnd2_domain` | Name of pwnd2 domain; note it should either be consistent with the TLD or a separate TLD actor would be needed; e.g., `pwnd2.com.` |
| `underlying_network.populate_resolver_cache` | Populate the cache of the resolver with the NS records of all the name server actors; this means NS resolutions will not require asking the root server or TLD e.g., `true` |
| `underlying_network.record_ttl` | The TTL of non-A records in zone files e.g, `3600` to enable caching|
| `underlying_network.record_ttl_a` | The TTL used by the iodine server for its records (responses to weird queries). A value larger than zero will result in caching the response records at the resolver. E.g., `0` |
| `underlying_network.addr_prefix` | The prefix to prepend to the actor names to create the actor unique address e.g., `addr-` |
|**weird_network**||
| `weird_network.module` | `iodine` |
| `weird_network.client_name` | `application-client` |
| `weird_network.client_weird_qtype` | `a` |
| `weird_network.severWResponseTTL` | `0.0` |
| `weird_network.monitor_address` | `monAddr` |
|**application**||
| `application.module` | `simplex` |
| `application.send_app_address` | `Alice` |
| `application.overwrite_queue` | If `overwrite_queue` is set to true, the Maude model will compute the queue of packets at start time from the `nondeterministic_parameters.fileSize` (in Bytes), `nondeterministic_parameters.packetOverhead` (in Bytes) e.g., `true` |
| `application.send_app_queue_pkt_sizes` | The size of the packets presented to the Iodine client may be pre-populated or generated from a file size. Use `send_app_queue_pkt_sizes` to specify the list of sizes (in Bytes) of the packets that should be sent by the Application, and set `overwrite_queue` to false. e.g., `[200, 200, 100, 10]` |
| `application.app_start_send_time` | `1.0` |
| `application.rcv_app_address` | `Bob` |
| `application.include_dns_client` | `false` |
|**background_traffic**| For background traffic, a paced client (ActorType PacedClient) creates a pacing query generator. A pacing generator sends a new query when receiving a paceTO (timeout) message (and resets the timer / sends a new paceTO message).  Responses are just dropped.  |
| `background_traffic.module` | `dns` |
| `background_traffic.num_paced_clients` | the number of dns perf client actors to spawn. Each actor will get an address that is the `paced_client_name` appended with a unique index, e.g.,  `1` |
| `background_traffic.paced_client_name` | represents the actor name e.g., `dnsperf` |
| `background_traffic.paced_client_Tlimit` | is an integer denoting max runtime in seconds; we calculate the total number of querie send as this time limit multipled by `paced_client_MaxQPS`, e.g., `2` |
| `background_traffic.paced_client_MaxQPS` | specifies the maximum queries per second E.g., `50` (High rate; or Medium = `30`, Low = `15`) |
|**non-deterministic_parameters**||
| `nondeterministic_parameters.fileSize` | The size in bytes of the file that is being sent over iodine e.g, `1000` |
| `nondeterministic_parameters.packetSize` | Packet sizes are fixed in nondeerministic mode. Packet sizes will be the quotient of `fileSize` over `packetSize` and `packetOverhead`, except for the last one, which will be the remainder. E.g., `530` |
| `nondeterministic_parameters.packetOverhead` | `33` |
| `nondeterministic_parameters.maxMinimiseCount` | `0` |
| `nondeterministic_parameters.maxFragmentLen` | Iodine divides packets into fragments of fixed but settable size (in Bytes). If too large for a single query, the Maude Iodine model will split packets into smaller fragments, which it thens encapsulates into queries.  The maximum size of each fragment is settable via `maxFragmentLen` (in Bytes) but fixed for every run. E.g., `100` |
| `nondeterministic_parameters.maxFragmentTx` | The maximum number of fragment transmission tries by the iodine client. E.g., `20` |
|**probabilistic_parameters** (override the above)||
| `probabilistic_parameters.maxPacketSize` | if `packetSize` is equal to `maxPacketSize`, (in Bytes) the packet sizes are fixed. If however it is different than `packetSize`, packet sizes will be sampled uniformly between `nondeterministic_parameters.packetSize` and `maxPacketSize` (or the remaining file bytes) plus overhead. E.g.,  `530` |
| `probabilistic_parameters.pacingTimeoutDelay` | The send application paces its packet transmission not to overwhelm the Iodine link, which could cause unrecoverable packet drops. The pace interval the amount of time after which the send application is allowed to transmit a packet after the previous one. This value may be: *random*: The application random is uniformly sampled between `pacingTimeoutDelay` and `pacingTimeoutDelayMax`; or *fixed* if `pacingTimeoutDelay` and `pacingTimeoutDelayMax` are equal. E.g., `0.05` |
| `probabilistic_parameters.pacingTimeoutDelayMax` | See `pacingTimeoutDelay` above. E.g., `0.07` |
| `probabilistic_parameters.ackTimeoutDelay` | Iodine client fragment timeout delay (how long to wait before a retry if it hasnt heard a response) E.g., `1.0` |
|**output**||
| `output.directory` | `results` |
| `output.result_format` | `maude` |
| `output.save_output` | `true` |
| `output.force_save` | `true` |
| `output.visualize` | `false` |
| `output.preamble` | The set of statement to add to the preamble of the comiled Maude file e.g., `['set clear rules off .', 'set print attribute off .', 'set show advisories off .']` |


# GML Overview 
The shadow yaml file also references a network GML file path.
A [GML file](https://shadow.github.io/docs/guide/network_graph_spec.html) specifies the
network graph nodes and link characteristics. For example, below we show a node 
and an edge/link. Links have latency, jitter, and packet loss which translate to 
link delays and loss in our formal model.  
```
 node [
    id 1
    label "public_dns"
    host_bandwidth_down "1Gbps"
    host_bandwidth_up "1Gbps"
  ]
  ...
  edge [
    source 1
    target 5
    label "public_dns to application_server"
    latency "5ms"
    jitter "0ms"
    packet_loss 0.0
  ]
  ....
```