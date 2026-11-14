"""Fase 3 — cenários de estresse e teste reverso (valores calculados à mão)."""
import pytest

from src.estresse import aplicar_cenario, carregar_cenarios, executar
from src.estresse import teste_reverso as reverso

PREMISSAS = {"aliquota_tributos_banco": 0.45, "aliquota_tributos_ip": 0.34, "duration_carteira": 2.0}


def _cenario(**choques):
    base = {"nome": "teste", "crescimento_credito": 0.0, "perda_credito": 0.0, "choque_juros": 0.0,
            "perda_cp": 0.0, "crescimento_pagamentos": 0.0}
    return {**base, **choques}


@pytest.fixture
def banco():
    return {"regime": "banco",
            "niveis": {"Capital Principal": 100.0, "Nível I": 110.0, "Patrimônio de Referência": 130.0},
            "requeridos": {"Capital Principal": 0.08, "Nível I": 0.095, "Patrimônio de Referência": 0.115},
            "parcelas": {"RWACPAD": 800.0, "RWAOPAD": 200.0, "RWAMPAD": 0.0, "RWASP": 0.0},
            "parcela_credito": "RWACPAD", "credito_ead": 600.0, "credito_rwa": 500.0, "exposicao_juros": 300.0}


@pytest.fixture
def ip():
    return {"regime": "ip", "niveis": {"PRIP": 100.0}, "requeridos": {"PRIP": 0.12},
            "parcelas": {"RWASP": 400.0, "RWARCSimp": 100.0, "RWACAMSimp": 0.0},
            "parcela_credito": "RWARCSimp", "credito_ead": 0.0, "credito_rwa": 0.0, "exposicao_juros": 0.0}


def test_base_sem_choque(banco):
    r = aplicar_cenario(banco, _cenario(), PREMISSAS)
    assert r["indice::Capital Principal"] == pytest.approx(0.10)
    assert r["situacao"] == "ADEQUADO"


def test_crescimento_de_credito_aumenta_rwa(banco):
    # RWACPAD 800 + 20% x RWA de crédito 500 = 900 -> RWA 1.100 -> CP 100 / 1.100
    r = aplicar_cenario(banco, _cenario(crescimento_credito=0.20), PREMISSAS)
    assert r["rwa_total"] == pytest.approx(1_100)
    assert r["indice::Capital Principal"] == pytest.approx(100 / 1_100)


def test_inadimplencia_liquida_de_tributos(banco):
    # 3% x EAD 600 x (1 - 45%) = 9,9
    r = aplicar_cenario(banco, _cenario(perda_credito=0.03), PREMISSAS)
    assert r["perda_credito"] == pytest.approx(9.9)
    assert r["capital::Capital Principal"] == pytest.approx(90.1)


def test_choque_de_juros_usa_duration(banco):
    # 300 bps x duration 2 x exposição 300 x (1 - 45%) = 9,9
    r = aplicar_cenario(banco, _cenario(choque_juros=0.03), PREMISSAS)
    assert r["perda_juros"] == pytest.approx(9.9)


def test_prejuizo_reduz_todos_os_niveis(banco):
    r = aplicar_cenario(banco, _cenario(perda_cp=0.10), PREMISSAS)
    assert r["capital::Nível I"] == pytest.approx(100)
    assert r["capital::Patrimônio de Referência"] == pytest.approx(120)


def test_situacao_abaixo_do_requerido(banco):
    r = aplicar_cenario(banco, _cenario(perda_cp=0.30), PREMISSAS)  # CP 70 < 8% x 1.000
    assert r["situacao"] == "ABAIXO DO REQUERIDO"


def test_ip_crescimento_de_pagamentos(ip):
    # RWASP 400 x 1,25 = 500 -> RWAIP 600
    r = aplicar_cenario(ip, _cenario(crescimento_pagamentos=0.25), PREMISSAS)
    assert r["indice::PRIP"] == pytest.approx(100 / 600)


def test_teste_reverso(banco):
    # folgas: CP 100-80=20 ; N1 110-95=15 ; PR 130-115=15 -> perda máxima 15
    # crescimento de RWA: min(20/0,08 ; 15/0,095 ; 15/0,115) = 130,43
    rv = reverso(banco, PREMISSAS)
    assert rv["perda_maxima_absorvivel"] == pytest.approx(15)
    assert rv["crescimento_rwa_maximo"] == pytest.approx(15 / 0.115)
    assert rv["perda_credito_equivalente_pct"] == pytest.approx(15 / 0.55 / 600)


def test_cenarios_configurados(banco):
    cenarios = carregar_cenarios()
    tabela = executar(banco, cenarios)
    assert tabela.iloc[0]["cenario"] == "Base"
    assert tabela.iloc[0]["variacao_pp"] == pytest.approx(0)
    assert (tabela["variacao_pp"] <= 1e-9).all()  # nenhum choque melhora o índice


def test_choque_negativo_rejeitado(tmp_path):
    arquivo = tmp_path / "c.toml"
    arquivo.write_text('[premissas]\nduration_carteira = 2.0\n[[cenarios]]\nnome = "x"\nperda_cp = -0.1\n')
    with pytest.raises(ValueError, match="negativo"):
        carregar_cenarios(arquivo)
