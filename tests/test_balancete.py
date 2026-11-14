"""Leitura de balancete Cosif e cálculo de capital por regime (IP e banco)."""
from pathlib import Path

import pandas as pd
import pytest

from src.balancete_cosif import analiticas, conciliar, identificacao, ler_balancete, prefixo_cosif
from src.capital_balancete import (analisar_balancete, carregar_mapeamento, detectar_regime, mapear,
                                   meses_no_semestre)
from src.config import carregar_parametros

# Balancetes reais ficam fora do Git: os testes com eles rodam só se houver arquivos na pasta
REAIS = sorted(Path("data/balancetes").glob("*.[cC][sS][vV]"))
sem_balancetes_reais = pytest.mark.skipif(not REAIS, reason="sem balancetes reais em data/balancetes")

CABECALHO = ("Balancete/Balanco Geral (DataBase:  202606 Documento: 4060 Instituição: 99999999)\n"
             "Data de geracao dos dados: 2026-08-31\nFonte: Instituições financeiras\n"
             "#DATA_BASE;DOCUMENTO;CNPJ;AGENCIA;NOME_INSTITUICAO;COD_CONGL;NOME_CONGL;TAXONOMIA;"
             "CONTA;NOME_CONTA;SALDO;REALIZAVEL_ATE_3M;REALIZAVEL_APOS_3M\n")


def _linha(conta, nome, saldo):
    valor = f"{saldo:.2f}".replace(".", ",")
    return f"202606;4060;99999999;;BANCO TESTE;;TESTE - PRUDENCIAL;CONGLOMERADO PRUDENCIAL;{conta};{nome};{valor};;\n"


@pytest.fixture
def balancete_banco(tmp_path):
    contas = [
        ("10000000", "Ativo Realizável", 2000), ("11000000", "DISPONIBILIDADES", 200),
        ("11100000", "Caixa", 200), ("11110000", "CAIXA", 200),
        ("16000000", "OPERAÇÕES DE CRÉDITO", 1000), ("16100000", "Empréstimos", 1000),
        ("16120000", "EMPRÉSTIMOS", 1000),
        ("18000000", "OUTROS CRÉDITOS", 800), ("18800000", "Diversos", 800),
        ("18825000", "ATIVOS FISCAIS DIFERIDOS", 300), ("18892000", "DEVEDORES DIVERSOS", 500),
        ("20000000", "Ativo Permanente", 100), ("25000000", "INTANGÍVEL", 100),
        ("25100000", "Ativos Intangíveis", 100), ("25115000", "SISTEMAS", 100),
        ("30000000", "Compensação Ativa", 400), ("33400000", "Compromissos", 400),
        ("33410000", "NÃO CANCELÁVEIS", 400),
        ("40000000", "Passivo", 1500), ("41510000", "DEPÓSITOS A PRAZO", 1500),
        ("60000000", "Patrimônio Líquido", 550), ("61110000", "CAPITAL", 550),
        ("70000000", "Resultado Credor", 120), ("71105000", "RENDAS DE EMPRÉSTIMOS", 100),
        ("71799000", "RECEITAS DE OUTROS SERVIÇOS", 20),
        ("80000000", "Resultado Devedor", -70), ("81130000", "DESPESAS DE DEPÓSITOS A PRAZO", -40),
        ("81733000", "DESPESAS DE PESSOAL", -30),
    ]
    caminho = tmp_path / "202606-4060-99999999.CSV"
    caminho.write_text(CABECALHO + "".join(_linha(*c) for c in contas), encoding="latin-1")
    return caminho


