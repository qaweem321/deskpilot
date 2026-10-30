const COLORS: Record<string, string> = {
  pending: "var(--warn)",
  shipped: "var(--accent)",
  delivered: "var(--ok)",
  cancelled: "var(--muted)",
  refunded: "var(--muted)",
  open: "var(--warn)",
  closed: "var(--muted)",
  urgent: "var(--bad)",
  high: "var(--warn)",
  done: "var(--ok)",
  denied: "var(--bad)",
  rejected: "var(--warn)",
};

export function StatusChip({ value }: { value: string }) {
  return (
    <span className="chip" style={{ color: COLORS[value] ?? "var(--text)" }}>
      {value}
    </span>
  );
}
