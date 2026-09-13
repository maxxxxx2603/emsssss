import json

# Nouvelles stats avec uniquement les employés actifs
new_stats = {
    "mahmoud-mendy": 88,
    "abdel-miller": 34,
    "logan-morales": 50,
    "maena-diaz": 55,
    "abdoul-riad": 31,
    "abdelkader-znina": 24,
    "ryan-cooper": 29,
    "ilyas-zakaka": 21,
    "kayden-smith": 15,
    "martin-martin": 20,
    "gino-rina": 14,
    "jhon-gotti": 73,
    "ayden-blasko": 11,
    "youssef-boumedin": 23,
    "bilel-manai": 7,
    "normand-auclair": 14,
    "naj-ben": 7,
    "samir-boey": 4,
    "juan-pablo-escobar": 26,
    "jack-talbot": 1
}

# Sauvegarder dans stats.json
with open('stats.json', 'w', encoding='utf-8') as f:
    json.dump(new_stats, f, ensure_ascii=False, indent=2)

print("✅ Stats mises à jour avec succès!")
print(f"📊 {len(new_stats)} employés enregistrés")
print(f"📈 Total des réas: {sum(new_stats.values())}")
