"use client";

import { Badge } from "@argus/ui";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import React from "react";

import type { NodeCost, NodeSecurityOverlay, NodeTelemetry } from "@/lib/graph-types";

function getServiceGlyph(type: string): string {
  if (type.includes("Instance")) return "EC2";
  if (type.includes("VPC")) return "VPC";
  if (type.includes("Subnet")) return "SBN";
  if (type.includes("Bucket")) return "S3";
  if (type.includes("DBInstance")) return "RDS";
  if (type.includes("Role")) return "IAM";
  if (type.includes("LoadBalancer")) return "ALB";
  if (type.includes("SecurityGroup")) return "SG";
  if (type.includes("Lambda")) return "LMB";
  return "AWS";
}

const SEVERITY_TONE = {
  critical: "danger",
  high: "warning",
  medium: "info",
  low: "neutral",
} as const;

function Sparkline({ telemetry }: { telemetry: NodeTelemetry }) {
  const points = telemetry.points.slice(-14);
  if (points.length === 0) return null;
  const max = Math.max(...points.map((point) => point.value), 1);
  const min = Math.min(...points.map((point) => point.value), 0);
  const span = max - min || 1;
  const width = 52;
  const height = 14;
  const path = points
    .map((point, index) => {
      const x = (index / Math.max(1, points.length - 1)) * width;
      const y = height - ((point.value - min) / span) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const latest = points.at(-1);
  const hasAnomaly = telemetry.anomalies.length > 0;
  return (
    <div
      className="flex items-center gap-1"
      title={latest ? `${telemetry.metric} · ${latest.value}${telemetry.unit}` : telemetry.metric}
    >
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden
        className={hasAnomaly ? "text-danger" : "text-info"}
      >
        <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      {latest && (
        <span className="text-[9px] tabular-nums text-muted-foreground">
          {Math.round(latest.value)}
          {telemetry.unit === "Percent" ? "%" : ""}
        </span>
      )}
    </div>
  );
}

export function ResourceNode({ data, selected }: NodeProps) {
  const nodeData = data as Record<string, unknown>;
  const name = String(nodeData.name || nodeData.id || "Resource");
  const type = String(nodeData.type || "AWS::Resource");
  const state = String(nodeData.state || "available");
  const isPulsing = Boolean(nodeData.isPulsing);
  const security = nodeData.security as NodeSecurityOverlay | undefined;
  const telemetry = nodeData.telemetry as NodeTelemetry | undefined;
  const cost = nodeData.cost as NodeCost | undefined;

  const isHealthy = state === "running" || state === "available" || state === "active";
  const severity = security?.max_severity;

  const ringClass =
    severity === "critical"
      ? "ring-2 ring-danger/50"
      : severity === "high"
        ? "ring-2 ring-warning/50"
        : "";

  return (
    <div
      className={`relative flex w-[220px] flex-col rounded-lg border bg-surface p-2.5 shadow-sm transition-all ${
        selected ? "border-accent ring-2 ring-accent/30" : "border-border hover:border-accent/60"
      } ${ringClass} ${isPulsing ? "animate-pulse ring-4 ring-warning" : ""}`}
    >
      <Handle type="target" position={Position.Left} className="!size-2 !bg-accent" />

      <div className="flex items-center justify-between gap-1.5">
        <div className="flex items-center gap-1.5">
          <span className="flex size-5 items-center justify-center rounded bg-surface-muted text-[10px] font-bold text-accent">
            {getServiceGlyph(type)}
          </span>
          <span className="truncate text-xs font-semibold text-foreground">{name}</span>
        </div>
        <span
          className={`size-2 shrink-0 rounded-full ${isHealthy ? "bg-success" : "bg-warning"}`}
          title={`State: ${state}`}
        />
      </div>

      <div className="mt-1 flex items-center justify-between gap-1">
        <span className="truncate text-[10px] text-muted-foreground">{type.split("::").pop()}</span>
        <div className="flex items-center gap-1">
          {cost && (
            <Badge tone="success" className="px-1.5 py-0 text-[9px] font-mono">
              ${Math.round(cost.monthly_amount)}/mo
            </Badge>
          )}
          {severity && (
            <Badge tone={SEVERITY_TONE[severity]} className="px-1.5 py-0 text-[9px]">
              {severity}
            </Badge>
          )}
          <Badge tone={isHealthy ? "neutral" : "warning"} className="text-[9px]">
            {state}
          </Badge>
        </div>
      </div>

      {(security && security.open_count > 0) || telemetry ? (
        <div className="mt-1 flex items-center justify-between border-t border-border/60 pt-1">
          {security && security.open_count > 0 ? (
            <span className="text-[9px] text-muted-foreground">
              {security.open_count} finding{security.open_count === 1 ? "" : "s"}
            </span>
          ) : (
            <span />
          )}
          {telemetry && <Sparkline telemetry={telemetry} />}
        </div>
      ) : null}

      <Handle type="source" position={Position.Right} className="!size-2 !bg-accent" />
    </div>
  );
}
