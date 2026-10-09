# Registro de decisões, achados e limitações

Registro citável do que o desenvolvimento produziu: as escolhas de projeto, o que
se descobriu sobre os dados abertos da UFFS e o que eles não permitem fazer.
Cada entrada tem identificador estável e, sempre que possível, evidência
numérica.

| Prefixo | O que registra |
|---|---|
| **D-nn** | Decisão de projeto ou metodológica |
| **A-nn** | Achado sobre os dados ou sobre a origem |
| **L-nn** | Limitação: algo que os dados ou as ferramentas não permitem |

Convenções:

- identificadores **não são reaproveitados** — uma entrada superada continua no
  registro, marcada como tal;
- os números são os da carga vigente na data da entrada. A origem é republicada
  semanalmente, então contagens variam um pouco entre cargas;
- o detalhe técnico está em [`dicionario-dados.md`](dicionario-dados.md),
  [`indicadores.md`](indicadores.md) e [`arquitetura.md`](arquitetura.md); aqui
  fica o essencial e o motivo.

---

# Decisões

## D-01 · Arquitetura medalhão com Bronze imutável e sem interpretação

**29/08/2026**

A Bronze guarda tudo como texto, exatamente como o JSON da API entregou: nenhuma
coluna renomeada ou convertida. Tipagem e regra de negócio só a partir da
Silver.

**Motivo:** uma mudança de regra nunca deve exigir nova requisição à origem —
especialmente com uma origem instável (A-06). Também é o que torna a Silver
reconstruível a qualquer momento.

**Consequência:** cada carga é um retrato datado, o que abre a possibilidade de
reconstruir séries temporais que a origem não publica (ver L-03).

## D-02 · Empurrar o filtro de escopo para a origem via JOIN no CKAN

**29/08/2026** · Detalhe: `dicionario-dados.md` §8

O recorte de Chapecó do `historico` é feito por `JOIN` com `turmas` dentro da
própria consulta SQL ao CKAN, não depois de baixar tudo.

**Motivo:** A-03 mostrou que o endpoint aceita junção entre recursos. Reduz de
**1.293.405 para 431.012 linhas** (−66,7%), o que alivia a memória do *runner*
gratuito e poupa um portal instável.

## D-03 · Deduplicar exclusivamente pela chave técnica `_id`

**29/08/2026** · Detalhe: comentário em `transformacao/silver.py`

A Silver deduplica apenas por `_id`, a chave primária do DataStore. **Nunca por
atributos de negócio.**

**Motivo:** decorrência direta de L-01. Sem identificador de estudante, dois
alunos de mesmo curso, coorte, cota, gênero, raça e situação produzem linhas
byte a byte idênticas — e **ambas são registros legítimos**.

**Evidência:** deduplicar por atributos de negócio descartava **8.813 dos 16.845
ingressantes de Chapecó (52,3%)**, reduzindo pela metade toda contagem do painel.
Era o comportamento inicial do código; foi detectado e corrigido.

**Por que importa:** é o exemplo mais concreto de como a anonimização na origem
restringe o desenho do pipeline. Um reflexo comum de ETL produz número errado, e
nada no código acusa.

## D-04 · `regras.py` como único lugar de classificação semântica

**29/08/2026**

Toda conversão de texto da origem em categoria de negócio vive num módulo só.

**Motivo:** revisão de indicador vira revisão de um arquivo, e a metodologia
passa a ter uma fonte única a citar. Valores não previstos caem em `OUTROS` e
são reportados no log — nenhum registro some em silêncio.

## D-05 · Categoria própria para reprovação simultânea por nota e frequência

**29/08/2026** · Detalhe: `dicionario-dados.md` §6.3

Em vez de forçar `REPROVADO POR NOTA E FALTA` numa das duas causas, criou-se
`REPROVADO_NOTA_E_FREQUENCIA`.

**Motivo:** A-09 mostrou que é o modo **dominante** de reprovação. Espremê-lo
numa das duas categorias distorceria o perfil da reprovação justamente no caso
mais comum. A proposta previa a divisão "estritamente" entre nota e frequência.

