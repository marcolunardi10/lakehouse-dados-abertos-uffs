"""Cliente do DataStore CKAN da UFFS.

Trata as três restrições medidas da origem (ver docs/dicionario-dados.md):

1. Teto de 32.000 linhas por requisição — resolvido por paginação.
2. Resets de conexão TLS esporádicos (~10-15% das requisições, medido em
   29/08/2026). O reset atinge a conexão, não a consulta: uma requisição
   idêntica reenviada em conexão nova é atendida. Retentar no nível da
   aplicação não basta, porque a `Session` devolve o socket morto do pool e
   todas as chamadas seguintes falham em cascata. A correção é a política
   `Retry` do urllib3, que descarta a conexão quebrada e refaz o handshake.
3. Consultas longas (o JOIN de `historico` envolvido pela subconsulta de
   paginação passa de 600 caracteres) — enviadas via POST com corpo JSON,
   que a Action API do CKAN aceita para qualquer ação.
"""

from __future__ import annotations

import time
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter, Retry

from .config import ConfigCKAN
from .log import configurar

log = configurar(__name__)


class ErroCKAN(RuntimeError):
    pass


class ClienteCKAN:
    def __init__(self, config: ConfigCKAN | None = None) -> None:
        self.config = config or ConfigCKAN()
        self.sessao = self._nova_sessao()

    def _nova_sessao(self) -> requests.Session:
        sessao = requests.Session()
        sessao.headers.update({"User-Agent": "uffs-tcc-pipeline/0.1"})
        politica = Retry(
            total=self.config.tentativas,
            connect=self.config.tentativas,
            read=self.config.tentativas,
            status=self.config.tentativas,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "POST"]),
        )
        adaptador = HTTPAdapter(max_retries=politica)
        sessao.mount("https://", adaptador)
        sessao.mount("http://", adaptador)
        return sessao

    def _requisitar(self, url: str, carga: dict[str, Any]) -> dict[str, Any]:
        """POST na Action API. O urllib3 já reteve falhas de conexão e 5xx.

        O laço externo cobre o que a política do urllib3 não cobre — sobretudo
        respostas 200 com `success: false` — e, ao repetir, troca a sessão
        inteira para garantir um pool de conexões limpo.
        """
        ultimo_erro: Exception | None = None
        for tentativa in range(1, self.config.tentativas + 1):
            try:
                resposta = self.sessao.post(url, json=carga, timeout=self.config.timeout_segundos)
                resposta.raise_for_status()
                corpo = resposta.json()
                if not corpo.get("success"):
                    raise ErroCKAN(f"CKAN retornou erro: {corpo.get('error')}")
                return corpo["result"]
            except Exception as erro:  # noqa: BLE001 — qualquer falha de rede é retentável
                ultimo_erro = erro
                espera = min(2**tentativa, 30)
                log.warning(
                    "Tentativa %d/%d falhou (%s). Sessão renovada; nova tentativa em %ds.",
                    tentativa,
                    self.config.tentativas,
                    type(erro).__name__,
                    espera,
                )
                self.sessao.close()
                self.sessao = self._nova_sessao()
                time.sleep(espera)
        raise ErroCKAN(f"Falha após {self.config.tentativas} tentativas: {ultimo_erro}")

    def consultar_paginado(self, sql: str) -> Iterator[list[dict[str, Any]]]:
        """Executa uma consulta SQL paginada, devolvendo um lote por página.

        A consulta do catálogo NÃO deve conter LIMIT/OFFSET — eles são
        aplicados aqui, envolvendo a consulta em uma subconsulta.
        """
        pagina = self.config.tamanho_pagina
        deslocamento = 0
        total = 0

        while True:
            consulta = f"SELECT * FROM ({sql}) AS pagina LIMIT {pagina} OFFSET {deslocamento}"
            registros = self._requisitar(self.config.url_sql, {"sql": consulta})["records"]
            if not registros:
                break

            total += len(registros)
            log.info("Página lida: %d registros (acumulado: %d)", len(registros), total)
            yield registros

            if len(registros) < pagina:
                break
            deslocamento += pagina

        log.info("Extração concluída: %d registros.", total)

    def metadados_recurso(self, resource_id: str) -> dict[str, Any]:
        """Esquema e volumetria de um recurso, sem baixar os dados."""
        resultado = self._requisitar(self.config.url_search, {"resource_id": resource_id, "limit": 0})
        return {
            "resource_id": resource_id,
            "total": resultado.get("total"),
            "campos": {c["id"]: c["type"] for c in resultado.get("fields", [])},
        }

    def recursos_do_pacote(self, pacote: str) -> list[dict[str, Any]]:
        resultado = self._requisitar(self.config.url_package_show, {"id": pacote})
        return [
            {
                "id": r["id"],
                "nome": r.get("name"),
                "formato": r.get("format"),
                "datastore_ativo": r.get("datastore_active"),
            }
            for r in resultado.get("resources", [])
        ]
