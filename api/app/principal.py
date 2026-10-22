"""Aplicação FastAPI — camada de serviço headless BI.

Local:  uvicorn app.principal:app --reload --app-dir api
Render: uvicorn app.principal:app --host 0.0.0.0 --port $PORT --app-dir api
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deposito import obter_deposito
from .rotas import demografia, desempenho, fluxo, saude
from .seguranca import exigir_api_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # Cache warming: paga a latência do R2 no boot, não na primeira consulta do gestor.
    obter_deposito().aquecer()
    yield
    obter_deposito().fechar()


app = FastAPI(
    title="Indicadores de Trajetória Discente — UFFS Chapecó",
    description=(
        "Camada de serviço do pipeline analítico sobre os Dados Abertos da UFFS. "
        "Os data marts da camada Gold são lidos do Cloudflare R2 e mantidos em "
        "memória no DuckDB, que responde às consultas. Rotas de dados exigem o "
        "cabeçalho X-API-Key."
    ),
    version="0.1.0",
    lifespan=ciclo_de_vida,
)

# O painel Streamlit roda em outro domínio (Streamlit Community Cloud).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["X-API-Key"],
)

# /health fica sem autenticação: é o alvo do UptimeRobot.
app.include_router(saude.roteador)

for roteador in (demografia.roteador, fluxo.roteador, desempenho.roteador):
    app.include_router(roteador, dependencies=[Depends(exigir_api_key)])
