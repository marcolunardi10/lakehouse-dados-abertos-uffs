"""Filtros globais da sidebar do painel, traduzidos em cláusula SQL parametrizada."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Query


@dataclass(frozen=True)
class Filtros:
    curso: str | None = None
    ano_inicio: int | None = None
    ano_fim: int | None = None
    semestre: int | None = None

    def clausula(self, coluna_curso: str, coluna_ano: str, coluna_semestre: str) -> tuple[str, list[Any]]:
        """Monta o WHERE. Os valores vão como parâmetros `?`, nunca interpolados."""
        condicoes: list[str] = []
        parametros: list[Any] = []

        if self.curso:
            condicoes.append(f"{coluna_curso} = ?")
            parametros.append(self.curso)
        if self.ano_inicio is not None:
            condicoes.append(f"{coluna_ano} >= ?")
            parametros.append(self.ano_inicio)
        if self.ano_fim is not None:
            condicoes.append(f"{coluna_ano} <= ?")
            parametros.append(self.ano_fim)
        if self.semestre is not None:
            condicoes.append(f"{coluna_semestre} = ?")
            parametros.append(self.semestre)

        return ("WHERE " + " AND ".join(condicoes) if condicoes else ""), parametros

    def chave_cache(self, prefixo: str) -> str:
        return f"{prefixo}:{self.curso}:{self.ano_inicio}:{self.ano_fim}:{self.semestre}"


async def obter_filtros(
    curso: str | None = Query(default=None, description="Nome do curso; omitir para todos"),
    ano_inicio: int | None = Query(default=None, ge=2009, le=2100),
    ano_fim: int | None = Query(default=None, ge=2009, le=2100),
    semestre: int | None = Query(default=None, ge=1, le=2),
) -> Filtros:
    return Filtros(curso=curso, ano_inicio=ano_inicio, ano_fim=ano_fim, semestre=semestre)
