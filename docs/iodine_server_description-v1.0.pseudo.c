[[]]: Things that probably do not need to be modeled and reflect implementation artifacts (or unused in CP1)
<  >: Things that keep state information
=>  : Things that probably include a rewrite
*   : Explicit messages between different components
*?  : Supposed messages that could help carry information between components but are not 
      necessarily "bits" on a wire / in the air


(Yarrick is a terrible implementation with lots of noob hacks and shortcuts.)


From what I can gather, data is exchanged over DNS queries.
The query hostname is where the data portion is.
One byte is used for client->server metadata.
One byte is used for server->client metadata.
Metadata is a packet segno and a fragment number.

The data to be sent is wrapped into a query.  Many (all?) query record types are supported.
I suspect a query without data is a ping, which the client may repeatedly send to let the server send messages downstream.
Data is encoded with a preset codec, and that gets embedded in a DNS query (hostname like <data_message>.domainname.com).

Things that the server has to remember:
From each client:
  - Last rx time from this client (used to decide whether to give up)
  - Query name (used to identify duplicates, contains data)
  - Query type (used to identify duplicates)
  - Second query name
  - Second query type (used to identify the second query)
  - "sendrealsoon" and "sendrealsoon2" queries
  - Queue from the app (used to store packets from apps while we are waiting to send current packet)
  - In packet seqno (used to figure out which packet to reconstruct)
  - In packet fragment number (used to figure out order of fragments)
  - In packet length
  - [[Out packet seqno (used to figure ACKs)]]
  - [[Out packet fragment number (used to figure fragment to send, ACKs)]]
  - [[Out packet length (used for fragmentation, when tx is done)]]
  - [[Sent out packet fragment size (used to increment the buffer offset when receiving an ACK)]]
  - Query DNS cache (though there should be no harm to omit modeling this cache, except for bugs)
    -- Note: There are two types of caches, not clear why.  One compares query type and hostname, the other the first 4 chars of the hostname.

.------.          .-------.     .--------.                .--------.     .-------.
| File |>>>>>>>>>>| Upstr |>>>>>| Outpkt |>>>>>>>>>>>>>>>>| Inpkt  |>>>>>| Upstr |   ?
|      |          |       |     |        |                |        |     |       |   ?
'------'          |  APP  | TUN | Client | DNS UDP Socket | Server | TUN |  APP  |   ?
.------.          |       |     |        |                |        |     |       |   ?
| File |<<<<<<<<<<|Downstr|<<<<<|  Inpkt |<<<<<<<<<<<<<<<<| Outpkt |<<<<<|Downstr|   ?
|______|          |_______|     |________|                |________|     |_______|


Questions left to clarify:
* What are sendrealsoon queries?
* What are second queries? >> Maybe a way to get more traffic through?


iodined app:
(Initialization)
- Do initializations:
  - Initialize and check IP address, topdomain, etc.
  - if requested to get external IP: ask opendns.com DNS service for external ip
