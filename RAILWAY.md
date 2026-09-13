# 🚀 Déploiement sur Railway

## Étapes à suivre :

### 1️⃣ Créer un dépôt GitHub
```bash
git init
git add .
git commit -m "Initial commit - EMS Bot"
git branch -M main
git remote add origin https://github.com/TON_USERNAME/ems-bot.git
git push -u origin main
```

### 2️⃣ Déployer sur Railway
1. Va sur [railway.app](https://railway.app)
2. Connecte-toi avec GitHub
3. Clique sur "New Project"
4. Sélectionne "Deploy from GitHub repo"
5. Choisis ton repo `ems-bot`

### 3️⃣ Configurer les variables d'environnement

Dans Railway → Ton projet → Variables → Ajoute ces variables :

```
TOKEN=TON_TOKEN_DISCORD_ICI
GUILD_ID=838102445083197470
LOGS_CHANNEL_ID=1458464678542970983
CV_CHANNEL_ID=1458464247548743691
DEPOT_CV_CHANNEL_ID=1346609766570659860
ROLE_ATTENTE_ID=896103247096471613
DISPO_CHANNEL_ID=1451553241065193555
ROLE_DIRECTION_ID=838120186585940010
```

### 4️⃣ Déploiement automatique
Railway va automatiquement :
- Installer les dépendances depuis `requirements.txt`
- Lancer le bot avec `python main.py`
- Redémarrer automatiquement en cas d'erreur

### 5️⃣ Vérifier les logs
Dans Railway → Deployments → Logs
Tu devrais voir :
```
✅ Bot: EMS#4616
📊 Stats: {...}
```

## ✅ Fichiers préparés pour Railway :
- ✅ `Procfile` - Commande de démarrage
- ✅ `railway.json` - Configuration Railway
- ✅ `main.py` - Modifié pour supporter les variables d'environnement
- ✅ `.gitignore` - Fichiers à ignorer (config.json, stats.json)

## 📝 Notes importantes :
- Le bot fonctionnera localement avec `config.json`
- Sur Railway, il utilisera les variables d'environnement
- `stats.json` sera recréé automatiquement sur Railway
- Le bot redémarrera automatiquement en cas d'erreur (max 10 fois)

## 🔄 Pour mettre à jour le bot :
```bash
git add .
git commit -m "Update bot"
git push
```
Railway redéploiera automatiquement !