## D-06 · Piso de frequência aplicado só ao `REPROVADO` sem qualificação

**29/08/2026**

`FREQUENCIA_MINIMA` (75,0) desempata apenas os 22.143 registros de `REPROVADO`
sem qualificação. Onde a origem diz explicitamente a causa, o rótulo dela
prevalece.

**Motivo:** A-08 mostrou que a origem já rotula a causa em **98,3%** dos casos.
A hipótese inicial da proposta — inferir a causa pela frequência — só é
necessária na fração restante.

**Fonte normativa do valor:** art. 113 da Resolução nº 40/CGAE/CONSUNI/2022 —
"para ser aprovado em uma disciplina ou módulo presencial, o estudante deve
comparecer a aulas que totalizem 75% (setenta e cinco por cento) ou mais da
carga horária do componente curricular".
Disponível em <https://boletim.uffs.edu.br/atos-normativos/resolucao/consunicgae/2022-0040>.

## D-07 · Dimensão de curso: `matrizes` autoritativa, derivação como complemento

**29/08/2026** · Detalhe: `dicionario-dados.md` §5

`gold/dim_curso` usa `graduacao_matrizes` como fonte oficial e **acrescenta** os
cursos que só existem no histórico de `ingressantes`.

**Motivo:** A-05 (o `graduacao_cursos` está vazio) somado a A-14. Mas `matrizes`
lista só matrizes vigentes: Ciências Econômicas, Engenharia Civil e Educação
Especial Inclusiva sumiriam dos filtros do painel.

**Evidência:** 24 linhas — 21 oficiais + 3 complementadas.

**Complemento de 19/09/2026:** o nome do curso é a chave do filtro global, e as
fontes divergem na grafia — `ingressantes` publica `Ciência Da Computação`,
enquanto `matrizes` e `turmas` publicam em caixa alta. Sem canonizar, o filtro
do painel devolvia vazio para qualquer curso nas Visões 1 e 2. A Silver passou a
gravar `nome_curso` em caixa alta, e a Gold confere a cada execução se todo
curso citado nos marts existe na dimensão.

## D-08 · Indicador de retenção com prazo institucional

**29/08/2026** · Detalhe: `indicadores.md`, "Indicador 10"

Classificação em No prazo / Em retenção / Risco de jubilamento / Sem parâmetro,
usando `quant_semestres` e `limite_semestres` publicados pela UFFS.

**Motivo:** a avaliação da retenção foi pedida pela banca do TCC I. Os
parâmetros são institucionais, não estimados — o que sustenta o indicador
metodologicamente.

**Escolha do projeto, declarada:** o corte de **80% do prazo máximo** para o
alerta de jubilamento não tem norma por trás. Está isolado na constante
`FATOR_ALERTA_JUBILAMENTO`.

**Evidência:** 2.240 no prazo · 181 em retenção · 101 em risco · 155 sem
parâmetro.

## D-09 · Período de referência derivado dos dados, não do relógio

**29/08/2026**

O "agora" para medir semestres decorridos é o último período com turmas
ofertadas (**2026/2**), extraído da própria base.

**Motivo:** reprodutibilidade. Reprocessar a mesma Bronze meses depois produz
exatamente os mesmos números — condição para que os resultados sejam
verificáveis por terceiros.

## D-10 · Adotar "evasão de curso" como termo, nunca "evasão"

**29/08/2026**

O indicador é nomeado "evasão de curso" em painel, API e texto, e a taxa dos
vínculos de reentrada é exibida ao lado.

**Motivo:** L-02. O grão do dado é o vínculo, não a pessoa.

**Evidência:** 2.162 vínculos (13,3%) são reentrada comprovada. Ao menos 1.419
dos 10.400 cancelamentos (13,6%) são de pessoas que ficaram na ou voltaram à
UFFS.

## D-11 · Análise 6 reformulada para taxa por coorte de ingresso

**29/08/2026** · Detalhe: `indicadores.md`

