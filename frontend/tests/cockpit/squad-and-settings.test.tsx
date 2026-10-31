import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SettingsScreen } from "@/cockpit/components/screens/SettingsScreen";
import { SquadAndReportsScreen } from "@/cockpit/components/screens/SquadAndReportsScreen";
import { currentUser, teamMembers, initialTasks } from "@/cockpit/data/mockData";

describe("SettingsScreen (Profile Pictures & Custom LLM Keys)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("renders profile identity settings and shows current user info", () => {
    const handleUpdateUser = vi.fn();
    render(
      <SettingsScreen
        user={currentUser}
        onUpdateUser={handleUpdateUser}
        teamMembers={teamMembers}
        isLoggedIn={true}
        onSignOut={vi.fn()}
        onSwitchViewMode={vi.fn()}
      />
    );

    expect(screen.getByText("Profile & System Settings")).toBeInTheDocument();
    expect(screen.getByText("Client & User Profile Picture")).toBeInTheDocument();
    expect(screen.getByDisplayValue(currentUser.name)).toBeInTheDocument();
    expect(screen.getByDisplayValue(currentUser.role)).toBeInTheDocument();
  });

  it("allows setting custom image URL and resetting to monogram", () => {
    const handleUpdateUser = vi.fn();
    render(
      <SettingsScreen
        user={currentUser}
        onUpdateUser={handleUpdateUser}
        teamMembers={teamMembers}
        isLoggedIn={true}
        onSignOut={vi.fn()}
        onSwitchViewMode={vi.fn()}
      />
    );

    // Toggle custom image URL input
    const customUrlBtn = screen.getByText("Image URL");
    fireEvent.click(customUrlBtn);

    const input = screen.getByPlaceholderText("https://example.com/avatar.jpg");
    fireEvent.change(input, {
      target: { value: "https://example.com/custom-avatar.jpg" },
    });

    const applyBtn = screen.getByText("Apply");
    fireEvent.click(applyBtn);

    // Click Save
    fireEvent.click(screen.getByText("Save Profile & Avatar Changes"));
    expect(handleUpdateUser).toHaveBeenCalledWith(
      expect.objectContaining({
        avatar: "https://example.com/custom-avatar.jpg",
      })
    );

    // Test Monogram reset via "Remove"
    const removeBtn = screen.getByText("Remove");
    fireEvent.click(removeBtn);
    fireEvent.click(screen.getByText("Save Profile & Avatar Changes"));
    expect(handleUpdateUser).toHaveBeenCalledWith(
      expect.objectContaining({
        avatar: "",
      })
    );
  });

  it("configures custom LLM provider, API key, and model choice", () => {
    render(
      <SettingsScreen
        user={currentUser}
        onUpdateUser={vi.fn()}
        teamMembers={teamMembers}
        isLoggedIn={true}
        onSignOut={vi.fn()}
        onSwitchViewMode={vi.fn()}
      />
    );

    expect(screen.getByText("Custom LLM & AI Model Integration")).toBeInTheDocument();

    // Select Groq provider
    const groqBtn = screen.getByTitle("Groq");
    fireEvent.click(groqBtn);

    // Click a popular model preset
    const deepseekPill = screen.getByText("deepseek-r1-distill-llama-70b");
    fireEvent.click(deepseekPill);

    // Enter API key
    const keyInput = screen.getByPlaceholderText("gsk_...");
    fireEvent.change(keyInput, { target: { value: "gsk_live_test_1234567890abcdef" } });

    // Submit form
    const saveLLMBtn = screen.getByText("Save LLM Configuration");
    fireEvent.click(saveLLMBtn);

    const saved = JSON.parse(localStorage.getItem("cji_llm_config") || "{}");
    expect(saved.provider).toBe("groq");
    expect(saved.model).toBe("deepseek-r1-distill-llama-70b");
    expect(saved.apiKey).toBe("gsk_live_test_1234567890abcdef");
  });

  it("allows writing any custom model name and toggling key reveal", () => {
    render(
      <SettingsScreen
        user={currentUser}
        onUpdateUser={vi.fn()}
        teamMembers={teamMembers}
        isLoggedIn={true}
        onSignOut={vi.fn()}
        onSwitchViewMode={vi.fn()}
      />
    );

    // Select Anthropic
    const anthropicBtn = screen.getByTitle("Anthropic");
    fireEvent.click(anthropicBtn);

    // Type a custom model into the freeform input
    const modelInput = screen.getByPlaceholderText(/e\.g\. claude-3-7-sonnet-latest/);
    fireEvent.change(modelInput, { target: { value: "claude-3-7-sonnet-20250219" } });

    // Type an API key
    const keyInput = screen.getByPlaceholderText("sk-ant-api03-...");
    expect(keyInput).toHaveAttribute("type", "password");
    fireEvent.change(keyInput, { target: { value: "sk-ant-api03-my-custom-key" } });

    // Toggle Reveal Key
    const revealBtn = screen.getByText("Reveal");
    fireEvent.click(revealBtn);
    expect(keyInput).toHaveAttribute("type", "text");

    const hideBtn = screen.getByText("Hide");
    fireEvent.click(hideBtn);
    expect(keyInput).toHaveAttribute("type", "password");

    // Save
    fireEvent.click(screen.getByText("Save LLM Configuration"));
    const saved = JSON.parse(localStorage.getItem("cji_llm_config") || "{}");
    expect(saved.model).toBe("claude-3-7-sonnet-20250219");
    expect(saved.apiKey).toBe("sk-ant-api03-my-custom-key");
  });

  it("allows switching workspace database isolation mode", () => {
    render(
      <SettingsScreen
        user={currentUser}
        onUpdateUser={vi.fn()}
        teamMembers={teamMembers}
        isLoggedIn={true}
        onSignOut={vi.fn()}
        onSwitchViewMode={vi.fn()}
      />
    );

    expect(screen.getByText("Workspace Database & Multi-Tenant Isolation")).toBeInTheDocument();

    const sandboxBtn = screen.getByText("Demo Sandbox");
    fireEvent.click(sandboxBtn);
    expect(localStorage.getItem("cji_workspace_data_mode")).toBe("demo");

    const cleanBtn = screen.getByText("Clean Live Workspace");
    fireEvent.click(cleanBtn);
    expect(localStorage.getItem("cji_workspace_data_mode")).toBe("clean");
  });
});

