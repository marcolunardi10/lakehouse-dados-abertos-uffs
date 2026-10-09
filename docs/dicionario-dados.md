# Dicionário de dados — fontes CKAN

Portal: <https://dados.uffs.edu.br> · Endpoint: `/api/3/action/datastore_search_sql`

Esquemas e volumetrias verificados diretamente na origem. Salvo indicação em
contrário, os números são da carga de **29/08/2026**; a seção 6.1 traz também a
de 19/09/2026. Os identificadores dos recursos e o esquema esperado de cada base
estão versionados em [`pipeline/config/datasets.yml`](../pipeline/config/datasets.yml).

O escopo da pesquisa é o *campus* **Chapecó**.

---

## 1. Estudantes Ingressantes da Graduação — `ingressantes`

- Pacote: `graduacao_estudantes_ingressantes`
- Recurso (dados): `bee823cd-7826-4dc6-95f7-dd13dfe609f3`
- Recurso (dicionário): `5ff2919d-ca1c-4bc0-bb71-6a1ffd1b9918`
- Volumetria total: **42.870 registros** (todos os *campi*) · Chapecó: **16.845**
- Granularidade: um registro por **vínculo** de estudante em um curso — não por
  estudante (ver seção 7)

| Coluna | Tipo | Observações |
|---|---|---|
| `_id` | int | chave técnica do DataStore, não é matrícula |
| `tipo_discente` | text | `REGULAR` / `ESPECIAL` — as métricas de fluxo usam só `REGULAR` |
| `raca` | text | grafias próprias da origem, diferentes das do IBGE (seção 6.5) |
| `genero` | text | `M` / `F` |
| `ano_ingresso` | int4 | |
| `semestre_ingresso` | int4 | 1 ou 2 |
| `forma_ingresso` | text | 17 valores; há descontinuidade de rótulos em 2023–2024 (seção 6.5) |
| `modalidade_inscricao` | text | `AC`, `N/A` e três gerações de códigos de cota (seção 6.4) |
| `modalidade_vaga_ocupada` | text | frequentemente nulo |
| `sit_matricula` | text | situação **atual** do vínculo (seção 6.2) — não há data de saída |
| `nome_campus` | text | filtro de escopo: `Chapecó` |
| `cod_uffs` | text | código UFFS do **curso** |
| `nome_curso` | text | vem em caixa mista (`Ciência Da Computação`); a Silver canoniza em caixa alta |
| `turno` | text | nulo para os estudantes `ESPECIAL` |
| `matriz` | text | ex.: `2026/1` — ano e período de entrada em vigor do currículo |
| `data_atualizacao` | timestamp | carimbo da carga na origem, com fração de segundo |

## 2. Turmas da Graduação — `turmas`

- Pacote: `graduacao_turmas`
- Recurso (dados): `670bc744-2570-4e2a-b73b-3acf2039a7c1`
- Recurso (dicionário): `d05954c6-9af5-4641-bdc8-88d95949c760`
- Volumetria total: **48.308 registros** · Chapecó: **14.805**
- Granularidade: uma turma ofertada (`ano`, `semestre`, `cod_ccr`, `id_unico_turma`)

| Coluna | Tipo | Observações |
|---|---|---|
| `nome_campus` | text | **única fonte de campus para o histórico** (seção 7) |
| `ano`, `semestre` | int4 | |
| `cod_ccr`, `nome_ccr`, `ch_ccr` | text/text/numeric | componente curricular. Um mesmo `nome_ccr` tem vários `cod_ccr` (seção 2.1) |
| `id_unico_turma` | int4 | chave de junção com `historico` |
| `id_relativo_turma` | int4 | |
| `quantidade_cursos` | int4 | 0 em oito turmas de Chapecó, que ficam sem curso declarado |
| `cod_uffs_cursos_turma` | text | lista separada por `;` |
| `cursos_turma` | text | lista separada por `;`, em caixa alta |
| `quantidade_docentes`, `lista_docentes`, `lista_ch_docentes` | int4/text/text | listas separadas por `;` |
| `vagas_turma`, `qtd_inscritos`, `qtd_passaram_pela_turma`, `qtd_aprovados` | int4 | agregados já calculados na origem |
| `sit_turma` | text | `CONSOLIDADA` / `ABERTA` — o desempenho usa só as consolidadas |
| `data_atualizacao` | timestamp | |

