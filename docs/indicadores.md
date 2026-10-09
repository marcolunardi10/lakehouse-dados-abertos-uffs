# Catálogo de indicadores do painel

As nove análises definidas na seção 4.3 da proposta do TCC I, mais o indicador
de retenção acrescentado depois, traduzidos em contrato técnico: fonte, chave de
agregação, fórmula e rota da API.

Filtros globais da barra lateral: **curso**, **ano de ingresso** e **semestre de
ingresso**, aplicados às três visões. Escopo fixo: *campus* Chapecó.

As justificativas de cada escolha estão em
[`registro-decisoes.md`](registro-decisoes.md), citadas aqui pelo identificador
(D-nn, A-nn, L-nn).

---

## Visão 1 — Retrato demográfico e ingresso

Data mart: `gold/visao1_demografia/` · Fonte: `silver/ingressantes`, apenas
`tipo_discente = 'REGULAR'`

| # | Indicador | Agregação | Fórmula |
|---|---|---|---|
| 1 | Distribuição de ingressantes por modalidade de cota | `modalidade_inscricao` × `ano_ingresso` | contagem de vínculos; `grupo_modalidade` reduz a AMPLA CONCORRENCIA / ACAO AFIRMATIVA / NAO SE APLICA |
| 2 | Evolução histórica de gênero e raça | `ano_ingresso` × `genero` e `ano_ingresso` × `raca` | **participação percentual** no total de ingressantes do ano |
| 3 | Mapeamento das formas de ingresso | `forma_ingresso` × `ano_ingresso` | contagem de vínculos; as seis formas de maior volume e as demais reunidas em "Outras formas" |

Rotas: `GET /v1/demografia/{cotas|genero-raca|formas-ingresso}`

Notas:

- A Análise 2 usa participação e não volume absoluto, que acompanharia o tamanho
  das turmas e esconderia a mudança de composição.
- A Análise 3 marca no gráfico a descontinuidade de rótulos de 2023–2024, quando
  `ENEM` zera e `SISU` e `PROCESSO SELETIVO SIMPLIFICADO` aparecem (A-10, L-07).

## Visão 2 — Fluxo acadêmico (evasão de curso e retenção)

Data marts: `gold/visao2_fluxo/` e `gold/visao2_retencao/` · Fonte principal:
`silver/ingressantes`, apenas `tipo_discente = 'REGULAR'` (estudantes especiais
cursam poucos componentes e distorceriam a taxa).

| # | Indicador | Agregação | Fórmula |
|---|---|---|---|
| 4 | Taxa de evasão de curso | `nome_curso` | `evadidos / total de vínculos` |
| 5 | Evasão de curso por modalidade de ingresso | `modalidade_inscricao` | mesma taxa; modalidades abaixo de um mínimo de vínculos ficam ocultas, por instabilidade |
| 6 | Evasão de curso por coorte de ingresso | `ano_ingresso` | taxa de cada coorte, comparada ao longo dos anos de ingresso |
| — | Primeiro ingresso × reentrada | `e_reentrada` | mesma taxa, separando os vínculos que não são o primeiro na UFFS |
| 10 | Retenção frente ao prazo de integralização | `nome_curso` | vínculos ativos classificados por progressão |

Rotas: `GET /v1/fluxo/{evasao-curso|evasao-cota|curva-evasao|evasao-reentrada|retencao}`

A taxa é calculada na API, a partir das contagens do mart, para que o
denominador acompanhe os filtros aplicados.

### Situações de vínculo

Lista fechada, validada contra a origem; domínio completo em
[`dicionario-dados.md`](dicionario-dados.md) §6.2. Implementada em
`regras.classificar_vinculo`.

| Classificação | Valores da origem |
|---|---|
| EVADIDO | `CANCELADO` |
| CONCLUIDO | `CONCLUÍDO`, `FORMADO` |
| ATIVO | `ATIVO`, `ATIVO - FORMANDO` |
| TRANCADO | `TRANCADO` |

### Por que "evasão de curso"

O grão do dado é o **vínculo estudante-curso**, não a pessoa: quem troca de
curso aparece como um `CANCELADO` mais um vínculo novo, e é contado como evasão
(D-10, L-02). Além disso, `CANCELADO` é o único rótulo de saída — a origem não
separa abandono, cancelamento a pedido e transferência.

O que dá para medir são os vínculos que comprovadamente **não** são o primeiro
na instituição: transferência interna, retorno de graduado e retorno de
aluno-abandono somam 13,3% dos vínculos. A evasão institucional é, portanto,
estritamente menor que a de curso, mas não é calculável.

### A Análise 6 mudou de forma

A proposta descrevia o "percentual acumulado de abandono de cada turma
ingressante **ao longo dos semestres**". Isso não é computável: `sit_matricula`
é a situação **atual** do vínculo, e nenhuma coluna registra *quando* o estudante
saiu (L-03). O que se entrega é a taxa de evasão **por coorte de ingresso**,
ajuste amparado pela seção 4.3.4 da proposta (D-11).

Coortes recentes têm muitos vínculos ainda ativos e taxa naturalmente menor. O
gráfico sombreia as coortes com mais de 20% dos vínculos ativos, para que a queda
não seja lida como melhora de retenção (D-20).

