"""Relatório no console e exportação para Excel (identidade visual RF Analytics)."""
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

LARANJA = "F56600"
QUASE_PRETO = "111111"
CINZA_CLARO = "F2F2F2"
CINZA_BORDA = "D9D9D9"
FONTE = "Arial"

FORMATO_REAIS = '"R$" #,##0.00;[Red]-"R$" #,##0.00'
FORMATO_PCT = "0.00%"


def _brl(valor: float) -> str:
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _pct(valor: float) -> str:
    return f"{valor:.2%}".replace(".", ",")


def exibir_relatorio(carteira_com_rwa: pd.DataFrame, parcelas_rwa: dict, capital: dict,
                     avaliacao: pd.DataFrame, capacidade: float, aporte: float) -> None:
    linha = "=" * 78
    print(linha)
    print("CAPITALRISKBR — REQUERIMENTO DE CAPITAL (Res. CMN 4.958/2021)")
    print(linha)

    print("\nRWA por parcela:")
    for parcela, valor in parcelas_rwa.items():
        print(f"  {parcela:<8} {_brl(valor):>22}")

    print("\nComposição do PR:")
    print(f"  Ajustes prudenciais deduzidos {_brl(capital['ajustes_prudenciais']):>20}")
    print(f"  Capital Principal             {_brl(capital['capital_principal']):>20}")
    print(f"  Nível I                       {_brl(capital['nivel_1']):>20}")
    print(f"  Patrimônio de Referência      {_brl(capital['patrimonio_referencia']):>20}")

    print("\nÍndices x requerimentos (mínimo + ACP):")
    for _, r in avaliacao.iterrows():
        print(f"  {r['nivel']:<25} {_pct(r['indice']):>7} | mín {_pct(r['minimo'])} "
              f"+ ACP {_pct(r['acp'])} = {_pct(r['requerido']):>6} | folga {_brl(r['folga_total']):>18} "
              f"| {r['situacao']}")

    print()
    if capacidade >= 0:
        print(f"Capacidade de crescimento de RWA: {_brl(capacidade)}")
    else:
        print(f"RWA acima do suportado em: {_brl(-capacidade)}")
        print(f"Aporte de Capital Principal para enquadrar: {_brl(aporte)}")
    print(linha)


def exportar_excel(caminho: str | Path, carteira_com_rwa: pd.DataFrame, por_classe: pd.DataFrame,
                   parcelas_rwa: dict, capital: dict, avaliacao: pd.DataFrame,
                   capacidade: float, aporte: float) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    resumo = avaliacao.rename(columns={
        "nivel": "Nível", "capital": "Capital (R$)", "indice": "Índice",
        "minimo": "Mínimo", "acp": "ACP", "requerido": "Requerido",
        "capital_requerido": "Capital requerido (R$)", "folga_minimo": "Folga s/ mínimo (R$)",
        "folga_total": "Folga s/ requerido (R$)", "situacao": "Situação",
    })
    rwa = pd.DataFrame({"Parcela": list(parcelas_rwa), "Valor (R$)": list(parcelas_rwa.values())})
    composicao = pd.DataFrame({
        "Item": ["Ajustes prudenciais deduzidos", "Capital Principal", "Nível I",
                 "Patrimônio de Referência", "Capacidade de crescimento de RWA",
                 "Aporte de CP para enquadrar"],
        "Valor (R$)": [capital["ajustes_prudenciais"], capital["capital_principal"],
                       capital["nivel_1"], capital["patrimonio_referencia"], capacidade, aporte],
    })
    carteira = carteira_com_rwa[[
        "id_operacao", "contraparte", "produto", "classe_exposicao", "saldo_balanco",
        "saldo_off", "tipo_off", "fcc", "ead", "fpr", "rwa",
    ]]

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        rwa.to_excel(writer, sheet_name="RWA", index=False)
        composicao.to_excel(writer, sheet_name="Composição PR", index=False)
        carteira.to_excel(writer, sheet_name="Carteira", index=False)
        por_classe.to_excel(writer, sheet_name="RWA por classe", index=False)

    _formatar(caminho)
    return caminho


def _formatar(caminho: Path) -> None:
    wb = load_workbook(caminho)
    borda = Border(bottom=Side(style="thin", color=CINZA_BORDA))
    colunas_pct = {"Índice", "Mínimo", "ACP", "Requerido", "fcc", "fpr"}

    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
        cabecalhos = [c.value for c in ws[1]]
        for celula in ws[1]:
            celula.font = Font(name=FONTE, bold=True, color="FFFFFF")
            celula.fill = PatternFill("solid", fgColor=QUASE_PRETO)
            celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for linha in ws.iter_rows(min_row=2):
            for celula in linha:
                nome = cabecalhos[celula.column - 1]
                celula.font = Font(name=FONTE, color=QUASE_PRETO)
                celula.border = borda
                if isinstance(celula.value, (int, float)):
                    if nome in colunas_pct:
                        celula.number_format = FORMATO_PCT
                    elif nome not in {"id_operacao"}:
                        celula.number_format = FORMATO_REAIS
                if nome == "Situação":
                    cor = "1E7B34" if celula.value == "ADEQUADO" else LARANJA
                    celula.font = Font(name=FONTE, bold=True, color=cor)
            if linha[0].row % 2 == 0:
                for celula in linha:
                    celula.fill = PatternFill("solid", fgColor=CINZA_CLARO)

        for coluna in ws.columns:
            largura = max(len(str(c.value)) if c.value is not None else 0 for c in coluna)
            ws.column_dimensions[coluna[0].column_letter].width = min(max(12, largura + 4), 45)
        ws.freeze_panes = "A2"

    wb.save(caminho)
