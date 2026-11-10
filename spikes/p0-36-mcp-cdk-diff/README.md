# Spike P0-36: MCP Sandboxing & Deterministic Plan Generation

## 1. Objective
De-risk the Phase 6 Action Engine execution path. Prove that an AWS MCP server running in an unprivileged, sandboxed container can execute a dry-run diff against an AWS resource, emit a deterministic JSON change plan, and await explicit operator approval before mutating any state.

## 2. Execution Model

```text
User Natural Language Intent: "Stop idle development instances in us-east-1"
                      |
                      v
       [ LLM Parser (Read-Only) ] -> Extracts { action: "ec2.stop_instances", targets: ["i-0123..."] }
                      |
                      v
     [ Action Compiler (Deterministic) ] -> Generates Immutable Plan with pre-check query
                      |
                      v
      [ Plan Diff Preview in UI ] -> Displays exact API payload & affected resources
                      |
                      v
        [ Dual-Operator Approval ] -> Signed approval stored in PostgreSQL
                      |
                      v
 [ Ephemeral Sandboxed Worker (15min STS) ] -> Calls AWS MCP Server with scoped AssumeRole
                      |
                      v
         [ Cryptographic Audit Log ] -> Recorded to DB + S3 Object Lock
```

## 3. Findings & Safety Constraints
1. **Never allow autonomous raw IAM execution:** The LLM is strictly prohibited from generating raw IAM policies or executing arbitrary AWS CLI commands.
2. **Pinned Action Catalog:** Only actions registered in `action_catalog` with defined parameter schemas and verified risk levels can be requested.
3. **Rollback Plan Generation:** Every mutating action must compile its compensatory inverse action (e.g. `ec2.start_instances`) before execution begins.
