"""Visão 3 — Desempenho e gargalos curriculares (Análises 7, 8, 9 e 11)."""

from __future__ import annotations

import plotly.express as px
import polars as pl
import streamlit as st

from cliente_api import buscar
from componentes import tema
from componentes.filtros import FiltrosGlobais

# Frequência mínima exigida pela UFFS para aprovação, espelhando
# regras.FREQUENCIA_MINIMA (registro-decisoes, D-06).
FREQUENCIA_MINIMA = 75.0

# Um mesmo componente curricular aparece com vários `cod_ccr` — versões da
# matriz e oferta por cursos distintos. As duas agregações respondem a
# perguntas diferentes e ambas são oferecidas (registro-decisoes.md, D-27).
AGRUPAMENTOS = {
    "Por disciplina (campus)": "nome",
    "Por disciplina e curso": "curso",
}

# Componentes de trabalho de conclusão aparecem no ranking com outra cor: a
# reprovação neles não é comparável à das disciplinas de conteúdo (A-43, D-41).
# A classificação vem da API; o painel só desenha.
TIPO_DISCIPLINA = "Disciplina"
TIPO_TCC = "Trabalho de conclusão de curso"

ROTULOS_REPROVACAO = {
    "REPROVADO_NOTA": "Por nota",
    "REPROVADO_FREQUENCIA": "Por frequência",
    "REPROVADO_NOTA_E_FREQUENCIA": "Por nota e frequência",
}


