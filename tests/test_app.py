"""Fase 4 — o dashboard abre sem erros (pulado se o Streamlit não estiver instalado)."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


def test_dashboard_abre_sem_erros():
    app = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=180).run()
    assert not app.exception
    if app.selectbox:  # há balancetes locais: percorre um de cada regime
        for opcao in app.selectbox[0].options[:3]:
            app.selectbox[0].select(opcao).run()
            assert not app.exception, opcao
