from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REGIMPACT_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    mode: Literal["local", "gcp"] = "local"
    data_dir: Path = PROJECT_ROOT / "data"
    session_ttl_seconds: int = Field(default=14400, ge=60)
    max_sessions: int = Field(default=1000, ge=1)
    session_db: Path | None = None
    runtime_dir: Path = PROJECT_ROOT / ".local"
    enable_live_ai: bool = False
    ai_calls_per_minute: int = Field(default=5, ge=1, le=60)
    ai_calls_per_day: int = Field(default=100, ge=1, le=10000)
    gcp_project_id: str = Field(default="", validation_alias="GCP_PROJECT_ID")
    gcp_region: str = Field(default="", validation_alias="GCP_REGION")
    vertex_location: str = Field(default="", validation_alias="VERTEX_LOCATION")
    gemini_model: str = Field(default="gemini-3.5-flash", validation_alias="GEMINI_MODEL")
    embedding_model: str = Field(default="gemini-embedding-001", validation_alias="EMBEDDING_MODEL")
    spanner_instance: str = Field(default="", validation_alias="SPANNER_INSTANCE")
    spanner_database: str = Field(default="", validation_alias="SPANNER_DATABASE")
    gcs_bucket: str = Field(default="", validation_alias="GCS_BUCKET")
    firestore_database: str = Field(default="(default)", validation_alias="FIRESTORE_DATABASE")
    model_armor_template: str = Field(default="", validation_alias="MODEL_ARMOR_TEMPLATE")
