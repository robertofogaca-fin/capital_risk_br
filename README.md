# CapitalRiskBR

Calculadora didática de **requerimento de capital regulatório** para instituições autorizadas pelo Banco Central do Brasil, seguindo o arcabouço de Basileia III como implementado no Brasil.

## O que calcula (Fase 1)

| Etapa | Fórmula | Norma de referência |
|---|---|---|
| EAD | saldo no balanço + FCC × saldo fora do balanço | Res. BCB 229/2022 |
| RWACPAD | Σ EAD × FPR | Res. BCB 229/2022 |
| RWA | RWACPAD + RWAMPAD + RWAOPAD + RWASP | Res. CMN 4.958/2021, art. 3º |
| Capital Principal | elementos de CP − ajustes prudenciais | Res. CMN 4.955/2021 |
| Nível I / PR | CP + Capital Complementar / Nível I + Nível II | Res. CMN 4.955/2021 |
| Mínimos | CP 4,5% · Nível I 6% · PR 8% do RWA | Res. CMN 4.958/2021 |
| ACP | Conservação + Contracíclico + Sistêmico | Res. CMN 4.958/2021 |

Saídas:

- **Situação por nível**: `ADEQUADO`, `ABAIXO DO ACP` (cumpre o mínimo, mas não o adicional) ou `ABAIXO DO MÍNIMO`.
- **Capacidade de crescimento de RWA**: quanto RWA adicional cabe no capital atual, ou seja, quanto ainda dá para emprestar sem aporte.
- **Aporte de Capital Principal** necessário para enquadrar todos os níveis.
- Relatório Excel em `output/relatorio_capital.xlsx`.

> O antigo PRE (`PEPR + PJUR + PCAM + PCOM + PACS + POPR`) pertence ao regime anterior a 2013 e foi substituído pela abordagem por RWA. A versão antiga deste projeto está em `legado/`.

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
data/rwa_outras_parcelas.csv RWAMPAD, RWAOPAD, RWASP informados (até as Fases 2 e 3)
src/risco_credito.py         EAD e RWACPAD
src/capital_regulatorio.py   composição do PR
src/basileia.py              RWA total, índices, ACP, folga, capacidade e aporte
src/relatorio.py             console e Excel
tests/                       testes com valores calculados à mão
```

## Roadmap

- **Fase 2**: RWAOPAD = (1/F) × (BIC × ILM), conforme a Res. BCB 356/2023, e RWASP (serviços de pagamento).
- **Fase 3**: RWAMPAD simplificado e cenários de estresse (choque de juros, crescimento da carteira, prejuízo). A Res. CMN 5.207/2025 altera a parcela de mercado a partir de 1º/1/2027.
- **Fase 4**: dashboard em Streamlit e CI no GitHub Actions.

## Limitações

Projeto educacional. Os FPR e FCC em `parametros.toml` são simplificados: a Res. BCB 229 os diferencia por categoria da contraparte, prazo, LTV, mitigadores e outros critérios. Não use para reporte regulatório.

---
Roberto Fogaça · RF Analytics
