# CapitalRiskBR

[![testes](https://github.com/robertofogaca-fin/capital_risk_br/actions/workflows/testes.yml/badge.svg)](https://github.com/robertofogaca-fin/capital_risk_br/actions/workflows/testes.yml)

Calculadora didática de **requerimento de capital regulatório** para instituições autorizadas pelo Banco Central do Brasil, seguindo o arcabouço de Basileia III como implementado no Brasil.

## O que calcula

| Etapa | Fórmula | Norma de referência |
|---|---|---|
| EAD | saldo no balanço + FCC × saldo fora do balanço | Res. BCB 229/2022 |
| RWACPAD | Σ EAD × FPR | Res. BCB 229/2022 |
| RWA | RWACPAD + RWAMPAD + RWAOPAD + RWASP | Res. CMN 4.958/2021, art. 3º |
| Capital Principal | elementos de CP − ajustes prudenciais | Res. CMN 4.955/2021 |
| Nível I / PR | CP + Capital Complementar / Nível I + Nível II | Res. CMN 4.955/2021 |
| Mínimos | CP 4,5% · Nível I 6% · PR 8% do RWA | Res. CMN 4.958/2021 |
| ACP | Conservação + Contracíclico + Sistêmico | Res. CMN 4.958/2021 |
| RWAOPAD | (1/F) × BIC × ILM | Res. BCB 356/2023 |
| RWASP | (1/F) × (MOE + ADQ + PISP) | Res. BCB 202/2022 |

### Risco operacional (Res. BCB 356/2023)

| Componente | Fórmula |
|---|---|
| ILDC | min(média \|II − IE\|; 2,25% × média dos ativos rentáveis) + média de dividendos |
| SC | max(média receitas de serviços; média despesas de serviços) + max(média outras receitas; média outras despesas) |
| FC | média \|carteira de negociação\| + média \|carteira bancária\| |
| BI | ILDC + SC + FC (médias dos 3 últimos períodos anuais) |
| BIC | 12% até R$ 5 bi + 15% de R$ 5 bi a R$ 150 bi + 18% acima |
| LC | média anual de perdas líquidas em 10 anos × **6** (Basileia usa 15), só eventos ≥ R$ 500 mil |
| ILM | ln(e − 1 + (LC/BIC)^0,8) para S1 e S2; igual a 1 para S4 (e para S3, salvo opção a partir de 2028) |
| Transição | se o novo RWAOPAD superar o de dez/2024: + 25% (2025), 50% (2026), 75% (2027) da diferença |

Instituições sujeitas ao RWASP excluem do BI as receitas e despesas de MOE, ADQ e PISP (art. 9º, § 1º), para não contar o mesmo risco duas vezes.

### Serviços de pagamento (Res. BCB 202/2022)

| Componente | Base (média dos últimos 12 meses) | Fator |
|---|---|---|
| MOE | pagamentos e transferências | 0,2% |
| MOE | saldo de moeda eletrônica emitida | 1% |
| ADQ | transações credenciadas | 2% |
| PISP | transações iniciadas | 1,5% |

Saídas:

- **Situação por nível**: `ADEQUADO`, `ABAIXO DO ACP` (cumpre o mínimo, mas não o adicional) ou `ABAIXO DO MÍNIMO`.
- **Capacidade de crescimento de RWA**: quanto RWA adicional cabe no capital atual, ou seja, quanto ainda dá para emprestar sem aporte.
- **Aporte de Capital Principal** necessário para enquadrar todos os níveis.
- Relatório Excel em `output/relatorio_capital.xlsx`.

> O antigo PRE (`PEPR + PJUR + PCAM + PCOM + PACS + POPR`) pertence ao regime anterior a 2013 e foi substituído pela abordagem por RWA. A versão antiga deste projeto está em `legado/`.


## A partir de balancete Cosif público

O projeto lê os balancetes que o Banco Central publica para qualquer instituição regulada e estima o requerimento de capital. O regime é detectado pela taxonomia do balancete:

| Tipo | Documento | Regime | Norma |
|---|---|---|---|
| Instituição de pagamento | 4010 | PRIP ≥ 12% × RWAIP (RWASP + RWARCSimp + RWACAMSimp) | Res. BCB 198/2022 e 437/2024 |
| Banco individual | 4010 | PR, Nível I e CP × RWA, com ACP (apenas comparação) | Res. CMN 4.955 e 4.958/2021 |
| Conglomerado prudencial | 4060 | PR, Nível I e CP × RWA, com ACP | Res. CMN 4.955 e 4.958/2021 |

```bash
python main.py --balancete data/balancetes/AAAAMM-4060-XXXXXXXX.CSV   # um balancete
python main.py --balancete data/balancetes/                           # todos da pasta
```

Como funciona:

1. **Leitura**: identifica as contas analíticas pelos níveis Cosif (grupo, subgrupo, desdobramento, título, subtítulo) e concilia a soma das analíticas com o saldo de cada grupo patrimonial e de resultado.
2. **Mapeamento conta a conta** (`config/mapeamento_cosif_*.csv`): cada conta recebe um destino (capital, dedução, exposição, base de serviços de pagamento) e uma classe de risco, pelo prefixo mais longo. Contas de ativo sem regra entram a 100% e aparecem no relatório.
3. **Capital**: PL (grupo 6.1) + resultado do período (grupos 7 e 8) − ajustes prudenciais. Para bancos, Capital Complementar e Nível II vêm das contas 43910000 e 30981000.
4. **RWA**: crédito por classe de exposição; risco operacional pelo BI das contas de resultado (art. 9º da Res. BCB 356, com exclusões); RWASP pelas contas de controle de saldo médio 30971000 e 30969000.
5. **Parâmetros por instituição** (`config/instituicoes.local.toml`, fora do Git; modelo em `config/instituicoes.exemplo.toml`): o que o balancete não traz (segmento, ACP sistêmico, parcela dedutível dos créditos tributários, RWA de mercado, volumes de CPOS/ADQ/PISP e índices divulgados para comparação).


### Série histórica

```bash
python main.py --serie data/balancetes/
```

Agrupa os balancetes por instituição e modelo (4010/4060) e calcula capital, RWA e índices em cada data-base. O Excel `output/serie_<instituição>_<modelo>.xlsx` traz a tabela da série, um gráfico de evolução dos índices, um gráfico da composição do RWA e o BI por semestre.

- **Indicador de Negócios com média anual (Res. BCB 356, arts. 2º e 6º)**: os balancetes de junho e dezembro trazem o resultado do semestre (as contas de resultado são zeradas nesses fechamentos). Cada período anual soma dois semestres, e os ativos rentáveis são a média dos dois saldos semestrais. Em cada data-base, usa o último fechamento semestral e até 3 períodos anuais completos. Sem histórico, anualiza o período corrente e registra a premissa.
- **Mudança do plano de contas em 01/2025 (Res. CMN 4.966)**: balancetes até 12/2024 usam o Cosif anterior e são publicados até o 3º nível. O projeto aplica um mapeamento próprio (`config/legado/`), com premissas mais grossas: compromissos de crédito, títulos elegíveis a capital e créditos tributários não são identificáveis, e a carteira de câmbio é compensada (ativa − passiva). A série sinaliza a quebra.
- Arquivos publicados com linhas duplicadas idênticas são tratados automaticamente; contas repetidas com saldos diferentes interrompem a leitura.

### Validação com um banco múltiplo S1 (conglomerado prudencial, 03/2026)

| | Estimado | Divulgado | RWA implícito |
|---|---|---|---|
| Capital Principal | 7,9% | 11,2% | R$ 757 bi |
| Índice de Basileia | 10,7% | 15,2% | R$ 752 bi |

O RWA implícito é praticamente o mesmo pelos dois índices, o que indica que a **composição do capital extraída do balancete está correta**. A diferença está no RWA estimado (R$ 1,07 tri): o balancete não mostra mitigadores, compensação de derivativos (SA-CCR), FPR por contraparte, LTV nem o phase-in regulatório. Os índices estimados são exercício metodológico e **não representam a situação regulatória oficial** de nenhuma instituição.

**Fonte dos dados:** balancetes Cosif nos modelos 4010 (individual) e 4060 (conglomerado prudencial), públicos no portal do Banco Central do Brasil.

**Privacidade:** o repositório publica apenas a metodologia. Os arquivos de balancete e o cadastro por CNPJ ficam na máquina local (`.gitignore`), e os relatórios identificam cada instituição por um apelido genérico, sem nome nem CNPJ (`[saida].anonimizar` em `parametros.toml`).

## Cenários de estresse (Fase 3)

Cada relatório de balancete traz as abas **Estresse** e **Teste Reverso**. Os choques ficam em `config/cenarios.toml`:

| Choque | Efeito |
|---|---|
| Crescimento da carteira | RWA de crédito × (1 + crescimento) |
| Inadimplência | perda adicional × EAD de crédito × (1 − alíquota) sai do capital |
| Choque de juros | Δ taxa × duration × exposição a valor justo × (1 − alíquota) sai do capital. A exposição vem das contas 32120000 e 32130000 (ativos a VJORA e VJR) menos 32180000 (passivos a VJR) |
| Prejuízo operacional | % do capital |
| Crescimento de pagamentos | RWASP × (1 + crescimento) |

O **teste reverso** calcula a perda máxima absorvível e o crescimento máximo de RWA antes de violar o requerido (mínimo + ACP), com o nível de capital limitante.

Quando há índice divulgado cadastrado, o estresse parte de uma **base calibrada**: o RWA estimado é escalado para o RWA implícito pelo índice de Basileia divulgado, e os choques medem a sensibilidade a partir da posição oficial.

## Dashboard (Fase 4)

```bash
pip install -r requirements-app.txt
streamlit run app.py
```

Painel no padrão visual RF Analytics, com balancetes de `data/balancetes/` ou enviados pela tela:

- **Visão geral**: índices, RWA e comparação com o índice divulgado.
- **Capital e RWA**: composição do capital, RWA por classe e Indicador de Negócios.
- **Série histórica**: evolução dos índices e da composição do RWA.
- **Estresse**: cenário personalizado com controles deslizantes, cenários configurados e teste reverso.
- **Mapeamento e premissas**: premissas, conciliação, mapeamento conta a conta e download do Excel.

> Se a instalação do Streamlit falhar numa versão muito recente do Python (pacotes como o `pyarrow` demoram a publicar versões prontas), crie um ambiente com o Python 3.13: `py -3.13 -m venv .venv`, ative-o e instale `requirements-app.txt`. O núcleo do projeto (`requirements.txt`) não depende do Streamlit.

## Testes e integração contínua

`python -m pytest` roda mais de 100 testes, com valores calculados à mão para cada fórmula. O GitHub Actions executa a suíte a cada push em Python 3.11, 3.12 e 3.13. Os testes com balancetes reais só rodam localmente, porque esses arquivos ficam fora do repositório.

## Como rodar

```bash
pip install -r requirements.txt
python main.py      # relatório no console + Excel
python -m pytest    # testes
```

## Estrutura

```
config/parametros.toml       fatores mínimos, ACP, FPR por classe, FCC por tipo
data/carteira.csv            operações (classe de exposição, saldo no balanço e fora dele)
data/capital.csv             componentes do PR por nível
data/dre_operacional.csv     3 períodos anuais: juros, serviços, carteiras (base do BI)
data/perdas_operacionais.csv eventos de perda operacional (base do LC)
data/servicos_pagamento.csv  12 meses de volumes de pagamento (base do RWASP)
data/rwa_outras_parcelas.csv RWAMPAD informado (até a Fase 3)
data/balancetes/             balancetes Cosif públicos (4010 e 4060) — fora do Git
config/mapeamento_cosif_*.csv regras conta Cosif -> destino regulatório (banco, IP e BI)
config/legado/               mapeamentos do plano Cosif anterior a 2025 (nível 3)
config/instituicoes.*.toml   parâmetros por CNPJ que o balancete não informa (local + exemplo)
src/balancete_cosif.py       leitura, contas analíticas e conciliação
src/capital_balancete.py     regimes banco e IP a partir do balancete
src/relatorio_balancete.py   console e Excel do balancete
src/serie_historica.py       série histórica, BI com média anual e gráficos
src/estresse.py              cenários de estresse e teste reverso
config/cenarios.toml         choques e premissas do estresse
app.py                       dashboard Streamlit (tema em .streamlit/config.toml)
.github/workflows/testes.yml CI: testes a cada push
src/risco_credito.py         EAD e RWACPAD
src/risco_operacional.py     BI, BIC, LC, ILM, transição e RWAOPAD
src/servicos_pagamento.py    MOE, ADQ, PISP e RWASP
src/capital_regulatorio.py   composição do PR
src/basileia.py              RWA total, índices, ACP, folga, capacidade e aporte
src/relatorio.py             console e Excel
tests/                       testes com valores calculados à mão
```

## Roadmap

- ~~Fase 1~~: RWA de crédito, composição do PR, mínimos e ACP.
- ~~Fase 2~~: RWAOPAD (Res. BCB 356/2023) e RWASP (Res. BCB 202/2022).
- ~~Balancete Cosif~~: estimativa para IP, banco e conglomerado a partir de dados públicos.
- ~~Série histórica~~: BI com média anual a partir dos balancetes semestrais e evolução dos índices.
- ~~Fase 3~~: cenários de estresse, base calibrada e teste reverso.
- ~~Fase 4~~: dashboard em Streamlit e CI no GitHub Actions.
- **Próximo**: comparação entre instituições da mesma data-base.

## Limitações

Projeto educacional. A segmentação S5, os conglomerados Tipo 2/3 (Res. BCB 197 a 201/2022), as regras para instituições novas (art. 20 da Res. BCB 356) e as rubricas Cosif do BI estão fora do escopo. Os FPR e FCC em `parametros.toml` são simplificados: a Res. BCB 229 os diferencia por categoria da contraparte, prazo, LTV, mitigadores e outros critérios. Não use para reporte regulatório.

## Licença

Código distribuído sob a licença [MIT](LICENSE): uso, cópia e adaptação livres, mantendo o aviso de copyright.

Os balancetes Cosif são dados públicos do Banco Central do Brasil e não fazem parte deste repositório. Os resultados são estimativas educacionais e não constituem apuração regulatória, recomendação de investimento ou opinião sobre a situação de qualquer instituição.

---
Roberto Fogaça · RF Analytics
