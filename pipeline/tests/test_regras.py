"""Testes das regras de negócio — o núcleo metodológico do trabalho.

Os domínios usados aqui são os **valores reais** das bases, colhidos em
29/08/2026 e documentados em `docs/dicionario-dados.md` §6. Não são exemplos
inventados: se a origem publicar uma categoria nova, estes testes continuam
passando (e é o alerta de `OUTROS` em produção que avisa), mas se alguém mexer
em `regras.py` e quebrar uma classificação já verificada, eles falham.
"""

from __future__ import annotations

import polars as pl
import pytest

from uffs_pipeline.transformacao import regras

# --------------------------------------------------------------------------- #
# Domínios reais (dicionario-dados.md §6)
# --------------------------------------------------------------------------- #

VINCULOS = ["CANCELADO", "CONCLUÍDO", "ATIVO", "ATIVO - FORMANDO", "TRANCADO", "FORMADO"]

RESULTADOS = [
    "APROVADO",
    "REPROVADO POR NOTA E FALTA",
    "REPROVADO POR NOTA",
    "TRANCADO",
    "CANCELADO",
    "MATRICULADO",
    "REPROVADO",
    "REPROVADO POR MÉDIA E POR FALTAS",
    "APROVADO POR NOTA",
    "DESISTENCIA",
    "REPROVADO POR FALTAS",
]

MODALIDADES = [
    "AC", "N/A", "L5", "L1", "LI_EP", "L6", "L2", "A1", "LB_EP", "LI_PPI",
    "A2", "LB_PPI", "L13", "A2-I", "L9", "LI_PCD", "LB_Q", "LB_PCD", "L10", "L14",
]

FORMAS_INGRESSO = [
    "ENEM", "SISU", "PROCESSO SELETIVO SIMPLIFICADO", "TRANSFERÊNCIA INTERNA",
    "RETORNO DE GRADUADO", "TRANSFERÊNCIA EXTERNA", "RETORNO DE ALUNO-ABANDONO",
    "PIN", "PRO-HAITI", "PRÓ-IMIGRANTE", "VESTIBULAR", "JUDICIAL", "PARFOR",
    "CONVÊNIO PEC-G", "TRANSFERÊNCIA COMPULSÓRIA (EX OFFICIO)",
]


def _classificar(valores: list, expressao: pl.Expr, coluna: str, **extras) -> list:
    """Aplica uma expressão de classificação e devolve a coluna resultante.

    A coluna de entrada é tipada como String de propósito: a Bronze grava tudo
    como texto e a Silver mantém as categóricas assim, então uma lista só de
    nulos precisa continuar sendo String — e não virar coluna de tipo Null,
    que não existe no pipeline real.
    """
    dados = {coluna: pl.Series(coluna, valores, dtype=pl.String)}
    dados.update({nome: [valor] * len(valores) for nome, valor in extras.items()})
    return pl.DataFrame(dados).with_columns(expressao).to_series(-1).to_list()


# --------------------------------------------------------------------------- #
# Situação de vínculo
# --------------------------------------------------------------------------- #


def test_nenhum_vinculo_real_cai_em_outros():
    """A garantia que sustenta os números do painel: domínio fechado."""
    saidas = _classificar(VINCULOS, regras.classificar_vinculo(), "sit_matricula")
    assert "OUTROS" not in saidas


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("CANCELADO", "EVADIDO"),
        ("CONCLUÍDO", "CONCLUIDO"),
        ("FORMADO", "CONCLUIDO"),
        ("ATIVO", "ATIVO"),
        ("ATIVO - FORMANDO", "ATIVO"),
        ("TRANCADO", "TRANCADO"),
    ],
)
def test_classificacao_de_vinculo(valor, esperado):
    assert _classificar([valor], regras.classificar_vinculo(), "sit_matricula") == [esperado]


def test_formando_conta_como_ativo_e_nao_como_concluido():
    """Quem cumpriu créditos e aguarda colação ainda tem vínculo ativo."""
    assert "ATIVO - FORMANDO" in regras.VINCULO_ATIVO
    assert "ATIVO - FORMANDO" not in regras.VINCULO_CONCLUIDO


