"""Série histórica de capital a partir de vários balancetes Cosif da mesma instituição.

- Agrupa os arquivos por instituição (CNPJ) e modelo (4010 ou 4060).
- Usa os balancetes de junho e dezembro (resultado do semestre) para montar os períodos anuais
  do Indicador de Negócios (Res. BCB 356, arts. 2º e 6º) — média de até 3 anos.
- Calcula capital, RWA e índices em cada data-base e exporta Excel com gráficos.
"""
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.chart import BarChart, LineChart, Reference

from src.balancete_cosif import analiticas, identificacao, ler_balancete
from src.capital_balancete import analisar_balancete, detectar_regime, somas_bi
from src.relatorio import LARANJA, QUASE_PRETO, _brl, _formatar, _pct
from src.relatorio_balancete import _slug

CINZA_MEDIO = "7F7F7F"
CINZA_CLARO_GRAFICO = "BFBFBF"


def agrupar(pasta: str | Path) -> dict:
    grupos = {}
    for arquivo in sorted(Path(pasta).glob("*.[cC][sS][vV]")):
        ident = identificacao(ler_balancete(arquivo))
        grupos.setdefault((ident["cnpj"], ident["documento"]), []).append((ident["data_base"], arquivo))
    return {chave: sorted(itens) for chave, itens in grupos.items()}


def montar_historico(itens: list) -> dict:
    """Somas do BI dos balancetes semestrais (junho e dezembro)."""
    historico = {}
    for data_base, arquivo in itens:
        if data_base[4:6] in {"06", "12"}:
            historico[data_base] = somas_bi(analiticas(ler_balancete(arquivo)), data_base)
    return historico


def _linha_banco(r: dict) -> dict:
    av = r["avaliacao"].set_index("nivel")
    p = r["parcelas"]
    return {
        "data_base": r["identificacao"]["data_base"], "cosif": r["versao_cosif"],
        "capital_principal": r["capital"]["capital_principal"], "nivel_1": r["capital"]["nivel_1"],
        "patrimonio_referencia": r["capital"]["patrimonio_referencia"],
        "RWACPAD": p["RWACPAD"], "RWAMPAD": p["RWAMPAD"], "RWAOPAD": p["RWAOPAD"], "RWASP": p["RWASP"],
        "RWA": p["RWA"],
        "indice_cp": av.loc["Capital Principal", "indice"], "indice_n1": av.loc["Nível I", "indice"],
        "indice_pr": av.loc["Patrimônio de Referência", "indice"],
        "requerido_cp": av.loc["Capital Principal", "requerido"],
        "requerido_pr": av.loc["Patrimônio de Referência", "requerido"],
        "bi": r["bi"]["BI"], "metodo_bi": r["bi"]["metodo"],
    }


def _linha_ip(r: dict) -> dict:
    p = r["parcelas"]
    return {
        "data_base": r["identificacao"]["data_base"], "cosif": r["versao_cosif"], "prip": r["prip"],
        "RWASP": p["RWASP"], "RWARCSimp": p["RWARCSimp"], "RWACAMSimp": p["RWACAMSimp"], "RWAIP": p["RWAIP"],
        "indice_prip": r["indice"], "requerido": r["f_linha"], "folga": r["folga"],
    }


def analisar_serie(itens: list, parametros: dict) -> dict:
    historico = montar_historico(itens)
    resultados = [analisar_balancete(arquivo, parametros, historico) for _, arquivo in itens]
    regime = resultados[-1]["regime"]
    tabela = pd.DataFrame([(_linha_ip if regime == "ip" else _linha_banco)(r) for r in resultados])
    premissas = list(dict.fromkeys(p for r in resultados for p in r["premissas"]))
    bi_semestral = pd.DataFrame([
        {"data_base": db, "cosif": h["versao"], "receitas_juros": h["ii"], "despesas_juros": h["ie"],
         "dividendos": h["di"], "receitas_servicos": h["fi"], "despesas_servicos": h["fe"],
         "outras_receitas": h["ooi"], "outras_despesas": h["ooe"], "financeiro": h["fin"],
         "ativos_rentaveis": h["IEA"]}
        for db, h in sorted(historico.items())])
    return {"regime": regime, "tabela": tabela, "premissas": premissas, "bi_semestral": bi_semestral,
            "identificacao": resultados[-1]["identificacao"], "ultimo": resultados[-1]}


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------

