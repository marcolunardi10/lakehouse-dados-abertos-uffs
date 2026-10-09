"""Ponto de entrada do pipeline. É o que o GitHub Actions invoca.

    python -m uffs_pipeline.cli catalogo
    python -m uffs_pipeline.cli dominios
    python -m uffs_pipeline.cli ingestao [--dataset NOME] [--se-atualizado]
    python -m uffs_pipeline.cli bronze-para-silver [--dataset NOME]
    python -m uffs_pipeline.cli silver-para-gold
    python -m uffs_pipeline.cli completo [--se-atualizado]

`--se-atualizado` compara o carimbo `data_atualizacao` da origem com o da última
partição Bronze e encerra sem reprocessar quando nada mudou. É o que permite
agendar verificações frequentes mesmo com a origem publicando por semestre.
"""

from __future__ import annotations

import argparse
import sys
import time

from .armazenamento import DataLake
from .ckan import ClienteCKAN
from .config import carregar_catalogo
from .ingestao.bronze import ingerir_dataset, ingerir_todos
from .log import configurar
from .transformacao.gold import construir_gold
from .transformacao.silver import TRANSFORMACOES, construir_silver, construir_silver_todos

log = configurar("uffs_pipeline.cli")

# Colunas categóricas cujo domínio alimenta as regras de negócio em regras.py.
COLUNAS_DOMINIO = {
    "ingressantes": [
        "tipo_discente",
        "sit_matricula",
        "forma_ingresso",
        "modalidade_inscricao",
        "genero",
        "raca",
        "turno",
    ],
    "turmas": ["sit_turma"],
    "historico": ["sit_matricula"],
}


def cmd_catalogo(_: argparse.Namespace) -> None:
    """Confere IDs, esquema e volumetria das fontes contra o catálogo versionado."""
    catalogo = carregar_catalogo()
    cliente = ClienteCKAN()
    for dataset in catalogo.todos():
        print(f"\n=== {dataset.nome} — {dataset.titulo}")
        print(f"    pacote: {dataset.pacote}")
        for recurso in cliente.recursos_do_pacote(dataset.pacote):
            print(f"    recurso: {recurso['id']} | {recurso['nome']} | ds_ativo={recurso['datastore_ativo']}")
        meta = cliente.metadados_recurso(dataset.resource_id)
        print(f"    volumetria: {meta['total']} registros")
        for campo, tipo in meta["campos"].items():
            print(f"      - {campo}: {tipo}")


def cmd_dominios(_: argparse.Namespace) -> None:
    """Lista os valores distintos das categóricas de negócio.

    A saída é o insumo para validar as listas de `transformacao/regras.py`.
    Roda direto contra o CKAN, sem depender do data lake.
    """
    catalogo = carregar_catalogo()
    cliente = ClienteCKAN()
    campus = catalogo.campus_escopo

    for nome, colunas in COLUNAS_DOMINIO.items():
        dataset = catalogo.obter(nome)
        # `historico` não tem nome_campus; as demais filtram por campus na origem.
        filtro = "" if nome == "historico" else f"WHERE \"nome_campus\" = '{campus}'"
        for coluna in colunas:
            sql = (
                f'SELECT "{coluna}" AS valor, count(*) AS n '
                f'FROM "{dataset.resource_id}" {filtro} GROUP BY 1 ORDER BY 2 DESC'
            )
            print(f"\n### {nome}.{coluna}")
            try:
                for lote in cliente.consultar_paginado(sql):
                    for linha in lote:
                        print(f"    {linha['valor']!r} => {linha['n']}")
            except Exception as erro:  # noqa: BLE001
                print(f"    !! falhou: {type(erro).__name__} — {erro}")
            time.sleep(1)  # o portal derruba rajadas de requisições


def cmd_ingestao(args: argparse.Namespace) -> bool:
    """Devolve True se alguma partição Bronze nova foi gravada."""
    lake, cliente = DataLake(), ClienteCKAN()
    somente_se_novo = getattr(args, "se_atualizado", False)
    if args.dataset:
        dataset = carregar_catalogo().obter(args.dataset)
        chaves = ingerir_dataset(dataset, lake, cliente, apenas_se_atualizado=somente_se_novo)
        return bool(chaves)
    resultado = ingerir_todos(lake, cliente, apenas_se_atualizado=somente_se_novo)
    return any(resultado.values())


def cmd_silver(args: argparse.Namespace) -> None:
    lake = DataLake()
    if args.dataset:
        construir_silver(args.dataset, lake)
    else:
        construir_silver_todos(lake)


def cmd_gold(_: argparse.Namespace) -> None:
    for nome, chave in construir_gold(DataLake()).items():
        log.info("Mart '%s' -> %s", nome, chave)


def cmd_completo(args: argparse.Namespace) -> None:
    houve_carga = cmd_ingestao(args)
    if getattr(args, "se_atualizado", False) and not houve_carga:
        log.info("Nenhuma base mudou na origem. Silver e Gold preservadas; nada a fazer.")
        return
    cmd_silver(args)
    cmd_gold(args)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uffs_pipeline", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("catalogo", help="Inspeciona esquema e volumetria das fontes CKAN").set_defaults(
        func=cmd_catalogo
    )
    sub.add_parser("dominios", help="Lista valores distintos das categóricas de negócio").set_defaults(
        func=cmd_dominios
    )

    p_ing = sub.add_parser("ingestao", help="CKAN -> Bronze")
    p_ing.add_argument("--dataset", choices=sorted(carregar_catalogo().datasets))
    p_ing.add_argument(
        "--se-atualizado",
        dest="se_atualizado",
        action="store_true",
        help="Só reingere se o carimbo data_atualizacao mudou na origem",
    )
    p_ing.set_defaults(func=cmd_ingestao)

    p_silver = sub.add_parser("bronze-para-silver", help="Bronze -> Silver")
    p_silver.add_argument("--dataset", choices=sorted(TRANSFORMACOES))
    p_silver.set_defaults(func=cmd_silver)

    sub.add_parser("silver-para-gold", help="Silver -> Gold").set_defaults(func=cmd_gold)

    p_completo = sub.add_parser("completo", help="Executa as três camadas em sequência")
    p_completo.add_argument("--dataset", default=None)
    p_completo.add_argument(
        "--se-atualizado",
        dest="se_atualizado",
        action="store_true",
        help="Encerra sem reprocessar se nenhuma base mudou na origem",
    )
    p_completo.set_defaults(func=cmd_completo)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    inicio = time.perf_counter()
    try:
        args.func(args)
    except Exception:
        log.exception("Pipeline falhou no comando '%s'.", args.comando)
        return 1
    log.info("Comando '%s' concluído em %.1fs.", args.comando, time.perf_counter() - inicio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