### 2.1 Um componente, vários códigos

Dos 1.198 nomes de componente curricular ofertados em Chapecó, **271 (22,6%)
aparecem com mais de um `cod_ccr`**. Há duas causas distintas:

- **versões sucessivas da matriz curricular** — Geometria Analítica foi `GEX004`
  (2010–2018), depois `GEX195` (2013–2025) e hoje é `GEX1142` (2025–2026), sempre
  para Ciência da Computação e Engenharia Ambiental, com períodos sobrepostos na
  transição;
- **oferta por cursos distintos** — `GEX503` é a Geometria Analítica da
  Matemática. `TRABALHO DE CONCLUSÃO DE CURSO I` chega a 15 códigos.

Agrupar por código fragmenta a disciplina. Por isso o *ranking* de gargalos
agrega por **nome** (ver `indicadores.md`).

## 3. Matriculados nas Turmas da Graduação — `historico`

> Base restabelecida pela UFFS após a solicitação LAI/Fala.BR
> NUP 23546.064378/2026-17 (atendida em 08/06/2026).

- Pacote: `graduacao_historico`
- Recurso (dados): `3c31f55b-be46-4ddc-9cd5-f10f614f06bc`
- Recurso (dicionário): `ceda2d3e-fa59-4f07-a6a0-27c05c26fac8`
- Volumetria total: **1.293.405 registros** · Chapecó: **431.012**
- Granularidade: uma matrícula de estudante em uma turma

| Coluna | Tipo | Observações |
|---|---|---|
| `ano`, `semestre` | int4 | |
| `cod_curso` | text | código UFFS do curso (equivale a `ingressantes.cod_uffs`) |
| `cod_ccr` | text | |
| `id_unico_turma` | **text** | tipagem divergente de `turmas.id_unico_turma` (int4) — exige *cast* |
| `ch_t_p` | int4 | carga horária teórica + prática, em **horas-aula** — não é a mesma unidade de `turmas.ch_ccr` (seção 3.1) |
| `numero_faltas` | int4 | |
| `freq_aluno` | numeric | percentual de frequência, **derivado** de faltas e carga horária; pode ser negativo (seção 3.1) |
| `media_final` | numeric | |
| `sit_matricula` | text | resultado na disciplina (seção 6.3) |
| `data_atualizacao` | timestamp | |

### 3.1 Frequências impossíveis

`freq_aluno` não é um dado colhido, e sim calculado pela origem:

```
freq_aluno = 100 − 100 × numero_faltas / ch_t_p
```

A fórmula foi conferida contra os dados. O problema é que **nada impede
`numero_faltas` de superar `ch_t_p`** — há registros com 76 faltas numa turma de
72 horas-aula. Nesses casos a frequência sai negativa.

| Medida | Valor |
|---|---|
| Matrículas com frequência fora de [0, 100] | **825** (0,19% de 431.012), em 322 turmas |
| Menor valor observado | **−122,2%** |
| Situação predominante | 823 são `REPROVADO POR NOTA E FALTA`; 808 têm média final 0 |
| Valores acima de 100 | nenhum |

O pipeline fixa esses valores em **0%** (`regras.frequencia_saneada`) e registra
a contagem no log a cada execução. O motivo está abaixo: quase todos são de
estudantes que faltaram a todas as aulas.

