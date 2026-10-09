"""Regras de negócio educacionais — o vocabulário controlado do domínio.

Este módulo concentra TODA classificação semântica do projeto. É deliberadamente
o único lugar onde valores textuais da origem viram categorias de negócio, para
que uma revisão de indicador seja uma revisão de um arquivo só — e para que a
metodologia do TCC II tenha uma fonte única a citar.

Os conjuntos abaixo foram **validados em 29/08/2026** contra os valores distintos
reais das três bases (`python -m uffs_pipeline.cli dominios`) e contra os
dicionários publicados pela própria UFFS no CKAN. Cada conjunto lista apenas
valores que de fato ocorrem na origem — nada de categorias hipotéticas.

Ao reexecutar o pipeline, qualquer valor novo cai em `OUTROS` e é reportado no
log por `alertar_categorias_nao_mapeadas`: nenhum registro é descartado em
silêncio. Se a origem publicar uma categoria nova, o alerta aparece e este
arquivo é o único lugar a corrigir.

Observação sobre acentuação: a Silver normaliza caixa e espaços, mas **não**
remove acentos. Os literais aqui precisam bater com a origem — daí `CONCLUÍDO`
e `REPROVADO POR MÉDIA E POR FALTAS` acentuados.
"""

from __future__ import annotations

import polars as pl

# --------------------------------------------------------------------------- #
# Situação de vínculo do estudante no curso (base: ingressantes)
#
# Domínio completo observado em Chapecó (16.845 vínculos):
#   CANCELADO 11.010 | CONCLUÍDO 3.091 | ATIVO 2.604 | ATIVO - FORMANDO 107
#   TRANCADO 27 | FORMADO 6
# --------------------------------------------------------------------------- #

# 'ATIVO - FORMANDO' é o estudante que cumpriu os créditos e aguarda colação;
# ainda é vínculo ativo, não conclusão.
VINCULO_ATIVO = {"ATIVO", "ATIVO - FORMANDO"}
VINCULO_CONCLUIDO = {"CONCLUÍDO", "FORMADO"}
# A origem não distingue desligamento por abandono de cancelamento a pedido:
# tudo chega como CANCELADO. A limitação vale para as Análises 4 a 6.
VINCULO_EVADIDO = {"CANCELADO"}
# Trancamento é suspensão temporária: não conta como evasão nem como conclusão.
VINCULO_TRANCADO = {"TRANCADO"}


def classificar_vinculo(coluna: str = "sit_matricula") -> pl.Expr:
    """`sit_matricula` de ingressantes -> ATIVO | CONCLUIDO | EVADIDO | TRANCADO | OUTROS."""
    return (
        pl.when(pl.col(coluna).is_in(list(VINCULO_ATIVO)))
        .then(pl.lit("ATIVO"))
        .when(pl.col(coluna).is_in(list(VINCULO_CONCLUIDO)))
        .then(pl.lit("CONCLUIDO"))
        .when(pl.col(coluna).is_in(list(VINCULO_EVADIDO)))
        .then(pl.lit("EVADIDO"))
        .when(pl.col(coluna).is_in(list(VINCULO_TRANCADO)))
        .then(pl.lit("TRANCADO"))
        .otherwise(pl.lit("OUTROS"))
        .alias("situacao_vinculo")
    )


# --------------------------------------------------------------------------- #
# Resultado do estudante na disciplina (base: historico)
#
# Domínio completo observado (1.293.405 matrículas, todos os campi — a consulta
# de domínios não filtra campus porque `historico` não tem `nome_campus`):
#   APROVADO 904.573 | REPROVADO POR NOTA E FALTA 116.752
#   REPROVADO POR NOTA 88.093 | TRANCADO 56.761 | CANCELADO 49.818
#   MATRICULADO 34.774 | REPROVADO 22.143 | REPROVADO POR MÉDIA E POR FALTAS 15.176
#   APROVADO POR NOTA 2.131 | DESISTENCIA 2.114 | REPROVADO POR FALTAS 1.070
# --------------------------------------------------------------------------- #

RESULTADO_APROVADO = {"APROVADO", "APROVADO POR NOTA"}