@pytest.fixture
def balancete_ip(tmp_path):
    contas = [
        ("10000000", "Ativo Realizável", 1300), ("11000000", "DISPONIBILIDADES", 100),
        ("11200000", "Depósitos Bancários", 100), ("11230000", "DEPÓSITOS BANCÁRIOS", 100),
        ("14000000", "RELAÇÕES INTERFINANCEIRAS", 1000), ("14200000", "Créditos Vinculados", 1000),
        ("14202000", "BANCO CENTRAL - DEPÓSITOS DE MOEDA ELETRÔNICA", 1000),
        ("18000000", "OUTROS CRÉDITOS", 200), ("18800000", "Diversos", 200),
        ("18825000", "ATIVOS FISCAIS DIFERIDOS", 50), ("18892000", "DEVEDORES DIVERSOS", 150),
        ("20000000", "Ativo Permanente", 30), ("25000000", "INTANGÍVEL", 30),
        ("25100000", "Ativos Intangíveis", 30), ("25115000", "SISTEMAS", 30),
        ("30000000", "Compensação Ativa", 3000), ("30900000", "Controle", 3000),
        ("30969000", "CONTA DE PAGAMENTO PRÉ-PAGA - SALDO MÉDIO", 1000),
        ("30971000", "TRANSAÇÕES DE PAGAMENTO REALIZADAS - SALDO MÉDIO", 2000),
        ("40000000", "Passivo Exigível", 1000), ("41930000", "CONTA DE PAGAMENTO PRÉ-PAGA", 1000),
        ("60000000", "Patrimônio Líquido", 300), ("61110000", "CAPITAL", 300),
        ("70000000", "Resultado Credor", 40), ("71705000", "RECEITAS POR SERVIÇOS DE PAGAMENTO", 40),
        ("80000000", "Resultado Devedor", -10), ("81919000", "DESPESAS COM SERVIÇOS", -10),
    ]
    cab = CABECALHO.replace("4060", "4010")
    linhas = "".join(_linha(*c).replace(";4060;", ";4010;")
                     .replace("CONGLOMERADO PRUDENCIAL", "INSTITUICOES DE PAGAMENTO") for c in contas)
    caminho = tmp_path / "202606-4010-88888888.CSV"
    caminho.write_text(cab + linhas, encoding="latin-1")
    return caminho


# ---------- Leitura ----------

@pytest.mark.parametrize("conta, esperado", [
    ("10000000", "1"), ("11000000", "11"), ("11200000", "112"), ("11230000", "11230"),
    ("30970000", "30970"), ("30971000", "30971"), ("18825000", "18825"),
])
def test_prefixo_cosif(conta, esperado):
    assert prefixo_cosif(conta) == esperado


def test_titulos_irmaos_nao_sao_pai_e_filho(balancete_ip):
    # 30969000 e 30971000 são títulos distintos: ambos analíticos
    b = ler_balancete(balancete_ip)
    assert b.set_index("conta").loc[["30969000", "30971000"], "analitica"].all()


def test_leitura_converte_decimal_brasileiro(balancete_banco):
    b = ler_balancete(balancete_banco)
    assert b.set_index("conta").loc["81130000", "saldo"] == -40.0


def test_identifica_analiticas(balancete_banco):
    a = analiticas(ler_balancete(balancete_banco))
    assert set(a["conta"]) >= {"11110000", "16120000", "18825000"}
    assert "11000000" not in set(a["conta"])


def test_conciliacao_patrimonial_fecha(balancete_ip):
    conc = conciliar(ler_balancete(balancete_ip))
    assert (conc.loc[conc["grupo"].isin(list("124678")), "diferenca"].abs() < 0.01).all()


def test_regime_por_taxonomia(balancete_ip):
    assert detectar_regime(identificacao(ler_balancete(balancete_ip))) == "ip"
    assert detectar_regime({"taxonomia": "BANCOS MULTIPLOS"}) == "banco"


def test_mapeamento_usa_prefixo_mais_longo(balancete_banco):
    m = mapear(analiticas(ler_balancete(balancete_banco)),
               carregar_mapeamento("mapeamento_cosif_banco.csv"), "outros_ativos")
    linha = m.set_index("conta")
    assert linha.loc["18825000", "destino"] == "dta"           # e não "18" (outros créditos)
    assert linha.loc["18892000", "classe"] == "outros_ativos"


