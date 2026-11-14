"""Relatório (console e Excel) do cálculo de capital a partir de balancete Cosif."""
import re
import unicodedata
from pathlib import Path

import pandas as pd

from src.estresse import base_do_resultado, carregar_cenarios, executar, tabela_apresentacao, teste_reverso
from src.relatorio import _brl, _formatar, _pct

DESCRICAO_PARCELAS = {
    "RWACPAD": "Risco de crédito (por conta Cosif)",
    "RWAMPAD": "Risco de mercado (informado)",
    "RWAOPAD": "Risco operacional (BI do balancete)",
    "RWASP": "Serviços de pagamento",
    "RWA": "RWA total",
    "RWARCSimp": "Risco de crédito simplificado (Res. BCB 437)",
    "RWACAMSimp": "Exposição cambial simplificada",
    "RWAIP": "RWA de instituição de pagamento",
}


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def estresse(r: dict) -> dict:
    cenarios = carregar_cenarios()
    base = base_do_resultado(r)
    return {"base": base, "tabela": executar(base, cenarios), "reverso": teste_reverso(base, cenarios["premissas"]),
            "premissas": cenarios["premissas"]}


def exibir(r: dict) -> None:
    ident = r["identificacao"]
    linha = "=" * 86
    print(linha)
    print(f"{ident['instituicao']} — {ident['tipo_documento']} ({ident['documento']}) — "
          f"data-base {ident['data_base'][4:]}/{ident['data_base'][:4]}")
    regime = "Instituição de pagamento (Res. BCB 198)" if r["regime"] == "ip" else \
        f"Banco/conglomerado (Res. CMN 4.958) — segmento {r['instituicao']['segmento']}"
    print(f"Regime: {regime}")
    print(f"Fonte: {ident['fonte']}")
    print(linha)

    print("\nComposição do capital:")
    for item, valor in r["composicao"]:
        print(f"  {item:<48} {_brl(valor):>26}")

    print("\nAtivos ponderados pelo risco:")
    for parcela, valor in r["parcelas"].items():
        print(f"  {parcela:<11} {DESCRICAO_PARCELAS.get(parcela, ''):<45} {_brl(valor):>26}")

    if r["regime"] == "ip":
        print("\nServiços de pagamento (componentes):")
        for nome, valor in r["componentes_sp"].items():
            print(f"  {nome:<48} {_brl(valor):>26}")
        print(f"\nPRIP / RWAIP: {_pct(r['indice'])} | requerido F' {_pct(r['f_linha'])} = "
              f"{_brl(r['requerido'])} | folga {_brl(r['folga'])}")
        print(f"Capacidade de crescimento de RWAIP: {_brl(r['capacidade'])}")
    else:
        print("\nÍndices ESTIMADOS com dados públicos x requerimentos (mínimo + ACP):")
        print("  (estimativa metodológica — não representa a situação regulatória oficial)")
        for _, a in r["avaliacao"].iterrows():
            print(f"  {a['nivel']:<25} {_pct(a['indice']):>7} | requerido {_pct(a['requerido']):>6} "
                  f"| folga {_brl(a['folga_total']):>24} | {a['situacao']}")
        if r.get("comparacao") is not None and not r["comparacao"].empty:
            print("\nComparação com o índice divulgado pela instituição:")
            for _, c in r["comparacao"].iterrows():
                print(f"  {c['nivel']:<25} estimado {_pct(c['estimado']):>7} | divulgado {_pct(c['publicado']):>7} "
                      f"| diferença {c['diferenca_pp']:+.1f} p.p. | RWA implícito {_brl(c['rwa_implicito'])} "
                      f"| situação pelo divulgado: {c['situacao_divulgada']}")
            print(f"  RWA estimado: {_brl(r['parcelas']['RWA'])} — a diferença para o RWA implícito vem de "
                  "mitigadores, SA-CCR, FPR por contraparte e LTV, que o balancete não mostra.")

    e = estresse(r)
    principal = next(iter(e["base"]["niveis"]))
    calibrada = e["base"]["calibracao_rwa"] != 1.0
    print(f"\nCenários de estresse — {principal}"
          + (f" (base calibrada ao índice divulgado: RWA x{e['base']['calibracao_rwa']:.2f})" if calibrada else "") + ":")
    for _, c in e["tabela"].iterrows():
        print(f"  {c['cenario']:<40} {_pct(c[f'indice::{principal}']):>7} ({c['variacao_pp']:+.2f} p.p.) | {c['situacao']}")
    rv = e["reverso"]
    print(f"  Teste reverso: perda máxima absorvível {_brl(rv['perda_maxima_absorvivel'])} "
          f"(limitante: {rv['nivel_limitante']}) | RWA pode crescer {_pct(rv['crescimento_rwa_maximo_pct'])}")

    print("\nPremissas da estimativa:")
    for premissa in r["premissas"]:
        print(f"  • {premissa}")
    if not r["sem_mapeamento"].empty:
        print(f"\n  ⚠ {len(r['sem_mapeamento'])} conta(s) sem mapeamento tratadas a 100%: "
              f"{', '.join(r['sem_mapeamento']['conta'])}")
    print(linha)