**Motivo:** L-03 — a métrica original é incomputável. Amparo na cláusula 4.3.4
da proposta.

**Declarado junto:** coortes recentes têm muitos vínculos ainda `ATIVO` e taxa
artificialmente menor. Sem sinalização, o gráfico sugeriria melhora inexistente
(tratado em D-20).

## D-12 · Ampliar o catálogo de três para seis bases

**29/08/2026** · Detalhe: `dicionario-dados.md` §4

Acrescentadas `graduacao_matrizes`, `estruturas_curriculares_graduacao` e
`graduacao_ccrs_matrizes`.

**Motivo:** A-05 e A-14, mais o pedido de avaliar retenção. Não altera a
arquitetura: mesma origem, mesma API, mesmo pipeline.

## D-13 · Cadência mensal com guarda de atualização

**29/08/2026** · **SUPERADA por D-25** — a premissa sobre a periodicidade da
origem estava errada. A guarda `--se-atualizado` permanece; só a frequência
mudou.

O `cron` rodava todo dia 1º com `--se-atualizado`: compara o carimbo
`data_atualizacao` da origem com o da última carga e encerra em poucos segundos
se nada mudou.

**Motivo à época:** A-16 — supunha-se que a origem publicava por semestre.

## D-14 · Marcador `_COMPLETO` nas partições da Bronze

**29/08/2026**

A partição só recebe o marcador depois que todas as páginas foram gravadas. Sem
marcador, a guarda `--se-atualizado` força a reingestão.

**Motivo:** a guarda compara apenas o carimbo da origem. Uma carga interrompida
no meio teria o carimbo certo, seria aceita como boa e deixaria o lake
incompleto até a publicação seguinte — numa execução agendada, sem ninguém
olhando.

## D-15 · Cliente CKAN com `Retry` do urllib3 e troca de sessão

**29/08/2026** · Detalhe: docstring de `ckan.py`

Política `Retry` no nível do socket, renovação da sessão a cada tentativa, e
POST com corpo JSON em vez de GET.

**Motivo:** A-06. Retentar no nível da aplicação **não bastava**, porque a
sessão devolvia o socket morto do *pool*.

**Evidência:** a consulta de domínios, que falhava indefinidamente, passou a
rodar em 14,7 s; a ingestão do histórico fez 14 requisições seguidas sem um
único *retry*.

## D-16 · Guarda contra falha silenciosa de tipagem

**29/08/2026**

A tipagem da Silver registra **erro** quando uma coluna que tinha conteúdo fica
inteiramente nula após a conversão.

**Motivo:** resposta a A-17 e a um padrão que apareceu três vezes num só dia —
erro que não levanta exceção e corrompe número (ver também D-03). A conversão
não estrita transforma falha em nulo silencioso.

## D-17 · Reportar `SEM PARAMETRO` em vez de omitir

**29/08/2026**

Vínculos ativos sem currículo correspondente aparecem como categoria própria no
mart de retenção, e o pipeline registra aviso com a contagem.

**Motivo:** omitir daria um percentual de retenção falsamente limpo. A
incompletude da fonte é resultado, não sujeira a esconder (L-05).

## D-18 · Resposta da API sem pyarrow

**19/09/2026** · `api/app/deposito.py`

`Deposito.consultar` monta os dicionários com `cursor.fetchall()` mais
`cursor.description`, em vez de `.arrow().to_pylist()`.

**Motivo:** o código original exigia pyarrow, que **não constava de
`api/requirements.txt`** — toda consulta teria falhado no Render. Entre
acrescentar a dependência e removê-la, remover é melhor: são ~40 MB a menos num
plano com 512 MB de RAM, e os marts (387 KB) cabem inteiros na resposta.

**Como apareceu:** na primeira execução da API.

## D-19 · Tema visual centralizado, com cores de status para a progressão

**19/09/2026** · `dashboard/componentes/tema.py`

Paleta e estilo dos gráficos num módulo só. A ordem das cores categóricas é
fixa — é o mecanismo de segurança para daltonismo, não escolha estética.

