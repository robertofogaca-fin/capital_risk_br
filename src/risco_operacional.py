"""RWAOPAD — risco operacional pela abordagem padronizada (Res. BCB 356/2023).

RWAOPAD = (1/F) x (BIC x ILM)

BI   = ILDC + SC + FC                       (art. 5º)
ILDC = min(média|II - IE|; 2,25% x média IEA) + média DI          (art. 6º)
SC   = max(média FI; média FE) + max(média OOI; média OOE)        (art. 7º)
FC   = média|NTB| + média|NBB|                                     (art. 8º)
BIC  = 12% até R$ 5 bi + 15% de R$ 5 bi a R$ 150 bi + 18% acima   (art. 4º)
ILM  = ln(e - 1 + (LC/BIC)^0,8)  -> S1 e S2; ILM = 1 para S4       (arts. 10 a 13)
LC   = média anual das perdas líquidas em 10 anos x 6              (art. 11)

Médias sobre os três últimos períodos anuais. Instituições sujeitas ao RWASP excluem
do BI as receitas e despesas de MOE, ADQ e PISP (art. 9º, § 1º).
"""
import math

import pandas as pd

COLUNAS_DRE = {
    "periodo", "receitas_juros", "despesas_juros", "ativos_rentaveis_medios", "dividendos",
    "receitas_servicos", "despesas_servicos", "receitas_servicos_pagamento",
    "despesas_servicos_pagamento", "outras_receitas_operacionais", "outras_despesas_operacionais",
    "resultado_carteira_negociacao", "resultado_carteira_bancaria",
}
COLUNAS_PERDAS = {"evento", "ano", "perda_bruta", "recuperacoes"}
SEGMENTOS_VALIDOS = {"S1", "S2", "S3", "S4"}


# ---------------------------------------------------------------------------
# Indicador de Negócios (BI)
# ---------------------------------------------------------------------------

