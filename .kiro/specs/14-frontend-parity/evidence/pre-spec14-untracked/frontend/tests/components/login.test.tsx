import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LoginForm } from "@/app/login/LoginForm";

import { axeViolations } from "../support/axe";

const signIn = vi.fn();
vi.mock("@/app/actions", () => ({ signIn: (...args: unknown[]) => signIn(...args) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

describe("LoginForm", () => {
  it("is a labelled password field that never pre-fills the token", async () => {
    const { container } = render(<LoginForm next="/runs" />);
    const field = screen.getByLabelText("API token");
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAttribute("autocomplete", "off");
    expect(field).toHaveValue("");
    expect(container.querySelector('input[name="next"]')).toHaveValue("/runs");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows the field error from the server action, linked to the field", async () => {
    signIn.mockResolvedValue({ fieldError: "This token is not valid, has expired or was revoked.", problem: null });
    render(<LoginForm next="/" />);
    await userEvent.type(screen.getByLabelText("API token"), "cji_api_wrong-token-value-000000");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const error = await screen.findByText("This token is not valid, has expired or was revoked.");
    const field = screen.getByLabelText("API token");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field.getAttribute("aria-describedby")).toContain(error.id);
  });

  it("shows API problems as a problem panel", async () => {
    signIn.mockResolvedValue({
      fieldError: null,
      problem: { status: 503, code: "backend_unreachable", title: "Backend unreachable", detail: "Check cji-api.", requestId: "r1", retryAfterS: null },
    });
    render(<LoginForm next="/" />);
    await userEvent.type(screen.getByLabelText("API token"), "cji_api_some-token-value-00000000");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign-in: Backend unreachable");
  });
});
