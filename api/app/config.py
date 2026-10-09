"""Configuração da API. Em produção vem do painel de Environment do Render."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_REPO = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ_REPO / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "uffs-lakehouse"
    r2_endpoint: str = ""
    r2_region: str = "auto"

    api_key: str = ""
    api_cache_ttl_segundos: int = 900

    @property
    def endpoint_s3(self) -> str:
        """Host do endpoint, sem esquema — formato exigido pelo httpfs do DuckDB."""
        bruto = self.r2_endpoint or f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        return bruto.removeprefix("https://").removeprefix("http://").rstrip("/")

    def caminho_mart(self, mart: str) -> str:
        return f"s3://{self.r2_bucket}/gold/{mart}/*.parquet"


@lru_cache(maxsize=1)
def obter_config() -> Config:
    return Config()