def test_trancado_nao_e_evasao():
    """Trancamento é suspensão temporária — contá-lo como evasão inflaria a taxa."""
    assert "TRANCADO" not in regras.VINCULO_EVADIDO


def test_valor_desconhecido_vira_outros_e_nao_explode():
    saidas = _classificar(["SITUACAO INEDITA"], regras.classificar_vinculo(), "sit_matricula")
    assert saidas == ["OUTROS"]


# --------------------------------------------------------------------------- #
# Resultado na disciplina
# --------------------------------------------------------------------------- #


def test_nenhum_resultado_real_cai_em_outros():
    for frequencia in (90.0, 40.0, None):
        saidas = _classificar(
            RESULTADOS, regras.classificar_resultado(), "sit_matricula", freq_aluno=frequencia
        )
        assert "OUTROS" not in saidas, f"com freq_aluno={frequencia}"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("APROVADO", "APROVADO"),
        ("APROVADO POR NOTA", "APROVADO"),
        ("REPROVADO POR NOTA", "REPROVADO_NOTA"),
        ("REPROVADO POR FALTAS", "REPROVADO_FREQUENCIA"),
        ("REPROVADO POR NOTA E FALTA", "REPROVADO_NOTA_E_FREQUENCIA"),
        ("REPROVADO POR MÉDIA E POR FALTAS", "REPROVADO_NOTA_E_FREQUENCIA"),
        ("TRANCADO", "NEUTRO"),
        ("CANCELADO", "NEUTRO"),
        ("MATRICULADO", "NEUTRO"),
        ("DESISTENCIA", "NEUTRO"),
    ],
)
def test_resultado_explicito_ignora_a_frequencia(valor, esperado):
    """Onde a origem diz a causa, o rótulo dela prevalece sobre a heurística."""
    for frequencia in (10.0, 99.0):
        saida = _classificar(
            [valor], regras.classificar_resultado(), "sit_matricula", freq_aluno=frequencia
        )
        assert saida == [esperado], f"{valor} com freq_aluno={frequencia}"


@pytest.mark.parametrize(
    ("frequencia", "esperado"),
    [
        (99.0, "REPROVADO_NOTA"),
        (75.0, "REPROVADO_NOTA"),  # exatamente no piso ainda é frequência suficiente
        (74.9, "REPROVADO_FREQUENCIA"),
        (0.0, "REPROVADO_FREQUENCIA"),
    ],
)
def test_reprovado_sem_qualificacao_e_desempatado_pela_frequencia(frequencia, esperado):
    saida = _classificar(
        ["REPROVADO"], regras.classificar_resultado(), "sit_matricula", freq_aluno=frequencia
    )
    assert saida == [esperado]


def test_reprovacao_simultanea_tem_categoria_propria():
    """Forçá-la em nota ou frequência distorceria o modo dominante de reprovação."""
    assert regras.RESULTADO_REPROVADO_NOTA_E_FREQUENCIA
    assert not regras.RESULTADO_REPROVADO_NOTA_E_FREQUENCIA & regras.RESULTADO_REPROVADO_NOTA
    assert not regras.RESULTADO_REPROVADO_NOTA_E_FREQUENCIA & regras.RESULTADO_REPROVADO_FREQUENCIA


# --------------------------------------------------------------------------- #
# Modalidade de ingresso
# --------------------------------------------------------------------------- #


def test_nenhuma_modalidade_real_cai_em_outros():
    saidas = _classificar(MODALIDADES, regras.agrupar_modalidade(), "modalidade_inscricao")
    assert "OUTROS" not in saidas


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("AC", "AMPLA CONCORRENCIA"),
        ("N/A", "NAO SE APLICA"),
        (None, "NAO SE APLICA"),
        ("L1", "ACAO AFIRMATIVA"),      # Lei 12.711/2012
        ("L14", "ACAO AFIRMATIVA"),
        ("LB_EP", "ACAO AFIRMATIVA"),   # Lei 14.723/2023
        ("LI_PCD", "ACAO AFIRMATIVA"),
        ("A1", "ACAO AFIRMATIVA"),      # institucionais da UFFS
        ("A2-I", "ACAO AFIRMATIVA"),
    ],
)
def test_agrupamento_de_modalidade(valor, esperado):
    assert _classificar([valor], regras.agrupar_modalidade(), "modalidade_inscricao") == [esperado]


