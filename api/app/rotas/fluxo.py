"""Visão 2 — Fluxo acadêmico: evasão e retenção (Análises 4, 5, 6 e 10).

Marts: `gold/visao2_fluxo` (curso × coorte × cota × forma de ingresso × situação)
e `gold/visao2_retencao` (curso × turno × coorte × progressão).

As taxas são computadas aqui, e não na Gold, para que o denominador acompanhe os
filtros aplicados pelo gestor.

Nomenclatura: o que este módulo mede é **evasão de curso**, não evasão
institucional — o grão do dado é o vínculo, não a pessoa (registro-decisoes.md,
D-10 e L-02). A rota `/evasao-reentrada` existe para que o painel exiba as duas
leituras lado a lado.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..deposito import Deposito, obter_deposito
from ..filtros import Filtros, obter_filtros

roteador = APIRouter(prefix="/v1/fluxo", tags=["Visão 2 — fluxo acadêmico"])

COLUNAS = ("nome_curso", "ano_ingresso", "semestre_ingresso")


def _taxa_por(
    deposito: Deposito, filtros: Filtros, dimensoes: list[str], nome_cache: str
) -> list[dict[str, Any]]:
    where, parametros = filtros.clausula(*COLUNAS)
    projecao = ", ".join(dimensoes)
    sql = f"""
        SELECT
            {projecao},
            sum(qtd_estudantes)                                             AS total_ingressantes,
            sum(CASE WHEN situacao_vinculo = 'EVADIDO'   THEN qtd_estudantes ELSE 0 END) AS evadidos,
            sum(CASE WHEN situacao_vinculo = 'CONCLUIDO' THEN qtd_estudantes ELSE 0 END) AS concluidos,
            sum(CASE WHEN situacao_vinculo = 'ATIVO'     THEN qtd_estudantes ELSE 0 END) AS ativos,
            round(
                100.0 * sum(CASE WHEN situacao_vinculo = 'EVADIDO' THEN qtd_estudantes ELSE 0 END)
                / nullif(sum(qtd_estudantes), 0), 2
            ) AS taxa_evasao
        FROM read_parquet('{deposito.mart_uri("visao2_fluxo")}')
        {where}
        GROUP BY {projecao}
        ORDER BY {projecao}
    """
    return deposito.consultar(sql, parametros, filtros.chave_cache(nome_cache))


@roteador.get("/evasao-curso", summary="Análise 4 — taxa de evasão por curso")
async def evasao_curso(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    return _taxa_por(deposito, filtros, ["nome_curso"], "fluxo.evasao_curso")


@roteador.get("/evasao-cota", summary="Análise 5 — evasão comparada por modalidade de ingresso")
async def evasao_cota(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    return _taxa_por(deposito, filtros, ["modalidade_inscricao"], "fluxo.evasao_cota")


@roteador.get("/curva-evasao", summary="Análise 6 — evasão por coorte de ingresso")
async def curva_evasao(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    """Taxa por coorte, não percentual acumulado ao longo dos semestres.

    A métrica original da proposta é incomputável: `sit_matricula` é a situação
    atual e nenhuma coluna registra quando o estudante saiu (L-03). Coortes
    recentes têm muitos vínculos ainda ativos e taxa artificialmente menor — o
    painel precisa sinalizar isso.
    """
    return _taxa_por(deposito, filtros, ["ano_ingresso"], "fluxo.curva_evasao")


@roteador.get(
    "/evasao-reentrada",
    summary="Evasão de curso separada entre primeiro ingresso e reentrada",
)
async def evasao_reentrada(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    """Distingue quem entrou pela primeira vez de quem já era da UFFS.

    Transferência interna, retorno de graduado e retorno de aluno-abandono
    comprovam que o vínculo não é o primeiro na instituição. É o que permite
    afirmar que a evasão institucional é estritamente menor que a de curso,
    ainda que não seja calculável (D-10).
    """
    return _taxa_por(deposito, filtros, ["e_reentrada"], "fluxo.evasao_reentrada")


@roteador.get("/retencao", summary="Análise 10 — retenção frente ao prazo de integralização")
async def retencao(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    """Progressão dos vínculos ativos contra a duração prevista do curso.

    Prazos vêm de `estruturas_curriculares_graduacao`, publicados pela UFFS —
    não são estimados. `sem_parametro` conta os vínculos cujo currículo não foi
    localizado e é devolvido de propósito: omiti-lo daria uma taxa falsamente
    limpa (D-17, L-05).
    """
    where, parametros = filtros.clausula(*COLUNAS)
    ativos = "('NO PRAZO', 'EM RETENCAO', 'RISCO DE JUBILAMENTO')"
    atrasados = "('EM RETENCAO', 'RISCO DE JUBILAMENTO')"
    sql = f"""
        SELECT
            nome_curso,
            sum(CASE WHEN progressao IN {ativos} THEN qtd_estudantes ELSE 0 END) AS ativos_com_parametro,
            sum(CASE WHEN progressao = 'NO PRAZO'             THEN qtd_estudantes ELSE 0 END) AS no_prazo,
            sum(CASE WHEN progressao = 'EM RETENCAO'          THEN qtd_estudantes ELSE 0 END) AS em_retencao,
            sum(CASE WHEN progressao = 'RISCO DE JUBILAMENTO' THEN qtd_estudantes ELSE 0 END) AS risco_jubilamento,
            sum(CASE WHEN progressao = 'SEM PARAMETRO'        THEN qtd_estudantes ELSE 0 END) AS sem_parametro,
            max(semestres_previstos) AS semestres_previstos,
            max(semestres_limite)    AS semestres_limite,
            round(
                100.0 * sum(CASE WHEN progressao IN {atrasados} THEN qtd_estudantes ELSE 0 END)
                / nullif(sum(CASE WHEN progressao IN {ativos} THEN qtd_estudantes ELSE 0 END), 0), 2
            ) AS taxa_atraso
        FROM read_parquet('{deposito.mart_uri("visao2_retencao")}')
        {where}
        GROUP BY nome_curso
        HAVING sum(qtd_estudantes) > 0
        ORDER BY taxa_atraso DESC NULLS LAST
    """
    return deposito.consultar(sql, parametros, filtros.chave_cache("fluxo.retencao"))
