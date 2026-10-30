"use client";

import { useCallback, useState } from "react";
import { useMe } from "@/components/auth";
import { ChatPanel } from "@/components/chat-panel";
import { StatusChip } from "@/components/status-chip";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Order, Stats, Ticket } from "@/lib/types";
import { usePolling } from "@/lib/use-polling";

const POLL_MS = 15_000;
const loadStats = () => api<Stats>("/api/stats");
const loadTickets = () => api<Ticket[]>("/api/tickets?limit=10");

export default function Dashboard() {
  const me = useMe();
  // Bumped after the assistant changes something, so the tables update at once.
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_26rem]">
      <div className="min-w-0 space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <StatsRow refreshKey={refreshKey} />
        <OrdersTable refreshKey={refreshKey} />
        <TicketsTable refreshKey={refreshKey} />
      </div>
      <div className="lg:sticky lg:top-4 lg:h-[calc(100vh-7rem)]">
        <ChatPanel userId={me.id} onActionDone={refresh} />
      </div>
    </div>
  );
}

function StatsRow({ refreshKey }: { refreshKey: number }) {
  const { data } = usePolling(loadStats, POLL_MS, refreshKey);
  const cards = [
    ["Pending orders", data?.orders.pending],
    ["Shipped", data?.orders.shipped],
    ["Open tickets", data?.tickets.open],
    ["Refunded orders", data?.orders.refunded],
  ] as const;
  return (
    <section aria-label="Live numbers" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map(([label, value]) => (
        <div key={label} className="panel p-3">
          <p className="text-xs muted">{label}</p>
          <p className="text-2xl font-semibold">{data ? (value ?? 0) : "–"}</p>
        </div>
      ))}
    </section>
  );
}

function OrdersTable({ refreshKey }: { refreshKey: number }) {
  const [status, setStatus] = useState("");
  const load = useCallback(() => api<Order[]>(`/api/orders?limit=12${status ? `&status=${status}` : ""}`), [status]);
  const { data, error } = usePolling(load, POLL_MS, refreshKey);
  return (
    <section className="panel overflow-hidden" aria-labelledby="orders-title">
      <div className="flex items-center justify-between p-3">
        <h2 id="orders-title" className="font-semibold">
          Recent orders
        </h2>
        <label className="flex items-center gap-2 text-sm">
          <span className="muted">Status</span>
          <select className="input w-auto py-1" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            {["pending", "shipped", "delivered", "cancelled", "refunded"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      <TableBody
        error={error}
        rows={data}
        empty="No orders with this status."
        head={["Order", "Customer", "Status", "Total", "Refunded", "Placed"]}
        render={(o: Order) => [o.id, o.customer, <StatusChip key="s" value={o.status} />, o.total, o.refunded, formatDate(o.created_at)]}
      />
    </section>
  );
}

function TicketsTable({ refreshKey }: { refreshKey: number }) {
  const { data, error } = usePolling(loadTickets, POLL_MS, refreshKey);
  return (
    <section className="panel overflow-hidden" aria-labelledby="tickets-title">
      <h2 id="tickets-title" className="p-3 font-semibold">
        Tickets
      </h2>
      <TableBody
        error={error}
        rows={data}
        empty="No tickets yet."
        head={["Ticket", "Subject", "Customer", "Status", "Priority", "Opened"]}
        render={(t: Ticket) => [
          t.id,
          t.subject,
          t.customer,
          <StatusChip key="s" value={t.status} />,
          <StatusChip key="p" value={t.priority} />,
          formatDate(t.created_at),
        ]}
      />
    </section>
  );
}

function TableBody<T extends { id: string | number }>({
  rows,
  error,
  empty,
  head,
  render,
}: {
  rows: T[] | null;
  error: string | null;
  empty: string;
  head: string[];
  render: (row: T) => React.ReactNode[];
}) {
  if (error) return <p className="p-3 text-sm" style={{ color: "var(--bad)" }}>{error}</p>;
  if (!rows) return <p className="p-3 text-sm muted" role="status">Loading...</p>;
  if (!rows.length) return <p className="p-3 text-sm muted">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              {render(row).map((cell, i) => (
                <td key={i} className="whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
