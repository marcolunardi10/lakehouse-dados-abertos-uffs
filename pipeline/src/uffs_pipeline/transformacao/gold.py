"""Camada Gold: data marts por visão do painel.

Cada função `mart_*` produz uma tabela pequena e amplamente agregada, pensada
para ser lida inteira pelo DuckDB da API e mantida em cache. A filtragem por
curso e recorte temporal acontece na API, sobre estes marts — não aqui.

Mapeamento visão -> mart -> análises está em docs/indicadores.md.
"""

from __future__ import annotations

import polars as pl

from ..armazenamento import DataLake
from ..log import configurar
from . import regras

log = configurar(__name__)

# Rótulo para turmas sem curso declarado na origem.
CURSO_NAO_INFORMADO = "CURSO NÃO INFORMADO"

# Colunas que carregam nome de curso em cada mart. O filtro global do painel
# compara essas colunas com `dim_curso`, então elas precisam falar a mesma
# língua — divergência de caixa já quebrou o filtro uma vez.
COLUNA_CURSO_POR_MART = {
    "visao1_demografia": "nome_curso",
    "visao2_fluxo": "nome_curso",
    "visao2_retencao": "nome_curso",
    "visao3_desempenho": "curso",
}


def _conferir_nomes_de_curso(tabelas: dict[str, pl.DataFrame]) -> None:
    """Garante que todo curso citado nos marts existe na dimensão.

    O nome do curso é a chave do filtro global. Se um mart grafar 'Ciência Da
    Computação' e a dimensão 'CIÊNCIA DA COMPUTAÇÃO', o painel devolve vazio
    sem erro nenhum — foi exatamente o que aconteceu, e esta checagem existe
    para que não volte a acontecer em silêncio.
    """
    conhecidos = set(tabelas["dim_curso"]["nome_curso"].drop_nulls().to_list())
    for mart, coluna in COLUNA_CURSO_POR_MART.items():
        usados = set(tabelas[mart][coluna].drop_nulls().to_list()) - {CURSO_NAO_INFORMADO}
        orfaos = sorted(usados - conhecidos)
        if orfaos:
            log.error(
                "Mart '%s': %d nome(s) de curso ausente(s) de dim_curso — o filtro "
                "do painel devolverá vazio para eles: %s",
                mart,
                len(orfaos),
                ", ".join(orfaos[:5]),
            )


def _ler_silver(lake: DataLake, dataset: str) -> pl.DataFrame:
    return lake.ler_prefixo(f"silver/{dataset}/")


# --------------------------------------------------------------------------- #
# Dimensão de curso
# --------------------------------------------------------------------------- #


def mart_dim_curso(ingressantes: pl.DataFrame, matrizes: pl.DataFrame) -> pl.DataFrame:
    """Dimensão de curso: `graduacao_matrizes` como fonte autoritativa.

    O recurso `graduacao_cursos` está publicado mas com DataStore vazio (ver
    docs/dicionario-dados.md §5). `graduacao_matrizes` o substitui e ainda traz
    grau acadêmico e situação do curso.

    Ela lista apenas matrizes vigentes, porém: cursos extintos que só existem no
    histórico de `ingressantes` (medido em 29/08/2026: Ciências Econômicas,
    Engenharia Civil e Educação Especial Inclusiva) precisam do complemento
    derivado, senão sumiriam dos filtros do painel.
    """
    oficial = matrizes.select(
        pl.col("cod_curso").alias("cod_uffs"),
        "nome_curso",
        pl.col("campus").alias("nome_campus"),
        "turno",
        "grau_academico",
        "situacao",
    ).unique(subset=["cod_uffs", "turno"])

    conhecidos = set(oficial["cod_uffs"].drop_nulls().to_list())
    derivado = (
        ingressantes.filter(~pl.col("cod_uffs").is_in(list(conhecidos)))
        .select("cod_uffs", "nome_curso", "nome_campus", "turno")
        .drop_nulls("cod_uffs")
        .unique(subset=["cod_uffs", "turno"])
        .with_columns(
            pl.lit(None, dtype=pl.String).alias("grau_academico"),
            pl.lit("NÃO CONSTA EM MATRIZES").alias("situacao"),
        )
    )
    if derivado.height:
        log.info(
            "dim_curso: %d curso(s) apenas em `ingressantes`, complementados: %s",
            derivado.height,
            sorted(set(derivado["nome_curso"].to_list())),
        )

    return pl.concat([oficial, derivado.select(oficial.columns)], how="vertical_relaxed").sort(
        "nome_curso", "turno"
    )