def _rotulo(data_base: str) -> str:
    return f"{data_base[4:]}/{data_base[2:4]}"


def exibir_serie(serie: dict) -> None:
    ident, t = serie["identificacao"], serie["tabela"]
    linha = "=" * 100
    print(linha)
    print(f"SÉRIE HISTÓRICA — {ident['apelido']} — {ident['tipo_documento']} ({ident['documento']})")
    print(f"Fonte: {ident['fonte']}")
    print(linha)
    if serie["regime"] == "ip":
        print(f"{'Data-base':<10}{'PRIP':>22}{'RWAIP':>24}{'PRIP/RWAIP':>12}")
        for _, r in t.iterrows():
            print(f"{_rotulo(r['data_base']):<10}{_brl(r['prip']):>22}{_brl(r['RWAIP']):>24}{_pct(r['indice_prip']):>12}")
    else:
        print(f"{'Data-base':<10}{'Cosif':<8}{'Cap. Principal':>24}{'RWA':>26}{'CP':>8}{'N1':>8}{'PR':>8}  BI")
        for _, r in t.iterrows():
            print(f"{_rotulo(r['data_base']):<10}{r['cosif']:<8}{_brl(r['capital_principal']):>24}"
                  f"{_brl(r['RWA']):>26}{_pct(r['indice_cp']):>8}{_pct(r['indice_n1']):>8}"
                  f"{_pct(r['indice_pr']):>8}  {r['metodo_bi'][:38]}")
        if (t["cosif"] == "legado").any() and (t["cosif"] == "atual").any():
            print("\n⚠ Quebra de série em 01/2025: mudança do plano de contas Cosif (Res. CMN 4.966).")
    print("\nPremissas:")
    for p in serie["premissas"]:
        print(f"  • {p}")
    print(linha)


def _grafico_linhas(ws, titulo, colunas, n, cores, eixo="Índice"):
    grafico = LineChart()
    grafico.title, grafico.y_axis.title, grafico.height, grafico.width = titulo, eixo, 8, 18
    grafico.y_axis.number_format = "0.0%"
    for coluna, cor in zip(colunas, cores):
        dados = Reference(ws, min_col=coluna, min_row=1, max_row=n + 1)
        grafico.add_data(dados, titles_from_data=True)
        serie = grafico.series[-1]
        serie.graphicalProperties.line.solidFill = cor
        serie.graphicalProperties.line.width = 28000
        serie.smooth = False
    grafico.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n + 1))
    return grafico


def _grafico_barras(ws, titulo, colunas, n, cores):
    grafico = BarChart()
    grafico.type, grafico.grouping, grafico.overlap = "col", "stacked", 100
    grafico.title, grafico.height, grafico.width = titulo, 8, 18
    grafico.y_axis.number_format = '#,##0,,," bi"'
    for coluna, cor in zip(colunas, cores):
        grafico.add_data(Reference(ws, min_col=coluna, min_row=1, max_row=n + 1), titles_from_data=True)
        grafico.series[-1].graphicalProperties.solidFill = cor
        grafico.series[-1].graphicalProperties.line.solidFill = cor
    grafico.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n + 1))
    return grafico


