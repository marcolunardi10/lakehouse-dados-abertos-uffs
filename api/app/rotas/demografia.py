"""Visão 1 — Retrato demográfico e ingresso (Análises 1, 2 e 3).

Mart: gold/visao1_demografia (grão: curso × coorte × cota × forma × gênero × raça).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..deposito import Deposito, obter_deposito
from ..filtros import Filtros, obter_filtros

roteador = APIRouter(prefix="/v1/demografia", tags=["Visão 1 — demografia e ingresso"])

COLUNAS = ("nome_curso", "ano_ingresso", "semestre_ingresso")


def _agregar(
    deposito: Deposito, filtros: Filtros, dimensoes: list[str], nome_cache: str
) -> list[dict[str, Any]]:
    where, parametros = filtros.clausula(*COLUNAS)
    projecao = ", ".join(dimensoes)
    sql = f"""
        SELECT {projecao}, sum(qtd_ingressantes) AS qtd
        FROM read_parquet('{deposito.mart_uri("visao1_demografia")}')
        {where}
        GROUP BY {projecao}
        ORDER BY {projecao}
    """
    return deposito.consultar(sql, parametros, filtros.chave_cache(nome_cache))


@roteador.get("/cotas", summary="Análise 1 — ingressantes por modalidade de cota")
async def cotas(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    return _agregar(
        deposito, filtros, ["ano_ingresso", "grupo_modalidade", "modalidade_inscricao"], "demografia.cotas"
    )


@roteador.get("/genero-raca", summary="Análise 2 — evolução histórica de gênero e raça")
async def genero_raca(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    return _agregar(deposito, filtros, ["ano_ingresso", "genero", "raca"], "demografia.genero_raca")


@roteador.get("/formas-ingresso", summary="Análise 3 — mapeamento das formas de ingresso")
async def formas_ingresso(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    return _agregar(deposito, filtros, ["ano_ingresso", "forma_ingresso"], "demografia.formas")


@roteador.get("/cursos", summary="Cursos disponíveis para o filtro global")
async def cursos(deposito: Deposito = Depends(obter_deposito)) -> list[dict[str, Any]]:
    sql = f"""
        SELECT DISTINCT nome_curso, turno
        FROM read_parquet('{deposito.mart_uri("dim_curso")}')
        ORDER BY nome_curso
    """
    return deposito.consultar(sql, chave_cache="dim_curso.lista")
