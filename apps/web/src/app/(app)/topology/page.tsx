"use client";

import React, { useEffect, useMemo, useState } from "react";

import { CanvasToolbar } from "@/components/canvas/canvas-toolbar";
import { CommandPalette } from "@/components/canvas/command-palette";
import { InspectorDrawer } from "@/components/canvas/inspector-drawer";
import { TopologyCanvas } from "@/components/canvas/topology-canvas";
import { apiFetch } from "@/lib/api";
import type {
  NodeCost,
  NodeSecurityOverlay,
  NodeTelemetry,
  TopologyNode,
  TopologySlice,
} from "@/lib/graph-types";
import { buildHierarchicalLayout } from "@/lib/layout";

interface SecurityOverlayResponse {
  resources: Record<string, NodeSecurityOverlay>;
  counts: { resources_with_findings: number; findings: number };
}

interface TelemetrySnapshotResponse {
  samples: NodeTelemetry[];
  resolution: number;
  generated_at: string;
}

const METRIC_LIMIT = 80;

function newIdempotencyKey(prefix: string): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) return `${prefix}-${cryptoApi.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}`;
}

export default function TopologyPage() {
  const [slice, setSlice] = useState<TopologySlice | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [isLive, setIsLive] = useState(true);
  const [fitViewCount, setFitViewCount] = useState(0);

  const [showSecurity, setShowSecurity] = useState(true);
  const [showMetrics, setShowMetrics] = useState(false);
  const [showCost, setShowCost] = useState(false);
  const [security, setSecurity] = useState<Record<string, NodeSecurityOverlay>>({});
  const [telemetry, setTelemetry] = useState<Record<string, NodeTelemetry>>({});
  const [costEstimates, setCostEstimates] = useState<Record<string, NodeCost>>({});
  const [telemetryError, setTelemetryError] = useState<string | null>(null);
  const [tabVisible, setTabVisible] = useState(true);

  // Pause metric polling while the tab is hidden; resume when it regains focus.
  useEffect(() => {
    const update = () => setTabVisible(document.visibilityState !== "hidden");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  // Load initial topology slice
  useEffect(() => {
    async function loadTopology() {
      setLoading(true);
      try {
        const data = await apiFetch<TopologySlice>("/api/v1/topology/query", {
          method: "POST",
          body: { depth: 2, max_nodes: 500, max_edges: 1500 },
          timeoutMs: 5_000,
        });
        setSlice(data);
      } catch {
        setSlice(null);
      } finally {
        setLoading(false);
      }
    }
    loadTopology();
  }, []);

  // Cost overlay: loads per-resource estimates when cost layer is toggled on.
  useEffect(() => {
    if (!showCost) return;
    let cancelled = false;
    async function loadCosts() {
      try {
        const data = await apiFetch<{ resources: NodeCost[] }>("/api/v1/cost/top?limit=50", {
          timeoutMs: 4_000,
        });
        if (cancelled) return;
        const mapped: Record<string, NodeCost> = {};
        for (const r of data.resources) {
          const resWithId = r as unknown as { resource_id: string };
          if (resWithId.resource_id) {
            mapped[resWithId.resource_id] = r;
          }
        }
        setCostEstimates(mapped);
      } catch {
        if (!cancelled) setCostEstimates({});
      }
    }
    loadCosts();
    return () => {
      cancelled = true;
    };
  }, [showCost]);
  useEffect(() => {
    if (!showSecurity) return;
    let cancelled = false;
    async function loadOverlay() {
      try {
        const data = await apiFetch<SecurityOverlayResponse>("/api/v1/security/overlay", {
          timeoutMs: 4_000,
        });
        if (!cancelled) setSecurity(data.resources);
      } catch {
        if (!cancelled) setSecurity({});
      }
    }
    loadOverlay();
    return () => {
      cancelled = true;
    };
  }, [showSecurity]);

  // Metrics snapshot: bounded to visible nodes so quotas stay predictable.
  useEffect(() => {
    if (!showMetrics || !slice || !tabVisible) return;
    const resourceIds = slice.nodes
      .filter((node) => !node.type.startsWith("AWS::Internet"))
      .slice(0, METRIC_LIMIT)
      .map((node) => node.id);
    if (resourceIds.length === 0) return;
    let cancelled = false;
    async function loadMetrics() {
      setTelemetryError(null);
      try {
        const data = await apiFetch<TelemetrySnapshotResponse>("/api/v1/telemetry/snapshot", {
          method: "POST",
          idempotencyKey: newIdempotencyKey("topology-metrics"),
          body: {
            resource_ids: resourceIds,
            metrics: ["CPUUtilization"],
            resolution: 60,
            periods: 30,
          },
          timeoutMs: 10_000,
        });
        if (cancelled) return;
        const next: Record<string, NodeTelemetry> = {};
        for (const sample of data.samples) {
          next[sample.resource_id] = sample;
        }
        setTelemetry(next);
      } catch (caught) {
        if (!cancelled) {
          setTelemetry({});
          setTelemetryError(
            caught instanceof Error ? caught.message : "Telemetry could not be loaded.",
          );
        }
      }
    }
    loadMetrics();
    return () => {
      cancelled = true;
    };
  }, [showMetrics, slice, tabVisible]);

  // Global shortcut for Cmd+K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Merge overlay data into the raw slice before layout.
  const decoratedNodes = useMemo<TopologyNode[]>(() => {
    if (!slice) return [];
    return slice.nodes.map((node) => ({
      ...node,
      security: showSecurity ? security[node.id] : undefined,
      telemetry: showMetrics ? telemetry[node.id] : undefined,
      cost: showCost ? costEstimates[node.id] : undefined,
    }));
  }, [slice, security, telemetry, costEstimates, showSecurity, showMetrics, showCost]);

  // Compute layout elements
  const { nodes, edges } = useMemo(() => {
    if (!slice) return { nodes: [], edges: [] };
    return buildHierarchicalLayout(decoratedNodes, slice.edges, slice.groups);
  }, [slice, decoratedNodes]);

  const selectedNode: TopologyNode | null = useMemo(() => {
    if (!selectedNodeId) return null;
    return decoratedNodes.find((n) => n.id === selectedNodeId) || null;
  }, [selectedNodeId, decoratedNodes]);

  return (
    <div className="flex h-[calc(100vh-80px)] flex-col gap-3">
      <CanvasToolbar
        onOpenSearch={() => setSearchOpen(true)}
        onFitView={() => setFitViewCount((c) => c + 1)}
        isLive={isLive}
        onToggleLive={() => setIsLive((l) => !l)}
        nodeCount={slice?.nodes.length || 0}
        edgeCount={slice?.edges.length || 0}
        showSecurity={showSecurity}
        onToggleSecurity={() => setShowSecurity((value) => !value)}
        showMetrics={showMetrics}
        onToggleMetrics={() => setShowMetrics((value) => !value)}
        showCost={showCost}
        onToggleCost={() => setShowCost((value) => !value)}
        securityCount={Object.keys(security).length}
        telemetryError={telemetryError}
      />

      <div className="relative flex-1">
        {loading ? (
          <div className="flex size-full items-center justify-center rounded-xl border border-border bg-surface text-xs text-muted-foreground">
            Loading topology graph…
          </div>
        ) : (
          <TopologyCanvas
            initialNodes={nodes}
            initialEdges={edges}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
            fitViewTrigger={fitViewCount}
          />
        )}

        <InspectorDrawer node={selectedNode} onClose={() => setSelectedNodeId(null)} />
      </div>

      <CommandPalette
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        onSelectNode={(nodeId) => {
          setSelectedNodeId(nodeId);
        }}
      />
    </div>
  );
}