describe("SquadAndReportsScreen (Unified Problem-Statement Hub)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders problem-statement diagnostic reports with dropoff % and rage clicks", () => {
    render(
      <SquadAndReportsScreen
        members={teamMembers}
        onAddMember={vi.fn()}
        onUpdateMemberAvatar={vi.fn()}
        onRemoveMember={vi.fn()}
        onAssignToMember={vi.fn()}
        tasks={initialTasks}
        onToggleTask={vi.fn()}
        onUpdateTaskStatus={vi.fn()}
        onNewTask={vi.fn()}
      />
    );

    expect(screen.getByText("Operations & Journey Diagnostic Reports")).toBeInTheDocument();
    expect(screen.getByText("Checkout Funnel Friction & Rage-Click Audit")).toBeInTheDocument();
    expect(screen.getByText("41.8%")).toBeInTheDocument();
  });

  it("filters reports by journey funnel", () => {
    render(
      <SquadAndReportsScreen
        members={teamMembers}
        onAddMember={vi.fn()}
        onUpdateMemberAvatar={vi.fn()}
        onRemoveMember={vi.fn()}
        onAssignToMember={vi.fn()}
        tasks={initialTasks}
        onToggleTask={vi.fn()}
        onUpdateTaskStatus={vi.fn()}
        onNewTask={vi.fn()}
      />
    );

    // Switch journey filter to user_onboarding
    const onboardingFilterBtn = screen.getByRole("button", { name: "user_onboarding" });
    fireEvent.click(onboardingFilterBtn);

    expect(
      screen.getByText("User Onboarding & Identity Verification Drop-Off Analysis")
    ).toBeInTheDocument();
    expect(screen.queryByText("Checkout Funnel Friction & Rage-Click Audit")).not.toBeInTheDocument();
  });

  it("opens modal and generates a new diagnostic audit report", () => {
    render(
      <SquadAndReportsScreen
        members={teamMembers}
        onAddMember={vi.fn()}
        onUpdateMemberAvatar={vi.fn()}
        onRemoveMember={vi.fn()}
        onAssignToMember={vi.fn()}
        tasks={initialTasks}
        onToggleTask={vi.fn()}
        onUpdateTaskStatus={vi.fn()}
        onNewTask={vi.fn()}
      />
    );

    const generateBtn = screen.getByText("Generate Journey Audit");
    fireEvent.click(generateBtn);

    expect(screen.getByText("Generate Live Diagnostic Audit")).toBeInTheDocument();

    const titleInput = screen.getByPlaceholderText("e.g. Checkout Funnel Sprint 4 Friction Audit");
    fireEvent.change(titleInput, { target: { value: "Pricing Page Dropoff Audit" } });

    const submitBtn = screen.getByText("Compile & Save Audit Report");
    fireEvent.click(submitBtn);

    expect(screen.getByText("Pricing Page Dropoff Audit")).toBeInTheDocument();
  });

  it("views detailed report findings with executive summary and recommended fixes", () => {
    render(
      <SquadAndReportsScreen
        members={teamMembers}
        onAddMember={vi.fn()}
        onUpdateMemberAvatar={vi.fn()}
        onRemoveMember={vi.fn()}
        onAssignToMember={vi.fn()}
        tasks={initialTasks}
        onToggleTask={vi.fn()}
        onUpdateTaskStatus={vi.fn()}
        onNewTask={vi.fn()}
      />
    );

    const viewFindingsButtons = screen.getAllByText("View Findings");
    fireEvent.click(viewFindingsButtons[0]!);

    expect(screen.getByText("Executive Diagnostic Summary")).toBeInTheDocument();
    expect(screen.getByText("Recommended Remediation Roadmap")).toBeInTheDocument();
    expect(screen.getByText("Download Standalone HTML Report")).toBeInTheDocument();
  });

  it("switches to Journey Squad Roster sub-tab, adds a teammate, and edits avatar", () => {
    const handleAddMember = vi.fn();
    const handleUpdateMemberAvatar = vi.fn();
    const handleRemoveMember = vi.fn();

    render(
      <SquadAndReportsScreen
        members={teamMembers}
        onAddMember={handleAddMember}
        onUpdateMemberAvatar={handleUpdateMemberAvatar}
        onRemoveMember={handleRemoveMember}
        onAssignToMember={vi.fn()}
        tasks={initialTasks}
        onToggleTask={vi.fn()}
        onUpdateTaskStatus={vi.fn()}
        onNewTask={vi.fn()}
      />
    );

    // Switch sub-tab to Squad Roster
    const squadTabBtn = screen.getByText(/Journey Squad Roster/);
    fireEvent.click(squadTabBtn);

    expect(screen.getByText("Add Teammate")).toBeInTheDocument();
    expect(screen.getByText("Elena Vance")).toBeInTheDocument();

    // Open Add Teammate modal
    const addTeammateBtn = screen.getByText("Add Teammate");
    fireEvent.click(addTeammateBtn);

    expect(screen.getByText("Add Journey Intelligence Operator")).toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText("e.g. Maya Sterling");
    fireEvent.change(nameInput, { target: { value: "Aarav Sharma" } });

    const submitAddBtn = screen.getByText("Add Operator to Squad");
    fireEvent.click(submitAddBtn);

    expect(handleAddMember).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Aarav Sharma",
      })
    );

    // Click edit avatar button on a teammate
    const editAvatarButtons = screen.getAllByTitle("Change Member Profile Photo");
    fireEvent.click(editAvatarButtons[0]!);

    expect(screen.getByText("Select Member Profile Photo")).toBeInTheDocument();
    const presetButtons = screen.getAllByRole("button").filter(b => b.querySelector("img"));
    if (presetButtons[0]) {
      fireEvent.click(presetButtons[0]);
      expect(handleUpdateMemberAvatar).toHaveBeenCalled();
    }
  });

  it("switches to Sprint Execution Kanban sub-tab and displays deliverables", () => {
    const handleToggleTask = vi.fn();
    render(
      <SquadAndReportsScreen
        members={teamMembers}
        onAddMember={vi.fn()}
        onUpdateMemberAvatar={vi.fn()}
        onRemoveMember={vi.fn()}
        onAssignToMember={vi.fn()}
        tasks={initialTasks}
        onToggleTask={handleToggleTask}
        onUpdateTaskStatus={vi.fn()}
        onNewTask={vi.fn()}
      />
    );

    // Switch to Kanban sub-tab
    const kanbanTabBtn = screen.getByText("Sprint Deliverables");
    fireEvent.click(kanbanTabBtn);

    expect(screen.getByText("Sprint Backlog")).toBeInTheDocument();
    expect(screen.getByText("In Flight (Active)")).toBeInTheDocument();
    expect(screen.getByText("Shipped & Verified")).toBeInTheDocument();
  });
});