# A origem já distingue a causa da reprovação na maior parte dos casos. Os dois
# pares de rótulos abaixo são sinônimos herdados dos sistemas SGA e SIGAA.
RESULTADO_REPROVADO_NOTA = {"REPROVADO POR NOTA"}
RESULTADO_REPROVADO_FREQUENCIA = {"REPROVADO POR FALTAS"}
RESULTADO_REPROVADO_NOTA_E_FREQUENCIA = {
    "REPROVADO POR NOTA E FALTA",
    "REPROVADO POR MÉDIA E POR FALTAS",
}

# 'REPROVADO' sem qualificação (22.143 registros) é o único caso ambíguo:
# a causa é inferida por `freq_aluno`, e só nele o piso de frequência é aplicado.
RESULTADO_REPROVADO_AMBIGUO = {"REPROVADO"}

# Situações que não expressam desempenho: a matrícula não chegou a um resultado.
# Ficam fora do numerador e do denominador das taxas de reprovação.
RESULTADO_NEUTRO = {"TRANCADO", "CANCELADO", "MATRICULADO", "DESISTENCIA"}

# Frequência mínima para aprovação em disciplina presencial: art. 113 da
# Resolução nº 40/CGAE/CONSUNI/2022 da UFFS. Usada APENAS para desambiguar
# 'REPROVADO' puro (Análise 9).
FREQUENCIA_MINIMA = 75.0

# Faixa aritmeticamente possível para um percentual de frequência.
LIMITES_FREQUENCIA = (0.0, 100.0)


def frequencia_saneada(coluna: str = "freq_aluno") -> pl.Expr:
    """Traz a frequência para a faixa possível de um percentual, [0, 100].

    A origem calcula `freq_aluno = 100 - 100 * numero_faltas / ch_t_p`. As
    faltas são contadas sobre as aulas efetivamente registradas, e o denominador
    é a carga horária nominal: quando a turma registra mais horas-aula do que a
    carga (76 faltas num componente de 72), quem faltou a tudo fica com
    frequência **negativa**. Medidos 825 registros em Chapecó (0,19%), mínimo de
    -122,2%; 91% deles são do estudante com mais faltas da turma.

    - **Negativa vira 0%.** Frequência não pode ser menor que zero, e quem
      faltou mais horas do que o componente tem compareceu a zero. Anular
      tiraria da análise justamente os estudantes que nunca foram à aula.
    - **Acima de 100% vira nulo.** Não ocorre na base e não teria explicação
      (exigiria faltas negativas); se aparecer, é erro a investigar, não valor
      a aproveitar.

    A contagem dos dois casos vai para o log a cada execução.
    """
    minimo, maximo = LIMITES_FREQUENCIA
    return (
        pl.when(pl.col(coluna) < minimo)
        .then(pl.lit(minimo))
        .when(pl.col(coluna) > maximo)
        .then(None)
        .otherwise(pl.col(coluna))
        .alias(coluna)
    )


def classificar_resultado(
    coluna_situacao: str = "sit_matricula",
    coluna_frequencia: str = "freq_aluno",
) -> pl.Expr:
    """`sit_matricula` de historico -> categoria de resultado.

    Saídas: APROVADO | REPROVADO_NOTA | REPROVADO_FREQUENCIA |
            REPROVADO_NOTA_E_FREQUENCIA | NEUTRO | OUTROS.

    A ordem das cláusulas importa: os rótulos explícitos da origem são sempre
    respeitados, e a heurística de frequência só age sobre 'REPROVADO' puro.
    """
    return (
        pl.when(pl.col(coluna_situacao).is_in(list(RESULTADO_APROVADO)))
        .then(pl.lit("APROVADO"))
        .when(pl.col(coluna_situacao).is_in(list(RESULTADO_REPROVADO_NOTA_E_FREQUENCIA)))
        .then(pl.lit("REPROVADO_NOTA_E_FREQUENCIA"))
        .when(pl.col(coluna_situacao).is_in(list(RESULTADO_REPROVADO_FREQUENCIA)))
        .then(pl.lit("REPROVADO_FREQUENCIA"))
        .when(pl.col(coluna_situacao).is_in(list(RESULTADO_REPROVADO_NOTA)))
        .then(pl.lit("REPROVADO_NOTA"))
        .when(
            pl.col(coluna_situacao).is_in(list(RESULTADO_REPROVADO_AMBIGUO))
            & (pl.col(coluna_frequencia) < FREQUENCIA_MINIMA)
        )
        .then(pl.lit("REPROVADO_FREQUENCIA"))
        .when(pl.col(coluna_situacao).is_in(list(RESULTADO_REPROVADO_AMBIGUO)))
        .then(pl.lit("REPROVADO_NOTA"))
        .when(pl.col(coluna_situacao).is_in(list(RESULTADO_NEUTRO)))
        .then(pl.lit("NEUTRO"))
        .otherwise(pl.lit("OUTROS"))
        .alias("resultado")
    )


