"""Barra lateral com os filtros globais (seção 4.3 da proposta).

Todos os blocos gráficos da tela principal se adaptam a partir do que esta
função devolve.

A proposta também previa filtragem cruzada por clique nos gráficos; a tentativa
de implementá-la esbarrou numa limitação do Streamlit (registro-decisoes.md,
L-10). Esta barra lateral é, portanto, o único mecanismo de filtro.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import streamlit as st

from cliente_api import buscar

ANO_MINIMO = 2010
ANO_MAXIMO = 2026

TODOS_OS_CURSOS = "Todos os cursos"


@dataclass(frozen=True)
class FiltrosGlobais:
    curso: str | None
    ano_inicio: int
    ano_fim: int
    semestre: int | None

    def como_parametros(self) -> dict[str, object]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def renderizar() -> FiltrosGlobais:
    st.sidebar.header("Filtros")

    try:
        cursos = buscar("/v1/demografia/cursos")
        opcoes = [TODOS_OS_CURSOS] + sorted(cursos["nome_curso"].unique().to_list())
    except Exception:  # noqa: BLE001 — API fora do ar não deve derrubar o painel
        st.sidebar.warning("Não foi possível carregar a lista de cursos.")
        opcoes = [TODOS_OS_CURSOS]

    escolhido = st.sidebar.selectbox("Curso", opcoes)
    curso = None if escolhido == TODOS_OS_CURSOS else escolhido

    ano_inicio, ano_fim = st.sidebar.slider(
        "Ano de ingresso", ANO_MINIMO, ANO_MAXIMO, (ANO_MINIMO, ANO_MAXIMO)
    )

    semestre_rotulo = st.sidebar.radio("Semestre de ingresso", ["Ambos", "1", "2"], horizontal=True)
    semestre = None if semestre_rotulo == "Ambos" else int(semestre_rotulo)

    st.sidebar.caption("Os filtros valem para as três visões simultaneamente.")

    return FiltrosGlobais(
        curso=curso, ano_inicio=ano_inicio, ano_fim=ano_fim, semestre=semestre
    )
