# Scenario 1 network mapping

```json
Net id mapping: {
    "client_net_mastodon": "cl[1]",
    "client_net_racetunnel": "cl[2]",
    "client_net_iodine": "cl[3]",
    "client_net_obfs": "cl[4]",
    "client_net_sky": "cl[5]",
    "server_net": "srvN",
    "minio_net": "minN",
    "mastodon_net": "masN",
    "dns_net": "dnsN"
}
```
Client id mapping
```json
"wtCl1IrcAddr": "alice_1",
"wtCl2IrcAddr": "alice_2",
"skyCl3IrcAddr": "alice_3",
"skyCl4IrcAddr": "alice_4",
"obfsCl5IrcAddr": "alice_5",
"obfsCl6IrcAddr": "alice_6",
"iodCl7IrcAddr": "alice_7",
"iodCl8IrcAddr": "alice_8",
"masCl9IrcAddr": "alice_9"
```


# Scenario 2 network mapping
```json
Net id mapping: {
    "client_net_mastodon": "cl[1]",
    "client_net_racetunnel": "cl[2]",
    "client_net_obfs": "cl[3]",
    "client_net_sky": "cl[4]",
    "server_net": "srvN",
    "minio_net": "minN",
    "mastodon_net": "masN",
    "dns_net": "dnsN"
}
```

Client id mapping
```json
"wtCl1IrcAddr": "alice_1",
"skyCl2IrcAddr": "alice_2",
"obfsCl3IrcAddr": "alice_3",
"masCl4IrcAddr": "alice_4"
```

# Included in this drop

Initial demo results (directories)
 * Scenario 1 performance/integrity/availability 7200 sec run results (163 samples)
   * scenario1_7271_perf_formatted
 * Scenario 2 performance/integrity/ availability 7200 sec run results (249 samples)
   * scenario2_7271_perf_formatted
 * Scenario 1 baseline generation run (25 prioritized combinations of vantage point and feature) 7200 sec run results (1 run results fed into the actual confidentiality runs)
   * baseline-combo1
   * baseline-combo2
 * Scenario 2 baseline generation run (25 prioritized combinations of vantage point and feature) 7200 sec run results (1 run results fed into the actual confidentiality runs) 
   * baseline-combo1
   * baseline-combo1
* Scenario 1 confidentiality (15 prioritized combinations of vantage point and feature) 910 sec run results (121 samples)
  * scenario1_910_conf_formatted  
* Scenario 1 confidentiality (10 prioritized different combinations of vantage point and feature) 1810 sec run results (35 samples)
  * scenario1_1811_conf_formatted    
* Scenario 2 confidentiality (10 prioritized combinations of vantage point and feature) 7200 sec run results (249 samples)
  * scenario2_7210_conf_formatted
* Scenario 2 confidentiality (15 prioritized different combinations of vantage point and feature) 1811 sec run results (64 samples)
  * scenario2_1811_conf_formatted  

