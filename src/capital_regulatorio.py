"""Composição do Patrimônio de Referência (Res. CMN 4.955/2021, versão didática).

Capital Principal (CP) = elementos de CP - ajustes prudenciais
Nível I               = CP + Capital Complementar
PR                    = Nível I + Nível II
"""
import pandas as pd

NIVEIS_VALIDOS = {"capital_principal", "ajuste_prudencial", "capital_complementar", "nivel_2"}


def validar_capital(capital: pd.DataFrame) -> None:
    faltantes = {"componente", "nivel", "valor"} - set(capital.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes no capital: {', '.join(sorted(faltantes))}")

    invalidos = set(capital["nivel"]) - NIVEIS_VALIDOS
    if invalidos:
        raise ValueError(f"Nível de capital inválido: {sorted(invalidos)}")

    if (capital["valor"] < 0).any():
        raise ValueError("Informe os valores em módulo; ajustes prudenciais são deduzidos pelo nível.")


def compor_pr(capital: pd.DataFrame) -> dict:
    validar_capital(capital)
    soma = capital.groupby("nivel")["valor"].sum()

    capital_principal = soma.get("capital_principal", 0.0) - soma.get("ajuste_prudencial", 0.0)
    nivel_1 = capital_principal + soma.get("capital_complementar", 0.0)
    pr = nivel_1 + soma.get("nivel_2", 0.0)

    return {
        "capital_principal": float(capital_principal),
        "nivel_1": float(nivel_1),
        "patrimonio_referencia": float(pr),
        "ajustes_prudenciais": float(soma.get("ajuste_prudencial", 0.0)),
    }


def carregar_capital(caminho_arquivo: str) -> dict:
    return compor_pr(pd.read_csv(caminho_arquivo, encoding="utf-8"))
