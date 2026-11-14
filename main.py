"""CapitalRiskBR — execução da Fase 1.

Uso:  python main.py
Saída: relatório no console + output/relatorio_capital.xlsx
"""
from pathlib import Path

import pandas as pd

from src.basileia import (avaliar_requerimentos, capacidade_crescimento_rwa, capital_necessario,
                          carregar_outras_parcelas, consolidar_rwa)
from src.capital_regulatorio import carregar_capital
from src.config import carregar_parametros
from src.relatorio import exibir_relatorio, exportar_excel
from src.risco_credito import calcular_rwa_por_operacao, rwa_por_classe

RAIZ = Path(__file__).resolve().parent
PASTA_DADOS = RAIZ / "data"
PASTA_SAIDA = RAIZ / "output"


def main() -> None:
    parametros = carregar_parametros()

    carteira = pd.read_csv(PASTA_DADOS / "carteira.csv", encoding="utf-8")
    carteira_com_rwa = calcular_rwa_por_operacao(carteira, parametros)
    por_classe = rwa_por_classe(carteira_com_rwa)

    outras = carregar_outras_parcelas(PASTA_DADOS / "rwa_outras_parcelas.csv")
    parcelas_rwa = consolidar_rwa(float(carteira_com_rwa["rwa"].sum()), outras)

    capital = carregar_capital(PASTA_DADOS / "capital.csv")
    avaliacao = avaliar_requerimentos(capital, parcelas_rwa["RWA"], parametros)
    capacidade = capacidade_crescimento_rwa(avaliacao)
    aporte = capital_necessario(avaliacao)

    exibir_relatorio(carteira_com_rwa, parcelas_rwa, capital, avaliacao, capacidade, aporte)
    arquivo = exportar_excel(PASTA_SAIDA / "relatorio_capital.xlsx", carteira_com_rwa, por_classe,
                             parcelas_rwa, capital, avaliacao, capacidade, aporte)
    print(f"Relatório Excel: {arquivo.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
