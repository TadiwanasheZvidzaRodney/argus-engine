"use client";

import React, { useId, useMemo, useState } from "react";

import { type TelemetryPoint } from "@/lib/ops-types";

// Helper to compute smooth SVG cubic bezier path
function generateBezierPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return "";
  const first = points[0];
  if (!first) return "";
  if (points.length === 1) return `M ${first.x},${first.y}`;

  let d = `M ${first.x.toFixed(1)},${first.y.toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = (i > 0 ? points[i - 1] : points[i]) ?? first;
    const p1 = points[i] ?? first;
    const p2 = points[i + 1] ?? p1;
    const p3 = (i !== points.length - 2 ? points[i + 2] : p2) ?? p2;

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }
  return d;
}

function formatMetricValue(
  val: number,
  format?: "percent" | "k_req" | "ms" | "tasks" | "raw",
): string {
  switch (format) {
    case "percent":
      return `${val}%`;
    case "k_req":
      return `${(val / 1000).toFixed(1)}k req/m`;
    case "ms":
      return `${val.toFixed(1)}ms`;
    case "tasks":
      return `${val} tasks`;
    case "raw":
    default:
      return String(val);
  }
}

export function AreaSparkChart({
  data,
  dataKey,
  strokeColor = "#a3e635",
  fillOpacity = 0.25,
  format = "raw",
  height = 54,
  yDomainMin,
  yDomainMax,
}: {
  data: TelemetryPoint[];
  dataKey: keyof TelemetryPoint;
  strokeColor?: string;
  fillOpacity?: number;
  format?: "percent" | "k_req" | "ms" | "tasks" | "raw";
  height?: number;
  yDomainMin?: number;
  yDomainMax?: number;
}) {
  const gradientId = useId();
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const values = useMemo(() => {
    return data.map((d) => Number(d[dataKey]) || 0);
  }, [data, dataKey]);

  const { coordinates, linePath, areaPath } = useMemo(() => {
    if (values.length === 0) {
      return { coordinates: [], linePath: "", areaPath: "" };
    }
    const computedMin = yDomainMin !== undefined ? yDomainMin : Math.min(...values);
    const computedMax = yDomainMax !== undefined ? yDomainMax : Math.max(...values);
    const spread = Math.max(0.0001, computedMax - computedMin);

    const width = 300;
    const padTop = 6;
    const padBottom = 4;
    const innerHeight = height - padTop - padBottom;

    const coords = values.map((val, idx) => {
      const x = (idx / Math.max(1, values.length - 1)) * width;
      const normalized = (val - computedMin) / spread;
      const y = height - padBottom - normalized * innerHeight;
      return { x, y };
    });

    const lPath = generateBezierPath(coords);
    const lastCoord = coords[coords.length - 1];
    const lastX = lastCoord ? lastCoord.x : width;
    const aPath = `${lPath} L ${lastX.toFixed(1)},${height} L 0,${height} Z`;

    return {
      coordinates: coords,
      linePath: lPath,
      areaPath: aPath,
    };
  }, [values, height, yDomainMin, yDomainMax]);

  if (values.length === 0) {
    return <div className="h-10 w-full opacity-40" />;
  }

  const activePoint = hoverIndex !== null ? data[hoverIndex] : null;
  const activeCoord = hoverIndex !== null ? coordinates[hoverIndex] : null;

  return (
    <div className="relative w-full select-none" onMouseLeave={() => setHoverIndex(null)}>
      {/* Tooltip on hover */}
      {activePoint && activeCoord && (
        <div
          className="pointer-events-none absolute -top-5 z-20 -translate-x-1/2 rounded bg-black/85 px-1.5 py-0.5 text-[10px] font-mono font-bold text-white shadow-md backdrop-blur-xs whitespace-nowrap"
          style={{ left: `${(activeCoord.x / 300) * 100}%` }}
        >
          {activePoint.time_label}: {formatMetricValue(Number(activePoint[dataKey]), format)}
        </div>
      )}

      <svg
        viewBox={`0 0 300 ${height}`}
        className="h-12 w-full overflow-visible"
        preserveAspectRatio="none"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
          const idx = Math.min(values.length - 1, Math.round(ratio * (values.length - 1)));
          setHoverIndex(idx);
        }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={strokeColor} stopOpacity={fillOpacity * 1.5} />
            <stop offset="100%" stopColor={strokeColor} stopOpacity={0.0} />
          </linearGradient>
        </defs>

        {/* Gradient Area Fill */}
        <path d={areaPath} fill={`url(#${gradientId})`} />

        {/* Spline Line */}
        <path
          d={linePath}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Active hover crosshair and dot */}
        {activeCoord && (
          <g>
            <line
              x1={activeCoord.x}
              y1={0}
              x2={activeCoord.x}
              y2={height}
              stroke="white"
              strokeWidth="1.2"
              strokeDasharray="2,2"
              opacity="0.8"
            />
            <circle
              cx={activeCoord.x}
              cy={activeCoord.y}
              r="3.5"
              fill={strokeColor}
              stroke="white"
              strokeWidth="1.5"
            />
          </g>
        )}
      </svg>
    </div>
  );
}

