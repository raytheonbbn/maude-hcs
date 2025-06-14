graph [
  directed 1
  id "ExampleNet"
  label "A small test network for Shadow parsing"
  node [ id 0 label "HostA" asn 100 ip_addr "10.0.0.1" host_bandwidth_up "1Gbps" host_bandwidth_down "1Gbps" ]
  node [ id 1 label "Router1" asn 200 ]
  node [ id 2 label "HostB" asn 100 ip_addr "10.0.0.2" host_bandwidth_up "5Gbps" host_bandwidth_down "1Gbps" ]
  edge [ source 0 target 1 label "Link_HostA_to_Router1" latency "10.5ms" jitter "1.2ms" packet_loss 0.01 ]
  edge [ source 1 target 0 label "Link_Router1_to_HostA" latency "10.5ms" jitter "0.0ms" packet_loss 0.0 ]
  edge [ source 1 target 2 label "Link_Router1_to_HostB" latency "15.0ms" jitter "2.0ms" packet_loss 0.005 ]
  edge [ source 2 target 1 label "Link_HostB_to_Router1" latency "15.0ms" jitter "1.8ms" packet_loss 0.008 ]
]