"""Requerimento de capital estimado a partir de balancete Cosif público.

Regimes:
  banco  -> PR, Nível I e Capital Principal x RWA (Res. CMN 4.955 e 4.958), com ACP
            RWA = RWACPAD (por conta Cosif) + RWAOPAD (BI do balancete) + RWAMPAD (informado) + RWASP
  ip     -> PRIP x F' x RWAIP (Res. BCB 198), RWAIP = RWASP + RWARCSimp + RWACAMSimp

É uma ESTIMATIVA com dados públicos: o cálculo oficial usa informações por operação
(contraparte, prazo, colateral, LTV), base de perdas e posições de mercado que não estão no balancete.
Cada premissa fica registrada no resultado.
"""
import copy
import sys
from pathlib import Path

import pandas as pd

from src.basileia import avaliar_requerimentos, capacidade_crescimento_rwa, capital_necessario
from src.balancete_cosif import analiticas, conciliar, identificacao, ler_balancete
from src.risco_operacional import calcular_bic

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

RAIZ = Path(__file__).resolve().parent.parent
PASTA_CONFIG = RAIZ / "config"

# Ativos rentáveis (IEA) para o teto do ILDC
PREFIXOS_IEA = ("12", "13110", "132", "134", "136", "137", "142", "16", "17", "181")
CONTAS_IGNORADAS = ("3999999",)  # linha de total geral do ativo publicada no grupo 3


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

def carregar_mapeamento(nome: str) -> pd.DataFrame:
    mapa = pd.read_csv(PASTA_CONFIG / nome, dtype=str, encoding="utf-8").fillna("")
    return mapa.assign(tamanho=mapa["prefixo"].str.len()).sort_values("tamanho", ascending=False)


def arquivo_instituicoes() -> Path:
    local = PASTA_CONFIG / "instituicoes.local.toml"
    return local if local.exists() else PASTA_CONFIG / "instituicoes.exemplo.toml"


def parametros_instituicao(cnpj: str) -> dict:
    with open(arquivo_instituicoes(), "rb") as arquivo:
        cadastro = tomllib.load(arquivo)
    dados = copy.deepcopy(cadastro.get("padrao", {}))
    especificos = cadastro.get(str(cnpj).zfill(8), {})
    for chave, valor in especificos.items():
        if isinstance(valor, dict):
            dados.setdefault(chave, {}).update(valor)
        else:
            dados[chave] = valor
    dados["cadastrada"] = bool(especificos)
    return dados


def detectar_regime(ident: dict) -> str:
    return "ip" if "PAGAMENTO" in ident["taxonomia"].upper() else "banco"


def apelido_padrao(ident: dict, regime: str) -> str:
    if regime == "ip":
        return "Instituição de pagamento"
    return "Conglomerado prudencial" if ident["documento"] in {"4060", "4066"} else "Banco (individual)"


def anonimizar(ident: dict, regime: str, inst: dict, parametros: dict) -> dict:
    saida = parametros.get("saida", {})
    ident = {**ident, "fonte": saida.get("fonte", "Balancete Cosif — Banco Central do Brasil")}
    if not saida.get("anonimizar", True):
        ident["apelido"] = ident["instituicao"]
        return ident
    ident.update({"apelido": inst.get("apelido") or apelido_padrao(ident, regime),
                  "instituicao": inst.get("apelido") or apelido_padrao(ident, regime),
                  "cnpj": "omitido", "conglomerado": ""})
    return ident


# ---------------------------------------------------------------------------
# Mapeamento conta a conta
# ---------------------------------------------------------------------------

def _casar(conta: str, mapa: pd.DataFrame) -> pd.Series | None:
    for _, linha in mapa.iterrows():
        if conta.startswith(linha["prefixo"]):
            return linha
    return None


