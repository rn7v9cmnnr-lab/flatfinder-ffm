"""Konfiguration. Alles ueber .env, nichts hartkodiert."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Criteria(BaseSettings):
    """Suchkriterien. Treiben Filter und Scoring."""

    model_config = SettingsConfigDict(env_prefix="SEARCH_", env_file=".env", extra="ignore")

    city: str = "Frankfurt am Main"
    price_max: int = 1400          # Kaltmiete, hartes Limit
    price_ideal: int = 1000        # darunter gibt es Punkte
    sqm_min: float = 55.0
    rooms_min: float = 2.0
    rooms_max: float = 4.0
    # Leere Liste = alle Stadtteile. Sonst Bonus fuer Treffer in der Liste.
    districts_preferred: list[str] = Field(default_factory=list)
    districts_excluded: list[str] = Field(default_factory=list)
    accept_wbs: bool = False       # Wohnberechtigungsschein vorhanden?
    accept_commission: bool = True

    notify_threshold: int = 50     # ab hier Nachricht
    auto_yes_threshold: int = 90   # ab hier Auto-Ja nach Timeout
    auto_yes_after_minutes: int = 10
    auto_yes_enabled: bool = False # bewusst aus - erst einschalten, wenn du
                                   # den generierten Texten vertraust


class Profile(BaseSettings):
    """Davids Bewerberprofil. Geht 1:1 in den Bewerbungstext.

    Nur wahre Angaben. Der Bot darf nichts erfinden - siehe compose.py.
    """

    model_config = SettingsConfigDict(env_prefix="PROFILE_", env_file=".env", extra="ignore")

    full_name: str = ""
    email: str = ""
    phone: str = ""
    occupation: str = ""           # "Softwareentwickler, unbefristet seit 2021"
    employer: str = ""
    net_income: int = 0            # Haushaltsnettoeinkommen/Monat
    household_size: int = 1
    household_detail: str = ""     # "alleinstehend, Nichtraucher, keine Haustiere"
    move_in_from: str = ""         # "ab sofort" / "zum 01.12.2026"
    schufa_available: bool = True
    docs_ready: str = ""           # "SCHUFA, 3 Gehaltsnachweise, Mietschuldenfreiheit"
    viewing_availability: str = "kurzfristig, auch abends und am Wochenende"
    extra_notes: str = ""          # freiwillig, z.B. "seit 8 Jahren in Frankfurt"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"

    messenger: str = "telegram"    # "telegram" | "whatsapp"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_recipient: str = ""        # deine Nummer, international: 4915...
    whatsapp_template_name: str = "neues_wohnungsangebot"
    whatsapp_verify_token: str = ""     # fuer die Webhook-Verifizierung

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Alarm-Modus: nur finden und melden, keine Bewerbungen.
    # Der Bewerbungs-Teil bleibt im Code, ist aber vom Weg.
    notify_only: bool = True

    db_path: str = "data/flatfinder.db"
    poll_interval_seconds: int = 3600
    ingest_token: str = ""              # Heim-Node -> Core Authentifizierung
    dry_run: bool = True                # NICHTS wird wirklich versendet