- Open tun device
- Open DNS socket
- Loop: "tunnel()" {
  - Set timeout:=10s
  - [[for all clients:]] { // In CP1, do for the only clientid we have
    - if clientid is active, and last heard from in <60s: {
      - =>Clear client sendrealsoon query <client[clientid].sendrealsoon>:=0
      - Set timeout:=20ms
    }
  }
  - [[Select with timeout]]
  - if timeout fired: {
    - if <max_idle_time>: return
  }
  - else:
    - if bits on tun (from App): "tunnel_tun()" {
      - // Process the data from the App, these would be packets
      - *Read data from tun (from App)
      - Read clientid from <data>
      - =>Compress data (=> transform data length)
      - if client_id is already sending (<client[clientid].outpkt> len > 0):
        - =>Enqueue <data> on <queue> (=> add <data> to <queue>)
        - goto TUNNEL_DNS
      - *?Copy data to <client[clientid].outpkt>, init fields to 0
      - [[if <client[clientid].sendrealsoon> srs_query is set: {
        - *Send fragment or dataless to clientid: "send_chunk_or_dataless(query=srs_query, clientid)" {
          // Send current fragment or empty ping if no fragment
          - if <client[clientid].outpkt> fragment retx > 5: {
            - =>Clear <client[clientid].outpkt>
            - =>Grab new <client[clientid].outpkt> from <queue> if any
          }
          - if <client[clientid].outpkt> is not empty: {
            [[- Copy current fragment to tx buffer]]
            - =>Increment <client[clientid].outpkt> fragment number
          }
          - Copy ACK info to tx buffer (1st byte) (from <client[clientid].inpkt> packet sequence number, fragment number)
          - Copy <client[clientid].outpkt> fragment info to buffer (2nd byte)
          - *Send tx buffer to clientid wrapped in query DNS message
          - if <client[clientid]>.secondquery as second_query: {
            - // Not sure what this means or what a second query really is
            - *Send tx buffer to clientid wrapped in second_query DNS message
          }
          - =>Cache ping or query
          - if whole packet was this one fragment: {
            - =>Reset <client[clientid].outpkt>
            - if more packets in <queue>: did_send:=false
          }
        }
      }]]
      - else if <client[clientid]> query is set as client_query: {
        - *=>send_chunk_or_dataless(query=client_query, clientid)
      }
    }
    == Label: TUNNEL_DNS ==
    - if bits on DNS (from Client(s)): "tunnel_dns()" {
      - *Read query on DNS socket (from clientid)
      - if domain_name len from query > 0: {
        - [[if query hostname starts with 'ns.' or 'www.' "handle_a_request()": {
          - Encode a DNS A response to query dest
          - *Send response out
          - continue
        }]]
        - [[if query type is T_NS "handle_ns_request()": {
          - Encode a DNS NS response to forward request using query dest
          - *Send response out
          - continue
        }]] 
        - else: "handle_null_request()": {
          - [[if query hostname starts with 'v' or 'V' (version): {
            - *Send version ACK}
          - if query hostname starts with 'l' or 'L' (login): {
            - *Send ACK password is accepted wrapping in query DNS message}
          - if query hostname starts with 'i' or 'I' (IP number): {
            - if Check authenticated user and IP fails: *Send BADIP ACK wrapped in query DNS message, continue
            - if query IP address is IpV4: *Send Ip Addr ACK wrapped in query DNS message}
          - if query hostname starts with 'z' or 'Z': {
            - *Send ACK with hostname as data (wrapped in query DNS message)}
          - if query hostname starts with 's' or 'S' (switch): {
            - if domain_len < 3: *Send BADLEN ACK wrapped in query DNS message, continue
            - Parse, switch <clientid> codec
            - *Send ACK with codec as data (wrapped in query DNS message)}
          - if query hostname starts with '0' or 'o': {
            - if domain_len < 3: *Send BADLEN ACK wrapped in query DNS message, continue
            - Parse, switch downstream codec to clientid}
          - if query hostname starts with 'y' or 'Y' (codec check): {
            - if domain_len < 6: *Send BADLEN ACK wrapped in query DNS message, continue
            - *Send ACK with coded string, wrapped in query DNS message, continue}
          - if query hostname starts with 'r' or 'R' (clientid fragmentation size): {
            - if domain_len < 16: *Send BADLEN ACK wrapped in query DNS message, continue
            - Parse the requested fragment size
            - *Send ACK with fragment size and pseudo-random sequence, wrapped in query DNS message, continue}
          - if query hostname starts with 'n' or 'N' (downstream fragmentation size): {
            - if domain_len < 3: *Send BADLEN ACK wrapped in query DNS message, continue
            - Parse the requested fragment size, set <client[clientid]> fragsize to fragment size
            - *Send ACK wrapped in query DNS message, continue}
          ]]
          - if query hostname starts with 'p' or 'P' (ping): {
            - Unpack data from query, check length 
            - Parse coded clientid (1st byte), [[check authenticated clientid + IP]]
            - if query is already in <dns_cache> (cached):
              - *Send cached answer to clientid wrapped in query DNS message
              - continue
            - if query is duplicate of <client[clientid]> query: save in <client[clientid]> query2, continue
            - if <client[clientid].sendrealsoon> name is different than query name: {
              - Save in <client[clientid].query2>
              - continue
            }
            - Read ACK (of downstream fragment) metainfo from query (2nd byte)
            - [[Process ACK: "process_downstream_ack()" {
              - if <client[clientid].outpkt> length >= 0 and not old ACK / out fragment (from <client[clientid].{seqno, fragment_number}>):
                - // There is a current outpkt to which to apply ACK
                - =>Move <client[clientid].outpkt> by last fragment send length
                - =>Clear <client[clientid].outpkt> last fragment send length
                - if <client[clientid].outpkt> offset >= outpkt length:
                  - // Packet is done sending
                  - Reset <client[clientid].outpkt> offset and length, decrement fragment number
                  - =>Get new <client[clientid].outpkt> from <queue>
            }]]
            - if <client[clientid].sendrealsoon> srs_query set: {
              - *=>send_chunk_or_dataless(query=srs_query, clientid)}
            - if <client[clientid].query> client_query set: {
              - *=>send_chunk_or_dataless(query=client_query, clientid)}
            - Set <client[clientid].query:>=query
            - Set <client[clientid].last_packet_time>:=now 
            - [[if not Lazy: {*send other pending queryies}]]
            - continue
          }
          - if query hostname starts with digit or 'a-f' or 'A-F' (clientid upstream data): {
            - if query id == 0: (drop) continue
            - Parse coded clientid (1st byte), check authenticated clientid + IP
            - if query is already in <dns_cache> (cached):
              - *Send <cached answer> to clientid wrapped in query DNS message
              - continue
            - if query is duplicate: =>save in <client[clientid].query2>:=query, continue
            - if query matches <client[clientid].sendrealsoon>: {
              - // Duplicate as well.
              - =>Set <client[clientid].sendrealsoon2>:=query
              - continue
            }
            - Read data header containing upstream (up data) and downstream (ACK) fragment and sequence info
            - =>Process ACK: "process_downstream_ack()" (see above)
            - if query contains up data from already received packet or fragments (compare to <client[clientid].inpkt{segno, fragment_number}>): {
              - // Previous ACK probably never received by the client
              }
            - else: {
              - if up data for new packet (compare to <client[clientid].inpkt.seqno>: {
                - =>Overwrite and initialize <client[clientid].inpkt> (forget any incomplete packet)}
              - // Data for current packet, may have missing fragments, which means checksum would fail:
              - =>Save fragment number into <client[clientid].inpkt>
              - Unpack up data
              - =>Copy fragment into <client[clientid].inpkt>
              - if last fragment: {
                - Process full packet:
                  - Uncompress
                  - if packet meant for this server (ip addr match): {
                    - *Send packet to App // (via tun)
                  }
                  - [[else: send compressed packet to destination clientid, but only one client in CP1]]
                  - =>Reset <client[clientid].inpkt>
              }
            }
            - if <client[clientid].sendrealsoon> as srs_query: {
              - *=>send_chunk_or_dataless(query=srs_query, clientid)}
            - if clientid_query to clientid waiting (<client[clientid].query> is set): {
                - *=>send_chunk_or_dataless(query=client_query, clientid)}
            - =>Save query as <client[clientid].query>:=query
            - =>Record current time into <client[clientid]>: <client[clientid].last_packet_time>:=now
            - [[if <client[clientid].outpkt> and not did_send: {
              - *=>send_chunk_or_dataless(query=query, clientid)}]]
            - else if not did_send:
              - if last fragment: {
                - =>Set clientid_query to sendrealsoon client_query:=<client[clientid].sendrealsoon>} // Will send ACK in just a bit.
              - else: {
                - *=>send_chunk_or_dataless(query=query, clientid)}
            - continue
          }
        }
      }
    }
  - [[For all clients:]] {
    - if <client[clientid].sendrealsoon> is set and new as srs_query: {
        - *=>send_chunk_or_dataless(query=srs_query, clientid)}
  }
}  

