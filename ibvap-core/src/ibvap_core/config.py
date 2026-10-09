"""Runtime settings, read from environment variables (see deploy/.env.example)."""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    site_id: str = Field("BOP-DEMO-01", validation_alias=_env("IBVAP_SITE_ID"))
    database_url: str = Field("sqlite:///./data/ibvap.db", validation_alias=_env("IBVAP_DATABASE_URL"))

    mqtt_enabled: bool = Field(True, validation_alias=_env("IBVAP_MQTT_ENABLED"))
    mqtt_host: str = Field("localhost", validation_alias=_env("MQTT_HOST"))
    mqtt_port: int = Field(1883, validation_alias=_env("MQTT_PORT"))
    mqtt_user: str | None = Field(None, validation_alias=_env("MQTT_USER"))
    mqtt_password: str | None = Field(None, validation_alias=_env("MQTT_PASSWORD"))
    frigate_topic_prefix: str = Field("frigate", validation_alias=_env("FRIGATE_TOPIC_PREFIX"))

    rules_path: str = Field("config/rules.yaml", validation_alias=_env("IBVAP_RULES_PATH"))
    site_path: str = Field("config/site.yaml", validation_alias=_env("IBVAP_SITE_PATH"))

    # Built operator dashboard (npm run build in dashboard/), served at /ui/ when present.
    dashboard_dir: str = Field("../dashboard/dist", validation_alias=_env("IBVAP_DASHBOARD_DIR"))

    # Frigate's internal API (port 5000), used to proxy snapshots and clips to the dashboard.
    frigate_api_url: str = Field("http://localhost:5000", validation_alias=_env("FRIGATE_API_URL"))

    # Plate reads below this score are flagged for human review (CLAUDE.md §4, ANPR).
    plate_review_threshold: float = Field(0.8, validation_alias=_env("IBVAP_PLATE_REVIEW_THRESHOLD"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
