"""Configuration error type (Spec 04). Pure module."""

from __future__ import annotations

from collections.abc import Sequence


class ConfigError(RuntimeError):
    """
    Every configuration problem found, collected into one error.

    Each problem names the variable, says what is wrong and how to fix it, and never
    contains a secret value. Subclasses RuntimeError so existing callers that catch
    RuntimeError (Spec 02 collector checks) keep working.
    """

    def __init__(
        self,
        problems: Sequence[str],
        *,
        role: str | None = None,
        env: str | None = None,
    ) -> None:
        self.problems: tuple[str, ...] = tuple(problems)
        self.role = role
        self.env = env
        super().__init__(self._render())

    def _render(self) -> str:
        where = f" for role '{self.role}'" if self.role else ""
        env = f" (CJI_ENV={self.env})" if self.env else ""
        lines = [f"CJI configuration is invalid{where}{env}:"]
        lines += [f"  {i}. {problem}" for i, problem in enumerate(self.problems, 1)]
        role = f" --role {self.role}" if self.role else ""
        lines.append(f"Run: cji-settings check{role}")
        return "\n".join(lines)
