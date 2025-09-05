Questions to ask T&E:
- Which Iodine implementation?  This is yarrick
- DNS or Raw UDP mode?
- Confirm Lazy mode
- What if two segments have the same data and the second ends up in a cache hit? The data would not get to the server.

[[]]: Things that probably do not need to be modeled and reflect implementation artifacts
<  >: Things that keep state information
=>  : Things that probably include a rewrite
*   : Explicit messages between different components
*?  : Supposed messages that could help carry information between components but are not 
      necessarily "bits" on a wire / in the air

Things that the client has to remember:
  - Last time it heard from the server
  - clientid (immutable)
  - Number of retransmissions
  - Out packet: seqno, fragments, num resend, etc.
  - [[In packet]]
  - send_ping_soon: Likely a variable to send a ping to server (and get more downstream data)
  - DNS id for current query (chunkid) 

.------.          .-------.     .--------.                .--------.     .-------.
| File |>>>>>>>>>>| Upstr |>>>>>| Outpkt |>>>>>>>>>>>>>>>>| Inpkt  |>>>>>| Upstr |   ?
|      |          |       |     |        |                |        |     |       |   ?
'------'          |  APP  | TUN | Client | DNS UDP Socket | Server | TUN |  APP  |   ?
.------.          |       |     |        |                |        |     |       |   ?
| File |<<<<<<<<<<|Downstr|<<<<<|  Inpkt |<<<<<<<<<<<<<<<<| Outpkt |<<<<<|Downstr|   ?
|______|          |_______|     |________|                |________|     |_______|



iodine app:
(Initialization)

- Check nameserver and top domain
- [[Open tun, sockets]]
- Client handshake:
  - Query type detection
  - *Exchange version info w/ Iodine server
  - *Exchange login info w/ Iodine server
  - (Force) DNS mode

(Execution)
"client_tunnel()"


client.c:
"client_tunnel()"

Loop
- Set timeout to 1s or send_ping_soon in ms
- [[Drop TCP packets if resending]]  (looks like an artifact of sending on sockets)
- [[Fall through select() with timeout]] (*Message received (or timer expires))
- if <last_downstream_time> > 60s: return
- if timer expired: {
  - if is_sending (<outpkt.length> > 0):
    - if <outpkt.num_retx> > 3: {
      - Reset <outpkt>
      - Send ping to server: "send_ping()": {
        - Create buffer with <clientid> and <inpkt.seqno> and <inpkt.fragment_number> (rest is random)
        - Send packet "send_packet(data=buffer)": {
          - Build hostname:=data . topdomain
          - Send query: "send_query(hostname)": {
            - =>Increment <chunkid>+=7727  // (???!?)
            - =>Set query id query.id:=<chunkid>
            - Wrap  hostname in query to make DNS message
            - *Send buffer to server (DNS)
            - Adjust timeout based on number of previously sent queries (seems to be attempt to fix issues with DNS relays timing out too quickly)
          }
        }
      }
    }
    - else: {
      - Retx <outpkt.current_fragment>: "send_chunk()" {
        - Build hostname:=<outpkt.data> . topdomain
        - Create buffer with clientid, [[encoded]] <outpkt.seqno> and <outpkt.fragment_number>, last fragment flag + arbitrary string, hostname
        - *send_query(hostname=buffer) (see above)
      }
    }
  - [[else: *send_ping()]] // Can probably omit since CP1 will not have downstream traffic (just ACKs)
  - =>Reset <send_ping_soon>
}
- else: {
  - if bits on tun (from App): "tunnel_tun()" {
    - *Read data
    - if [[Bad read]] or <is_sending>: continue
    - else: {
      - =>Compress read data (from app)
      - =>Set <outpkt.{seqno, fragment, etc.}>:=data
      - *send_chunk()
    }
  }
  - else if bits from distant: "tunnel_dns()": {
    - Read data into a DNS query: "read_dns_withq()" {
      - *Read data [[(on socket)]]
      - Decode response type (CNAME, TXT, T_MX, T_SRV), read codec
      - Unpack and decode data depending on type
    }
    - if data is not for this <clientid>: {
      - =>Set <send_ping_soon>:= 700, continue}
    - else: {
      - if read data < 2B: {
        - *Send DNS error wrapped in DNS query 
        - =>Log and set <send_ping_soon>:=900,
        - Do other checks and resets
        - continue
      }
      - else (and bad read error): {
        - if <send_ping_soon> is set: {
          - Set send_something_now
          - =>Reset <send_ping_soon>
        }
        - Read downstream query with data, and ACK metainfo from header (seqno, fragment_number, ...)
        - if data is not related to current packet, but from recent packet {
          - // Probably out of sequence duplicate
          - =>Set <send_ping_soon>:=500
        }
        - if query is not current or recent (last 2): {
          - if [lazy] and other maintenance tests: reset query counts
          - if send_something_now is set: {
            - *send_ping()
            - =>Reset <send_ping_soon>
          }
          - continue
        }
        - Set <last_downstream_time>:=now
        - if query matches current one <chunkid> [[and lazy mode]]: =>set <send_ping_soon>:=min(<send_ping_soon>, 900)
        - [[if new downstream packet and no data: {
          - // Something is not quite right, get things back on track.
          - =>Reset <inpkt> seqno, fragment number, len, etc. with received query info
          - =>Set <send_ping_soon>:=500
        }
        - if new downstream packet (compare to <inpkt.seqno>): set <inpkt>:=downstream query
        - else if duplicate <inpkt.fragment_number> >= downstream data fragment_number: {
          - =>Set <send_ping_soon>:=500
          - goto IS_SENDING
        }]]
        - [[*?Copy downstream pkt data into <inpkt>]]
        - [[=>Increment length of <inpkt.length> += data.length]]
        - [[if this is last fragment of a <inpkt> (check header flag): {
          - Uncompress data
          - *Send to App (tun write)
          - =>Set <inpkt.length>:=0
        }]]
        - [[if <inpkt.length> == 0: =>Set <send_ping_soon>:=5
        - else: Set send_something_now:=1]]
      == Label: IS_SENDING ==
      - if is_sending (<outpkt.length> > 0): {
        - if this is ACK of previous fragment (<outpkt.{seqno, fragment_number}> match): {
          - =><outpkt.offset> += <outpkt.sentlen>
          - if pkt fully sent (from <outpkt> offset vs length): {
            - Reset <outpkt>
            - =>Set <send_ping_soon>:=min(<send_ping_soon>,  20)
          }
        }
        - else: {
          - =>Move <outpkt> fragment up
          - *send_chunk()
          - =>Reset <send_ping_soon>
          - Reset send_something_now
        }
      }
      - if send_something_now: {
        - *send_ping()
        - Reset <send_ping_soon>:=0
      }
    }
  }
}



