"""Fase 3 — cenários de estresse sobre o capital regulatório.

Cada cenário aplica choques sobre a posição da data-base e recalcula capital, RWA e índices:
  Δ capital = − perda_cp × capital
              − perda_credito × EAD de crédito × (1 − alíquota)
              − choque_juros × duration × exposição a valor justo × (1 − alíquota)
  Δ RWA     = crescimento_credito × RWA de crédito + crescimento_pagamentos × RWASP

O teste reverso responde: qual perda o capital absorve e quanto o RWA pode crescer antes de
violar o requerido (mínimo + ACP).
"""
import sys
from pathlib import Path

import pandas as pd

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

CAMINHO_CENARIOS = Path(__file__).resolve().parent.parent / "config" / "cenarios.toml"
CLASSES_CREDITO_BANCO = {"varejo", "corporativo", "imobiliario_residencial", "imobiliario_comercial"}
CLASSES_CREDITO_IP = {"reduzido_iii"}
CHOQUES = ("crescimento_credito", "perda_credito", "choque_juros", "perda_cp", "crescimento_pagamentos")


def carregar_cenarios(caminho: str | Path = CAMINHO_CENARIOS) -> dict:
    with open(caminho, "rb") as arquivo:
        dados = tomllib.load(arquivo)
    for cenario in dados["cenarios"]:
        for chave in CHOQUES:
            cenario.setdefault(chave, 0.0)
            if cenario[chave] < 0:
                raise ValueError(f"Choque negativo no cenário '{cenario['nome']}': {chave}")
    return dados


def _exposicao_valor_justo(mapeamento: pd.DataFrame, versao: str) -> float:
    contas = mapeamento.set_index("conta")["saldo"]
    if versao == "legado":  # sem classificação por categoria: carteira livre de TVM
        return float(mapeamento.loc[mapeamento["conta"].str.startswith("131"), "saldo"].sum())
    ativos = mapeamento.loc[mapeamento["conta"].str.startswith(("32120", "32130")), "saldo"].sum()
    passivos = mapeamento.loc[mapeamento["conta"].str.startswith("32180"), "saldo"].sum()
    return float(max(0.0, ativos - passivos)) if len(contas) else 0.0


def base_do_resultado(r: dict, calibrar: bool = True) -> dict:
    """Extrai a posição-base de um resultado de analisar_balancete.

    Com calibrar=True e índice divulgado cadastrado (bancos), o RWA estimado é escalado para o
    RWA implícito pelo índice de Basileia divulgado: o cenário base reproduz a posição oficial e os
    choques medem a sensibilidade a partir dela.
    """
    expos = r["exposicoes"]
    if r["regime"] == "ip":
        credito = expos[expos["classe"].isin(CLASSES_CREDITO_IP)]
        return {
            "regime": "ip", "niveis": {"PRIP": r["prip"]}, "requeridos": {"PRIP": r["f_linha"]},
            "parcelas": {k: v for k, v in r["parcelas"].items() if k != "RWAIP"},
            "parcela_credito": "RWARCSimp", "credito_ead": float(credito["ead"].sum()),
            "credito_rwa": float(credito["rwa"].sum()),
            "exposicao_juros": _exposicao_valor_justo(r["mapeamento"], r.get("versao_cosif", "atual")),
            "calibracao_rwa": 1.0,
        }
    credito = expos[expos["classe"].isin(CLASSES_CREDITO_BANCO)]
    av = r["avaliacao"].set_index("nivel")
    fator = 1.0
    comparacao = r.get("comparacao")
    if calibrar and comparacao is not None and not comparacao.empty:
        pr = comparacao.set_index("nivel").get("rwa_implicito", pd.Series()).get("Patrimônio de Referência")
        if pr:
            fator = pr / r["parcelas"]["RWA"]
    return {"calibracao_rwa": fator, **{
        "parcelas": {k: v * fator for k, v in r["parcelas"].items() if k != "RWA"},
        "credito_rwa": float(credito["rwa"].sum()) * fator}, **{
        "regime": "banco",
        "niveis": {"Capital Principal": r["capital"]["capital_principal"], "Nível I": r["capital"]["nivel_1"],
                   "Patrimônio de Referência": r["capital"]["patrimonio_referencia"]},
        "requeridos": av["requerido"].to_dict(),
        "parcela_credito": "RWACPAD", "credito_ead": float(credito["ead"].sum()),
        "exposicao_juros": _exposicao_valor_justo(r["mapeamento"], r.get("versao_cosif", "atual")),
    }}