def mapear(contas: pd.DataFrame, mapa: pd.DataFrame, classe_padrao: str) -> pd.DataFrame:
    contas = contas[~contas["conta"].str.startswith(CONTAS_IGNORADAS)].copy()
    registros = []
    for _, conta in contas.iterrows():
        regra = _casar(conta["conta"], mapa)
        if regra is not None:
            registros.append({"prefixo_regra": regra["prefixo"], "destino": regra["destino"],
                              "classe": regra["classe"], "fcc": float(regra["fcc"] or 1),
                              "moeda_estrangeira": regra["moeda_estrangeira"] == "1",
                              "observacao": regra["observacao"]})
        elif conta["grupo"] in {"1", "2"}:
            registros.append({"prefixo_regra": "", "destino": "exposicao", "classe": classe_padrao,
                              "fcc": 1.0, "moeda_estrangeira": False,
                              "observacao": "SEM MAPEAMENTO — tratada como 100%"})
        else:
            registros.append({"prefixo_regra": "", "destino": "nao_utilizado", "classe": "",
                              "fcc": 0.0, "moeda_estrangeira": False, "observacao": ""})
    return pd.concat([contas.reset_index(drop=True), pd.DataFrame(registros)], axis=1)


def _soma(m: pd.DataFrame, destino: str) -> float:
    return float(m.loc[m["destino"] == destino, "saldo"].sum())


# ---------------------------------------------------------------------------
# Indicador de Negócios a partir das contas de resultado
# ---------------------------------------------------------------------------

def meses_no_semestre(data_base: str) -> int:
    mes = int(str(data_base)[4:6])
    return mes - 6 if mes > 6 else mes


def calcular_bi_balancete(contas: pd.DataFrame, data_base: str, parametros: dict) -> dict:
    mapa = carregar_mapeamento("mapeamento_cosif_bi.csv")
    resultado = contas[contas["grupo"].isin(["7", "8"])].copy()
    resultado["componente"] = [
        (r["componente"] if (r := _casar(c, mapa)) is not None else "nao_mapeado")
        for c in resultado["conta"]
    ]
    meses = meses_no_semestre(data_base)
    fator = 12 / meses
    soma = resultado.groupby("componente")["saldo"].sum()

    def anual(chave):
        return float(soma.get(chave, 0.0)) * fator

    iea = float(contas.loc[contas["conta"].str.startswith(PREFIXOS_IEA)
                           & ~contas["conta"].str.startswith("133"), "saldo"].sum())
    margem = abs(anual("ii") + anual("ie"))  # despesas vêm negativas
    teto = parametros["risco_operacional"]["teto_ildc_sobre_iea"] * iea
    ildc = min(margem, teto) + anual("di")
    sc = max(anual("fi"), abs(anual("fe"))) + max(anual("ooi"), abs(anual("ooe")))
    fc = abs(anual("fin"))
    return {
        "meses_apurados": meses, "fator_anualizacao": fator, "IEA": iea,
        "margem_juros_anual": margem, "teto_ildc": teto, "ILDC": ildc, "SC": sc, "FC": fc,
        "BI": ildc + sc + fc,
        "contas_nao_mapeadas": resultado.loc[resultado["componente"] == "nao_mapeado",
                                             ["conta", "nome_conta", "saldo"]],
        "detalhe": resultado[["conta", "nome_conta", "saldo", "componente"]],
    }


# ---------------------------------------------------------------------------
# Regime banco / conglomerado
# ---------------------------------------------------------------------------