# --------------------------------------------------------------------------- #
# Visão 1 — Retrato demográfico e ingresso (Análises 1, 2 e 3)
# --------------------------------------------------------------------------- #


def mart_demografia(ingressantes: pl.DataFrame) -> pl.DataFrame:
    """Grão: curso × coorte × cota × forma de ingresso × gênero × raça.

    Um único mart cobre as três análises da Visão 1 — a API agrega o que cada
    gráfico precisa. Mantém o mart pequeno e evita três tabelas redundantes.
    """
    base = ingressantes.filter(pl.col("tipo_discente") == regras.TIPO_DISCENTE_ESCOPO)
    return (
        base.with_columns(regras.agrupar_modalidade())
        .group_by(
            "nome_curso",
            "ano_ingresso",
            "semestre_ingresso",
            "modalidade_inscricao",
            "grupo_modalidade",
            "forma_ingresso",
            "genero",
            "raca",
        )
        .agg(pl.len().alias("qtd_ingressantes"))
        .sort("ano_ingresso", "nome_curso")
    )


# --------------------------------------------------------------------------- #
# Visão 2 — Fluxo acadêmico (Análises 4, 5 e 6)
# --------------------------------------------------------------------------- #


def mart_fluxo(ingressantes: pl.DataFrame) -> pl.DataFrame:
    """Grão: curso × coorte × cota × forma de ingresso, por situação de vínculo.

    A taxa de evasão é calculada na API a partir destas contagens, e não aqui:
    assim o denominador pode mudar conforme os filtros aplicados pelo gestor.

    `forma_ingresso` está no grão por causa da consideração da banca sobre
    evasão de curso versus evasão da universidade (docs/registro-decisoes.md,
    D-10). Formas como TRANSFERÊNCIA INTERNA e RETORNO DE ALUNO-ABANDONO marcam
    vínculos que são reentrada na instituição, não ingresso pela primeira vez —
    sem essa quebra o painel não consegue separar as duas leituras.
    """
    base = ingressantes.filter(pl.col("tipo_discente") == regras.TIPO_DISCENTE_ESCOPO)
    classificado = base.with_columns(
        regras.classificar_vinculo(),
        regras.marcar_reentrada(),
    )
    regras.alertar_categorias_nao_mapeadas(classificado, "situacao_vinculo", "Gold/fluxo")

    return (
        classificado.group_by(
            "nome_curso",
            "ano_ingresso",
            "semestre_ingresso",
            "modalidade_inscricao",
            "forma_ingresso",
            "e_reentrada",
            "situacao_vinculo",
        )
        .agg(pl.len().alias("qtd_estudantes"))
        .sort("nome_curso", "ano_ingresso", "semestre_ingresso")
    )


def periodo_referencia(turmas: pl.DataFrame) -> tuple[int, int]:
    """Período letivo mais recente com turmas ofertadas.

    Serve de "agora" para medir semestres decorridos. Vem dos dados, não do
    relógio: assim a Gold é reproduzível — reprocessar a mesma Bronze meses
    depois produz exatamente os mesmos números.
    """
    ano = turmas["ano"].max()
    semestre = turmas.filter(pl.col("ano") == ano)["semestre"].max()
    return int(ano), int(semestre)


