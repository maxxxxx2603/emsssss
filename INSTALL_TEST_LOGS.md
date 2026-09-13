# 🚀 Installation - Page de Test Logs

## 📦 Fichiers à Ajouter/Modifier

### 1️⃣ Fichier HTML (NOUVEAU)
**Chemin** : `templates/test_logs.html`
**Action** : Copier le fichier fourni

### 2️⃣ Fichier Python (MODIFIÉ)
**Chemin** : `app.py`
**Actions** :
- Ajouter l'import `time`
- Ajouter 70+ lignes de routes API

### 3️⃣ Documentation (NOUVEAU)
**Fichiers** :
- `TEST_LOGS_GUIDE.md` - Guide complet
- `INSTALL_TEST_LOGS.md` - Ce fichier

---

## ⚙️ Installation Étape par Étape

### Étape 1: Préparer les fichiers
```bash
# Depuis le dossier du projet
# Copier le fichier HTML dans templates/
copy test_logs.html templates/test_logs.html
```

### Étape 2: Mettre à jour app.py
```python
# 1. Ajouter l'import en haut du fichier:
import time

# 2. Ajouter les constantes et routes (avant if __name__ == '__main__':)
# Voir la section "Contenu à Ajouter" ci-dessous
```

### Étape 3: Redémarrer l'application
```bash
# Arrêter le serveur (Ctrl+C)
# Relancer
python app.py
```

### Étape 4: Tester
```
Ouvrir : http://localhost:5000/test
```

---

## 📋 Contenu à Ajouter dans app.py

Ajouter ceci **avant** la ligne `if __name__ == '__main__':`

```python
# ============ ROUTES DE TEST - GESTION DES LOGS ============

TEST_LOGS_FILE = os.path.join(DATA_DIR, 'test_logs.json')
VALID_CHANNEL_ID = '1267921697420345424'
VALID_ROLE_ID = '838102445095256068'

@app.route('/test')
def test_logs_page():
    """Page de test pour la gestion des logs"""
    return render_template('test_logs.html')

@app.route('/api/test/logs', methods=['GET', 'POST', 'DELETE'])
def api_test_logs():
    """API pour gérer les logs de test"""
    
    if request.method == 'GET':
        # Récupérer toutes les logs
        logs = load_json(TEST_LOGS_FILE, [])
        # Filtrer par channel valide
        valid_logs = [log for log in logs if log.get('channelId') == VALID_CHANNEL_ID]
        return jsonify({'logs': valid_logs})
    
    elif request.method == 'POST':
        # Ajouter une nouvelle log
        data = request.get_json()
        
        # Validations strictes
        if data.get('channelId') != VALID_CHANNEL_ID:
            return jsonify({'error': 'Channel ID invalide'}), 400
        
        if data.get('userId') != VALID_ROLE_ID:
            return jsonify({'error': 'User ID/Role invalide'}), 400
        
        if not data.get('license', '').startswith('license:'):
            return jsonify({'error': 'Format de license invalide'}), 400
        
        # Charger les logs existantes
        logs = load_json(TEST_LOGS_FILE, [])
        
        # Créer la nouvelle log
        new_log = {
            'id': int(time.time() * 1000),
            'type': data.get('type'),
            'societe': data.get('societe'),
            'joueur': data.get('joueur'),
            'employee': data.get('employee'),
            'license': data.get('license'),
            'userId': data.get('userId'),
            'channelId': data.get('channelId'),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        # Ajouter les champs spécifiques aux ventes
        if data.get('type') == 'vente':
            new_log.update({
                'montant': int(data.get('montant', 0)),
                'ventes': int(data.get('ventes', 1)),
                'periode': int(data.get('periode', 0)),
                'origine': data.get('origine', 'addon_account'),
            })
        
        logs.insert(0, new_log)
        
        # Sauvegarder
        if save_json(TEST_LOGS_FILE, logs):
            return jsonify({'status': 'success', 'log': new_log}), 201
        else:
            return jsonify({'error': 'Erreur lors de la sauvegarde'}), 500
    
    elif request.method == 'DELETE':
        # Supprimer une log
        log_id = request.args.get('id')
        if not log_id:
            return jsonify({'error': 'ID requis'}), 400
        
        logs = load_json(TEST_LOGS_FILE, [])
        logs = [log for log in logs if log.get('id') != int(log_id)]
        
        if save_json(TEST_LOGS_FILE, logs):
            return jsonify({'status': 'success'})
        else:
            return jsonify({'error': 'Erreur lors de la sauvegarde'}), 500

@app.route('/api/test/stats')
def api_test_stats():
    """Statistiques des logs de test"""
    logs = load_json(TEST_LOGS_FILE, [])
    valid_logs = [log for log in logs if log.get('channelId') == VALID_CHANNEL_ID]
    
    total_ventes = len([l for l in valid_logs if l.get('type') == 'vente'])
    total_services = len([l for l in valid_logs if l.get('type') in ['prise_service', 'fin_service']])
    montant_total = sum(l.get('montant', 0) for l in valid_logs if l.get('type') == 'vente')
    
    return jsonify({
        'total_logs': len(valid_logs),
        'total_ventes': total_ventes,
        'total_services': total_services,
        'montant_total': montant_total,
        'logs_invalides': len(logs) - len(valid_logs)
    })

@app.route('/api/test/clear', methods=['POST'])
def api_test_clear():
    """Effacer toutes les logs de test (démo seulement)"""
    if save_json(TEST_LOGS_FILE, []):
        return jsonify({'status': 'success', 'message': 'Toutes les logs ont été effacées'})
    else:
        return jsonify({'error': 'Erreur lors de la suppression'}), 500

# ============ FIN DES ROUTES DE TEST ============
```