# --------------------------------------------------------------------------- #
# Modalidade de ingresso (base: ingressantes)
#
# Domínio observado em Chapecó, com os significados do dicionário publicado
# (recurso 5ff2919d-ca1c-4bc0-bb71-6a1ffd1b9918):
#   AC 5.687   — ampla concorrência
#   N/A 4.197  — "não se aplica": formas de ingresso sem cota (transferência,
#                retorno de graduado, aluno especial...). A Silver converte em
#                nulo, junto com os vazios da origem.
#   L1/L2/L5/L6/L9/L10/L13/L14 — cotas da Lei nº 12.711/2012, combinando
#                escola pública, renda, PPI e PcD.
#   LB_*/LI_*  — nomenclatura pós Lei nº 14.723/2023 (LB = baixa renda,
#                LI = independente de renda; sufixos EP, PPI, PCD, Q).
#                Ainda ausentes do dicionário publicado.
#   A1 144 / A2 38 / A2-I 27 — ações afirmativas próprias da UFFS: A1 é ensino
#                médio parcial em escola pública, A2 é vaga reservada a
#                indígenas (RANI/FUNAI).
# --------------------------------------------------------------------------- #

# Programas de ação afirmativa que não seguem o prefixo 'L' das leis de cotas.
ACAO_AFIRMATIVA_INSTITUCIONAL = {"A1", "A2", "A2-I"}


def agrupar_modalidade(coluna: str = "modalidade_inscricao") -> pl.Expr:
    """Reduz as modalidades a três grupos, para a leitura macro da Análise 1.

    A quebra detalhada por código de cota continua disponível na coluna original.

    'NAO SE APLICA' cobre tanto o literal `N/A` do dicionário quanto os nulos —
    a Silver já unifica os dois. Não é ausência de informação: é a marcação de
    que aquela forma de ingresso não passa por cota.
    """
    return (
        pl.when(pl.col(coluna).is_null() | (pl.col(coluna) == "N/A"))
        .then(pl.lit("NAO SE APLICA"))
        .when(pl.col(coluna) == "AC")
        .then(pl.lit("AMPLA CONCORRENCIA"))
        # Pega L1..L14 (Lei 12.711/2012) e LB_*/LI_* (Lei 14.723/2023).
        .when(pl.col(coluna).str.starts_with("L"))
        .then(pl.lit("ACAO AFIRMATIVA"))
        .when(pl.col(coluna).is_in(list(ACAO_AFIRMATIVA_INSTITUCIONAL)))
        .then(pl.lit("ACAO AFIRMATIVA"))
        .otherwise(pl.lit("OUTROS"))
        .alias("grupo_modalidade")
    )


# --------------------------------------------------------------------------- #
# Reentrada institucional (base: ingressantes)
#
# Responde à consideração da banca sobre evasão de curso versus evasão da
# universidade (docs/registro-decisoes.md, D-10). `ingressantes` tem uma linha
# por vínculo estudante-curso, e sem identificador de estudante um aluno que
# troca de curso vira um CANCELADO mais um vínculo novo — contado como evasão.
#
# Estas formas de ingresso comprovam que o vínculo NÃO é o primeiro na UFFS.
# Não capturam quem sai e reingressa pelo SISU (indistinguível de calouro),
# então o total é uma COTA INFERIOR da mobilidade interna, nunca a medida exata.
# Medido em Chapecó (29/08/2026): 2.162 de 16.201 vínculos, 13,3%.
# --------------------------------------------------------------------------- #