def exportar_serie(serie: dict, pasta: str | Path) -> Path:
    ident = serie["identificacao"]
    caminho = Path(pasta) / f"serie_{_slug(ident['apelido'])}_{ident['documento']}.xlsx"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    t = serie["tabela"].copy()
    t.insert(0, "Data-base", t.pop("data_base").map(_rotulo))

    if serie["regime"] == "ip":
        grafico_df = t[["Data-base", "indice_prip", "requerido"]].rename(
            columns={"indice_prip": "Índice", "requerido": "Requerido"})
        rwa_df = t[["Data-base", "RWASP", "RWARCSimp", "RWACAMSimp"]].rename(
            columns={"RWASP": "RWASP (R$)", "RWARCSimp": "RWARCSimp (R$)", "RWACAMSimp": "RWACAMSimp (R$)"})
    else:
        grafico_df = t[["Data-base", "indice_cp", "indice_n1", "indice_pr", "requerido_pr"]].rename(columns={
            "indice_cp": "Índice", "indice_n1": "Mínimo", "indice_pr": "ACP", "requerido_pr": "Requerido"})
        grafico_df.columns = ["Data-base", "Índice", "Mínimo", "ACP", "Requerido"]  # formatos de %
        rwa_df = t[["Data-base", "RWACPAD", "RWAOPAD", "RWAMPAD", "RWASP"]].rename(columns={
            "RWACPAD": "Crédito (R$)", "RWAOPAD": "Operacional (R$)", "RWAMPAD": "Mercado (R$)",
            "RWASP": "Serviços de pagamento (R$)"})

    renomear = {
        "cosif": "Plano Cosif", "capital_principal": "Capital Principal (R$)", "nivel_1": "Nível I (R$)",
        "patrimonio_referencia": "PR (R$)", "RWACPAD": "RWACPAD (R$)", "RWAMPAD": "RWAMPAD (R$)",
        "RWAOPAD": "RWAOPAD (R$)", "RWASP": "RWASP (R$)", "RWA": "RWA (R$)", "indice_cp": "Índice",
        "indice_n1": "Mínimo", "indice_pr": "ACP", "requerido_cp": "Requerido", "requerido_pr": "fpr",
        "bi": "BI (R$)", "metodo_bi": "Método do BI", "prip": "PRIP (R$)", "RWARCSimp": "RWARCSimp (R$)",
        "RWACAMSimp": "RWACAMSimp (R$)", "RWAIP": "RWAIP (R$)", "indice_prip": "Índice", "requerido": "Requerido",
        "folga": "Folga (R$)",
    }
    tabela = t.rename(columns=renomear)
    bi = serie["bi_semestral"].copy()
    if not bi.empty:
        bi.insert(0, "Data-base", bi.pop("data_base").map(_rotulo))
        bi = bi.rename(columns={c: f"{c.replace('_', ' ').capitalize()} (R$)" for c in bi.columns
                                if c not in {"Data-base", "cosif"}}).rename(columns={"cosif": "Plano Cosif"})

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        tabela.to_excel(writer, sheet_name="Série", index=False)
        grafico_df.to_excel(writer, sheet_name="Gráfico Índices", index=False)
        rwa_df.to_excel(writer, sheet_name="Gráfico RWA", index=False)
        if not bi.empty:
            bi.to_excel(writer, sheet_name="BI Semestral", index=False)
        pd.DataFrame({"Premissa": serie["premissas"] + [f"Fonte: {ident['fonte']}"]}).to_excel(
            writer, sheet_name="Premissas", index=False)

    _formatar(caminho)

    wb = load_workbook(caminho)
    n = len(t)
    ws = wb["Gráfico Índices"]
    if serie["regime"] == "ip":
        ws["B1"], ws["C1"] = "PRIP / RWAIP", "Requerido (F' 12%)"
        g = _grafico_linhas(ws, "Índice PRIP / RWAIP", [2, 3], n, [LARANJA, QUASE_PRETO])
    else:
        ws["B1"], ws["C1"], ws["D1"], ws["E1"] = ("Capital Principal", "Nível I", "PR (Basileia)",
                                                  "PR requerido (mín. + ACP)")
        g = _grafico_linhas(ws, "Índices de capital estimados", [2, 3, 4, 5], n,
                            [LARANJA, CINZA_MEDIO, QUASE_PRETO, CINZA_CLARO_GRAFICO])
    ws.add_chart(g, "H2")
    ws_rwa = wb["Gráfico RWA"]
    cores = [QUASE_PRETO, LARANJA, CINZA_MEDIO, CINZA_CLARO_GRAFICO]
    ws_rwa.add_chart(_grafico_barras(ws_rwa, "Composição do RWA", list(range(2, len(rwa_df.columns) + 1)), n,
                                     cores), "H2")
    # cabeçalhos auxiliares renomeados para manter o formato de % na Série
    ws_serie = wb["Série"]
    for celula in ws_serie[1]:
        celula.value = {"Índice": "Índice CP" if serie["regime"] == "banco" else "PRIP / RWAIP",
                        "Mínimo": "Índice N1", "ACP": "Índice PR",
                        "Requerido": "CP requerido" if serie["regime"] == "banco" else "Requerido",
                        "fpr": "PR requerido"}.get(celula.value, celula.value)
    wb.save(caminho)
    return caminho
