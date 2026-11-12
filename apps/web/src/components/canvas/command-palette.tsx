"use client";

import { Badge } from "@argus/ui";
import React, { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

interface SearchResult {
  id: string;
  name: string;
  type: string;
  region: string;
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onSelectNode: (nodeId: string) => void;
}

export function CommandPalette({ open, onClose, onSelectNode }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await apiFetch<{ items: SearchResult[] }>(
          `/api/v1/topology/search?q=${encodeURIComponent(query)}&limit=10`,
          { timeoutMs: 2_000 },
        );
        setResults(res.items || []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-24 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border border-border bg-surface p-3 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border pb-2">
          <input
            autoFocus
            type="search"
            placeholder="Search topology (name, ARN, type)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-transparent px-2 text-sm text-foreground outline-hidden placeholder:text-muted-foreground"
          />
          <kbd className="rounded border border-border bg-surface-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            ESC
          </kbd>
        </div>

        <div className="mt-2 max-h-72 overflow-y-auto">
          {loading && (
            <p className="p-3 text-center text-xs text-muted-foreground">Searching topology…</p>
          )}

          {!loading && results.length === 0 && query.trim() && (
            <p className="p-3 text-center text-xs text-muted-foreground">No resources found.</p>
          )}

          {!loading && results.length === 0 && !query.trim() && (
            <p className="p-3 text-center text-xs text-muted-foreground">
              Type to search resources across all connected accounts.
            </p>
          )}

          {results.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                onSelectNode(item.id);
                onClose();
              }}
              className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs transition-colors hover:bg-surface-muted"
            >
              <div className="flex items-center gap-2 truncate">
                <Badge tone="neutral">{item.type.split("::").pop()}</Badge>
                <span className="font-medium text-foreground truncate">{item.name || item.id}</span>
              </div>
              <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                {item.region}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
