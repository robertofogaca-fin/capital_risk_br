# Calculadora simplificada de Basileia e Patrimônio de Referência (PR/PRE)

# Capital regulatório da instituição (em R$)
cet1 = 1_200_000
tier1 = 1_500_000
capital_total = 2_000_000

# Carteira de crédito: (nome, exposição, peso de risco)
carteira = [
    ("Títulos públicos", 5_000_000, 0.00),
    ("Crédito corporativo", 1_000_000, 1.00),
    ("Crédito imobiliário", 800_000, 0.50),
    ("Crédito a pessoa física", 500_000, 0.75),
]

# Parcelas simplificadas do PRE (em R$)
pepr = 0.11 * sum(exposicao for _, exposicao, _ in carteira)
pjur = 50_000
pcam = 30_000
pcom = 20_000
pacs = 0
popr = 0

pre = pepr + pjur + pcam + pcom + pacs + popr
pr = capital_total

# Cálculo do RWA de crédito
rwa_credito = sum(exposicao * peso for _, exposicao, peso in carteira)

# Índices de Basileia
indice_cet1 = cet1 / rwa_credito
indice_tier1 = tier1 / rwa_credito
indice_capital_total = capital_total / rwa_credito

# Exigências mínimas de Basileia
minimo_cet1 = 0.045
minimo_tier1 = 0.06
minimo_capital_total = 0.08

# Exibição dos resultados
print("=" * 50)
print("CALCULADORA SIMPLIFICADA DE BASILEIA E PRE")
print("=" * 50)

print("\nCarteira de crédito:")
for nome, exposicao, peso in carteira:
    rwa = exposicao * peso
    print(f"{nome:<28} | Exposição: R$ {exposicao:>12,.2f} | "
          f"Peso: {peso:.0%} | RWA: R$ {rwa:>12,.2f}")

print(f"\nRWA de crédito: R$ {rwa_credito:,.2f}")

print("\nÍndices de Basileia:")
print(f"CET1: {indice_cet1:.2%} | mínimo: {minimo_cet1:.2%} | "
      f"{'ADEQUADO' if indice_cet1 >= minimo_cet1 else 'INSUFICIENTE'}")

print(f"Tier 1: {indice_tier1:.2%} | mínimo: {minimo_tier1:.2%} | "
      f"{'ADEQUADO' if indice_tier1 >= minimo_tier1 else 'INSUFICIENTE'}")

print(f"Capital total: {indice_capital_total:.2%} | mínimo: {minimo_capital_total:.2%} | "
      f"{'ADEQUADO' if indice_capital_total >= minimo_capital_total else 'INSUFICIENTE'}")

print("\nPatrimônio de Referência:")
print(f"PEPR: R$ {pepr:,.2f}")
print(f"PRE total: R$ {pre:,.2f}")
print(f"PR disponível: R$ {pr:,.2f}")
print(f"Excedente de PR: R$ {pr - pre:,.2f}")

if pr >= pre:
    print("Situação: PR adequado em relação ao PRE.")
else:
    print("Situação: PR insuficiente em relação ao PRE.")