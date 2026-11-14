"""Fase 2 — risco operacional (Res. BCB 356/2023) e RWASP (Res. BCB 202/2022).

Valores esperados calculados à mão a partir de data/*.csv.
"""
import copy
import math

import pandas as pd
import pytest

from src.config import carregar_parametros
from src.risco_operacional import (aplicar_transicao, calcular_bic, calcular_componentes_bi,
                                   calcular_ilm, calcular_lc, calcular_rwaopad, ilm_aplicavel,
                                   preparar_perdas)
from src.servicos_pagamento import calcular_rwasp


@pytest.fixture
def parametros():
    return carregar_parametros()


@pytest.fixture
def dre():
    return pd.read_csv("data/dre_operacional.csv", encoding="utf-8")


@pytest.fixture
def perdas():
    return pd.read_csv("data/perdas_operacionais.csv", encoding="utf-8")


@pytest.fixture
def servicos():
    return pd.read_csv("data/servicos_pagamento.csv", encoding="utf-8")


# ---------- BI ----------

def test_ildc_respeita_teto_de_225(parametros, dre):
    # média |II-IE| = 950.000 > 2,25% x 22.500.000 = 506.250 -> 506.250 + dividendos 10.000
    bi = calcular_componentes_bi(dre, parametros, sujeita_rwasp=True)
    assert bi["teto_ildc_aplicado"]
    assert bi["ILDC"] == pytest.approx(516_250)


def test_sc_exclui_servicos_de_pagamento(parametros, dre):
    # FI líquida média = 640.000 ; OOE média = 79.666,67 -> SC = 719.666,67
    assert calcular_componentes_bi(dre, parametros, True)["SC"] == pytest.approx(719_666.6667)
    # sem exclusão: FI média = 880.000 -> SC = 959.666,67
    assert calcular_componentes_bi(dre, parametros, False)["SC"] == pytest.approx(959_666.6667)


def test_fc_usa_valor_absoluto(parametros, dre):
    # média(70k, 35k, 52k) + média(45k, 40k, 38k) = 52.333,33 + 41.000
    assert calcular_componentes_bi(dre, parametros, True)["FC"] == pytest.approx(93_333.3333)


def test_dre_precisa_de_tres_periodos(parametros, dre):
    with pytest.raises(ValueError, match="3 períodos"):
        calcular_componentes_bi(dre.head(2), parametros, True)


# ---------- BIC ----------

def test_bic_primeira_faixa(parametros):
    assert calcular_bic(1_000_000, parametros["risco_operacional"]["faixas_bic"]) == pytest.approx(120_000)


def test_bic_marginal_entre_faixas(parametros):
    # 12% x 5 bi + 15% x 5 bi = 0,6 bi + 0,75 bi
    faixas = parametros["risco_operacional"]["faixas_bic"]
    assert calcular_bic(10e9, faixas) == pytest.approx(1.35e9)


def test_bic_terceira_faixa(parametros):
    # 0,6 bi + 15% x 145 bi + 18% x 50 bi = 0,6 + 21,75 + 9 = 31,35 bi
    faixas = parametros["risco_operacional"]["faixas_bic"]
    assert calcular_bic(200e9, faixas) == pytest.approx(31.35e9)


# ---------- LC e ILM ----------

def test_lc_janela_e_limiar(parametros, perdas):
    # Consideradas: 2019 (550 mil) e 2024 (600 mil). Fora: 2014 (janela), 2022 e 2025 (< 500 mil)
    preparadas = preparar_perdas(perdas, 2026, parametros)
    assert preparadas["considerada"].sum() == 2
    assert calcular_lc(preparadas, parametros) == pytest.approx(1_150_000 / 10 * 6)


def test_ilm_igual_a_1_quando_lc_igual_bic():
    assert calcular_ilm(100.0, 100.0) == pytest.approx(1.0)


def test_ilm_abaixo_de_1_sem_perdas():
    assert calcular_ilm(0.0, 100.0) == pytest.approx(math.log(math.e - 1))


@pytest.mark.parametrize("segmento, opta, esperado", [
    ("S1", False, 1.6), ("S2", False, 1.6), ("S3", False, 1.0), ("S3", True, 1.6), ("S4", False, 1.0),
])
def test_ilm_por_segmento(segmento, opta, esperado):
    assert ilm_aplicavel(segmento, 1.6, opta) == esperado


def test_s5_fora_do_escopo():
    with pytest.raises(ValueError, match="S5"):
        ilm_aplicavel("S5", 1.2)


# ---------- Transição (art. 19) ----------

def test_transicao_2026_aplica_50(parametros):
    valor, _ = aplicar_transicao(2_000_000, 2026, parametros)  # base 1.900.000
    assert valor == pytest.approx(1_950_000)


def test_transicao_nao_reduz_quando_novo_menor(parametros):
    valor, _ = aplicar_transicao(1_500_000, 2026, parametros)
    assert valor == 1_500_000


def test_transicao_encerrada_em_2028(parametros):
    valor, _ = aplicar_transicao(2_000_000, 2028, parametros)
    assert valor == 2_000_000


# ---------- RWAOPAD completo ----------

def test_rwaopad_exemplo(parametros, dre, perdas):
    # BI = 1.329.250 ; BIC = 159.510 ; S4 -> ILM 1 ; integral = 1.993.875 ; transição 2026 -> 1.946.937,50
    r = calcular_rwaopad(dre, perdas, parametros)
    assert r["BIC"] == pytest.approx(159_510)
    assert r["RWAOPAD_integral"] == pytest.approx(1_993_875)
    assert r["RWAOPAD"] == pytest.approx(1_946_937.5)


def test_rwaopad_s2_usa_ilm(parametros, dre, perdas):
    p = copy.deepcopy(parametros)
    p["instituicao"]["segmento"] = "S2"
    p["risco_operacional"]["transicao"]["aplicar"] = False
    r = calcular_rwaopad(dre, perdas, p)
    esperado_ilm = math.log(math.e - 1 + (690_000 / 159_510) ** 0.8)
    assert r["ILM_aplicado"] == pytest.approx(esperado_ilm)
    assert r["RWAOPAD"] == pytest.approx(159_510 * esperado_ilm / 0.08)


# ---------- RWASP ----------

def test_rwasp_exemplo(parametros, servicos):
    # MOE = 0,2% x 3.002.500 + 1% x 1.487.500 = 6.005 + 14.875
    # ADQ = 2% x 3.985.000 = 79.700 ; PISP = 1,5% x 41.250 = 618,75
    r = calcular_rwasp(servicos, parametros)
    assert r["MOE"] == pytest.approx(20_880)
    assert r["ADQ"] == pytest.approx(79_700)
    assert r["PISP"] == pytest.approx(618.75)
    assert r["RWASP"] == pytest.approx(101_198.75 / 0.08)


def test_rwasp_zero_quando_nao_sujeita(parametros, servicos):
    p = copy.deepcopy(parametros)
    p["instituicao"]["sujeita_rwasp"] = False
    assert calcular_rwasp(servicos, p)["RWASP"] == 0


def test_rwasp_exige_12_meses(parametros, servicos):
    with pytest.raises(ValueError, match="12 meses"):
        calcular_rwasp(servicos.head(11), parametros)
