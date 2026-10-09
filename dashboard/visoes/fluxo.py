"""Visão 2 — Fluxo acadêmico: evasão de curso e retenção.

Nomenclatura: o que se mede aqui é **evasão de curso**, não evasão
institucional. O grão do dado é o vínculo estudante-curso, não a pessoa — quem
troca de curso aparece como um cancelamento mais um vínculo novo. Ver
`docs/registro-decisoes.md`, D-10 e L-02.
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st

from cliente_api import buscar
from componentes import tema
from componentes.filtros import FiltrosGlobais

# Fração de vínculos ainda ativos a partir da qual a coorte é jovem demais para
# ter uma taxa de evasão comparável às antigas.
LIMIAR_COORTE_IMATURA = 0.20

PROGRESSAO = {
    "no_prazo": ("No prazo", tema.STATUS["bom"]),
    "em_retencao": ("Em retenção", tema.STATUS["atencao"]),
    "risco_jubilamento": ("Risco de jubilamento", tema.STATUS["critico"]),
}


def _formatar(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


# NOTA sobre filtragem cruzada (seção 4.2.7 da proposta):
# tentou-se acionar o filtro global clicando numa barra de curso, via
# `st.plotly_chart(on_select='rerun')`. Em 19/09/2026, com Streamlit 1.52.2 e
# Plotly 6.4.0, a seleção acontece visualmente no gráfico (a barra destaca, as
# demais esmaecem) mas **o evento não chega ao servidor**: nenhum *rerun* é
# disparado e nenhuma exceção é registrada. Foram testadas quatro combinações
# de `clickmode`, `dragmode` e `selection_mode`. Ver registro-decisoes.md, L-10.
# O filtro de curso continua na barra lateral, que funciona e cobre o caso de uso.


def renderizar(filtros: FiltrosGlobais) -> None:
    st.subheader("Fluxo acadêmico — evasão de curso e retenção")
    st.caption(
        "Diagnóstico quantitativo dos pontos de evasão e do atraso na integralização."
    )

    parametros = filtros.como_parametros()
    cores = tema.cores()

    _analise_4(parametros, cores)
    _reentrada(parametros)
    _analise_5(parametros)
    _analise_6(parametros, cores)
    _analise_10(parametros)


# --------------------------------------------------------------------- Análise 4
def _analise_4(parametros: dict, cores: tema.Cores) -> None:
    st.markdown("#### Análise 4 — Taxa de evasão de curso, por curso")
    dados = buscar("/v1/fluxo/evasao-curso", **parametros)
    if dados.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    total = int(dados["total_ingressantes"].sum())
    evadidos = int(dados["evadidos"].sum())
    a, b, c = st.columns(3)
    a.metric("Vínculos no recorte", _formatar(total))
    b.metric("Evadidos", _formatar(evadidos))
    c.metric("Taxa de evasão de curso", f"{100 * evadidos / total:.1f}%" if total else "—")

    ordenado = dados.sort("taxa_evasao")
    figura = px.bar(
        ordenado,
        x="taxa_evasao",
        y="nome_curso",
        orientation="h",
        labels={"taxa_evasao": "Taxa de evasão de curso (%)", "nome_curso": ""},
        hover_data=["total_ingressantes", "evadidos", "concluidos", "ativos"],
        text="taxa_evasao",
    )
    # Série única: sem legenda — o título já diz o que é.
    figura.update_traces(
        marker_color=cores.categorica[0],
        texttemplate="%{text:.1f}%",
        textposition="outside",
        textfont_color=cores.tinta_secundaria,
        cliponaxis=False,
    )
    tema.separar_barras(figura, arredondar=True)
    tema.aplicar(figura, altura=460)
    figura.update_xaxes(range=[0, max(100, ordenado["taxa_evasao"].max() * 1.15)])
    st.plotly_chart(figura, width="stretch")


# ------------------------------------------------------------------- Reentradas
def _reentrada(parametros: dict) -> None:
    st.markdown("#### Evasão de curso não é evasão da universidade")
    dados = buscar("/v1/fluxo/evasao-reentrada", **parametros)
    if dados.is_empty():
        return

    dados = dados.with_columns(
        pl.when(pl.col("e_reentrada"))
        .then(pl.lit("Reentrada na UFFS"))
        .otherwise(pl.lit("Primeiro ingresso"))
        .alias("grupo")
    ).sort("e_reentrada")

    reentradas = int(
        dados.filter(pl.col("e_reentrada"))["total_ingressantes"].sum()
    )
    total = int(dados["total_ingressantes"].sum())

    st.caption(
        f"**{_formatar(reentradas)} dos {_formatar(total)} vínculos "
        f"({100 * reentradas / total:.1f}%)** vêm de transferência interna, retorno de "
        "graduado ou retorno após abandono — ou seja, não são o primeiro ingresso na "
        "instituição. A evasão institucional é, portanto, estritamente menor que a de "
        "curso, mas não é calculável: as bases não expõem identificador de estudante."
    )

    figura = px.bar(
        dados,
        x="grupo",
        y="taxa_evasao",
        color="grupo",
        # `colorway` do layout não vale aqui: o px já fixa a cor de cada traço
        # quando se usa `color=`. A sequência precisa ser passada na criação.
        color_discrete_sequence=tema.cores().categorica,
        labels={"taxa_evasao": "Taxa de evasão de curso (%)", "grupo": ""},
        hover_data=["total_ingressantes", "evadidos", "ativos"],
        text="taxa_evasao",
    )
    figura.update_traces(
        texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False
    )
    tema.separar_barras(figura, arredondar=True)
    tema.aplicar(figura, altura=320)
    # Duas categorias ocupando a largura toda viram blocos enormes.
    figura.update_layout(showlegend=False, bargap=0.6)
    figura.update_yaxes(rangemode="tozero")
    st.plotly_chart(figura, width="stretch")


# --------------------------------------------------------------------- Análise 5
def _analise_5(parametros: dict) -> None:
    st.markdown("#### Análise 5 — Evasão comparada por modalidade de ingresso")
    dados = buscar("/v1/fluxo/evasao-cota", **parametros)
    if dados.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    # Modalidades com poucos vínculos produzem taxas instáveis (uma saída move
    # dezenas de pontos). O corte fica visível em vez de silencioso.
    minimo = st.slider(
        "Mínimo de vínculos para a modalidade aparecer",
        min_value=10,
        max_value=500,
        value=50,
        step=10,
        help="Modalidades com poucos vínculos geram taxas muito instáveis.",
        key="fluxo_minimo_cota",
    )
    visivel = dados.filter(pl.col("total_ingressantes") >= minimo).sort("taxa_evasao")
    ocultas = dados.height - visivel.height

    if visivel.is_empty():
        st.info("Nenhuma modalidade atinge o mínimo escolhido.")
        return

    figura = px.bar(
        visivel,
        x="taxa_evasao",
        y="modalidade_inscricao",
        orientation="h",
        labels={"taxa_evasao": "Taxa de evasão de curso (%)", "modalidade_inscricao": ""},
        hover_data=["total_ingressantes", "evadidos", "concluidos", "ativos"],
        text="taxa_evasao",
    )
    figura.update_traces(
        marker_color=tema.cores().categorica[0],
        texttemplate="%{text:.1f}%",
        textposition="outside",
        cliponaxis=False,
    )
    tema.separar_barras(figura, arredondar=True)
    tema.aplicar(figura, altura=max(320, 28 * visivel.height + 120))
    st.plotly_chart(figura, width="stretch")

    if ocultas:
        st.caption(f"{ocultas} modalidade(s) abaixo do mínimo, ocultadas.")
    st.caption(
        "`AC` é ampla concorrência; `N/A` marca formas de ingresso sem cota, não "
        "dado faltante. Os códigos convivem em três gerações: `L1`–`L14` da Lei "
        "12.711/2012, `LB_*`/`LI_*` da Lei 14.723/2023 e `A1`/`A2` institucionais."
    )


# --------------------------------------------------------------------- Análise 6
def _analise_6(parametros: dict, cores: tema.Cores) -> None:
    st.markdown("#### Análise 6 — Evasão por coorte de ingresso")
    dados = buscar("/v1/fluxo/curva-evasao", **parametros)
    if dados.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    dados = dados.sort("ano_ingresso").with_columns(
        (pl.col("ativos") / pl.col("total_ingressantes")).alias("fracao_ativos")
    )

    figura = go.Figure()
    figura.add_trace(
        go.Scatter(
            x=dados["ano_ingresso"],
            y=dados["taxa_evasao"],
            mode="lines+markers",
            name="Taxa de evasão de curso",
            line=dict(color=cores.categorica[0], width=2),
            marker=dict(size=8, line=dict(color=cores.superficie, width=2)),
            hovertemplate=(
                "Coorte %{x}<br>Evasão %{y:.1f}%"
                "<br>Vínculos %{customdata[0]}<br>Ainda ativos %{customdata[1]}<extra></extra>"
            ),
            customdata=dados[["total_ingressantes", "ativos"]].to_numpy(),
        )
    )

    # Coortes jovens ainda têm muita gente cursando: a taxa é estruturalmente
    # menor e não é comparável às antigas. A faixa vem dos dados, não de uma
    # regra fixa de anos.
    imaturas = dados.filter(pl.col("fracao_ativos") > LIMIAR_COORTE_IMATURA)
    if not imaturas.is_empty():
        inicio = int(imaturas["ano_ingresso"].min())
        fim = int(dados["ano_ingresso"].max())
        figura.add_vrect(
            x0=inicio - 0.5,
            x1=fim + 0.5,
            fillcolor=cores.tinta_suave,
            opacity=0.12,
            line_width=0,
            annotation_text="coortes ainda em curso",
            annotation_position="top left",
            annotation_font_color=cores.tinta_suave,
        )

    tema.aplicar(figura, altura=400)
    figura.update_layout(showlegend=False, hovermode="x unified")
    figura.update_yaxes(title_text="Taxa de evasão de curso (%)", rangemode="tozero")
    figura.update_xaxes(title_text="Ano de ingresso", dtick=1)
    st.plotly_chart(figura, width="stretch")

    st.caption(
        "A proposta previa o percentual acumulado de abandono **ao longo dos "
        "semestres** de cada coorte. Isso não é computável: `sit_matricula` "
        "registra a situação atual do vínculo e nenhuma coluna diz **quando** o "
        "estudante saiu. O que se compara aqui é a taxa final de cada coorte. "
        "A faixa sombreada marca as coortes com mais de "
        f"{LIMIAR_COORTE_IMATURA:.0%} dos vínculos ainda ativos — a queda ali é "
        "efeito do tempo, não melhora de retenção."
    )


# -------------------------------------------------------------------- Análise 10
def _analise_10(parametros: dict) -> None:
    st.markdown("#### Análise 10 — Retenção frente ao prazo de integralização")
    dados = buscar("/v1/fluxo/retencao", **parametros)
    if dados.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    em_retencao = int(dados["em_retencao"].sum())
    risco = int(dados["risco_jubilamento"].sum())
    sem_parametro = int(dados["sem_parametro"].sum())
    com_parametro = int(dados["ativos_com_parametro"].sum())

    a, b, c = st.columns(3)
    a.metric("Em retenção", _formatar(em_retencao))
    b.metric("Risco de jubilamento", _formatar(risco))
    c.metric(
        "Atraso entre os ativos",
        f"{100 * (em_retencao + risco) / com_parametro:.1f}%" if com_parametro else "—",
    )

    com_ativos = dados.filter(pl.col("ativos_com_parametro") > 0)
    if com_ativos.is_empty():
        st.info("Nenhum vínculo ativo com currículo identificado no recorte.")
    else:
        ordenado = com_ativos.sort("taxa_atraso")
        figura = go.Figure()
        for coluna, (rotulo, cor) in PROGRESSAO.items():
            figura.add_trace(
                go.Bar(
                    y=ordenado["nome_curso"],
                    x=ordenado[coluna],
                    name=rotulo,
                    orientation="h",
                    marker_color=cor,
                    hovertemplate=f"%{{y}}<br>{rotulo}: %{{x}}<extra></extra>",
                )
            )
        # Pilha de status: legenda sempre presente e rótulo direto no total, para
        # que a identidade nunca dependa só da cor (o amarelo de atenção tem
        # contraste baixo contra o fundo claro, por desenho da paleta).
        tema.separar_barras(figura)
        tema.aplicar(figura, altura=max(360, 30 * ordenado.height + 140))
        figura.update_layout(barmode="stack")
        figura.update_xaxes(title_text="Vínculos ativos")
        figura.update_yaxes(title_text="")
        st.plotly_chart(figura, width="stretch")

    st.caption(
        "Prazos vindos de `estruturas_curriculares_graduacao`, publicados pela "
        "UFFS — não são estimados. **Em retenção** é o vínculo ativo que passou "
        "da duração prevista; **risco de jubilamento**, o que passou de 80% do "
        "prazo máximo de integralização. Esse corte de 80% é escolha do painel, "
        "sem norma institucional por trás."
    )

    if sem_parametro:
        st.caption(
            f"**{_formatar(sem_parametro)} vínculos ativos sem parâmetro** — cursos "
            "ausentes da base de matrizes curriculares, portanto sem duração "
            "publicada. Aparecem aqui em vez de serem descartados em silêncio."
        )

    with st.expander("Ver tabela"):
        st.dataframe(
            dados.rename(
                {
                    "nome_curso": "Curso",
                    "ativos_com_parametro": "Ativos",
                    "no_prazo": "No prazo",
                    "em_retencao": "Em retenção",
                    "risco_jubilamento": "Risco de jubilamento",
                    "sem_parametro": "Sem parâmetro",
                    "semestres_previstos": "Semestres previstos",
                    "semestres_limite": "Limite",
                    "taxa_atraso": "Atraso (%)",
                }
            ),
            width="stretch",
            hide_index=True,
        )

