export type Role = "viewer" | "support" | "manager";
export type Me = { id: number; name: string; role: Role; permissions: string[] };

export type Order = {
  id: string;
  customer: string;
  customer_email: string;
  status: string;
  total: string;
  refunded: string;
  refundable: string;
  created_at: string;
};

export type Ticket = {
  id: string;
  customer: string;
  order_id: string | null;
  subject: string;
  status: string;
  priority: string;
  created_at: string;
};

export type AuditRow = {
  id: number;
  user: string;
  action: string;
  args: Record<string, unknown>;
  outcome: string;
  detail: string;
  via_assistant: boolean;
  created_at: string;
};

export type Stats = { orders: Record<string, number>; tickets: Record<string, number> };
