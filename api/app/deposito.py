"""Acesso analítico aos data marts com DuckDB embarcado.

Os seis marts da Gold são copiados do R2 para **tabelas em memória** na
inicialização (aquecimento) e recarregados quando passam do tempo de vida
configurado. Toda consulta das rotas roda sobre a memória, sem rede.

Por que não consultar o Parquet no R2 a cada requisição, como a proposta
descrevia: medido em 10/10/2026, cada consulta ainda não vista levava de 0,35 a
1 s de ida ao R2, e o painel dispara cerca de dez por troca de filtro. Os marts
somam 387 KB — não há bloco a pular num arquivo desse tamanho, ele vem inteiro
de qualquer forma. Ver docs/registro-decisoes.md, D-30.

Condição da escolha: a Gold precisa caber com folga na memória do serviço. Se um
dia os marts chegarem a centenas de megabytes, a consulta direta ao Parquet
volta a ser o desenho certo.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import duckdb

from .config import Config, obter_config

log = logging.getLogger(__name__)

# Marts carregados em memória. É também a lista fechada de nomes de tabela que
# podem aparecer no SQL das rotas.
MARTS_AQUECIDOS = (
    "dim_curso",
    "visao1_demografia",
    "visao2_fluxo",
    "visao2_retencao",
    "visao3_desempenho",
    "visao3_frequencia_media",
)

# Se a recarga falhar e houver uma cópia anterior, espera-se este tempo antes
# de tentar de novo — sem isso, cada requisição durante uma queda do R2 pagaria
# o tempo de uma tentativa de rede fracassada.
ESPERA_APOS_FALHA_SEGUNDOS = 60


class Deposito:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or obter_config()
        # Reentrante: `tabela` pode recarregar um mart enquanto já segura a trava.
        self._trava = threading.RLock()
        self._carregado_em: dict[str, float] = {}
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

    # ------------------------------------------------------------------ carga
    def _carregar(self, mart: str) -> int:
        """Copia um mart do R2 para uma tabela em memória. Devolve o nº de linhas."""
        origem = self.config.caminho_mart(mart)
        self._conexao.execute(
            f"CREATE OR REPLACE TABLE {mart} AS SELECT * FROM read_parquet('{origem}')"
        )
        self._carregado_em[mart] = time.monotonic()
        return self._conexao.execute(f"SELECT count(*) FROM {mart}").fetchone()[0]

    def tabela(self, mart: str) -> str:
        """Nome da tabela em memória de um mart, garantindo que ela esteja fresca.

        É o único caminho pelo qual um nome de tabela entra no SQL das rotas, e
        ele valida contra a lista fechada de marts.

        Se o tempo de vida venceu, recarrega do R2 antes de devolver. Se a
        recarga falhar e já houver uma cópia, a API segue servindo a cópia
        antiga — melhor um dado de 15 minutos atrás do que um erro.
        """
        if mart not in MARTS_AQUECIDOS:
            raise KeyError(f"Mart desconhecido: {mart}")

        with self._trava:
            carregado_em = self._carregado_em.get(mart)
            vencido = (
                carregado_em is None
                or time.monotonic() - carregado_em >= self.config.api_cache_ttl_segundos
            )
            if vencido:
                try:
                    self._carregar(mart)
                except Exception as erro:  # noqa: BLE001 — qualquer falha de rede ou de leitura
                    if carregado_em is None:
                        raise
                    log.warning(
                        "Falha ao recarregar '%s' (%s). Servindo a cópia anterior; "
                        "nova tentativa em %d s.",
                        mart,
                        erro,
                        ESPERA_APOS_FALHA_SEGUNDOS,
                    )
                    self._carregado_em[mart] = (
                        time.monotonic()
                        - self.config.api_cache_ttl_segundos
                        + ESPERA_APOS_FALHA_SEGUNDOS
                    )
        return mart

    # ------------------------------------------------------------------ consulta
    def consultar(self, sql: str, parametros: list[Any] | None = None) -> list[dict[str, Any]]:
        """Executa SQL parametrizado e devolve registros prontos para serializar.

        `sql` usa `?` para valores — nunca interpole entrada de usuário no texto
        da consulta. Nomes de tabela vêm de `tabela`, que valida contra a lista
        conhecida.

        Não há cache de respostas: com os dados em memória a consulta leva
        poucos milissegundos, e um cache por combinação de filtros só cresceria.
        """
        with self._trava:  # a conexão DuckDB não é thread-safe para execução concorrente
            cursor = self._conexao.execute(sql, parametros or [])
            colunas = [descricao[0] for descricao in cursor.description]
            # `fetchall` + `description` evita a dependência de pyarrow (~40 MB),
            # que pesaria nos 512 MB de RAM do plano gratuito do Render.
            return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]

    # ------------------------------------------------------------------ ciclo de vida
    def aquecer(self) -> None:
        """Carrega todos os marts em memória no boot do container.

        Paga a latência do R2 uma vez, na inicialização, em vez de na primeira
        consulta de cada gestor.
        """
        for mart in MARTS_AQUECIDOS:
            try:
                inicio = time.perf_counter()
                with self._trava:
                    linhas = self._carregar(mart)
                log.info(
                    "Mart '%s' em memória: %s linhas em %.0f ms",
                    mart,
                    linhas,
                    (time.perf_counter() - inicio) * 1000,
                )
            except Exception as erro:  # noqa: BLE001 — o boot não pode falhar por um mart ausente
                log.warning("Falha ao carregar '%s': %s", mart, erro)

    def saudavel(self) -> bool:
        try:
            with self._trava:
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
