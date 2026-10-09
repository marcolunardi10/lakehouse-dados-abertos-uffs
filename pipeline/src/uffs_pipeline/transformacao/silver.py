"""Camada Silver: tipagem estrita, deduplicação e padronização.

A Silver é derivada determinística da Bronze — pode ser reconstruída a qualquer
momento sem tocar na origem. Por isso o prefixo é apagado e reescrito a cada
execução.

Regras aplicadas aqui (e em nenhum outro lugar):
  - conversão de tipos a partir das strings da Bronze;
  - remoção da coluna técnica `_id` do DataStore;
  - deduplicação por chave de negócio;
  - normalização de categóricas: espaços nas pontas, caixa alta nas colunas de
    status e unificação de vazio / `N/A` / `NULL` em nulo;
  - normalização do tipo de `id_unico_turma`, que difere entre as bases.

Acentos são preservados de propósito: a origem publica `CONCLUÍDO` e
`REPROVADO POR MÉDIA E POR FALTAS`, e remover acentos aqui exigiria manter duas
grafias em `regras.py`. Os literais daquele módulo batem com a origem.
"""

from __future__ import annotations

import polars as pl

from ..armazenamento import DataLake
from ..ingestao.bronze import particao_completa, prefixo_bronze
from ..log import configurar

log = configurar(__name__)

COLUNA_TECNICA = "_id"

# --------------------------------------------------------------------------- #
# Deduplicação — decisão metodológica, não detalhe de implementação
#
# A única chave de deduplicação é `_id`, a chave primária do DataStore do CKAN.
# Ela protege contra o único duplicado possível: a mesma linha da origem vir
# duas vezes por sobreposição de páginas.
#
# NUNCA deduplicar `ingressantes` por atributos de negócio. Como nenhuma base
# expõe identificador de estudante (docs/dicionario-dados.md §7, "Restrições
# analíticas"), dois estudantes distintos de mesmo curso, coorte, cota, gênero,
# raça e situação produzem linhas byte a byte idênticas — e ambas são
# registros legítimos. Medido em 29/08/2026: deduplicar por esses atributos
# descartaria 8.813 dos 16.845 ingressantes de Chapecó (52%), reduzindo pela
# metade toda contagem do painel.
# --------------------------------------------------------------------------- #

# Chaves naturais conferidas apenas para RELATÓRIO de qualidade — a duplicidade
# é registrada no log e as linhas são preservadas.
CHAVES_NEGOCIO: dict[str, list[str]] = {
    "turmas": ["ano", "semestre", "cod_ccr", "id_unico_turma"],
}

# Coluna de particionamento físico, para permitir partition pruning no DuckDB.
PARTICAO: dict[str, str] = {
    "turmas": "ano",
    "historico": "ano",
}


def _texto_normalizado(coluna: str) -> pl.Expr:
    """Remove espaços nas pontas e converte string vazia em nulo."""
    return (
        pl.col(coluna)
        .str.strip_chars()
        .replace({"": None, "N/A": None, "NULL": None})
        .alias(coluna)
    )


# A origem carimba com fração de segundo: '2026-08-24T02:30:16.733317'.
# O `%.f` é obrigatório — sem ele a conversão falha e, com strict=False,
# a coluna inteira vira nulo sem erro nenhum.
FORMATO_TIMESTAMP = "%Y-%m-%dT%H:%M:%S%.f"


def _tipar(df: pl.DataFrame, inteiros: list[str], decimais: list[str], datas: list[str]) -> pl.DataFrame:
    presentes = set(df.columns)
    tipado = df.with_columns(
        [pl.col(c).cast(pl.Int32, strict=False) for c in inteiros if c in presentes]
        + [pl.col(c).cast(pl.Float64, strict=False) for c in decimais if c in presentes]
        + [
            pl.col(c).str.to_datetime(FORMATO_TIMESTAMP, strict=False)
            for c in datas
            if c in presentes
        ]
    )

    # Conversão não-estrita falha em silêncio. Se uma coluna que tinha conteúdo
    # ficou inteiramente nula, o formato mudou na origem — e isso precisa gritar.
    for coluna in [c for c in inteiros + decimais + datas if c in presentes]:
        if df[coluna].null_count() < df.height and tipado[coluna].null_count() == tipado.height:
            log.error(
                "Coluna '%s' ficou 100%% nula após a tipagem — o formato da origem mudou. "
                "Valor de exemplo: %r",
                coluna,
                df[coluna].drop_nulls().head(1).to_list(),
            )
    return tipado


# --------------------------------------------------------------------------- #
# Transformações por dataset
# --------------------------------------------------------------------------- #


