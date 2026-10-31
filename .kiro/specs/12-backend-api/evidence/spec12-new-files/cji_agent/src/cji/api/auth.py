"""
Bearer-token authentication and role/journey authorization for /api/v1 (Spec 12, OD-109, OD-110).

Tokens are `cji_api_<43 url-safe characters>`. Only their SHA-256 is stored, in a JSON token file managed by
`cji-api-token`. Lookups hash the presented token and compare it with every stored hash in constant time.
The file is re-read when its modification time or size changes. Logs name tokens by id, never by value.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Role = Literal["viewer", "operator", "admin"]
ROLE_RANK: dict[str, int] = {"viewer": 1, "operator": 2, "admin": 3}
TOKEN_PREFIX = "cji_api_"  # nosec B105 - public token prefix, not a secret
ALL_JOURNEYS = "*"


class TokenFileError(RuntimeError):
    """The token file exists but cannot be used (invalid JSON or entries)."""


class TokenEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^tok_[0-9a-f]{8,16}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    label: str = Field(min_length=1, max_length=80)
    role: Role
    journeys: list[str] = Field(min_length=1, max_length=100)
    created_at: str
    expires_at: str | None = None
    revoked: bool = False


class TokenFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    tokens: list[TokenEntry] = Field(default_factory=list)


@dataclass(frozen=True)
class Principal:
    token_id: str
    label: str
    role: str
    journeys: tuple[str, ...]

    def has_role(self, role: str) -> bool:
        return ROLE_RANK.get(self.role, 0) >= ROLE_RANK[role]

    @property
    def all_journeys(self) -> bool:
        return ALL_JOURNEYS in self.journeys

    def can_see(self, journey_id: str | None) -> bool:
        """`None` (journey unknown) is visible only to tokens with every journey."""
        if self.all_journeys:
            return True
        return journey_id is not None and journey_id in self.journeys

    def visible_journeys(self) -> tuple[str, ...] | None:
        """None = all journeys."""
        return None if self.all_journeys else self.journeys


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_id_for(token: str) -> str:
    """Public id of a token: derived from its hash, safe to log and show."""
    return "tok_" + hash_token(token)[:12]


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)          # Python 3.11+ reads a trailing Z
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def load_token_file(path: Path) -> TokenFile:
    if not path.exists():
        return TokenFile()
    try:
        return TokenFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise TokenFileError(f"token file {path.name} is not valid ({type(exc).__name__})") from None


def save_token_file(path: Path, data: TokenFile) -> None:
    """Atomic write (temporary file in the same directory, then rename); owner-only permissions where supported."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data.model_dump_json(indent=2))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def create_token(path: Path, *, label: str, role: str, journeys: list[str], expires_days: int | None = None) -> str:
    """Add a token to the file and return it (the only time the value is available)."""
    data = load_token_file(path)
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = _now()
    expires = (now + timedelta(days=expires_days)).isoformat() if expires_days is not None else None
    data.tokens.append(TokenEntry(id=token_id_for(token), sha256=hash_token(token), label=label, role=role,  # type: ignore[arg-type]
                                  journeys=list(journeys), created_at=now.isoformat(), expires_at=expires))
    save_token_file(path, data)
    return token


def revoke_token(path: Path, token_id: str) -> bool:
    data = load_token_file(path)
    changed = False
    for entry in data.tokens:
        if entry.id == token_id and not entry.revoked:
            entry.revoked = True
            changed = True
    if changed:
        save_token_file(path, data)
    return changed


class TokenStore:
    """Authenticates bearer tokens against the token file (reloaded when it changes)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._stamp: tuple[int, int] | None = None
        self._entries: list[TokenEntry] = []

    def _stat(self) -> tuple[int, int] | None:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size

    def entries(self) -> list[TokenEntry]:
        with self._lock:
            stamp = self._stat()
            if stamp != self._stamp or stamp is None:
                self._entries = load_token_file(self.path).tokens
                self._stamp = stamp
            return list(self._entries)

    def authenticate(self, token: str) -> Principal | None:
        if not token or not token.startswith(TOKEN_PREFIX) or len(token) > 200:
            return None
        presented = hash_token(token)
        match: TokenEntry | None = None
        for entry in self.entries():                     # compare against every entry: no early exit
            if hmac.compare_digest(presented, entry.sha256):
                match = entry
        if match is None or match.revoked:
            return None
        if match.expires_at is not None and _parse_time(match.expires_at) <= _now():
            return None
        return Principal(match.id, match.label, match.role, tuple(match.journeys))
