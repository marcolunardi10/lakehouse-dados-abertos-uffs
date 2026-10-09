"""Acesso analítico aos data marts com DuckDB embarcado.

Estratégia de latência (seção 4.2.6 da proposta): conexão única de longa vida
com `httpfs` configurado, cache em memória com TTL e aquecimento no startup.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import duckdb

from .config import Config, obter_config

log = logging.getLogger(__name__)

# Marts aquecidos na inicialização. Todos cabem em poucas centenas de KB.
MARTS_AQUECIDOS = (
    "dim_curso",
    "visao1_demografia",
    "visao2_fluxo",
    "visao2_retencao",
    "visao3_desempenho",
    "visao3_frequencia_media",
)


class Deposito:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or obter_config()
        self._trava = threading.Lock()
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._conexao = self._conectar()

    def _conectar(self) -> duckdb.DuckDBPyConnection:
        conexao = duckdb.connect(":memory:")
        conexao.execute("INSTALL httpfs; LOAD httpfs;")
        conexao.execute(f"SET s3_endpoint = '{self.config.endpoint_s3}';")
        conexao.execute(f"SET s3_region = '{self.config.r2_region}';")
        conexao.execute(f"SET s3_access_key_id = '{self.config.r2_access_key_id}';")
        conexao.execute(f"SET s3_secret_access_key = '{self.config.r2_secret_access_key}';")
        conexao.execute("SET s3_url_style = 'path';")  # exigido pelo R2
        log.info("DuckDB conectado ao R2 em %s", self.config.endpoint_s3)
        return conexao

    # ------------------------------------------------------------------ consulta
    def consultar(
        self,
        sql: str,
        parametros: list[Any] | None = None,
        chave_cache: str | None = None,
    ) -> list[dict[str, Any]]:
        """Executa SQL parametrizado e devolve registros prontos para serializar.

        `sql` usa `?` para valores — nunca interpole entrada de usuário no texto
        da consulta. Nomes de mart vêm de `mart_uri`, que valida contra a lista
        conhecida.
        """
        agora = time.monotonic()
        if chave_cache:
            entrada = self._cache.get(chave_cache)
            if entrada and agora - entrada[0] < self.config.api_cache_ttl_segundos:
                return entrada[1]

        with self._trava:  # a conexão DuckDB não é thread-safe para execução concorrente
            cursor = self._conexao.execute(sql, parametros or [])
            colunas = [descricao[0] for descricao in cursor.description]
            # `fetchall` + `description` evita a dependência de pyarrow (~40 MB),
            # que pesaria nos 512 MB de RAM do plano gratuito do Render. Os marts
            # são pequenos o bastante para materializar a resposta inteira.
            resultado = [dict(zip(colunas, linha)) for linha in cursor.fetchall()]

        if chave_cache:
            self._cache[chave_cache] = (agora, resultado)
        return resultado

    def mart_uri(self, mart: str) -> str:
        if mart not in MARTS_AQUECIDOS:
            raise KeyError(f"Mart desconhecido: {mart}")
        return self.config.caminho_mart(mart)

    # ------------------------------------------------------------------ ciclo de vida
    def aquecer(self) -> None:
        """Cache warming: paga a latência de rede uma vez, no boot do container."""
        for mart in MARTS_AQUECIDOS:
            try:
                inicio = time.perf_counter()
                total = self.consultar(f"SELECT count(*) AS n FROM read_parquet('{self.mart_uri(mart)}')")
                log.info(
                    "Mart '%s' aquecido: %s linhas em %.0f ms",
                    mart,
                    total[0]["n"],
                    (time.perf_counter() - inicio) * 1000,
                )
            except Exception as erro:  # noqa: BLE001 — o boot não pode falhar por um mart ausente
                log.warning("Falha ao aquecer '%s': %s", mart, erro)

    def saudavel(self) -> bool:
        try:
            self._conexao.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False

    def fechar(self) -> None:
        self._conexao.close()


_deposito: Deposito | None = None


def obter_deposito() -> Deposito:
    """Dependência do FastAPI. Uma instância por processo."""
    global _deposito
    if _deposito is None:
        _deposito = Deposito()
    return _deposito