def silver_ingressantes(df: pl.DataFrame) -> pl.DataFrame:
    textuais = [
        "tipo_discente",
        "raca",
        "genero",
        "forma_ingresso",
        "modalidade_inscricao",
        "modalidade_vaga_ocupada",
        "sit_matricula",
        "nome_campus",
        "cod_uffs",
        "nome_curso",
        "turno",
        "matriz",
    ]
    return (
        df.with_columns([_texto_normalizado(c) for c in textuais if c in df.columns])
        .pipe(_tipar, ["ano_ingresso", "semestre_ingresso"], [], ["data_atualizacao"])
        .with_columns(
            # Categóricas de status e ingresso em caixa alta: a origem mistura
            # 'ATIVO' com 'Ativo' entre os sistemas SGA e SIGAA.
            pl.col("tipo_discente").str.to_uppercase(),
            pl.col("sit_matricula").str.to_uppercase(),
            pl.col("forma_ingresso").str.to_uppercase(),
            pl.col("modalidade_inscricao").str.to_uppercase(),
            # `nome_curso` é chave de filtro entre marts, e as fontes divergem:
            # `ingressantes` publica 'Ciência Da Computação', enquanto `matrizes`
            # e `turmas` publicam em caixa alta. Sem canonizar aqui, o filtro de
            # curso do painel não casa com as Visões 1 e 2 e devolve vazio.
            pl.col("nome_curso").str.to_uppercase(),
        )
    )


def silver_turmas(df: pl.DataFrame) -> pl.DataFrame:
    textuais = [
        "nome_campus",
        "cod_ccr",
        "nome_ccr",
        "cod_uffs_cursos_turma",
        "cursos_turma",
        "lista_docentes",
        "lista_ch_docentes",
        "sit_turma",
    ]
    return (
        df.with_columns([_texto_normalizado(c) for c in textuais if c in df.columns])
        .pipe(
            _tipar,
            [
                "ano",
                "semestre",
                "id_unico_turma",
                "id_relativo_turma",
                "quantidade_cursos",
                "quantidade_docentes",
                "vagas_turma",
                "qtd_inscritos",
                "qtd_passaram_pela_turma",
                "qtd_aprovados",
            ],
            ["ch_ccr"],
            ["data_atualizacao"],
        )
        .with_columns(
            pl.col("nome_ccr").str.to_uppercase(),
            pl.col("sit_turma").str.to_uppercase(),
        )
    )


def silver_historico(df: pl.DataFrame) -> pl.DataFrame:
    textuais = ["cod_curso", "cod_ccr", "sit_matricula"]
    return (
        df.with_columns([_texto_normalizado(c) for c in textuais if c in df.columns])
        # id_unico_turma vem como text no histórico e int4 em turmas.
        # Normalizar aqui é o que torna a junção da Gold possível.
        .pipe(
            _tipar,
            ["ano", "semestre", "id_unico_turma", "ch_t_p", "numero_faltas"],
            ["freq_aluno", "media_final"],
            ["data_atualizacao"],
        )
        .with_columns(pl.col("sit_matricula").str.to_uppercase())
    )


def silver_matrizes(df: pl.DataFrame) -> pl.DataFrame:
    """Dimensão de curso oficial. `campus` aqui equivale a `nome_campus` nas outras."""
    textuais = ["campus", "cod_curso", "nome_curso", "turno", "grau_academico", "situacao", "enfase"]
    return (
        df.with_columns([_texto_normalizado(c) for c in textuais if c in df.columns])
        .pipe(_tipar, ["id_matriz"], [], ["data_atualizacao"])
        .with_columns(
            # `nome_curso` vem em caixa alta aqui e em caixa mista em
            # ingressantes. Normalizar para alta dos dois lados evita que a
            # junção por nome falhe — embora a chave preferida seja cod_curso.
            pl.col("nome_curso").str.to_uppercase(),
            pl.col("grau_academico").str.to_uppercase(),
        )
    )


def silver_estruturas(df: pl.DataFrame) -> pl.DataFrame:
    """Currículos: duração prevista e prazo máximo de integralização."""
    textuais = ["desc_matriz", "em_andamento"]
    return (
        df.with_columns([_texto_normalizado(c) for c in textuais if c in df.columns])
        .pipe(
            _tipar,
            [
                "id_curriculo",
                "id_matriz",
                "ano_entrada_vigor",
                "periodo_entrada_vigor",
                "ch_obrigatoria",
                "ch_optativa",
                "ch_eletiva",
                "ch_accs",
                "ch_total",
                "ch_max_sem",
                "ch_min_sem",
                "ch_1o_nivel",
                "quant_semestres",
                "limite_semestres",
            ],
            [],
            ["data_atualizacao"],
        )
        .with_columns(
            pl.col("em_andamento").str.to_uppercase(),
            # Chave de junção com ingressantes.matriz, que vem como '2026/1'.
            (
                pl.col("ano_entrada_vigor").cast(pl.String)
                + pl.lit("/")
                + pl.col("periodo_entrada_vigor").cast(pl.String)
            ).alias("matriz"),
        )
    )