@pytest.mark.parametrize("data_base, meses", [("202603", 3), ("202606", 6), ("202609", 3), ("202612", 6)])
def test_meses_no_semestre(data_base, meses):
    assert meses_no_semestre(data_base) == meses


# ---------- Regime IP (balancete sintético) ----------

def test_prip_ip(balancete_ip):
    # PL 300 + resultado 30 - intangível 30 - créditos tributários 50 = 250
    r = analisar_balancete(balancete_ip, carregar_parametros())
    assert r["regime"] == "ip"
    assert r["prip"] == pytest.approx(250)


def test_rwasp_ip(balancete_ip):
    # MOE = 0,2% x 2.000 + 1% x 1.000 = 14 ; RWASP = 14 / 8% = 175
    r = analisar_balancete(balancete_ip, carregar_parametros())
    assert r["parcelas"]["RWASP"] == pytest.approx(175)


def test_rwarcsimp_ip(balancete_ip):
    # depósitos bancários 100 x 35% + Banco Central 1.000 x 0% + devedores 150 x 100%
    r = analisar_balancete(balancete_ip, carregar_parametros())
    assert r["parcelas"]["RWARCSimp"] == pytest.approx(185)


def test_requerimento_ip_usa_f_linha_12(balancete_ip):
    r = analisar_balancete(balancete_ip, carregar_parametros())
    assert r["requerido"] == pytest.approx(0.12 * 360)


def test_relatorio_anonimizado(balancete_ip):
    r = analisar_balancete(balancete_ip, carregar_parametros())
    assert r["identificacao"]["cnpj"] == "omitido"
    assert "TESTE" not in r["identificacao"]["instituicao"].upper()


# ---------- Regime banco (balancete sintético) ----------

def test_banco_sintetico(balancete_banco):
    r = analisar_balancete(balancete_banco, carregar_parametros())
    # CP = 550 + (120 - 70) - intangível 100 = 500 (créditos tributários: 0% deduzido)
    assert r["capital"]["capital_principal"] == pytest.approx(500)
    # RWACPAD = caixa 0 + empréstimos 1.000 x 75% + DTA 300 x 100% + devedores 500 x 100%
    #         + compromisso 400 x 40% x 100% = 750 + 300 + 500 + 160
    assert r["parcelas"]["RWACPAD"] == pytest.approx(1_710)


def test_bi_sintetico_anualiza_semestre(balancete_banco):
    # data-base 06: semestre completo -> fator 2
    # ILDC = min(|100 - 40| x 2 = 120 ; 2,25% x 1.000 = 22,5) = 22,5 ; SC = 20 x 2 = 40 ; FC = 0
    r = analisar_balancete(balancete_banco, carregar_parametros())
    assert r["bi"]["fator_anualizacao"] == 2
    assert r["bi"]["ILDC"] == pytest.approx(22.5)
    assert r["bi"]["SC"] == pytest.approx(40)
    assert r["bi"]["RWAOPAD"] == pytest.approx(62.5 * 0.12 / 0.08)


# ---------- Balancetes reais (locais, fora do Git) ----------

@sem_balancetes_reais
@pytest.mark.parametrize("arquivo", REAIS, ids=lambda a: a.name[:11])
def test_real_concilia_e_calcula(arquivo):
    parametros = carregar_parametros()
    r = analisar_balancete(arquivo, parametros)
    assert (r["conciliacao"]["diferenca"].abs() < 0.01).all()
    assert r["sem_mapeamento"].empty
    total = "RWAIP" if r["regime"] == "ip" else "RWA"
    assert r["parcelas"][total] > 0


@sem_balancetes_reais
def test_real_rwa_implicito_consistente():
    # Validação: com índices divulgados cadastrados, o RWA implícito pelo CP e pelo PR deve coincidir
    for arquivo in REAIS:
        r = analisar_balancete(arquivo, carregar_parametros())
        if r.get("comparacao") is not None and len(r["comparacao"]) == 2:
            implicitos = r["comparacao"]["rwa_implicito"]
            assert implicitos.max() / implicitos.min() == pytest.approx(1, abs=0.02)
