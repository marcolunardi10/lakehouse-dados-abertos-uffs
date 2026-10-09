# Engenharia de Dados para Gestão Educacional

Pipeline *serverless* de Engenharia de Dados e painel analítico de indicadores de
trajetória discente sobre os Dados Abertos da UFFS — *Campus* Chapecó.

Trabalho de Conclusão de Curso — Ciência da Computação, UFFS Chapecó.
Autor: Marco Aurélio Lunardi · Orientadora: Profª Raquel Aparecida Pegoraro.
Proposta defendida no TCC I: [`docs/TCC1_Marco_Aurelio_Lunardi.pdf`](docs/TCC1_Marco_Aurelio_Lunardi.pdf).

---

## Arquitetura

```
  CKAN UFFS            GitHub Actions              Cloudflare R2            Render            Streamlit Cloud
 (datastore_        (orquestração + execução)     (data lakehouse)      (camada serviço)       (consumo)
  search_sql)
      │                        │                         │                     │                    │
      └── extração ──────────► Polars ────────────► bronze/ (raw)              │                    │
                               Polars ────────────► silver/ (limpo)            │                    │
                               Polars ────────────► gold/   (data marts) ──► DuckDB ──► FastAPI ──► Streamlit + Plotly
                                                                                  ▲
                                                                     UptimeRobot ─┘ (ping /health a cada 5 min)
```

Arquitetura medalhão sobre armazenamento de objetos, com processamento em
Polars, consulta analítica em DuckDB e painel desacoplado da regra de negócio
(*headless BI*). Toda a pilha opera em planos gratuitos.

## Estrutura do repositório

| Caminho | Responsabilidade | Onde roda |
|---|---|---|
| `pipeline/` | Ingestão CKAN → Bronze → Silver → Gold (Polars, Parquet, R2) e testes das regras de negócio | GitHub Actions |
| `api/` | Camada de serviço: DuckDB sobre Parquet no R2, exposto em rotas REST | Render |
| `dashboard/` | Painel gerencial (Streamlit + Plotly) | Streamlit Community Cloud |
| `notebooks/` | Análise exploratória do TCC I (`eda_escopo/` = bases do escopo; `eda_fora_escopo/` = investigação preliminar de outros domínios) | — |
| `docs/` | Proposta do TCC I e documentação técnica | — |
| `.github/workflows/` | Agendamento do pipeline, testes e *keep-alive* dos agendamentos | GitHub |

Cada aplicação implantável (`pipeline/`, `api/`, `dashboard/`) tem seu próprio
`requirements.txt`, para que cada plataforma instale apenas o que precisa.

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/arquitetura.md`](docs/arquitetura.md) | Zonas operacionais, layout do *data lake* e fluxo de execução |
| [`docs/dicionario-dados.md`](docs/dicionario-dados.md) | Esquemas, volumetrias, domínios das categóricas e limites da API do CKAN |
| [`docs/indicadores.md`](docs/indicadores.md) | Definição, fonte e fórmula de cada análise do painel |
| [`docs/registro-decisoes.md`](docs/registro-decisoes.md) | Decisões de projeto, achados sobre os dados e limitações, com evidência |

## Fontes de dados

Portal de Dados Abertos da UFFS (CKAN) — <https://dados.uffs.edu.br>. Seis
conjuntos, todos recortados para o *campus* Chapecó:

- `graduacao_estudantes_ingressantes`, `graduacao_turmas` e `graduacao_historico`
- `graduacao_matrizes`, `estruturas_curriculares_graduacao` e `graduacao_ccrs_matrizes`

Os identificadores dos recursos e o esquema esperado de cada um estão em
[`pipeline/config/datasets.yml`](pipeline/config/datasets.yml). A origem
republica semanalmente; o pipeline só reprocessa quando detecta atualização.

## Indicadores

| Visão | Análises |
|---|---|
| Demografia e ingresso | Modalidade de cota · gênero e raça ao longo do tempo · formas de ingresso |
| Fluxo acadêmico | Evasão de curso por curso, por modalidade e por coorte · retenção frente ao prazo de integralização |
| Desempenho | Gargalos curriculares · frequência × média final · perfil da reprovação |

As bases não expõem identificador de estudante. Por isso o grão é o vínculo
estudante-curso — daí "evasão de curso", e não evasão institucional — e não é
possível cruzar perfil demográfico com desempenho por disciplina.

## Reprodução

O projeto roda inteiramente em serviços gerenciados; não há passo de instalação
local. Para replicá-lo em outra instituição que publique dados em CKAN, é
preciso:

- um bucket no Cloudflare R2 e um token com acesso a ele;
- os segredos `R2_ENDPOINT`, `R2_ACCESS_KEY_ID` e `R2_SECRET_ACCESS_KEY` no
  GitHub Actions, que executa o pipeline;
- um serviço no Render para a API (definido em `render.yaml`), com as mesmas
  credenciais em modo somente leitura e uma `API_KEY`;
- o painel no Streamlit Community Cloud (`dashboard/app.py`), com
  `API_BASE_URL` e `API_KEY`.

Os identificadores em `pipeline/config/datasets.yml` são os da UFFS e precisam
ser trocados pelos da instituição de destino.

## Licença e ciência aberta

Repositório público, em atendimento à seção 4.5 da proposta (gestão e
disponibilização de dados e códigos).

- **Código** (`pipeline/`, `api/`, `dashboard/`, `notebooks/` e os workflows):
  licença [MIT](LICENSE) — pode ser usado, modificado e redistribuído, mantido o
  aviso de autoria.
- **Documentos** (a proposta do TCC I e os textos em `docs/`): permanecem com os
  direitos do autor e não são cobertos pela licença MIT. Podem ser citados com
  a devida referência.
- **Dados**: são da UFFS, publicados no seu Portal de Dados Abertos. Este
  repositório não os redistribui.