def silver_ccrs_matrizes(df: pl.DataFrame) -> pl.DataFrame:
    """CCR × currículo. `ids_curriculos` e `niveis_oferta` são listas paralelas."""
    textuais = [
        "cod_ccr",
        "nome_ccr",
        "unid_responsavel",
        "ids_curriculos",
        "niveis_oferta",
        "cod_cursos",
        "nome_cursos",
    ]
    return (
        df.with_columns([_texto_normalizado(c) for c in textuais if c in df.columns])
        .pipe(
            _tipar,
            ["n_curriculos", "n_cursos", "ch_total"],
            [],
            ["data_atualizacao"],
        )
        .with_columns(pl.col("nome_ccr").str.to_uppercase())
    )


TRANSFORMACOES = {
    "ingressantes": silver_ingressantes,
    "turmas": silver_turmas,
    "historico": silver_historico,
    "matrizes": silver_matrizes,
    "estruturas": silver_estruturas,
    "ccrs_matrizes": silver_ccrs_matrizes,
}


# --------------------------------------------------------------------------- #
# Orquestração da camada
# --------------------------------------------------------------------------- #


def _relatar_duplicidade_negocio(df: pl.DataFrame, dataset: str) -> None:
    """Verifica a chave natural sem remover nada.

    Se a chave que a documentação da UFFS descreve como única deixar de ser
    única, isso é um achado sobre a origem — e precisa aparecer no log, não
    sumir dentro de um `unique()`.
    """
    chaves = [c for c in CHAVES_NEGOCIO.get(dataset, []) if c in df.columns]
    if not chaves:
        return
    distintas = df.select(chaves).n_unique()
    if distintas != df.height:
        log.warning(
            "Silver '%s': chave natural %s não é única — %d linhas para %d chaves. "
            "Linhas preservadas; verificar antes de usar a chave em junções.",
            dataset,
            chaves,
            df.height,
            distintas,
        )


def construir_silver(dataset: str, lake: DataLake | None = None) -> list[str]:
    lake = lake or DataLake()

    particao = lake.ultima_particao_bronze(dataset)
    if not particao_completa(dataset, particao, lake):
        log.warning(
            "Silver '%s': partição Bronze %s não tem marcador de conclusão. "
            "A carga pode estar incompleta e os números, subestimados. "
            "Rode `cli ingestao --dataset %s` antes de confiar no resultado.",
            dataset,
            particao,
            dataset,
        )
    log.info("Silver '%s': lendo Bronze data_carga=%s", dataset, particao)
    bruto = lake.ler_prefixo(prefixo_bronze(dataset, particao))

    if dataset not in TRANSFORMACOES:
        raise KeyError(f"Sem transformação Silver definida para '{dataset}'.")

    df = TRANSFORMACOES[dataset](bruto)

    antes = df.height
    if COLUNA_TECNICA in df.columns:
        df = df.unique(subset=[COLUNA_TECNICA], keep="first")
        if df.height != antes:
            log.warning(
                "Silver '%s': %d linhas repetidas por %s removidas "
                "(provável sobreposição de páginas na ingestão).",
                dataset,
                antes - df.height,
                COLUNA_TECNICA,
            )
    else:
        log.warning(
            "Silver '%s': sem a coluna %s — deduplicação técnica não aplicada.",
            dataset,
            COLUNA_TECNICA,
        )

    _relatar_duplicidade_negocio(df, dataset)

    if COLUNA_TECNICA in df.columns:
        df = df.drop(COLUNA_TECNICA)

    log.info("Silver '%s': %d linhas gravadas.", dataset, df.height)

    lake.apagar_prefixo(f"silver/{dataset}/")

    coluna_particao = PARTICAO.get(dataset)
    if not coluna_particao:
        return [lake.escrever_parquet(df, f"silver/{dataset}/parte-000.parquet")]

    chaves_gravadas = []
    for (valor,), grupo in df.partition_by(coluna_particao, as_dict=True).items():
        destino = f"silver/{dataset}/{coluna_particao}={valor}/parte-000.parquet"
        chaves_gravadas.append(lake.escrever_parquet(grupo, destino))
    return chaves_gravadas


def construir_silver_todos(lake: DataLake | None = None) -> dict[str, list[str]]:
    lake = lake or DataLake()
    return {nome: construir_silver(nome, lake) for nome in TRANSFORMACOES}
