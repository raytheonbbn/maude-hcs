
# DNS Model

The high level sequence diagram
```mermaid
%%{init: {'theme': 'neo', 'themeVariables': { 'fontSize': '44px', 'fontFamily': 'Inter'}}}%%
sequenceDiagram
    participant C as Client
    participant R as Resolver
    participant NS as Nameserver

    C->>R: DNS Query (e.g., www.example.com A?)
    Note over R: Check Cache
    alt Cache Hit
        R->>C: DNS Response (from Cache)
    else Cache Miss
        R->>NS: Query (iterative process)
        NS->>R: Response / Referral
        Note over R: Process Response, Cache Data
        R->>C: DNS Response
    end
```

## DNS Resolver

High level state machine
```mermaid
graph TD
    A[Idle] --> B{Cache Hit?}
    B -- Yes --> C[Respond from Cache]
    B -- No --> D[Determine Target NS]
    D --> E{NS Address Known?}
    E -- Yes --> F[Send Query to NS]
    E -- No --> G[Resolve NS Address]
    G --> H[Cache NS Address] --> F[Send Query to NS]
    F --> I[Wait for Response]
    I --> J{Process Response}
    J --> K{CNAME?}
    K -- Yes --> L{Follow CNAME}
    L --> B{Cache Hit?}
    K -- No --> M{Answer/Update State}
    M -- Client Query --> C[Respond from Cache]
    M -- Resolver Subquery --> N[Update SLISTs, Send/Abort]
    N --> O{All Queries Processed?}
    O -- Yes --> A[Idle]
    O -- No --> F[Send Query to NS]
```

Cache check state machine
```mermaid
%%{init: {'theme': 'neo', 'themeVariables': { 'fontSize': '44px', 'fontFamily': 'Inter'}}}%%
graph LR
    A[Client Query In] --> B{Resolver};
    B -- "1 Prune Cache" --> C["Check Cache (Data, NXDOMAIN, NoData)"];
    C -- Cache Hit --> D[Construct & Send Response to Client];
    C -- Cache Miss --> E[Proceed to Query Nameservers];
```

Cache miss state machine
```mermaid
graph TD
    A[Cache Miss] --> B(Find Best NS);
    B --> C{NS Addr Known?};
    C -- Yes --> D(Prep Query w/ QMIN);
    C -- No --> E(Create Subquery for NS Addr);
    E --> F(Queue Original Query);
    D --> G{Work Budget OK?};
    G -- Yes --> H[Send Query to NS];
    G -- No --> I[Abort/Queue Query];
    H --> J(Wait for Response);
```

## Nameserver

```mermaid
%%{init: {'theme': 'neo', 'themeVariables': { 'fontSize': '44px', 'fontFamily': 'Inter'}}}%%
graph TD
    subgraph "Incoming Query Processing"
        A["Query Arrives  (from SRC: Resolver or Client)"] --> B{"Client Query AND  Forwarding Enabled AND  Not Authoritative?"};
        B -- "Yes (Forward Flow)" --> C["Store Client Info  (in queriesFwd)"];
        C --> D["Forward Query to Upstream (ADDR)"];
        D --> E["End (Waiting for Response)"];

        B -- "No (Direct Processing Flow)" --> F["Calculate Response = matchDown()  (Data/NXDOMAIN/Referral...)"];
        F --> G["Send Response to Original Source (SRC)"];
        G --> H["End"];
    end

    subgraph "Incoming Forwarded Response Processing"
        I["Forwarded Response Arrives  (from Upstream ADDR)"] --> J["Match Response ID to stored query  (in queriesFwd)"];
        J --> K["Retrieve Original Client Addr (CL)"];
        K --> L["Remove Stored Info (from queriesFwd)"];
        L --> M["Forward Response to Original Client (CL)"];
        M --> N["End"];
    end
```

## Scheduler 

```mermaid
%%{init: {'theme': 'neo', 'themeVariables': { 'fontSize': '44px', 'fontFamily': 'Inter'}}}%%
graph TD
    subgraph "System State"
        State("Actors + Scheduler {GT | SL}")
    end

    subgraph "Message Scheduling"
        NewMsg("[t_rel, M, 0] Arrives") --> CalcTime("t_abs = GT + t_rel");
        CalcTime --> Insert("Insert [t_abs, M, 0] into SL maintaining time order");
        Insert --> State;
    end

    subgraph "Simulation Step (tick/run calls step repeatedly)"
        StartStep("Start 'step'") --> CheckSL{"SL empty?"};
        CheckSL -- "No" --> CheckLimit{"GT <= LIMIT?"};
        CheckSL -- "Yes" --> Stop("Wait / End Tick");
        CheckLimit -- "No" --> Stop;
        CheckLimit -- "Yes" --> Extract("Extract first msg [t_next, M_next, 0] from SL");
        Extract --> AdvanceGT("Set GT = t_next");
        AdvanceGT --> Activate("Make {t_next, M_next} active");
        Activate --> Process("Actors process active message");
        Process --> Loop("Back to Start 'step' / CheckSL for next iteration");
         Loop --> StartStep;
    end

    State --> StartStep;

    style Stop fill:#f9f,stroke:#333,stroke-width:2px
```    

