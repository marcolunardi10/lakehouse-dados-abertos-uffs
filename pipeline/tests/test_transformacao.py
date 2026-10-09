"""Testes das camadas Silver e Gold — regressões de bugs que já custaram caro."""

from __future__ import annotations

import polars as pl

from uffs_pipeline.transformacao import gold, silver


# --------------------------------------------------------------------------- #
# Silver — tipagem
# --------------------------------------------------------------------------- #


def test_timestamp_com_fracao_de_segundo_e_convertido():
    """A origem publica `2026-09-14T02:30:17.136425`.

    Sem `%.f` no formato, a conversão falhava e, com `strict=False`, a coluna
    inteira virava nulo sem erro nenhum — bug real, encontrado em produção.
    """
    df = pl.DataFrame({"data_atualizacao": ["2026-09-14T02:30:17.136425"]})
    tipado = silver._tipar(df, [], [], ["data_atualizacao"])
    valor = tipado["data_atualizacao"].to_list()[0]
    assert valor is not None
    assert (valor.year, valor.month, valor.day) == (2026, 9, 14)


def test_coluna_que_fica_toda_nula_apos_tipagem_registra_erro(caplog):
    """A guarda que impede a falha silenciosa de se repetir."""
    df = pl.DataFrame({"data_atualizacao": ["formato/inesperado"]})
    silver._tipar(df, [], [], ["data_atualizacao"])
    assert "100% nula" in caplog.text or "100%% nula" in caplog.text


def test_coluna_originalmente_nula_nao_dispara_alarme_falso(caplog):
    df = pl.DataFrame({"data_atualizacao": [None]}, schema={"data_atualizacao": pl.String})
    silver._tipar(df, [], [], ["data_atualizacao"])
    assert "nula" not in caplog.text


def test_inteiros_e_decimais_sao_convertidos():
    df = pl.DataFrame({"ano": ["2026"], "freq_aluno": ["87.5"]})
    tipado = silver._tipar(df, ["ano"], ["freq_aluno"], [])
    assert tipado["ano"].to_list() == [2026]
    assert tipado["freq_aluno"].to_list() == [87.5]


# --------------------------------------------------------------------------- #
# Silver — normalização de texto
# --------------------------------------------------------------------------- #


def test_vazio_na_e_null_viram_nulo():
    df = pl.DataFrame({"campo": ["  valor  ", "", "N/A", "NULL", None]})
    saida = df.with_columns(silver._texto_normalizado("campo"))["campo"].to_list()
    assert saida == ["valor", None, None, None, None]


def test_acentos_sao_preservados():
    """`regras.py` casa com os literais da origem: remover acento quebraria tudo."""
    df = pl.DataFrame({"campo": ["CONCLUÍDO"]})
    assert df.with_columns(silver._texto_normalizado("campo"))["campo"].to_list() == ["CONCLUÍDO"]


# --------------------------------------------------------------------------- #
# Silver — deduplicação
# --------------------------------------------------------------------------- #


def test_ingressantes_nunca_deduplica_por_atributo_de_negocio():
    """Regressão do bug mais caro do projeto.

    Sem identificador de estudante, dois alunos de mesmo curso, coorte, cota,
    gênero, raça e situação geram linhas idênticas — e ambas são legítimas.
    Deduplicar por negócio descartava 52% dos ingressantes de Chapecó.
    """
    assert "ingressantes" not in silver.CHAVES_NEGOCIO


def test_chave_de_negocio_de_turmas_e_so_para_relatorio():
    """Duplicidade na chave natural é achado a reportar, não linha a remover."""
    assert silver.CHAVES_NEGOCIO["turmas"] == ["ano", "semestre", "cod_ccr", "id_unico_turma"]


def test_duplicidade_na_chave_natural_e_reportada_sem_remover(caplog):
    df = pl.DataFrame(
        {
            "ano": [2026, 2026],
            "semestre": [1, 1],
            "cod_ccr": ["GEX001", "GEX001"],
            "id_unico_turma": [7, 7],
        }
    )
    silver._relatar_duplicidade_negocio(df, "turmas")
    assert "não é única" in caplog.text
    assert df.height == 2