> Cada partição da Bronze guarda um retrato datado de `sit_matricula`. Acumular
> as cargas semanais reconstrói, daqui para frente, a série temporal que a origem
> não publica — a primeira é de 29/08/2026.

### Indicador 10 — Retenção

Fontes: `silver/ingressantes` ⋈ `silver/matrizes` ⋈ `silver/estruturas`.
Não estava na proposta; entra pela cláusula 4.3.4 (D-08).

| Classificação | Critério |
|---|---|
| NO PRAZO | `ATIVO` e semestres decorridos ≤ `quant_semestres` |
| EM RETENCAO | `ATIVO` e decorridos > `quant_semestres` |
| RISCO DE JUBILAMENTO | `ATIVO` e decorridos > 80% de `limite_semestres` |
| SEM PARAMETRO | `ATIVO` sem currículo correspondente (5,8% dos ativos) |

Os prazos vêm de `estruturas_curriculares_graduacao`, publicados pela própria
UFFS — não são estimados. O corte de 80% para o alerta é escolha do painel, sem
norma institucional por trás, isolado em `regras.FATOR_ALERTA_JUBILAMENTO`.

O "agora" é o último período com turmas ofertadas, derivado dos dados e não do
relógio, para que o reprocessamento seja determinístico (D-09).

## Visão 3 — Desempenho e gargalos curriculares

Data marts: `gold/visao3_desempenho/` e `gold/visao3_frequencia_media/` · Fonte:
`silver/historico` ⋈ `silver/turmas`, apenas turmas `CONSOLIDADA`.
Junção: `(ano, semestre, cod_ccr, id_unico_turma)`.

| # | Indicador | Agregação | Fórmula |
|---|---|---|---|
| 7 | *Ranking* de gargalos curriculares | `nome_ccr`, opcionalmente × `curso` | 10 componentes com maior `reprovados / matrículas`, acima de um piso mínimo de matrículas |
| 8 | Frequência × média final | faixas de 5 pontos percentuais de `freq_aluno` | média final ponderada por faixa; tamanho do ponto = matrículas na faixa |
| 9 | Perfil da reprovação | `resultado` | participação de cada causa no total de reprovações |

Rotas: `GET /v1/desempenho/{gargalos|frequencia-media|perfil-reprovacao}`

Notas:

- **Análise 7 ordena por taxa, não por contagem.** A proposta pedia reprovação
  "absoluta"; por contagem o *ranking* mediria tamanho de turma, e os
  obrigatórios de primeira fase apareceriam sempre.
- **Análise 8 parte de um mart já agregado em faixas.** A nuvem crua teria 431
  mil pontos. A rota filtra por nome do componente e não usa os filtros globais,
  porque o mart não carrega curso nem ano. Frequências negativas — de quem
  faltou mais horas do que a carga nominal do componente — entram como 0%
  (D-22).
- **Análise 9 tem três causas, não duas.** A proposta previa dividir
  "estritamente" entre nota e frequência; a origem rotula um terceiro caso —
  reprovação simultânea por nota e falta —, que é o mais frequente (D-05). A
  causa vem do rótulo da origem; o piso de frequência só desempata os
  `REPROVADO` sem qualificação (D-06).

### Agregação dos componentes curriculares

Um mesmo componente tem **vários `cod_ccr`**: 271 dos 1.198 nomes de CCR de
Chapecó (22,6%) aparecem com mais de um código, por versões sucessivas da matriz
curricular e por oferta em cursos distintos (A-24). Geometria Analítica, por
exemplo, tem quatro.

A Análise 7 agrega por **nome**, em dois recortes selecionáveis (D-27):

- **por disciplina (campus)** — une versões de matriz e cursos;
- **por disciplina e curso** — mantém os cursos separados.

Cada linha informa quantos códigos reuniu e quais. A Análise 8 usa o mesmo grão,
para não exibir apenas um fragmento da disciplina.

---

## Limitações

Nenhuma base expõe identificador de estudante (anonimização LGPD). Daí decorre:

1. **As Visões 1–2 e a Visão 3 não podem ser cruzadas**: não é possível medir
   desempenho por modalidade de cota, gênero ou raça.
2. **O grão é o vínculo, não a pessoa** — por isso "evasão de curso".
3. **Predição de risco por estudante é inviável**, não por escopo mas por
   ausência do dado: não há como montar o histórico de uma pessoa.

Outras ressalvas de leitura:

- o total de matrículas da Visão 3 **sem filtro de curso** é inflado em 2,6%,
  porque uma turma compartilhada conta uma vez por curso atendido (L-11); com o
  filtro de curso o número é exato;
- os filtros são os da barra lateral. A filtragem cruzada por clique nos
  gráficos, prevista na proposta, não foi obtida com a versão usada do Streamlit
  (L-10).

## Cláusula de flexibilização

A seção 4.3.4 da proposta resguarda a inclusão, o ajuste e o refinamento de
métricas durante o TCC II. Todo desvio em relação ao que foi proposto está
registrado, com justificativa, em [`registro-decisoes.md`](registro-decisoes.md).
