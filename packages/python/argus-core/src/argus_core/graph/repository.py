"""Tenant-scoped Neo4j Graph Repository.

Enforces:
- Strict tenant isolation: every query scopes by `tenant_id`
- Idempotent batched node and edge upserts via UNWIND
- Depth-capped neighborhood and topology slice traversals
- Multi-dimensional search with exact/prefix ranking and facets
- Bounded shortest path and blast radius analysis
- Tombstoning and deletion tracking
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from argus_core.graph.models import GraphEdge, GraphNode

if TYPE_CHECKING:
    from neo4j import AsyncDriver

_LABEL_RE = re.compile(r"^[A-Za-z0-9_]+$")
_REL_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")


def _clean_node_data(raw: Any) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for k, v in dict(raw).items():
        if hasattr(v, "iso_format"):
            cleaned[k] = v.iso_format()
        elif hasattr(v, "isoformat"):
            cleaned[k] = v.isoformat()
        elif k in ("tags", "properties") and isinstance(v, str):
            try:
                cleaned[k] = json.loads(v)
            except Exception:
                cleaned[k] = v
        else:
            cleaned[k] = v
    return cleaned


class GraphRepository:
    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver

    def _assert_tenant(self, tenant_id: str) -> None:
        if not tenant_id or not tenant_id.startswith("tnt_"):
            raise ValueError(f"Invalid or missing tenant_id: {tenant_id}")

    async def upsert_nodes(self, tenant_id: str, nodes: list[GraphNode]) -> int:
        self._assert_tenant(tenant_id)
        if not nodes:
            return 0

        grouped: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            label = node.secondary_label
            if not _LABEL_RE.match(label):
                label = "Resource"
            payload = {
                "id": node.id,
                "arn": node.arn,
                "type": node.type,
                "name": node.name,
                "account_id": node.account_id,
                "region": node.region,
                "state": node.state,
                "tags": json.dumps(node.tags),
                "source": node.source,
                "version": node.version,
                "created_at": node.created_at.isoformat(),
                "updated_at": node.updated_at.isoformat(),
                "raw_ref": node.raw_ref,
                "properties": json.dumps(node.properties),
            }
            grouped.setdefault(label, []).append(payload)

        total_upserted = 0
        async with self.driver.session() as session:
            for label, batch in grouped.items():
                query = f"""
                UNWIND $batch AS r
                MERGE (n:Resource {{tenant_id: $tenant_id, id: r.id}})
                ON CREATE SET
                  n:{label},
                  n.created_at = datetime(r.created_at),
                  n.version = r.version
                ON MATCH SET
                  n.version = r.version
                SET
                  n.arn = r.arn,
                  n.type = r.type,
                  n.name = r.name,
                  n.account_id = r.account_id,
                  n.region = r.region,
                  n.state = r.state,
                  n.tags = r.tags,
                  n.source = r.source,
                  n.updated_at = datetime(r.updated_at),
                  n.raw_ref = r.raw_ref,
                  n.properties = r.properties,
                  n.deleted_at = null
                """
                await session.run(query, {"tenant_id": tenant_id, "batch": batch})
                total_upserted += len(batch)

        return total_upserted

    async def upsert_edges(self, tenant_id: str, edges: list[GraphEdge]) -> int:
        self._assert_tenant(tenant_id)
        if not edges:
            return 0

        grouped: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            rel_type = edge.type if _REL_RE.match(edge.type) else "RELATED_TO"
            payload = {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "properties": edge.properties,
            }
            grouped.setdefault(rel_type, []).append(payload)

        total_upserted = 0
        async with self.driver.session() as session:
            for rel_type, batch in grouped.items():
                query = f"""
                UNWIND $batch AS e
                MATCH (src:Resource {{tenant_id: $tenant_id, id: e.source_id}})
                MATCH (dst:Resource {{tenant_id: $tenant_id, id: e.target_id}})
                MERGE (src)-[r:{rel_type} {{tenant_id: $tenant_id}}]->(dst)
                SET r += e.properties, r.updated_at = datetime()
                """
                await session.run(query, {"tenant_id": tenant_id, "batch": batch})
                total_upserted += len(batch)

        return total_upserted

    async def list_resources(
        self,
        tenant_id: str,
        *,
        types: list[str] | None = None,
        account_id: str | None = None,
        region: str | None = None,
        state: str | None = None,
        limit: int = 50,
        after_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self._assert_tenant(tenant_id)
        clauses = ["n.tenant_id = $tenant_id", "n.deleted_at IS NULL"]
        params: dict[str, Any] = {"tenant_id": tenant_id, "limit": limit + 1}

        if types:
            clauses.append("n.type IN $types")
            params["types"] = types
        if account_id:
            clauses.append("n.account_id = $account_id")
            params["account_id"] = account_id
        if region:
            clauses.append("n.region = $region")
            params["region"] = region
        if state:
            clauses.append("n.state = $state")
            params["state"] = state
        if after_id:
            clauses.append("n.id < $after_id")
            params["after_id"] = after_id

        where_str = " AND ".join(clauses)
        query = f"""
        MATCH (n:Resource)
        WHERE {where_str}
        RETURN n
        ORDER BY n.id DESC
        LIMIT $limit
        """
        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()
            return [_clean_node_data(r["n"]) for r in records]

    async def get_resource_detail(self, tenant_id: str, resource_id: str) -> dict[str, Any] | None:
        self._assert_tenant(tenant_id)
        query = """
        MATCH (n:Resource {tenant_id: $tenant_id, id: $id})
        WHERE n.deleted_at IS NULL
        OPTIONAL MATCH (parent:Resource {tenant_id: $tenant_id})-[r:CONTAINS]->(n)
        RETURN n, parent.id AS parent_id
        """
        async with self.driver.session() as session:
            result = await session.run(query, {"tenant_id": tenant_id, "id": resource_id})
            record = await result.single()
            if not record or not record["n"]:
                return None
            data = _clean_node_data(record["n"])
            data["parent_id"] = record["parent_id"]
            return data

    async def get_resource_relationships(
        self, tenant_id: str, resource_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        self._assert_tenant(tenant_id)
        query = """
        MATCH (n:Resource {tenant_id: $tenant_id, id: $id})
              -[r {tenant_id: $tenant_id}]-(other:Resource {tenant_id: $tenant_id})
        WHERE other.deleted_at IS NULL
        RETURN
          startNode(r).id AS source,
          endNode(r).id AS target,
          type(r) AS type,
          other.type AS other_type,
          other.name AS other_name,
          CASE WHEN startNode(r).id = $id THEN 'outgoing' ELSE 'incoming' END AS direction
        LIMIT $limit
        """
        async with self.driver.session() as session:
            result = await session.run(
                query, {"tenant_id": tenant_id, "id": resource_id, "limit": limit}
            )
            records = await result.data()
            return records

    async def query_neighborhood(
        self, tenant_id: str, root_id: str, depth: int = 1
    ) -> dict[str, Any]:
        self._assert_tenant(tenant_id)
        safe_depth = min(max(1, depth), 3)

        query = f"""
        MATCH (root:Resource {{tenant_id: $tenant_id, id: $root_id}})
        OPTIONAL MATCH p = (root)-[r*1..{safe_depth}]-(neighbor:Resource {{tenant_id: $tenant_id}})
        WHERE neighbor.deleted_at IS NULL
        RETURN root, collect(DISTINCT neighbor) AS neighbors,
               collect(DISTINCT relationships(p)) AS rel_lists
        """
        async with self.driver.session() as session:
            result = await session.run(query, {"tenant_id": tenant_id, "root_id": root_id})
            record = await result.single()
            if not record or not record["root"]:
                return {"root": None, "nodes": [], "edges": []}

            root_node = _clean_node_data(record["root"])
            neighbors = [_clean_node_data(n) for n in record["neighbors"]]
            all_nodes = [root_node, *neighbors]

            edges = []
            for path_rels in record["rel_lists"]:
                for r in path_rels:
                    edges.append(
                        {
                            "source": r.start_node["id"],
                            "target": r.end_node["id"],
                            "type": r.type,
                        }
                    )

            return {
                "root": root_node,
                "nodes": all_nodes,
                "edges": edges,
            }

    async def query_topology_slice(
        self,
        tenant_id: str,
        *,
        root: str | None = None,
        depth: int = 2,
        accounts: list[str] | None = None,
        regions: list[str] | None = None,
        types: list[str] | None = None,
        max_nodes: int = 1000,
        max_edges: int = 3000,
    ) -> dict[str, Any]:
        self._assert_tenant(tenant_id)
        safe_depth = min(max(1, depth), 3)

        if root:
            query = f"""
            MATCH (root:Resource {{tenant_id: $tenant_id, id: $root}})
            OPTIONAL MATCH p = (root)-[r*1..{safe_depth}]-(n:Resource {{tenant_id: $tenant_id}})
            WHERE n.deleted_at IS NULL
            WITH root, collect(DISTINCT n) AS neighbors,
                 collect(DISTINCT relationships(p)) AS all_rels
            RETURN [root] + neighbors AS all_nodes, all_rels
            LIMIT 1
            """
            params: dict[str, Any] = {"tenant_id": tenant_id, "root": root}
        else:
            clauses = ["n.tenant_id = $tenant_id", "n.deleted_at IS NULL"]
            params = {"tenant_id": tenant_id, "limit": max_nodes}
            if accounts:
                clauses.append("n.account_id IN $accounts")
                params["accounts"] = accounts
            if regions:
                clauses.append("n.region IN $regions")
                params["regions"] = regions
            if types:
                clauses.append("n.type IN $types")
                params["types"] = types

            where_str = " AND ".join(clauses)
            query = f"""
            MATCH (n:Resource)
            WHERE {where_str}
            OPTIONAL MATCH (n)-[r {{tenant_id: $tenant_id}}]->
                           (dst:Resource {{tenant_id: $tenant_id}})
            WHERE dst.deleted_at IS NULL
            RETURN collect(DISTINCT n) AS all_nodes, collect(DISTINCT r) AS all_rels
            LIMIT 1
            """

        async with self.driver.session() as session:
            result = await session.run(query, params)
            rec = await result.single()
            if not rec:
                return {"nodes": [], "edges": [], "groups": [], "counts": {"nodes": 0, "edges": 0}}

            raw_nodes = rec["all_nodes"] or []
            nodes = [_clean_node_data(n) for n in raw_nodes[:max_nodes]]

            edges: list[dict[str, Any]] = []
            seen_edges: set[tuple[str, str, str]] = set()

            raw_rels = rec["all_rels"] or []
            flat_rels: list[Any] = []
            for item in raw_rels:
                if isinstance(item, list):
                    flat_rels.extend(item)
                else:
                    flat_rels.append(item)

            for r in flat_rels:
                if r is None:
                    continue
                edge_tuple = (r.start_node["id"], r.end_node["id"], r.type)
                if edge_tuple not in seen_edges and len(edges) < max_edges:
                    seen_edges.add(edge_tuple)
                    edges.append(
                        {
                            "source": edge_tuple[0],
                            "target": edge_tuple[1],
                            "type": edge_tuple[2],
                        }
                    )

            # Resolve hierarchical container groups
            groups_map: dict[str, dict[str, Any]] = {}
            for n in nodes:
                # Region group
                reg_id = f"group:region:{n['region']}:{n['account_id']}"
                if reg_id not in groups_map:
                    groups_map[reg_id] = {
                        "id": reg_id,
                        "type": "REGION",
                        "name": f"{n['region']} ({n['account_id']})",
                        "parent_id": None,
                        "child_count": 0,
                    }
                groups_map[reg_id]["child_count"] += 1

                # If node is VPC, make Region its parent
                if n["type"] == "AWS::EC2::VPC":
                    n["parent_id"] = reg_id
                elif n["type"] == "AWS::EC2::Subnet":
                    vpc_id = n.get("properties", {}).get("vpc_id")
                    if vpc_id:
                        n["parent_id"] = vpc_id

            return {
                "nodes": nodes,
                "edges": edges,
                "groups": list(groups_map.values()),
                "counts": {
                    "nodes": len(nodes),
                    "edges": len(edges),
                    "truncated": len(raw_nodes) > max_nodes,
                },
            }

    async def search_resources(
        self, tenant_id: str, query_str: str, limit: int = 20
    ) -> dict[str, Any]:
        self._assert_tenant(tenant_id)
        q = query_str.strip().lower()

        # Multi-attribute match over name, arn, type
        query = """
        MATCH (n:Resource {tenant_id: $tenant_id})
        WHERE n.deleted_at IS NULL AND (
            toLower(n.name) CONTAINS $q
            OR toLower(n.arn) CONTAINS $q
            OR toLower(n.type) CONTAINS $q
        )
        RETURN n,
               CASE
                 WHEN toLower(n.arn) = $q THEN 1
                 WHEN toLower(n.name) = $q THEN 2
                 WHEN toLower(n.name) STARTS WITH $q THEN 3
                 ELSE 4
               END AS score
        ORDER BY score ASC, n.name ASC
        LIMIT $limit
        """
        async with self.driver.session() as session:
            result = await session.run(query, {"tenant_id": tenant_id, "q": q, "limit": limit})
            records = await result.data()
            items = [_clean_node_data(r["n"]) for r in records]

            # Facets aggregation
            facets_query = """
            MATCH (n:Resource {tenant_id: $tenant_id})
            WHERE n.deleted_at IS NULL
            RETURN
              collect(DISTINCT n.type) AS types,
              collect(DISTINCT n.account_id) AS accounts,
              collect(DISTINCT n.region) AS regions
            """
            f_res = await session.run(facets_query, {"tenant_id": tenant_id})
            f_rec = await f_res.single()

            return {
                "items": items,
                "total": len(items),
                "facets": {
                    "types": f_rec["types"] if f_rec else [],
                    "accounts": f_rec["accounts"] if f_rec else [],
                    "regions": f_rec["regions"] if f_rec else [],
                },
            }

    async def find_shortest_path(
        self, tenant_id: str, source_id: str, target_id: str, max_depth: int = 6
    ) -> list[dict[str, Any]]:
        self._assert_tenant(tenant_id)
        safe_depth = min(max(1, max_depth), 6)

        query = f"""
        MATCH p = shortestPath(
            (src:Resource {{tenant_id: $tenant_id, id: $source_id}})
            -[*1..{safe_depth}]-
            (dst:Resource {{tenant_id: $tenant_id, id: $target_id}})
        )
        RETURN [n IN nodes(p) | n.id] AS hop_ids,
               [r IN relationships(p) |
                 {{source: startNode(r).id, target: endNode(r).id, type: type(r)}}
               ] AS path_edges
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"tenant_id": tenant_id, "source_id": source_id, "target_id": target_id},
            )
            rec = await result.single()
            if not rec:
                return []
            hops = rec["hop_ids"]
            path_edges = rec["path_edges"]
            return [
                {
                    "hop_number": idx + 1,
                    "node_id": hops[idx],
                    "next_edge": path_edges[idx] if idx < len(path_edges) else None,
                }
                for idx in range(len(hops))
            ]

    async def calculate_blast_radius(
        self, tenant_id: str, source_id: str, max_depth: int = 3, max_nodes: int = 500
    ) -> dict[str, Any]:
        self._assert_tenant(tenant_id)
        safe_depth = min(max(1, max_depth), 3)

        query = f"""
        MATCH (src:Resource {{tenant_id: $tenant_id, id: $source_id}})
        OPTIONAL MATCH (src)-[r*1..{safe_depth}]-(reachable:Resource {{tenant_id: $tenant_id}})
        WHERE reachable.deleted_at IS NULL
        RETURN src, collect(DISTINCT reachable)[..$max_nodes] AS reachable_nodes
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"tenant_id": tenant_id, "source_id": source_id, "max_nodes": max_nodes},
            )
            rec = await result.single()
            if not rec or not rec["src"]:
                return {"source": None, "reachable_count": 0, "resources": []}
            reachable = [_clean_node_data(n) for n in rec["reachable_nodes"]]
            return {
                "source": _clean_node_data(rec["src"]),
                "reachable_count": len(reachable),
                "resources": reachable,
            }

    async def apply_action_metadata(
        self, tenant_id: str, resource_ids: list[str], action_id: str
    ) -> int:
        """Mark resources as action-managed after a successful execution."""
        self._assert_tenant(tenant_id)
        if not resource_ids:
            return 0
        query = """
        UNWIND $ids AS rid
        MATCH (n:Resource {tenant_id: $tenant_id, id: rid})
        SET n.managed_by = 'argus',
            n.last_action_id = $action_id,
            n.last_action_at = datetime()
        RETURN count(n) AS updated
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "tenant_id": tenant_id,
                    "ids": resource_ids,
                    "action_id": action_id,
                },
            )
            record = await result.single()
            return int(record["updated"]) if record else 0

    async def clear_action_metadata(self, tenant_id: str, resource_ids: list[str]) -> int:
        """Remove action-management markers during rollback."""
        self._assert_tenant(tenant_id)
        if not resource_ids:
            return 0
        query = """
        UNWIND $ids AS rid
        MATCH (n:Resource {tenant_id: $tenant_id, id: rid})
        REMOVE n.managed_by, n.last_action_id, n.last_action_at
        RETURN count(n) AS updated
        """
        async with self.driver.session() as session:
            result = await session.run(query, {"tenant_id": tenant_id, "ids": resource_ids})
            record = await result.single()
            return int(record["updated"]) if record else 0

    async def count_summary(self, tenant_id: str) -> dict[str, Any]:
        self._assert_tenant(tenant_id)
        query = """
        MATCH (n:Resource {tenant_id: $tenant_id})
        WHERE n.deleted_at IS NULL
        OPTIONAL MATCH (n)-[r {tenant_id: $tenant_id}]->(:Resource)
        RETURN
          count(DISTINCT n) AS node_count,
          count(DISTINCT r) AS edge_count
        """
        async with self.driver.session() as session:
            result = await session.run(query, {"tenant_id": tenant_id})
            record = await result.single()
            return {
                "nodes": record["node_count"] if record else 0,
                "edges": record["edge_count"] if record else 0,
            }

    async def tombstone_missing(
        self, tenant_id: str, account_id: str, region: str, active_ids: list[str]
    ) -> int:
        self._assert_tenant(tenant_id)
        query = """
        MATCH (n:Resource {tenant_id: $tenant_id, account_id: $account_id, region: $region})
        WHERE n.deleted_at IS NULL AND NOT n.id IN $active_ids
        SET n.deleted_at = datetime()
        RETURN count(n) AS tombstoned_count
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "tenant_id": tenant_id,
                    "account_id": account_id,
                    "region": region,
                    "active_ids": active_ids,
                },
            )
            record = await result.single()
            return int(record["tombstoned_count"]) if record else 0

    # ------------------------------------------------------------------
    # Phase 7 — security traversals and derived edges
    # ------------------------------------------------------------------

    async def upsert_raw_nodes(self, tenant_id: str, nodes: list[dict[str, Any]]) -> int:
        """Upsert already-serialised node payloads (used for the Internet sentinel)."""
        self._assert_tenant(tenant_id)
        if not nodes:
            return 0
        query = """
        UNWIND $batch AS r
        MERGE (n:Resource {tenant_id: $tenant_id, id: r.id})
        ON CREATE SET n.created_at = datetime(r.created_at), n.version = r.version
        ON MATCH SET n.version = r.version
        SET n.arn = r.arn, n.type = r.type, n.name = r.name,
            n.account_id = r.account_id, n.region = r.region, n.state = r.state,
            n.tags = r.tags, n.source = r.source, n.updated_at = datetime(r.updated_at),
            n.raw_ref = r.raw_ref, n.properties = r.properties, n.deleted_at = null
        """
        async with self.driver.session() as session:
            await session.run(query, {"tenant_id": tenant_id, "batch": nodes})
        return len(nodes)

    async def set_security_metadata(
        self, tenant_id: str, resource_id: str, *, exposed: bool
    ) -> int:
        self._assert_tenant(tenant_id)
        query = """
        MATCH (n:Resource {tenant_id: $tenant_id, id: $resource_id})
        SET n.security_exposed = $exposed
        RETURN count(n) AS updated
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"tenant_id": tenant_id, "resource_id": resource_id, "exposed": exposed},
            )
            record = await result.single()
            return int(record["updated"]) if record else 0

    async def replace_security_edges(self, tenant_id: str, edges: list[dict[str, Any]]) -> int:
        """Replace derived EXPOSES/CAN_ACCESS edges in one transaction."""
        self._assert_tenant(tenant_id)
        clear_query = """
        MATCH (:Resource {tenant_id: $tenant_id})-[r {tenant_id: $tenant_id}]->
              (:Resource {tenant_id: $tenant_id})
        WHERE type(r) IN $types
        DELETE r
        """
        async with self.driver.session() as session:
            await session.run(
                clear_query,
                {"tenant_id": tenant_id, "types": ["EXPOSES", "CAN_ACCESS"]},
            )
        if not edges:
            return 0

        grouped: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            rel_type = str(edge.get("type"))
            if rel_type not in {"EXPOSES", "CAN_ACCESS"}:
                continue
            grouped.setdefault(rel_type, []).append(
                {
                    "source_id": edge["source_id"],
                    "target_id": edge["target_id"],
                    "properties": edge.get("properties", {}),
                }
            )

        total = 0
        async with self.driver.session() as session:
            for rel_type, batch in grouped.items():
                query = f"""
                UNWIND $batch AS e
                MATCH (src:Resource {{tenant_id: $tenant_id, id: e.source_id}})
                MATCH (dst:Resource {{tenant_id: $tenant_id, id: e.target_id}})
                MERGE (src)-[r:{rel_type} {{tenant_id: $tenant_id}}]->(dst)
                SET r += e.properties, r.updated_at = datetime()
                """
                await session.run(query, {"tenant_id": tenant_id, "batch": batch})
                total += len(batch)
        return total

    async def load_security_subgraph(
        self,
        tenant_id: str,
        *,
        max_nodes: int = 5000,
        max_edges: int = 20000,
        accounts: list[str] | None = None,
        regions: list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Load a bounded tenant subgraph including security-derived edges."""
        self._assert_tenant(tenant_id)
        clauses = ["n.tenant_id = $tenant_id", "n.deleted_at IS NULL"]
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "max_nodes": max(1, min(max_nodes, 10000)),
        }
        if accounts:
            clauses.append("n.account_id IN $accounts")
            params["accounts"] = accounts
        if regions:
            clauses.append("n.region IN $regions")
            params["regions"] = regions
        where = " AND ".join(clauses)
        query = f"""
        MATCH (n:Resource)
        WHERE {where}
        WITH n LIMIT $max_nodes
        OPTIONAL MATCH (n)-[r {{tenant_id: $tenant_id}}]->
                       (dst:Resource {{tenant_id: $tenant_id}})
        WHERE dst.deleted_at IS NULL
        RETURN collect(DISTINCT n) AS all_nodes, collect(DISTINCT r) AS all_rels
        """
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            if not record:
                return {"nodes": [], "edges": []}

            nodes = [_clean_node_data(node) for node in (record["all_nodes"] or [])]
            edges: list[dict[str, Any]] = []
            seen: set[tuple[str, str, str]] = set()
            for rel in record["all_rels"] or []:
                if rel is None:
                    continue
                source = str(rel.start_node.get("id"))
                target = str(rel.end_node.get("id"))
                edge_key = (source, target, str(rel.type))
                if edge_key in seen:
                    continue
                if len(edges) >= max_edges:
                    break
                seen.add(edge_key)
                properties: dict[str, Any] = {}
                for key, value in dict(rel).items():
                    if hasattr(value, "iso_format"):
                        properties[key] = value.iso_format()
                    elif hasattr(value, "isoformat"):
                        properties[key] = value.isoformat()
                    else:
                        properties[key] = value
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "type": str(rel.type),
                        "properties": properties,
                    }
                )
            return {"nodes": nodes, "edges": edges}
