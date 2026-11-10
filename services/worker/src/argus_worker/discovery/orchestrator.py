"""Discovery backfill orchestrator."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from argus_api.models import ResourceCoverage, SyncJob, SyncJobShard
from argus_core.events import EventType, build_envelope, new_uuid7
from argus_core.graph.repository import GraphRepository
from argus_core.logging import get_logger
from argus_worker.discovery.adapters.sample_data import build_enterprise_topology
from argus_worker.discovery.resolvers import RelationshipResolver
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from argus_worker.queue import EventSink


@dataclass(frozen=True)
class SyncSummary:
    job_id: UUID
    tenant_id: str
    account_id: str
    nodes_ingested: int
    edges_ingested: int
    duration_ms: float


class SyncOrchestrator:
    def __init__(self, graph_repo: GraphRepository, event_sink: EventSink | None = None) -> None:
        self.graph_repo = graph_repo
        self.event_sink = event_sink

    async def run_sync_for_account(
        self,
        *,
        db_session: AsyncSession,
        job_id: UUID,
        tenant_id: str,
        account_uuid: UUID,
        account_id: str,
        regions: list[str] | None = None,
    ) -> SyncSummary:
        log = get_logger("discovery.orchestrator")
        start = time.perf_counter()
        active_regions = regions or ["us-east-1", "us-west-2"]

        log.info(
            "sync.started",
            job_id=str(job_id),
            tenant_id=tenant_id,
            account_id=account_id,
            regions=active_regions,
        )

        total_nodes = 0
        total_edges = 0
        coverage_counts: dict[str, int] = {}

        for reg in active_regions:
            shard_id = new_uuid7()
            shard = SyncJobShard(
                id=shard_id,
                job_id=job_id,
                tenant_id=UUID(tenant_id.removeprefix("tnt_")),
                service="all-supported",
                region=reg,
                status="running",
            )
            db_session.add(shard)
            await db_session.flush()

            # 1. Discover or synthesize topology
            nodes = build_enterprise_topology(
                tenant_id=tenant_id,
                account_id=account_id,
                region=reg,
            )

            # 2. Resolve relationships
            edges = RelationshipResolver.resolve(tenant_id, nodes)

            # 3. Ingest into Neo4j
            n_count = await self.graph_repo.upsert_nodes(tenant_id, nodes)
            e_count = await self.graph_repo.upsert_edges(tenant_id, edges)

            total_nodes += n_count
            total_edges += e_count

            for node in nodes:
                coverage_counts[node.type] = coverage_counts.get(node.type, 0) + 1

            shard.status = "succeeded"
            shard.items_discovered = len(nodes)
            shard.items_upserted = n_count + e_count
            await db_session.flush()

        # Update resource coverage in Postgres
        tid_uuid = UUID(tenant_id.removeprefix("tnt_"))
        for res_type, count in coverage_counts.items():
            existing_stmt = select(ResourceCoverage).where(
                ResourceCoverage.tenant_id == tid_uuid,
                ResourceCoverage.account_id == account_uuid,
                ResourceCoverage.resource_type == res_type,
            )
            cov = (await db_session.execute(existing_stmt)).scalar_one_or_none()
            if cov:
                cov.count = count
                cov.last_seen_at = datetime.now(tz=UTC)
            else:
                db_session.add(
                    ResourceCoverage(
                        id=new_uuid7(),
                        tenant_id=tid_uuid,
                        account_id=account_uuid,
                        resource_type=res_type,
                        supported=True,
                        count=count,
                    )
                )

        # Update Job record
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        await db_session.execute(
            update(SyncJob)
            .where(SyncJob.id == job_id)
            .values(
                status="succeeded",
                completed_at=datetime.now(tz=UTC),
                resource_count=total_nodes,
            )
        )
        await db_session.flush()

        # Emit completion event
        if self.event_sink:
            envelope = build_envelope(
                event_type=EventType.SYNC_COMPLETED,
                source="argus.discovery",
                tenant_id=tenant_id,
                account_id=account_id,
                idempotency_key=f"sync:{job_id}",
                data={
                    "job_id": str(job_id),
                    "nodes": total_nodes,
                    "edges": total_edges,
                    "duration_ms": duration_ms,
                },
            )
            await self.event_sink.publish(envelope)

        log.info(
            "sync.completed",
            job_id=str(job_id),
            nodes=total_nodes,
            edges=total_edges,
            duration_ms=duration_ms,
        )

        return SyncSummary(
            job_id=job_id,
            tenant_id=tenant_id,
            account_id=account_id,
            nodes_ingested=total_nodes,
            edges_ingested=total_edges,
            duration_ms=duration_ms,
        )