**Não é diferença de unidade.** As duas colunas de carga horária estão, de fato,
em unidades diferentes: `historico.ch_t_p` vale exatamente **1,2 ×**
`turmas.ch_ccr` em 99,97% das matrículas (72 contra 60, 54 contra 45), isto é,
`ch_t_p` está em horas-aula de 50 minutos e `ch_ccr` em horas. Mas a fórmula da
frequência usa `ch_t_p`, a mesma unidade em que as faltas são lançadas — a
presença é registrada por hora-aula (art. 111 da Resolução nº
40/CGAE/CONSUNI/2022). A conta é coerente; quem calcular frequência dividindo
faltas por `ch_ccr` é que erra, em 20%.

**A causa é o denominador.** As faltas são contadas sobre as aulas efetivamente
registradas na turma, e o denominador é a carga horária nominal do componente.
Quando a turma registra mais horas-aula do que a carga nominal, quem faltou a
tudo passa de 100% de ausência:

- **752 dos 825** casos (91%) são do estudante com **mais faltas da turma** —
  quem não compareceu a nenhuma aula;
- o excesso é quase sempre pequeno: em 733 casos (89%) as faltas superam a carga
  em até 20%, e o mais comum são 1 a 4 horas-aula a mais (75 ou 76 faltas num
  componente de 72);
- os 60 casos extremos, com faltas acima de 1,5 vez a carga, concentram-se em
  **20 turmas**, várias delas de três componentes de Filosofia que registram
  128 a 160 faltas para 72 horas-aula, em anos seguidos. A causa desse registro
  em dobro não é identificável pelos dados;
- o fenômeno é do sistema acadêmico antigo: chega a 1,26% das matrículas em
  2011, cai ano a ano e praticamente some a partir de 2023 (um caso em 2024,
  nenhum em 2023, 2025 e 2026).

Consequência para a leitura: nas turmas que registraram mais aulas que a carga
nominal, a frequência de **todos** os estudantes fica levemente subestimada, não
só a dos 825 que cruzaram o zero.

## 4. Bases de estrutura curricular

Três bases acrescentadas ao escopo original. Todas com DataStore ativo e
populado.

### 4.1 `matrizes` — Matrizes Curriculares da Graduação

- Pacote: `graduacao_matrizes` · Recurso: `857e9283-5f9f-474a-b47b-5dd4f0f9710a`
- Volumetria: **63 registros** · Chapecó: **21**
- Granularidade: uma matriz por curso **e turno** (Administração tem matutino e
  noturno como matrizes distintas)

| Coluna | Tipo | Observações |
|---|---|---|
| `id_matriz` | int4 | chave para `estruturas` |
| `campus` | text | **atenção**: chama-se `campus`, não `nome_campus` |
| `cod_curso` | text | equivale a `ingressantes.cod_uffs` |
| `nome_curso` | text | em caixa alta |
| `turno`, `grau_academico`, `situacao` | text | situação: `Em Atividade` / `Em Extinção` |
| `enfase`, `data_inicio_funcionamento` | text/date | |

É a **dimensão de curso oficial** (seção 5).

### 4.2 `estruturas` — Estruturas Curriculares da Graduação

- Pacote: `estruturas_curriculares_graduacao` · Recurso: `ed0d3da3-d1d0-4b93-84cf-6975bbebca83`
- Volumetria: **160 registros** · Chapecó: **43**
- Granularidade: um currículo por matriz e período de entrada em vigor
- Chave `(id_matriz, ano_entrada_vigor, periodo_entrada_vigor)` verificada
  **única** (160/160)

| Coluna | Tipo | Observações |
|---|---|---|
| `id_curriculo`, `id_matriz` | int4 | |
| `ano_entrada_vigor`, `periodo_entrada_vigor` | int4 | a Silver concatena em `matriz` (`'2026/1'`) para casar com `ingressantes.matriz` |
| `em_andamento` | text | `SIM` marca o currículo vigente |
| **`quant_semestres`** | int4 | duração prevista — base do indicador de retenção |
| **`limite_semestres`** | int4 | prazo máximo de integralização; nas 43 estruturas de Chapecó é **exatamente o dobro** de `quant_semestres` |
| `ch_total`, `ch_obrigatoria`, `ch_optativa`, `ch_eletiva`, `ch_accs` | int4 | |
| `ch_max_sem`, `ch_min_sem`, `ch_1o_nivel` | int4 | |

