"""Logging estruturado — a saída é a trilha de observabilidade do GitHub Actions."""

from __future__ import annotations

import logging
import os
import sys


def configurar(nome: str = "uffs_pipeline") -> logging.Logger:
    nivel = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger(nome)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(nivel)
    logger.propagate = False
    return logger
