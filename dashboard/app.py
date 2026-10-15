"""Painel analítico — Indicadores de Trajetória Discente, UFFS Campus Chapecó.

Execução local:  streamlit run dashboard/app.py
Produção:        Streamlit Community Cloud, arquivo principal `dashboard/app.py`
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from cliente_api import verificar_saude
from componentes.filtros import renderizar as renderizar_filtros
from visoes import demografia, desempenho, fluxo

st.set_page_config(
    page_title="Indicadores de Trajetória Discente — UFFS Chapecó",
    page_icon="🎓",
    layout="wide",
)

# Assinatura visual do campus, conforme o Manual de Identidade Visual da UFFS
# (fev. 2017): a versão em branco dentro do retângulo verde é a admitida tanto
# sobre fundo claro quanto sobre fundo escuro, então serve aos dois temas.
st.sidebar.image(
    str(Path(__file__).parent / "static" / "uffs_campus_chapeco_fundo_verde.png"),
    width="stretch",
)

st.title("Indicadores de Trajetória Discente")
st.caption(
    "Universidade Federal da Fronteira Sul — Campus Chapecó · Dados Abertos institucionais. "
    "Projeto acadêmico de Trabalho de Conclusão de Curso; **não é um sistema oficial da UFFS**."
)

if not verificar_saude():
    st.error(
        "A camada de serviço não respondeu. No plano gratuito do Render o primeiro "
        "acesso após inatividade pode levar até um minuto (cold start). Recarregue a página.",
        icon="🔌",
    )
    st.stop()

filtros = renderizar_filtros()

aba_demografia, aba_fluxo, aba_desempenho = st.tabs(
    [
        "1 · Demografia e ingresso",
        "2 · Fluxo acadêmico",
        "3 · Desempenho e gargalos",
    ]
)

with aba_demografia:
    demografia.renderizar(filtros)

with aba_fluxo:
    fluxo.renderizar(filtros)

with aba_desempenho:
    desempenho.renderizar(filtros)

st.divider()
st.caption(
    "Fonte: Portal de Dados Abertos da UFFS (dados.uffs.edu.br). "
    "TCC — Ciência da Computação · Marco Aurélio Lunardi · Orientadora: Profª Raquel Aparecida Pegoraro."
)