# Iodine Model

Sequence diagram summarizing all the interactions

```mermaid
---
config:
  theme: neo
  themeVariables:
    fontSize: 44px
    fontFamily: Inter
  layout: elk
---
sequenceDiagram
    participant Alice
    participant WClient
    participant Resolver
    participant WNameserver
    participant Bob

    Alice ->> WClient: Send Packet(P)
    activate WClient
    Note over WClient: Fragments Packet P (rule: iClientEmbedding)
    WClient ->> Resolver: DNS Query(ID1, Frag1)
    activate Resolver
    Note over WClient: Set ACK Timer (Frag1)
    Resolver ->> WNameserver: Forward Query(ID1, Frag1)
    activate WNameserver
    Note over WNameserver: Process Frag1 (rule: wnameserver-receive-query-weird / extractS)
    WNameserver -->> Resolver: DNS Response(ID1, ACK Frag1)
    opt Packet Complete
        Note over WNameserver: (rule: wnameserver-receive-query-weird / updateRcvApp)
        WNameserver -->> Bob: Send Reassembled Packet
    end
    deactivate WNameserver
    Resolver -->> WClient: Forward Response(ID1, ACK Frag1)
    deactivate Resolver
    activate WClient
    Note over WClient: Process ACK, Matches Frag1 (rule: iClientExtractFromServer)
    Note over WClient: Move to Frag2
    WClient ->> Resolver: DNS Query(ID2, Frag2)
    activate Resolver
    Note over WClient: Set ACK Timer (Frag2)
    Resolver ->> WNameserver: Forward Query(ID2, Frag2)
    activate WNameserver
    Note over WNameserver: Process Frag2 (rule: wnameserver-receive-query-weird / extractS)
    WNameserver -->> Resolver: DNS Response(ID2, ACK Frag2)
    opt Packet Complete
        Note over WNameserver: (rule: wnameserver-receive-query-weird / updateRcvApp)
        WNameserver -->> Bob: Send Reassembled Packet
    end
    deactivate WNameserver
    Resolver -->> WClient: Forward Response(ID2, ACK Frag2)
    deactivate Resolver
    activate WClient
    Note over WClient: Process ACK, Matches Frag2 (rule: iClientExtractFromServer)
    Note over WClient: ...continues until last fragment...

    alt Timeout and Retransmit (Example for FragN)
        Note over WClient: ACK Timer for FragN expires
        WClient ->> WClient: Check Attempts < Max (rule: iClientTimeout)
        WClient ->> Resolver: Re-Send DNS Query(ID_N, FragN)
        activate Resolver
        Note over WClient: Reset ACK Timer (FragN)
        Resolver ->> WNameserver: Forward Query(ID_N, FragN)
        activate WNameserver
        WNameserver -->> Resolver: DNS Response(ID_N, ACK FragN)
        deactivate WNameserver
        Resolver -->> WClient: Forward Response(ID_N, ACK FragN)
        deactivate Resolver
        activate WClient
        Note over WClient: Process ACK...
    else Timeout and Abort (Example for FragN)
        Note over WClient: ACK Timer for FragN expires
        WClient ->> WClient: Check Attempts >= Max (rule: iClientTimeout)
        WClient ->> WClient: Drop Packet Fragments
        WClient ->> Alice: Signal Failed / Ready
    else Old ACK Received (Example: ACK for Frag(N-1) after FragN sent)
        Resolver -->> WClient: Forward Response(ID_N-1, ACK Frag(N-1))
        Note over WClient: Ignore Old ACK (rule: wClientExtractOldResponseFromServer-ignore)
    end
    deactivate WClient
```


## Iodine server

