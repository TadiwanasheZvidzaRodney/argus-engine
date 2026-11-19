"use client";

import { useId, useState } from "react";

import { type HistoryMetric, type SecurityHistoryPoint, securityTime } from "@/lib/security-types";

export interface SecuritySeries {
  key: HistoryMetric;
  label: string;
  color: string;
}

export function HistoryChart({
  title,
  points,
  series,
  compact = false,
}: {
  title: string;
  points: SecurityHistoryPoint[];
  series: SecuritySeries[];
  compact?: boolean;
}) {
  const id = useId();
  const [selected, setSelected] = useState<number | null>(null);
  const width = 600;
  const height = compact ? 90 : 215;
  const left = compact ? 2 : 36;
  const right = compact ? 2 : 14;
  const top = 10;
  const bottom = height - (compact ? 16 : 32);
  const from = Date.parse(points[0]?.bucket_start ?? "");
  const to = Date.parse(points[points.length - 1]?.timestamp ?? "");
  const x = (iso: string) =>
    left + ((Date.parse(iso) - from) / Math.max(1, to - from)) * (width - left - right);
  const values = points.flatMap((p) => series.map((s) => p[s.key]));
  const max = Math.max(1, ...values.filter((v): v is number => v !== null));
  const y = (value: number) => bottom - (value / max) * (bottom - top);
  const active = selected === null ? null : points[Math.min(selected, points.length - 1)];
  const known = values.some((v) => v !== null);
  const ticks = Array.from(new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]));

  if (!known) {
    return (
      <div
        className={
          compact ? "py-5 text-xs opacity-80" : "py-14 text-center text-xs text-muted-foreground"
        }
      >
        No recorded history
      </div>
    );
  }

  return (
    <div className="relative min-w-0" data-security-chart={title}>
      {!compact && (
        <div className="mb-2 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
          {series.map((s) => (
            <span key={s.key} className="flex items-center gap-1.5">
              <span aria-hidden className="size-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className={compact ? "h-20 w-full" : "h-52 w-full"}
        role="img"
        aria-label={title}
        onPointerMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const svgX = ((event.clientX - rect.left) / rect.width) * width;
          let nearest = 0;
          let distance = Infinity;
          points.forEach((point, index) => {
            const diff = Math.abs(x(point.timestamp) - svgX);
            if (diff < distance) {
              distance = diff;
              nearest = index;
            }
          });
          setSelected(nearest);
        }}
        onPointerLeave={() => setSelected(null)}
      >
        <title>{title}</title>
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`${id}-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity=".28" />
              <stop offset="100%" stopColor={s.color} stopOpacity=".02" />
            </linearGradient>
          ))}
        </defs>
        {!compact &&
          [0, 0.5, 1].map((fraction) => (
            <g key={fraction}>
              <line
                x1={left}
                x2={width - right}
                y1={y(max * fraction)}
                y2={y(max * fraction)}
                stroke="currentColor"
                opacity=".12"
                strokeDasharray="3 4"
              />
              <text
                x={left - 8}
                y={y(max * fraction) + 3}
                textAnchor="end"
                fill="currentColor"
                opacity=".6"
                fontSize="10"
              >
                {Math.round(max * fraction)}
              </text>
            </g>
          ))}
        {series.map((s) => {
          // Linear segments avoid spline overshoot (negative or fractional findings).
          // Nulls break the path rather than being turned into healthy zeroes.
          const segments: SecurityHistoryPoint[][] = [];
          let segment: SecurityHistoryPoint[] = [];
          for (const point of points) {
            if (point[s.key] === null) {
              if (segment.length) segments.push(segment);
              segment = [];
            } else {
              segment.push(point);
            }
          }
          if (segment.length) segments.push(segment);
          return segments.map((part) => {
            const first = part[0];
            const last = part[part.length - 1];
            if (!first || !last) return null;
            const path = part
              .map((p, i) => `${i ? "L" : "M"} ${x(p.timestamp)} ${y(p[s.key] ?? 0)}`)
              .join(" ");
            return (
              <g key={`${s.key}-${first.timestamp}`}>
                <path
                  d={`${path} L ${x(last.timestamp)} ${bottom} L ${x(first.timestamp)} ${bottom} Z`}
                  fill={`url(#${id}-${s.key})`}
                />
                <path
                  data-series={s.key}
                  d={path}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="2"
                  vectorEffect="non-scaling-stroke"
                />
                {part.length === 1 && (
                  <circle cx={x(first.timestamp)} cy={y(first[s.key] ?? 0)} r="3" fill={s.color} />
                )}
              </g>
            );
          });
        })}
        {active && (
          <line
            x1={x(active.timestamp)}
            x2={x(active.timestamp)}
            y1={top}
            y2={bottom}
            stroke="currentColor"
            strokeDasharray="3 3"
            opacity=".6"
          />
        )}
        {ticks.map((index) => {
          const point = points[index];
          if (!point) return null;
          const iso = index === 0 ? point.bucket_start : point.timestamp;
          return (
            <text
              key={index}
              x={index === 0 ? left : x(iso)}
              y={height - 3}
              textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}
              fill="currentColor"
              fontSize="10"
              opacity=".65"
            >
              {to - from <= 86400000 ? iso.slice(11, 16) : iso.slice(5, 10)}
            </text>
          );
        })}
      </svg>
      {active && (
        <div
          role="status"
          className="pointer-events-none absolute top-4 left-1/2 z-10 max-w-full -translate-x-1/2 rounded-md border border-border bg-surface px-3 py-2 text-[11px] text-foreground shadow-lg"
        >
          <p className="whitespace-nowrap font-mono text-muted-foreground">
            {securityTime(active.timestamp)}
          </p>
          {series.map((s) => (
            <p key={s.key}>
              {s.label}: <strong>{active[s.key] ?? "Not recorded"}</strong>
            </p>
          ))}
        </div>
      )}
      {!compact && (
        <label className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
          Inspect history
          <input
            type="range"
            aria-label={`Inspect ${title}`}
            className="min-w-0 flex-1 accent-accent"
            min={0}
            max={Math.max(0, points.length - 1)}
            value={selected ?? points.length - 1}
            onChange={(event) => setSelected(Number(event.target.value))}
          />
        </label>
      )}
    </div>
  );
}
