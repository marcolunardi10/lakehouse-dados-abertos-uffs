"""Configuração do pipeline: variáveis de ambiente e catálogo de datasets.

Nenhuma credencial é lida de arquivo versionado. Localmente vem do `.env`;
em produção, dos GitHub Actions Secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ_PIPELINE = Path(__file__).resolve().parents[2]
RAIZ_REPO = RAIZ_PIPELINE.parent
CAMINHO_CATALOGO = RAIZ_PIPELINE / "config" / "datasets.yml"

load_dotenv(RAIZ_REPO / ".env")


def _obrigatorio(chave: str) -> str:
    valor = os.getenv(chave)
    if not valor:
        raise RuntimeError(
            f"Variável de ambiente {chave} não definida. "
            "As variáveis necessárias estão na seção 'Reprodução' do README."
        )
    return valor


@dataclass(frozen=True)
class ConfigCKAN:
    base_url: str = field(
        default_factory=lambda: os.getenv("CKAN_BASE_URL", "https://dados.uffs.edu.br")
    )
    # Limite real do DataStore da UFFS: pedidos maiores são truncados em silêncio.
    tamanho_pagina: int = 32_000
    tentativas: int = 6
    timeout_segundos: int = 120

    @property
    def url_sql(self) -> str:
        return f"{self.base_url}/api/3/action/datastore_search_sql"

    @property
    def url_search(self) -> str:
        return f"{self.base_url}/api/3/action/datastore_search"

    @property
    def url_package_show(self) -> str:
        return f"{self.base_url}/api/3/action/package_show"


@dataclass(frozen=True)
class ConfigR2:
    """Cloudflare R2 — API compatível com S3."""

    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    region: str = "auto"

    @classmethod
    def do_ambiente(cls) -> "ConfigR2":
        endpoint = os.getenv("R2_ENDPOINT") or (
            f"https://{_obrigatorio('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
        )
        return cls(
            endpoint=endpoint,
            access_key_id=_obrigatorio("R2_ACCESS_KEY_ID"),
            secret_access_key=_obrigatorio("R2_SECRET_ACCESS_KEY"),
            bucket=os.getenv("R2_BUCKET", "uffs-lakehouse"),
            region=os.getenv("R2_REGION", "auto"),
        )


@dataclass(frozen=True)
class Dataset:
    nome: str
    titulo: str
    pacote: str
    resource_id: str
    dicionario_resource_id: str | None
    sql: str
    # Esquema congelado, usado como contrato na ingestão (seção 4.2.4 da proposta).
    colunas: tuple[str, ...] = ()
    # Subconjunto crítico: além de existir, não pode ter nulos.
    chaves: tuple[str, ...] = ()


@dataclass(frozen=True)
class Catalogo:
    campus_escopo: str
    datasets: dict[str, Dataset]

    def todos(self) -> list[Dataset]:
        return list(self.datasets.values())

    def obter(self, nome: str) -> Dataset:
        if nome not in self.datasets:
            disponiveis = ", ".join(sorted(self.datasets))
            raise KeyError(f"Dataset '{nome}' não existe no catálogo. Disponíveis: {disponiveis}")
        return self.datasets[nome]


@lru_cache(maxsize=1)
def carregar_catalogo(caminho: Path = CAMINHO_CATALOGO) -> Catalogo:
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    datasets = {
        nome: Dataset(
            nome=nome,
            titulo=item["titulo"],
            pacote=item["pacote"],
            resource_id=item["resource_id"],
            dicionario_resource_id=item.get("dicionario_resource_id"),
            sql=item["sql"].strip(),
            colunas=tuple(item.get("colunas", ())),
            chaves=tuple(item.get("chaves", ())),
        )
        for nome, item in bruto["datasets"].items()
    }
    return Catalogo(campus_escopo=bruto["campus_escopo"], datasets=datasets)
