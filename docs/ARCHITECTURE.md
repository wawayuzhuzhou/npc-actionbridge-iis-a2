# ActionBridge architecture

Frozen v1 is `a613062`. Baseline B and enhanced A are alternative conditions with
separate SQLite databases; shared inference does not merge their histories.
The diagram is an implementation description, not an experiment or screenshot.

```mermaid
flowchart TD
    P[Player text and held-items summary] --> API[FastAPI dialogue route]
    DB[(Selected B or A SQLite)] -->|NPC and player NPC history| API
    API --> R[FAISS Top 5 facts]
    R --> Q[Qwen structured dialogue and proposed action]
    Q -->|B| B[Store raw conversation; immediate Godot dispatch]
    B --> DB
    B --> S[Actual local Gold Katana and door nodes]
    Q -->|A action none| N[Store and display ordinary dialogue]
    N --> DB
    Q -->|A consequential action| PR[Store proposal; outward action none]
    PR --> DB
    PR --> V[Godot validates actual local state]
    S --> V
    V -->|invalid| RJ[Rejected without execution]
    V -->|valid| C[Player Confirm or Cancel]
    C -->|Cancel| CA[Cancelled without execution]
    C -->|Confirm| RV[Revalidate before execution]
    S --> RV
    RV -->|invalid| RJ
    RV -->|valid| EX[Execute original action; verify actual post state]
    EX --> S
    RJ --> O[Outcome report and factual feedback]
    CA --> O
    EX --> O
    O --> CH[Backend checks trusted report consistency]
    CH --> TX[Atomic proposal and conversation update]
    TX --> DB
    O -->|save fails| RET[Retain same report; retry saving only]
    RET --> CH
```

Only `Committed` preserves the consequential action in the linked conversation;
`Rejected`, `Cancelled` and `Failed` do not. Backend checks can downgrade an
inconsistent committed report, but do not independently observe inventory.
Save retry blocks new generation and does not execute the action again or call
the model. In an indoor shop, the dojo node may be absent and door state null.
Confirming a state-valid proposal does not prove correct intent interpretation.

Source: [baseline context/storage](../adapter/qwen_baseline/fastapi_app.py),
[proposal wrapper](../adapter/actionbridge/api.py),
[Godot boundary](../adapter/actionbridge/godot/ActionBridge.gd),
[save-only retry](../adapter/actionbridge/godot/ActionBridgeUI.gd), and
[outcome store](../adapter/actionbridge/store.py).
