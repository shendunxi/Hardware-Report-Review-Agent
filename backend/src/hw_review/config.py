"""Configuration defaults for the local vertical slice."""

from dataclasses import dataclass, field
from pathlib import Path


def _default_a11_template_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "a11"
        / "hardware-test-process-checklist-a11.xls"
    )


@dataclass(frozen=True, slots=True)
class Settings:
    """Local development settings; production persistence is intentionally undecided."""

    database_url: str = "sqlite:///./hw-review.db"
    storage_root: Path = Path("./storage")
    a11_template_path: Path = field(default_factory=_default_a11_template_path)
    auth_mode: str = "local"
    local_session_secret: str = "local-development-only-change-me"
    local_session_ttl_seconds: int = 28_800
    local_session_cookie: str = "hw_review_session"


def get_settings() -> Settings:
    """Return the explicit local-development defaults."""

    return Settings()
