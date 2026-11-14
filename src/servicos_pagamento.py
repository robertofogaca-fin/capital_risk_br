"""RWASP — riscos associados a serviços de pagamento (Res. BCB 202/2022; Res. CMN 4.958, art. 3º).

RWASP = (1/F) x (MOE + ADQ + PISP)

MOE  = 0,2% x média mensal de pagamentos e transferências
     + 1%   x média mensal do saldo de moeda eletrônica emitida
ADQ  = 2%   x média mensal das transações credenciadas (credenciador/subcredenciador)
PISP = 1,5% x média mensal das transações iniciadas
Médias dos últimos 12 meses. Os percentuais ficam em parametros.toml.
"""
import pandas as pd

COLUNAS = {"mes", "pagamentos_transferencias", "saldo_moeda_eletronica",
           "transacoes_credenciadas", "transacoes_iniciadas"}


def validar_servicos(servicos: pd.DataFrame, meses: int) -> None:
    faltantes = COLUNAS - set(servicos.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes em serviços de pagamento: {', '.join(sorted(faltantes))}")
    if len(servicos) != meses:
        raise ValueError(f"Informe exatamente {meses} meses de serviços de pagamento.")
    if servicos["mes"].duplicated().any():
        raise ValueError("Há meses duplicados em serviços de pagamento.")
    if (servicos[list(COLUNAS - {"mes"})] < 0).any().any():
        raise ValueError("Valores de serviços de pagamento não podem ser negativos.")


def calcular_rwasp(servicos: pd.DataFrame, parametros: dict) -> dict:
    sp = parametros["servicos_pagamento"]
    fator_f = parametros["requerimentos_minimos"]["patrimonio_referencia"]

    if not parametros["instituicao"].get("sujeita_rwasp", False):
        return {"MOE": 0.0, "ADQ": 0.0, "PISP": 0.0, "total_componentes": 0.0, "RWASP": 0.0,
                "aplicavel": False}

    validar_servicos(servicos, sp["meses_media"])
    medias = servicos.drop(columns="mes").mean()

    moe_pagamentos = sp["moe_pagamentos_transferencias"] * medias["pagamentos_transferencias"]
    moe_saldo = sp["moe_saldo_moeda_eletronica"] * medias["saldo_moeda_eletronica"]
    adq = sp["adq_credenciamento"] * medias["transacoes_credenciadas"]
    pisp = sp["pisp_iniciacao"] * medias["transacoes_iniciadas"]
    total = moe_pagamentos + moe_saldo + adq + pisp

    return {
        "media_pagamentos_transferencias": float(medias["pagamentos_transferencias"]),
        "media_saldo_moeda_eletronica": float(medias["saldo_moeda_eletronica"]),
        "media_transacoes_credenciadas": float(medias["transacoes_credenciadas"]),
        "media_transacoes_iniciadas": float(medias["transacoes_iniciadas"]),
        "MOE_pagamentos": float(moe_pagamentos),
        "MOE_saldo": float(moe_saldo),
        "MOE": float(moe_pagamentos + moe_saldo),
        "ADQ": float(adq),
        "PISP": float(pisp),
        "total_componentes": float(total),
        "F": fator_f,
        "RWASP": float(total / fator_f),
        "aplicavel": True,
    }