export function TelemetryDetailChart({
  title,
  subtitle,
  data,
  series,
  thresholdLine,
}: {
  title: string;
  subtitle: string;
  data: TelemetryPoint[];
  series: {
    key: keyof TelemetryPoint;
    label: string;
    color: string;
    unit?: string;
    format?: "percent" | "k_req" | "ms" | "tasks" | "raw";
    dash?: boolean;
  }[];
  thresholdLine?: {
    value: number;
    label: string;
    color?: string;
  };
}) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const { width, height, padLeft, padRight, padTop, innerWidth, innerHeight } = {
    width: 600,
    height: 180,
    padLeft: 44,
    padRight: 20,
    padTop: 16,
    innerWidth: 600 - 44 - 20,
    innerHeight: 180 - 16 - 28,
  };

  const { minVal, maxVal, seriesData } = useMemo(() => {
    const allVals: number[] = [];
    series.forEach((s) => {
      data.forEach((d) => allVals.push(Number(d[s.key]) || 0));
    });
    if (thresholdLine) {
      allVals.push(thresholdLine.value);
    }
    const computedMin = Math.min(0, ...allVals);
    const computedMax = Math.max(1, ...allVals) * 1.1;
    const spread = Math.max(0.0001, computedMax - computedMin);

    const sData = series.map((s) => {
      const coords = data.map((d, idx) => {
        const x = padLeft + (idx / Math.max(1, data.length - 1)) * innerWidth;
        const val = Number(d[s.key]) || 0;
        const normalized = (val - computedMin) / spread;
        const y = padTop + innerHeight - normalized * innerHeight;
        return { x, y, val };
      });
      return {
        ...s,
        coords,
        path: generateBezierPath(coords),
      };
    });

    return { minVal: computedMin, maxVal: computedMax, seriesData: sData };
  }, [data, series, thresholdLine, padLeft, innerWidth, padTop, innerHeight]);

  const activePoint = hoverIndex !== null ? data[hoverIndex] : null;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
        <div>
          <h3 className="text-xs font-bold text-foreground uppercase tracking-wide">{title}</h3>
          <p className="text-[11px] text-muted-foreground">{subtitle}</p>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          {series.map((s) => (
            <div
              key={String(s.key)}
              className="flex items-center gap-1.5 font-medium text-foreground"
            >
              <span className="size-2 rounded-full" style={{ backgroundColor: s.color }} />
              <span>{s.label}</span>
            </div>
          ))}
          {thresholdLine && (
            <div className="flex items-center gap-1.5 font-medium text-danger">
              <span className="h-0.5 w-3 bg-danger" />
              <span>{thresholdLine.label}</span>
            </div>
          )}
        </div>
      </div>

      <div className="relative w-full select-none pt-1" onMouseLeave={() => setHoverIndex(null)}>
        {/* Scrubber Tooltip */}
        {activePoint && hoverIndex !== null && (
          <div
            className="pointer-events-none absolute top-2 z-20 rounded-md border border-border/80 bg-surface/95 p-2 text-xs shadow-lg backdrop-blur-sm"
            style={{
              left: `${Math.min(78, Math.max(12, (hoverIndex / Math.max(1, data.length - 1)) * 100))}%`,
            }}
          >
            <div className="mb-1 border-b border-border pb-1 font-mono text-[10px] font-bold text-muted-foreground">
              {activePoint.time_label} ({new Date(activePoint.timestamp).toLocaleDateString()})
            </div>
            {series.map((s) => (
              <div
                key={String(s.key)}
                className="flex items-center justify-between gap-3 text-[11px]"
              >
                <span className="flex items-center gap-1 font-medium" style={{ color: s.color }}>
                  <span className="size-1.5 rounded-full" style={{ backgroundColor: s.color }} />
                  {s.label}:
                </span>
                <span className="font-mono font-bold text-foreground">
                  {s.format
                    ? formatMetricValue(Number(activePoint[s.key]), s.format)
                    : `${activePoint[s.key]} ${s.unit || ""}`}
                </span>
              </div>
            ))}
          </div>
        )}

        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-44 w-full overflow-visible"
          preserveAspectRatio="none"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left - padLeft) / innerWidth));
            const idx = Math.min(
              data.length - 1,
              Math.max(0, Math.round(ratio * (data.length - 1))),
            );
            setHoverIndex(idx);
          }}
        >
          {/* Horizontal Gridlines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
            const y = padTop + innerHeight * (1 - pct);
            const val = minVal + (maxVal - minVal) * pct;
            return (
              <g key={pct}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={width - padRight}
                  y2={y}
                  stroke="currentColor"
                  className="text-border/60"
                  strokeWidth="1"
                  strokeDasharray="3,3"
                />
                <text
                  x={padLeft - 6}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-muted-foreground text-[9px] font-mono"
                >
                  {val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val.toFixed(val < 1 ? 2 : 0)}
                </text>
              </g>
            );
          })}

          {/* Threshold line if defined */}
          {thresholdLine && (
            <line
              x1={padLeft}
              y1={padTop + innerHeight * (1 - (thresholdLine.value - minVal) / (maxVal - minVal))}
              x2={width - padRight}
              y2={padTop + innerHeight * (1 - (thresholdLine.value - minVal) / (maxVal - minVal))}
              stroke="#ff6b5b"
              strokeWidth="1.5"
              strokeDasharray="4,4"
            />
          )}

          {/* Render series lines */}
          {seriesData.map((s) => (
            <path
              key={String(s.key)}
              d={s.path}
              fill="none"
              stroke={s.color}
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={s.dash ? "4,4" : undefined}
            />
          ))}

          {/* Active hover crosshair vertical guide */}
          {hoverIndex !== null && seriesData[0] && seriesData[0].coords[hoverIndex] && (
            <line
              x1={seriesData[0].coords[hoverIndex].x}
              y1={padTop}
              x2={seriesData[0].coords[hoverIndex].x}
              y2={padTop + innerHeight}
              stroke="white"
              strokeWidth="1.2"
              strokeDasharray="2,2"
              opacity="0.8"
            />
          )}

          {/* Time Axis Labels along the bottom */}
          {data.map((d, idx) => {
            const step = Math.max(1, Math.floor(data.length / 6));
            if (idx % step !== 0 && idx !== data.length - 1) return null;
            const x = padLeft + (idx / Math.max(1, data.length - 1)) * innerWidth;
            return (
              <text
                key={d.timestamp}
                x={x}
                y={height - 8}
                textAnchor="middle"
                className="fill-muted-foreground text-[9px] font-mono"
              >
                {d.time_label}
              </text>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