def _formatar(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def renderizar(filtros: FiltrosGlobais) -> None:
    st.subheader("Desempenho e gargalos curriculares")
    st.caption("Fluxo pedagógico dentro das disciplinas, cruzando oferta de turmas e rendimento.")

    st.warning(
        "As bases não expõem identificador de estudante (anonimização LGPD). "
        "Portanto esta visão **não pode** ser cruzada com cota, gênero ou raça das Visões 1 e 2.",
        icon="⚠️",
    )

    parametros = filtros.como_parametros()

    gargalos = _analise_7(parametros)
    _analise_8(gargalos)
    _analise_9(parametros)
    _analise_11(parametros)


# --------------------------------------------------------------------- Análise 7
def _analise_7(parametros: dict) -> pl.DataFrame:
    st.markdown("#### Análise 7 — Ranking de gargalos curriculares")

    coluna_a, coluna_b = st.columns([2, 3])
    rotulo = coluna_a.radio(
        "Agrupar",
        list(AGRUPAMENTOS),
        key="desempenho_agrupamento",
        help=(
            "A mesma disciplina tem vários códigos, por causa das versões da "
            "matriz curricular e da oferta por cursos diferentes."
        ),
    )
    agrupamento = AGRUPAMENTOS[rotulo]
    minimo = coluna_b.slider(
        "Mínimo de matrículas com resultado",
        10,
        500,
        50,
        step=10,
        key="desempenho_minimo",
        help="Sem um piso, componentes de turma única dominam o topo por ruído estatístico.",
    )

    gargalos = buscar(
        "/v1/desempenho/gargalos",
        limite=10,
        minimo_matriculas=minimo,
        agrupamento=agrupamento,
        **parametros,
    )
    if gargalos.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return gargalos

    # O rótulo precisa dizer de qual curso se trata. No recorte por curso, é o
    # próprio curso da linha; no de campus, o curso com mais matrículas e,
    # se houver outros, quantos são — a lista completa vai no tooltip e na
    # tabela (D-40).
    # A coluna `cursos` só existe a partir da API com D-40; durante uma
    # implantação o painel pode chegar antes dela.
    tem_cursos = "cursos" in gargalos.columns
    if agrupamento == "curso":
        gargalos = gargalos.with_columns(
            (pl.col("nome_ccr") + pl.lit("  ·  ") + pl.col("curso")).alias("rotulo")
        )
    elif not tem_cursos:
        gargalos = gargalos.with_columns(pl.col("nome_ccr").alias("rotulo"))
    else:
        principal = pl.col("cursos").str.split(" (").list.first()
        outros = pl.col("n_cursos") - 1
        gargalos = gargalos.with_columns(
            pl.when(outros > 0)
            .then(
                pl.col("nome_ccr") + pl.lit("  ·  ") + principal
                + pl.lit(" e +") + outros.cast(pl.String)
            )
            .otherwise(pl.col("nome_ccr") + pl.lit("  ·  ") + principal)
            .alias("rotulo")
        )

    tem_marca_tcc = "e_trabalho_conclusao" in gargalos.columns
    gargalos = gargalos.with_columns(
        pl.when(pl.col("e_trabalho_conclusao") if tem_marca_tcc else pl.lit(False))
        .then(pl.lit(TIPO_TCC))
        .otherwise(pl.lit(TIPO_DISCIPLINA))
        .alias("tipo")
    )

    ordenado = gargalos.sort("taxa_reprovacao")
    dados_tooltip = ["codigos", "n_codigos", "total_matriculas", "reprovados"]
    if agrupamento == "nome" and tem_cursos:
        dados_tooltip.append("cursos")
    figura = px.bar(
        ordenado,
        x="taxa_reprovacao",
        y="rotulo",
        orientation="h",
        labels={
            "taxa_reprovacao": "Taxa de reprovação (%)",
            "rotulo": "",
            "cursos": "Cursos (matrículas)",
        },
        hover_data=dados_tooltip,
        text="taxa_reprovacao",
        color="tipo",
        color_discrete_map={
            TIPO_DISCIPLINA: tema.cores().categorica[0],
            TIPO_TCC: tema.cores().tinta_suave,
        },
        category_orders={"tipo": [TIPO_DISCIPLINA, TIPO_TCC]},
    )
    # Com duas séries, o Plotly ordenaria o eixo por série; a ordem é a da taxa.
    figura.update_yaxes(categoryorder="array", categoryarray=ordenado["rotulo"].to_list())
    figura.update_layout(legend_title_text="")
    figura.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
        cliponaxis=False,
    )
    tema.separar_barras(figura, arredondar=True)
    tema.aplicar(
        figura, altura=max(360, 30 * ordenado.height + 140), rotulos_externos=True
    )
    st.plotly_chart(figura, width="stretch")

    st.caption(
        "A proposta pedia o *ranking* por reprovação **absoluta**. Ordenar por "
        "contagem faria a lista medir tamanho de turma, não dificuldade: os "
        "obrigatórios de primeira fase apareceriam sempre. Aqui a ordenação é "
        "por taxa, com piso mínimo de matrículas. A taxa é reprovados sobre "
        "matrículas **com resultado**: trancamentos, cancelamentos e turmas em "
        "curso não contam como aprovação nem como reprovação."
    )

    reunidos = ordenado.filter(pl.col("n_codigos") > 1)
    if not reunidos.is_empty():
        st.caption(
            f"**{reunidos.height} das {ordenado.height} linhas reúnem mais de um "
            "código de CCR** — versões sucessivas da matriz curricular e, no "
            "recorte de campus, oferta por cursos diferentes. Sem essa união a "
            "mesma disciplina apareceria repetida no *ranking*, cada fragmento "
            "com uma taxa própria. Os códigos estão no *tooltip* e na tabela."
        )

    if (ordenado["tipo"] == TIPO_TCC).any():
        st.caption(
            "Em cinza, componentes de **trabalho de conclusão de curso**. A "
            "reprovação neles não é comparável à das disciplinas: cada curso "
            "organiza o trabalho de um jeito, e quem reprova costuma ter nota "
            "próxima de zero com frequência alta, o que indica trabalho não "
            "entregue no semestre. Leia-os no recorte por curso. No recorte de "
            "*campus*, um mesmo nome, como *Trabalho de Conclusão de Curso I*, "
            "reúne componentes diferentes de vários cursos."
        )

    if agrupamento == "nome" and tem_cursos:
        st.caption(
            "Ao lado de cada componente aparece o curso com mais matrículas nele. "
            "A lista completa, com as matrículas de cada curso, está no *tooltip* e "
            "na tabela. O curso é o **da turma**, e não o do estudante: as bases "
            "não informam o curso de quem se matricula. Uma turma que atende mais "
            "de um curso conta em cada um deles."
        )

    tabela = ordenado.sort("taxa_reprovacao", descending=True).drop(
        "rotulo", "e_trabalho_conclusao", strict=False
    )
    if agrupamento == "curso":
        tabela = tabela.drop("cursos", "n_cursos", strict=False)
    with st.expander("Ver tabela com os códigos e os cursos"):
        st.dataframe(
            tabela.rename(
                {
                    "nome_ccr": "Componente",
                    "codigos": "Códigos",
                    "n_codigos": "Nº de códigos",
                    "total_matriculas": "Matrículas com resultado",
                    "reprovados": "Reprovados",
                    "taxa_reprovacao": "Taxa (%)",
                    "n_cursos": "Nº de cursos",
                    "cursos": "Cursos (matrículas)",
                    "tipo": "Tipo",
                },
                strict=False,
            ),
            width="stretch",
            hide_index=True,
        )
    return gargalos