FORMA_INGRESSO_REENTRADA = {
    "TRANSFERÊNCIA INTERNA",  # trocou de curso dentro da UFFS
    "RETORNO DE GRADUADO",  # já concluiu uma graduação na instituição
    "RETORNO DE ALUNO-ABANDONO",  # abandonou e retornou formalmente
}


def marcar_reentrada(coluna: str = "forma_ingresso") -> pl.Expr:
    """Marca vínculos que comprovadamente não são o primeiro ingresso na UFFS."""
    return pl.col(coluna).is_in(list(FORMA_INGRESSO_REENTRADA)).alias("e_reentrada")


# --------------------------------------------------------------------------- #
# Retenção / progressão no curso
#
# Responde ao pedido da banca de "avaliar retenção" (P9). O parâmetro NÃO é
# estimado: `estruturas_curriculares_graduacao` publica `quant_semestres`
# (duração prevista) e `limite_semestres` (prazo máximo de integralização) por
# currículo. Nas 43 estruturas de Chapecó o limite é exatamente o dobro da
# duração prevista.
# --------------------------------------------------------------------------- #

# Fração do prazo máximo a partir da qual o vínculo entra em alerta. Não há
# norma publicada para esse corte — é uma escolha do painel, e por isso fica
# aqui, isolada e nomeada, em vez de embutida numa expressão.
FATOR_ALERTA_JUBILAMENTO = 0.8


def classificar_progressao(
    coluna_situacao: str = "situacao_vinculo",
    coluna_decorridos: str = "semestres_decorridos",
    coluna_previstos: str = "quant_semestres",
    coluna_limite: str = "limite_semestres",
) -> pl.Expr:
    """Classifica o andamento de um vínculo ativo em relação ao prazo do curso.

    Saídas: NO PRAZO | EM RETENCAO | RISCO DE JUBILAMENTO | SEM PARAMETRO,
    além de repassar CONCLUIDO / EVADIDO / TRANCADO já vindos do vínculo.

    Só vínculos ATIVO são avaliados: retenção é atraso de quem ainda cursa.
    `SEM PARAMETRO` marca o vínculo cujo currículo não foi encontrado — caso
    real dos cursos ausentes de `graduacao_matrizes`. Nunca é silencioso.
    """
    ativo = pl.col(coluna_situacao) == "ATIVO"
    tem_parametro = pl.col(coluna_previstos).is_not_null() & pl.col(coluna_decorridos).is_not_null()
    return (
        pl.when(~ativo)
        .then(pl.col(coluna_situacao))
        .when(ativo & ~tem_parametro)
        .then(pl.lit("SEM PARAMETRO"))
        .when(pl.col(coluna_decorridos) <= pl.col(coluna_previstos))
        .then(pl.lit("NO PRAZO"))
        .when(pl.col(coluna_decorridos) > pl.col(coluna_limite) * FATOR_ALERTA_JUBILAMENTO)
        .then(pl.lit("RISCO DE JUBILAMENTO"))
        .otherwise(pl.lit("EM RETENCAO"))
        .alias("progressao")
    )


# --------------------------------------------------------------------------- #
# Recortes de escopo
# --------------------------------------------------------------------------- #

# Estudantes especiais cursam poucos componentes e distorceriam a taxa de evasão
# (seção 4.3.2 da proposta). Vale só para as Visões 1 e 2.
TIPO_DISCENTE_ESCOPO = "REGULAR"

# Turmas não consolidadas ainda não têm resultado final lançado.
SITUACAO_TURMA_ESCOPO = "CONSOLIDADA"

# Piso de matriculados para um CCR entrar no ranking de gargalos (Análise 7),
# evitando que optativas de turma única dominem o topo por ruído estatístico.
MINIMO_MATRICULADOS_GARGALO = 50


def alertar_categorias_nao_mapeadas(df: pl.DataFrame, coluna: str, rotulo: str) -> None:
    """Loga valores que caíram em OUTROS. Falha silenciosa aqui é erro de tese."""
    from ..log import configurar

    log = configurar(__name__)
    nao_mapeados = df.filter(pl.col(coluna) == "OUTROS")
    if nao_mapeados.height:
        log.warning(
            "%s: %d registros não mapeados em '%s'. Revise regras.py.",
            rotulo,
            nao_mapeados.height,
            coluna,
        )
