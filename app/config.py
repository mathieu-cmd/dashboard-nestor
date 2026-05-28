"""Settings — alles uit environment variables.

Dashboard-nestor heeft een schoner config dan invoice-bundler want we
hebben geen Service Bus, geen email, geen Peppol — alleen Prato Postgres
+ optionele lokale opslag voor latere SQLite-cache.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Settings:
    # Optioneel — voor latere sessies/auth. Lege string als niet gezet.
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "")

    # Volume mount path — bedoeld voor latere SQLite-cache van Prato-data.
    DATA_DIR: str = os.environ.get("DATA_DIR", "/data")

    # ── Prato Postgres (read-only via reporter_nestor_nestor) ────────────
    PRATO_DB_HOST: str = os.environ.get("PRATO_DB_HOST", "")
    PRATO_DB_PORT: int = int(os.environ.get("PRATO_DB_PORT", "5432"))
    PRATO_DB_USER: str = os.environ.get("PRATO_DB_USER", "")
    PRATO_DB_PASSWORD: str = os.environ.get("PRATO_DB_PASSWORD", "")
    PRATO_DB_NAME: str = os.environ.get("PRATO_DB_NAME", "")
    PRATO_DB_SSLMODE: str = os.environ.get("PRATO_DB_SSLMODE", "require")
    PRATO_DB_STATEMENT_TIMEOUT_MS: int = int(
        os.environ.get("PRATO_DB_STATEMENT_TIMEOUT_MS", "300000")
    )


settings = Settings()
