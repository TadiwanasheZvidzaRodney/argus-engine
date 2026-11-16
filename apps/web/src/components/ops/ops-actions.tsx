"use client";

import { Button } from "@argus/ui";
import { useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/idempotency";

export function TvModeToggle() {
  const [kiosk, setKiosk] = useState(false);

  // Sync data-kiosk attribute whenever kiosk state changes
  useEffect(() => {
    if (kiosk) {
      document.documentElement.setAttribute("data-kiosk", "true");
      document.body.setAttribute("data-kiosk", "true");
    } else {
      document.documentElement.removeAttribute("data-kiosk");
      document.body.removeAttribute("data-kiosk");
    }
  }, [kiosk]);

  // Clean up attributes on unmount
  useEffect(() => {
    return () => {
      document.documentElement.removeAttribute("data-kiosk");
      document.body.removeAttribute("data-kiosk");
      if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    };
  }, []);

  // Listen to keyboard 'F' and hardware fullscreenchange events
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (
        (e.key === "f" || e.key === "F") &&
        !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)
      ) {
        setKiosk((prev) => !prev);
      }
    };

    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        setKiosk(false);
      }
    };

    window.addEventListener("keydown", handleKey);
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      window.removeEventListener("keydown", handleKey);
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, []);

  const handleToggle = () => {
    setKiosk((prev) => {
      const next = !prev;
      if (next) {
        if (document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen().catch(() => {});
        }
      } else {
        if (document.fullscreenElement && document.exitFullscreen) {
          document.exitFullscreen().catch(() => {});
        }
      }
      return next;
    });
  };

  return (
    <Button
      size="sm"
      variant={kiosk ? "primary" : "secondary"}
      onClick={handleToggle}
      title="Toggle TV / NOC Kiosk layout (Press F)"
    >
      {kiosk ? "Exit Kiosk (F)" : "📺 TV Kiosk Mode (F)"}
    </Button>
  );
}

export function AutoRefreshBadge({ intervalSeconds = 15 }: { intervalSeconds?: number }) {
  const router = useRouter();
  const [countdown, setCountdown] = useState(intervalSeconds);

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          setTimeout(() => {
            router.refresh();
          }, 0);
          return intervalSeconds;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [router, intervalSeconds]);

  return (
    <span className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1 text-[11px] font-mono text-muted-foreground">
      <span className="size-2 rounded-full bg-success animate-ping" />
      <span>{countdown}s refresh</span>
    </span>
  );
}

export function TestEmailAlertButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSend() {
    setBusy(true);
    setSent(false);
    try {
      await apiFetch("/api/v1/ops/alerts/test-email", {
        method: "POST",
        idempotencyKey: newIdempotencyKey("test-mail"),
        body: {
          to_email: "devops@zimworx.com",
          subject: "[TEST ALERT] Argus Operations Wallboard Verification",
          message:
            "Test notification dispatched to verify devops@zimworx.com group delivery from Argus Engine.",
        },
      });
      setSent(true);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button
      size="sm"
      variant="ghost"
      loading={busy}
      onClick={handleSend}
      title="Send a test alert email to devops@zimworx.com"
    >
      {sent ? "Sent to devops@zimworx.com ✓" : "Test Alert Email"}
    </Button>
  );
}

export function AlertActionControls({
  alertId,
  status,
  actionId,
}: {
  alertId: string;
  status: string;
  actionId?: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function handleAck() {
    setBusy(true);
    try {
      await apiFetch(`/api/v1/ops/alerts/${alertId}/ack`, {
        method: "POST",
        idempotencyKey: newIdempotencyKey("ack-alert"),
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve() {
    setBusy(true);
    try {
      await apiFetch(`/api/v1/ops/alerts/${alertId}/resolve`, {
        method: "POST",
        idempotencyKey: newIdempotencyKey("res-alert"),
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (status === "RESOLVED") {
    return <span className="text-[11px] text-muted-foreground">Resolved</span>;
  }

  return (
    <div className="flex items-center gap-1.5">
      {status === "FIRING" && (
        <Button size="sm" variant="secondary" loading={busy} onClick={handleAck}>
          Acknowledge
        </Button>
      )}
      <Button size="sm" variant="ghost" loading={busy} onClick={handleResolve}>
        Resolve
      </Button>
      {actionId && (
        <a
          href={`/actions/${actionId}`}
          className="text-xs font-semibold text-accent underline underline-offset-4"
        >
          View Action ↗
        </a>
      )}
    </div>
  );
}