### 4.3 `ccrs_matrizes` — CCRs das Estruturas Curriculares

- Pacote: `graduacao_ccrs_matrizes` · Recurso: `c51852e5-c5ae-4ce2-97d8-9261033b8877`
- Volumetria: **7.609 registros** (todos os *campi* — a base não tem coluna de
  campus e `cod_cursos` é lista separada por `;`, então não há filtro possível
  na origem)
- Granularidade: um CCR, com listas paralelas de currículos e níveis

| Coluna | Tipo | Observações |
|---|---|---|
| `cod_ccr`, `nome_ccr`, `unid_responsavel` | text | |
| `ids_curriculos` | text | lista `;` — paralela a `niveis_oferta` |
| `niveis_oferta` | text | fase do curso em que o CCR é previsto, lista `;` |
| `cod_cursos`, `nome_cursos` | text | listas `;` |
| `ch_total` e 10 colunas de carga horária detalhada | int4 | presencial/EAD × teórica/prática/extensão/orientação |

> **Não há campo de obrigatório/optativo.** 1.445 CCRs têm `niveis_oferta = 0`,
> contra centenas em cada fase de 1 a 10 — a leitura provável é que 0 marca
> componentes sem fase fixa (optativos/eletivos), mas isso é **inferência**, não
> documentação da origem.

### 4.4 Caminho de junção para retenção

```
ingressantes(cod_uffs, turno) ──► matrizes(cod_curso, turno) ──► id_matriz
                                                                     │
ingressantes.matriz ('2026/1') ──────────────────────────────────────┤
                                                                     ▼
                                          estruturas(id_matriz, matriz)
                                          └─► quant_semestres, limite_semestres
```

Cobertura medida: **2.522 de 2.677 vínculos ativos (94,2%)**. Os 155 restantes
são de três cursos ausentes de `graduacao_matrizes` — Ciências Econômicas
(1610), Engenharia Civil (1310) e Educação Especial Inclusiva (1750) — e são
classificados como `SEM PARAMETRO`, nunca descartados.

## 5. O `graduacao_cursos` vazio e a dimensão de curso

O pacote `graduacao_cursos` (recurso `50224c6a-5b9b-47fb-99c1-280293d8e960`)
seria o candidato natural a tabela de dimensão de curso, mas seu DataStore está
**vazio (0 registros)** — o esquema está publicado, os dados não.

`graduacao_matrizes` (seção 4.1) cumpre o papel, com a vantagem de trazer também
grau acadêmico e situação do curso. O mart `gold/dim_curso` usa `matrizes` como
fonte autoritativa e **complementa** com os cursos que só existem no histórico
de `ingressantes` — Ciências Econômicas, Engenharia Civil e Educação Especial
Inclusiva —, que de outro modo sumiriam dos filtros do painel. Resultado: 24
linhas (21 oficiais + 3 complementadas).

### Escopo do catálogo

A proposta do TCC I (seção 2.1.4.1) delimitava três bases. O catálogo tem
**seis**: as três originais mais as três de estrutura curricular. A ampliação
está amparada pela cláusula de flexibilização (seção 4.3.4 da proposta) e não
muda o desenho — mesma origem, mesma API, mesmo pipeline.

## 6. Domínios das categóricas

Colhidos com `python -m uffs_pipeline.cli dominios` e conferidos contra os
dicionários publicados pela UFFS. São a base literal de
`pipeline/src/uffs_pipeline/transformacao/regras.py`: **nenhum valor observado
cai em `OUTROS`**, e a suíte de testes fixa essa garantia.

### 6.1 Volumetria do recorte de Chapecó

| Base | Total (todos os *campi*) | Chapecó em 29/08/2026 | Chapecó em 19/09/2026 |
|---|---:|---:|---:|
| `ingressantes` | 42.870 | **16.845** (16.201 `REGULAR` + 644 `ESPECIAL`) | 16.871 |
| `turmas` | 48.308 | **14.805** (14.287 `CONSOLIDADA` + 518 `ABERTA`) | 14.804 |
| `historico` | 1.293.405 | **431.012** | 431.218 |

