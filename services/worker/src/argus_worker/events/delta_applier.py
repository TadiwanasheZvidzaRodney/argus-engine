"""Applies normalized deltas to Neo4j, assigns sequence numbers, and streams deltas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from argus_core.graph.repository import GraphRepository
from argus_core.logging import get_logger
from argus_worker.events.normalizer import NormalizedDelta

if TYPE_CHECKING:
    from redis.asyncio import Redis

STREAM_MAXLEN = 10_000


@dataclass(frozen=True)
class AppliedDeltaResult:
    seq: int
    tenant_id: str
    resource_id: str
    op: str
    applied: bool
    reason: str = "ok"


class DeltaApplier:
    def __init__(self, graph_repo: GraphRepository, redis: Redis | None = None) -> None:
        self.graph_repo = graph_repo
        self.redis = redis
        self._local_seq: dict[str, int] = {}

    async def _next_seq(self, tenant_id: str) -> int:
        if self.redis is not None:
            return int(await self.redis.incr(f"seq:{tenant_id}"))
        self._local_seq[tenant_id] = self._local_seq.get(tenant_id, 0) + 1
        return self._local_seq[tenant_id]

    async def apply_delta(self, delta: NormalizedDelta) -> AppliedDeltaResult:
        log = get_logger("events.delta_applier")

        # 1. Version Guard / Last-Write-Wins Check
        async with self.graph_repo.driver.session() as session:
            check_res = await session.run(
                """
                MATCH (n:Resource {tenant_id: $tenant_id, id: $id})
                RETURN n.version AS version
                """,
                {"tenant_id": delta.tenant_id, "id": delta.resource_id},
            )
            rec = await check_res.single()
            if rec and rec["version"] and int(rec["version"]) >= delta.version:
                log.info(
                    "delta.dropped.out_of_order",
                    tenant_id=delta.tenant_id,
                    resource_id=delta.resource_id,
                    existing_version=rec["version"],
                    event_version=delta.version,
                )
                return AppliedDeltaResult(
                    seq=0,
                    tenant_id=delta.tenant_id,
                    resource_id=delta.resource_id,
                    op=delta.change_type,
                    applied=False,
                    reason="out-of-order version",
                )

        # 2. Mutate Graph
        if delta.change_type == "DELETE":
            async with self.graph_repo.driver.session() as session:
                await session.run(
                    """
                    MATCH (n:Resource {tenant_id: $tenant_id, id: $id})
                    SET n.deleted_at = datetime()
                    """,
                    {"tenant_id": delta.tenant_id, "id": delta.resource_id},
                )
        elif delta.change_type == "UPSERT" and delta.node:
            await self.graph_repo.upsert_nodes(delta.tenant_id, [delta.node])
            if delta.edges:
                await self.graph_repo.upsert_edges(delta.tenant_id, delta.edges)

        # 3. Assign Sequence and Publish to Stream
        seq = await self._next_seq(delta.tenant_id)
        change_payload: dict[str, Any] = {
            "op": delta.change_type.lower(),
            "entity": "node",
            "id": delta.resource_id,
            "version": delta.version,
            "actor": delta.actor,
            "ts": datetime.now(tz=UTC).isoformat(),
        }

        if self.redis is not None:
            stream_key = f"stream:{delta.tenant_id}:deltas"
            await self.redis.xadd(
                stream_key,
                {"seq": str(seq), "payload": json.dumps(change_payload)},
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )
            # Publish notification to WebSocket relay channel
            pubsub_channel = f"channel:{delta.tenant_id}:deltas"
            msg = json.dumps({"seq": seq, "change": change_payload})
            await self.redis.publish(pubsub_channel, msg)

        log.info(
            "delta.applied",
            tenant_id=delta.tenant_id,
            resource_id=delta.resource_id,
            op=delta.change_type,
            seq=seq,
        )

        return AppliedDeltaResult(
            seq=seq,
            tenant_id=delta.tenant_id,
            resource_id=delta.resource_id,
            op=delta.change_type,
            applied=True,
        )
