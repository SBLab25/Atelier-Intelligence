"""Journey definitions (Spec 12, OD-111): today the configured journey; a list so more can be added."""
from __future__ import annotations

from cji.domain.journeys import JourneyDefinition, journey_from_config
from cji.settings import Settings


def configured_steps() -> list[str]:
    from cji.config import JOURNEY_CONFIG

    return list(JOURNEY_CONFIG["steps"])


def list_journeys(settings: Settings) -> list[JourneyDefinition]:
    """All configured journeys and dynamically discovered journeys, ordered by name."""
    names = [settings.app.journey_name]
    for candidate in ("user_onboarding", "onboarding", "my_vercel_site", "all"):
        if candidate not in names:
            names.append(candidate)

    # Dynamic journey discovery from database if configured
    db_url = settings.database.url_value()
    if db_url:
        try:
            from sqlalchemy import create_engine, text
            eng = create_engine(db_url, pool_pre_ping=True)
            with eng.connect() as conn:
                rows = conn.execute(text("SELECT DISTINCT journey_name FROM live_events WHERE journey_name IS NOT NULL LIMIT 50")).fetchall()
                for r in rows:
                    if r[0] and r[0] not in names:
                        names.append(str(r[0]))
                key_rows = conn.execute(text("SELECT DISTINCT journey_name FROM api_keys WHERE journey_name IS NOT NULL LIMIT 50")).fetchall()
                for kr in key_rows:
                    if kr[0]:
                        for item in str(kr[0]).replace(";", ",").split(","):
                            clean = item.strip()
                            if clean and clean != "*" and clean not in names:
                                names.append(clean)
            eng.dispose()
        except Exception:
            pass

    return [journey_from_config({"name": n, "steps": configured_steps()}) for n in sorted(set(names))]


def get_journey(settings: Settings, journey_id: str) -> JourneyDefinition | None:
    return next((j for j in list_journeys(settings) if j.name == journey_id), None)
