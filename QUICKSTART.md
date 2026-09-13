# 🚀 DÉMARRAGE RAPIDE - EMS Management System v2.0

## ⚡ Commandes d'Installation (3 étapes)

### Étape 1: Installer les dépendances
```bash
pip install -r requirements.txt
```

### Étape 2: Vérifier le setup
```bash
python test_setup.py
```

### Étape 3: Lancer le système
```bash
python run_all.py
```

**Voilà!** ✅ Tous les services sont maintenant actifs.

---

## 🌐 Accès Immédiat

| Service | URL/Accès |
|---------|-----------|
| 📊 Dashboard | http://localhost:5000 |
| 👔 Employés | http://localhost:5000/employees |
| 🔗 Webhooks | http://localhost:5000/webhooks |
| 🤖 Discord Bot | Connecté automatiquement |

---

## 📝 Utilisation Immédiate

### Discord: Déclarer une absence
```
/absence employee:mat-duja date:2024-12-25 raison:Congé
```

### API: Envoyer un résultat de test
```bash
curl -X POST http://localhost:5000/api/test-result/webhook \
  -H "Content-Type: application/json" \
  -d '{"secret":"changeme123","employee":"mat-duja","test_type":"écrit","result":"passed","score":85}'
```

### Site: Gérer les absences
1. Allez sur http://localhost:5000/employees
2. Cliquez "Ajouter absence" pour un employé
3. Sélectionnez la date et cliquez "Ajouter"

---

## 🎯 Configuration (Optionnel)

Si vous avez une clé secrète personnalisée, éditez `.env`:

```bash
cp .env.example .env
# Puis modifiez WEBHOOK_SECRET
```

---

## 📊 Fichiers Créés

**Nouveaux fichiers:**
- ✨ `app.py` - Site Flask (12 KB)
- ✨ `templates/dashboard.html` - Dashboard (11 KB)
- ✨ `templates/employees.html` - Gestion employés (13 KB)
- ✨ `templates/webhooks.html` - Configuration webhooks (10 KB)
- ✨ `absences.json` - Base de données absences
- ✨ `webhook_logs.json` - Logs des webhooks
- ✨ `run_all.py` - Lanceur unifié (2.4 KB)
- ✨ `test_setup.py` - Tests de configuration (5.4 KB)
- ✨ `.env.example` - Configuration exemple
- ✨ `NOUVELLES_FONCTIONNALITES.md` - Documentation complète
- ✨ `README_V2.md` - Guide d'utilisation
- ✨ `MODIFICATIONS.md` - Détail des changements

**Modifiés:**
- 📝 `main.py` - Ajout commande `/absence`
- 📝 `requirements.txt` - Ajout dépendances Flask, pandas, matplotlib

---

## ✅ Ce Qui A Été Implémenté

### 1️⃣ Site Web (app.py)
- ✅ Dashboard avec graphiques Chart.js
- ✅ Gestion des employés et absences
- ✅ Page de configuration des webhooks
- ✅ API REST complète
- ✅ Système de logging

### 2️⃣ Commande Discord (/absence)
- ✅ Déclarer absence depuis Discord
- ✅ Intégration automatique avec le site
- ✅ Validation et confirmation
- ✅ Support des dates personalisées

### 3️⃣ Webhooks pour Tests
- ✅ Endpoint `/api/test-result/webhook`
- ✅ Enregistrement des résultats de tests
- ✅ Logging automatique
- ✅ Consultation via le site

### 4️⃣ Graphiques Réparés
- ✅ Graphiques interactifs (Chart.js)
- ✅ Code couleur automatique (🔴🟠🟢)
- ✅ Graphiques statiques (matplotlib)
- ✅ Rafraîchissement toutes les 30 sec

---

## 🔗 Intégrations Prêtes

### Avec des Tests Externes
```json
POST /api/test-result/webhook
{
  "secret": "changeme123",
  "employee": "mat-duja",
  "test_type": "écrit",
  "result": "passed",
  "score": 85
}
```

### Avec Discord
```
/absence employee:nom date:YYYY-MM-DD raison:texte
```

### Avec le Site
- Dashboard: Voir en temps réel
- Employés: Gérer manuellement
- Webhooks: Monitorer les événements

---

## 🚨 En Cas de Problème

### Le site ne démarre pas
```bash
# Port déjà utilisé? Changez le port
python -m flask run --port 5001
```

### Erreur "Unauthorized" sur les webhooks
```bash
# Vérifiez la clé secrète dans vos requêtes
# Elle doit correspondre à WEBHOOK_SECRET
```

### Graphiques vides
```bash
# Assurez-vous qu'il y a des données dans stats.json
# Rafraîchissez la page (Ctrl+F5)
```

### Bot ne démarre pas
```bash
# Vérifiez que TOKEN est défini
# Vérifiez les logs pour les erreurs
```

---

## 📚 Pour Aller Plus Loin

Consultez les fichiers de documentation:
- **NOUVELLES_FONCTIONNALITES.md** - Guide complet et exemples
- **README_V2.md** - Manuel utilisateur complet
- **MODIFICATIONS.md** - Détail technique des changements

---

## 🎉 Vous êtes Prêt!

Tout est configuré et prêt à l'emploi. 

**Lancez simplement:**
```bash
python run_all.py
```

Et accédez aux services! 🚀

---

**Temps d'installation:** ~2-3 minutes
**Dépendances:** 7 packages (Flask, pandas, matplotlib, discord.py, aiohttp, etc.)
**Espace disque:** ~50 MB
**Ports utilisés:** 5000 (Flask), Discord WebSocket

Bon travail! 🎉
