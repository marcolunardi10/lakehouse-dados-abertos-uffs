"""Visão 1 — Retrato demográfico e ingresso (Análises 1, 2 e 3)."""

from __future__ import annotations

import plotly.express as px
import polars as pl
import streamlit as st

from cliente_api import buscar
from componentes import tema
from componentes.filtros import FiltrosGlobais

# Acima disso o gráfico vira sopa de cores e a paleta perde a garantia de
# distinção: o excedente é agrupado em "Outras formas".
MAXIMO_FORMAS = 6

# A origem trocou os rótulos de forma de ingresso na migração SGA -> SIGAA.
# Ver registro-decisoes.md, A-10 e L-07.
ANO_TROCA_ROTULOS = 2023


def renderizar(filtros: FiltrosGlobais) -> None:
    st.subheader("Retrato demográfico e ingresso")
    st.caption(
        "Perfil socioeconômico e representatividade do corpo discente que ingressa no campus."
    )

    parametros = filtros.como_parametros()

    _analise_1(parametros)
    _analise_2(parametros)
    _analise_3(parametros)


# Ordem fixa dos grupos na Análise 1, para que cada um mantenha a sua cor
# qualquer que seja o filtro.
ORDEM_GRUPOS_COTA = ["AMPLA CONCORRENCIA", "NAO SE APLICA", "ACAO AFIRMATIVA"]


def _participacao(dados: pl.DataFrame, dimensao: str) -> pl.DataFrame:
    """Reagrega por ano e converte para participação percentual no ano.

    O mart vem cruzado por gênero E raça ao mesmo tempo; cada análise precisa
    somar por cima da dimensão que não lhe interessa.
    """
    return (
        dados.group_by("ano_ingresso", dimensao)
        .agg(pl.col("qtd").sum())
        .with_columns(
            (100 * pl.col("qtd") / pl.col("qtd").sum().over("ano_ingresso")).alias("participacao")
        )
        .sort("ano_ingresso", dimensao)
    )


def _ordem_por_volume(dados: pl.DataFrame, dimensao: str) -> list[str]:
    """Categorias da maior para a menor, para que as cores caiam em ordem fixa."""
    return (
        dados.group_by(dimensao)
        .agg(pl.col("qtd").sum())
        .sort("qtd", descending=True)[dimensao]
        .to_list()
    )


# --------------------------------------------------------------------- Análise 1
def _analise_1(parametros: dict) -> None:
    st.markdown("#### Análise 1 — Distribuição de ingressantes por modalidade de cota")
    cotas = buscar("/v1/demografia/cotas", **parametros)
    if cotas.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    # A rota devolve uma linha por código de cota. Empilhar essas linhas direto
    # faria de cada código um segmento à parte dentro da mesma cor, e o valor
    # mostrado ao passar o mouse seria o do código, não o do grupo — a ação
    # afirmativa apareceria como vários números pequenos ao lado de um só da
    # ampla concorrência. O gráfico soma por grupo; o código fica na tabela.
    por_grupo = (
        cotas.group_by("ano_ingresso", "grupo_modalidade")
        .agg(pl.col("qtd").sum())
        .sort("ano_ingresso", "grupo_modalidade")
    )
    figura = px.bar(
        por_grupo,
        x="ano_ingresso",
        y="qtd",
        color="grupo_modalidade",
        color_discrete_sequence=tema.cores().categorica,
        category_orders={"grupo_modalidade": ORDEM_GRUPOS_COTA},
        labels={
            "ano_ingresso": "Ano de ingresso",
            "qtd": "Ingressantes",
            "grupo_modalidade": "Modalidade",
        },
    )
    tema.separar_barras(figura)
    tema.aplicar(figura, altura=420)
    figura.update_layout(barmode="stack", hovermode="x unified")
    st.plotly_chart(figura, width="stretch")

    st.caption(
        "`AC` é ampla concorrência; `N/A` marca formas de ingresso sem cota — não é "
        "dado faltante. Os códigos convivem em três gerações: `L1`–`L14` da Lei "
        "12.711/2012, `LB_*`/`LI_*` da Lei 14.723/2023 e `A1`/`A2` institucionais."
    )

    with st.expander("Detalhamento por código de cota"):
        st.dataframe(
            cotas.pivot(
                on="modalidade_inscricao",
                index="ano_ingresso",
                values="qtd",
                aggregate_function="sum",
            )
            .fill_null(0)
            .sort("ano_ingresso"),
            width="stretch",
            hide_index=True,
        )


