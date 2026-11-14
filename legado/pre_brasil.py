FATOR_PEPR = 0.11


def calcular_pepr(carteira) -> float:
    exposicao_total = sum(exposicao for _, exposicao, _ in carteira)
    return FATOR_PEPR * exposicao_total


def calcular_pre(pepr: float, pjur: float, pcam: float, pcom: float) -> float:
    return pepr + pjur + pcam + pcom


def avaliar_pr(pre: float, pr: float) -> dict:
    excedente = pr - pre

    return {
        "pre": pre,
        "pr": pr,
        "excedente": excedente,
        "situacao": "ADEQUADO" if excedente >= 0 else "INSUFICIENTE",
    }