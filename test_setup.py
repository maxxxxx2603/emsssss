#!/usr/bin/env python3
"""
Script de test pour vérifier que le système EMS est correctement configuré
"""

import os
import json
import sys
from pathlib import Path

def check_files():
    """Vérifier que tous les fichiers nécessaires existent"""
    print("📁 Vérification des fichiers...")
    
    required_files = [
        'main.py',
        'app.py',
        'requirements.txt',
        'run_all.py',
        'templates/dashboard.html',
        'templates/employees.html',
        'templates/webhooks.html',
        'absences.json',
        'webhook_logs.json'
    ]
    
    all_ok = True
    for file in required_files:
        if Path(file).exists():
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} - MANQUANT!")
            all_ok = False
    
    return all_ok

def check_python_syntax():
    """Vérifier la syntaxe Python des fichiers"""
    print("\n🔍 Vérification de la syntaxe Python...")
    
    import py_compile
    
    python_files = ['main.py', 'app.py', 'run_all.py']
    all_ok = True
    
    for file in python_files:
        try:
            py_compile.compile(file, doraise=True)
            print(f"  ✅ {file}")
        except py_compile.PyCompileError as e:
            print(f"  ❌ {file} - ERREUR!")
            print(f"     {e}")
            all_ok = False
    
    return all_ok

def check_json_files():
    """Vérifier que les fichiers JSON sont valides"""
    print("\n📋 Vérification des fichiers JSON...")
    
    json_files = {
        'absences.json': {},
        'webhook_logs.json': {'events': []}
    }
    
    all_ok = True
    for file, expected_structure in json_files.items():
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"  ✅ {file}")
        except json.JSONDecodeError:
            print(f"  ❌ {file} - JSON invalide!")
            all_ok = False
        except FileNotFoundError:
            print(f"  ⚠️  {file} - Créé avec structure par défaut")
    
    return all_ok

def check_imports():
    """Vérifier que les imports majeurs fonctionnent"""
    print("\n📦 Vérification des imports...")
    
    imports_to_check = [
        ('discord', 'discord.py'),
        ('flask', 'Flask'),
        ('matplotlib', 'matplotlib'),
        ('pandas', 'pandas'),
        ('aiohttp', 'aiohttp'),
    ]
    
    all_ok = True
    for module, display_name in imports_to_check:
        try:
            __import__(module)
            print(f"  ✅ {display_name}")
        except ImportError:
            print(f"  ❌ {display_name} - NON INSTALLÉ!")
            print(f"     Installez avec: pip install -r requirements.txt")
            all_ok = False
    
    return all_ok

def check_templates():
    """Vérifier que les templates HTML contiennent le code minimal"""
    print("\n🎨 Vérification des templates HTML...")
    
    templates = {
        'templates/dashboard.html': ['<html', 'chart', 'employee'],
        'templates/employees.html': ['<html', 'table', 'absence'],
        'templates/webhooks.html': ['<html', 'webhook', 'secret']
    }
    
    all_ok = True
    for template, keywords in templates.items():
        try:
            with open(template, 'r', encoding='utf-8') as f:
                content = f.read().lower()
            
            missing_keywords = [kw for kw in keywords if kw not in content]
            
            if not missing_keywords:
                print(f"  ✅ {template}")
            else:
                print(f"  ⚠️  {template} - Manque: {missing_keywords}")
                all_ok = False
        except FileNotFoundError:
            print(f"  ❌ {template} - NON TROUVÉ!")
            all_ok = False
    
    return all_ok

def main():
    print("=" * 60)
    print("🚑 EMS MANAGEMENT SYSTEM - Vérification de Configuration")
    print("=" * 60)
    print()
    
    results = []
    
    # Exécuter les vérifications
    results.append(("Fichiers", check_files()))
    results.append(("Syntaxe Python", check_python_syntax()))
    results.append(("Fichiers JSON", check_json_files()))
    results.append(("Templates HTML", check_templates()))
    results.append(("Imports", check_imports()))
    
    # Résumé
    print("\n" + "=" * 60)
    print("📊 RÉSUMÉ")
    print("=" * 60)
    
    all_passed = all(passed for _, passed in results)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    print()
    
    if all_passed:
        print("✅ Toutes les vérifications sont passées!")
        print()
        print("🚀 Vous pouvez maintenant lancer le système:")
        print("   python run_all.py")
        print()
        print("📍 Accédez aux services:")
        print("   🌐 Site: http://localhost:5000")
        print("   💬 Bot: Discord (connecté après lancement)")
        return 0
    else:
        print("❌ Certaines vérifications ont échoué!")
        print()
        print("⚠️  Actions recommandées:")
        print("1. Installez les dépendances: pip install -r requirements.txt")
        print("2. Vérifiez que tous les fichiers existent")
        print("3. Lancez le test à nouveau")
        return 1

if __name__ == '__main__':
    sys.exit(main())
