"""Camada Bronze: extração do CKAN e persistência bruta em Parquet.

Contrato da Bronze: cópia fiel do escopo da pesquisa, sem qualquer regra de
negócio. Nenhuma coluna é renomeada, removida ou convertida — tudo entra como
string, exatamente como o JSON da API entregou. A tipagem é responsabilidade da
Silver. Isso garante que uma mudança de regra nunca exija nova requisição à
origem.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from ..armazenamento import CHAVE_PARTICAO_BRONZE, DataLake
from ..ckan import ClienteCKAN
from ..config import Dataset, carregar_catalogo
from ..log import configurar

log = configurar(__name__)

# Coluna técnica do DataStore, sem significado de negócio.
COLUNA_TECNICA = "_id"

# Índice de busca (tsvector) que o DataStore do CKAN mantém internamente. Não
# consta de nenhum dicionário publicado, não é campo do conjunto de dados e
# respondia por 74% do tamanho da Bronze (7,94 MB -> 2,04 MB por carga).
# Descartar é preservar o registro publicado, não mutilá-lo.
COLUNA_INDICE_BUSCA = "_full_text"


class ErroEstrutura(RuntimeError):
    """A origem mudou de esquema de um jeito que quebraria o pipeline."""


def validar_estrutura(dataset: Dataset, recebidas: list[str]) -> None:
    """Confere o esquema recebido contra o contrato do catálogo.

    Cumpre a checagem de integridade estrutural prevista na seção 4.2.4 da
    proposta. A assimetria é deliberada:

    - **coluna esperada que sumiu** é fatal, porque a transformação seguinte
      produziria nulos ou simplesmente não encontraria o campo;
    - **coluna nova** é apenas aviso: a origem acrescentar um campo não quebra
      nada, e a Bronze a preserva de qualquer modo.
    """
    if not dataset.colunas:
        log.warning("Dataset '%s' sem contrato de colunas no catálogo.", dataset.nome)
        return

    esperadas, presentes = set(dataset.colunas), set(recebidas)
    faltando = sorted(esperadas - presentes)
    novas = sorted(presentes - esperadas)

    if novas:
        log.warning(
            "Dataset '%s': %d coluna(s) nova(s) na origem: %s. "
            "Não impede a carga; atualize `colunas` em datasets.yml.",
            dataset.nome,
            len(novas),
            ", ".join(novas),
        )
    if faltando:
        raise ErroEstrutura(
            f"Dataset '{dataset.nome}': a origem deixou de fornecer "
            f"{len(faltando)} coluna(s) do contrato: {', '.join(faltando)}. "
            "Carga abortada para não gravar uma Bronze incompleta."
        )


def validar_chaves(dataset: Dataset, df: pl.DataFrame) -> None:
    """Garante que as colunas críticas existem e estão preenchidas.

    Uma chave nula não levanta exceção sozinha: ela quebra junção ou
    deduplicação em silêncio, mais adiante, e o número errado só aparece no
    painel. Por isso a checagem é aqui, na entrada.
    """
    for chave in dataset.chaves:
        if chave not in df.columns:
            raise ErroEstrutura(
                f"Dataset '{dataset.nome}': chave '{chave}' ausente na resposta da origem."
            )
        nulos = df[chave].null_count()
        if nulos:
            raise ErroEstrutura(
                f"Dataset '{dataset.nome}': chave '{chave}' tem {nulos} valor(es) nulo(s) "
                f"em {df.height} registros. Junção e deduplicação ficariam incorretas."
            )


def prefixo_bronze(dataset: str, data_carga: str) -> str:
    """Prefixo de uma partição de carga. Único lugar que monta esse caminho."""
    return f"bronze/{dataset}/{CHAVE_PARTICAO_BRONZE}={data_carga}/"


def caminho_bronze(dataset: str, data_carga: date, parte: int = 0) -> str:
    return f"{prefixo_bronze(dataset, data_carga.isoformat())}parte-{parte:03d}.parquet"


COLUNA_ATUALIZACAO = "data_atualizacao"

# Marcador escrito só depois que todas as páginas de uma carga foram gravadas.
# Sem ele, uma ingestão interrompida no meio deixaria uma partição parcial que a
# guarda `--se-atualizado` aceitaria como boa — e, com execução semestral, o
# lake ficaria incompleto por meses sem ninguém notar.
MARCADOR_COMPLETO = "_COMPLETO"


def particao_completa(dataset: str, data_carga: str, lake: DataLake) -> bool:
    return f"{prefixo_bronze(dataset, data_carga)}{MARCADOR_COMPLETO}" in lake.listar(
        prefixo_bronze(dataset, data_carga)
    )


def atualizacao_na_origem(dataset: Dataset, cliente: ClienteCKAN) -> str | None:
    """Carimbo de atualização publicado na origem, sem baixar os dados.

    Uma linha de resposta. É o que permite rodar o agendamento sem reingerir
    bases que não mudaram.
    """
    sql = f'SELECT max("{COLUNA_ATUALIZACAO}") AS carimbo FROM "{dataset.resource_id}"'
    for lote in cliente.consultar_paginado(sql):
        if lote:
            return lote[0].get("carimbo")
    return None


def atualizacao_no_lake(dataset: str, lake: DataLake) -> str | None:
    """Carimbo guardado na partição Bronze mais recente e **completa**.

    Devolve None se a última carga não terminou, para que a guarda force a
    reingestão em vez de aceitar dados parciais.
    """
    try:
        particao = lake.ultima_particao_bronze(dataset)
    except FileNotFoundError:
        return None
    if not particao_completa(dataset, particao, lake):
        log.warning(
            "Partição Bronze %s de '%s' está sem o marcador %s — carga anterior "
            "não terminou. Será reingerida.",
            particao,
            dataset,
            MARCADOR_COMPLETO,
        )
        return None
    df = lake.ler_parquet(f"{prefixo_bronze(dataset, particao)}parte-000.parquet")
    if COLUNA_ATUALIZACAO not in df.columns or not df.height:
        return None
    return df[COLUNA_ATUALIZACAO].max()


def ingerir_dataset(
    dataset: Dataset,
    lake: DataLake | None = None,
    cliente: ClienteCKAN | None = None,
    data_carga: date | None = None,
    apenas_se_atualizado: bool = False,
) -> list[str]:
    """Extrai um dataset e grava uma partição Bronze por data de carga.

    Com `apenas_se_atualizado`, compara o carimbo da origem com o da última
    partição e devolve lista vazia se nada mudou — sem baixar nenhuma linha.
    """
    lake = lake or DataLake()
    cliente = cliente or ClienteCKAN()
    data_carga = data_carga or date.today()

    if apenas_se_atualizado:
        origem = atualizacao_na_origem(dataset, cliente)
        local = atualizacao_no_lake(dataset.nome, lake)
        if origem is not None and origem == local:
            log.info(
                "Dataset '%s' inalterado na origem (carimbo %s). Ingestão dispensada.",
                dataset.nome,
                origem,
            )
            return []
        log.info("Dataset '%s': origem=%s, lake=%s — reingerindo.", dataset.nome, origem, local)

    log.info("Ingerindo '%s' (%s)...", dataset.nome, dataset.titulo)
    chaves: list[str] = []

    for parte, registros in enumerate(cliente.consultar_paginado(dataset.sql)):
        # Tudo como string: a Bronze não interpreta, apenas preserva.
        df = pl.DataFrame(registros, schema={c: pl.String for c in registros[0]}, strict=False)
        if COLUNA_INDICE_BUSCA in df.columns:
            df = df.drop(COLUNA_INDICE_BUSCA)

        if parte == 0:
            # O esquema é o mesmo em todas as páginas da carga; conferir na
            # primeira evita repetir a checagem 14 vezes no histórico.
            validar_estrutura(dataset, df.columns)
        validar_chaves(dataset, df)

        chave = caminho_bronze(dataset.nome, data_carga, parte)
        chaves.append(lake.escrever_parquet(df, chave))

    if not chaves:
        log.warning("Dataset '%s' retornou zero registros — nada gravado.", dataset.nome)
        return chaves

    # Só aqui a partição vira confiável. Qualquer falha acima deixa a carga sem
    # marcador, e a próxima execução a refaz em vez de aceitá-la.
    lake.escrever_marcador(
        f"{prefixo_bronze(dataset.nome, data_carga.isoformat())}{MARCADOR_COMPLETO}"
    )
    return chaves


def ingerir_todos(
    lake: DataLake | None = None,
    cliente: ClienteCKAN | None = None,
    apenas_se_atualizado: bool = False,
) -> dict[str, list[str]]:
    catalogo = carregar_catalogo()
    lake = lake or DataLake()
    cliente = cliente or ClienteCKAN()
    return {
        d.nome: ingerir_dataset(d, lake, cliente, apenas_se_atualizado=apenas_se_atualizado)
        for d in catalogo.todos()
    }