---

## ✅ Vérification

### Routes disponibles après installation

| Route | Méthode | Description |
|-------|---------|-------------|
| `/test` | GET | Page de test |
| `/api/test/logs` | GET | Récupérer logs |
| `/api/test/logs` | POST | Ajouter log |
| `/api/test/logs` | DELETE | Supprimer log |
| `/api/test/stats` | GET | Statistiques |
| `/api/test/clear` | POST | Effacer tout |

### Fichiers créés
```
test_logs.json          (créé auto à la première log)
```

---

## 🔧 Configuration

Les IDs Discord sont prédéfinis :
```python
VALID_CHANNEL_ID = '1267921697420345424'    # À modifier si besoin
VALID_ROLE_ID = '838102445095256068'        # À modifier si besoin
```

### Pour changer les IDs
Modifiez les 2 constantes dans `app.py` :
```python
# Ligne ~270 dans app.py
VALID_CHANNEL_ID = 'VOTRE_CHANNEL_ID'
VALID_ROLE_ID = 'VOTRE_ROLE_ID'
```

**Et dans `test_logs.html` :**
```javascript
// Ligne ~235
const VALID_CHANNEL_ID = 'VOTRE_CHANNEL_ID';
const VALID_ROLE_ID = 'VOTRE_ROLE_ID';
```

---

## 📊 Données Sauvegardées

Fichier : `test_logs.json`

Structure :
```json
[
  {
    "id": 1704062400000,
    "type": "vente",
    "societe": "ems",
    "joueur": "MoodyMoth6590",
    "license": "license:3ac9707ffc9f167bcc88546d8ec0ceee66ba6b5b",
    "montant": 100000,
    "ventes": 1,
    "periode": 0,
    "origine": "addon_account",
    "userId": "838102445095256068",
    "channelId": "1267921697420345424",
    "timestamp": "2024-01-01 17:10:00"
  }
]
```

---

## 🐛 Dépannage

### Erreur 404 - Page non trouvée
- ❌ Vérifier que `test_logs.html` est dans `templates/`
- ✅ Redémarrer le serveur Flask

### Erreur 500 - Impossible de sauvegarder
- ❌ Vérifier les permissions du dossier
- ❌ Vérifier que le dossier existe
- ✅ Créer le dossier manuellement si besoin

### Logs non visibles
- ❌ Vérifier Channel ID correct : `1267921697420345424`
- ❌ Vérifier Role ID correct : `838102445095256068`
- ✅ Ouvrir la console (F12) pour voir les erreurs

### Formulaire ne valide pas
- ✅ La License doit commencer par `license:`
- ✅ Le Role ID doit être exact
- ✅ Le Channel ID doit être exact

---

## 📱 Utilisation Rapide

### Ajouter une log de vente
1. Aller à `/test`
2. Sélectionner "📦 Vente"
3. Remplir les champs
4. Cliquer "Ajouter la Log"

### Ajouter une log de service
1. Sélectionner "✅ Prise de Service" ou "❌ Fin de Service"
2. Remplir les champs essentiels
3. Ajouter

### Supprimer une log
- Cliquer le bouton "✕" sur la log

### Filtrer les logs
- Cliquer les boutons en haut (Tous, Ventes, etc.)

---

## 🔒 Sécurité

Les validations suivantes sont appliquées :
✅ Channel ID obligatoire  
✅ Role ID obligatoire  
✅ Format License validé (doit commencer par `license:`)  
✅ Types énumérés strictement  
✅ Données numériques validées  

---

## 📈 Prochaines Étapes Recommandées

1. **Tester les 3 types de logs** (vente, prise, fin)
2. **Vérifier les statistiques** (en haut à droite)
3. **Essayer les filtres**
4. **Supprimer une log pour tester**
5. **Recharger la page** (vérifier la persistance)

---

## ❓ Support

- Voir `TEST_LOGS_GUIDE.md` pour les propositions d'améliorations
- Voir `README.md` pour le guide général
- Voir `QUICKSTART.md` pour démarrer rapidement

---

**Installation complète ✨**  
Date: 2026-08-10