def calcular_banco(m: pd.DataFrame, ident: dict, parametros: dict, inst: dict) -> dict:
    pb = parametros["balancete_banco"]
    premissas = []

    pl, resultado = _soma(m, "capital_principal"), _soma(m, "resultado")
    intangivel, atuarial = _soma(m, "deducao_intangivel"), _soma(m, "deducao_atuarial")
    dta = _soma(m, "dta")
    dta_deduzido = dta * inst["dta_percentual_deduzido"]
    cp_antes = pl + resultado - intangivel - atuarial - dta_deduzido

    participacoes = _soma(m, "participacoes")
    individual = ident["documento"] in {"4010", "4016"}
    limiar = pb["limiar_deducao_cp"] * cp_antes
    part_deduzida = 0.0 if individual else max(0.0, participacoes - limiar)
    cp = cp_antes - part_deduzida

    instrumentos = _soma(m, "instrumentos_capital")
    nivel_2 = min(_soma(m, "nivel_2_autorizado"), instrumentos)
    complementar = instrumentos - nivel_2

    capital = {"capital_principal": cp, "nivel_1": cp + complementar,
               "patrimonio_referencia": cp + complementar + nivel_2}
    composicao = [
        ("Patrimônio líquido (grupo 6.1)", pl), ("Resultado do período (grupos 7 e 8)", resultado),
        ("(-) Intangível e ágio", -intangivel), ("(-) Ativo atuarial", -atuarial),
        ("(-) Créditos tributários deduzidos", -dta_deduzido),
        ("(-) Participações acima de 10% do CP", -part_deduzida),
        ("= Capital Principal", cp), ("+ Capital Complementar", complementar),
        ("= Nível I", capital["nivel_1"]), ("+ Nível II", nivel_2),
        ("= Patrimônio de Referência", capital["patrimonio_referencia"]),
    ]
    premissas += [
        f"Créditos tributários: {inst['dta_percentual_deduzido']:.0%} deduzido; restante ponderado a "
        f"{parametros['balancete_banco']['fpr']['dta_nao_deduzido']:.0%} (convertíveis, Lei 12.838/2013).",
        "Participação de não controladores não computada no Capital Principal.",
        "Nível II = conta 30981000 (autorizados); Capital Complementar = 43910000 − Nível II.",
        ("Participações (balancete individual): ponderadas a 250%, sem dedução — no conglomerado "
         "prudencial as controladas são consolidadas." if individual else
         "Participações fora do conglomerado: excedente a 10% do CP deduzido; restante ponderado a 250%."),
    ]

    # RWACPAD
    fpr = pb["fpr"]
    expos = m[m["destino"].isin(["exposicao", "exposicao_off"])].copy()
    expos["ead"] = expos["saldo"] * expos["fcc"].where(expos["destino"] == "exposicao_off", 1.0)
    extras = pd.DataFrame([
        {"conta": "18825000", "nome_conta": "Créditos tributários não deduzidos", "saldo": dta - dta_deduzido,
         "destino": "exposicao", "classe": "dta_nao_deduzido", "ead": dta - dta_deduzido, "fcc": 1.0,
         "observacao": "Parcela não deduzida do CP"},
        {"conta": "21200000", "nome_conta": "Participações não deduzidas", "saldo": participacoes - part_deduzida,
         "destino": "exposicao", "classe": "acoes_e_participacoes", "ead": participacoes - part_deduzida,
         "fcc": 1.0, "observacao": "Parcela não deduzida do CP"},
    ])
    expos = pd.concat([expos, extras], ignore_index=True)
    expos["fpr"] = expos["classe"].map(fpr)
    if expos["fpr"].isna().any():
        raise ValueError(f"Classe sem FPR: {sorted(set(expos.loc[expos['fpr'].isna(), 'classe']))}")
    expos["rwa"] = expos["ead"] * expos["fpr"]
    rwacpad = float(expos["rwa"].sum())

    # RWAOPAD
    bi = calcular_bi_balancete(m, ident["data_base"], parametros)
    bic = calcular_bic(bi["BI"], parametros["risco_operacional"]["faixas_bic"])
    fator_f = parametros["requerimentos_minimos"]["patrimonio_referencia"]
    rwaopad = bic / fator_f
    premissas.append(
        f"RWAOPAD: BI de um único período ({bi['meses_apurados']} meses) anualizado x{bi['fator_anualizacao']:.0f}; "
        "a norma usa a média de 3 anos. ILM = 1 (base de perdas não é pública).")

    # RWASP (Tipo 1 em S2-S5)
    sujeita_sp = inst["segmento"] != "S1"
    moe = (parametros["instituicao_pagamento"]["moe_transacoes"] * _soma(m, "base_moe_transacoes")
           + parametros["instituicao_pagamento"]["moe_saldo"] * _soma(m, "base_moe_saldo"))
    rwasp = moe / fator_f if sujeita_sp else 0.0
    rwampad = float(inst.get("rwampad", 0.0))
    if rwampad == 0:
        premissas.append("RWAMPAD = 0: risco de mercado não é estimável pelo balancete "
                         "(informe o valor do Pilar 3 no cadastro de instituições).")

    parcelas = {"RWACPAD": rwacpad, "RWAMPAD": rwampad, "RWAOPAD": rwaopad, "RWASP": rwasp}
    parcelas["RWA"] = sum(parcelas.values())

    params = copy.deepcopy(parametros)
    params["adicional_capital_principal"]["sistemico"] = inst.get("acp_sistemico", 0.0)
    avaliacao = avaliar_requerimentos(capital, parcelas["RWA"], params)

    params = copy.deepcopy(parametros)
    params["adicional_capital_principal"]["sistemico"] = inst.get("acp_sistemico", 0.0)
    avaliacao = avaliar_requerimentos(capital, parcelas["RWA"], params)

    comparacao = None
    publicado = inst.get("publicado", {})
    if (publicado and str(publicado.get("data_base")) == ident["data_base"]
            and str(publicado.get("documento", "4060")) == ident["documento"]):
        linhas = []
        for nome, chave in (("Capital Principal", "capital_principal"),
                            ("Patrimônio de Referência", "patrimonio_referencia")):
            if chave in publicado:
                estimado = capital[chave] / parcelas["RWA"]
                requerido = float(avaliacao.loc[avaliacao["nivel"] == nome, "requerido"].iloc[0])
                linhas.append({"nivel": nome, "estimado": estimado, "publicado": publicado[chave],
                               "requerido": requerido,
                               "situacao_divulgada": "ADEQUADO" if publicado[chave] >= requerido else "ABAIXO",
                               "diferenca_pp": (estimado - publicado[chave]) * 100,
                               "rwa_implicito": capital[chave] / publicado[chave]})
        comparacao = pd.DataFrame(linhas)

    return {
        "regime": "banco", "capital": capital, "comparacao": comparacao, "composicao": composicao, "parcelas": parcelas,
        "avaliacao": avaliacao, "capacidade": capacidade_crescimento_rwa(avaliacao),
        "aporte": capital_necessario(avaliacao), "exposicoes": expos,
        "bi": {**bi, "BIC": bic, "RWAOPAD": rwaopad}, "premissas": premissas,
    }


