"""Rota de verificação de saúde — alvo do UptimeRobot a cada 5 minutos.

Fica fora da autenticação por API Key: o monitor precisa alcançá-la sem segredo,
e ela não expõe dado nenhum.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deposito import Deposito, obter_deposito

roteador = APIRouter(tags=["operação"])


@roteador.get("/health", summary="Verificação de saúde")
async def health(deposito: Deposito = Depends(obter_deposito)) -> dict[str, str]:
    return {"status": "ok" if deposito.saudavel() else "degradado"}