A origem republica as seis bases num lote só, às segundas-feiras por volta das
02:30 — carimbos `data_atualizacao` de 24/08, 14/09 e 05/10/2026, todos
segunda-feira. A carga de 08/10/2026 trouxe 431.223 matrículas no histórico.

### 6.2 `ingressantes.sit_matricula` → vínculo

| Valor | n (Chapecó) | Classificação |
|---|---:|---|
| `CANCELADO` | 11.010 | EVADIDO |
| `CONCLUÍDO` | 3.091 | CONCLUIDO |
| `ATIVO` | 2.604 | ATIVO |
| `ATIVO - FORMANDO` | 107 | ATIVO |
| `TRANCADO` | 27 | TRANCADO |
| `FORMADO` | 6 | CONCLUIDO |

A origem **não distingue** abandono de cancelamento a pedido nem de
transferência: tudo chega como `CANCELADO`. A evasão medida é, portanto,
"vínculo encerrado sem conclusão", sem separar a motivação.

### 6.3 `historico.sit_matricula` → resultado na disciplina

| Valor | n (todos os *campi*) | Classificação |
|---|---:|---|
| `APROVADO` | 904.573 | APROVADO |
| `REPROVADO POR NOTA E FALTA` | 116.752 | REPROVADO_NOTA_E_FREQUENCIA |
| `REPROVADO POR NOTA` | 88.093 | REPROVADO_NOTA |
| `TRANCADO` | 56.761 | NEUTRO |
| `CANCELADO` | 49.818 | NEUTRO |
| `MATRICULADO` | 34.774 | NEUTRO |
| `REPROVADO` | 22.143 | desambiguado por `freq_aluno` |
| `REPROVADO POR MÉDIA E POR FALTAS` | 15.176 | REPROVADO_NOTA_E_FREQUENCIA |
| `APROVADO POR NOTA` | 2.131 | APROVADO |
| `DESISTENCIA` | 2.114 | NEUTRO |
| `REPROVADO POR FALTAS` | 1.070 | REPROVADO_FREQUENCIA |

Dois pontos relevantes para o perfil da reprovação:

1. **A origem já rotula a causa da reprovação** em 98,3% dos casos. Inferir a
   causa pelo piso de frequência só é necessário para os 22.143 registros de
   `REPROVADO` sem qualificação.
2. **Há pares de rótulos sinônimos** herdados dos sistemas SGA e SIGAA
   (`REPROVADO POR NOTA E FALTA` ≡ `REPROVADO POR MÉDIA E POR FALTAS`).
   Reprovação simultânea por nota e por frequência tem categoria própria em vez
   de ser forçada em uma das duas causas.

### 6.4 `ingressantes.modalidade_inscricao` → grupo

`AC` (5.687) → ampla concorrência. `N/A` (4.197) → **não se aplica**: formas de
ingresso sem cota, conforme o dicionário oficial — não é dado faltante.

Ação afirmativa reúne três gerações de nomenclatura:

- `L1`, `L2`, `L5`, `L6`, `L9`, `L10`, `L13`, `L14` — Lei nº 12.711/2012;
- `LB_EP`, `LB_PPI`, `LB_PCD`, `LB_Q`, `LI_EP`, `LI_PPI`, `LI_PCD` — Lei nº
  14.723/2023 (`LB` = baixa renda, `LI` = independente de renda). **Ainda não
  constam do dicionário publicado**, que só documenta o esquema antigo;
- `A1` (144), `A2` (38), `A2-I` (27) — programas próprios da UFFS: `A1` é ensino
  médio parcial em escola pública, `A2` é vaga reservada a indígenas.

### 6.5 Demais categóricas

