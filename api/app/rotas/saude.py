"""Rota de verificação de saúde — alvo do UptimeRobot a cada 5 minutos.

Fica fora da autenticação por API Key: o monitor precisa alcançá-la sem segredo,
e ela não expõe dado nenhum.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deposito import Deposito, obter_deposito

roteador = APIRouter(tags=["operação"])


# HEAD além de GET: o UptimeRobot consulta com HEAD por padrão, e uma rota só
# de GET responde 405 — o monitor acusa queda com a API saudável.
@roteador.api_route("/health", methods=["GET", "HEAD"], summary="Verificação de saúde")
async def health(deposito: Deposito = Depends(obter_deposito)) -> dict[str, str]:
    return {"status": "ok" if deposito.saudavel() else "degradado"}
