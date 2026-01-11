# EMS Bot - Discord Bot pour Entreprise EMS

## ⚙️ Installation

### 1. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 2. Configurer le bot

Ouvre `config.json` et remplace les valeurs :

```json
{
    "TOKEN": "TON_TOKEN_DISCORD_ICI",
    "GUILD_ID": 838102445083197470,
    "LOGS_CHANNEL_ID": 123456789,
    "CV_CHANNEL_ID": 123456789,
    "DEPOT_CV_CHANNEL_ID": 123456789,
    "ROLE_ATTENTE_ID": 896103247096471613,
    "DISPO_CHANNEL_ID": 1451553241065193555
}
```

**Où trouver ces IDs :**
- **TOKEN** : Dans les paramètres du bot sur Discord Developer Portal
- **GUILD_ID** : ID de ton serveur Discord
- **LOGS_CHANNEL_ID** : ID du channel où les logs apparaissent
- **CV_CHANNEL_ID** : ID du channel où les CVs sont validés
- **DEPOT_CV_CHANNEL_ID** : ID du channel où les utilisateurs cliquent le bouton
- **ROLE_ATTENTE_ID** : ID du rôle "Attente d'entretien"
- **DISPO_CHANNEL_ID** : ID du channel des disponibilités

### 3. Lancer le bot
```bash
python main.py
```

## 🎯 Fonctionnalités

### 1️⃣ Système de Boules (Comptage d'Images)
- L'utilisateur envoie une image avec le message `rouge`, `orange` ou `verte`
- Le bot ajoute automatiquement la réaction 🔴 🟠 🟢
- Un log est envoyé dans le channel logs

### 2️⃣ Commandes Admin
- `/total` → Affiche les statistiques (rouge, orange, verte)
- `/reset` → Remet les compteurs à 0

### 3️⃣ Système de Recrutement CV
- L'utilisateur clique sur le bouton "Dépose ton CV" dans le channel dédié
- Un channel privé se crée
- Le bot pose 4 questions (nom, âge, expérience, disponibilités)
- Les réponses sont envoyées dans le channel CV
- Admin peut accepter ou refuser :
  - **Accepter** → MP + ajout du rôle + message positif
  - **Refuser** → MP avec message de refus

## ⚙️ Permissions Requises

Le bot doit avoir les permissions :
- ✅ Gérer les canaux (Manage Channels)
- ✅ Gérer les rôles (Manage Roles)
- ✅ Envoyer des messages (Send Messages)
- ✅ Ajouter des réactions (Add Reactions)
- ✅ Lire l'historique des messages (Read Message History)

## 🔧 Permissions du Bot sur le Serveur

Le rôle du bot doit être placé **au-dessus** du rôle "Attente d'entretien" dans la hiérarchie des rôles Discord.

## 📝 Notes

- Les CVs sont sauvegardés dans le channel CV avec les réactions d'acceptation/refus
- Les compteurs sont sauvegardés dans `stats.json`
- Chaque utilisateur ne peut avoir qu'un seul ticket CV ouvert à la fois
- Timeout des questions : 10 minutes

Bon recrutement ! 🚀
