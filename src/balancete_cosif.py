"""Leitura de balancetes Cosif publicados pelo Banco Central (documentos 4010, 4016, 4060 etc.).

Layout do arquivo do BCB (Dados Abertos / IF.data):
  3 linhas de cabeçalho livre, depois
  #DATA_BASE;DOCUMENTO;CNPJ;AGENCIA;NOME_INSTITUICAO;COD_CONGL;NOME_CONGL;TAXONOMIA;CONTA;NOME_CONTA;SALDO;...
  Separador ';', decimal ',', codificação Latin-1.

O balancete traz contas sintéticas e analíticas misturadas (10000000, 11000000, 11200000,
11230000...). Para não somar duas vezes, os cálculos usam só as contas ANALÍTICAS (folhas),
identificadas pelo nível Cosif: grupo (1 dígito), subgrupo (2), desdobramento (3),
título (5) e subtítulo (7).
"""
import re
from pathlib import Path

import pandas as pd

NIVEIS_COSIF = (1, 2, 3, 5, 7)

DOCUMENTOS = {
    "4010": "Balancete individual",
    "4016": "Balancete individual (semestral)",
    "4060": "Balancete do conglomerado prudencial",
    "4066": "Balancete do conglomerado prudencial (semestral)",
}


def prefixo_cosif(conta: str) -> str:
    """Código significativo da conta, respeitando os níveis Cosif.

    11200000 -> '112' ; 11230000 -> '11230' ; 30970000 -> '30970' ; 10000000 -> '1'
    """
    conta = str(conta).strip().zfill(8)
    for tamanho in NIVEIS_COSIF:
        if set(conta[tamanho:7]) <= {"0"}:
            return conta[:tamanho]
    return conta[:7]


def ler_balancete(caminho: str | Path) -> pd.DataFrame:
    caminho = Path(caminho)
    with open(caminho, encoding="latin-1") as arquivo:
        linhas = arquivo.read().replace("\xa0", " ").splitlines()

    inicio = next((i for i, l in enumerate(linhas) if l.startswith("#DATA_BASE")), None)
    if inicio is None:
        raise ValueError(f"{caminho.name}: cabeçalho '#DATA_BASE' não encontrado. É um balancete do BCB?")

    cabecalho = linhas[inicio].lstrip("#").split(";")
    registros = [l.split(";") for l in linhas[inicio + 1:] if l.strip()]
    df = pd.DataFrame([r[:len(cabecalho)] for r in registros], columns=cabecalho)

    df["CONTA"] = df["CONTA"].str.strip().str.zfill(8)
    df["SALDO"] = (df["SALDO"].str.strip().replace("", "0")
                   .str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float))
    df = df.rename(columns={
        "DATA_BASE": "data_base", "DOCUMENTO": "documento", "CNPJ": "cnpj",
        "NOME_INSTITUICAO": "instituicao", "NOME_CONGL": "conglomerado",
        "TAXONOMIA": "taxonomia", "CONTA": "conta", "NOME_CONTA": "nome_conta", "SALDO": "saldo",
    })
    df["nome_conta"] = df["nome_conta"].map(lambda t: re.sub(r"[\x00-\x1f\x7f]", " ", t)).str.strip()
    # Alguns arquivos publicados repetem todas as linhas: descarta duplicatas idênticas
    df = df.drop_duplicates().reset_index(drop=True)
    divergentes = df[df["conta"].duplicated(keep=False)]
    if not divergentes.empty:
        raise ValueError(f"{caminho.name}: contas repetidas com saldos diferentes "
                         f"({', '.join(sorted(set(divergentes['CONTA'] if 'CONTA' in divergentes else divergentes['conta'])))[:200]})")

    df["prefixo"] = df["conta"].map(prefixo_cosif)
    df["grupo"] = df["conta"].str[0]

    prefixos = set(df["prefixo"])
    df["analitica"] = [not any(p != q and q.startswith(p) for q in prefixos) for p in df["prefixo"]]
    return df[["data_base", "documento", "cnpj", "instituicao", "conglomerado", "taxonomia",
               "conta", "prefixo", "grupo", "nome_conta", "saldo", "analitica"]]


def identificacao(balancete: pd.DataFrame) -> dict:
    linha = balancete.iloc[0]
    return {
        "data_base": str(linha["data_base"]),
        "documento": str(linha["documento"]),
        "tipo_documento": DOCUMENTOS.get(str(linha["documento"]), "Balancete"),
        "cnpj": str(linha["cnpj"]),
        "instituicao": str(linha["instituicao"] or linha["conglomerado"]).strip(),
        "conglomerado": str(linha["conglomerado"]).strip(),
        "taxonomia": str(linha["taxonomia"]).strip(),
    }


def conciliar(balancete: pd.DataFrame) -> pd.DataFrame:
    """Confere se a soma das analíticas bate com o saldo de cada grupo (1 dígito)."""
    sinteticos = balancete[balancete["prefixo"].str.len() == 1].set_index("grupo")["saldo"]
    analiticas = balancete[balancete["analitica"]].groupby("grupo")["saldo"].sum()
    resultado = pd.DataFrame({"saldo_grupo": sinteticos, "soma_analiticas": analiticas}).fillna(0.0)
    resultado["diferenca"] = (resultado["saldo_grupo"] - resultado["soma_analiticas"]).round(2)
    return resultado.reset_index().rename(columns={"index": "grupo"})


def analiticas(balancete: pd.DataFrame) -> pd.DataFrame:
    return balancete[balancete["analitica"]].copy()
