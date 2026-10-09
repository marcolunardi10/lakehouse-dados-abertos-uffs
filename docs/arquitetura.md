# Arquitetura da solução

Implementação da arquitetura de referência descrita na seção 4.2.2 da proposta
do TCC I (Figura 4.1). As justificativas de cada escolha estão em
[`registro-decisoes.md`](registro-decisoes.md), citadas aqui pelo identificador.

## Zonas operacionais

| Zona | Tecnologia | Plano | Diretório |
|---|---|---|---|
| Origem | CKAN UFFS (`datastore_search_sql`) | público | — |
| Orquestração e execução | GitHub Actions (agendamento semanal) | gratuito | `.github/workflows/` |
| Processamento | Python + Polars | — | `pipeline/` |
| Armazenamento (*lakehouse*) | Cloudflare R2 + Apache Parquet | 10 GB gratuitos | — |
| Camada de serviço (*headless BI*) | FastAPI + DuckDB, no Render | gratuito | `api/` |
| Observabilidade | Logs do GitHub Actions + UptimeRobot | gratuito | — |
| Consumo | Streamlit + Plotly, no Streamlit Community Cloud | gratuito | `dashboard/` |

## Layout do data lake (arquitetura medalhão)

```
s3://uffs-lakehouse/
├── bronze/                                  # imutável, cópia fiel do escopo
│   └── <dataset>/data_carga=YYYY-MM-DD/
│       ├── parte-000.parquet
│       └── _COMPLETO                        # atesta que a carga terminou
├── silver/                                  # limpo e tipado
│   └── <dataset>/[ano=YYYY/]parte-000.parquet
└── gold/                                    # data marts por visão do painel
    ├── dim_curso/
    ├── visao1_demografia/
    ├── visao2_fluxo/
    ├── visao2_retencao/
    ├── visao3_desempenho/
    └── visao3_frequencia_media/
```

Os seis *datasets* da Bronze e da Silver são `ingressantes`, `turmas`,
`historico`, `matrizes`, `estruturas` e `ccrs_matrizes`.

**Bronze** guarda tudo como texto, exatamente como a API entregou, e é
particionada por data de carga: cada execução escreve uma partição nova. Isso
preserva o histórico de retratos e permite reprocessar sem nova requisição à
origem (D-01).

**Silver** é derivada determinística da Bronze, sobrescrita a cada execução.
Concentra tipagem, normalização de categóricas e deduplicação. Os conjuntos
volumosos são particionados por `ano`.

**Gold** contém tabelas pequenas e amplamente agregadas — **387 KB somando os
seis marts** —, o que viabiliza o aquecimento integral do cache da API na
inicialização.

Dimensões medidas em 19/09/2026: Bronze **2,03 MB** por carga, Silver 3,79 MB,
Gold 0,38 MB. O pipeline completo roda em cerca de três minutos.

## Fluxo de execução

1. **Agendamento semanal.** O workflow `pipeline.yml` roda às terças com
   `--se-atualizado`. A origem republica às segundas por volta das 02:30; se o
   carimbo `data_atualizacao` não mudou, o job encerra em poucos segundos sem
   transferir dados (D-25).
2. **Ingestão.** Consome `datastore_search_sql` com paginação de 32.000 linhas,
   já com o filtro de *campus* na própria consulta. Antes de gravar, **valida o
   esquema recebido contra o contrato do catálogo** — aborta se faltar coluna,
   avisa se houver coluna nova, exige chaves sem nulos (D-23) — e descarta o
   índice de busca `_full_text` (D-24). Ao terminar, grava o marcador
   `_COMPLETO` (D-14).
3. **Bronze → Silver.** Tipagem estrita, normalização de categóricas e
   deduplicação **apenas pela chave técnica `_id`** (D-03).
4. **Silver → Gold.** As regras de negócio, concentradas em `regras.py`,
   produzem um data mart por visão do painel (D-04).
5. **API.** O DuckDB consulta a Gold no R2 via `httpfs`. Os marts são aquecidos
   na inicialização e as respostas ficam em cache em memória com TTL.
6. **Painel.** Consome apenas a API; nenhuma regra de negócio vive nele.
7. **UptimeRobot** faz *ping* em `/health` a cada 5 minutos, evitando a
   suspensão por inatividade do plano gratuito do Render.

## Decisões de implementação

### Filtro de escopo empurrado para a origem

O endpoint SQL do CKAN aceita `JOIN` entre recursos. Como `historico` não possui
coluna de *campus*, o recorte de Chapecó é feito juntando com `turmas` já na
consulta remota: 431.012 linhas em vez de 1.293.405 — dois terços a menos de
tráfego (D-02).

Contrapartida: a Bronze deixa de ser uma cópia *integral* da origem e passa a
ser uma cópia fiel *do escopo da pesquisa*, coerente com a delimitação da seção
4.1 da proposta.

### Polars em toda a pilha

Todo o processamento de dados é Polars, da ingestão à apresentação: o Plotly 6
consome DataFrames Polars nativamente, e o painel não importa pandas em nenhuma
linha (D-21). O pandas permanece no ambiente do painel apenas como dependência
obrigatória do Streamlit.

Com 431 mil linhas no maior conjunto, a leitura é feita inteira em memória e
sobra folga. A API *lazy* do Polars (`scan_parquet`) fica como reserva caso o
volume cresça, por exemplo com a extensão a todos os *campi*.

### DuckDB na API em vez de um banco provisionado

O DuckDB roda embarcado no processo da FastAPI e consulta Parquet remoto
diretamente via `httpfs`. Isso elimina o custo e a manutenção de um servidor de
banco ativo em tempo integral — o requisito de sustentabilidade financeira da
seção 1.3 da proposta. As respostas são montadas sem pyarrow, para poupar
memória no plano gratuito do Render (D-18).

### Cliente CKAN tolerante a quedas de conexão

O portal derruba cerca de 10–15% das conexões TLS. O reset atinge a conexão, não
a consulta, e envenena o *pool keep-alive*: retentar no nível da aplicação não
basta, porque a sessão devolve o socket morto. O cliente usa a política `Retry`
do urllib3, renova a sessão a cada tentativa e envia a consulta por POST (D-15).

### Falha silenciosa tratada como defeito

Três erros deste projeto corromperam números sem levantar exceção. Em resposta,
a tipagem registra erro quando uma coluna com conteúdo fica inteiramente nula
após a conversão (D-16), categorias não previstas vão para `OUTROS` com aviso, e
toda linha perdida em junção é contada no log.

### Gestão de segredos

Nenhuma credencial no código. As chaves do R2 e a `API_KEY` vivem nos cofres de
segredos das três plataformas (GitHub Actions Secrets, Render Environment,
Streamlit Secrets). As variáveis necessárias estão listadas na seção
"Reprodução" do [`README`](../README.md).

### Testes

A suíte em `pipeline/tests/` é inteiramente offline — nenhuma chamada ao CKAN ou
ao R2 — e roda a cada *push* pelo workflow `testes.yml`. Ela fixa os domínios
reais das bases e as decisões metodológicas, de modo que uma alteração
descuidada nas regras de negócio não passe despercebida (D-26).

### Keep-alive dos agendamentos

O GitHub desativa workflows agendados em repositórios sem *commits* por 60 dias
(risco mapeado na seção 4.2.8 da proposta). O workflow `keep-alive.yml` grava em
`.github/keep-alive.log` nos dias 1 e 15 de cada mês e faz *commit*, mantendo o
agendamento vivo após o fim do desenvolvimento ativo.
