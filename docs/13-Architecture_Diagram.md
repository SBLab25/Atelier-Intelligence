> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Customer Journey Intelligence Architecture Flow

The flowchart below models exactly the multi-agent system and server structure you provided in the reference image. 

```mermaid
flowchart TD
    %% Styling Definitions
    classDef txtHeader fill:none,stroke:none,color:#aaa,font-weight:bold,font-size:14px;
    classDef classNew fill:#185340,stroke:#3b7b62,stroke-width:1px,color:white,border-radius:6px;
    classDef classAPI fill:#184a7e,stroke:#346fab,stroke-width:1px,color:white,border-radius:6px;
    classDef classDemo fill:none,stroke:#444,stroke-width:1px,stroke-dasharray: 4 4,color:#aaa;
    classDef classMCP fill:#7d301f,stroke:#ad4f3c,stroke-width:1px,color:white,border-radius:6px;
    classDef classSup fill:#3c3289,stroke:#554caa,stroke-width:1px,color:white,border-radius:6px;
    classDef classDash fill:#8c5606,stroke:#bc7b17,stroke-width:1px,color:white,border-radius:6px;

    %% Header dividing lines
    N1["New in realtime mode — everything below this line is unchanged"]:::txtHeader
    N2["1 MCP server updated (mode-aware data source) — 3 unchanged"]:::txtHeader
    N3["Everything below is 100% unchanged in both modes"]:::txtHeader

    %% Components
    T["<b>tracker.js</b><br>browser script"]:::classNew
    C["<b>Collector API</b><br>FastAPI + DuckDB"]:::classAPI
    D["NEW components<br>demo mode uses<br>synthetic_data.py instead"]:::classDemo

    MCP1["<b>Journey data MCP</b><br>mode-aware source<br><small>updated</small>"]:::classMCP
    MCP2["<b>Friction engine MCP</b><br>pure scoring logic<br><small>unchanged</small>"]:::classMCP
    MCP3["<b>Insight MCP</b><br>LLM + ChromaDB<br><small>unchanged</small>"]:::classMCP
    MCP4["<b>Report MCP</b><br>HTML report<br><small>unchanged</small>"]:::classMCP

    W1["<b>Data worker</b><br>mode-aware params"]:::classNew
    W2["<b>Friction worker</b><br>unchanged"]:::classNew
    W3["<b>Insight worker</b><br>unchanged"]:::classNew
    W4["<b>Report worker</b><br>unchanged"]:::classNew

    SUP["<b>LangGraph supervisor</b><br>rule-based routing, interrupt_before, checkpoints — unchanged"]:::classSup
    DASH["<b>Dashboard / CLI</b><br>mode toggle added — rest unchanged"]:::classDash

    %% Structural Alignment Layering
    subgraph L1 [ ]
    direction LR
      T --> C
      C -.-> D
    end
    style L1 fill:none,stroke:none

    subgraph L2 [ ]
    direction LR
      MCP1 ~~~ MCP2 ~~~ MCP3 ~~~ MCP4
    end
    style L2 fill:none,stroke:none

    subgraph L3 [ ]
    direction LR
      W1 ~~~ W2 ~~~ W3 ~~~ W4
    end
    style L3 fill:none,stroke:none
    
    %% Main Flows
    N1 ~~~ L1
    L1 ~~~ N2
    N2 ~~~ L2
    
    MCP1 --- W1
    MCP2 --- W2
    MCP3 --- W3
    MCP4 --- W4

    L2 ~~~ N3
    N3 ~~~ L3

    W1 --> SUP
    W2 --> SUP
    W3 --> SUP
    W4 --> SUP

    SUP --> DASH
```
