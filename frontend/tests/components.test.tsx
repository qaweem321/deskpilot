import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmCard } from "@/components/chat-panel";
import { PasswordInput } from "@/components/password-input";

describe("ConfirmCard", () => {
  it("asks before acting and reports the choice", async () => {
    const onDecide = vi.fn();
    render(<ConfirmCard actions={[{ id: "1", action: "refund_order", summary: "Refund $20.00 on order ORD-1002" }]} onDecide={onDecide} disabled={false} />);
    expect(screen.getByRole("alertdialog", { name: "Are you sure?" })).toHaveTextContent("Refund $20.00 on order ORD-1002");
    await userEvent.click(screen.getByRole("button", { name: "No, cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, do it" }));
    expect(onDecide.mock.calls).toEqual([[false], [true]]);
  });
  it("disables both buttons while busy", () => {
    render(<ConfirmCard actions={[{ id: "1", action: "x", summary: "s" }]} onDecide={vi.fn()} disabled />);
    screen.getAllByRole("button").forEach((b) => expect(b).toBeDisabled());
  });
});

describe("PasswordInput", () => {
  it("shows and hides the password", async () => {
    render(<PasswordInput id="p" name="p" />);
    const input = document.getElementById("p") as HTMLInputElement;
    expect(input.type).toBe("password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(input.type).toBe("text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
  });
});