def mart_retencao(
    ingressantes: pl.DataFrame,
    matrizes: pl.DataFrame,
    estruturas: pl.DataFrame,
    turmas: pl.DataFrame,
) -> pl.DataFrame:
    """Retenção com prazo institucional (consideração P9 da banca).

    Grão: curso × turno × coorte × progressão.

    Caminho de junção, validado em 29/08/2026:
        ingressantes(cod_uffs, turno) -> matrizes(cod_curso, turno) -> id_matriz
        (id_matriz, matriz) -> estruturas -> quant_semestres, limite_semestres

    `matriz` de ingressantes vem como 'AAAA/P' e a Silver de estruturas monta a
    mesma chave a partir de ano/período de entrada em vigor.
    """
    ano_ref, semestre_ref = periodo_referencia(turmas)
    log.info("Retenção: período de referência %d/%d.", ano_ref, semestre_ref)

    dim = matrizes.select(
        pl.col("cod_curso").alias("cod_uffs"), "turno", "id_matriz"
    ).unique()
    curriculos = estruturas.select(
        "id_matriz", "matriz", "quant_semestres", "limite_semestres"
    ).unique()

    base = (
        ingressantes.filter(pl.col("tipo_discente") == regras.TIPO_DISCENTE_ESCOPO)
        .with_columns(regras.classificar_vinculo())
        .join(dim, on=["cod_uffs", "turno"], how="left")
        .join(curriculos, on=["id_matriz", "matriz"], how="left")
        .with_columns(
            (
                (pl.lit(ano_ref) - pl.col("ano_ingresso")) * 2
                + (pl.lit(semestre_ref) - pl.col("semestre_ingresso"))
            ).alias("semestres_decorridos")
        )
        .with_columns(regras.classificar_progressao())
    )

    ativos = base.filter(pl.col("situacao_vinculo") == "ATIVO")
    sem_parametro = ativos.filter(pl.col("progressao") == "SEM PARAMETRO").height
    if sem_parametro:
        log.warning(
            "Retenção: %d de %d vínculos ativos (%.1f%%) sem currículo correspondente "
            "em `estruturas` — entram como SEM PARAMETRO.",
            sem_parametro,
            ativos.height,
            100 * sem_parametro / ativos.height,
        )

    return (
        base.group_by(
            "nome_curso",
            "turno",
            "ano_ingresso",
            "semestre_ingresso",
            "modalidade_inscricao",
            "progressao",
        )
        .agg(
            pl.len().alias("qtd_estudantes"),
            pl.col("semestres_decorridos").mean().round(1).alias("semestres_decorridos_medio"),
            pl.col("quant_semestres").max().alias("semestres_previstos"),
            pl.col("limite_semestres").max().alias("semestres_limite"),
        )
        .sort("nome_curso", "ano_ingresso", "semestre_ingresso")
    )


# --------------------------------------------------------------------------- #
# Visão 3 — Desempenho e gargalos curriculares (Análises 7, 8 e 9)
# --------------------------------------------------------------------------- #


def _historico_com_turma(historico: pl.DataFrame, turmas: pl.DataFrame) -> pl.DataFrame:
    """Junta histórico e turmas — a única forma de saber campus e curso da matrícula.

    Chave: (ano, semestre, cod_ccr, id_unico_turma). Ambos os lados já foram
    tipados para Int32 na Silver.
    """
    turmas_escopo = turmas.filter(pl.col("sit_turma") == regras.SITUACAO_TURMA_ESCOPO).select(
        "ano", "semestre", "cod_ccr", "id_unico_turma", "nome_ccr", "ch_ccr", "cursos_turma", "nome_campus"
    )

    juncao = historico.join(
        turmas_escopo,
        on=["ano", "semestre", "cod_ccr", "id_unico_turma"],
        how="inner",
    )

    perdidos = historico.height - juncao.height
    if perdidos:
        log.warning(
            "Junção historico⋈turmas descartou %d de %d matrículas (%.1f%%) — "
            "turmas não consolidadas ou fora do escopo.",
            perdidos,
            historico.height,
            100 * perdidos / historico.height,
        )

    # Frequências impossíveis são saneadas aqui, uma vez só, para que todos os
    # marts da Visão 3 partam do mesmo dado.
    minimo, maximo = regras.LIMITES_FREQUENCIA
    negativas = juncao.filter(pl.col("freq_aluno") < minimo).height
    acima = juncao.filter(pl.col("freq_aluno") > maximo).height
    juncao = juncao.with_columns(regras.frequencia_saneada())
    if negativas:
        log.warning(
            "Frequência negativa em %d de %d matrículas (%.2f%%) — faltas "
            "registradas acima da carga horária nominal. Fixadas em 0%%.",
            negativas,
            juncao.height,
            100 * negativas / juncao.height,
        )
    if acima:
        log.error(
            "Frequência acima de 100%% em %d matrículas — não deveria ocorrer "
            "com a fórmula da origem. Anuladas; investigar.",
            acima,
        )
    return juncao


