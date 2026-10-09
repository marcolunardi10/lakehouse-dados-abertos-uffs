"""Autenticação entre microsserviços por API Key (seção 4.2.3.2 da proposta)."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from .config import obter_config


async def exigir_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Protege as rotas de dados. `/health` fica de fora, para o UptimeRobot."""
    config = obter_config()
    if not config.api_key:
        # Sem chave configurada a API roda aberta — aceitável só em desenvolvimento.
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, config.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header X-API-Key ausente ou inválido.",
        )
