"""Série histórica: períodos anuais do BI (Res. BCB 356, arts. 2º e 6º) e versões do Cosif."""
import pytest

from src.capital_balancete import (analisar_balancete, periodos_anuais, semestre_de_referencia,
                                   versao_cosif)
from src.config import carregar_parametros
from src.serie_historica import agrupar, analisar_serie

CAB = ("Balancete/Balanco Geral (DataBase:  {db} Documento: 4060 Instituição: 99999999)\n"
       "Data de geracao dos dados: 2026-08-31\nFonte: Instituições financeiras\n"
       "#DATA_BASE;DOCUMENTO;CNPJ;AGENCIA;NOME_INSTITUICAO;COD_CONGL;NOME_CONGL;TAXONOMIA;"
       "CONTA;NOME_CONTA;SALDO;REALIZAVEL_ATE_3M;REALIZAVEL_APOS_3M\n")


def _balancete(pasta, db, rendas_credito, despesas_captacao, servicos, ativos_rentaveis):
    contas = [
        ("10000000", "Ativo", ativos_rentaveis), ("16120000", "EMPRÉSTIMOS", ativos_rentaveis),
        ("40000000", "Passivo", ativos_rentaveis - 100), ("41510000", "DEPÓSITOS A PRAZO", ativos_rentaveis - 100),
        ("60000000", "PL", 100), ("61110000", "CAPITAL", 100),
        ("70000000", "Credor", rendas_credito + servicos), ("71105000", "RENDAS DE EMPRÉSTIMOS", rendas_credito),
        ("71799000", "RECEITAS DE OUTROS SERVIÇOS", servicos),
        ("80000000", "Devedor", -despesas_captacao), ("81130000", "DESPESAS DE DEPÓSITOS A PRAZO", -despesas_captacao),
    ]
    linhas = "".join(
        f"{db};4060;99999999;;BANCO TESTE;;TESTE;CONGLOMERADO PRUDENCIAL;{c};{n};{f'{v:.2f}'.replace('.', ',')};;\n"
        for c, n, v in contas)
    (pasta / f"{db}-4060-99999999.CSV").write_text(CAB.format(db=db) + linhas, encoding="latin-1")


@pytest.mark.parametrize("data_base, referencia", [
    ("202603", "202512"), ("202606", "202606"), ("202609", "202606"), ("202512", "202512"), ("202503", "202412"),
])
def test_semestre_de_referencia(data_base, referencia):
    assert semestre_de_referencia(data_base) == referencia


def test_periodos_anuais_usa_so_pares_completos():
    historico = {db: {} for db in ("202406", "202412", "202506", "202512", "202306")}
    # 202312 ausente: o 3º período (06/23 + 12/23) fica de fora
    assert periodos_anuais("202603", historico) == [("202506", "202512"), ("202406", "202412")]


def test_versao_cosif():
    assert versao_cosif("202412") == "legado"
    assert versao_cosif("202501") == "atual"


def test_bi_media_de_dois_anos(tmp_path):
    # Semestres: 2024 (06 e 12) e 2025 (06 e 12) ; margem anual 2024 = 2 x (100 - 60) = 80 ;
    # 2025 = 2 x (130 - 70) = 120 ; IEA = 10.000 -> teto 2,25% = 225 (não limita)
    # ILDC = média(80; 120) = 100 ; SC = média(2x10; 2x20) = 30 ; BI = 130
    for db, ii, ie, fi in (("202406", 100, 60, 10), ("202412", 100, 60, 10),
                           ("202506", 130, 70, 20), ("202512", 130, 70, 20)):
        _balancete(tmp_path, db, ii, ie, fi, 10_000)
    _balancete(tmp_path, "202603", 70, 40, 12, 10_000)
    historico = analisar_serie(agrupar(tmp_path)[("99999999", "4060")], carregar_parametros())
    ultimo = historico["ultimo"]
    assert ultimo["bi"]["periodos"] == 2
    assert ultimo["bi"]["ILDC"] == pytest.approx(100)
    assert ultimo["bi"]["SC"] == pytest.approx(30)
    assert ultimo["bi"]["BI"] == pytest.approx(130)
    assert len(historico["tabela"]) == 5


def test_sem_historico_anualiza(tmp_path):
    _balancete(tmp_path, "202603", 70, 40, 12, 10_000)
    r = analisar_balancete(tmp_path / "202603-4060-99999999.CSV", carregar_parametros())
    assert r["bi"]["periodos"] == 0
    assert r["bi"]["fator_anualizacao"] == 4
