# ARGUS ENGINE

Building a full interactive management console with multi-account/multi-region support, continuous auto-discovery, live visual topology, and bidirectional mutation control requires an event-driven graph architecture.

---

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Visual Canvas Frontend (Browser)                      │
│   ┌─────────────────────────┐  ┌───────────────────────┐  ┌──────────────┐   │
│   │ React Flow / WebGL Graph│  │ AWS MCP Interactive   │  │ Live Metrics │   │
│   │ Visual Topology Engine  │  │ Command Engine        │  │ & Overlays   │   │
│   └────────────┬────────────┘  └──────────┬────────────┘  └──────┬───────┘   │
└────────────────┼──────────────────────────┼──────────────────────┼──────────┘
                 │ WebSockets / gRPC        │ HTTP / SSE           │ SSE
┌────────────────┼──────────────────────────┼──────────────────────┼──────────┐
│                ▼                          ▼                      ▼          │
│                             Backend API Gateway & Services                  │
│   ┌────────────────────────┐  ┌────────────────────────┐ ┌────────────────┐ │
│   │ Multi-Tenant Auth      │  │ AWS MCP Host Client    │ │ Resource Graph │ │
│   │ (OIDC / IAM Identity)  │  │ & Prompt Execution Engine│ Dynamic Aggregator│
│   └────────────────────────┘  └───────────┬────────────┘ └───────┬────────┘ │
└───────────────────────────────────────────┼──────────────────────┼──────────┘
                                            │                      │
┌───────────────────────────────────────────┼──────────────────────┼──────────┐
│ Data & Infrastructure Integration Layer   ▼                      ▼          │
│  ┌───────────────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ AWS MCP Servers           │  │ Neo4j Graph DB   │  │ PostgreSQL /     │ │
│  │ (Core, CDK, Cost, IAM)    │  │ (Resource Topology)│  │ Audit Logs & State│
│  └─────────────┬─────────────┘  └────────┬─────────┘  └────────┬─────────┘ │
└────────────────┼─────────────────────────┼─────────────────────┼────────────┘
                 │                         │                     │
                 └─────────────────────────┼─────────────────────┘
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │ Multi-Account & Multi-Region AWS Ecosystem   │
                    │ AWS Organizations + EventBridge + STS Roles  │
                    └──────────────────────────────────────────────┘

```

---

### Tech Stack Breakdown

| Architectural Layer | Recommended Technology | Role & Justification |
| --- | --- | --- |
| **Frontend Framework** | **React 19 + TypeScript + Next.js** | Provides robust client side performance, SSR for administrative panels, and type safety across complex AWS API payloads. |
| **Canvas & Visualization** | **React Flow Pro + Three.js / R3F** | **React Flow** powers the 2D infinite canvas for nested VPCs, subnets, and node connections. **Three.js** provides optional 3D multi-account macro view. |
| **State & Data Handling** | **TanStack Query + Zustand** | **Zustand** manages dynamic node dragging, multi-selection, and active UI modes. **TanStack Query** caches server-side resource queries. |
| **Graph Database Engine** | **Neo4j** (or **Amazon Neptune**) | AWS infrastructure is a graph. Relational DBs struggle with recursive relationship queries (e.g., *Find all EC2 instances routed through Gateway X to IAM Role Y*). Neo4j executes Cypher graph queries instantly. |
| **Backend & Execution API** | **FastAPI (Python 3.12)** or **NestJS (Node)** | Python native integration with `boto3` and AWS MCP server clients; WebSockets and SSE for streaming live CloudWatch metrics to UI cards. |
| **Multi-Account Auth** | **AWS STS (`AssumeRole`) + AWS Control Tower** | Secure cross-account ingestion engine using external IDs per account without storing long-lived static secret keys. |
| **Real-time Synchronization** | **Amazon EventBridge Global Bus + SQS** | Ingests `ConfigurationItemChangeNotification` events globally so node state updates on the canvas within seconds of real-world AWS changes. |

---

### Deep Dive: Architectural Sub-Systems

#### 1. Multi-Account / Multi-Region Discovery Pipeline

To visualize multi-account organizations without hitting AWS API rate limits:

* **Initial Sync:** Uses **AWS Resource Explorer** cross-account search combined with parallelized SDK workers via AWS STS to build the initial topology into Neo4j.
* **Real-time Event Engine:** AWS Config rules in target accounts emit resource changes to a Central EventBridge bus. The backend processes the delta and emits a WebSocket message to update only the modified node on the active canvas.

#### 2. Interactive AWS MCP Action Engine (Read + Write Canvas)

* **Bidirectional Canvas Operations:** Dragging a connection between an EC2 node and an S3 bucket triggers an AWS MCP IAM / CDK prompt to compute the precise policy delta.
* **Safe Mutation Protocol (Plan & Diff Preview):** Before applying any write operation, the UI runs a `cdk diff` / `terraform plan` via the MCP server and presents a visual diff overlay (green/red additions) on the node prior to user authorization.

#### 3. Real-Time Telemetry & Security Heatmaps

* **Live Telemetry Overlays:** CloudWatch metrics (CPU, IOPS, Error Rates) are streamed to node micro-charts.
* **Security & IAM Attack Surface Visualizer:** Highlights exposed security group ports ($0.0000/0$) or overly permissive IAM roles as glowing red edges directly on the interactive diagram.

---