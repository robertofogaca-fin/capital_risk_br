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


def _memoria_operacional(op: dict) -> pd.DataFrame:
    linhas = [
        ("Margem de juros média |II - IE|", op["margem_juros_media"], "R$"),
        ("Teto: 2,25% x ativos rentáveis médios", op["teto_ildc"], "R$"),
        ("ILDC — juros, arrendamento e participações", op["ILDC"], "R$"),
        ("SC — serviços", op["SC"], "R$"),
        ("FC — financeiro", op["FC"], "R$"),
        ("BI — Indicador de Negócios", op["BI"], "R$"),
        ("BIC — Indicador de Negócios Ponderado", op["BIC"], "R$"),
        ("LC — componente de perdas (média 10 anos x 6)", op["LC"], "R$"),
        ("ILM calculado ln(e - 1 + (LC/BIC)^0,8)", op["ILM_calculado"], "x"),
        (f"ILM aplicado (segmento {op['segmento']})", op["ILM_aplicado"], "x"),
        ("Fator F", op["F"], "%"),
        ("RWAOPAD integral = BIC x ILM / F", op["RWAOPAD_integral"], "R$"),
        (f"RWAOPAD apurado ({op['regra_transicao']})", op["RWAOPAD"], "R$"),
        ("Referência: RWAOPAD se o ILM calculado fosse aplicado", op["RWAOPAD_se_ILM_calculado"], "R$"),
    ]
    return pd.DataFrame(linhas, columns=["Item", "Valor", "Unidade"])


def _memoria_pagamentos(sp: dict) -> pd.DataFrame:
    if not sp["aplicavel"]:
        return pd.DataFrame([("Instituição não sujeita ao RWASP", 0.0, "R$")],
                            columns=["Item", "Valor", "Unidade"])
    linhas = [
        ("Média mensal de pagamentos e transferências", sp["media_pagamentos_transferencias"], "R$"),
        ("Média mensal do saldo de moeda eletrônica", sp["media_saldo_moeda_eletronica"], "R$"),
        ("Média mensal de transações credenciadas", sp["media_transacoes_credenciadas"], "R$"),
        ("Média mensal de transações iniciadas", sp["media_transacoes_iniciadas"], "R$"),
        ("MOE — pagamentos e transferências (0,2%)", sp["MOE_pagamentos"], "R$"),
        ("MOE — moeda eletrônica (1%)", sp["MOE_saldo"], "R$"),
        ("ADQ — credenciamento (2%)", sp["ADQ"], "R$"),
        ("PISP — iniciação de pagamento (1,5%)", sp["PISP"], "R$"),
        ("MOE + ADQ + PISP", sp["total_componentes"], "R$"),
        ("RWASP = (MOE + ADQ + PISP) / F", sp["RWASP"], "R$"),
    ]
    return pd.DataFrame(linhas, columns=["Item", "Valor", "Unidade"])


def _imprimir_memoria(titulo: str, memoria: pd.DataFrame) -> None:
    print(f"\n{titulo}")
    for _, r in memoria.iterrows():
        if r["Unidade"] == "R$":
            valor = _brl(r["Valor"])
        elif r["Unidade"] == "%":
            valor = _pct(r["Valor"])
        else:
            valor = f"{r['Valor']:.4f}".replace(".", ",")
        print(f"  {r['Item']:<58} {valor:>20}")


def exibir_relatorio(carteira_com_rwa: pd.DataFrame, parcelas_rwa: dict, capital: dict,
                     avaliacao: pd.DataFrame, capacidade: float, aporte: float,
                     operacional: dict | None = None, pagamentos: dict | None = None) -> None:
    linha = "=" * 82
    print(linha)
    print("CAPITALRISKBR — REQUERIMENTO DE CAPITAL (Res. CMN 4.958/2021)")
    print(linha)

    if operacional:
        _imprimir_memoria("Risco operacional — RWAOPAD (Res. BCB 356/2023):", _memoria_operacional(operacional))
    if pagamentos:
        _imprimir_memoria("Serviços de pagamento — RWASP (Res. BCB 202/2022):", _memoria_pagamentos(pagamentos))

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
                   capacidade: float, aporte: float, operacional: dict | None = None,
                   pagamentos: dict | None = None, dre: pd.DataFrame | None = None,
                   servicos: pd.DataFrame | None = None) -> Path:
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
        if operacional:
            _memoria_operacional(operacional).to_excel(writer, sheet_name="Risco Operacional", index=False)
            if dre is not None:
                dre.to_excel(writer, sheet_name="DRE Operacional", index=False)
            perdas = operacional["perdas"].rename(columns={
                "na_janela": "Na janela de 10 anos", "acima_limiar": "Acima de R$ 500 mil",
                "considerada": "Considerada no LC"})
            perdas.to_excel(writer, sheet_name="Perdas Operacionais", index=False)
        if pagamentos:
            _memoria_pagamentos(pagamentos).to_excel(writer, sheet_name="Serviços de Pagamento", index=False)
            if servicos is not None:
                servicos.to_excel(writer, sheet_name="Volumes Pagamento", index=False)

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

        idx_unidade = cabecalhos.index("Unidade") if "Unidade" in cabecalhos else None
        for linha in ws.iter_rows(min_row=2):
            unidade = linha[idx_unidade].value if idx_unidade is not None else None
            for celula in linha:
                nome = cabecalhos[celula.column - 1]
                celula.font = Font(name=FONTE, color=QUASE_PRETO)
                celula.border = borda
                if isinstance(celula.value, bool):
                    celula.value = "Sim" if celula.value else "Não"
                    continue
                if isinstance(celula.value, (int, float)):
                    if unidade == "x" and nome == "Valor":
                        celula.number_format = "0.0000"
                    elif unidade == "%" and nome == "Valor":
                        celula.number_format = FORMATO_PCT
                    elif nome in {"ano"}:
                        celula.number_format = "0"
                    elif nome in colunas_pct:
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
