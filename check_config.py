"""
Script de vérification de la configuration du bot EMS
"""
import json
import os

def check_config():
    print("🔍 Vérification de la configuration...\n")
    
    # Vérifier l'existence de config.json
    if not os.path.exists('config.json'):
        print("❌ ERREUR : Le fichier config.json n'existe pas !")
        return False
    
    # Charger la configuration
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print("❌ ERREUR : Le fichier config.json n'est pas un JSON valide !")
        return False
    
    # Vérifier les clés requises
    required_keys = [
        "TOKEN",
        "GUILD_ID",
        "LOGS_CHANNEL_ID",
        "CV_CHANNEL_ID",
        "DEPOT_CV_CHANNEL_ID",
        "ROLE_ATTENTE_ID",
        "DISPO_CHANNEL_ID"
    ]
    
    missing_keys = []
    for key in required_keys:
        if key not in config:
            missing_keys.append(key)
    
    if missing_keys:
        print(f"❌ ERREUR : Clés manquantes dans config.json : {', '.join(missing_keys)}")
        return False
    
    print("✅ Toutes les clés requises sont présentes\n")
    
    # Vérifier les valeurs
    warnings = []
    
    if config["TOKEN"] == "TON_TOKEN_DE_BOT_ICI":
        warnings.append("⚠️  TOKEN : Vous devez remplacer 'TON_TOKEN_DE_BOT_ICI' par votre vrai token")
    elif config["TOKEN"]:
        print("✅ TOKEN configuré")
    
    if config["GUILD_ID"] == 838102445083197470:
        print("✅ GUILD_ID configuré")
    
    if config["LOGS_CHANNEL_ID"] == 0:
        warnings.append("⚠️  LOGS_CHANNEL_ID : Valeur à 0, pensez à mettre l'ID du salon logs")
    else:
        print(f"✅ LOGS_CHANNEL_ID configuré : {config['LOGS_CHANNEL_ID']}")
    
    if config["CV_CHANNEL_ID"] == 0:
        warnings.append("⚠️  CV_CHANNEL_ID : Valeur à 0, pensez à mettre l'ID du salon CV")
    else:
        print(f"✅ CV_CHANNEL_ID configuré : {config['CV_CHANNEL_ID']}")
    
    if config["DEPOT_CV_CHANNEL_ID"] == 0:
        warnings.append("⚠️  DEPOT_CV_CHANNEL_ID : Valeur à 0, pensez à mettre l'ID du salon dépôt")
    else:
        print(f"✅ DEPOT_CV_CHANNEL_ID configuré : {config['DEPOT_CV_CHANNEL_ID']}")
    
    if config["ROLE_ATTENTE_ID"] == 896103247096471613:
        print("✅ ROLE_ATTENTE_ID configuré")
    
    if config["DISPO_CHANNEL_ID"] == 1451553241065193555:
        print("✅ DISPO_CHANNEL_ID configuré")
    
    print()
    
    # Afficher les avertissements
    if warnings:
        print("⚠️  AVERTISSEMENTS :")
        for warning in warnings:
            print(f"   {warning}")
        print("\n📋 Le bot peut ne pas fonctionner correctement tant que ces valeurs ne sont pas configurées.\n")
        return False
    
    print("✅ Configuration valide ! Le bot peut être lancé.\n")
    print("💡 Commandes pour lancer le bot :")
    print("   - Windows : start.bat")
    print("   - Ou : python main.py")
    return True

if __name__ == "__main__":
    check_config()
    input("\nAppuyez sur Entrée pour fermer...")
