"use client";

import { useMe } from "@/components/auth";
import { StatusChip } from "@/components/status-chip";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AuditRow } from "@/lib/types";
import { usePolling } from "@/lib/use-polling";

const loadAudit = () => api<AuditRow[]>("/api/audit?limit=100");
const loadNothing = () => Promise.resolve([] as AuditRow[]);

export default function AuditPage() {
  const me = useMe();
  const allowed = me.permissions.includes("audit.read");
  const { data, error } = usePolling(allowed ? loadAudit : loadNothing, 10_000);
  if (!allowed) return <p>Only managers can see the audit log.</p>;
  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Audit log</h1>
        <p className="text-sm muted">Every change, every refused attempt, and every tool the assistant used.</p>
      </div>
      <div className="panel overflow-x-auto">
        {error ? <p className="p-3" style={{ color: "var(--bad)" }}>{error}</p> : null}
        {!data ? <p className="p-3 muted" role="status">Loading...</p> : null}
        {data && !data.length ? <p className="p-3 muted">Nothing has happened yet.</p> : null}
        {data?.length ? (
          <table>
            <thead>
              <tr>
                {["When", "Who", "Via", "Action", "Details", "Outcome"].map((h) => (
                  <th key={h} scope="col">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td className="whitespace-nowrap">{formatDateTime(r.created_at)}</td>
                  <td className="whitespace-nowrap">{r.user}</td>
                  <td>{r.via_assistant ? <span className="chip">assistant</span> : <span className="chip">API</span>}</td>
                  <td className="whitespace-nowrap font-mono text-xs">{r.action}</td>
                  <td className="text-xs">
                    {Object.entries(r.args).map(([k, v]) => `${k}: ${String(v)}`).join(", ")}
                    {r.detail ? <span className="block muted">{r.detail}</span> : null}
                  </td>
                  <td><StatusChip value={r.outcome} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </section>
  );
}
