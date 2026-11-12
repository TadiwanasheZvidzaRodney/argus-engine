"use client";

import { Badge, Button, Card } from "@argus/ui";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import {
  type ActionDetail,
  type CatalogItem,
  type ParsedIntent,
  riskTone,
} from "@/lib/action-types";

const PARAMETER_DEFAULTS: Record<string, Record<string, unknown>> = {
  "iam.grant_s3_access": { actions: ["s3:GetObject"], prefix: "app-data/*" },
  "network.allow_security_group_ingress": {
    port: 5432,
    protocol: "tcp",
    cidr: "10.0.0.0/16",
  },
  "s3.harden_bucket": {},
  "iam.attach_least_privilege_policy": { actions: ["s3:GetObject"] },
  "tagging.apply": { tags: { owner: "platform", "cost-center": "engineering" } },
  "ec2.stop_start_instance": {},
  "observability.create_alarm": {
    metric_name: "CPUUtilization",
    threshold: 80,
    comparison: "GreaterThanThreshold",
  },
  "optimization.resize_instance": { instance_type: "t3.small" },
};

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function splitList(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ActionComposer({ catalog }: { catalog: CatalogItem[] }) {
  const router = useRouter();
  const [actionType, setActionType] = useState(catalog[0]?.action_type ?? "");
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [resources, setResources] = useState("");
  const [parameters, setParameters] = useState(
    pretty(PARAMETER_DEFAULTS[catalog[0]?.action_type ?? ""] ?? {}),
  );
  const [environment, setEnvironment] = useState<"dev" | "staging" | "prod">("staging");
  const [maintenanceWindow, setMaintenanceWindow] = useState(false);
  const [breakGlass, setBreakGlass] = useState(false);
  const [incidentId, setIncidentId] = useState("");
  const [justification, setJustification] = useState("");
  const [naturalLanguage, setNaturalLanguage] = useState("");
  const [parsed, setParsed] = useState<ParsedIntent | null>(null);
  const [error, setError] = useState<{ message: string; details: string[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [parsing, setParsing] = useState(false);

  const definition = useMemo(
    () => catalog.find((item) => item.action_type === actionType) ?? null,
    [catalog, actionType],
  );

  useEffect(() => {
    setParameters(pretty(PARAMETER_DEFAULTS[actionType] ?? {}));
  }, [actionType]);

  function describeError(err: unknown): { message: string; details: string[] } {
    if (err instanceof ApiError) {
      return {
        message: err.message,
        details: (err.problem.errors ?? []).map((field) => `${field.pointer}: ${field.detail}`),
      };
    }
    return { message: err instanceof Error ? err.message : "Request failed.", details: [] };
  }

  async function handleParse(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setParsing(true);
    try {
      const result = await apiFetch<ParsedIntent>("/api/v1/actions/parse-intent", {
        method: "POST",
        body: { text: naturalLanguage },
      });
      setParsed(result);
      if (result.action_type) {
        setActionType(result.action_type);
        setSource(String(result.targets.source ?? ""));
        setTarget(String(result.targets.target ?? ""));
        const list = result.targets.resources;
        setResources(Array.isArray(list) ? list.map(String).join(", ") : "");
        setParameters(pretty(result.parameters));
        const env = result.constraints.environment;
        if (env === "dev" || env === "staging" || env === "prod") setEnvironment(env);
        setMaintenanceWindow(Boolean(result.constraints.maintenance_window));
      }
    } catch (err) {
      setError(describeError(err));
    } finally {
      setParsing(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      let parsedParameters: Record<string, unknown>;
      try {
        const value: unknown = JSON.parse(parameters || "{}");
        if (typeof value !== "object" || value === null || Array.isArray(value)) {
          throw new Error("Parameters must be a JSON object.");
        }
        parsedParameters = value as Record<string, unknown>;
      } catch (err) {
        throw new Error(
          `Parameters are not valid JSON: ${err instanceof Error ? err.message : "unknown"}`,
        );
      }

      const created = await apiFetch<ActionDetail>("/api/v1/actions", {
        method: "POST",
        idempotencyKey: `action-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
        body: {
          type: actionType,
          targets: {
            source: source || null,
            target: target || null,
            resources: splitList(resources),
          },
          parameters: parsedParameters,
          constraints: {
            environment,
            maintenance_window: maintenanceWindow,
            break_glass: breakGlass,
            incident_id: incidentId || null,
          },
          justification,
        },
      });
      router.push(`/actions/${created.id}`);
      router.refresh();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div className="flex flex-col gap-6">
        <Card
          title="Describe the change"
          description="The language model only drafts a typed intent. Plans are compiled deterministically from the catalog."
        >
          <form onSubmit={handleParse} className="flex flex-col gap-3">
            <textarea
              aria-label="Natural-language action request"
              rows={3}
              value={naturalLanguage}
              onChange={(event) => setNaturalLanguage(event.target.value)}
              placeholder="e.g. Grant arn:aws:iam::123456789012:role/app-role read access to arn:aws:s3:::my-bucket"
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
            />
            <div className="flex items-center gap-2">
              <Button type="submit" variant="secondary" size="sm" loading={parsing}>
                Parse intent
              </Button>
              {parsed && (
                <span className="text-xs text-muted-foreground">
                  {parsed.rejected
                    ? `Rejected: ${parsed.rejection_reason}`
                    : `${Math.round(parsed.confidence * 100)}% confidence — ${parsed.rationale}`}
                </span>
              )}
            </div>
          </form>
        </Card>

        <Card title="Typed intent">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Action type
              <select
                value={actionType}
                onChange={(event) => setActionType(event.target.value)}
                className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground"
              >
                {catalog.map((item) => (
                  <option key={item.action_type} value={item.action_type}>
                    {item.name} ({item.action_type})
                  </option>
                ))}
              </select>
            </label>

            {definition && (
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={riskTone(definition.risk_level)}>{definition.risk_level} risk</Badge>
                <Badge tone="neutral">{definition.category}</Badge>
                <Badge tone="info">max blast radius {definition.max_blast_radius}</Badge>
                <span className="text-xs text-muted-foreground">{definition.description}</span>
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Source resource
                <input
                  type="text"
                  value={source}
                  onChange={(event) => setSource(event.target.value)}
                  placeholder="arn:aws:iam::…:role/app-role"
                  className="h-10 rounded-md border border-border bg-background px-3 font-mono text-xs text-foreground"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Target resource
                <input
                  type="text"
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                  placeholder="arn:aws:s3:::my-bucket"
                  className="h-10 rounded-md border border-border bg-background px-3 font-mono text-xs text-foreground"
                />
              </label>
            </div>

            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Additional resources (comma or newline separated)
              <textarea
                rows={2}
                value={resources}
                onChange={(event) => setResources(event.target.value)}
                placeholder="arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123"
                className="rounded-md border border-border bg-background px-3 py-2 font-mono text-xs text-foreground"
              />
            </label>

            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Parameters (JSON)
              <textarea
                rows={7}
                value={parameters}
                onChange={(event) => setParameters(event.target.value)}
                spellCheck={false}
                className="rounded-md border border-border bg-background px-3 py-2 font-mono text-xs text-foreground"
              />
            </label>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Environment
                <select
                  value={environment}
                  onChange={(event) =>
                    setEnvironment(event.target.value as "dev" | "staging" | "prod")
                  }
                  className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground"
                >
                  <option value="dev">dev</option>
                  <option value="staging">staging</option>
                  <option value="prod">prod</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Incident ID (break-glass)
                <input
                  type="text"
                  value={incidentId}
                  onChange={(event) => setIncidentId(event.target.value)}
                  placeholder="INC-1234"
                  className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground"
                />
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={maintenanceWindow}
                  onChange={(event) => setMaintenanceWindow(event.target.checked)}
                />
                Declared maintenance window
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={breakGlass}
                  onChange={(event) => setBreakGlass(event.target.checked)}
                />
                Break-glass
              </label>
            </div>

            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Justification (min 10 characters)
              <textarea
                rows={3}
                required
                minLength={10}
                value={justification}
                onChange={(event) => setJustification(event.target.value)}
                placeholder="Explain why this change is required and what happens if it fails."
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
            </label>

            {error && (
              <div role="alert" className="rounded-md border border-danger/30 bg-danger/10 p-3">
                <p className="text-xs font-medium text-danger">{error.message}</p>
                {error.details.length > 0 && (
                  <ul className="mt-1 list-inside list-disc text-[11px] text-danger">
                    {error.details.map((detail) => (
                      <li key={detail}>{detail}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <Button type="submit" loading={loading} disabled={!actionType}>
              Compile plan and request approval
            </Button>
          </form>
        </Card>
      </div>

      <div className="flex flex-col gap-4">
        <Card title="Guardrail checklist">
          <ul className="flex flex-col gap-2 text-xs text-muted-foreground">
            <li>• Protected and deny-listed resources are refused before planning.</li>
            <li>• Blast radius and per-tenant quotas are enforced server-side.</li>
            <li>• Production and irreversible changes require break-glass.</li>
            <li>• Wildcard IAM actions escalate to critical risk.</li>
          </ul>
        </Card>
        {definition && (
          <Card title="Required permissions">
            <ul className="flex flex-col gap-1 font-mono text-[11px] text-muted-foreground">
              {definition.required_permissions.map((permission) => (
                <li key={permission}>{permission}</li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}