**Duas verificações feitas com validador de paleta, não a olho:**

- reentrada (azul × laranja): aprovado em todas as checagens, incluindo
  separação sob protanopia e deuteranopia;
- pilha de retenção: usa a paleta de **status** (bom / atenção / crítico),
  porque progressão é estado, não categoria. As cores de status ficam de
  propósito fora da banda de luminosidade das categóricas, e o amarelo de
  atenção tem contraste 1,79 contra o fundo claro. A mitigação é **rótulo direto
  mais legenda mais tabela equivalente** — nunca cor sozinha.

**Consequência:** a acessibilidade do painel é afirmação verificável, não
alegação.

## D-20 · Sinalizar coortes imaturas na Análise 6 a partir dos dados

**19/09/2026** · `dashboard/visoes/fluxo.py`

O gráfico marca com faixa sombreada as coortes em que mais de **20%** dos
vínculos ainda estão ativos, com o rótulo "coortes ainda em curso".

**Motivo:** decorrência de D-11. Sem a marcação, a queda da taxa nos anos
recentes se lê como melhora de retenção, quando é só efeito do tempo. O corte
vem da fração de ativos observada, não de uma regra fixa de anos — assim a
sinalização se ajusta sozinha a cursos de durações diferentes.

## D-21 · Polars em toda a pilha, inclusive no painel

**19/09/2026** · `dashboard/cliente_api.py` e as três visões

O painel foi convertido de pandas para Polars: `buscar()` devolve
`pl.DataFrame`, e todas as manipulações das visões usam a API do Polars.

**Motivo:** a proposta do TCC I detalha o uso de Polars. O pandas havia entrado
no painel por inércia, sem estar no documento e sem necessidade técnica. O
Plotly 6 consome Polars nativamente e o Streamlit também aceita.

**Ressalva:** *pandas* e *pyarrow* **continuam no ambiente do painel**, porque o
Streamlit os declara como dependências obrigatórias. O que a conversão garante é
que **nenhuma linha de código do projeto** usa pandas: todo o processamento, da
ingestão à apresentação, é Polars. Afirmar mais que isso seria impreciso.

**Efeito colateral:** a conversão obrigou a passar `color_discrete_sequence` nos
gráficos com `color=`, o que revelou que o `colorway` do layout **não** recolore
traços que o Plotly Express já pintou. A Análise 1 estava com as cores padrão
sem que se notasse.

## D-22 · Frequência negativa é fixada em 0%

**19/09/2026, revista em 08/10/2026** · `regras.frequencia_saneada`, aplicada em
`_historico_com_turma`

Valores negativos de `freq_aluno` viram **0%**, uma única vez, no ponto em que a
Visão 3 é montada, para que todos os marts partam do mesmo dado. Valores acima
de 100% — que não ocorrem na base — virariam nulo e gerariam erro no log. A
contagem é registrada a cada execução.

**Motivo:** A-22 e A-27. Frequência não pode ser menor que zero, e 91% dos casos
são do estudante que faltou a todas as aulas da turma: quem faltou mais horas do
que o componente tem compareceu a zero.

**Revisão:** a primeira versão desta decisão **anulava** os valores, por tratá-los
como inconsistência sem explicação. Descoberta a causa (A-27), anular passou a
ser o tratamento errado — retirava da análise justamente os estudantes que nunca
foram à aula. Com o valor em 0%, a faixa de 0 a 5% de frequência da Análise 8
vai de 5.386 para 6.210 matrículas. Como efeito secundário, um `REPROVADO` sem
qualificação com frequência negativa deixa de ser desempatado como reprovação
por nota e passa, corretamente, a reprovação por frequência.

**Como apareceu:** ao renderizar a Análise 8 pela primeira vez. O eixo de
frequência ia de **−130 a 110**. Nenhum teste automatizado teria pego isso — foi
o gráfico que denunciou.

## D-23 · Contrato de esquema validado na ingestão

**19/09/2026** · `ingestao/bronze.py`, `pipeline/config/datasets.yml`