- `raca`: `Branco` 11.342 · `Pardo` 2.783 · `Negro` 952 · `Indígeno` 897 ·
  `Não Informado` 844 · `Amarelo (de origem oriental)` 19 ·
  `Remanescente de quilombo` 8.
  As grafias **divergem das categorias do IBGE** (`Negro` em vez de `Preto`,
  `Indígeno` em vez de `Indígena`). O painel preserva os rótulos da origem.
- `genero`: apenas `F` (8.919) e `M` (7.926) — binário, sem categoria aberta.
- `turno`: 644 nulos, número **idêntico** ao de estudantes `ESPECIAL`. Como as
  métricas de demografia e fluxo filtram `tipo_discente = REGULAR`, os nulos não
  chegam aos marts.
- `forma_ingresso`: `ENEM` vai de 746 ingressantes em 2022 a **zero em 2024**,
  exatamente quando `SISU` (346) e `PROCESSO SELETIVO SIMPLIFICADO` (282)
  aparecem. Só pelos dados não é possível saber se houve mudança real na
  política de ingresso ou renomeação de rótulo na migração para o SIGAA.

---

## 7. Modelo relacional e chaves de junção

```
ingressantes ──(cod_uffs, turno)──► matrizes ──(id_matriz)──► estruturas
      │                                 │
      └──── nome_curso ─────────────────┴──► dim_curso
                                             (matrizes + cursos só do histórico)

historico ──(ano, semestre, cod_ccr, id_unico_turma::int)──► turmas
                                                              └─► nome_campus, cursos_turma
```

### Restrições analíticas

1. **Não há identificador de estudante em nenhuma base.** Nem `ingressantes` nem
   `historico` expõem matrícula ou pseudônimo — decorrência da anonimização
   LGPD. Consequências:
   - é **impossível** ligar o perfil demográfico de um estudante ao seu
     desempenho por disciplina: demografia, ingresso e fluxo vêm de
     `ingressantes`; gargalos, frequência e reprovação vêm de
     `historico` ⋈ `turmas`;
   - o grão de `ingressantes` é o vínculo, não a pessoa — quem troca de curso
     aparece como um cancelamento mais um vínculo novo;
   - dois estudantes de mesmo curso, coorte, cota, gênero, raça e situação geram
     linhas idênticas. Deduplicar por esses atributos descartaria 52% dos
     ingressantes; a única chave de deduplicação segura é `_id`.
2. **`historico` não tem `nome_campus`.** O recorte de Chapecó só é possível pela
   junção com `turmas`.
3. **`id_unico_turma` tem tipo divergente** entre as bases (`text` × `int4`).
4. **`sit_matricula` é reaproveitado** com semânticas diferentes: vínculo no
   curso em `ingressantes`, resultado na disciplina em `historico`.
5. **Turma compartilhada conta uma vez por curso.** Só 225 das 14.288 turmas
   consolidadas (carga de 19/09/2026) atendem mais de um curso, mas isso infla
   em 2,6% o total de matrículas quando somado sem filtro de curso (429.622
   contra 418.740).

## 8. Limites da API CKAN

| Restrição | Valor medido | Tratamento |
|---|---|---|
| Máximo de linhas por requisição | **32.000** — o servidor trunca em silêncio pedidos maiores | paginação `LIMIT`/`OFFSET` com página de 32.000 |
| `JOIN` entre recursos | **suportado** — validado com `historico ⋈ turmas` filtrando `nome_campus = 'Chapecó'` | o filtro de escopo vai na própria consulta: 431.012 linhas em vez de 1.293.405 |
| Instabilidade de conexão | resets de TLS em ~10–15% das requisições. O reset atinge a conexão, não a consulta, e envenena o *pool keep-alive*: as chamadas seguintes falham em cascata | política `Retry` do urllib3 no nível do socket, sessão renovada a cada tentativa e consulta por POST |
| Coluna `_full_text` | índice de busca interno do DataStore, devolvido em todo `SELECT *`; respondia por 74% do volume baixado | descartada na ingestão — não consta de nenhum dicionário publicado |
