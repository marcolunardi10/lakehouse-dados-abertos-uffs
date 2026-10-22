"""Barra lateral com os filtros globais (seção 4.3 da proposta).

Todos os blocos gráficos da tela principal se adaptam a partir do que esta
função devolve.

A proposta também previa filtragem cruzada por clique nos gráficos; a tentativa
de implementá-la esbarrou numa limitação do Streamlit (registro-decisoes.md,
L-10). Esta barra lateral é, portanto, o único mecanismo de filtro.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

import streamlit as st

from cliente_api import buscar

ANO_MINIMO = 2010
# O limite do controle acompanha o calendário, mas nunca recua de 2026, último
# ano presente na data de corte do TCC. Com o controle encostado num extremo, o
# filtro não é enviado à API (ver `renderizar`), então nenhum ano fica de fora
# por causa deste número (D-39).
ANO_MAXIMO = max(2026, date.today().year)

TODOS_OS_CURSOS = "Todos os cursos"


@dataclass(frozen=True)
class FiltrosGlobais:
    curso: str | None
    ano_inicio: int | None
    ano_fim: int | None
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

    # O mesmo controle filtra coisas diferentes conforme a visão: o ingresso nas
    # Visões 1 e 2, cujo grão é o vínculo, e o período letivo da turma na Visão
    # 3, cujo grão é a matrícula. O rótulo não pode prometer só o primeiro.
    ano_inicio, ano_fim = st.sidebar.slider(
        "Ano", ANO_MINIMO, ANO_MAXIMO, (ANO_MINIMO, ANO_MAXIMO)
    )
    semestre_rotulo = st.sidebar.radio("Semestre", ["Ambos", "1", "2"], horizontal=True)
    semestre = None if semestre_rotulo == "Ambos" else int(semestre_rotulo)

    st.sidebar.caption(
        "Os filtros valem para as três visões. Nas Visões 1 e 2, ano e semestre são "
        "os de **ingresso**; na Visão 3, os do **período letivo** das turmas."
    )

    # Extremos do controle significam "sem limite": assim um ano que ainda não
    # existia quando o controle foi desenhado não é descartado em silêncio.
    return FiltrosGlobais(
        curso=curso,
        ano_inicio=None if ano_inicio == ANO_MINIMO else ano_inicio,
        ano_fim=None if ano_fim == ANO_MAXIMO else ano_fim,
        semestre=semestre,
    )