# ---------------------------------------------------------------------------
# Regime instituição de pagamento (Res. BCB 198)
# ---------------------------------------------------------------------------

def calcular_ip(m: pd.DataFrame, ident: dict, parametros: dict, inst: dict) -> dict:
    p = parametros["instituicao_pagamento"]
    f_linha = p["fator_f_linha"]
    premissas = []

    pl, resultado = _soma(m, "capital_principal"), _soma(m, "resultado")
    deducoes = {
        "(-) Intangível": _soma(m, "deducao_intangivel"),
        "(-) Créditos tributários": _soma(m, "dta"),
        "(-) Ativo atuarial": _soma(m, "deducao_atuarial"),
        "(-) Participações não consolidadas": _soma(m, "deducao_participacoes"),
    }
    prip = pl + resultado - sum(deducoes.values())
    composicao = ([("Patrimônio líquido (grupo 6.1)", pl), ("Resultado do período (grupos 7 e 8)", resultado)]
                  + [(k, -v) for k, v in deducoes.items()] + [("= PRIP", prip)])

    fpr = {**p["fpr"], "elevado": 1 / f_linha}
    expos = m[m["destino"].isin(["exposicao", "exposicao_off"])].copy()
    expos["ead"] = expos["saldo"] * expos["fcc"].where(expos["destino"] == "exposicao_off", 1.0)
    expos["fpr"] = expos["classe"].map(fpr)
    expos["rwa"] = expos["ead"] * expos["fpr"]
    rwarcsimp = float(expos["rwa"].sum())

    exposicao_cambial = abs(float(m.loc[m["moeda_estrangeira"], "saldo"].sum()))
    rwacamsimp = exposicao_cambial * p["fpr_rwacamsimp"]

    volumes = inst.get("volumes_ip", {})
    base_transacoes, base_saldo = _soma(m, "base_moe_transacoes"), _soma(m, "base_moe_saldo")
    componentes_sp = {
        "MOE — transações (0,2%)": p["moe_transacoes"] * base_transacoes,
        "MOE — saldo pré-pago (1%)": p["moe_saldo"] * base_saldo,
        "CPOS (4%)": p["cpos"] * volumes.get("cpos", 0.0),
        "ADQ (2%)": p["adq"] * volumes.get("adq", 0.0),
        "PISP (1,5%)": p["pisp"] * volumes.get("pisp", 0.0),
    }
    rwasp = sum(componentes_sp.values()) / p["fator_d_rwasp"]

    parcelas = {"RWASP": rwasp, "RWARCSimp": rwarcsimp, "RWACAMSimp": rwacamsimp}
    parcelas["RWAIP"] = sum(parcelas.values())
    requerido = f_linha * parcelas["RWAIP"]
    folga = prip - requerido

    premissas += [
        "MOE calculado sobre as contas de controle de saldo médio 30971000 e 30969000.",
        "CPOS, ADQ e PISP não constam do balancete: volumes informados no cadastro de instituições "
        f"(atual: {volumes}).",
        "Renda fixa livre (13110000) tratada como título público federal (Reduzido I).",
        "RWACAMSimp = exposição bruta em moeda estrangeira x 100% (passivos em moeda estrangeira não identificados).",
        "Créditos tributários e participações deduzidos integralmente (art. 4º, Res. BCB 198).",
    ]
    if ident["documento"] == "4010":
        premissas.append("Balancete individual: se a IP integrar conglomerado, o requerimento é consolidado.")

    return {
        "regime": "ip", "prip": prip, "composicao": composicao, "parcelas": parcelas,
        "componentes_sp": componentes_sp, "requerido": requerido, "folga": folga,
        "indice": prip / parcelas["RWAIP"], "f_linha": f_linha,
        "capacidade": folga / f_linha, "exposicoes": expos, "premissas": premissas,
    }


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def analisar_balancete(caminho: str | Path, parametros: dict) -> dict:
    balancete = ler_balancete(caminho)
    ident = identificacao(balancete)
    regime = detectar_regime(ident)
    inst = parametros_instituicao(ident["cnpj"])

    mapa = carregar_mapeamento("mapeamento_cosif_ip.csv" if regime == "ip" else "mapeamento_cosif_banco.csv")
    m = mapear(analiticas(balancete), mapa, "padrao" if regime == "ip" else "outros_ativos")

    resultado = (calcular_ip if regime == "ip" else calcular_banco)(m, ident, parametros, inst)
    cnpj_original = ident["cnpj"]
    ident = anonimizar(ident, regime, inst, parametros)
    if regime == "banco" and ident["documento"] == "4010":
        resultado["premissas"].append(
            "Balancete INDIVIDUAL de banco: o requerimento oficial é apurado no conglomerado prudencial "
            "(documento 4060). Use o 4010 apenas como comparação.")
    if not inst["cadastrada"]:
        resultado["premissas"].append(
            f"Instituição sem cadastro em {arquivo_instituicoes().name}: usados os parâmetros padrão "
            f"(segmento {inst['segmento']}).")

    sem_mapa = m[m["observacao"].str.startswith("SEM MAPEAMENTO")]
    conc = conciliar(balancete)
    return {**resultado, "identificacao": ident, "cnpj_original": cnpj_original, "instituicao": inst, "mapeamento": m,
            "sem_mapeamento": sem_mapa,
            "conciliacao": conc[~conc["grupo"].isin(["3", "9"])]}
