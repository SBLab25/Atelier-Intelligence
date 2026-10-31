"""Spec 08 T2: gateway settings (OD-54/56/58/59/62/66). Exact single-match replacements."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[5]
APP = ROOT / "cji_agent"


def edit(rel, pairs):
    path = APP / rel
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        n = text.count(old)
        assert n == 1, f"{rel}: expected 1 match, found {n}: {old[:70]!r}"
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("edited", rel)


edit("settings/model.py", [
    ("class StorageSettings(_Frozen):\n    data_dir: Path\n    reports_dir: Path\n",
     "class StorageSettings(_Frozen):\n    data_dir: Path\n    reports_dir: Path\n"
     "    audit_dir: Path | None = None    # gateway audit JSONL files; None = log only (Spec 08)\n"),
    ('''class LLMSettings(_Frozen):
    model: str = "claude-sonnet-4-6"
    temperature: float = 0.0
    max_tokens: int = 2048
    groq_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    timeout_s: float = 30.0
    retry: RetryPolicy = RetryPolicy()
''', '''# LLM providers the gateway supports (Spec 08, OD-54). One per process; never switched silently.
LLM_PROVIDERS: tuple[str, ...] = ("groq", "anthropic", "none")
DEFAULT_LLM_MODELS: dict[str, str] = {
    "groq": "openai/gpt-oss-120b",        # what insight/report sent with default settings before Spec 08
    "anthropic": "claude-sonnet-4-6",     # the settings default before Spec 08
    "none": "none",
}


def llm_model_mismatch(provider: str, model: str) -> str | None:
    """A message when LLM_MODEL obviously belongs to another provider, else None."""
    m = model.strip().lower()
    if provider == "groq" and (m.startswith("claude") or m.startswith("anthropic/")):
        return f"LLM_MODEL={model!r} is an Anthropic model but CJI_LLM_PROVIDER=groq."
    if provider == "anthropic" and not m.removeprefix("anthropic/").startswith("claude"):
        return f"LLM_MODEL={model!r} is not an Anthropic model but CJI_LLM_PROVIDER=anthropic."
    return None


class RunBudgetSettings(_Frozen):
    """Per-run LLM limits (Spec 08, OD-59). Cost is enforced only when prices are configured."""

    max_calls: int = 20
    max_tokens: int = 50_000
    max_cost_usd: float | None = None


class LLMSettings(_Frozen):
    provider: str = "groq"
    model: str = DEFAULT_LLM_MODELS["groq"]
    temperature: float = 0.0
    max_tokens: int = 2048
    groq_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None   # read but unused (F-28)
    timeout_s: float = 30.0
    deadline_s: float = 90.0
    retry: RetryPolicy = RetryPolicy()
    rate_per_min: int = 30
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    run_budget: RunBudgetSettings = RunBudgetSettings()
'''),
    ("    read_timeout_s: float = 300.0\n",
     "    read_timeout_s: float = 300.0\n    call_timeout_s: float = 150.0   # one tool call (Spec 08, OD-66)\n"),
    ('            "storage": {"data_dir": str(self.storage.data_dir), "reports_dir": str(self.storage.reports_dir)},\n',
     '            "storage": {\n'
     '                "data_dir": str(self.storage.data_dir),\n'
     '                "reports_dir": str(self.storage.reports_dir),\n'
     '                "audit_dir": str(self.storage.audit_dir) if self.storage.audit_dir else "off",\n'
     '            },\n'),
    ('                "model": self.llm.model,\n',
     '                "provider": self.llm.provider,\n'
     '                "model": self.llm.model,\n'
     '                "deadline_s": self.llm.deadline_s,\n'
     '                "rate_per_min": self.llm.rate_per_min,\n'
     '                "price_input_per_mtok": self.llm.price_input_per_mtok,\n'
     '                "price_output_per_mtok": self.llm.price_output_per_mtok,\n'
     '                "run_budget": self.llm.run_budget.model_dump(),\n'),
])

edit("settings/load.py", [
    ("    RetryPolicy,\n    Settings,\n", "    RetryPolicy,\n    RunBudgetSettings,\n    Settings,\n"),
    ('    "CJI_LLM_TIMEOUT_S", "CJI_LLM_RETRY_ATTEMPTS", "CJI_LLM_RETRY_MIN_S", "CJI_LLM_RETRY_MAX_S",\n',
     '    "CJI_LLM_TIMEOUT_S", "CJI_LLM_RETRY_ATTEMPTS", "CJI_LLM_RETRY_MIN_S", "CJI_LLM_RETRY_MAX_S",\n'
     '    "CJI_LLM_PROVIDER", "CJI_LLM_DEADLINE_S", "CJI_LLM_RATE_PER_MIN", "CJI_LLM_RUN_MAX_CALLS",\n'
     '    "CJI_LLM_RUN_MAX_TOKENS", "CJI_LLM_RUN_MAX_COST_USD", "CJI_LLM_PRICE_INPUT_PER_MTOK",\n'
     '    "CJI_LLM_PRICE_OUTPUT_PER_MTOK", "CJI_MCP_CALL_TIMEOUT_S", "CJI_AUDIT_DIR",\n'),
    ('        reports_dir=_path(r.raw("CJI_REPORTS_DIR"), APP_ROOT / "reports"),\n    )\n',
     '        reports_dir=_path(r.raw("CJI_REPORTS_DIR"), APP_ROOT / "reports"),\n    )\n'
     '    # Gateway audit files (Spec 08, OD-62): <data_dir>/audit unless "off"; log only in tests.\n'
     '    raw_audit = r.raw("CJI_AUDIT_DIR")\n'
     '    if raw_audit is not None and raw_audit.strip().lower() == "off":\n'
     '        audit_dir = None\n'
     '    elif raw_audit is not None:\n'
     '        audit_dir = _path(raw_audit, storage.data_dir / "audit")\n'
     '    else:\n'
     '        audit_dir = None if env == "test" else storage.data_dir / "audit"\n'
     '    storage = storage.model_copy(update={"audit_dir": audit_dir})\n'),
    ('    llm = LLMSettings(\n        model=r.text("LLM_MODEL", "claude-sonnet-4-6"),\n',
     '    # One provider per process, never switched silently (Spec 08, OD-54).\n'
     '    provider = r.choice("CJI_LLM_PROVIDER", LLM_PROVIDERS, "groq")\n'
     '    model = r.text("LLM_MODEL", DEFAULT_LLM_MODELS[provider])\n'
     '    mismatch = llm_model_mismatch(provider, model)\n'
     '    if mismatch:\n'
     '        r.problems.append(mismatch + " Set CJI_LLM_PROVIDER to the model\'s provider or choose a model it serves.")\n'
     '    price_in = _optional_number(r, "CJI_LLM_PRICE_INPUT_PER_MTOK")\n'
     '    price_out = _optional_number(r, "CJI_LLM_PRICE_OUTPUT_PER_MTOK")\n'
     '    max_cost = _optional_number(r, "CJI_LLM_RUN_MAX_COST_USD")\n'
     '    if max_cost is not None and (price_in is None or price_out is None):\n'
     '        r.problems.append(\n'
     '            "CJI_LLM_RUN_MAX_COST_USD needs CJI_LLM_PRICE_INPUT_PER_MTOK and CJI_LLM_PRICE_OUTPUT_PER_MTOK "\n'
     '            "(USD per million tokens); CJI has no built-in prices."\n'
     '        )\n'
     '    llm = LLMSettings(\n'
     '        provider=provider,\n'
     '        model=model,\n'),
    ('        retry=retry,\n    )\n    mcp = MCPSettings(\n',
     '        retry=retry,\n'
     '        deadline_s=r.number("CJI_LLM_DEADLINE_S", 90.0, positive=True, unit="seconds"),\n'
     '        rate_per_min=r.integer("CJI_LLM_RATE_PER_MIN", 30, minimum=1),\n'
     '        price_input_per_mtok=price_in,\n'
     '        price_output_per_mtok=price_out,\n'
     '        run_budget=RunBudgetSettings(\n'
     '            max_calls=r.integer("CJI_LLM_RUN_MAX_CALLS", 20, minimum=0),\n'
     '            max_tokens=r.integer("CJI_LLM_RUN_MAX_TOKENS", 50_000, minimum=0),\n'
     '            max_cost_usd=max_cost,\n'
     '        ),\n'
     '    )\n'
     '    mcp = MCPSettings(\n'),
    ('        read_timeout_s=r.number("CJI_MCP_READ_TIMEOUT_S", 300.0, positive=True, unit="seconds"),\n    )\n',
     '        read_timeout_s=r.number("CJI_MCP_READ_TIMEOUT_S", 300.0, positive=True, unit="seconds"),\n'
     '        call_timeout_s=r.number("CJI_MCP_CALL_TIMEOUT_S", 150.0, positive=True, unit="seconds"),\n'
     '    )\n'
     '    if mcp.call_timeout_s < llm.deadline_s:\n'
     '        r.warnings.append(\n'
     '            f"CJI_MCP_CALL_TIMEOUT_S={mcp.call_timeout_s:g} is below CJI_LLM_DEADLINE_S={llm.deadline_s:g}: "\n'
     '            "an insight or narrative tool call can time out before its LLM call finishes."\n'
     '        )\n'),
])

# Helper and imports for load.py.
path = APP / "settings/load.py"
text = path.read_text(encoding="utf-8")
anchor = "\nclass _Reader:\n"
assert text.count(anchor) == 1
text = text.replace(anchor, '''

def _optional_number(r: "_Reader", key: str) -> float | None:
    """A non-negative number when the key is set, else None (Spec 08 prices and cost cap)."""
    return None if r.raw(key) is None else r.number(key, 0.0, minimum=0.0, unit="USD")

''' + anchor, 1)
old_import = "    StorageSettings,\n)\n"
assert text.count(old_import) == 1
text = text.replace(old_import, "    StorageSettings,\n    llm_model_mismatch,\n)\n", 1)
path.write_text(text, encoding="utf-8")
print("edited settings/load.py (helper, imports)")
