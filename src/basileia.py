"""Requerimentos mínimos de capital e ACP (Res. CMN 4.958/2021).

RWA = RWACPAD + RWAMPAD + RWAOPAD + RWASP
Requerido (com ACP) = mínimo do nível + ACP total
  -> Capital Principal 4,5% + ACP | Nível I 6% + ACP | PR 8% + ACP
"""
import pandas as pd

PARCELAS_RWA = ("RWACPAD", "RWAMPAD", "RWAOPAD", "RWASP")

NIVEIS = (
    ("Capital Principal", "capital_principal"),
    ("Nível I", "nivel_1"),
    ("Patrimônio de Referência", "patrimonio_referencia"),
)

SITUACAO_OK = "ADEQUADO"
SITUACAO_ACP = "ABAIXO DO ACP"          # cumpre o mínimo, mas não o adicional
SITUACAO_MINIMO = "ABAIXO DO MÍNIMO"    # descumpre o requerimento mínimo


def carregar_outras_parcelas(caminho_arquivo: str) -> dict:
    tabela = pd.read_csv(caminho_arquivo, encoding="utf-8")
    parcelas = dict(zip(tabela["parcela"], tabela["valor"].astype(float)))

    desconhecidas = set(parcelas) - set(PARCELAS_RWA)
    if desconhecidas:
        raise ValueError(f"Parcela de RWA desconhecida: {sorted(desconhecidas)}")
    if any(valor < 0 for valor in parcelas.values()):
        raise ValueError("Parcelas de RWA não podem ser negativas.")
    return parcelas


def consolidar_rwa(rwa_credito: float, outras_parcelas: dict | None = None) -> dict:
    outras_parcelas = outras_parcelas or {}
    parcelas = {
        "RWACPAD": rwa_credito,
        "RWAMPAD": outras_parcelas.get("RWAMPAD", 0.0),
        "RWAOPAD": outras_parcelas.get("RWAOPAD", 0.0),
        "RWASP": outras_parcelas.get("RWASP", 0.0),
    }
    parcelas["RWA"] = sum(parcelas.values())
    if parcelas["RWA"] <= 0:
        raise ValueError("O RWA total deve ser maior que zero.")
    return parcelas


def acp_total(parametros: dict) -> float:
    return float(sum(parametros["adicional_capital_principal"].values()))


def avaliar_requerimentos(capital: dict, rwa: float, parametros: dict) -> pd.DataFrame:
    if rwa <= 0:
        raise ValueError("O RWA deve ser maior que zero.")

    acp = acp_total(parametros)
    minimos = parametros["requerimentos_minimos"]
    linhas = []

    for nome, chave in NIVEIS:
        valor_capital = capital[chave]
        minimo = minimos[chave]
        requerido = minimo + acp
        folga_minimo = valor_capital - minimo * rwa
        folga_total = valor_capital - requerido * rwa

        if folga_total >= 0:
            situacao = SITUACAO_OK
        elif folga_minimo >= 0:
            situacao = SITUACAO_ACP
        else:
            situacao = SITUACAO_MINIMO

        linhas.append({
            "nivel": nome,
            "capital": valor_capital,
            "indice": valor_capital / rwa,
            "minimo": minimo,
            "acp": acp,
            "requerido": requerido,
            "capital_requerido": requerido * rwa,
            "folga_minimo": folga_minimo,
            "folga_total": folga_total,
            "situacao": situacao,
        })

    return pd.DataFrame(linhas)


def capacidade_crescimento_rwa(avaliacao: pd.DataFrame) -> float:
    """Quanto RWA adicional cabe no capital atual, respeitando mínimo + ACP em todos os níveis.

    Valor negativo indica quanto RWA precisaria ser reduzido para enquadrar.
    """
    return float((avaliacao["folga_total"] / avaliacao["requerido"]).min())


def capital_necessario(avaliacao: pd.DataFrame) -> float:
    """Aporte de Capital Principal que enquadra todos os níveis (CP conta em N1 e PR)."""
    return float(max(0.0, -avaliacao["folga_total"].min()))