# --------------------------------------------------------------------- Análise 8
def _analise_8(gargalos: pl.DataFrame) -> None:
    st.markdown("#### Análise 8 — Correlação entre frequência e média final")

    opcoes = {"Todos os componentes": None}
    if not gargalos.is_empty():
        # `unique` porque no recorte por curso o mesmo componente aparece uma
        # vez por curso, e aqui o grão é o componente.
        for nome in gargalos["nome_ccr"].unique(maintain_order=True).to_list():
            opcoes[str(nome)] = nome

    escolhido = st.selectbox(
        "Componente curricular",
        list(opcoes),
        key="desempenho_ccr",
        help="A lista traz os gargalos da Análise 7.",
    )
    nome_ccr = opcoes[escolhido]

    dados = buscar("/v1/desempenho/frequencia-media", nome_ccr=nome_ccr)
    if dados.is_empty():
        st.info("Sem dados para o componente selecionado.")
        return

    cores = tema.cores()
    figura = px.scatter(
        dados,
        x="faixa_freq",
        y="media_final_ponderada",
        size="qtd_matriculas",
        labels={
            "faixa_freq": "Faixa de frequência (%)",
            "media_final_ponderada": "Média final ponderada",
            "qtd_matriculas": "Matrículas",
        },
        size_max=44,
    )
    figura.update_traces(
        marker=dict(
            color=cores.categorica[0],
            line=dict(color=cores.superficie, width=2),
            opacity=0.85,
        ),
        hovertemplate=(
            "Frequência %{x}–%{customdata[1]}%<br>Média %{y:.2f}"
            "<br>%{customdata[0]} matrículas<extra></extra>"
        ),
        customdata=dados.select(
            "qtd_matriculas", (pl.col("faixa_freq") + 5).alias("faixa_fim")
        ).to_numpy(),
    )
    figura.add_vline(
        x=FREQUENCIA_MINIMA,
        line_dash="dash",
        line_color=tema.STATUS["critico"],
        line_width=2,
        annotation_text=f"piso de {FREQUENCIA_MINIMA:.0f}%",
        annotation_position="top left",
        annotation_font_color=tema.STATUS["critico"],
    )
    tema.aplicar(figura, altura=420)
    figura.update_xaxes(dtick=10)
    figura.update_yaxes(rangemode="tozero")
    st.plotly_chart(figura, width="stretch")

    st.caption(
        "Cada ponto é uma faixa de 5 pontos percentuais de frequência; o tamanho "
        "é o volume de matrículas na faixa. O mart já vem agregado em faixas — a "
        "nuvem crua teria 431 mil pontos e não passaria pela API sem custo de "
        "latência. A linha tracejada marca a frequência mínima de 75% exigida "
        "para aprovação."
    )

    with st.expander("Ver tabela"):
        st.dataframe(
            dados.rename(
                {
                    "faixa_freq": "Faixa de frequência (%)",
                    "qtd_matriculas": "Matrículas",
                    "media_final_ponderada": "Média final ponderada",
                }
            ),
            width="stretch",
            hide_index=True,
        )


