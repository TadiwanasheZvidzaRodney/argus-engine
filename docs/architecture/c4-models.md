# Argus Engine — C4 Architecture Models

> **Status:** Ratified in Phase 0  
> **Reference Architecture:** `ARGUS_ENGINE_HIGH_LEVEL_SYSTEM_ARCHITECTURE.md`

---

## 1. System Context (Level 1)

```text
+-------------------------------------------------------------------------+
|                              AWS CUSTOMER                               |
| (DevOps, Platform Engineers, SREs, Security Ops, Cloud Architects)      |
+-------------------------------------------------------------------------+
       |                                                 ^
       | Interacts with UI & approves plans              | Real-time alerts
       v                                                 | & topologies
+-------------------------------------------------------------------------+
|                              ARGUS ENGINE                               |
|  - Real-time AWS topology graph                                         |
|  - Telemetry & security overlay                                         |
|  - Safe, deterministic MCP action engine                                |
|  - Cost attribution & macro view                                        |
+-------------------------------------------------------------------------+
       |                                                 ^
       | Assumes STS role with scoped policy             | Ingests Config,
       | Executes approved plans via MCP                 | CloudTrail, EventBridge
       v                                                 |
+-------------------------------------------------------------------------+
|                          CUSTOMER AWS ESTATE                            |
| (Management Account, Workload Accounts, VPCs, IAM, EC2, ECS, RDS, S3)  |
+-------------------------------------------------------------------------+
```

---

## 2. Container Diagram (Level 2)

```text
+-----------------------------------------------------------------------------+
|                                  USER BROWSER                               |
|  +-----------------------------------------------------------------------+  |
|  | Single Page Application (Next.js 16, React 19, Tailwind, React Flow)  |  |
|  +-----------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------+
             | (HTTPS / Cookies)                       ^ (WSS / JSON frames)
             v                                         |
+------------------------------------+   +------------------------------------+
|       NEXT.JS BFF WEB SERVER       |   |        WEBSOCKET GATEWAY           |
| (App Router, OIDC session manager) |   | (FastAPI, Redis pub/sub relay)     |
+------------------------------------+   +------------------------------------+
             | (HTTP / SigV4)                          ^
             v                                         | (Publish delta)
+------------------------------------+                 |
|             API GATEWAY            |                 |
| (FastAPI, OpenAPI 3.1, RFC 9457)   |                 |
+------------------------------------+                 |
       |                   |                           |
       v                   v                           |
+--------------+    +--------------+    +-------------------------------------+
|  POSTGRESQL  |    |    NEO4J 5   |    |           WORKER DAEMONS            |
| (Aurora v2,  |    | (Aura /      |    | - Discovery worker (Explorer API)   |
|  RLS multi-  |    |  Cypher,     |<---| - Real-time sync (EventBridge/SQS)  |
|  tenancy)    |    |  topology)   |    | - Action engine (MCP runtime)       |
+--------------+    +--------------+    +-------------------------------------+
       |                   |                           ^
       +---------+---------+                           |
                 |                                     |
                 v                                     |
        +------------------+                           |
        |  REDIS 7 CLUSTER |---------------------------+
        | (Cache, Locks,   |
        |  Idempotency)    |
        +------------------+
```

---

## 3. Data Flow Pathways

1. **Topology Discovery Flow:**
   Worker assumes read-only role via STS -> queries AWS Resource Explorer 2 -> normalizes AWS entities into standard JSON -> writes nodes & edges to Neo4j -> publishes `argus.resource.discovered.v1` -> WebSocket gateway relays delta to connected canvas browsers.
2. **Safe Action Flow:**
   User requests action -> LLM suggests action type & parameters -> Action Engine compiles deterministic dry-run plan -> displays side-by-side diff in UI -> Operator approves -> Worker assumes scoped execution role -> MCP executes via pinned API calls -> verifier checks post-state -> logs tamper-evident audit record to PostgreSQL and S3 Object Lock.
