#!/usr/bin/env python3
"""
Script pour démarrer le bot Discord et le site Flask simultanément
"""

import subprocess
import sys
import time
import os
from pathlib import Path

def main():
    print("🚀 Démarrage du système EMS Management...")
    print("-" * 50)
    
    # Vérifier que les fichiers existent
    required_files = ['main.py', 'app.py', 'requirements.txt']
    for file in required_files:
        if not Path(file).exists():
            print(f"❌ Erreur: {file} introuvable!")
            return 1
    
    # Installation des dépendances
    print("📦 Vérification des dépendances...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '-q'])
        print("✅ Dépendances OK")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Erreur lors de l'installation des dépendances: {e}")
        return 1
    
    print("-" * 50)
    print("🚀 Lancement des services...")
    print()
    
    # Lancer le site Flask en arrière-plan
    print("🌐 Démarrage du site Flask... (port 5000)")
    flask_process = subprocess.Popen([sys.executable, 'app.py'])
    time.sleep(2)  # Attendre que Flask se lance
    
    # Lancer le bot Discord
    print("🤖 Démarrage du bot Discord...")
    discord_process = subprocess.Popen([sys.executable, 'main.py'])
    
    print()
    print("✅ Tous les services sont lancés!")
    print("-" * 50)
    print("📍 Site Flask: http://localhost:5000")
    print("💬 Bot Discord: Connecté")
    print("-" * 50)
    print()
    print("⚠️  Appuyez sur Ctrl+C pour arrêter tous les services")
    print()
    
    try:
        # Attendre que les deux processus se terminent
        flask_process.wait()
        discord_process.wait()
    except KeyboardInterrupt:
        print()
        print("⏹️ Arrêt des services...")
        print("💾 Sauvegarde des données...")
        
        # Terminer proprement les processus
        try:
            discord_process.terminate()
            discord_process.wait(timeout=5)
        except:
            discord_process.kill()
        
        try:
            flask_process.terminate()
            flask_process.wait(timeout=5)
        except:
            flask_process.kill()
        
        print("✅ Arrêt complet")
        return 0
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