# --------------------------------------------------------------------- Análise 2
def _analise_2(parametros: dict) -> None:
    st.markdown("#### Análise 2 — Evolução histórica de gênero e raça")
    dados = buscar("/v1/demografia/genero-raca", **parametros)
    if dados.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    st.caption(
        "Participação percentual no total de ingressantes de cada ano — e não "
        "volume absoluto, que acompanharia o tamanho das turmas e esconderia a "
        "mudança de composição."
    )

    esquerda, direita = st.columns(2)
    for coluna, dimensao, titulo in (
        (esquerda, "genero", "Gênero"),
        (direita, "raca", "Raça"),
    ):
        serie = _participacao(dados, dimensao)
        figura = px.area(
            serie,
            x="ano_ingresso",
            y="participacao",
            color=dimensao,
            category_orders={dimensao: _ordem_por_volume(dados, dimensao)},
            color_discrete_sequence=tema.cores().categorica,
            labels={"ano_ingresso": "", "participacao": "Participação (%)", dimensao: titulo},
        )
        figura.update_traces(line_width=2, hovertemplate="%{y:.1f}%<extra></extra>")
        tema.aplicar(figura, altura=380)
        figura.update_layout(title_text=titulo, hovermode="x unified")
        figura.update_yaxes(range=[0, 100])
        coluna.plotly_chart(figura, width="stretch")

    st.caption(
        "As categorias de raça são as da origem e **divergem da nomenclatura do "
        "IBGE** (`Negro` em vez de `Preto`, `Indígeno` em vez de `Indígena`). "
        "Foram preservadas como publicadas; qualquer tradução precisa ser "
        "declarada. `genero` só admite `F` e `M` na fonte."
    )

    with st.expander("Ver tabelas"):
        for dimensao, titulo in (("genero", "Gênero"), ("raca", "Raça")):
            st.markdown(f"**{titulo}**")
            st.dataframe(
                _participacao(dados, dimensao)
                .with_columns(pl.col("participacao").round(1))
                .pivot(on=dimensao, index="ano_ingresso", values="participacao")
                .fill_null(0)
                .sort("ano_ingresso"),
                width="stretch",
                hide_index=True,
            )


# --------------------------------------------------------------------- Análise 3
def _analise_3(parametros: dict) -> None:
    st.markdown("#### Análise 3 — Mapeamento das formas de ingresso")
    dados = buscar("/v1/demografia/formas-ingresso", **parametros)
    if dados.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    principais = _ordem_por_volume(dados, "forma_ingresso")[:MAXIMO_FORMAS]
    agrupado = (
        dados.with_columns(
            pl.when(pl.col("forma_ingresso").is_in(principais))
            .then(pl.col("forma_ingresso"))
            .otherwise(pl.lit("Outras formas"))
            .alias("forma")
        )
        .group_by("ano_ingresso", "forma")
        .agg(pl.col("qtd").sum())
        .sort("ano_ingresso")
    )

    figura = px.bar(
        agrupado,
        x="ano_ingresso",
        y="qtd",
        color="forma",
        category_orders={"forma": principais + ["Outras formas"]},
        color_discrete_sequence=tema.cores().categorica,
        labels={"ano_ingresso": "Ano de ingresso", "qtd": "Ingressantes", "forma": "Forma"},
    )
    tema.separar_barras(figura)
    tema.aplicar(figura, altura=440)
    figura.update_layout(barmode="stack", hovermode="x unified")

    # A descontinuidade de rótulos é um artefato do sistema de origem, não uma
    # mudança de comportamento — precisa estar visível no gráfico.
    anos = agrupado["ano_ingresso"]
    if anos.max() is not None and int(anos.max()) >= ANO_TROCA_ROTULOS:
        figura.add_vrect(
            x0=ANO_TROCA_ROTULOS - 0.5,
            x1=int(anos.max()) + 0.5,
            fillcolor=tema.cores().tinta_suave,
            opacity=0.12,
            line_width=0,
            annotation_text="troca de rótulos SGA → SIGAA",
            annotation_position="top left",
            annotation_font_color=tema.cores().tinta_suave,
        )
    st.plotly_chart(figura, width="stretch")

    st.warning(
        "`ENEM` zera exatamente quando `SISU` e `PROCESSO SELETIVO SIMPLIFICADO` "
        "aparecem, na migração para o SIGAA. **Não é possível saber, apenas pelos "
        "dados, se houve mudança real na política de ingresso ou apenas renomeação "
        "de rótulo** — a leitura da série ao longo desse corte exige confirmação "
        "institucional.",
        icon="⚠️",
    )

    if len(principais) < dados["forma_ingresso"].n_unique():
        restantes = dados["forma_ingresso"].n_unique() - len(principais)
        st.caption(
            f"As {restantes} formas de menor volume foram agrupadas em "
            "«Outras formas»; a tabela abaixo traz todas."
        )

    with st.expander("Ver todas as formas de ingresso"):
        st.dataframe(
            dados.pivot(
                on="forma_ingresso", index="ano_ingresso", values="qtd", aggregate_function="sum"
            )
            .fill_null(0)
            .sort("ano_ingresso"),
            width="stretch",
            hide_index=True,
        )
