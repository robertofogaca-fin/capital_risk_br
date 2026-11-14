"""Leitura e validação dos parâmetros regulatórios (config/parametros.toml).

Usa tomllib, da biblioteca padrão (Python 3.11+): nenhuma dependência externa.
"""
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

CAMINHO_PADRAO = Path(__file__).resolve().parent.parent / "config" / "parametros.toml"


def carregar_parametros(caminho: str | Path = CAMINHO_PADRAO) -> dict:
    with open(caminho, "rb") as arquivo:
        parametros = tomllib.load(arquivo)

    for chave in ("requerimentos_minimos", "adicional_capital_principal",
                  "fpr_por_classe", "fcc_por_tipo"):
        if chave not in parametros:
            raise ValueError(f"Seção ausente em parametros.toml: {chave}")

    for classe, fpr in parametros["fpr_por_classe"].items():
        if fpr < 0:
            raise ValueError(f"FPR negativo para a classe {classe}.")

    for tipo, fcc in parametros["fcc_por_tipo"].items():
        if not 0 <= fcc <= 1:
            raise ValueError(f"FCC fora do intervalo [0, 1] para o tipo {tipo}.")

    return parametros
