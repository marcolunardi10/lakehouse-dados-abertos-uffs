"""Visão 3 — Desempenho e gargalos curriculares (Análises 7, 8, 9 e 11).

Marts: gold/visao3_desempenho e gold/visao3_frequencia_media.
Atenção: o grão aqui é a MATRÍCULA EM TURMA, não o ingressante. As colunas de
filtro mudam de nome (`curso`, `ano`, `semestre`) em relação às Visões 1 e 2.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..deposito import Deposito, obter_deposito
from ..filtros import Filtros, obter_filtros

roteador = APIRouter(prefix="/v1/desempenho", tags=["Visão 3 — desempenho e gargalos"])

COLUNAS = ("curso", "ano", "semestre")

# Piso de matrículas para um CCR entrar no ranking, espelhando
# regras.MINIMO_MATRICULADOS_GARGALO do pipeline.
MINIMO_MATRICULAS_PADRAO = 50

# Matrículas que não chegaram a um resultado (trancamento, cancelamento,
# desistência, turma em curso) ficam fora do numerador e do denominador das
# taxas e das médias, como define `regras.RESULTADO_NEUTRO` no pipeline (D-35).
COM_RESULTADO = "resultado <> 'NEUTRO'"


def _com_resultado(where: str) -> str:
    """Acrescenta o recorte de matrículas com resultado ao WHERE dos filtros."""
    return f"{where} AND {COM_RESULTADO}" if where else f"WHERE {COM_RESULTADO}"

# Um mesmo componente curricular tem vários `cod_ccr`: 271 dos 1.198 nomes de
# CCR de Chapecó (22,6%) aparecem com mais de um código, por duas razões —
# versões sucessivas da matriz curricular e oferta por cursos distintos.
# Agrupar só por código fragmenta a disciplina, cria linhas aparentemente
# duplicadas no ranking e esconde a magnitude real (Geometria Analítica passa
# de 1.173 matrículas no maior fragmento para 3.341 somada).
#
# As duas leituras são legítimas e respondem a perguntas diferentes:
AGRUPAMENTOS = {
    # "Qual disciplina é gargalo no campus?" — une versões de matriz e cursos.
    "nome": ["nome_ccr"],
    # "Qual disciplina é gargalo em cada curso?" — mantém cursos separados,
    # útil para a coordenação; ainda une as versões de matriz dentro do curso.
    "curso": ["curso", "nome_ccr"],
}


@roteador.get("/gargalos", summary="Análise 7 — ranking de gargalos curriculares")
async def gargalos(
    filtros: Filtros = Depends(obter_filtros),
    limite: int = Query(default=10, ge=1, le=100),
    minimo_matriculas: int = Query(default=MINIMO_MATRICULAS_PADRAO, ge=1),
    agrupamento: str = Query(
        default="nome",
        pattern="^(nome|curso)$",
        description="'nome' agrega o campus; 'curso' separa por curso",
    ),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    """Ranking por **taxa** de reprovação, não por contagem absoluta.

    A proposta pedia "reprovação absoluta"; ordenar por contagem faria a lista
    medir tamanho de turma — os obrigatórios de primeira fase apareceriam
    sempre. O piso de matrículas evita que componentes de turma única dominem
    o topo por ruído.

    O denominador é o de matrículas **com resultado**: trancadas, canceladas e
    em curso não são aprovação nem reprovação (D-35). `total_matriculas` e o
    piso contam só essas.

    `codigos` devolve os `cod_ccr` reunidos em cada linha, para rastreabilidade.
    """
    dimensoes = AGRUPAMENTOS[agrupamento]
    projecao = ", ".join(dimensoes)
    where, parametros = filtros.clausula(*COLUNAS)
    reprovados = "sum(CASE WHEN resultado LIKE 'REPROVADO%' THEN qtd_matriculas ELSE 0 END)"
    sql = f"""
        SELECT
            {projecao},
            count(DISTINCT cod_ccr) AS n_codigos,
            string_agg(DISTINCT cod_ccr, ', ' ORDER BY cod_ccr) AS codigos,
            sum(qtd_matriculas) AS total_matriculas,
            {reprovados} AS reprovados,
            round(100.0 * {reprovados} / nullif(sum(qtd_matriculas), 0), 2) AS taxa_reprovacao
        FROM {deposito.tabela("visao3_desempenho")}
        {_com_resultado(where)}
        GROUP BY {projecao}
        HAVING sum(qtd_matriculas) >= ?
        ORDER BY taxa_reprovacao DESC, total_matriculas DESC
        LIMIT ?
    """
    return deposito.consultar(sql, [*parametros, minimo_matriculas, limite])


@roteador.get("/perfil-reprovacao", summary="Análise 9 — reprovação por nota vs. por frequência")
async def perfil_reprovacao(
    filtros: Filtros = Depends(obter_filtros),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    where, parametros = filtros.clausula(*COLUNAS)
    sql = f"""
        SELECT resultado, sum(qtd_matriculas) AS qtd
        FROM {deposito.tabela("visao3_desempenho")}
        {where}
        GROUP BY resultado
        ORDER BY qtd DESC
    """
    return deposito.consultar(sql, parametros)


@roteador.get("/frequencia-media", summary="Análise 8 — correlação entre frequência e média final")
async def frequencia_media(
    nome_ccr: str | None = Query(
        default=None,
        description="Restringe a um componente pelo nome; omitir para o agregado",
    ),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    """Filtra por **nome** do componente, não por código.

    Mesmo grão da Análise 7: um componente tem vários `cod_ccr` (versões da
    matriz e oferta por cursos distintos), e filtrar por código mostraria só
    um fragmento da disciplina.

    Este mart é binado por faixa de frequência e não carrega curso nem ano —
    por isso não usa os filtros globais.
    """
    where = "WHERE nome_ccr = ?" if nome_ccr else ""
    sql = f"""
        SELECT
            faixa_freq,
            sum(qtd_matriculas) AS qtd_matriculas,
            round(
                sum(media_final_media * qtd_matriculas) / nullif(sum(qtd_matriculas), 0), 2
            ) AS media_final_ponderada
        FROM {deposito.tabela("visao3_frequencia_media")}
        {where}
        GROUP BY faixa_freq
        ORDER BY faixa_freq
    """
    return deposito.consultar(sql, [nome_ccr] if nome_ccr else [])


# Recortes da Análise 11. Lista fechada: o valor escolhe a dimensão do GROUP BY.
AGRUPAMENTOS_MEDIA = {"curso": "curso", "ano": "ano"}


@roteador.get("/media-curso", summary="Análise 11 — média de notas por curso")
async def media_curso(
    filtros: Filtros = Depends(obter_filtros),
    agrupamento: str = Query(
        default="curso",
        pattern="^(curso|ano)$",
        description="'curso' compara os cursos no período; 'ano' mostra a evolução",
    ),
    deposito: Deposito = Depends(obter_deposito),
) -> list[dict[str, Any]]:
    """Média aritmética de `media_final` das matrículas com resultado (D-34).

    Entram aprovações e reprovações de qualquer causa, inclusive as notas zero
    de quem reprovou por nota e falta; ficam fora as matrículas sem resultado.
    O curso é o da turma, não o do estudante (A-33): a média do curso é a das
    notas lançadas nas turmas que o atendem.

    Calculada como soma das notas / número de notas, e não como média de
    médias, para que cada matrícula pese igual sob qualquer filtro.
    """
    dimensao = AGRUPAMENTOS_MEDIA[agrupamento]
    where, parametros = filtros.clausula(*COLUNAS)
    sql = f"""
        SELECT
            {dimensao},
            sum(qtd_com_nota) AS matriculas_com_nota,
            sum(CASE WHEN resultado = 'APROVADO' THEN qtd_matriculas ELSE 0 END) AS aprovados,
            round(sum(soma_media_final) / nullif(sum(qtd_com_nota), 0), 2) AS media
        FROM {deposito.tabela("visao3_desempenho")}
        {_com_resultado(where)}
        GROUP BY {dimensao}
        ORDER BY {"media DESC" if dimensao == "curso" else "ano"}
    """
    return deposito.consultar(sql, parametros)
