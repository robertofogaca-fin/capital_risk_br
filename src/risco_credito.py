"""RWACPAD — risco de crédito pela abordagem padronizada (Res. BCB 229/2022, versão didática).

EAD = saldo no balanço + FCC x saldo fora do balanço
RWACPAD = soma(EAD x FPR)
"""
import pandas as pd

COLUNAS_OBRIGATORIAS = {
    "id_operacao", "contraparte", "produto", "classe_exposicao",
    "saldo_balanco", "saldo_off", "tipo_off",
}


def validar_carteira(carteira: pd.DataFrame, parametros: dict) -> None:
    faltantes = COLUNAS_OBRIGATORIAS - set(carteira.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes na carteira: {', '.join(sorted(faltantes))}")

    if (carteira[["saldo_balanco", "saldo_off"]] < 0).any().any():
        raise ValueError("Saldos não podem ser negativos.")

    classes_invalidas = set(carteira["classe_exposicao"]) - set(parametros["fpr_por_classe"])
    if classes_invalidas:
        raise ValueError(f"Classe de exposição sem FPR configurado: {sorted(classes_invalidas)}")

    tipos_invalidos = set(carteira["tipo_off"]) - set(parametros["fcc_por_tipo"])
    if tipos_invalidos:
        raise ValueError(f"Tipo de exposição fora do balanço sem FCC: {sorted(tipos_invalidos)}")


def calcular_rwa_por_operacao(carteira: pd.DataFrame, parametros: dict) -> pd.DataFrame:
    validar_carteira(carteira, parametros)

    resultado = carteira.copy()
    resultado["fcc"] = resultado["tipo_off"].map(parametros["fcc_por_tipo"])
    resultado["ead"] = resultado["saldo_balanco"] + resultado["fcc"] * resultado["saldo_off"]
    resultado["fpr"] = resultado["classe_exposicao"].map(parametros["fpr_por_classe"])
    resultado["rwa"] = resultado["ead"] * resultado["fpr"]
    return resultado


def calcular_rwa_credito(carteira: pd.DataFrame, parametros: dict) -> float:
    return float(calcular_rwa_por_operacao(carteira, parametros)["rwa"].sum())


def rwa_por_classe(carteira_com_rwa: pd.DataFrame) -> pd.DataFrame:
    return (
        carteira_com_rwa.groupby("classe_exposicao", as_index=False)[["ead", "rwa"]]
        .sum()
        .sort_values("rwa", ascending=False)
    )
