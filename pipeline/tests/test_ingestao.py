"""Testes do contrato de esquema da ingestão (seção 4.2.4 da proposta)."""

from __future__ import annotations

import polars as pl
import pytest

from uffs_pipeline.config import Dataset, carregar_catalogo
from uffs_pipeline.ingestao import bronze


def _dataset(colunas: tuple[str, ...], chaves: tuple[str, ...] = ()) -> Dataset:
    return Dataset(
        nome="fake",
        titulo="Base de teste",
        pacote="pacote",
        resource_id="rid",
        dicionario_resource_id=None,
        sql="SELECT 1",
        colunas=colunas,
        chaves=chaves,
    )


# --------------------------------------------------------------------------- #
# Estrutura
# --------------------------------------------------------------------------- #


def test_esquema_intacto_passa():
    d = _dataset(("a", "b", "c"))
    bronze.validar_estrutura(d, ["a", "b", "c"])


def test_ordem_das_colunas_nao_importa():
    d = _dataset(("a", "b", "c"))
    bronze.validar_estrutura(d, ["c", "a", "b"])


def test_coluna_nova_apenas_avisa(caplog):
    """A origem acrescentar campo não quebra nada, e a Bronze o preserva."""
    d = _dataset(("a", "b"))
    bronze.validar_estrutura(d, ["a", "b", "campo_novo"])
    assert "campo_novo" in caplog.text


def test_coluna_ausente_aborta_a_carga():
    d = _dataset(("a", "b", "c"))
    with pytest.raises(bronze.ErroEstrutura, match="c"):
        bronze.validar_estrutura(d, ["a", "b"])


def test_mensagem_de_erro_nomeia_todas_as_colunas_perdidas():
    d = _dataset(("a", "b", "c", "d"))
    with pytest.raises(bronze.ErroEstrutura) as erro:
        bronze.validar_estrutura(d, ["a"])
    for coluna in ("b", "c", "d"):
        assert coluna in str(erro.value)


def test_dataset_sem_contrato_avisa_em_vez_de_falhar(caplog):
    bronze.validar_estrutura(_dataset(()), ["qualquer"])
    assert "sem contrato" in caplog.text


# --------------------------------------------------------------------------- #
# Chaves
# --------------------------------------------------------------------------- #


def test_chaves_preenchidas_passam():
    d = _dataset(("_id", "ano"), chaves=("_id", "ano"))
    bronze.validar_chaves(d, pl.DataFrame({"_id": ["1", "2"], "ano": ["2026", "2026"]}))


def test_chave_ausente_aborta():
    d = _dataset(("_id",), chaves=("_id",))
    with pytest.raises(bronze.ErroEstrutura, match="_id"):
        bronze.validar_chaves(d, pl.DataFrame({"outra": ["x"]}))


def test_chave_com_nulo_aborta():
    """Chave nula não levanta exceção sozinha: corrompe junção em silêncio."""
    d = _dataset(("_id",), chaves=("_id",))
    df = pl.DataFrame({"_id": ["1", None, "3"]})
    with pytest.raises(bronze.ErroEstrutura, match="nulo"):
        bronze.validar_chaves(d, df)


def test_dataset_sem_chaves_declaradas_nao_falha():
    bronze.validar_chaves(_dataset(("a",)), pl.DataFrame({"a": [None]}))


# --------------------------------------------------------------------------- #
# Catálogo real
# --------------------------------------------------------------------------- #


def test_catalogo_tem_as_seis_bases():
    catalogo = carregar_catalogo()
    assert set(catalogo.datasets) == {
        "ingressantes",
        "turmas",
        "historico",
        "matrizes",
        "estruturas",
        "ccrs_matrizes",
    }


@pytest.mark.parametrize("nome", [
    "ingressantes", "turmas", "historico", "matrizes", "estruturas", "ccrs_matrizes",
])
def test_todo_dataset_declara_contrato_e_chaves(nome):
    dataset = carregar_catalogo().obter(nome)
    assert dataset.colunas, f"{nome} sem `colunas` no catálogo"
    assert dataset.chaves, f"{nome} sem `chaves` no catálogo"


@pytest.mark.parametrize("nome", [
    "ingressantes", "turmas", "historico", "matrizes", "estruturas", "ccrs_matrizes",
])
def test_chaves_sao_subconjunto_das_colunas(nome):
    dataset = carregar_catalogo().obter(nome)
    assert set(dataset.chaves) <= set(dataset.colunas)


@pytest.mark.parametrize("nome", [
    "ingressantes", "turmas", "historico", "matrizes", "estruturas", "ccrs_matrizes",
])
def test_id_e_sempre_chave(nome):
    """`_id` é a única chave de deduplicação — sem ela a Silver não protege nada."""
    assert bronze.COLUNA_TECNICA in carregar_catalogo().obter(nome).chaves


def test_indice_de_busca_nao_faz_parte_de_nenhum_contrato():
    """`_full_text` é índice interno do CKAN e é descartado na ingestão."""
    for dataset in carregar_catalogo().todos():
        assert bronze.COLUNA_INDICE_BUSCA not in dataset.colunas


def test_caminho_da_bronze_usa_a_particao_declarada():
    caminho = bronze.prefixo_bronze("turmas", "2026-09-19")
    assert caminho == f"bronze/turmas/{bronze.CHAVE_PARTICAO_BRONZE}=2026-09-19/"
