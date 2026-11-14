"""Testes com valores calculados à mão."""
import pandas as pd
import pytest

from src.basileia import (SITUACAO_ACP, SITUACAO_MINIMO, SITUACAO_OK, avaliar_requerimentos,
                          capacidade_crescimento_rwa, capital_necessario, consolidar_rwa)
from src.capital_regulatorio import compor_pr
from src.config import carregar_parametros
from src.risco_credito import calcular_rwa_credito, calcular_rwa_por_operacao


@pytest.fixture
def parametros():
    return carregar_parametros()


def _operacao(classe, saldo, off=0.0, tipo_off="nenhum"):
    return pd.DataFrame([{
        "id_operacao": 1, "contraparte": "X", "produto": "Y", "classe_exposicao": classe,
        "saldo_balanco": saldo, "saldo_off": off, "tipo_off": tipo_off,
    }])


# ---------- Risco de crédito ----------

def test_soberano_tem_rwa_zero(parametros):
    assert calcular_rwa_credito(_operacao("soberano_brasil", 1_000_000), parametros) == 0


def test_ead_inclui_fcc_do_fora_do_balanco(parametros):
    # 4.000.000 + 10% x 6.000.000 = 4.600.000; x 75% = 3.450.000
    op = calcular_rwa_por_operacao(_operacao("varejo", 4_000_000, 6_000_000, "limite_cartao"), parametros)
    assert op.loc[0, "ead"] == pytest.approx(4_600_000)
    assert op.loc[0, "rwa"] == pytest.approx(3_450_000)


def test_aceita_fpr_acima_de_100(parametros):
    # 500.000 x 150% = 750.000
    assert calcular_rwa_credito(_operacao("em_atraso", 500_000), parametros) == pytest.approx(750_000)


def test_garantia_prestada_fcc_100(parametros):
    assert calcular_rwa_credito(
        _operacao("corporativo", 0, 1_000_000, "garantia_prestada"), parametros
    ) == pytest.approx(1_000_000)


def test_classe_desconhecida_gera_erro(parametros):
    with pytest.raises(ValueError, match="sem FPR"):
        calcular_rwa_credito(_operacao("cripto", 100), parametros)


def test_saldo_negativo_gera_erro(parametros):
    with pytest.raises(ValueError):
        calcular_rwa_credito(_operacao("corporativo", -1), parametros)


def test_carteira_exemplo(parametros):
    carteira = pd.read_csv("data/carteira.csv", encoding="utf-8")
    assert calcular_rwa_credito(carteira, parametros) == pytest.approx(18_250_000)


# ---------- Composição do PR ----------

def test_composicao_pr_deduz_ajustes():
    capital = pd.DataFrame({
        "componente": ["Capital", "Intangível", "Complementar", "Subordinada"],
        "nivel": ["capital_principal", "ajuste_prudencial", "capital_complementar", "nivel_2"],
        "valor": [1_000, 100, 200, 300],
    })
    resultado = compor_pr(capital)
    assert resultado["capital_principal"] == 900
    assert resultado["nivel_1"] == 1_100
    assert resultado["patrimonio_referencia"] == 1_400


# ---------- Requerimentos e ACP ----------

def test_rwa_soma_parcelas():
    parcelas = consolidar_rwa(18_250_000, {"RWAMPAD": 1_200_000, "RWAOPAD": 2_500_000})
    assert parcelas["RWA"] == pytest.approx(21_950_000)


def test_rwa_zero_gera_erro():
    with pytest.raises(ValueError):
        consolidar_rwa(0)


def _capital(cp, n1, pr):
    return {"capital_principal": cp, "nivel_1": n1, "patrimonio_referencia": pr}


def test_tres_situacoes(parametros):
    # RWA 1.000: requeridos com ACP 2,5% -> CP 70 | N1 85 | PR 105
    avaliacao = avaliar_requerimentos(_capital(70, 70, 100), 1_000, parametros)
    situacoes = dict(zip(avaliacao["nivel"], avaliacao["situacao"]))
    assert situacoes["Capital Principal"] == SITUACAO_OK        # 70 >= 70
    assert situacoes["Nível I"] == SITUACAO_ACP                 # 60 <= 70 < 85
    assert situacoes["Patrimônio de Referência"] == SITUACAO_ACP  # 80 <= 100 < 105


def test_abaixo_do_minimo(parametros):
    avaliacao = avaliar_requerimentos(_capital(40, 40, 40), 1_000, parametros)
    assert (avaliacao["situacao"] == SITUACAO_MINIMO).all()


def test_capacidade_e_aporte_exemplo(parametros):
    # PR 2.300.000 - 10,5% x 21.950.000 = -4.750 -> RWA excedente 45.238,10
    avaliacao = avaliar_requerimentos(_capital(1_800_000, 2_000_000, 2_300_000), 21_950_000, parametros)
    assert capital_necessario(avaliacao) == pytest.approx(4_750)
    assert capacidade_crescimento_rwa(avaliacao) == pytest.approx(-4_750 / 0.105)


def test_capacidade_positiva(parametros):
    # Folgas: CP 300-70=230 (/0,07=3.285,7) | N1 300-85=215 (/0,085=2.529,4) | PR 300-105=195 (/0,105=1.857,1)
    avaliacao = avaliar_requerimentos(_capital(300, 300, 300), 1_000, parametros)
    assert capacidade_crescimento_rwa(avaliacao) == pytest.approx(195 / 0.105)
    assert capital_necessario(avaliacao) == 0
