"""CapitalRiskBR — dashboard (Fase 4).

Uso:  streamlit run app.py
Lê balancetes Cosif da pasta data/balancetes/ ou enviados pela tela e mostra capital, RWA,
série histórica, cenários de estresse e premissas — no padrão visual RF Analytics.
"""
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src.capital_balancete import analisar_balancete
from src.config import carregar_parametros
from src.estresse import base_do_resultado, carregar_cenarios, executar, tabela_apresentacao, teste_reverso
from src.relatorio_balancete import DESCRICAO_PARCELAS, exportar
from src.serie_historica import agrupar, analisar_serie

RAIZ = Path(__file__).resolve().parent
PASTA_BALANCETES = RAIZ / "data" / "balancetes"
LARANJA, PRETO, CINZA, CINZA_CLARO = "#F56600", "#111111", "#7F7F7F", "#BFBFBF"
PALETA = [PRETO, LARANJA, CINZA, CINZA_CLARO]

st.set_page_config(page_title="CapitalRiskBR", page_icon="📊", layout="wide")
st.markdown(f"""<style>
  html, body, [class*="css"] {{ font-family: Arial, Helvetica, sans-serif; }}
  h1, h2, h3 {{ color: {PRETO}; }}
  [data-testid="stMetricValue"] {{ color: {PRETO}; }}
  .faixa {{ border-left: 6px solid {LARANJA}; padding: .4rem .8rem; background: #F2F2F2; margin-bottom: 1rem; }}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def brl(valor: float) -> str:
    sinal = "-" if valor < 0 else ""
    valor = abs(valor)
    for limite, sufixo in ((1e9, "bi"), (1e6, "mi"), (1e3, "mil")):
        if valor >= limite:
            return f"{sinal}R$ {valor / limite:,.1f} {sufixo}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(valor: float) -> str:
    return f"{valor:.2%}".replace(".", ",")


def rotulo_data(data_base: str) -> str:
    return f"{data_base[4:]}/{data_base[:4]}"


@st.cache_data(show_spinner=False)
def catalogo(pasta: str, assinatura: tuple) -> list[dict]:
    parametros = carregar_parametros()
    itens = []
    for (cnpj, doc), arquivos in agrupar(pasta).items():
        for data_base, caminho in arquivos:
            ident = analisar_balancete(caminho, parametros)["identificacao"]
            itens.append({"chave": (cnpj, doc), "data_base": data_base, "caminho": str(caminho),
                          "rotulo": f"{ident['apelido']} — {ident['tipo_documento']} — {rotulo_data(data_base)}"})
    return sorted(itens, key=lambda i: (i["rotulo"].split(" — ")[0], i["chave"][1], i["data_base"]), reverse=True)


@st.cache_data(show_spinner="Calculando capital…")
def analisar(caminho: str, assinatura: float, historico_de: tuple | None = None):
    parametros = carregar_parametros()
    historico = None
    if historico_de:
        from src.serie_historica import montar_historico
        historico = montar_historico([(db, Path(c)) for db, c in historico_de])
    return analisar_balancete(caminho, parametros, historico)


@st.cache_data(show_spinner="Montando a série histórica…")
def serie(itens: tuple):
    return analisar_serie([(db, Path(c)) for db, c in itens], carregar_parametros())


def eixo_reais(maximo: float) -> alt.Axis:
    divisor, sufixo = (1e9, "bi") if maximo >= 1e9 else (1e6, "mi") if maximo >= 1e6 else (1, "")
    return alt.Axis(labelExpr=f"'R$ ' + replace(format(datum.value / {divisor}, ',.0f'), ',', '.') + ' {sufixo}'",
                    labelLimit=200)


def grafico_barras(df, x, y, cor=None, titulo="", horizontal=False, ordem_cor=None):
    base = alt.Chart(df).properties(title=titulo, height=320)
    maximo = float(df.groupby(x)[y].sum().max()) if not df.empty else 0.0
    if horizontal:
        enc = base.mark_bar(color=LARANJA).encode(
            y=alt.Y(f"{x}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X(f"{y}:Q", title=None, axis=eixo_reais(maximo)),
            tooltip=[x, alt.Tooltip(y, format=",.0f")])
    else:
        escala = alt.Scale(domain=ordem_cor, range=PALETA) if ordem_cor else alt.Scale(range=PALETA)
        enc = base.mark_bar().encode(
            x=alt.X(f"{x}:N", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{y}:Q", title=None, axis=eixo_reais(maximo)),
            color=(alt.Color(f"{cor}:N", scale=escala, sort=ordem_cor, legend=alt.Legend(orient="bottom"))
                   if cor else alt.value(PRETO)),
            order=(alt.Order("ordem:Q") if cor and ordem_cor else alt.Undefined),
            tooltip=[x, alt.Tooltip(y, format=",.0f")] + ([cor] if cor else []))
    return enc.configure_axis(labelFont="Arial", titleFont="Arial").configure_title(font="Arial", anchor="start")


# ---------------------------------------------------------------------------
# Seleção do balancete
# ---------------------------------------------------------------------------

st.sidebar.title("CapitalRiskBR")
st.sidebar.caption("Requerimento de capital a partir de balancetes Cosif públicos do BCB")

arquivos = sorted(PASTA_BALANCETES.glob("*.[cC][sS][vV]")) if PASTA_BALANCETES.exists() else []
assinatura = tuple((a.name, a.stat().st_mtime) for a in arquivos)
opcoes = catalogo(str(PASTA_BALANCETES), assinatura) if arquivos else []

origem = st.sidebar.radio("Origem do balancete", ["Pasta data/balancetes", "Enviar arquivo CSV"],
                          index=0 if opcoes else 1)
selecionado, historico_de, itens_serie = None, None, ()
if origem == "Pasta data/balancetes" and opcoes:
    escolha = st.sidebar.selectbox("Instituição e data-base", [o["rotulo"] for o in opcoes])
    atual = next(o for o in opcoes if o["rotulo"] == escolha)
    selecionado = atual["caminho"]
    mesma = [(o["data_base"], o["caminho"]) for o in opcoes if o["chave"] == atual["chave"]]
    itens_serie = tuple(sorted(mesma))
    historico_de = tuple(i for i in itens_serie if i[0][4:6] in {"06", "12"})
else:
    enviado = st.sidebar.file_uploader("Balancete CSV (modelo 4010 ou 4060)", type=["csv"])
    if enviado:
        temporario = Path(tempfile.gettempdir()) / f"capitalriskbr_{enviado.name}"
        temporario.write_bytes(enviado.getvalue())
        selecionado = str(temporario)

st.sidebar.markdown("---")
st.sidebar.caption("Fonte: Balancete Cosif (modelos 4010 e 4060) — dados públicos do Banco Central do Brasil. "
                   "Estimativa educacional: não representa a situação regulatória oficial.")

if not selecionado:
    st.title("CapitalRiskBR")
    st.info("Coloque balancetes CSV do BCB em `data/balancetes/` ou envie um arquivo pela barra lateral.")
    st.stop()

try:
    r = analisar(selecionado, Path(selecionado).stat().st_mtime, historico_de)
except Exception as erro:  # noqa: BLE001
    st.error(f"Não foi possível ler o balancete: {erro}")
    st.stop()

ident = r["identificacao"]
ip = r["regime"] == "ip"

st.title(ident["apelido"])
st.markdown(
    f"<div class='faixa'><b>{ident['tipo_documento']} ({ident['documento']})</b> · data-base "
    f"<b>{rotulo_data(ident['data_base'])}</b> · "
    f"{'Instituição de pagamento — Res. BCB 198' if ip else 'Banco/conglomerado — Res. CMN 4.958 · segmento ' + r['instituicao']['segmento']}"
    f" · plano Cosif {'anterior a 2025' if r['versao_cosif'] == 'legado' else 'atual'}</div>",
    unsafe_allow_html=True)

abas = st.tabs(["Visão geral", "Capital e RWA", "Série histórica", "Estresse", "Mapeamento e premissas"])

# ---------------------------------------------------------------------------
# Visão geral
# ---------------------------------------------------------------------------
with abas[0]:
    if ip:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PRIP / RWAIP", pct(r["indice"]), f"{(r['indice'] - r['f_linha']) * 100:+.1f} p.p. sobre F' 12%")
        c2.metric("PRIP", brl(r["prip"]))
        c3.metric("RWAIP", brl(r["parcelas"]["RWAIP"]))
        c4.metric("Folga de capital", brl(r["folga"]))
    else:
        av = r["avaliacao"].set_index("nivel")
        colunas = st.columns(4)
        for coluna, nivel in zip(colunas, ["Capital Principal", "Nível I", "Patrimônio de Referência"]):
            coluna.metric(f"Índice {nivel} (estimado)", pct(av.loc[nivel, "indice"]),
                          f"{(av.loc[nivel, 'indice'] - av.loc[nivel, 'requerido']) * 100:+.1f} p.p. vs requerido "
                          f"{pct(av.loc[nivel, 'requerido'])}")
        colunas[3].metric("RWA estimado", brl(r["parcelas"]["RWA"]))
        if r.get("comparacao") is not None and not r["comparacao"].empty:
            st.subheader("Estimado x divulgado")
            comp = r["comparacao"].copy()
            st.dataframe(pd.DataFrame({
                "Nível": comp["nivel"], "Estimado": comp["estimado"].map(pct),
                "Divulgado": comp["publicado"].map(pct), "Diferença (p.p.)": comp["diferenca_pp"].round(1),
                "RWA implícito": comp["rwa_implicito"].map(brl),
                "Situação pelo divulgado": comp["situacao_divulgada"]}), hide_index=True, width="stretch")
            st.caption(f"RWA estimado: {brl(r['parcelas']['RWA'])}. A diferença para o RWA implícito vem de "
                       "mitigadores, SA-CCR, FPR por contraparte e LTV, que o balancete não mostra.")
        else:
            st.caption("Índices estimados com dados públicos — exercício metodológico.")

    parcelas = pd.DataFrame([{"Parcela": k, "Descrição": DESCRICAO_PARCELAS.get(k, ""), "Valor": v}
                             for k, v in r["parcelas"].items() if k not in {"RWA", "RWAIP"}])
    st.altair_chart(grafico_barras(parcelas, "Parcela", "Valor", titulo="Composição do RWA"),
                    width="stretch")

# ---------------------------------------------------------------------------
# Capital e RWA
# ---------------------------------------------------------------------------
with abas[1]:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Composição do capital")
        st.dataframe(pd.DataFrame([{"Item": i, "Valor": brl(v)} for i, v in r["composicao"]]),
                     hide_index=True, width="stretch")
    with col2:
        st.subheader("RWA de crédito por classe")
        por_classe = (r["exposicoes"].groupby("classe", as_index=False)["rwa"].sum()
                      .query("rwa != 0").sort_values("rwa", ascending=False))
        st.altair_chart(grafico_barras(por_classe, "classe", "rwa", horizontal=True), width="stretch")
    if not ip:
        bi = r["bi"]
        st.subheader("Risco operacional — Indicador de Negócios")
        st.caption(f"Método: {bi['metodo']}")
        cols = st.columns(5)
        for coluna, (nome, chave) in zip(cols, [("ILDC", "ILDC"), ("SC", "SC"), ("FC", "FC"), ("BI", "BI"),
                                                 ("BIC", "BIC")]):
            coluna.metric(nome, brl(bi[chave]))
    st.subheader("Exposições")
    st.dataframe(r["exposicoes"][["conta", "nome_conta", "classe", "ead", "fpr", "rwa"]].rename(columns={
        "conta": "Conta", "nome_conta": "Nome", "classe": "Classe", "ead": "EAD (R$)", "fpr": "FPR", "rwa": "RWA (R$)"}),
        hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Série histórica
# ---------------------------------------------------------------------------
with abas[2]:
    if len(itens_serie) < 2:
        st.info("A série histórica aparece quando há balancetes de duas ou mais datas-base da mesma "
                "instituição e modelo em `data/balancetes/`.")
    else:
        s = serie(itens_serie)
        t = s["tabela"].copy()
        t["Data-base"] = t["data_base"].map(lambda d: f"{d[4:]}/{d[2:4]}")
        if ip:
            longo = t.melt(id_vars="Data-base", value_vars=["indice_prip"], var_name="Índice", value_name="Valor")
            longo["Índice"] = "PRIP / RWAIP"
            rwa_cols = {"RWARCSimp": "Crédito", "RWASP": "Serviços de pagamento", "RWACAMSimp": "Câmbio"}
        else:
            longo = t.melt(id_vars="Data-base", value_vars=["indice_cp", "indice_n1", "indice_pr"],
                           var_name="Índice", value_name="Valor")
            longo["Índice"] = longo["Índice"].map({"indice_cp": "Capital Principal", "indice_n1": "Nível I",
                                                   "indice_pr": "PR (Basileia)"})
            rwa_cols = {"RWACPAD": "Crédito", "RWAOPAD": "Operacional", "RWAMPAD": "Mercado", "RWASP": "Pagamentos"}
        linhas = alt.Chart(longo).mark_line(point=True, strokeWidth=3).encode(
            x=alt.X("Data-base:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Valor:Q", axis=alt.Axis(format=".0%"), title=None),
            color=alt.Color("Índice:N", scale=alt.Scale(range=[LARANJA, CINZA, PRETO]),
                            legend=alt.Legend(orient="bottom")),
            tooltip=["Data-base", "Índice", alt.Tooltip("Valor:Q", format=".2%")]
        ).properties(title="Índices de capital estimados", height=340)
        st.altair_chart(linhas.configure_title(font="Arial", anchor="start"), width="stretch")
        rwa = t.melt(id_vars="Data-base", value_vars=list(rwa_cols), var_name="Parcela", value_name="Valor")
        rwa["Parcela"] = rwa["Parcela"].map(rwa_cols)
        ordem = list(rwa_cols.values())
        rwa["ordem"] = rwa["Parcela"].map({nome: i for i, nome in enumerate(ordem)})
        st.altair_chart(grafico_barras(rwa, "Data-base", "Valor", cor="Parcela", titulo="Composição do RWA",
                                       ordem_cor=ordem),
                        width="stretch")
        if (t["cosif"] == "legado").any() and (t["cosif"] == "atual").any():
            st.warning("Quebra de série em 01/2025: mudança do plano de contas Cosif (Res. CMN 4.966). "
                       "Até 12/2024 o balancete é publicado até o 3º nível e não separa instrumentos de capital.")

# ---------------------------------------------------------------------------
# Estresse
# ---------------------------------------------------------------------------
with abas[3]:
    config = carregar_cenarios()
    premissas = dict(config["premissas"])
    calibrar = (not ip) and r.get("comparacao") is not None and not r["comparacao"].empty
    if calibrar:
        calibrar = st.toggle("Calibrar a base ao índice divulgado", value=True,
                             help="Escala o RWA estimado para o RWA implícito pelo índice de Basileia divulgado.")
    base = base_do_resultado(r, calibrar=calibrar)
    principal = next(iter(base["niveis"]))

    st.subheader("Monte o seu cenário")
    c1, c2, c3 = st.columns(3)
    personalizado = {
        "nome": "Personalizado",
        "crescimento_credito": c1.slider("Crescimento da carteira de crédito", 0, 50, 10, format="%d%%") / 100,
        "perda_credito": c1.slider("Perda adicional de crédito", 0.0, 10.0, 3.0, 0.5, format="%.1f%%") / 100,
        "choque_juros": c2.slider("Alta de juros (bps)", 0, 600, 300, 25) / 10_000,
        "perda_cp": c2.slider("Prejuízo operacional (% do capital)", 0, 30, 5, format="%d%%") / 100,
        "crescimento_pagamentos": c3.slider("Crescimento de pagamentos", 0, 100, 15, format="%d%%") / 100,
    }
    premissas["duration_carteira"] = c3.number_input("Duration da carteira (anos)", 0.0, 10.0,
                                                    float(premissas["duration_carteira"]), 0.5)
    config["cenarios"] = config["cenarios"] + [personalizado]
    tabela = executar(base, config)

    linha = tabela.iloc[-1]
    m1, m2, m3, m4 = st.columns(4)
    indice_base = tabela.iloc[0][f"indice::{principal}"]
    m1.metric(f"Índice {principal} — base", pct(indice_base))
    m2.metric(f"Índice {principal} — cenário", pct(linha[f"indice::{principal}"]), f"{linha['variacao_pp']:+.2f} p.p.")
    m3.metric("Impacto no capital", brl(linha["impacto_capital"]))
    m4.metric("Situação", "Adequado" if linha["situacao"] == "ADEQUADO" else "Abaixo",
              "cumpre mínimo + ACP" if linha["situacao"] == "ADEQUADO" else "viola mínimo + ACP",
              delta_color="normal" if linha["situacao"] == "ADEQUADO" else "inverse")

    grafico = tabela[["cenario", f"indice::{principal}"]].rename(
        columns={"cenario": "Cenário", f"indice::{principal}": "Índice"})
    requerido = base["requeridos"][principal]
    barras = alt.Chart(grafico).mark_bar().encode(
        y=alt.Y("Cenário:N", sort=None, title=None, axis=alt.Axis(labelLimit=320)),
        x=alt.X("Índice:Q", axis=alt.Axis(format=".0%"), title=None),
        color=alt.condition(alt.datum["Índice"] >= requerido, alt.value(PRETO), alt.value(LARANJA)),
        tooltip=["Cenário", alt.Tooltip("Índice:Q", format=".2%")])
    regra = alt.Chart(pd.DataFrame({"r": [requerido]})).mark_rule(color=CINZA, strokeDash=[6, 4], size=2).encode(x="r:Q")
    st.altair_chart((barras + regra).properties(
        title=f"Índice {principal} por cenário (linha tracejada: requerido {pct(requerido)})", height=320
    ).configure_title(font="Arial", anchor="start"), width="stretch")

    rv = teste_reverso(base, premissas)
    st.subheader("Teste reverso")
    t1, t2, t3 = st.columns(3)
    t1.metric("Perda máxima absorvível", brl(rv["perda_maxima_absorvivel"]), f"limitante: {rv['nivel_limitante']}",
              delta_color="off")
    if rv["perda_credito_equivalente_pct"] == rv["perda_credito_equivalente_pct"]:
        t2.metric("Equivale a perda de crédito de", pct(rv["perda_credito_equivalente_pct"]))
    t3.metric("RWA pode crescer até", pct(rv["crescimento_rwa_maximo_pct"]), brl(rv["crescimento_rwa_maximo"]),
              delta_color="off")
    with st.expander("Tabela completa dos cenários"):
        st.dataframe(tabela_apresentacao(tabela), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Mapeamento e premissas
# ---------------------------------------------------------------------------
with abas[4]:
    st.subheader("Premissas da estimativa")
    for premissa in r["premissas"]:
        st.markdown(f"- {premissa}")
    if not r["sem_mapeamento"].empty:
        st.warning(f"{len(r['sem_mapeamento'])} conta(s) sem mapeamento tratadas a 100%.")
    st.subheader("Conciliação (soma das analíticas x saldo do grupo)")
    st.dataframe(r["conciliacao"], hide_index=True, width="stretch")
    st.subheader("Mapeamento conta a conta")
    filtro = st.text_input("Filtrar por conta ou nome")
    m = r["mapeamento"][["conta", "nome_conta", "saldo", "destino", "classe", "observacao"]]
    if filtro:
        m = m[m["conta"].str.contains(filtro) | m["nome_conta"].str.contains(filtro, case=False)]
    st.dataframe(m, hide_index=True, width="stretch")

    with tempfile.TemporaryDirectory() as pasta:
        arquivo = exportar(r, pasta)
        st.download_button("Baixar relatório Excel", arquivo.read_bytes(), file_name=arquivo.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
