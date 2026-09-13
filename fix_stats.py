import json

# Charger les stats actuelles
with open('stats.json', 'r', encoding='utf-8') as f:
    stats = json.load(f)

print("📊 Stats AVANT fusion:")
for key, value in sorted(stats.items(), key=lambda x: x[1], reverse=True):
    print(f"  {key}: {value}")

# Fonction pour normaliser les clés (retirer les préfixes de grade)
def normalize_key(key):
    """Retire les préfixes de grade (dir-, cds-, med-, etc.)"""
    prefixes = ["dir-", "cds-", "med-", "inf-", "ads-", "int-", "emt-", "rh-", "drh-"]
    for prefix in prefixes:
        if key.startswith(prefix):
            return key[len(prefix):]
    return key

# Fusionner les stats avec la même clé normalisée
merged_stats = {}
duplicates = []

for key, value in stats.items():
    normalized_key = normalize_key(key)
    
    if normalized_key in merged_stats:
        # C'est un doublon ! Fusionner les valeurs
        old_value = merged_stats[normalized_key]
        merged_stats[normalized_key] += value
        duplicates.append(f"  ✅ Fusion: '{key}' ({value}) + '{normalized_key}' ({old_value}) = {merged_stats[normalized_key]}")
    else:
        merged_stats[normalized_key] = value

print(f"\n🔄 Fusion en cours...")
if duplicates:
    print(f"📌 {len(duplicates)} doublon(s) détecté(s):")
    for dup in duplicates:
        print(dup)
else:
    print("✅ Aucun doublon détecté")

print(f"\n📊 Stats APRÈS fusion:")
for key, value in sorted(merged_stats.items(), key=lambda x: x[1], reverse=True):
    print(f"  {key}: {value}")

# Sauvegarder les stats fusionnées
with open('stats.json', 'w', encoding='utf-8') as f:
    json.dump(merged_stats, f, ensure_ascii=False, indent=2)

print(f"\n✅ Stats mises à jour!")
print(f"📈 Total: {sum(merged_stats.values())} réas")
print(f"👥 Employés: {len(merged_stats)}")

# Nettoyer le channel_map.json pour forcer la recréation du mapping
with open('channel_map.json', 'w', encoding='utf-8') as f:
    json.dump({}, f, ensure_ascii=False, indent=2)

print(f"🗑️ Mapping des channels réinitialisé (sera recréé automatiquement)")
