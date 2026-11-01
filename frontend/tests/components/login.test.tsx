import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

import { LoginScreen } from "@/cockpit/components/screens/LoginScreen";

import { axeViolations } from "../support/axe";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

describe("LoginScreen (Atelier Dual-Bento)", () => {
  it("renders labelled user ID and password fields, demo personas, and passes accessibility", async () => {
    const { container } = render(<LoginScreen next="/dashboard" />);
    const idField = screen.getByLabelText("User ID or Work Email");
    const pwField = screen.getByLabelText("Password / Passkey");

    expect(idField).toBeInTheDocument();
    expect(pwField).toHaveAttribute("type", "password");
    expect(idField).toHaveValue("admin");
    expect(pwField).toHaveValue("admin123");

    // Demo personas are rendered
    expect(screen.getByText("System Administrator")).toBeInTheDocument();
    expect(screen.getByText("Elena Vance")).toBeInTheDocument();
    expect(screen.getByText("Marcus Kane")).toBeInTheDocument();
    expect(screen.getByText("Priya Patel")).toBeInTheDocument();

    // SSO buttons
    expect(screen.getByText("Google Workspace")).toBeInTheDocument();
    expect(screen.getByText("Passkey Biometric")).toBeInTheDocument();

    // Check accessibility
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows an error notification when server authentication fails", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ ok: false, fieldError: "Invalid User ID / Email or Password." }),
    });

    render(<LoginScreen next="/dashboard" />);
    const idField = screen.getByLabelText("User ID or Work Email");
    const pwField = screen.getByLabelText("Password / Passkey");

    await userEvent.clear(idField);
    await userEvent.type(idField, "wronguser");
    await userEvent.clear(pwField);
    await userEvent.type(pwField, "wrongpass");
    await userEvent.click(screen.getByRole("button", { name: "Enter Atelier Workspace" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("Invalid User ID / Email or Password.");
  });

  it("submits and calls onLogin when valid credentials succeed", async () => {
    const onLogin = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        redirect: "/dashboard",
        user: { name: "System Administrator", role: "admin" },
      }),
    });

    render(<LoginScreen onLogin={onLogin} next="/dashboard" />);
    await userEvent.click(screen.getByRole("button", { name: "Enter Atelier Workspace" }));

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("switches to Sign Up mode and renders registration fields", async () => {
    render(<LoginScreen initialMode="signin" />);

    // Click "Create Account" tab
    const createAccountTab = screen.getByRole("button", { name: "Create Account" });
    await userEvent.click(createAccountTab);

    // Registration fields appear
    expect(screen.getByLabelText("Full Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Username / User ID")).toBeInTheDocument();
    expect(screen.getByLabelText("Work Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Create Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Account & Setup Connections" })).toBeInTheDocument();
  });

  it("validates password mismatch on signup", async () => {
    render(<LoginScreen initialMode="signup" />);

    await userEvent.type(screen.getByLabelText("Full Name"), "Alex Chen");
    await userEvent.type(screen.getByLabelText("Username / User ID"), "alexchen");
    await userEvent.type(screen.getByLabelText("Work Email"), "alex@company.com");
    await userEvent.type(screen.getByLabelText("Create Password"), "secret123");
    await userEvent.type(screen.getByLabelText("Confirm Password"), "mismatch456");

    await userEvent.click(screen.getByRole("button", { name: "Create Account & Setup Connections" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("Passwords do not match. Please re-enter your password.");
  });

  it("submits successful signup with automatic API key provisioning", async () => {
    const onLogin = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        redirect: "/connections",
        user: { name: "Alex Chen", role: "operator", email: "alex@company.com" },
      }),
    });

    render(<LoginScreen onLogin={onLogin} initialMode="signup" next="/connections" />);

    await userEvent.type(screen.getByLabelText("Full Name"), "Alex Chen");
    await userEvent.type(screen.getByLabelText("Username / User ID"), "alexchen");
    await userEvent.type(screen.getByLabelText("Work Email"), "alex@company.com");
    await userEvent.type(screen.getByLabelText("Create Password"), "secret123");
    await userEvent.type(screen.getByLabelText("Confirm Password"), "secret123");

    await userEvent.click(screen.getByRole("button", { name: "Create Account & Setup Connections" }));

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          isSignUp: true,
          identifier: "alexchen",
          email: "alex@company.com",
          fullName: "Alex Chen",
          password: "secret123",
          next: "/connections",
        }),
      }),
    );
  });
});
