from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    google_genai_use_vertexai: bool = Field(default=False, alias="GOOGLE_GENAI_USE_VERTEXAI")
    database_path: Path = Field(default=ROOT / "data" / "logipilot.db", alias="LOGIPILOT_DATABASE_PATH")
    env: str = Field(default="development", alias="LOGIPILOT_ENV")
    use_sample_data: bool = Field(default=True, alias="LOGIPILOT_USE_SAMPLE_DATA")
    avg_speed_kmh: float = Field(default=40.0, alias="LOGIPILOT_AVG_SPEED_KMH")
    road_factor: float = Field(default=1.3, alias="LOGIPILOT_ROAD_FACTOR")
    max_detour_km: float = Field(default=80.0, alias="LOGIPILOT_MAX_DETOUR_KM")
    max_detour_pct: float = Field(default=0.15, alias="LOGIPILOT_MAX_DETOUR_PCT")
    fuel_l_per_100km: float = Field(default=25.0, alias="LOGIPILOT_FUEL_L_PER_100KM")
    fuel_price_per_litre: float = Field(default=96.0, alias="LOGIPILOT_FUEL_PRICE_PER_LITRE")
    currency: str = Field(default="INR", alias="LOGIPILOT_CURRENCY")
    approval_secret: str = Field(default="change-me-in-production", alias="LOGIPILOT_APPROVAL_SECRET")
    host: str = Field(default="0.0.0.0", alias="LOGIPILOT_HOST")
    port: int = Field(default=8080, alias="LOGIPILOT_PORT")
    loadlink_algorithm_version: str = Field(
        default="loadlink-match-1.0.0", alias="LOADLINK_ALGORITHM_VERSION"
    )
    routewise_algorithm_version: str = Field(
        default="routewise-nn-2opt-1.0.0", alias="ROUTEWISE_ALGORITHM_VERSION"
    )
    gemini_model: str = Field(default="gemini-flash-latest", alias="LOGIPILOT_GEMINI_MODEL")

    @property
    def data_class(self) -> str:
        return "simulated" if self.use_sample_data else "operational"


@lru_cache
def get_settings() -> Settings:
    return Settings()
