"""Cliente HTTP da camada de serviço.

O painel é puramente de apresentação: nenhuma regra de negócio educacional vive
aqui — é o que sustenta o desacoplamento headless BI da seção 4.2.6 da proposta.
"""

from __future__ import annotations

import os
from typing import Any

import polars as pl
import requests
import streamlit as st

TIMEOUT = 30


def _segredo(chave: str, padrao: str = "") -> str:
    """Lê de `st.secrets` quando houver, senão do ambiente.

    `st.secrets.get(...)` **não** protege contra a ausência do arquivo: o
    simples acesso a `st.secrets` dispara a procura por `secrets.toml` e
    levanta `StreamlitSecretNotFoundError` antes de o `.get` ser avaliado.
    No Streamlit Community Cloud os valores vêm dos *secrets*; localmente,
    do `.env` exportado no ambiente.
    """
    try:
        valor = st.secrets.get(chave)
    except Exception:  # noqa: BLE001 — sem secrets.toml é o caso normal em desenvolvimento
        valor = None
    return str(valor) if valor else os.getenv(chave, padrao)


def _base_url() -> str:
    return _segredo("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _cabecalhos() -> dict[str, str]:
    chave = _segredo("API_KEY")
    return {"X-API-Key": chave} if chave else {}


@st.cache_data(ttl=900, show_spinner="Consultando indicadores...")
def buscar(rota: str, **parametros: Any) -> pl.DataFrame:
    """GET em uma rota da API, já como DataFrame Polars.

    Polars em toda a pilha, como descrito na proposta: o Plotly 6 consome
    DataFrames Polars nativamente (via Narwhals) e o Streamlit também, então o
    painel não precisa de uma segunda biblioteca de dados só para apresentar.

    O TTL de 15 min espelha o da API (D-30): os dados só mudam quando o pipeline
    roda, então recarregar com mais frequência só gera latência.
    """
    limpos = {k: v for k, v in parametros.items() if v is not None}
    resposta = requests.get(
        f"{_base_url()}{rota}", params=limpos, headers=_cabecalhos(), timeout=TIMEOUT
    )
    resposta.raise_for_status()
    registros = resposta.json()
    # `infer_schema_length=None` varre todos os registros: as rotas devolvem
    # colunas numéricas que podem vir nulas nas primeiras linhas.
    return pl.DataFrame(registros, infer_schema_length=None) if registros else pl.DataFrame()


def verificar_saude() -> bool:
    try:
        resposta = requests.get(f"{_base_url()}/health", timeout=10)
        return resposta.ok and resposta.json().get("status") == "ok"
    except requests.RequestException:
        return False