def mart_desempenho(historico: pl.DataFrame, turmas: pl.DataFrame) -> pl.DataFrame:
    """Grão: CCR × período × curso, com contagens por resultado.

    Alimenta as Análises 7 (ranking de gargalos) e 9 (perfil da reprovação).
    """
    base = _historico_com_turma(historico, turmas).with_columns(regras.classificar_resultado())
    regras.alertar_categorias_nao_mapeadas(base, "resultado", "Gold/desempenho")

    # Uma turma pode atender vários cursos: a lista vem separada por ';'.
    # Oito turmas de Chapecó têm `quantidade_cursos = 0` e a lista vazia; o
    # rótulo explícito evita um nulo mudo na dimensão de curso (D-17).
    por_curso = (
        base.with_columns(pl.col("cursos_turma").str.split(";").alias("curso"))
        .explode("curso")
        .with_columns(
            pl.col("curso")
            .str.strip_chars()
            .replace({"": None})
            .fill_null(CURSO_NAO_INFORMADO)
        )
    )
    sem_curso = por_curso.filter(pl.col("curso") == CURSO_NAO_INFORMADO).height
    if sem_curso:
        log.warning(
            "Desempenho: %d matrícula(s) em turmas sem curso declarado — "
            "agrupadas como '%s'.",
            sem_curso,
            CURSO_NAO_INFORMADO,
        )

    return (
        por_curso.group_by("curso", "cod_ccr", "nome_ccr", "ano", "semestre", "resultado")
        .agg(
            pl.len().alias("qtd_matriculas"),
            pl.col("media_final").mean().round(2).alias("media_final_media"),
            pl.col("freq_aluno").mean().round(2).alias("freq_media"),
        )
        .sort("curso", "cod_ccr", "ano", "semestre")
    )


def mart_frequencia_media(historico: pl.DataFrame, turmas: pl.DataFrame) -> pl.DataFrame:
    """Análise 8: dispersão frequência × média final.

    Binado em faixas de 5 pontos percentuais de frequência para que o mart caiba
    em poucos KB — a nuvem de pontos crua teria 431 mil linhas e não passaria
    pela API sem penalizar a latência.
    """
    base = (
        _historico_com_turma(historico, turmas)
        .filter(pl.col("freq_aluno").is_not_null() & pl.col("media_final").is_not_null())
        .with_columns(regras.classificar_resultado())
    )
    return (
        base.with_columns(((pl.col("freq_aluno") / 5).floor() * 5).cast(pl.Int32).alias("faixa_freq"))
        .group_by("cod_ccr", "nome_ccr", "faixa_freq", "resultado")
        .agg(
            pl.len().alias("qtd_matriculas"),
            pl.col("media_final").mean().round(2).alias("media_final_media"),
            pl.col("media_final").std().round(2).alias("media_final_desvio"),
        )
        .sort("cod_ccr", "faixa_freq")
    )


# --------------------------------------------------------------------------- #
# Orquestração da camada
# --------------------------------------------------------------------------- #

MARTS = (
    "dim_curso",
    "visao1_demografia",
    "visao2_fluxo",
    "visao2_retencao",
    "visao3_desempenho",
    "visao3_frequencia_media",
)


def construir_gold(lake: DataLake | None = None) -> dict[str, str]:
    lake = lake or DataLake()

    ingressantes = _ler_silver(lake, "ingressantes")
    turmas = _ler_silver(lake, "turmas")
    historico = _ler_silver(lake, "historico")
    matrizes = _ler_silver(lake, "matrizes")
    estruturas = _ler_silver(lake, "estruturas")

    tabelas = {
        "dim_curso": mart_dim_curso(ingressantes, matrizes),
        "visao1_demografia": mart_demografia(ingressantes),
        "visao2_fluxo": mart_fluxo(ingressantes),
        "visao2_retencao": mart_retencao(ingressantes, matrizes, estruturas, turmas),
        "visao3_desempenho": mart_desempenho(historico, turmas),
        "visao3_frequencia_media": mart_frequencia_media(historico, turmas),
    }

    _conferir_nomes_de_curso(tabelas)

    gravados: dict[str, str] = {}
    for nome, df in tabelas.items():
        lake.apagar_prefixo(f"gold/{nome}/")
        gravados[nome] = lake.escrever_parquet(df, f"gold/{nome}/parte-000.parquet")
    return gravados
