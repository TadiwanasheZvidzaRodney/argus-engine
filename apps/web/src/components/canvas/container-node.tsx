"use client";

import { Badge } from "@argus/ui";
import type { NodeProps } from "@xyflow/react";
import React from "react";

export function ContainerNode({ data, selected }: NodeProps) {
  const nodeData = data as Record<string, unknown>;
  const label = String(nodeData.label || "Container");
  const groupType = String(nodeData.groupType || "GROUP");
  const childCount = Number(nodeData.childCount || 0);

  return (
    <div
      className={`relative size-full rounded-xl border-2 border-dashed bg-surface-muted/40 p-3 transition-colors ${
        selected ? "border-accent" : "border-border/80"
      }`}
    >
      <header className="flex items-center justify-between border-b border-border/50 pb-2">
        <div className="flex items-center gap-2">
          <Badge tone="info">{groupType}</Badge>
          <span className="truncate text-xs font-semibold text-foreground">{label}</span>
        </div>
        <span className="text-[11px] text-muted-foreground">{childCount} items</span>
      </header>
    </div>
  );
}