Cada dataset do catálogo declara `colunas` (o esquema verificado, congelado) e
`chaves` (o subconjunto crítico). A ingestão confere antes de gravar:

| Situação | Reação |
|---|---|
| Coluna do contrato sumiu da origem | **aborta** a carga |
| Coluna nova na origem | **avisa** e segue |
| Chave ausente | **aborta** |
| Chave com valor nulo | **aborta** |

**Motivo:** cumpre a checagem de integridade estrutural prevista na seção 4.2.4
da proposta. A assimetria é deliberada — coluna nova não quebra nada e a Bronze
a preserva; coluna ausente produziria nulos silenciosos adiante.

A checagem de **nulo em chave** é a mais valiosa: uma chave nula não levanta
exceção sozinha, apenas corrompe junção e deduplicação lá na frente, e o número
errado só aparece no painel.

O esquema é conferido na primeira página de cada carga (é o mesmo em todas); as
chaves, em todas as páginas.

## D-24 · `_full_text` não entra na Bronze

**19/09/2026** · `ingestao/bronze.py`

A coluna `_full_text` é descartada na ingestão.

**Motivo:** é o índice de busca (tsvector) que o DataStore do CKAN mantém
internamente. Não consta de nenhum dos seis dicionários publicados pela UFFS,
não é campo do conjunto de dados, e nenhuma camada a consome.

**Evidência:** respondia por **74% do tamanho da Bronze** — 7,94 MB caem para
2,03 MB por carga. Por dataset: histórico −74,4%, turmas −77,4%,
`ccrs_matrizes` −71,9%, ingressantes −68,5%. A Silver, que a carregava junto,
foi de 12,56 MB para 3,79 MB.

**Sobre o contrato da Bronze:** a camada promete preservar o registro publicado,
e é isso que faz. O índice de busca é infraestrutura do CKAN, não conteúdo — o
que define um registro é o dicionário de dados, e `_full_text` não está lá.

## D-25 · Cadência semanal, substituindo a mensal

**19/09/2026** · **SUPERA D-13** · `.github/workflows/pipeline.yml`

O `cron` roda **terças às 06:00 UTC**, com folga sobre a atualização de
segunda-feira da origem, mantendo `--se-atualizado`.

**Motivo:** A-23 corrigiu A-16. A conclusão de que a origem publicava por
semestre vinha de **uma amostra única** — a segunda carga, três semanas depois,
mostrou carimbo novo e 206 matrículas a mais.

**Por que cabe:** D-24 reduziu a Bronze a 2,03 MB por carga. Mesmo com 52 cargas
reais por ano, são ~106 MB anuais contra 10 GB gratuitos — décadas de folga. A
cadência semanal só se tornou barata **por causa** do descarte do `_full_text`.

**Ganho colateral, relevante para L-03:** cada carga guarda um retrato datado de
`sit_matricula`. Semanalmente, a série temporal que a origem não publica se
reconstrói bem mais rápido do que com cargas mensais.

**Lição:** inferir periodicidade de uma amostra só foi erro de método. A
correção só apareceu porque a segunda carga foi comparada com a primeira.

## D-26 · Suíte de testes das regras de negócio

**19/09/2026** · `pipeline/tests/`, `.github/workflows/testes.yml`

105 testes cobrindo `regras.py`, o contrato de esquema da ingestão e as
transformações da Silver e da Gold. Inteiramente **offline** — nenhuma chamada
ao CKAN ou ao R2 —, o que os torna executáveis em qualquer máquina e sem
credenciais.

**Motivo:** as regras de negócio educacionais são o núcleo metodológico do
trabalho. Uma alteração descuidada em `regras.py` muda os números do painel.

**O que os testes fixam:**

- os domínios reais de `dicionario-dados.md` §6 como casos concretos — nenhum
  valor observado pode cair em `OUTROS`;
- as fronteiras das regras: frequência exatamente no piso de 75%, decorridos
  exatamente na duração prevista, 80% do prazo máximo;
