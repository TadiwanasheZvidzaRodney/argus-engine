"use client";

import { Badge, Button, cn } from "@argus/ui";
import React from "react";

export interface CanvasToolbarProps {
  onOpenSearch: () => void;
  onFitView: () => void;
  isLive: boolean;
  onToggleLive: () => void;
  nodeCount: number;
  edgeCount: number;
  showSecurity?: boolean;
  onToggleSecurity?: () => void;
  showMetrics?: boolean;
  onToggleMetrics?: () => void;
  showCost?: boolean;
  onToggleCost?: () => void;
  securityCount?: number;
  telemetryError?: string | null;
}

export function CanvasToolbar({
  onOpenSearch,
  onFitView,
  isLive,
  onToggleLive,
  nodeCount,
  edgeCount,
  showSecurity = false,
  onToggleSecurity,
  showMetrics = false,
  onToggleMetrics,
  showCost = false,
  onToggleCost,
  securityCount = 0,
  telemetryError,
}: CanvasToolbarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-2 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" size="sm" onClick={onOpenSearch}>
          🔍 Search (⌘K)
        </Button>
        <Button variant="ghost" size="sm" onClick={onFitView}>
          Fit View
        </Button>
        {onToggleSecurity && (
          <button
            type="button"
            onClick={onToggleSecurity}
            aria-pressed={showSecurity}
            className={cn(
              "inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors",
              showSecurity
                ? "border-danger/40 bg-danger/10 text-danger"
                : "border-border bg-surface text-muted-foreground hover:bg-surface-muted",
            )}
          >
            Security
            {securityCount > 0 && (
              <span className="rounded-full bg-danger/20 px-1.5 text-[10px] tabular-nums">
                {securityCount}
              </span>
            )}
          </button>
        )}
        {onToggleMetrics && (
          <button
            type="button"
            onClick={onToggleMetrics}
            aria-pressed={showMetrics}
            className={cn(
              "inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors",
              showMetrics
                ? "border-info/40 bg-info/10 text-info"
                : "border-border bg-surface text-muted-foreground hover:bg-surface-muted",
            )}
          >
            Metrics
          </button>
        )}
        {onToggleCost && (
          <button
            type="button"
            onClick={onToggleCost}
            aria-pressed={showCost}
            className={cn(
              "inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors",
              showCost
                ? "border-success/40 bg-success/10 text-success"
                : "border-border bg-surface text-muted-foreground hover:bg-surface-muted",
            )}
          >
            Cost
          </button>
        )}
        {telemetryError && (
          <span className="text-[11px] text-danger" title={telemetryError}>
            telemetry unavailable
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-xs text-muted-foreground">
          <strong>{nodeCount}</strong> nodes · <strong>{edgeCount}</strong> edges
        </span>

        <button
          type="button"
          onClick={onToggleLive}
          className="flex items-center gap-1.5 cursor-pointer"
          title={isLive ? "Click to pause real-time delta stream" : "Click to resume live updates"}
        >
          <span
            className={`size-2 rounded-full ${isLive ? "bg-success animate-ping" : "bg-muted-foreground"}`}
          />
          <Badge tone={isLive ? "success" : "neutral"}>{isLive ? "Live" : "Paused"}</Badge>
        </button>
      </div>
    </div>
  );
}
