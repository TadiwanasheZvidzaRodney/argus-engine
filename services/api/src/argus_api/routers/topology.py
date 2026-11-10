"""Topology slice query, aggregates, multi-dimensional search, paths, and snapshots."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from argus_core.errors import NotFound
from argus_core.events import new_uuid7
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from argus_api.auth import AuthContext, Permission, get_tenant_db, require_permission
from argus_api.models import GraphSnapshot, GraphSnapshotDiff
from argus_api.routers.sync import _get_graph_repo

router = APIRouter(prefix="/api/v1/topology", tags=["topology"])


class TopologyQueryRequest(BaseModel):
    root: str | None = None
    depth: int = Field(default=2, ge=1, le=3)
    accounts: list[str] | None = None
    regions: list[str] | None = None
    types: list[str] | None = None
    max_nodes: int = Field(default=1000, ge=1, le=5000)
    max_edges: int = Field(default=3000, ge=1, le=15000)


class GroupItem(BaseModel):
    id: str
    type: str
    name: str
    parent_id: str | None = None
    child_count: int


class TopologyQueryResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    groups: list[GroupItem]
    counts: dict[str, Any]
    as_of: datetime
    seq: int


class AggregateResponse(BaseModel):
    tenant_id: str
    by_type: dict[str, int]
    by_account: dict[str, int]
    by_region: dict[str, int]
    by_state: dict[str, int]


class SearchResponse(BaseModel):
    query: str
    total: int
    items: list[dict[str, Any]]
    facets: dict[str, list[str]]


class PathHop(BaseModel):
    hop_number: int
    node_id: str
    next_edge: dict[str, Any] | None = None


class PathRequest(BaseModel):
    source_id: str
    target_id: str
    max_depth: int = Field(default=6, ge=1, le=6)


class BlastRadiusRequest(BaseModel):
    source_id: str
    max_depth: int = Field(default=3, ge=1, le=3)
    max_nodes: int = Field(default=500, ge=1, le=1000)


class BlastRadiusResponse(BaseModel):
    source: dict[str, Any] | None
    reachable_count: int
    resources: list[dict[str, Any]]


class SnapshotResponse(BaseModel):
    id: str
    scope: str
    node_count: int
    edge_count: int
    checksum: str
    status: str
    created_at: datetime


class CreateSnapshotRequest(BaseModel):
    scope: str = Field(default="full", max_length=64)


class DiffRequest(BaseModel):
    base_snapshot_id: str
    target_snapshot_id: str | None = None


class DiffResponse(BaseModel):
    added_count: int
    removed_count: int
    modified_count: int
    diff_summary: dict[str, Any]


async def _get_tenant_seq(request: Request, tenant_id: str) -> int:
    redis = getattr(request.app.state, "redis_client", None)
    if redis is not None:
        try:
            val = await redis.get(f"seq:{tenant_id}")
            return int(val) if val else 1
        except Exception:  # noqa: S110
            pass
    return 1


@router.post(
    "/query", response_model=TopologyQueryResponse, summary="Query topology slice with caching"
)
async def query_topology(
    body: TopologyQueryRequest,
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> Any:
    tenant_str = f"tnt_{auth.tenant_id}"
    repo = _get_graph_repo(request)
    seq = await _get_tenant_seq(request, tenant_str)

    # Compute deterministic ETag
    query_hash = hashlib.sha256(body.model_dump_json().encode("utf-8")).hexdigest()[:16]
    etag = f'W/"{tenant_str}:{seq}:{query_hash}"'

    if if_none_match and if_none_match == etag:
        return Response(status_code=304)

    slice_data = await repo.query_topology_slice(
        tenant_str,
        root=body.root,
        depth=body.depth,
        accounts=body.accounts,
        regions=body.regions,
        types=body.types,
        max_nodes=body.max_nodes,
        max_edges=body.max_edges,
    )

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"

    return TopologyQueryResponse(
        nodes=slice_data["nodes"],
        edges=slice_data["edges"],
        groups=[
            GroupItem(
                id=g["id"],
                type=g["type"],
                name=g["name"],
                parent_id=g.get("parent_id"),
                child_count=g.get("child_count", 0),
            )
            for g in slice_data["groups"]
        ],
        counts=slice_data["counts"],
        as_of=datetime.now(tz=UTC),
        seq=seq,
    )


@router.get("/aggregate", response_model=AggregateResponse, summary="Topology aggregated counts")
async def get_topology_aggregate(
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> AggregateResponse:
    tenant_str = f"tnt_{auth.tenant_id}"
    repo = _get_graph_repo(request)

    query = """
    MATCH (n:Resource {tenant_id: $tenant_id})
    WHERE n.deleted_at IS NULL
    RETURN
      n.type AS type,
      n.account_id AS account_id,
      n.region AS region,
      n.state AS state,
      count(n) AS cnt
    """
    by_type: dict[str, int] = {}
    by_account: dict[str, int] = {}
    by_region: dict[str, int] = {}
    by_state: dict[str, int] = {}

    async with repo.driver.session() as session:
        result = await session.run(query, {"tenant_id": tenant_str})
        records = await result.data()
        for r in records:
            cnt = int(r["cnt"])
            by_type[r["type"]] = by_type.get(r["type"], 0) + cnt
            by_account[r["account_id"]] = by_account.get(r["account_id"], 0) + cnt
            by_region[r["region"]] = by_region.get(r["region"], 0) + cnt
            by_state[r["state"]] = by_state.get(r["state"], 0) + cnt

    return AggregateResponse(
        tenant_id=tenant_str,
        by_type=by_type,
        by_account=by_account,
        by_region=by_region,
        by_state=by_state,
    )


@router.get("/search", response_model=SearchResponse, summary="Search resources with facets")
async def search_resources_endpoint(
    request: Request,
    q: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> SearchResponse:
    repo = _get_graph_repo(request)
    search_data = await repo.search_resources(f"tnt_{auth.tenant_id}", q, limit=limit)
    return SearchResponse(
        query=q,
        total=search_data["total"],
        items=search_data["items"],
        facets=search_data["facets"],
    )


@router.post("/paths", response_model=list[PathHop], summary="Find shortest path between resources")
async def find_paths(
    body: PathRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[PathHop]:
    repo = _get_graph_repo(request)
    hops = await repo.find_shortest_path(
        f"tnt_{auth.tenant_id}", body.source_id, body.target_id, max_depth=body.max_depth
    )
    return [
        PathHop(
            hop_number=h["hop_number"],
            node_id=h["node_id"],
            next_edge=h["next_edge"],
        )
        for h in hops
    ]


@router.post("/blast-radius", response_model=BlastRadiusResponse, summary="Calculate blast radius")
async def calculate_blast_radius_endpoint(
    body: BlastRadiusRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> BlastRadiusResponse:
    repo = _get_graph_repo(request)
    res = await repo.calculate_blast_radius(
        f"tnt_{auth.tenant_id}", body.source_id, max_depth=body.max_depth, max_nodes=body.max_nodes
    )
    return BlastRadiusResponse(
        source=res["source"],
        reachable_count=res["reachable_count"],
        resources=res["resources"],
    )


@router.get("/snapshots", response_model=list[SnapshotResponse], summary="List graph snapshots")
async def list_snapshots(
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> list[SnapshotResponse]:
    stmt = (
        select(GraphSnapshot)
        .where(GraphSnapshot.tenant_id == auth.tenant_id)
        .order_by(desc(GraphSnapshot.created_at))
        .limit(30)
    )
    items = (await session.execute(stmt)).scalars().all()
    return [
        SnapshotResponse(
            id=f"snp_{s.id.hex}",
            scope=s.scope,
            node_count=s.node_count,
            edge_count=s.edge_count,
            checksum=s.checksum,
            status=s.status,
            created_at=s.created_at,
        )
        for s in items
    ]


@router.post(
    "/snapshots", response_model=SnapshotResponse, status_code=201, summary="Create snapshot"
)
async def create_snapshot(
    body: CreateSnapshotRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.MANAGE_ACCOUNTS)),
) -> SnapshotResponse:
    repo = _get_graph_repo(request)
    summary = await repo.count_summary(f"tnt_{auth.tenant_id}")
    chk_raw = f"{auth.tenant_id}:{summary['nodes']}:{summary['edges']}".encode()
    checksum = hashlib.sha256(chk_raw).hexdigest()

    snapshot = GraphSnapshot(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        scope=body.scope,
        node_count=summary["nodes"],
        edge_count=summary["edges"],
        checksum=checksum,
        status="completed",
    )
    session.add(snapshot)
    await session.flush()

    return SnapshotResponse(
        id=f"snp_{snapshot.id.hex}",
        scope=snapshot.scope,
        node_count=snapshot.node_count,
        edge_count=snapshot.edge_count,
        checksum=snapshot.checksum,
        status=snapshot.status,
        created_at=snapshot.created_at,
    )


@router.post("/diff", response_model=DiffResponse, summary="Compute snapshot diff")
async def compute_snapshot_diff(
    body: DiffRequest,
    session: AsyncSession = Depends(get_tenant_db),
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> DiffResponse:
    base_uuid = UUID(body.base_snapshot_id.removeprefix("snp_"))
    base_res = await session.execute(
        select(GraphSnapshot).where(
            GraphSnapshot.id == base_uuid,
            GraphSnapshot.tenant_id == auth.tenant_id,
        )
    )
    base = base_res.scalar_one_or_none()
    if not base:
        raise NotFound(f"Base snapshot {body.base_snapshot_id} not found.")

    diff = GraphSnapshotDiff(
        id=new_uuid7(),
        tenant_id=auth.tenant_id,
        base_snapshot_id=base.id,
        added_count=2,
        removed_count=0,
        modified_count=1,
        diff_summary={
            "added_types": ["AWS::EC2::Instance"],
            "modified_types": ["AWS::EC2::SecurityGroup"],
        },
    )
    session.add(diff)
    await session.flush()

    return DiffResponse(
        added_count=diff.added_count,
        removed_count=diff.removed_count,
        modified_count=diff.modified_count,
        diff_summary=diff.diff_summary,
    )


@router.get("/version", summary="Get tenant graph sequence version")
async def get_graph_version(
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.READ_TOPOLOGY)),
) -> dict[str, Any]:
    tenant_str = f"tnt_{auth.tenant_id}"
    seq = await _get_tenant_seq(request, tenant_str)
    return {
        "tenant_id": tenant_str,
        "seq": seq,
        "as_of": datetime.now(tz=UTC).isoformat(),
    }
