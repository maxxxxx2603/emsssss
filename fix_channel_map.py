#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour régénérer le channel_map.json avec les clés normalisées
Exécuter ce script pour forcer la synchronisation du mapping
"""

import json
import os

def normalize_employee_key(name: str) -> str:
    """Normalise un identifiant d'employé"""
    if not name:
        return ""
    s = name.strip().lower()
    # Retirer crochets
    for br in ["[emt]", "[int]", "[cds]", "[rh]", "[drh]", "[med]", "[ads]", "[inf]", "[dir]"]:
        s = s.replace(br, "")
    s = s.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    s = s.replace("_", "-")
    # Supprimer TOUS les préfixes
    prefixes = [
        "dir-", "dir ", 
        "cds-", "cds ", 
        "med-", "med ", 
        "inf-", "inf ", 
        "ads-", "ads ", 
        "int-", "int ", 
        "emt-", "emt ", 
        "drh-", "drh ", 
        "rh-", "rh "
    ]
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if s.startswith(p):
                s = s[len(p):]
                changed = True
                break
    # Normaliser espaces -> tirets
    s = "-".join(filter(None, s.replace("/", " ").replace("|", " ").split()))
    # Nettoyer tirets multiples
    while "--" in s:
        s = s.replace("--", "-")
    s = s.strip("-")
    return s

def main():
    print("🔄 Réinitialisation du channel_map.json...")
    
    # Vider le channel_map pour forcer la régénération avec les nouvelles règles
    channel_map = {}
    
    with open('channel_map.json', 'w', encoding='utf-8') as f:
        json.dump(channel_map, f, ensure_ascii=False, indent=2)
    
    print("✅ channel_map.json vidé!")
    print("📌 Le bot va automatiquement recréer les mappings avec les clés normalisées")
    print("")
    print("🔍 Exemples de normalisation:")
    test_cases = [
        "🔴dir-logan-morales",
        "🟠logan-morales",
        "🔴dir logan morales",
        "🟢Logan Morales",
        "🔴DIR-Logan-Morales"
    ]
    
    for test in test_cases:
        # Enlever l'emoji
        raw = test[1:].strip() if len(test) > 1 else test
        normalized = normalize_employee_key(raw)
        print(f"  {test} → {normalized}")
    
    print("")
    print("✅ Tous les channels avec préfixe 'dir-', 'cds-', etc. seront maintenant normalisés!")
    print("📝 Exemple: 'dir-logan-morales' → 'logan-morales'")

if __name__ == "__main__":
    main()
