# 🚑 EMS Management System - Nouvelles Fonctionnalités

## ✨ Nouveautés Récentes

### 1. 🔗 **Système de Webhooks pour Résultats de Tests**

Vous pouvez maintenant intégrer les résultats de vos tests externes (quiz, évaluations, etc.) directement dans le site EMS.

#### Configuration

**Endpoint:** `http://votre-domaine.com/api/test-result/webhook`

**Méthode:** POST

**Paramètres requis:**
```json
{
  "secret": "changeme123",
  "employee": "mat-duja",
  "test_type": "écrit",
  "result": "passed",
  "score": 85
}
```

**Valeurs acceptées pour `result`:** `passed`, `failed`, `pending`

#### Exemple avec cURL
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

#### Exemple avec Python
```python
import requests

data = {
    "secret": "changeme123",
    "employee": "mat-duja",
    "test_type": "écrit",
    "result": "passed",
    "score": 85
}

response = requests.post('http://localhost:5000/api/test-result/webhook', json=data)
print(response.json())
```

---

### 2. 📋 **Commande Discord `/absence`**

Une nouvelle commande Discord permet de déclarer rapidement une absence depuis Discord.

#### Utilisation

```
/absence employee:mat-duja date:2024-12-25 raison:Congé
```

#### Paramètres

| Paramètre | Obligatoire | Description |
|-----------|-------------|-------------|
| `employee` | ✅ Oui | Nom de l'employé |
| `date` | ❌ Non | Date au format YYYY-MM-DD (par défaut: aujourd'hui) |
| `raison` | ❌ Non | Raison de l'absence |

#### Exemples

**Déclarer une absence pour aujourd'hui:**
```
/absence employee:mat-duja
```

**Déclarer une absence pour une date spécifique:**
```
/absence employee:mat-duja date:2024-12-25 raison:Congé payé
```

#### Réponse du bot

L'absence est enregistrée et le bot confirme avec un message ephémère:
- ✅ **Absence enregistrée**
- L'employé apparaît comme "Absent" sur le site
- Un log est créé dans le journal des webhooks

---

### 3. 🌐 **Site Web Amélioré**

#### Pages Disponibles

**Dashboard Principal:** `http://localhost:5000/`
- 📊 Graphique des réanimations en temps réel
- 👥 Liste de tous les employés avec leur statut
- 📈 Statistiques globales

**Gestion des Employés:** `http://localhost:5000/employees`
- 📋 Liste complète avec détails
- ➕ Ajouter/retirer des absences
- 📅 Historique des absences récentes
- 📊 Statut du quota de chacun

**Gestion des Webhooks:** `http://localhost:5000/webhooks`
- 🔐 Clé secrète webhook
- 📡 URLs des endpoints
- 📝 Exemples d'utilisation
- 📜 Journal des événements (derniers 50)
- 📊 Résumé des événements par type

---

## 🔧 Configuration

### Variables d'Environnement

Définissez la clé secrète des webhooks:

```env
WEBHOOK_SECRET=votre_clé_secrète_ici
```

**Défaut:** `changeme123` (à changer en production!)

### Fichiers de Données

Les nouvelles données sont stockées dans:
- `absences.json` - Enregistrement des absences
- `webhook_logs.json` - Journal des webhooks

---

## 📡 API Endpoints

### Récupérer les Absences
```
GET /api/absences
```

**Réponse:**
```json
{
  "mat-duja": ["2024-12-25", "2024-12-26"],
  "wilson-koffi": ["2024-12-25"]
}
```

### Ajouter une Absence
```
POST /api/absence/add
Content-Type: application/json

{
  "secret": "changeme123",
  "employee": "mat-duja",
  "date": "2024-12-25",
  "reason": "Congé"
}
```

### Retirer une Absence
```
POST /api/absence/remove
Content-Type: application/json

{
  "secret": "changeme123",
  "employee": "mat-duja",
  "date": "2024-12-25"
}
```

### Enregistrer un Résultat de Test
```
POST /api/test-result/webhook
Content-Type: application/json

{
  "secret": "changeme123",
  "employee": "mat-duja",
  "test_type": "écrit",
  "result": "passed",
  "score": 85
}
```

### Obtenir le Journal des Webhooks
```
GET /api/webhook/log
```

---

## 🚀 Démarrage

### Lancer tous les services

```bash
python run_all.py
```

Cela démarrera:
1. Le site Flask (port 5000)
2. Le bot Discord

### Lancer séparément

**Site Flask:**
```bash
python app.py
```

**Bot Discord:**
```bash
python main.py
```

---

## 🔍 Dépannage

### "Unauthorized" sur les webhooks
- Vérifiez que la clé secrète est correcte
- La variable `WEBHOOK_SECRET` doit être définie correctement

### Le site Flask ne démarre pas
- Vérifiez que le port 5000 n'est pas utilisé
- Installez les dépendances: `pip install -r requirements.txt`

### La commande `/absence` ne fonctionne pas
- Le site Flask doit être en cours d'exécution
- Vérifiez que `http://localhost:5000` est accessible
- Consultez les logs du bot pour plus de détails

### Les graphiques ne s'affichent pas
- Rechargez la page (F5)
- Vérifiez que des données de statistiques existent
- Consultez la console du navigateur pour les erreurs (F12)

---

## 📊 Architecture

```
emsssss/
├── main.py              # Bot Discord
├── app.py               # Site Flask
├── run_all.py           # Lanceur des deux services
├── requirements.txt     # Dépendances
├── stats.json          # Statistiques des réanimations
├── absences.json       # Absences enregistrées
├── webhook_logs.json   # Journal des webhooks
├── templates/          # Pages HTML
│   ├── dashboard.html
│   ├── employees.html
│   └── webhooks.html
└── static/            # Ressources statiques (CSS, JS, etc.)
```

---

## 🔐 Sécurité

⚠️ **IMPORTANT:** Changez la clé secrète webhook par défaut en production!

1. Définissez une clé forte dans les variables d'environnement:
```env
WEBHOOK_SECRET=aZ9xK2mL7pQ4wN6vR8sT1uY3jH5fG7dC
```

2. Utilisez HTTPS en production
3. Ne partagez jamais la clé secrète

---

## 📞 Support

En cas de problème:
1. Vérifiez les logs du bot (`main.py`) et du site (`app.py`)
2. Consultez le journal des webhooks dans `/webhooks`
3. Vérifiez que tous les services sont en cours d'exécution

---

**Dernière mise à jour:** 2024
**Version:** 2.0