```mermaid
---
config:
  theme: neo
  themeVariables:
    fontSize: 44px
    fontFamily: Inter
  layout: fixed
---
flowchart TD
    A["Query Arrives"] --> B@{ label: "Is Query 'Weird'?" }
    B -- No (Normal) --> C["Pass Query Internally to wrappedNS"]
    C --> D["Wait for Internal Response"]
    D -- Response Ready --> E["Relay Response from wrappedNS to Original Querier"]
    E --> F["End"]
    B -- Yes (Weird) --> G["Extract Fragment (extractS)\n& Update Internal State"]
    G --> H["Send DNS Response (ACK)\nto Querier"]
    H --> I{"Packet Complete?\n(updateRcvApp)"}
    I -- Yes --> J["Send Reassembled Packet\nto Target App (Bob)"]
    J --> K["End"]
    I -- No --> K
    B@{ shape: diamond}
```

## Iodine client

```mermaid
---
config:
  theme: neo
  themeVariables:
    fontSize: 44px
    fontFamily: Inter
  layout: elk
---
flowchart TD
 subgraph subGraph0["Main States"]
        Idle["Idle / Ready for Packet"]
        Waiting["Waiting for ACK / Timeout"]
  end
    Idle -- Receive Packet from App --> FragPkt["Fragment Packet & Store Fragments"]
    FragPkt --> SendFrag["Send Current Fragment Query & Set numAttempts=1"]
    SendFrag --> SetTimeout["Set ACK Timeout"]
    SetTimeout --> Waiting
    Waiting -- Receive DNS Response --> CheckResp{"Is ACK for Current Fragment?"}
    CheckResp -- Yes --> ProcACK["Process ACK & Reset numAttempts"]
    ProcACK --> CheckDone{"All Fragments Sent?"}
    CheckDone -- Yes --> SignalDone["Signal App Complete"]
    SignalDone --> Idle
    CheckDone -- No --> MoveNext["Move to Next Fragment"]
    MoveNext --> SendFrag
    CheckResp -- No (Old ACK) --> IgnoreResp["Ignore Response"]
    IgnoreResp --> Waiting
    Waiting -- Receive ACK Timeout Msg --> CheckTimeout{"Is Timeout for Current Fragment?"}
    CheckTimeout -- Yes --> ProcTimeout["Process Timeout"]
    ProcTimeout --> CheckAttempts{"Max Attempts Reached?"}
    CheckAttempts -- Yes --> DropPkt["Drop Fragments & Signal App Failed/Ready"]
    DropPkt --> Idle
    CheckAttempts -- No --> IncAttempts["Increment numAttempts"]
    IncAttempts --> ResendFrag["Resend Current Fragment Query"]
    ResendFrag --> SetTimeout
    CheckTimeout -- No (Old Timeout) --> IgnoreTimeout["Ignore Timeout"]
    IgnoreTimeout --> Waiting
```
## Send app (Alice)

```mermaid
---
config:
  theme: neo
  themeVariables:
    fontSize: 44px
    fontFamily: Inter
  layout: elk
---
graph TD
    subgraph "State"
        S["queue: PacketList; sent: PacketList; numAdmittedPkts: Nat; nwclientReady: Bool"]
    end

    subgraph "Trigger: Receive 'start' Message (from WClient)"
        T1_Start["'start' Received"] --> T1_SetReady["Set wclientReady = true"];
        T1_SetReady --> T1_Check{"numAdmittedPkts > 0 AND queue not empty?"};
        T1_Check -- "Yes" --> T1_Send["Send Packet from queue, Decrement numAdmittedPkts, Set wclientReady = false"];
        T1_Send --> T1_SetTimeout["Schedule pktTimeout"];
        T1_SetTimeout --> T1_End["End"];
        T1_Check -- "No" --> T1_End;
    end

    subgraph "Trigger: Receive 'pktTimeout' Message (Self)"
        T2_Start["'pktTimeout' Received"] --> T2_IncPkts["Increment numAdmittedPkts"];
        T2_IncPkts --> T2_Check{"wclientReady == true AND queue not empty?"};
        T2_Check -- "Yes" --> T2_Send["Send Packet from queue Decrement numAdmittedPkts Set wclientReady = false"];
        T2_Send --> T2_SetTimeout["Schedule next pktTimeout"];
        T2_SetTimeout --> T2_End["End"];
        T2_Check -- "No" --> T2_End;
    end
```

## Receive App

```mermaid
---
config:
  theme: neo
  themeVariables:
    fontSize: 44px
    fontFamily: Inter
  layout: elk
---
graph TD
    subgraph "State"
        S["rcvd: PacketList"]
    end

    subgraph "Trigger: Receive Packet Message (from WNameserver)"
        T1_Start["Packet Message Received"] --> T1_Store["Prepend Packet to 'rcvd' list"];
        T1_Store --> T1_End["End (Return to Idle)"];
    end
```