def test_nao_se_aplica_nao_e_dado_faltante():
    """`N/A` marca forma de ingresso sem cota — significado, não ausência."""
    saidas = _classificar(["N/A", None], regras.agrupar_modalidade(), "modalidade_inscricao")
    assert saidas == ["NAO SE APLICA", "NAO SE APLICA"]


# --------------------------------------------------------------------------- #
# Reentrada institucional
# --------------------------------------------------------------------------- #


def test_reentrada_marca_apenas_quem_ja_era_da_uffs():
    saidas = _classificar(FORMAS_INGRESSO, regras.marcar_reentrada(), "forma_ingresso")
    marcadas = {f for f, e in zip(FORMAS_INGRESSO, saidas) if e}
    assert marcadas == {
        "TRANSFERÊNCIA INTERNA",
        "RETORNO DE GRADUADO",
        "RETORNO DE ALUNO-ABANDONO",
    }


def test_transferencia_externa_nao_e_reentrada():
    """Vem de outra instituição: é primeiro vínculo na UFFS."""
    assert "TRANSFERÊNCIA EXTERNA" not in regras.FORMA_INGRESSO_REENTRADA


# --------------------------------------------------------------------------- #
# Frequência
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (100.0, 100.0),
        (75.0, 75.0),
        (0.0, 0.0),
        (-122.22, 0.0),    # faltas acima da carga horária nominal: faltou a tudo
        (-0.01, 0.0),
        (100.01, None),    # não ocorre na base; se ocorrer é erro, não valor
        (None, None),
    ],
)
def test_frequencia_e_trazida_para_a_faixa_possivel(valor, esperado):
    saida = pl.DataFrame({"freq_aluno": [valor]}).with_columns(
        regras.frequencia_saneada()
    )["freq_aluno"].to_list()
    assert saida == [esperado]


def test_frequencia_negativa_conta_como_reprovacao_por_frequencia():
    """Quem faltou a tudo e tem só o rótulo 'REPROVADO' reprovou por frequência.

    Com a frequência anulada, o desempate caía em reprovação por nota — o
    contrário do que os dados dizem.
    """
    saida = (
        pl.DataFrame({"sit_matricula": ["REPROVADO"], "freq_aluno": [-5.6]})
        .with_columns(regras.frequencia_saneada())
        .with_columns(regras.classificar_resultado())["resultado"]
        .to_list()
    )
    assert saida == ["REPROVADO_FREQUENCIA"]


# --------------------------------------------------------------------------- #
# Progressão / retenção
# --------------------------------------------------------------------------- #


def _progressao(situacao, decorridos, previstos, limite):
    return pl.DataFrame(
        {
            "situacao_vinculo": [situacao],
            "semestres_decorridos": [decorridos],
            "quant_semestres": [previstos],
            "limite_semestres": [limite],
        }
    ).with_columns(regras.classificar_progressao())["progressao"].to_list()[0]


@pytest.mark.parametrize(
    ("decorridos", "esperado"),
    [
        (1, "NO PRAZO"),
        (10, "NO PRAZO"),   # exatamente na duração prevista
        (11, "EM RETENCAO"),
        (16, "EM RETENCAO"),  # 80% de 20 é 16; só acima disso vira alerta
        (17, "RISCO DE JUBILAMENTO"),
        (25, "RISCO DE JUBILAMENTO"),
    ],
)
def test_progressao_de_vinculo_ativo(decorridos, esperado):
    assert _progressao("ATIVO", decorridos, 10, 20) == esperado


@pytest.mark.parametrize("situacao", ["EVADIDO", "CONCLUIDO", "TRANCADO"])
def test_progressao_so_avalia_ativos(situacao):
    """Retenção é atraso de quem ainda cursa; os demais passam adiante."""
    assert _progressao(situacao, 99, 10, 20) == situacao


def test_ativo_sem_curriculo_e_reportado_e_nao_omitido():
    assert _progressao("ATIVO", 5, None, None) == "SEM PARAMETRO"


def test_fator_de_alerta_e_uma_escolha_declarada():
    """Não há norma para este corte — se mudar, é decisão consciente."""
    assert regras.FATOR_ALERTA_JUBILAMENTO == 0.8
