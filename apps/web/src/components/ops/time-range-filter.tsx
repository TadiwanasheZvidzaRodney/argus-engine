"use client";

import { useRouter, useSearchParams } from "next/navigation";
import React from "react";

import { type TimeRangeOption } from "@/lib/ops-types";

const RANGE_OPTIONS: { key: TimeRangeOption; label: string }[] = [
  { key: "today", label: "Today (Since 00:00)" },
  { key: "24h", label: "24h" },
  { key: "7d", label: "7 Days" },
  { key: "30d", label: "30 Days" },
];

export function TimeRangeFilter({ currentRange = "today" }: { currentRange?: TimeRangeOption }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeRange = (searchParams.get("range") as TimeRangeOption) || currentRange;

  const handleSelect = (range: TimeRangeOption) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("range", range);
    router.push(`/ops?${params.toString()}`);
  };

  return (
    <div
      role="group"
      aria-label="Time range selector"
      className="inline-flex items-center rounded-md border border-border bg-surface p-0.5 text-xs shadow-xs"
    >
      {RANGE_OPTIONS.map((opt) => {
        const isActive = activeRange === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            onClick={() => handleSelect(opt.key)}
            className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-all ${
              isActive
                ? "bg-accent text-accent-foreground shadow-xs font-bold"
                : "text-muted-foreground hover:bg-surface-muted hover:text-foreground"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