def _tabela(itens, colunas) -> pd.DataFrame:
    return pd.DataFrame(itens, columns=colunas)


def exportar(r: dict, pasta: str | Path) -> Path:
    ident = r["identificacao"]
    caminho = Path(pasta) / f"capital_{_slug(ident['apelido'])}_{ident['documento']}_{ident['data_base']}.xlsx"
    caminho.parent.mkdir(parents=True, exist_ok=True)

    campos = {"apelido": "Instituição", "cnpj": "CNPJ", "tipo_documento": "Documento",
              "documento": "Modelo Cosif", "data_base": "Data-base", "taxonomia": "Taxonomia BCB",
              "fonte": "Fonte"}
    identificacao = _tabela([(rotulo, ident[chave]) for chave, rotulo in campos.items()]
                            + [("Regime", r["regime"]), ("Segmento", r["instituicao"].get("segmento", ""))],
                            ["Campo", "Valor"])
    composicao = _tabela(r["composicao"], ["Item", "Valor (R$)"])
    parcelas = _tabela([(k, DESCRICAO_PARCELAS.get(k, ""), v) for k, v in r["parcelas"].items()],
                       ["Parcela", "Descrição", "Valor (R$)"])
    exposicoes = r["exposicoes"][["conta", "nome_conta", "classe", "saldo", "fcc", "ead", "fpr", "rwa",
                                  "observacao"]].rename(columns={"saldo": "Saldo (R$)", "ead": "EAD (R$)",
                                                                 "rwa": "RWA (R$)"})
    por_classe = (r["exposicoes"].groupby("classe", as_index=False)[["ead", "rwa"]].sum()
                  .sort_values("rwa", ascending=False).rename(columns={"ead": "EAD (R$)", "rwa": "RWA (R$)"}))
    mapeamento = r["mapeamento"][["conta", "nome_conta", "saldo", "prefixo_regra", "destino", "classe",
                                  "observacao"]].rename(columns={"saldo": "Saldo (R$)"})
    premissas = _tabela([(p,) for p in r["premissas"]], ["Premissa"])
    conciliacao = r["conciliacao"].rename(columns={"saldo_grupo": "Saldo do grupo (R$)",
                                                   "soma_analiticas": "Soma das analíticas (R$)",
                                                   "diferenca": "Diferença (R$)"})

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        identificacao.to_excel(writer, sheet_name="Identificação", index=False)
        if r["regime"] == "ip":
            resumo = _tabela([
                ("PRIP", r["prip"], "R$"), ("RWAIP", r["parcelas"]["RWAIP"], "R$"),
                ("Índice PRIP / RWAIP", r["indice"], "%"), ("Fator F'", r["f_linha"], "%"),
                ("Requerimento mínimo", r["requerido"], "R$"), ("Folga", r["folga"], "R$"),
                ("Capacidade de crescimento de RWAIP", r["capacidade"], "R$"),
            ], ["Item", "Valor", "Unidade"])
            resumo.to_excel(writer, sheet_name="Resumo", index=False)
            _tabela(list(r["componentes_sp"].items()), ["Componente", "Valor (R$)"]).to_excel(
                writer, sheet_name="Serviços de Pagamento", index=False)
        else:
            r["avaliacao"].rename(columns={
                "nivel": "Nível", "capital": "Capital (R$)", "indice": "Índice", "minimo": "Mínimo",
                "acp": "ACP", "requerido": "Requerido", "capital_requerido": "Capital requerido (R$)",
                "folga_minimo": "Folga s/ mínimo (R$)", "folga_total": "Folga s/ requerido (R$)",
                "situacao": "Situação"}).to_excel(writer, sheet_name="Resumo", index=False)
            if r.get("comparacao") is not None and not r["comparacao"].empty:
                r["comparacao"].rename(columns={
                    "nivel": "Nível", "estimado": "Índice", "publicado": "ACP",
                    "requerido": "Requerido", "diferenca_pp": "Diferença (p.p.)",
                    "rwa_implicito": "RWA implícito (R$)", "situacao_divulgada": "Situação"}
                ).rename(columns={"ACP": "Mínimo"}).to_excel(writer, sheet_name="Comparação", index=False)
            bi = r["bi"]
            _tabela([
                ("Meses apurados no semestre", bi["meses_apurados"], "x"),
                ("Fator de anualização", bi["fator_anualizacao"], "x"),
                ("Ativos rentáveis (IEA)", bi["IEA"], "R$"),
                ("Margem de juros anualizada |II − IE|", bi["margem_juros_anual"], "R$"),
                ("Teto 2,25% x IEA", bi["teto_ildc"], "R$"),
                ("ILDC", bi["ILDC"], "R$"), ("SC", bi["SC"], "R$"), ("FC", bi["FC"], "R$"),
                ("BI", bi["BI"], "R$"), ("BIC", bi["BIC"], "R$"), ("RWAOPAD = BIC / F", bi["RWAOPAD"], "R$"),
            ], ["Item", "Valor", "Unidade"]).to_excel(writer, sheet_name="Risco Operacional", index=False)
            bi["detalhe"].rename(columns={"saldo": "Saldo (R$)"}).to_excel(
                writer, sheet_name="BI por conta", index=False)
        e = estresse(r)
        tabela_apresentacao(e["tabela"]).to_excel(writer, sheet_name="Estresse", index=False)
        rv = e["reverso"]
        _tabela([
            ("Base do estresse", "calibrada ao índice divulgado" if e["base"]["calibracao_rwa"] != 1.0
             else "estimativa do balancete", "x"),
            ("Fator de calibração do RWA", e["base"]["calibracao_rwa"], "x"),
            ("Nível limitante", rv["nivel_limitante"], "x"),
            ("Perda máxima absorvível", rv["perda_maxima_absorvivel"], "R$"),
            ("Perda de crédito equivalente (% da carteira)", rv["perda_credito_equivalente_pct"], "%"),
            ("Crescimento máximo de RWA", rv["crescimento_rwa_maximo"], "R$"),
            ("Crescimento máximo de RWA (%)", rv["crescimento_rwa_maximo_pct"], "%"),
            ("Exposição a valor justo (choque de juros)", e["base"]["exposicao_juros"], "R$"),
            ("EAD de crédito (inadimplência)", e["base"]["credito_ead"], "R$"),
            ("Duration da carteira (anos)", e["premissas"]["duration_carteira"], "x"),
        ], ["Item", "Valor", "Unidade"]).to_excel(writer, sheet_name="Teste Reverso", index=False)
        composicao.to_excel(writer, sheet_name="Composição do Capital", index=False)
        parcelas.to_excel(writer, sheet_name="RWA", index=False)
        por_classe.to_excel(writer, sheet_name="RWA por classe", index=False)
        exposicoes.to_excel(writer, sheet_name="Exposições", index=False)
        mapeamento.to_excel(writer, sheet_name="Mapeamento Cosif", index=False)
        conciliacao.to_excel(writer, sheet_name="Conciliação", index=False)
        premissas.to_excel(writer, sheet_name="Premissas", index=False)

    _formatar(caminho)
    return caminho
