"""Paleta e estilo compartilhados dos gráficos do painel.

Centralizado para que os gráficos das três visões leiam como um sistema só, e
para que uma troca de identidade visual aconteça em um arquivo apenas.

Os valores vêm de uma paleta validada: a ordem das cores categóricas é o
mecanismo de segurança para daltonismo, não escolha estética — trocar a ordem
invalida a garantia. As duplas usadas no painel foram conferidas com o validador
da paleta (`ΔE` OKLab sob simulação de protanopia e deuteranopia):

- reentrada (azul × laranja): aprovado em todas as verificações;
- pilha de retenção (status): as cores de status ficam de propósito fora da
  banda de luminosidade das categóricas, e `#fab219` tem contraste 1,79 contra o
  fundo claro. A mitigação prevista é **rótulo direto mais legenda**, nunca cor
  sozinha — por isso os gráficos de retenção sempre trazem os dois, além da
  tabela equivalente.
"""

from __future__ import annotations

from dataclasses import dataclass

import plotly.graph_objects as go
import streamlit as st

FONTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# Ordem fixa. Nunca ciclar: uma 9ª série vira "Outros" ou um gráfico separado.
CATEGORICA_CLARA = [
    "#2a78d6",  # azul
    "#eb6834",  # laranja
    "#1baf7a",  # aqua
    "#eda100",  # amarelo
    "#e87ba4",  # magenta
    "#008300",  # verde
    "#4a3aa7",  # violeta
    "#e34948",  # vermelho
]
CATEGORICA_ESCURA = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
]

# Reservadas para estado. Nunca reaproveitar como "série 4".
STATUS = {
    "bom": "#0ca30c",
    "atencao": "#fab219",
    "serio": "#ec835a",
    "critico": "#d03b3b",
}


@dataclass(frozen=True)
class Cores:
    superficie: str
    tinta: str
    tinta_secundaria: str
    tinta_suave: str
    grade: str
    eixo: str
    categorica: list[str]


CLARO = Cores(
    superficie="#fcfcfb",
    tinta="#0b0b0b",
    tinta_secundaria="#52514e",
    tinta_suave="#898781",
    grade="#e1e0d9",
    eixo="#c3c2b7",
    categorica=CATEGORICA_CLARA,
)

ESCURO = Cores(
    superficie="#1a1a19",
    tinta="#ffffff",
    tinta_secundaria="#c3c2b7",
    tinta_suave="#898781",
    grade="#2c2c2a",
    eixo="#383835",
    categorica=CATEGORICA_ESCURA,
)


def _modo_escuro() -> bool:
    """Descobre o tema ativo do Streamlit, com degradação segura para claro.

    O tema declarado em `.streamlit/config.toml` tem precedência. Com ele fixo
    em claro (D-37), `st.context.theme` continua informando a preferência do
    sistema operacional do visitante: medido no Streamlit 1.52.2, quem prefere o
    escuro recebia página clara com gráficos escuros e legenda ilegível.
    """
    try:
        base = st.get_option("theme.base")
        if base in ("light", "dark"):
            return base == "dark"
    except Exception:  # noqa: BLE001 — opção ausente em versões antigas
        pass
    try:
        tema = st.context.theme
        if tema is not None and getattr(tema, "type", None):
            return tema.type == "dark"
    except Exception:  # noqa: BLE001 — API de tema varia entre versões
        pass
    return False


def cores() -> Cores:
    return ESCURO if _modo_escuro() else CLARO


# Largura reservada à direita para o rótulo de valor de uma barra horizontal
# ("100.0%" na fonte do tema cabe em ~45 px).
MARGEM_ROTULO_EXTERNO = 56


def aplicar(
    figura: go.Figure, *, altura: int | None = None, rotulos_externos: bool = False
) -> go.Figure:
    """Estilo comum: superfície, tintas, grade recessiva e legenda no topo.

    `rotulos_externos` é para barras horizontais com o valor escrito depois da
    barra: reserva margem fixa à direita. Sem ela o rótulo da barra mais longa
    depende da folga do eixo, que é proporcional à largura do gráfico, e é
    cortado em janelas estreitas.
    """
    c = cores()
    figura.update_layout(
        paper_bgcolor=c.superficie,
        plot_bgcolor=c.superficie,
        font=dict(family=FONTE, color=c.tinta_secundaria, size=13),
        margin=dict(l=8, r=MARGEM_ROTULO_EXTERNO if rotulos_externos else 8, t=48, b=8),
        hoverlabel=dict(font_family=FONTE),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title_text="",
            bgcolor="rgba(0,0,0,0)",
        ),
        colorway=c.categorica,
    )
    if altura:
        figura.update_layout(height=altura)

    # Grade e eixos recessivos: a tinta forte fica para os dados.
    figura.update_xaxes(
        gridcolor=c.grade, zerolinecolor=c.eixo, linecolor=c.eixo, tickfont_color=c.tinta_suave
    )
    figura.update_yaxes(
        gridcolor=c.grade, zerolinecolor=c.eixo, linecolor=c.eixo, tickfont_color=c.tinta_suave
    )
    return figura


def separar_barras(figura: go.Figure, *, arredondar: bool = False) -> go.Figure:
    """Contorno na cor da superfície: cria o respiro de 2px entre preenchimentos.

    `arredondar` só vale para barras simples — numa pilha, arredondar cada
    segmento descola a série da linha de base e atrapalha a leitura.
    """
    c = cores()
    figura.update_traces(marker_line_color=c.superficie, marker_line_width=2)
    if arredondar:
        figura.update_traces(marker_cornerradius=4)
    return figura