# --------------------------------------------------------------------- Análise 9
def _analise_9(parametros: dict) -> None:
    st.markdown("#### Análise 9 — Perfil qualitativo da reprovação")
    dados = buscar("/v1/desempenho/perfil-reprovacao", **parametros)
    if dados.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    reprovacoes = (
        dados.filter(pl.col("resultado").str.starts_with("REPROVADO"))
        .with_columns(
            pl.col("resultado")
            .replace_strict(ROTULOS_REPROVACAO, default="Outros")
            .alias("motivo")
        )
        .sort("qtd", descending=True)
    )
    if reprovacoes.is_empty():
        st.info("Nenhuma reprovação no recorte selecionado.")
        return

    # Denominador: só matrículas com resultado, como no ranking de gargalos e na
    # média por curso. Trancamento, cancelamento e turma em curso não são
    # aprovação nem reprovação (D-35, D-42).
    total_reprovacoes = int(reprovacoes["qtd"].sum())
    com_resultado = int(dados.filter(pl.col("resultado") != "NEUTRO")["qtd"].sum())
    a, b = st.columns(2)
    a.metric("Reprovações no recorte", _formatar(total_reprovacoes))
    b.metric(
        "Sobre as matrículas com resultado",
        f"{100 * total_reprovacoes / com_resultado:.1f}%" if com_resultado else "—",
    )

    com_percentual = reprovacoes.with_columns(
        (100 * pl.col("qtd") / total_reprovacoes).alias("participacao")
    )
    figura = px.bar(
        com_percentual.sort("qtd"),
        x="participacao",
        y="motivo",
        orientation="h",
        color="motivo",
        category_orders={"motivo": list(ROTULOS_REPROVACAO.values())},
        color_discrete_sequence=tema.cores().categorica,
        labels={"participacao": "Participação nas reprovações (%)", "motivo": ""},
        hover_data=["qtd"],
        text="participacao",
    )
    figura.update_traces(
        texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False
    )
    tema.separar_barras(figura, arredondar=True)
    tema.aplicar(figura, altura=340, rotulos_externos=True)
    figura.update_layout(showlegend=False)
    st.plotly_chart(figura, width="stretch")

    st.caption(
        "A proposta previa dividir a reprovação **estritamente** entre nota e "
        "frequência. A origem rotula explicitamente um terceiro caso — reprovação "
        "simultânea por nota **e** falta —, que costuma ser o mais frequente. "
        "Forçá-lo numa das duas categorias distorceria o indicador justamente no "
        "caso mais comum, então ele tem categoria própria."
    )
    st.caption(
        "A causa vem do rótulo da origem, que já a informa em 98,3% dos registros. "
        "O piso de frequência só é usado para desempatar os casos de `REPROVADO` "
        "sem qualificação."
    )

    with st.expander("Ver todos os resultados, não só as reprovações"):
        st.dataframe(
            dados.rename({"resultado": "Resultado", "qtd": "Matrículas"}),
            width="stretch",
            hide_index=True,
        )


# -------------------------------------------------------------------- Análise 11
def _analise_11(parametros: dict) -> None:
    st.markdown("#### Análise 11 — Média de notas por curso")
    st.caption(
        "Média das notas finais lançadas nas turmas que atendem cada curso, no "
        "período filtrado. Entram aprovações e reprovações de qualquer causa, "
        "inclusive as notas zero de quem reprovou por nota e falta. Trancamentos, "
        "cancelamentos e turmas em curso ficam de fora."
    )

    por_curso = buscar("/v1/desempenho/media-curso", agrupamento="curso", **parametros)
    por_ano = buscar("/v1/desempenho/media-curso", agrupamento="ano", **parametros)
    if por_curso.is_empty():
        st.info("Sem dados para os filtros selecionados.")
        return

    cores = tema.cores()

    ordenado = por_curso.sort("media")
    figura = px.bar(
        ordenado,
        x="media",
        y="curso",
        orientation="h",
        labels={"media": "Média final (0 a 10)", "curso": ""},
        hover_data=["matriculas_com_nota", "aprovados"],
        text="media",
    )
    figura.update_traces(
        marker_color=cores.categorica[0],
        texttemplate="%{text:.2f}",
        textposition="outside",
        cliponaxis=False,
    )
    tema.separar_barras(figura, arredondar=True)
    tema.aplicar(
        figura, altura=max(320, 28 * ordenado.height + 120), rotulos_externos=True
    )
    # Escala fixa de 0 a 10: médias de cursos diferentes ficam comparáveis
    # entre recortes, e a diferença não é exagerada por um eixo truncado.
    figura.update_xaxes(range=[0, 10])
    st.plotly_chart(figura, width="stretch")

    figura = px.line(
        por_ano,
        x="ano",
        y="media",
        markers=True,
        labels={"ano": "Ano letivo", "media": "Média final (0 a 10)"},
        hover_data=["matriculas_com_nota"],
    )
    figura.update_traces(
        line=dict(color=cores.categorica[0], width=2),
        marker=dict(size=7, line=dict(color=cores.superficie, width=2)),
    )
    tema.aplicar(figura, altura=320)
    figura.update_layout(title_text="Evolução da média no recorte, por ano letivo")
    figura.update_yaxes(range=[0, 10])
    figura.update_xaxes(dtick=1)
    st.plotly_chart(figura, width="stretch")

    with st.expander("Ver tabela"):
        st.dataframe(
            por_curso.rename(
                {
                    "curso": "Curso",
                    "matriculas_com_nota": "Matrículas com nota",
                    "aprovados": "Aprovações",
                    "media": "Média",
                }
            ),
            width="stretch",
            hide_index=True,
        )
