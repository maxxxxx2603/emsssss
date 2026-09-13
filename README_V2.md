# 🚑 EMS Management System - Version 2.0

Un système complet de gestion des ambulanciers avec intégration Discord et site web.

## ✨ Nouvelles Fonctionnalités (v2.0)

### 1. 🌐 **Site Web Flask**
- Dashboard interactif avec graphiques en temps réel
- Gestion des employés et absences
- Page de configuration des webhooks
- API REST complète

### 2. 🔗 **Webhooks pour Résultats de Tests**
- Endpoint `/api/test-result/webhook` pour enregistrer les résultats de tests
- Intégration avec des plateformes de test externes
- Logging automatique de tous les événements

### 3. 📋 **Commande Discord `/absence`**
- Déclarer une absence directement depuis Discord
- Intégration automatique avec le site web
- Validation et confirmation instantée

### 4. 📊 **Graphiques Corrigés**
- Graphiques interactifs Chart.js
- Graphiques statiques matplotlib
- Affichage des quotas avec code couleur (🔴🟠🟢)

---

## 🚀 Installation Rapide

### Windows (PowerShell)
```powershell
# Exécuter le script d'installation
.\install.ps1
```

### Linux/Mac (Bash)
```bash
# Installer les dépendances
pip install -r requirements.txt

# Vérifier la configuration
python test_setup.py

# Lancer les services
python run_all.py
```

### Manual
```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Vérifier le setup
python test_setup.py

# 3. Configurer (optionnel)
cp .env.example .env
# Éditer .env avec vos paramètres

# 4. Lancer tous les services
python run_all.py

# OU lancer séparément:
python app.py   # Site (port 5000)
python main.py  # Bot Discord
```

---

## 📍 Accès aux Services

Une fois lancé, accédez à:

- **🌐 Dashboard:** http://localhost:5000
- **👔 Gestion des Employés:** http://localhost:5000/employees
- **🔗 Gestion des Webhooks:** http://localhost:5000/webhooks
- **💬 Bot Discord:** @bot_name

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [NOUVELLES_FONCTIONNALITES.md](NOUVELLES_FONCTIONNALITES.md) | Guide complet des nouvelles features |
| [MODIFICATIONS.md](MODIFICATIONS.md) | Détail des changements implémentés |
| `.env.example` | Configuration exemple |

---

## 🎮 Utilisation

### Commande Discord
```
/absence employee:mat-duja date:2024-12-25 raison:Congé
```

### API Webhooks
```bash
curl -X POST http://localhost:5000/api/test-result/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "changeme123",
    "employee": "mat-duja",
    "test_type": "écrit",
    "result": "passed",
    "score": 85
  }'
```

### Site Web
- Dashboard: Voir en temps réel
- Employees: Gérer les absences
- Webhooks: Configurer et monitorer

---

## 🔧 Configuration

### Variables d'Environnement Principales

```env
# Bot Discord
TOKEN=votre_token_discord
GUILD_ID=votre_guild_id

# Sécurité (⚠️ À changer en production!)
WEBHOOK_SECRET=changeme123

# Site Flask
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

Voir `.env.example` pour la liste complète.

---

## 📁 Structure du Projet

```
emsssss/
├── 📄 main.py                      # Bot Discord
├── 🌐 app.py                       # Site Flask
├── 🚀 run_all.py                   # Lanceur unifié
├── 📋 requirements.txt             # Dépendances
├── 🧪 test_setup.py               # Vérification du setup
│
├── 📂 templates/                   # Pages HTML
│   ├── dashboard.html              # Dashboard principal
│   ├── employees.html              # Gestion employés
│   └── webhooks.html               # Gestion webhooks
│
├── 📂 static/                      # Ressources statiques
│
├── 📊 stats.json                   # Statistiques
├── 📋 absences.json               # Absences enregistrées
├── 🔗 webhook_logs.json           # Journal des webhooks
│
├── 📚 Documentation
│   ├── NOUVELLES_FONCTIONNALITES.md
│   ├── MODIFICATIONS.md
│   └── .env.example
│
└── 🔧 Scripts
    ├── run_all.py
    ├── test_setup.py
    └── install.ps1
```

---

## 🧪 Tests

Vérifier que le système est correctement configuré:

```bash
python test_setup.py
```

Le script vérifie:
- ✅ Présence des fichiers
- ✅ Syntaxe Python
- ✅ Validité des JSON
- ✅ Templates HTML
- ✅ Imports Python

---

## 🔐 Sécurité

⚠️ **IMPORTANT:**

1. **Changez la clé secrète** en production:
   ```env
   WEBHOOK_SECRET=votre_clé_très_secrète_ici
   ```

2. **Utilisez HTTPS** en production

3. **Ne partagez jamais** la clé secrète

4. **Limitez les accès** aux endpoints webhook

---

## 🐛 Dépannage

### Site Flask ne démarre pas
```bash
# Vérifier que le port 5000 est libre
netstat -ano | findstr :5000

# Changer le port dans run_all.py ou app.py
```

### Commande `/absence` ne fonctionne pas
```bash
# Vérifier que le site Flask est actif
curl http://localhost:5000

# Vérifier les logs du bot
```

### Graphiques ne s'affichent pas
```bash
# Rafraîchir la page (Ctrl+F5)
# Vérifier qu'il existe des données de stats
# Ouvrir la console (F12) pour voir les erreurs
```

### Erreur "Unauthorized" sur les webhooks
```bash
# Vérifier la clé secrète dans les requêtes
# Comparer avec WEBHOOK_SECRET dans les variables d'environnement
```

---

## 📞 Support

Pour toute question:

1. Consultez la documentation: `NOUVELLES_FONCTIONNALITES.md`
2. Vérifiez les logs: Console du terminal
3. Lancez le test: `python test_setup.py`
4. Assurez-vous que tous les services sont actifs

---

## 📦 Dépendances

```
discord.py>=2.3.0       # Bot Discord
python-dotenv>=1.0.0    # Variables d'environnement
aiohttp>=3.9.0          # Requêtes HTTP async
flask>=2.3.0            # Framework web
pandas>=1.5.0           # Analyse de données
matplotlib>=3.7.0       # Graphiques
gunicorn>=21.0.0        # Serveur WSGI (production)
```

Installez avec:
```bash
pip install -r requirements.txt
```

---

## 🎯 Prochaines Étapes

1. ✅ Installation
2. ✅ Configuration (.env)
3. ✅ Lancement (run_all.py)
4. ✅ Test des features
5. ✅ Déploiement en production (Railway, Heroku, etc.)

---

## 📝 Changelog

### v2.0 (Actuelle)
- ✨ Site web Flask complet
- ✨ Commande Discord `/absence`
- ✨ Webhooks pour résultats de tests
- ✨ Graphiques interactifs
- ✨ API REST complète
- ✨ Gestion des absences
- ✨ Documentation complète

### v1.0
- Bot Discord basique
- Gestion des réanimations
- Système de catégories

---

## 🙏 Crédits

- Système de gestion EMS
- Intégration Discord.py
- Framework Flask
- Chart.js pour les graphiques

---

**Dernière mise à jour:** 2024
**Statut:** ✅ Prêt pour la production
**License:** À définir

---

### ❓ Des questions?

Consultez les fichiers de documentation:
- [NOUVELLES_FONCTIONNALITES.md](NOUVELLES_FONCTIONNALITES.md) - Guide détaillé
- [MODIFICATIONS.md](MODIFICATIONS.md) - Changements implémentés
- [.env.example](.env.example) - Configuration

**Bonne chance! 🚑**
