"""CapitalRiskBR — requerimento de capital regulatório.

Uso:
  python main.py                                   exemplo didático (data/*.csv)
  python main.py --balancete data/balancetes/X.CSV  estimativa a partir de balancete Cosif do BCB
  python main.py --balancete data/balancetes/       todos os balancetes da pasta
  python main.py --serie data/balancetes/           série histórica por instituição e modelo
"""
import argparse
from pathlib import Path

import pandas as pd

from src.basileia import (avaliar_requerimentos, capacidade_crescimento_rwa, capital_necessario,
                          carregar_outras_parcelas, consolidar_rwa)
from src.capital_regulatorio import carregar_capital
from src.config import carregar_parametros
from src.relatorio import exibir_relatorio, exportar_excel
from src.risco_credito import calcular_rwa_por_operacao, rwa_por_classe
from src.risco_operacional import calcular_rwaopad
from src.servicos_pagamento import calcular_rwasp

RAIZ = Path(__file__).resolve().parent
PASTA_DADOS = RAIZ / "data"
PASTA_SAIDA = RAIZ / "output"


def _ler(nome: str) -> pd.DataFrame:
    return pd.read_csv(PASTA_DADOS / nome, encoding="utf-8")


def analisar_balancetes(caminho: Path) -> None:
    from src.capital_balancete import analisar_balancete
    from src.relatorio_balancete import exibir, exportar

    parametros = carregar_parametros()
    arquivos = sorted(caminho.glob("*.[cC][sS][vV]")) if caminho.is_dir() else [caminho]
    if not arquivos:
        raise SystemExit(f"Nenhum balancete encontrado em {caminho}")
    for arquivo in arquivos:
        resultado = analisar_balancete(arquivo, parametros)
        exibir(resultado)
        saida = exportar(resultado, PASTA_SAIDA)
        print(f"Relatório Excel: {saida.relative_to(RAIZ)}\n")


def analisar_series(pasta: Path) -> None:
    from src.serie_historica import agrupar, analisar_serie, exibir_serie, exportar_serie

    parametros = carregar_parametros()
    for itens in agrupar(pasta).values():
        serie = analisar_serie(itens, parametros)
        exibir_serie(serie)
        print(f"Relatório Excel: {exportar_serie(serie, PASTA_SAIDA).relative_to(RAIZ)}\n")


def exemplo_didatico() -> None:
    parametros = carregar_parametros()

    # Risco de crédito
    carteira_com_rwa = calcular_rwa_por_operacao(_ler("carteira.csv"), parametros)
    por_classe = rwa_por_classe(carteira_com_rwa)

    # Risco operacional e serviços de pagamento
    dre = _ler("dre_operacional.csv")
    servicos = _ler("servicos_pagamento.csv")
    operacional = calcular_rwaopad(dre, _ler("perdas_operacionais.csv"), parametros)
    pagamentos = calcular_rwasp(servicos, parametros)

    # RWA total (mercado ainda informado — Fase 3)
    outras = carregar_outras_parcelas(PASTA_DADOS / "rwa_outras_parcelas.csv")
    outras.update({"RWAOPAD": operacional["RWAOPAD"], "RWASP": pagamentos["RWASP"]})
    parcelas_rwa = consolidar_rwa(float(carteira_com_rwa["rwa"].sum()), outras)

    # Capital e requerimentos
    capital = carregar_capital(PASTA_DADOS / "capital.csv")
    avaliacao = avaliar_requerimentos(capital, parcelas_rwa["RWA"], parametros)
    capacidade = capacidade_crescimento_rwa(avaliacao)
    aporte = capital_necessario(avaliacao)

    exibir_relatorio(carteira_com_rwa, parcelas_rwa, capital, avaliacao, capacidade, aporte,
                     operacional, pagamentos)
    arquivo = exportar_excel(PASTA_SAIDA / "relatorio_capital.xlsx", carteira_com_rwa, por_classe,
                             parcelas_rwa, capital, avaliacao, capacidade, aporte,
                             operacional, pagamentos, dre, servicos)
    print(f"Relatório Excel: {arquivo.relative_to(RAIZ)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CapitalRiskBR — requerimento de capital regulatório")
    parser.add_argument("--balancete", type=Path,
                        help="arquivo CSV de balancete do BCB (4010/4060) ou pasta com vários")
    parser.add_argument("--serie", type=Path,
                        help="pasta com balancetes de várias datas-base: gera a série histórica")
    argumentos = parser.parse_args()
    if argumentos.serie:
        analisar_series(argumentos.serie)
    elif argumentos.balancete:
        analisar_balancetes(argumentos.balancete)
    else:
        exemplo_didatico()


if __name__ == "__main__":
    main()