- as **decisões** e não só o comportamento: que `ingressantes` nunca é
  deduplicado por atributo de negócio (D-03), que `_full_text` não está em
  contrato nenhum (D-24), que todo mart da Gold é conhecido pela API;
- as regressões das falhas silenciosas: fração de segundo no carimbo, coluna que
  fica 100% nula após a tipagem, nome de curso em grafias diferentes.

**Verificação da própria suíte:** removendo `ATIVO - FORMANDO` do conjunto de
vínculos ativos, **três testes falham**. Suíte verde não prova nada sem esse
passo.

## D-27 · Gargalos agregados por nome de componente, com dois recortes

**19/09/2026** · `api/app/rotas/desempenho.py`, `dashboard/visoes/desempenho.py`

A Análise 7 deixa de agrupar por `cod_ccr` e passa a agrupar por **nome do
componente**, em dois recortes que o usuário escolhe:

| Recorte | Pergunta que responde |
|---|---|
| **Por disciplina (campus)** | "Qual disciplina é gargalo no campus?" — une versões de matriz e cursos |
| **Por disciplina e curso** | "Qual disciplina é gargalo em cada curso?" — mantém cursos separados |

**Motivo:** A-24. Agrupar por código fragmentava a disciplina e produzia três
efeitos ruins: linhas aparentemente duplicadas no *ranking* (3 nomes repetidos no
top 20), magnitude real escondida, e **7 disciplinas excluídas** do *ranking*
porque cada fragmento isolado ficava abaixo do piso de 50 matrículas.

**Evidência do ganho:** Geometria Analítica passa de 1.173 matrículas no maior
fragmento (56,8%) para **3.341 somada (50,9%)**.

**Por que os dois recortes:** eles revelam coisas diferentes. No recorte por
curso aparecem `CIÊNCIA DA COMPUTAÇÃO · MATEMÁTICA INSTRUMENTAL` (1.003
matrículas, 54,0%), que **não figura no ranking de campus**, e `FILOSOFIA · TCC
III` (64,4%), mostrando que o problema do TCC está concentrado num curso. A
Geometria da Ciência da Computação (53,2%) é pior que a média de campus, diluída
pela oferta da Matemática.

**Rastreabilidade:** cada linha devolve o número de códigos reunidos e a lista
deles, exibidos no *tooltip* e na tabela — a união nunca é opaca.

**Consequência:** a Análise 8 passou a filtrar por nome do componente, para
ficar no mesmo grão.

---

# Achados