def test_todas_as_seis_bases_tem_transformacao_silver():
    assert set(silver.TRANSFORMACOES) == {
        "ingressantes", "turmas", "historico", "matrizes", "estruturas", "ccrs_matrizes",
    }


# --------------------------------------------------------------------------- #
# Gold
# --------------------------------------------------------------------------- #


def test_nome_de_curso_e_canonizado_em_caixa_alta():
    """Regressão: o filtro global compara nome de curso entre marts.

    `ingressantes` publica 'Ciência Da Computação' e `matrizes`/`turmas`
    publicam em caixa alta. Sem canonizar, o filtro do painel devolvia vazio
    para qualquer curso selecionado nas Visões 1 e 2.
    """
    df = pl.DataFrame(
        {
            "nome_curso": ["Ciência Da Computação"],
            "tipo_discente": ["Regular"],
            "sit_matricula": ["Ativo"],
            "forma_ingresso": ["Enem"],
            "modalidade_inscricao": ["ac"],
        }
    )
    saida = silver.silver_ingressantes(df)
    assert saida["nome_curso"].to_list() == ["CIÊNCIA DA COMPUTAÇÃO"]


def test_conferencia_de_nomes_de_curso_acusa_divergencia(caplog):
    tabelas = {
        "dim_curso": pl.DataFrame({"nome_curso": ["ADMINISTRAÇÃO"]}),
        "visao1_demografia": pl.DataFrame({"nome_curso": ["Administração"]}),
        "visao2_fluxo": pl.DataFrame({"nome_curso": ["ADMINISTRAÇÃO"]}),
        "visao2_retencao": pl.DataFrame({"nome_curso": ["ADMINISTRAÇÃO"]}),
        "visao3_desempenho": pl.DataFrame({"curso": ["ADMINISTRAÇÃO"]}),
    }
    gold._conferir_nomes_de_curso(tabelas)
    assert "visao1_demografia" in caplog.text
    assert "Administração" in caplog.text


def test_conferencia_ignora_o_rotulo_de_curso_nao_informado(caplog):
    tabelas = {
        "dim_curso": pl.DataFrame({"nome_curso": ["ADMINISTRAÇÃO"]}),
        "visao1_demografia": pl.DataFrame({"nome_curso": ["ADMINISTRAÇÃO"]}),
        "visao2_fluxo": pl.DataFrame({"nome_curso": ["ADMINISTRAÇÃO"]}),
        "visao2_retencao": pl.DataFrame({"nome_curso": ["ADMINISTRAÇÃO"]}),
        "visao3_desempenho": pl.DataFrame({"curso": [gold.CURSO_NAO_INFORMADO]}),
    }
    gold._conferir_nomes_de_curso(tabelas)
    assert "ausente" not in caplog.text


def test_periodo_de_referencia_vem_dos_dados_e_nao_do_relogio():
    """Reprocessar a mesma Bronze meses depois precisa dar o mesmo número."""
    turmas = pl.DataFrame(
        {"ano": [2024, 2026, 2026, 2025], "semestre": [2, 1, 2, 2]}
    )
    assert gold.periodo_referencia(turmas) == (2026, 2)


def test_periodo_de_referencia_usa_o_maior_semestre_do_maior_ano():
    turmas = pl.DataFrame({"ano": [2026, 2026, 2025], "semestre": [1, 1, 2]})
    assert gold.periodo_referencia(turmas) == (2026, 1)


def test_marts_da_gold_batem_com_os_aquecidos_pela_api():
    """Um mart novo na Gold sem entrada na API passaria despercebido."""
    from pathlib import Path

    deposito = Path(__file__).resolve().parents[2] / "api" / "app" / "deposito.py"
    texto = deposito.read_text(encoding="utf-8")
    for mart in gold.MARTS:
        assert f'"{mart}"' in texto, f"mart '{mart}' não está em MARTS_AQUECIDOS"