def aplicar_cenario(base: dict, cenario: dict, premissas: dict) -> dict:
    aliquota = premissas["aliquota_tributos_ip" if base["regime"] == "ip" else "aliquota_tributos_banco"]
    capital_ref = next(iter(base["niveis"].values()))  # CP (banco) ou PRIP (IP)

    perda_operacional = cenario["perda_cp"] * capital_ref
    perda_credito = cenario["perda_credito"] * base["credito_ead"] * (1 - aliquota)
    perda_juros = (cenario["choque_juros"] * premissas["duration_carteira"]
                   * base["exposicao_juros"] * (1 - aliquota))
    impacto = perda_operacional + perda_credito + perda_juros

    parcelas = dict(base["parcelas"])
    parcelas[base["parcela_credito"]] += cenario["crescimento_credito"] * base["credito_rwa"]
    if "RWASP" in parcelas:
        parcelas["RWASP"] *= 1 + cenario["crescimento_pagamentos"]
    rwa = sum(parcelas.values())

    linha = {"cenario": cenario["nome"], "perda_operacional": perda_operacional,
             "perda_credito": perda_credito, "perda_juros": perda_juros, "impacto_capital": -impacto,
             **parcelas, "rwa_total": rwa}
    situacoes = []
    for nivel, valor in base["niveis"].items():
        estressado = valor - impacto
        requerido = base["requeridos"][nivel]
        linha[f"capital::{nivel}"] = estressado
        linha[f"indice::{nivel}"] = estressado / rwa
        linha[f"folga::{nivel}"] = estressado - requerido * rwa
        situacoes.append(linha[f"folga::{nivel}"] >= 0)
    linha["situacao"] = "ADEQUADO" if all(situacoes) else "ABAIXO DO REQUERIDO"
    return linha


def executar(base: dict, cenarios: dict | None = None) -> pd.DataFrame:
    cenarios = cenarios or carregar_cenarios()
    tabela = pd.DataFrame([aplicar_cenario(base, c, cenarios["premissas"]) for c in cenarios["cenarios"]])
    principal = next(iter(base["niveis"]))
    indice_base = base["niveis"][principal] / sum(base["parcelas"].values())
    tabela["variacao_pp"] = (tabela[f"indice::{principal}"] - indice_base) * 100
    return tabela


def teste_reverso(base: dict, premissas: dict) -> dict:
    """Perda máxima absorvível e crescimento máximo de RWA até o requerido (mínimo + ACP)."""
    rwa = sum(base["parcelas"].values())
    folgas = {n: v - base["requeridos"][n] * rwa for n, v in base["niveis"].items()}
    limitante = min(folgas, key=folgas.get)
    perda_max = folgas[limitante]
    crescimento_rwa = min(f / base["requeridos"][n] for n, f in folgas.items())
    aliquota = premissas["aliquota_tributos_ip" if base["regime"] == "ip" else "aliquota_tributos_banco"]
    return {
        "nivel_limitante": limitante,
        "perda_maxima_absorvivel": float(perda_max),
        "perda_credito_equivalente_pct": (float(perda_max / (1 - aliquota) / base["credito_ead"])
                                          if base["credito_ead"] else float("nan")),
        "crescimento_rwa_maximo": float(crescimento_rwa),
        "crescimento_rwa_maximo_pct": float(crescimento_rwa / rwa),
    }


def tabela_apresentacao(tabela: pd.DataFrame) -> pd.DataFrame:
    """Colunas em português para relatório e dashboard."""
    renomear = {"cenario": "Cenário", "perda_operacional": "Prejuízo operacional (R$)",
                "perda_credito": "Perda de crédito líquida (R$)", "perda_juros": "Perda com juros líquida (R$)",
                "impacto_capital": "Impacto no capital (R$)", "rwa_total": "RWA estressado (R$)",
                "variacao_pp": "Variação do índice (p.p.)", "situacao": "Situação"}
    saida = tabela.rename(columns=renomear)
    novos = {}
    for coluna in saida.columns:
        if coluna.startswith("capital::"):
            novos[coluna] = f"{coluna.split('::')[1]} (R$)"
        elif coluna.startswith("indice::"):
            novos[coluna] = f"Índice {coluna.split('::')[1]}"
        elif coluna.startswith("folga::"):
            novos[coluna] = f"Folga {coluna.split('::')[1]} (R$)"
        elif coluna.startswith("RWA"):
            novos[coluna] = f"{coluna} (R$)"
    return saida.rename(columns=novos)