| ID | Achado | Evidência | Onde no TCC |
|---|---|---|---|
| **A-01** | Nenhuma das bases expõe identificador de estudante (anonimização LGPD) | `ingressantes` e `historico` sem matrícula ou pseudônimo | Resultados + Limitações (ver L-01) |
| **A-02** | `historico` não tem `nome_campus`; o recorte de campus só existe via junção com `turmas` | chave `(ano, semestre, cod_ccr, id_unico_turma)`; tipos divergentes (`text` × `int4`) | Desenvolvimento |
| **A-03** | O endpoint SQL do CKAN aceita `JOIN` entre recursos | validado com `count(*)`; base de D-02 | Desenvolvimento |
| **A-04** | Teto de 32.000 linhas por requisição, com **truncamento silencioso** | pedidos de 50.000 retornam 32.000 sem aviso | Desenvolvimento |
| **A-05** | `graduacao_cursos` tem esquema publicado e DataStore **vazio** | 0 registros | Resultados (qualidade do portal) |
| **A-06** | Os resets de TLS atingem a conexão, não a consulta: envenenam o *pool keep-alive* e derrubam em cascata as chamadas seguintes | ~10–15% das requisições; 8 de 8 com sucesso usando `Retry`, contra 1 falha em 8 sem ele, mesmo abrindo sessão nova a cada chamada | Resultados (contribuição ao portal) |
| **A-07** | `CANCELADO` é o **único** rótulo de saída em `ingressantes` | não separa abandono, pedido ou transferência | Limitações (ver L-02) |
| **A-08** | A origem já rotula a causa da reprovação em **98,3%** dos casos | só 22.143 de 1.293.405 são `REPROVADO` sem qualificação | Resultados |
| **A-09** | Reprovação simultânea por nota **e** frequência é o modo dominante | 54.738 em Chapecó, contra 38.063 só por nota | Resultados |
| **A-10** | Descontinuidade em `forma_ingresso`: `ENEM` zera em 2024 quando `SISU` e `PSS` assumem | 2022: ENEM 746 / SISU 0 · 2024: ENEM 0 / SISU 346 / PSS 282 | Resultados + Limitações (L-07) |
| **A-11** | As categorias de `raca` divergem das do IBGE | `Negro` em vez de `Preto`; `Indígeno` em vez de `Indígena` | Resultados |
| **A-12** | `turno` é nulo exatamente para os estudantes `ESPECIAL` | 644 nulos = 644 especiais | Desenvolvimento |
| **A-13** | `modalidade_inscricao` mistura três gerações de nomenclatura | L1–L14 (Lei 12.711/2012), LB\_\*/LI\_\* (Lei 14.723/2023), A1/A2 (institucionais). O dicionário publicado **não documenta** LB/LI | Resultados |
| **A-14** | Três bases de estrutura curricular estão populadas e resolvem o que faltava | `matrizes` 21 · `estruturas` 43 · `ccrs_matrizes` 7.609 | Desenvolvimento |
| **A-15** | `ccrs_matrizes` **não** tem campo de obrigatório/optativo | tem `niveis_oferta`; 1.445 CCRs com nível 0 — inferência não confirmada | Limitações (L-08) |
| **A-16** | ~~A origem republica por semestre~~ — **corrigido por A-23**: a conclusão vinha de uma amostra única | — | — |
| **A-17** | `data_atualizacao` traz fração de segundo | `2026-08-24T02:30:16.733317` | Desenvolvimento |
| **A-18** | **Reentradas evadem mais que primeiro ingresso** | 71,3% contra 63,1% — 8 p.p. acima | Resultados (destaque) |
| **A-19** | A retenção é muito desigual entre cursos | Ciência da Computação 20,8% · Medicina 1,3% | Resultados (destaque) |
| **A-20** | 13,3% dos vínculos são reentrada comprovada | 2.162 de 16.201 | Resultados |
| **A-21** | `freq_aluno` é derivada: `100 − 100 × numero_faltas / ch_t_p` | conferido contra os dados | Desenvolvimento |
| **A-22** | **Há frequências negativas**: a origem registra mais faltas do que a carga horária da turma | 825 matrículas (0,19%), mínimo **−122,2%**; 823 delas são `REPROVADO POR NOTA E FALTA` e 808 têm média 0 | Resultados (qualidade dos dados abertos) |
| **A-23** | A origem republica **semanalmente**, às segundas por volta das 02:30, as seis bases no mesmo lote | carimbos 2026-08-24, 2026-09-14 e 2026-10-05, todos segunda-feira às 02:30, com intervalos múltiplos de 7 dias. Histórico de Chapecó nas três cargas: 431.012 → 431.218 → 431.223; ingressantes 16.845 → 16.871 → 16.871 | Desenvolvimento (base de D-25) |
| **A-24** | **Um componente curricular tem vários `cod_ccr`** — versões sucessivas da matriz e oferta por cursos distintos | 271 de 1.198 nomes (22,6%) têm mais de um código. `TRABALHO DE CONCLUSÃO DE CURSO I` tem 15; Geometria Analítica tem 4 (`GEX004` 2010–18, `GEX195` 2013–25, `GEX1142` 2025–26, todos de Ciência da Computação e Engenharia Ambiental; `GEX503` é da Matemática) | Resultados + Desenvolvimento |
| **A-25** | Uma turma compartilhada **conta a mesma matrícula uma vez por curso** atendido | fator 1,03 no campus (429.622 contra 418.740 reais); só 225 de 14.288 turmas atendem mais de um curso | Limitações (L-11) |
| **A-26** | As duas colunas de carga horária estão em **unidades diferentes**: `historico.ch_t_p` em horas-aula, `turmas.ch_ccr` em horas | razão exata de 1,2 em 99,97% das matrículas (72 × 60, 54 × 45). Coerente com o art. 111 da Resolução nº 40/CGAE/CONSUNI/2022, que registra a presença por hora-aula | Desenvolvimento |
| **A-27** | **Causa das frequências negativas (A-22): as faltas são contadas sobre as aulas registradas, e o denominador é a carga nominal.** Não é diferença de unidade | 752 dos 825 casos (91%) são do estudante com mais faltas da turma; em 89% o excesso é de até 20%, tipicamente 1 a 4 horas-aula. 60 casos extremos em 20 turmas. Pico de 1,26% das matrículas em 2011, praticamente zero desde 2023 | Resultados (qualidade dos dados abertos) |