def validar_dre(dre: pd.DataFrame, periodos_exigidos: int | None = 3) -> None:
    faltantes = COLUNAS_DRE - set(dre.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes na DRE operacional: {', '.join(sorted(faltantes))}")
    if periodos_exigidos is not None and len(dre) != periodos_exigidos:
        raise ValueError("A DRE operacional deve ter exatamente 3 períodos anuais (art. 2º).")
    if not 1 <= len(dre) <= 3:
        raise ValueError("A DRE operacional deve ter de 1 a 3 períodos anuais.")
    if (dre["ativos_rentaveis_medios"] < 0).any():
        raise ValueError("Ativos rentáveis não podem ser negativos.")
    if (dre["receitas_servicos_pagamento"] > dre["receitas_servicos"]).any() or \
       (dre["despesas_servicos_pagamento"] > dre["despesas_servicos"]).any():
        raise ValueError("Serviços de pagamento não podem superar o total de serviços.")


def calcular_componentes_bi(dre: pd.DataFrame, parametros: dict, sujeita_rwasp: bool,
                            periodos_exigidos: int | None = 3) -> dict:
    validar_dre(dre, periodos_exigidos)
    teto = parametros["risco_operacional"]["teto_ildc_sobre_iea"]

    margem_juros = (dre["receitas_juros"] - dre["despesas_juros"]).abs().mean()
    teto_ildc = teto * dre["ativos_rentaveis_medios"].mean()
    ildc = min(margem_juros, teto_ildc) + dre["dividendos"].mean()

    receitas_servicos = dre["receitas_servicos"]
    despesas_servicos = dre["despesas_servicos"]
    if sujeita_rwasp:
        receitas_servicos = receitas_servicos - dre["receitas_servicos_pagamento"]
        despesas_servicos = despesas_servicos - dre["despesas_servicos_pagamento"]

    sc = (max(receitas_servicos.mean(), despesas_servicos.abs().mean())
          + max(dre["outras_receitas_operacionais"].mean(),
                dre["outras_despesas_operacionais"].abs().mean()))

    fc = (dre["resultado_carteira_negociacao"].abs().mean()
          + dre["resultado_carteira_bancaria"].abs().mean())

    return {
        "margem_juros_media": float(margem_juros),
        "teto_ildc": float(teto_ildc),
        "teto_ildc_aplicado": bool(margem_juros > teto_ildc),
        "ILDC": float(ildc),
        "SC": float(sc),
        "FC": float(fc),
        "BI": float(ildc + sc + fc),
    }


def calcular_bic(bi: float, faixas: list[dict]) -> float:
    """Soma marginal por faixa (como uma tabela progressiva de IR)."""
    if bi < 0:
        raise ValueError("O BI não pode ser negativo.")
    bic, piso = 0.0, 0.0
    for faixa in faixas:
        teto = faixa["limite_superior"] or math.inf
        if bi > piso:
            bic += (min(bi, teto) - piso) * faixa["coeficiente"]
        piso = teto
    return bic


# ---------------------------------------------------------------------------
# Componente de perdas (LC) e multiplicador (ILM)
# ---------------------------------------------------------------------------

def preparar_perdas(perdas: pd.DataFrame, ano_base: int, parametros: dict) -> pd.DataFrame:
    faltantes = COLUNAS_PERDAS - set(perdas.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes nas perdas: {', '.join(sorted(faltantes))}")
    if (perdas[["perda_bruta", "recuperacoes"]] < 0).any().any():
        raise ValueError("Perdas e recuperações devem ser informadas em módulo.")

    ro = parametros["risco_operacional"]
    resultado = perdas.copy()
    resultado["perda_liquida"] = resultado["perda_bruta"] - resultado["recuperacoes"]
    inicio = ano_base - ro["janela_perdas_anos"] + 1
    resultado["na_janela"] = resultado["ano"].between(inicio, ano_base)
    resultado["acima_limiar"] = resultado["perda_liquida"] >= ro["limiar_perda_evento"]
    resultado["considerada"] = resultado["na_janela"] & resultado["acima_limiar"]
    return resultado


def calcular_lc(perdas_preparadas: pd.DataFrame, parametros: dict) -> float:
    ro = parametros["risco_operacional"]
    total = perdas_preparadas.loc[perdas_preparadas["considerada"], "perda_liquida"].sum()
    return float(total / ro["janela_perdas_anos"] * ro["multiplicador_lc"])


def calcular_ilm(lc: float, bic: float, expoente: float = 0.8) -> float:
    if bic <= 0:
        raise ValueError("O BIC deve ser maior que zero para calcular o ILM.")
    return math.log(math.e - 1 + (lc / bic) ** expoente)


def ilm_aplicavel(segmento: str, ilm_calculado: float, s3_opta_calculado: bool = False) -> float:
    if segmento == "S5":
        raise ValueError("S5 usa metodologia simplificada, fora do escopo da Res. BCB 356.")
    if segmento not in SEGMENTOS_VALIDOS:
        raise ValueError(f"Segmento inválido: {segmento}")
    if segmento in {"S1", "S2"} or (segmento == "S3" and s3_opta_calculado):
        return ilm_calculado
    return 1.0


# ---------------------------------------------------------------------------
# Transição (art. 19) e consolidação
# ---------------------------------------------------------------------------

def aplicar_transicao(rwaopad_calculado: float, ano_base: int, parametros: dict) -> tuple[float, str]:
    transicao = parametros["risco_operacional"].get("transicao", {})
    if not transicao.get("aplicar", False):
        return rwaopad_calculado, "sem transição"

    base_2024 = transicao["rwaopad_dez2024"]
    percentual = transicao["percentual_por_ano"].get(str(ano_base))
    if percentual is None:
        return rwaopad_calculado, f"transição encerrada ou não aplicável em {ano_base}"
    if rwaopad_calculado <= base_2024:
        return rwaopad_calculado, "novo valor não supera o de dez/2024"

    aplicado = base_2024 + percentual * (rwaopad_calculado - base_2024)
    return aplicado, f"dez/2024 + {percentual:.0%} da diferença ({ano_base})"


def calcular_rwaopad(dre: pd.DataFrame, perdas: pd.DataFrame, parametros: dict) -> dict:
    inst = parametros["instituicao"]
    ro = parametros["risco_operacional"]
    fator_f = parametros["requerimentos_minimos"]["patrimonio_referencia"]
    ano_base = int(str(inst["data_base"])[:4])

    componentes = calcular_componentes_bi(dre, parametros, inst["sujeita_rwasp"])
    bic = calcular_bic(componentes["BI"], ro["faixas_bic"])

    perdas_prep = preparar_perdas(perdas, ano_base, parametros)
    lc = calcular_lc(perdas_prep, parametros)
    ilm_calc = calcular_ilm(lc, bic, ro["expoente_ilm"])
    ilm = ilm_aplicavel(inst["segmento"], ilm_calc, inst.get("s3_opta_ilm_calculado", False))

    rwaopad_integral = bic * ilm / fator_f
    rwaopad, regra = aplicar_transicao(rwaopad_integral, ano_base, parametros)

    return {
        **componentes,
        "BIC": bic,
        "LC": lc,
        "ILM_calculado": ilm_calc,
        "ILM_aplicado": ilm,
        "segmento": inst["segmento"],
        "F": fator_f,
        "RWAOPAD_integral": rwaopad_integral,
        "RWAOPAD": rwaopad,
        "regra_transicao": regra,
        "RWAOPAD_se_ILM_calculado": bic * ilm_calc / fator_f,
        "perdas": perdas_prep,
    }
