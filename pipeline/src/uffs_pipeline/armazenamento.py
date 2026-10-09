"""Acesso ao data lake no Cloudflare R2 (API S3).

A serialização Parquet acontece em memória e o upload é feito com boto3, para
que o comportamento seja idêntico no runner do GitHub Actions e na máquina local.
"""

from __future__ import annotations

import io
from typing import Iterator

import boto3
import polars as pl
from botocore.config import Config as ConfigBoto

from .config import ConfigR2
from .log import configurar

log = configurar(__name__)

COMPRESSAO = "zstd"

# Nome da partição Hive da Bronze. Definido aqui porque `particoes_bronze`
# precisa desmontar o caminho que `ingestao.bronze` monta.
CHAVE_PARTICAO_BRONZE = "data_carga"


class DataLake:
    def __init__(self, config: ConfigR2 | None = None) -> None:
        self.config = config or ConfigR2.do_ambiente()
        self.cliente = boto3.client(
            "s3",
            endpoint_url=self.config.endpoint,
            aws_access_key_id=self.config.access_key_id,
            aws_secret_access_key=self.config.secret_access_key,
            region_name=self.config.region,
            config=ConfigBoto(retries={"max_attempts": 5, "mode": "standard"}),
        )

    # ------------------------------------------------------------------ escrita
    def escrever_parquet(self, df: pl.DataFrame, chave: str) -> str:
        buffer = io.BytesIO()
        df.write_parquet(buffer, compression=COMPRESSAO)
        tamanho = buffer.tell()
        buffer.seek(0)

        self.cliente.put_object(Bucket=self.config.bucket, Key=chave, Body=buffer.getvalue())
        log.info("Gravado s3://%s/%s (%d linhas, %.1f KB)", self.config.bucket, chave, df.height, tamanho / 1024)
        return chave

    def escrever_marcador(self, chave: str) -> str:
        """Grava um objeto vazio. Usado para sinalizar partição concluída."""
        self.cliente.put_object(Bucket=self.config.bucket, Key=chave, Body=b"")
        log.info("Marcador s3://%s/%s", self.config.bucket, chave)
        return chave

    # ------------------------------------------------------------------ leitura
    def ler_parquet(self, chave: str) -> pl.DataFrame:
        objeto = self.cliente.get_object(Bucket=self.config.bucket, Key=chave)
        return pl.read_parquet(io.BytesIO(objeto["Body"].read()))

    def ler_prefixo(self, prefixo: str) -> pl.DataFrame:
        """Concatena todos os Parquet sob um prefixo. Usado para ler partições."""
        chaves = [c for c in self.listar(prefixo) if c.endswith(".parquet")]
        if not chaves:
            raise FileNotFoundError(f"Nenhum Parquet em s3://{self.config.bucket}/{prefixo}")
        return pl.concat([self.ler_parquet(c) for c in chaves], how="vertical_relaxed")

    # ------------------------------------------------------------------ listagem
    def listar(self, prefixo: str) -> list[str]:
        paginador = self.cliente.get_paginator("list_objects_v2")
        chaves: list[str] = []
        for pagina in paginador.paginate(Bucket=self.config.bucket, Prefix=prefixo):
            chaves.extend(item["Key"] for item in pagina.get("Contents", []))
        return sorted(chaves)

    def particoes_bronze(self, dataset: str) -> list[str]:
        """Datas de carga disponíveis na Bronze, da mais antiga para a mais recente.

        Devolve apenas a data (`2026-08-29`), sem o `data_carga=` do caminho no
        estilo Hive — quem chama remonta o prefixo com `CHAVE_PARTICAO_BRONZE`.
        """
        prefixo = f"bronze/{dataset}/"
        marcador = f"{CHAVE_PARTICAO_BRONZE}="
        datas = {
            segmento[len(marcador):]
            for chave in self.listar(prefixo)
            if chave.endswith(".parquet")
            for segmento in [chave[len(prefixo):].split("/", 1)[0]]
            if segmento.startswith(marcador)
        }
        return sorted(datas)

    def ultima_particao_bronze(self, dataset: str) -> str:
        particoes = self.particoes_bronze(dataset)
        if not particoes:
            raise FileNotFoundError(
                f"Bronze vazia para '{dataset}'. Rode primeiro: cli ingestao --dataset {dataset}"
            )
        return particoes[-1]

    def apagar_prefixo(self, prefixo: str) -> int:
        """Limpa uma camada derivada antes de reescrevê-la (Silver e Gold)."""
        chaves = self.listar(prefixo)
        for lote in _em_lotes(chaves, 1000):
            self.cliente.delete_objects(
                Bucket=self.config.bucket,
                Delete={"Objects": [{"Key": c} for c in lote]},
            )
        if chaves:
            log.info("Removidos %d objetos sob %s", len(chaves), prefixo)
        return len(chaves)


def _em_lotes(itens: list[str], tamanho: int) -> Iterator[list[str]]:
    for inicio in range(0, len(itens), tamanho):
        yield itens[inicio : inicio + tamanho]