> **A-18 e A-19 ainda são hipóteses.** Precisam de quebra por curso e de
> validação com as coordenações antes de virarem afirmação.

---

# Limitações

| ID | Limitação | Consequência | Contorno |
|---|---|---|---|
| **L-01** | Sem identificador de estudante | (a) impossível cruzar perfil demográfico com desempenho por disciplina; (b) o grão é o vínculo, não a pessoa; (c) predição de risco por estudante é inviável | Nenhum. É consequência da anonimização na origem, não falha do artefato |
| **L-02** | Evasão institucional não é calculável | só a evasão **de curso** é mensurável | Cota inferior a partir das formas de ingresso de reentrada (D-10) |
| **L-03** | Análise 6 original incomputável: não há data de saída | não existe curva acumulada dentro da coorte, nem leitura do efeito pandêmico | Taxa por coorte (D-11); o acúmulo de retratos da Bronze reconstrói a série **a partir de 29/08/2026** |
| **L-04** | Estado de origem do estudante não existe em nenhuma base | inviabiliza análises multifatoriais de evasão | Nenhum |
| **L-05** | 5,8% dos vínculos ativos sem currículo correspondente | 155 de 2.677, em três cursos ausentes de `matrizes` | Categoria `SEM PARAMETRO` explícita (D-17) |
| **L-06** | A junção `historico ⋈ turmas` descarta matrículas | 12.289 de 431.012 (2,9%) — turmas não consolidadas | Registrado em log a cada execução |
| **L-07** | Não dá para saber se ENEM→SISU foi mudança de política ou renomeação | muda por completo a leitura da Análise 3 | Descontinuidade marcada no gráfico; depende de confirmação institucional |
| **L-08** | Obrigatório versus optativo não é publicado | limita a qualificação do *ranking* de gargalos | Inferência por `niveis_oferta`, não confirmada |
| **L-09** | A frequência publicada usa a carga horária **nominal** como denominador, não as aulas efetivamente dadas (A-27) | 825 matrículas com frequência negativa; nas turmas que registraram mais aulas que a carga nominal, a frequência de todos os estudantes fica levemente subestimada | Negativas fixadas em 0% e contadas em log (D-22). A subestimação nas demais não é corrigível: a base não publica o número de aulas dadas |
| **L-10** | **Filtragem cruzada por clique não foi obtida.** Com Streamlit 1.52.2 e Plotly 6.4.0, `st.plotly_chart(on_select='rerun')` destaca a barra no navegador mas **não dispara reexecução no servidor** — nenhum evento chega ao Python e nenhuma exceção é registrada. Testadas quatro combinações de `clickmode`, `dragmode` e `selection_mode` | o filtro global fica só na barra lateral | A barra lateral cobre o caso de uso: seleciona curso, ano e semestre para as três visões |
| **L-11** | **Matrícula em turma compartilhada conta uma vez por curso.** O mart da Visão 3 separa a lista de cursos da turma para permitir o filtro por curso; somar sem filtrar infla o total | fator 1,03 — 429.622 contra 418.740 matrículas reais (A-25) | Inflação de 2,6% só no agregado de campus; por curso o número é exato |
