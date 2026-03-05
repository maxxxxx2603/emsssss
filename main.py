import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
import aiohttp
import io
from datetime import datetime, timedelta

# --- CONFIGURATION ---
# Support à la fois config.json (local) et variables d'environnement (Railway)
if os.path.exists('config.json'):
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
else:
    config = {
        "TOKEN": os.environ.get("TOKEN"),
        "GUILD_ID": int(os.environ.get("GUILD_ID", 0)),
        "LOGS_CHANNEL_ID": int(os.environ.get("LOGS_CHANNEL_ID", 0)),
        "CV_CHANNEL_ID": int(os.environ.get("CV_CHANNEL_ID", 0)),
        "CV_ACCEPTED_LOG_CHANNEL_ID": int(os.environ.get("CV_ACCEPTED_LOG_CHANNEL_ID", 0)),
        "DEPOT_CV_CHANNEL_ID": int(os.environ.get("DEPOT_CV_CHANNEL_ID", 0)),
        "ROLE_ATTENTE_ID": int(os.environ.get("ROLE_ATTENTE_ID", 0)),
        "DISPO_CHANNEL_ID": int(os.environ.get("DISPO_CHANNEL_ID", 0)),
        "ROLE_DIRECTION_ID": int(os.environ.get("ROLE_DIRECTION_ID", 0))
    }

STATS_FILE = 'stats.json'
TAXI_STATS_FILE = 'taxi_stats.json'
CHANNEL_MAP_FILE = 'channel_map.json'
CATEGORIES_FILE = 'categories.json'
BONUSES_WEEK_FILE = 'bonuses_week.json'

# Configuration Taxi
TAXI_CHANNEL_ID = 1457304629456011264
TAXI_ROLE_ID = 1163206112355561472
ROLE_DIRECTION_EMS_ID = 838120186585940010
ROLE_DIRECTION_TAXI_ID = 1311787019546136596

# Configuration BurgerShot
BURGERSHOT_CHANNEL_ID = 1462099226166165588
BURGERSHOT_ROLE_ID = 1462097148995965041
BURGERSHOT_STATS_FILE = 'burgershot_stats.json'

# Configuration Tickets
ROLE_REQUEST_CHANNEL_ID = 1450938023033176247
APPOINTMENT_CHANNEL_ID = 1415783172163244132
TICKET_CATEGORY_ID = 840364236189335553
ROLE_LSPD_ID = 1070687458825601115
ROLE_BCSO_ID = 1070374792450027560
ROLE_MARSHALL_ID = 1365068483074855045
ROLE_NO_TEST_ID = 1163524216688230591
ROLE_TAXI_REQUEST_ID = 1311784189984505876

# Configuration Reset
ROLE_BASE_ID = 838102445095256066  # Rôle de base à conserver
RESET_CHANNEL_ID = 1450938023033176247

# Configuration Leaderboard
LEADERBOARD_CHANNEL_ID = 1018904202971459644
LEADERBOARD_ROLE_ID = 838102445095256068

# Configuration Avis
AVIS_CHANNEL_ID = 1478910608228487255
CITOYEN_ROLE_ID = 838102445095256066

# Configuration Dispo
DISPO_REQUEST_CHANNEL_ID = 1478916243858915591  # Canal pour les demandes initiales
DISPO_CHANNEL_ID = 1478912686069780602  # Canal pour les décisions de recrutement
DISPO_CONFIRMATION_ROLE_ID = 896103247096471613
DIRECTION_ROLE_ID = 838120186585940010  # Rôle direction pour validation dispo et recrutement
ROLE_PENDING_ID = 896103247096471613
ROLE_EMT_1 = 838102445095256070
ROLE_EMT_2 = 838102445095256068
ROLE_EMT_3 = 895047492784238652
ROLE_CITOYEN = 838102445095256068

# Configuration Giveaway
GIVEAWAY_PING_ROLE_ID = 838102445095256068  # Rôle à ping pour les giveaways
GIVEAWAY_FILE = 'giveaways.json'

# --- FONCTIONS UTILITAIRES JSON ---
def atomic_write_json(path: str, data: dict, make_backup: bool = True):
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # Ecrire/mettre à jour une sauvegarde simple
        if make_backup:
            try:
                with open(f"{path}.bak", 'w', encoding='utf-8') as bf:
                    json.dump(data, bf, ensure_ascii=False, indent=2)
            except:
                pass
        os.replace(tmp_path, path)
    except Exception:
        # Nettoyage tmp si besoin
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except:
            pass
        raise

def robust_load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                raise ValueError("empty")
            return json.loads(content)
    except:
        # Essayer la sauvegarde .bak
        bak = f"{path}.bak"
        if os.path.exists(bak):
            try:
                with open(bak, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return json.loads(content)
            except:
                pass
        return default

# Fonction pour charger les catégories
def load_categories():
    default = {
        "CATEGORY_EMT_ID": 0,
        "CATEGORY_INT_ID": 0,
        "CATEGORY_ADS_ID": 0,
        "CATEGORY_INF_ID": 0,
        "CATEGORY_MED_ID": 0,
        "CATEGORY_CDS_ID": 0,
        "CATEGORY_DIR_ID": 0
    }
    return robust_load_json(CATEGORIES_FILE, default)

def save_categories(cats):
    atomic_write_json(CATEGORIES_FILE, cats)

# Charger les catégories au démarrage
categories = load_categories()
CATEGORY_EMT_ID = categories.get("CATEGORY_EMT_ID", 0)
CATEGORY_INT_ID = categories.get("CATEGORY_INT_ID", 0)
CATEGORY_ADS_ID = categories.get("CATEGORY_ADS_ID", 0)
CATEGORY_INF_ID = categories.get("CATEGORY_INF_ID", 0)
CATEGORY_MED_ID = categories.get("CATEGORY_MED_ID", 0)
CATEGORY_CDS_ID = categories.get("CATEGORY_CDS_ID", 0)
CATEGORY_DIR_ID = categories.get("CATEGORY_DIR_ID", 0)

# Cooldown pour réactions
processed_reactions = set()

# --- COULEURS EMS ---
EMS_RED = discord.Color.from_rgb(220, 20, 60)
EMS_DARK_RED = discord.Color.from_rgb(178, 34, 52)

# --- SETUP BOT ---
class EMSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(CVButton())
        # self.add_view(FormulaireCVButton())  # Désactivé - on utilise l'ancien système
        self.add_view(RoleRequestButton())
        self.add_view(AppointmentButton())
        self.add_view(ResetMemberButton())
        # Démarrer les tâches automatisées
        weekly_taxi_announcement.start()
        check_giveaways.start()

bot = EMSBot()

# --- GESTION DES STATS ---
def load_stats():
    # Données par défaut (16 employés) - doit correspondre à stats.json
    DEFAULT_STATS = {
        "mat-duja": 155,
        "wilson-koffi": 134,
        "marc-zenter": 59,
        "balake-andrew": 48,
        "max-ferdinand": 43,
        "jorghen-monteiro-mbombo": 80,
        "thomas-bult": 37,
        "mouloud-pembele": 15,
        "jason-trigo": 14,
        "farid-lamatraque": 7,
        "mehmet-momo": 5,
        "melano-montasart": 5,
        "imran-meknessi": 4,
        "alvaro-benz": 3,
        "jean-dan": 3,
        "labigne-evan": 1
    }
    
    if not os.path.exists(STATS_FILE):
        # Fichier n'existe pas - créer avec les données par défaut
        atomic_write_json(STATS_FILE, DEFAULT_STATS)
        return DEFAULT_STATS
    
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            data = f.read().strip()
            if not data:
                # Fichier vide - créer avec les données par défaut
                atomic_write_json(STATS_FILE, DEFAULT_STATS)
                return DEFAULT_STATS
            loaded = json.loads(data)
            # Si le fichier est vide (dict vide), utiliser par défaut
            if not loaded:
                atomic_write_json(STATS_FILE, DEFAULT_STATS)
                return DEFAULT_STATS
            return loaded
    except:
        # Erreur de parsing - utiliser par défaut
        atomic_write_json(STATS_FILE, DEFAULT_STATS)
        return DEFAULT_STATS

def save_stats(stats):
    atomic_write_json(STATS_FILE, stats)

# --- GESTION DES BONUSES CUMULATIFS PAR SEMAINE ---
def get_week_start():
    """Retourne la date du lundi de cette semaine"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")

def load_bonuses_week():
    """Charge les bonuses cumulatifs de cette semaine"""
    default = {}
    if not os.path.exists(BONUSES_WEEK_FILE):
        return default
    return robust_load_json(BONUSES_WEEK_FILE, default)

def save_bonuses_week(bonuses):
    """Sauvegarde les bonuses cumulatifs"""
    atomic_write_json(BONUSES_WEEK_FILE, bonuses)

def get_week_bonus_count(employee_key):
    """Retourne le nombre de jours avec bonus cette semaine (1M, 2M, 3M...)"""
    bonuses = load_bonuses_week()
    week_start = get_week_start()
    key = f"{employee_key}_{week_start}"
    
    if key not in bonuses:
        return 0
    
    # Retourner le nombre de jours distincts
    days = bonuses[key]
    if isinstance(days, list):
        return len(set(days))
    return 0

def award_bonus_week(employee_key):
    """
    Ajoute un bonus pour aujourd'hui si entre 21h-23h
    Retourne le nombre total de jours avec bonus cette semaine
    """
    now = datetime.now()
    
    # Vérifier que c'est entre 21h et 23h
    if not (21 <= now.hour < 23):
        return 0
    
    bonuses = load_bonuses_week()
    week_start = get_week_start()
    today = now.strftime("%Y-%m-%d")
    key = f"{employee_key}_{week_start}"
    
    # Initialiser la liste si elle n'existe pas
    if key not in bonuses:
        bonuses[key] = []
    
    # Ajouter la date d'aujourd'hui si pas déjà présente
    if today not in bonuses[key]:
        bonuses[key].append(today)
    
    # Sauvegarder
    save_bonuses_week(bonuses)
    
    # Retourner le nombre total de jours distincts
    return len(set(bonuses[key]))

def normalize_employee_key(name: str) -> str:
    """Normalise un identifiant d'employé pour correspondre aux clés de stats.json.
    - met en minuscules
    - supprime les préfixes de rôle (dir-, cds-, med-, int-, emt-, ads-, inf-, rh-, drh-)
    - remplace les espaces par des tirets
    - retire les crochets/espaces parasites
    """
    if not name:
        return ""
    s = name.strip().lower()
    # Retirer crochets type [emt] ou [rh]
    for br in ["[emt]", "[int]", "[cds]", "[rh]", "[drh]", "[med]", "[ads]", "[inf]", "[dir]"]:
        s = s.replace(br, "")
    s = s.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    s = s.replace("_", "-")
    # Supprimer TOUS les préfixes de grade connus (avec tiret OU espace)
    # Ordre important: dir- avant drh- pour éviter confusion
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
    # Boucler jusqu'à ce qu'aucun préfixe ne soit détecté (au cas où il y en aurait plusieurs)
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
    # Supprimer tirets au début/fin
    s = s.strip("-")
    return s

def load_channel_map():
    return robust_load_json(CHANNEL_MAP_FILE, {})

def save_channel_map(mapping: dict):
    atomic_write_json(CHANNEL_MAP_FILE, mapping)

def get_channel_employee_key(channel: discord.abc.GuildChannel) -> str:
    """Retourne la clé employé pour un channel donné en s'appuyant sur un mapping persistant.
    Si absente, la déduit du nom du channel et persiste le mapping.
    Force toujours la normalisation pour garantir la cohérence.
    """
    mapping = load_channel_map()
    
    # Extraire le nom du channel (enlever l'emoji couleur)
    raw = channel.name[1:].strip() if channel.name and len(channel.name) > 1 else channel.name
    # TOUJOURS normaliser le nom pour garantir la cohérence
    key = normalize_employee_key(raw or "")
    
    # Vérifier si un mapping existe déjà pour ce channel
    existing_key = mapping.get(str(channel.id))
    
    # Si le mapping existe MAIS la clé est différente, mettre à jour avec la clé normalisée
    if existing_key != key:
        mapping[str(channel.id)] = key
        save_channel_map(mapping)
    
    return key

def extract_employee_name(channel_name):
    """Extrait le nom normalisé de l'employé à partir du nom du channel (sans l'emoji)."""
    if len(channel_name) > 1:
        raw = channel_name[1:].strip()
        return normalize_employee_key(raw)
    return None

def get_color_emoji(count):
    """Retourne l'emoji couleur en fonction du nombre de réactions"""
    if count >= 100:
        return "🟢"
    elif count >= 75:
        return "🟠"
    else:
        return "🔴"

# --- GESTION DES STATS TAXI ---
def load_taxi_stats():
    return robust_load_json(TAXI_STATS_FILE, {"count": 0, "week_start": datetime.now().isoformat()})

def save_taxi_stats(stats):
    atomic_write_json(TAXI_STATS_FILE, stats)

def reset_taxi_week():
    """Réinitialise les stats taxi pour la nouvelle semaine"""
    stats = {"count": 0, "week_start": datetime.now().isoformat()}
    save_taxi_stats(stats)
    return stats

# --- GESTION DES STATS BURGERSHOT ---
def load_burgershot_stats():
    return robust_load_json(BURGERSHOT_STATS_FILE, {"count": 0, "week_start": datetime.now().isoformat()})

def save_burgershot_stats(stats):
    atomic_write_json(BURGERSHOT_STATS_FILE, stats)

def reset_burgershot_week():
    """Réinitialise les stats BurgerShot pour la nouvelle semaine"""
    stats = {"count": 0, "week_start": datetime.now().isoformat()}
    save_burgershot_stats(stats)
    return stats

# --- GESTION DES GIVEAWAYS ---
def load_giveaways():
    return robust_load_json(GIVEAWAY_FILE, {})

def save_giveaways(giveaways):
    atomic_write_json(GIVEAWAY_FILE, giveaways)

# --- SYSTEME DE RÉACTIONS ET COMPTAGE TAXI ---

def load_bonuses():
    """Charge les bonus journaliers (format: {'employee-key_YYYY-MM-DD': 1})"""
    return robust_load_json("bonuses.json", {})

def save_bonuses(bonuses):
    """Sauvegarde les bonus journaliers"""
    atomic_write_json("bonuses.json", bonuses, make_backup=True)

def get_today_bonus(employee_key: str) -> int:
    """Retourne le bonus total d'aujourd'hui pour cet employé (0 ou 1M)"""
    bonuses = load_bonuses()
    today = datetime.now().strftime("%Y-%m-%d")
    bonus_key = f"{employee_key}_{today}"
    # Retourne 1 si la clé existe, sinon 0
    return 1 if bonus_key in bonuses else 0

def award_bonus(employee_key: str) -> bool:
    """Attribue le bonus 1M de la soirée si pas déjà donné aujourd'hui"""
    bonuses = load_bonuses()
    today = datetime.now().strftime("%Y-%m-%d")
    bonus_key = f"{employee_key}_{today}"
    
    if bonus_key not in bonuses:
        bonuses[bonus_key] = 1
        save_bonuses(bonuses)
        return True  # Bonus attribué
    return False  # Bonus déjà reçu

def get_total_bonuses(employee_key: str) -> int:
    """Retourne le nombre total de primes jamais reçues par cet employé"""
    bonuses = load_bonuses()
    total = 0
    for key, value in bonuses.items():
        if key.startswith(f"{employee_key}_"):
            total += value
    return total

async def update_channel_description(channel: discord.TextChannel, count: int):
    """Met � jour la description du channel avec r�a et prime soir 1M"""
    try:
        emoji = get_color_emoji(count)
        employee_key = get_channel_employee_key(channel)
        
        if not employee_key:
            return
        
        # Vérifier si c'est entre 21h et 23h pour la prime soirée
        current_hour = datetime.now().hour
        bonus_text = ""
        
        if 21 <= current_hour < 23:
            if award_bonus(employee_key):
                bonus_text = " 1M NEW"  # Bonus fraîchement attribué
            else:
                bonus_text = " 1M"  # Bonus déjà reçu aujourd'hui
        
        description = f"{emoji} {count}/100{bonus_text}"
        await channel.edit(topic=description)
    except Exception as e:
        print(f"Erreur update_channel_description: {e}")
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # Comptage automatique pour les tests d'aptitude taxi (réaction + comptage)
    if message.channel.id == TAXI_CHANNEL_ID:
        # Vérifier si l'auteur a le rôle taxi
        if any(role.id == TAXI_ROLE_ID for role in getattr(message.author, "roles", [])):
            # Ajouter une réaction
            try:
                await message.add_reaction("✅")
            except:
                pass
            
            # Incrémenter le compteur
            taxi_stats = load_taxi_stats()
            taxi_stats["count"] += 1
            save_taxi_stats(taxi_stats)
    
    # Comptage automatique pour les tests d'aptitude BurgerShot (réaction + comptage)
    # Pour BurgerShot : on compte TOUS les messages avec image, pas besoin de vérifier le rôle
    if message.channel.id == BURGERSHOT_CHANNEL_ID:
        # Vérifier si le message contient une image
        if message.attachments:
            # Ajouter une réaction
            try:
                await message.add_reaction("✅")
            except:
                pass
            
            # Incrémenter le compteur
            burgershot_stats = load_burgershot_stats()
            burgershot_stats["count"] += 1
            save_burgershot_stats(burgershot_stats)

    if not message.attachments or not getattr(message.channel, "name", None):
        return
    
    # Éviter les traitements multiples
    if message.id in processed_reactions:
        return
    
    channel_name = message.channel.name
    
    # Vérifier si c'est un channel de réactions
    if len(channel_name) > 0 and channel_name[0] in ["🔴", "🟠", "🟢"]:
        processed_reactions.add(message.id)
        
        # Nettoyer si trop grand
        if len(processed_reactions) > 500:
            processed_reactions.clear()
        
        stats = load_stats()
        # Utiliser un mapping persistant channel->employé pour garantir la stabilité
        employee_key = get_channel_employee_key(message.channel)
        
        if not employee_key:
            return
        
        # Incrémenter le compteur
        if employee_key not in stats:
            stats[employee_key] = 0
        
        stats[employee_key] += 1
        current_count = stats[employee_key]
        save_stats(stats)
        await update_channel_description(message.channel, current_count)
        # Pas de logique de badges: on garde simple et fiable
        
        # Ajouter réaction
        try:
            await message.add_reaction("✅")
        except:
            pass
        
        # Changer l'emoji du channel
        current_emoji = channel_name[0]
        new_emoji = get_color_emoji(current_count)
        
        if current_emoji != new_emoji:
            new_channel_name = f"{new_emoji}{channel_name[1:]}"
            try:
                await message.channel.edit(name=new_channel_name)
            except:
                pass
        
        # Envoyer log simplifié
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            new_emoji = get_color_emoji(current_count)
            
            # Message simple et normal (affiche la clé normalisée)
            message_text = f"✅ **{employee_key}** | {current_count} réas"
            
            try:
                await log_channel.send(message_text)
            except:
                pass

# --- COMMANDES ADMIN ---
@bot.tree.command(name="total", description="Affiche le total des réactions + primes")
@app_commands.checks.has_permissions(administrator=True)
async def total(interaction: discord.Interaction):
    await interaction.response.defer()
    
    stats = load_stats()
    
    if not stats:
        embed = discord.Embed(
            title="🚑 Statistiques",
            description="Aucune donnée",
            color=EMS_RED
        )
        embed.set_footer(text="🚑 EMS System")
        await interaction.followup.send(embed=embed)
        return
    
    # Regrouper les stats par nom normalisé (sans préfixes de grade)
    grouped_stats = {}
    for name, count in stats.items():
        # Normaliser le nom pour supprimer les préfixes (dir-, cds-, etc.)
        normalized = normalize_employee_key(name)
        if normalized not in grouped_stats:
            grouped_stats[normalized] = 0
        grouped_stats[normalized] += count
    
    sorted_stats = sorted(grouped_stats.items(), key=lambda x: x[1], reverse=True)
    
    # Créer plusieurs embeds si nécessaire (25 champs max par embed)
    embeds = []
    current_embed = None
    field_count = 0
    
    for name, count in sorted_stats:
        if field_count >= 25:
            # Ajouter l'embed courant à la liste AVANT de créer un nouveau
            embeds.append(current_embed)
            # Créer un nouvel embed
            current_embed = discord.Embed(
                title=f"🚑 📊 Statistiques (suite)",
                color=EMS_RED
            )
            field_count = 0
        
        if current_embed is None:
            current_embed = discord.Embed(
                title="🚑 📊 Statistiques",
                color=EMS_RED
            )
        
        emoji = get_color_emoji(count)
        # Afficher le nom joliment formaté
        display_name = ' '.join([p.capitalize() for p in name.split('-')])
        # Ajouter les primes totales
        total_bonuses = get_total_bonuses(name)
        bonus_text = f" (+{total_bonuses}M primes)" if total_bonuses > 0 else ""
        current_embed.add_field(name=f"{emoji} {display_name}", value=f"{count}/100{bonus_text}", inline=False)
        field_count += 1
    
    # Ajouter le dernier embed avec le footer
    if current_embed:
        current_embed.set_footer(text="🚑 EMS System")
        embeds.append(current_embed)
    
    # Calculer le total des réactions et primes
    total_reactions = sum(grouped_stats.values())
    total_all_bonuses = sum(get_total_bonuses(name) for name, _ in grouped_stats.items())
    
    # Ajouter un dernier embed avec le résumé
    summary_embed = discord.Embed(
        title="📊 RÉSUMÉ DE CETTE SEMAINE",
        description=f"**Total des réactions :** `{total_reactions}` 🎯\n**Total des primes :** `{total_all_bonuses}M` 💰",
        color=EMS_RED
    )
    summary_embed.set_footer(text="🚑 EMS System")
    embeds.append(summary_embed)
    
    # Envoyer tous les embeds
    for embed in embeds:
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="reset", description="Réinitialise les compteurs")
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction):
    await interaction.response.defer()
    save_stats({})
    
    embed = discord.Embed(
        title="🚑 ✅ Réinitialisation",
        description="Compteurs réinitialisés",
        color=EMS_RED
    )
    embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="help", description="Affiche toutes les commandes disponibles")
@app_commands.checks.has_permissions(administrator=True)
async def help_command(interaction: discord.Interaction):
    await interaction.response.defer()
    
    # Embed Principal
    main_embed = discord.Embed(
        title="🚑 EMS MANAGEMENT SYSTEM - AIDE",
        description="Liste complète des commandes disponibles",
        color=EMS_RED
    )
    main_embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    
    # Embed Stats & Gestion
    stats_embed = discord.Embed(
        title="📊 STATISTIQUES & GESTION",
        description="Commandes pour gérer les statistiques des employés",
        color=EMS_RED
    )
    stats_embed.add_field(
        name="/total",
        value="📊 Affiche le classement complet\n• Liste tous les employés\n• Nombre de réas par personne\n• Émojis de couleur (🔴🟠🟢)\n• Résumé du total",
        inline=False
    )
    stats_embed.add_field(
        name="/reset",
        value="🔄 Réinitialise les compteurs\n• Remet tous les compteurs à 0\n• Conserve les channels",
        inline=False
    )
    stats_embed.add_field(
        name="/semaine",
        value="📅 Nouvelle semaine complète\n• Envoie le bilan hebdomadaire\n• Reset tous les compteurs\n• Change tous les channels en 🔴\n• Annonce dans tous les channels",
        inline=False
    )
    stats_embed.add_field(
        name="/stats_info",
        value="💾 Infos sur la sauvegarde\n• État du fichier stats.json\n• Nombre d'employés\n• Total des réas\n• Dernière modification",
        inline=False
    )
    
    # Embed Employés
    employee_embed = discord.Embed(
        title="👥 GESTION DES EMPLOYÉS",
        description="Commandes pour recruter et gérer les employés",
        color=EMS_RED
    )
    employee_embed.add_field(
        name="/employer @membre",
        value="✅ Recruter un employé\n• Ajoute le tag [EMT]\n• Attribue les rôles\n• Crée le channel personnel\n• Retire le rôle attente",
        inline=False
    )
    employee_embed.add_field(
        name="/virer @membre",
        value="❌ Virer un employé\n• Retire tous les rôles EMS\n• Reset le pseudo\n• Supprime le channel personnel\n• Ajoute le rôle attente",
        inline=False
    )
    employee_embed.add_field(
        name="/up @membre",
        value="⬆️ Promouvoir un employé\n• EMT → INT → ADS → INF → MED → CDS → DIR\n• Change le tag automatiquement\n• Déplace le channel\n• Met à jour les rôles",
        inline=False
    )
    employee_embed.add_field(
        name="/reset_names [@membre]",
        value="🏷️ Applique les tags selon les rôles\n• Détecte les rôles Discord\n• Applique le tag approprié\n• Optionnel: un seul membre ou tous",
        inline=False
    )
    
    # Embed CV & Recrutement
    cv_embed = discord.Embed(
        title="📋 CV & RECRUTEMENT",
        description="Système de candidature automatisé",
        color=EMS_RED
    )
    cv_embed.add_field(
        name="/setup_cv",
        value="📝 Affiche le bouton de dépôt CV\n• 13 questions automatiques\n• Demande de documents\n• Validation par la direction\n• DM automatique",
        inline=False
    )
    
    # Embed Taxi
    taxi_embed = discord.Embed(
        title="🚕 GESTION TAXI",
        description="Commandes pour le système taxi",
        color=EMS_RED
    )
    taxi_embed.add_field(
        name="/taxi",
        value="📊 Affiche le compteur taxi\n• Nombre de tests d'aptitude\n• Compteur hebdomadaire",
        inline=False
    )
    taxi_embed.add_field(
        name="/taxi_announce",
        value="📢 Envoie l'annonce hebdomadaire\n• Bilan de la semaine\n• Revenus calculés\n• Reset du compteur",
        inline=False
    )
    
    # Embed Tickets
    tickets_embed = discord.Embed(
        title="🎫 SYSTÈME DE TICKETS",
        description="Gestion des demandes et rendez-vous",
        color=EMS_RED
    )
    tickets_embed.add_field(
        name="/setup_role_request",
        value="👮 Bouton demande de rôle LSPD/BCSO\n• Questions automatiques\n• Attribution des rôles\n• Changement de pseudo\n• Fermeture auto",
        inline=False
    )
    tickets_embed.add_field(
        name="/setup_appointment",
        value="📅 Bouton prise de rendez-vous\n• Création de channel privé\n• Discussion avec l'équipe\n• Bouton de fermeture",
        inline=False
    )
    
    # Embed Catégories
    cat_embed = discord.Embed(
        title="🏗️ GESTION DES CATÉGORIES",
        description="Organisation des channels par grade",
        color=EMS_RED
    )
    cat_embed.add_field(
        name="/setup_categories",
        value="🔨 Crée les catégories par grade\n• DIR, CDS, MED, INF, ADS, INT, EMT\n• Organisation automatique",
        inline=False
    )
    
    # Embed Footer
    footer_embed = discord.Embed(
        title="ℹ️ INFORMATIONS",
        description=(
            "**🔐 Permissions requises :**\n"
            "La plupart des commandes nécessitent les permissions administrateur.\n\n"
            "**💾 Sauvegarde automatique :**\n"
            "Toutes les modifications sont sauvegardées immédiatement.\n"
            "Les stats sont préservées lors du redémarrage.\n\n"
            "**📞 Support :**\n"
            "En cas de problème, contactez la direction.\n\n"
            "**🔄 Mises à jour :**\n"
            "Le bot est automatiquement mis à jour via GitHub."
        ),
        color=EMS_RED
    )
    footer_embed.set_footer(text="🚑 EMS System | Version 2.0")
    
    # Envoyer tous les embeds
    embeds = [main_embed, stats_embed, employee_embed, cv_embed, taxi_embed, tickets_embed, cat_embed, footer_embed]
    for embed in embeds:
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="info", description="Envoie les informations EMS dans le channel d�di�")
@app_commands.checks.has_permissions(administrator=True)
async def info(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # Channel et r�le cibles
    target_channel_id = 1306021673912238142
    ping_role_id = 838102445095256068

    target_channel = bot.get_channel(target_channel_id)
    if not target_channel:
        await interaction.followup.send(" Channel cible introuvable!", ephemeral=True)
        return

    role = interaction.guild.get_role(ping_role_id)
    role_mention = f"<@&{ping_role_id}>" if role else "@everyone"

    # Cr�er l'embed principal
    embed = discord.Embed(
        title=" :EMS: Fr�quence EMS : 9",
        description="Toutes les infos utiles � savoir",
        color=EMS_RED
    )

    # Section conformit�
    embed.add_field(
        name=" Conformit�",
        value=(
            "Avant de d�buter votre formation, assurez-vous d'�tre en conformit� avec le r�glement int�rieur. "
            "Ne pas respecter les r�gles peut entra�ner un licenciement sans frais.\n\n"
            "Vous devez repr�senter l'institution publique m�dicale des EMS avec s�rieux et fiert�."
        ),
        inline=False
    )

    # Section syst�me de paie
    embed.add_field(
        name=" Syst�me de Paie",
        value=(
            "La paye d�pend du nombre de r�animations effectu�es.\n"
            " **Paye maximale :** jusqu'� 10 000 000$ selon le nombre de r�animations."
        ),
        inline=False
    )

    # Section quota
    embed.add_field(
        name=" Quota Hebdomadaire",
        value=(
            "**Chaque semaine, vous devez effectuer un minimum de 75 r�animations.**\n\n"
            "** Syst�me de couleurs (�mojis) :**\n"
            " **Rouge** : Moins de 75 r�animations\n"
            " **Orange** : 75 r�animations (quota atteint)\n"
            " **Vert** : 100 r�animations et plus (augmentation de grade)"
        ),
        inline=False
    )

    # Section prime soir�e
    embed.add_field(
        name=" Prime d'Activit� Soir�e",
        value=(
            "**Bonus 1M par soir entre 21h-23h**\n"
            " Effectuez au moins 1 r�animation entre 21h et 23h\n"
            " Gagnez automatiquement +1M (primes � la fin de la semaine)\n"
            " Consultez votre progression dans la **description de votre channel personnel**\n"
            " La progression s'affiche comme :  75/100 1M"
        ),
        inline=False
    )


    # Section nourriture
    embed.add_field(
        name=" Nourriture",
        value="Fourniture de 5x produits de chaque type lors de la prise de service.",
        inline=False
    )

    # Section prix des soins
    embed.add_field(
        name=" Prix des Soins",
        value=(
            "**R�animation :** Pr�lev� automatiquement\n"
            "**Bandage :** 5 000 $"
        ),
        inline=False
    )

    # Section r�gles importantes
    embed.add_field(
        name=" R�gles Importantes",
        value=(
            " Il est fortement recommand� d'�tre dans une radio Discord en service (Radio Chill)\n"
            " Toute erreur ou quota non respect� sera sanctionn�\n"
            " Pas de vente de medikits ou bandages � usage personnel, uniquement professionnel\n"
            "  **IMPORTANT : Envoyez la preuve (screenshot) de chaque r�animation d�s que vous r�animez !**"
        ),
        inline=False
    )

    # Section captures d'�cran
    embed.add_field(
        name=" Captures d'�cran obligatoires",
        value="Voir les images ci-dessous",
        inline=False
    )

    embed.set_footer(text=" EMS System | Respectez ces r�gles pour garantir votre carri�re au sein des EMS")

    # Envoyer le ping + embed
    await target_channel.send(
        content=f"{role_mention} **Nouvelles informations EMS !**",
        embed=embed
    )

    # Envoyer toutes les images ensemble
    await target_channel.send("https://media.discordapp.net/attachments/1306021673912238142/1454172566489923776/image.png")
    await target_channel.send("https://media.discordapp.net/attachments/1306021673912238142/1454172153422418091/Grade_1.png")
    await target_channel.send("https://media.discordapp.net/attachments/1306021673912238142/1454172154315804846/Grade_4.png")

    # Confirmation
    await interaction.followup.send(f" Informations EMS envoy�es dans {target_channel.mention}!", ephemeral=True)
@bot.tree.command(name="stats_info", description="Affiche les informations sur la sauvegarde des stats")
@app_commands.checks.has_permissions(administrator=True)
async def stats_info(interaction: discord.Interaction):
    await interaction.response.defer()
    
    stats = load_stats()
    
    # Obtenir les informations du fichier
    try:
        import os
        from datetime import datetime
        
        file_size = os.path.getsize(STATS_FILE)
        mod_time = os.path.getmtime(STATS_FILE)
        mod_datetime = datetime.fromtimestamp(mod_time)
        
        embed = discord.Embed(
            title="💾 INFORMATIONS DE SAUVEGARDE",
            description="État actuel du système de statistiques",
            color=EMS_RED
        )
        
        embed.add_field(
            name="📊 Données chargées",
            value=f"**Employés enregistrés :** {len(stats)}\n**Total des réas :** {sum(stats.values())}",
            inline=False
        )
        
        embed.add_field(
            name="📁 Fichier stats.json",
            value=f"**Taille :** {file_size} octets\n**Dernière modification :** {mod_datetime.strftime('%d/%m/%Y %H:%M:%S')}",
            inline=False
        )
        
        # Top 5
        if stats:
            top_5 = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:5]
            top_text = "\n".join([f"{get_color_emoji(count)} **{name}** : {count}" for name, count in top_5])
            embed.add_field(
                name="🏆 Top 5",
                value=top_text,
                inline=False
            )
        
        embed.add_field(
            name="✅ Statut",
            value="**Sauvegarde automatique :** Activée ✓\n**Backup au démarrage :** Activé ✓\n**Système :** Opérationnel",
            inline=False
        )
        
        embed.set_footer(text="🚑 EMS System | Les stats sont sauvegardées à chaque modification")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Erreur",
            description=f"Impossible de récupérer les informations:\n```{e}```",
            color=EMS_DARK_RED
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="sync_rea", description="Synchronise les réanimations non traitées pendant l'offline")
@app_commands.checks.has_permissions(administrator=True)
async def sync_rea(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    stats = load_stats()
    
    synced_count = 0
    channels_synced = []
    
    # Parcourir tous les channels de réanimation
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]:
            channel_synced = 0
            
            # Récupérer l'employé associé au channel
            employee_key = get_channel_employee_key(channel)
            if not employee_key:
                continue
            
            # Chercher le dernier message de /semaine (NOUVELLE SEMAINE) pour ne traiter que les messages après
            last_semaine_date = None
            try:
                async for msg in channel.history(limit=200):
                    if msg.author.id == bot.user.id and msg.embeds:
                        for embed in msg.embeds:
                            if embed.title and "NOUVELLE SEMAINE" in embed.title:
                                last_semaine_date = msg.created_at
                                break
                        if last_semaine_date:
                            break
            except:
                pass
            
            # Récupérer les messages (limité aux 100 derniers pour éviter les timeouts)
            try:
                async for message in channel.history(limit=100):
                    # Si on a trouvé un message de /semaine, ignorer les messages avant cette date
                    if last_semaine_date and message.created_at < last_semaine_date:
                        continue
                    
                    # Vérifier si le message a des pièces jointes
                    if not message.attachments or message.author.bot:
                        continue
                    
                    # Vérifier si le bot a déjà réagi avec ✅
                    bot_reacted = False
                    for reaction in message.reactions:
                        if str(reaction.emoji) == "✅":
                            # Vérifier si c'est le bot qui a réagi
                            async for user in reaction.users():
                                if user.id == bot.user.id:
                                    bot_reacted = True
                                    break
                            if bot_reacted:
                                break
                    
                    # Si le bot n'a pas encore réagi, traiter le message
                    if not bot_reacted:
                        # Incrémenter le compteur
                        if employee_key not in stats:
                            stats[employee_key] = 0
                        
                        stats[employee_key] += 1
                        channel_synced += 1
                        synced_count += 1
                        
                        # Ajouter la réaction
                        try:
                            await message.add_reaction("✅")
                        except:
                            pass
                        
                        # Envoyer log
                        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
                        if log_channel:
                            current_count = stats[employee_key]
                            emoji = get_color_emoji(current_count)
                            message_text = f"🔄 **{employee_key}** | {current_count} réas (sync)"
                            
                            try:
                                await log_channel.send(message_text)
                            except:
                                pass
            
            except Exception as e:
                print(f"Erreur sync channel {channel.name}: {e}")
                continue
            
            # Mettre à jour la couleur du channel si des messages ont été synchronisés
            if channel_synced > 0:
                channels_synced.append(f"{channel.mention} (+{channel_synced})")
                current_count = stats.get(employee_key, 0)
                new_emoji = get_color_emoji(current_count)
                current_emoji = channel.name[0]
                
                if current_emoji != new_emoji:
                    new_channel_name = f"{new_emoji}{channel.name[1:]}"
                    try:
                        await channel.edit(name=new_channel_name)
                    except:
                        pass
    
    # Sauvegarder les stats
    save_stats(stats)
    
    # Message de confirmation
    if synced_count > 0:
        embed = discord.Embed(
            title="🔄 SYNCHRONISATION COMPLÉTÉE",
            description=f"**{synced_count} réanimation(s) récupérée(s) et ajoutée(s) aux quotas**",
            color=EMS_RED
        )
        
        if channels_synced:
            channels_text = "\n".join(channels_synced[:25])  # Limiter à 25 pour éviter les embeds trop longs
            embed.add_field(name="📊 Channels synchronisés", value=channels_text, inline=False)
        
        embed.add_field(
            name="✅ Actions effectuées",
            value="• Messages cochés avec ✅\n• Compteurs mis à jour\n• Couleurs des channels actualisées\n• Logs envoyés\n• ⏱️ Uniquement les réas après /semaine",
            inline=False
        )
        embed.set_footer(text="🚑 EMS System | Synchronisation automatique")
    else:
        embed = discord.Embed(
            title="✅ SYNCHRONISATION COMPLÉTÉE",
            description="Aucune réanimation à rattraper. Tous les messages ont déjà été traités !",
            color=EMS_RED
        )
        embed.set_footer(text="🚑 EMS System")
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="force_update", description="Force la mise à jour des stats d'un employé")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    member="Le membre à mettre à jour",
    value="La nouvelle valeur de réanimations"
)
async def force_update(interaction: discord.Interaction, member: discord.Member, value: int):
    await interaction.response.defer()
    
    stats = load_stats()
    member_name = f"{member.name}".lower().replace(" ", "-")
    
    # Chercher la clé dans stats
    found_key = None
    for key in stats.keys():
        if member.name.lower() in key or key.lower() in member.name.lower():
            found_key = key
            break
    
    if found_key:
        old_value = stats[found_key]
        stats[found_key] = value
        save_stats(stats)
        
        # Mettre à jour la description du channel si applicable
        if member.name in [ch.name for ch in interaction.guild.text_channels]:
            channel = discord.utils.get(interaction.guild.text_channels, name=member.name)
            if channel:
                try:
                    emoji = get_color_emoji(value)
                    description = f"{emoji} {value}/100"
                    await channel.edit(topic=description)
                except:
                    pass
        
        embed = discord.Embed(
            title="✅ STATS MISES À JOUR",
            description=f"**{member.name}**\nAncienne valeur: `{old_value}`\nNouvelle valeur: `{value}`",
            color=EMS_RED
        )
        embed.set_footer(text="🚑 EMS System | Force Update")
    else:
        embed = discord.Embed(
            title="❌ ERREUR",
            description=f"Impossible de trouver les stats de `{member.name}`",
            color=0xFF0000
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="force_update_all", description="Force la mise à jour de TOUS les stats EMS")
@app_commands.checks.has_permissions(administrator=True)
async def force_update_all(interaction: discord.Interaction):
    await interaction.response.defer()
    
    # Mise à jour forcée de toutes les stats
    new_stats = {
        "balake-andrew": 234,
        "marc-zenter": 204,
        "momo-ahmet": 161,
        "alvaro-benz": 152,
        "mehmet-momo": 152,
        "bouras-anas": 110,
        "ethan-cocacherry": 102,
        "sacha-icetee": 100,
        "david-tares": 98,
        "alex-winston": 82,
        "jason-trigo": 81,
        "avi-ramirez": 81,
        "mathis-martin": 70,
        "farid-lamatraque": 90,
        "juan-pablo-escobar": 54,
        "louis-fera": 46,
        "jean-martin": 35,
        "imran-meknessi": 24,
        "jonson-jayden": 15,
        "leo-lenz": 14,
        "jean-dan": 6
    }
    
    save_stats(new_stats)
    
    # Mettre à jour les descriptions des channels
    guild = interaction.guild
    updated_count = 0
    
    for key, value in new_stats.items():
        # Chercher le channel correspondant
        channel_name = key.replace("-", " ").title()
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        
        if channel:
            try:
                emoji = get_color_emoji(value)
                description = f"{emoji} {value}/100"
                await channel.edit(topic=description)
                updated_count += 1
            except:
                pass
    
    embed = discord.Embed(
        title="✅ TOUS LES STATS MIS À JOUR",
        description=f"**{len(new_stats)} employés mises à jour**\n**{updated_count} channels descriptions mises à jour**",
        color=EMS_RED
    )
    
    # Ajouter les détails
    stats_text = "\n".join([f"`{k}`: {v}/100" for k, v in list(new_stats.items())[:10]])
    embed.add_field(name="Premiers 10 employés", value=stats_text, inline=False)
    embed.set_footer(text="🚑 EMS System | Force Update All")
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="fix_emojis", description="Corrige les emojis et descriptions de tous les salons EMS")
@app_commands.checks.has_permissions(administrator=True)
async def fix_emojis(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    stats = load_stats()
    
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    
    # Délai entre chaque mise à jour pour éviter le rate limiting
    DELAY_BETWEEN_UPDATES = 1.5  # secondes
    
    for key, value in stats.items():
        try:
            # Chercher le channel correspondant
            displayname = key.replace("-", " ").title()
            channel = discord.utils.get(guild.text_channels, name=displayname)
            
            if channel:
                try:
                    emoji = get_color_emoji(value)
                    description = f"{emoji} {value}/100"
                    await channel.edit(topic=description)
                    updated_count += 1
                    # Délai pour éviter le rate limiting
                    await asyncio.sleep(DELAY_BETWEEN_UPDATES)
                except Exception as e:
                    failed_count += 1
                    print(f"❌ Erreur mise à jour {key}: {e}")
            else:
                skipped_count += 1
                
        except Exception as e:
            failed_count += 1
            print(f"❌ Erreur traitement {key}: {e}")
    
    embed = discord.Embed(
        title="✅ CORRECTION DES EMOJIS COMPLÉTÉE",
        description=f"Mise à jour des descriptions de salons",
        color=EMS_RED
    )
    embed.add_field(name="✅ Mis à jour", value=f"{updated_count} salons", inline=True)
    embed.add_field(name="⏭️ Ignorés", value=f"{skipped_count} salons", inline=True)
    embed.add_field(name="❌ Erreurs", value=f"{failed_count} salons", inline=True)
    embed.set_footer(text="🚑 EMS System | Fix Emojis")
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="update_colors", description="Met à jour les couleurs de tous les channels selon les quotas")
@app_commands.checks.has_permissions(administrator=True)
async def update_colors(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    stats = load_stats()
    
    updated_count = 0
    errors = []
    
    # Parcourir tous les channels avec emoji
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]:
            try:
                # Récupérer la clé employé
                employee_key = get_channel_employee_key(channel)
                if not employee_key:
                    continue
                
                # Récupérer le compteur
                current_count = stats.get(employee_key, 0)
                
                # Calculer la nouvelle couleur
                new_emoji = get_color_emoji(current_count)
                current_emoji = channel.name[0]
                
                # Mettre à jour si différent
                if current_emoji != new_emoji:
                    new_channel_name = f"{new_emoji}{channel.name[1:]}"
                    await channel.edit(name=new_channel_name)
                    updated_count += 1
                    
            except Exception as e:
                errors.append(f"❌ {channel.name}: {str(e)[:50]}")
    
    # Message de confirmation
    embed = discord.Embed(
        title="🎨 MISE À JOUR DES COULEURS",
        description=f"**{updated_count} channel(s) mis à jour**",
        color=EMS_RED
    )
    
    if errors:
        embed.add_field(
            name="⚠️ Erreurs",
            value="\n".join(errors[:10]),
            inline=False
        )
    
    embed.add_field(
        name="📊 Légende",
        value="🔴 Moins de 50 réas\n🟠 Entre 50 et 99 réas\n🟢 100 réas ou plus",
        inline=False
    )
    
    embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="semaine", description="Réinitialise la semaine - Remet tout à 0 et met en rouge")
@app_commands.checks.has_permissions(administrator=True)
async def semaine(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # 1) Envoyer d'abord le bilan hebdomadaire EMS dans les logs avant reset
    pre_stats = load_stats()
    log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
    if log_channel and pre_stats:
        # Ordonner par nombre décroissant
        ordered = sorted(pre_stats.items(), key=lambda kv: kv[1], reverse=True)

        embeds = []
        current_embed = None
        field_count = 0
        page_index = 1
        total_reactions = sum(pre_stats.values())

        def pretty_name(key: str) -> str:
            parts = key.split('-')
            return ' '.join([p.capitalize() for p in parts])

        for name_key, count in ordered:
            if current_embed is None or field_count >= 25:
                if current_embed is not None:
                    current_embed.set_footer(text=f"🚑 EMS System | Page {page_index}")
                    embeds.append(current_embed)
                    page_index += 1
                current_embed = discord.Embed(
                    title="📊 BILAN HEBDOMADAIRE EMS",
                    description="Récapitulatif des réanimations par employé (semaine)",
                    color=EMS_RED
                )
                field_count = 0

            emoji = get_color_emoji(count)
            display_name = pretty_name(name_key)
            current_embed.add_field(name=f"{emoji} {display_name}", value=f"{count}/100", inline=False)
            field_count += 1

        if current_embed is not None:
            current_embed.set_footer(text=f"🚑 EMS System | Page {page_index}")
            embeds.append(current_embed)

        summary_embed = discord.Embed(
            title="📊 RÉSUMÉ SEMAINE EMS",
            description=f"**Total des réanimations (semaine):** `{total_reactions}` 🎯",
            color=EMS_RED
        )
        summary_embed.set_footer(text="🚑 EMS System")
        embeds.append(summary_embed)

        for e in embeds:
            try:
                await log_channel.send(embed=e)
            except:
                pass

    # 2) Réinitialiser stats
    save_stats({})
    
    # Mettre tous les channels en 🔴 et garder la liste pour l'annonce
    announcement_channels = []
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]:
            new_name = f"🔴{channel.name[1:]}"
            try:
                await channel.edit(name=new_name)
                announcement_channels.append(channel)
            except:
                pass
    
    # Télécharger la bannière NOUVELLE SEMAINE une seule fois
    banner_url = "https://media.discordapp.net/attachments/1432501937085087896/1457439823215460487/image.png?ex=695ea51b&is=695d539b&hm=73669ae578193fac7bb528589592facb8ffa94a53f6521f1fad68165e393d32c&=&format=webp&quality=lossless&width=1872&height=571"
    banner_file = None
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(banner_url) as resp:
                if resp.status == 200:
                    banner_data = await resp.read()
                    banner_file = discord.File(io.BytesIO(banner_data), filename="nouvelle_semaine.png")
    except Exception as e:
        print(f"Erreur téléchargement bannière: {e}")
    
    # Embed d'annonce de semaine
    embed = discord.Embed(
        title="🚑 NOUVELLE SEMAINE !",
        description="**✅ Réinitialisation complète de la semaine**\n\n• Tous les compteurs remis à 0\n• Tous les channels en 🔴\n• C'est repartit de zéro !\n\n**Bonne chance à tous ! 💪**",
        color=EMS_RED
    )
    embed.set_footer(text="🚑 EMS System | Nouvelle semaine, nouveau challenge !")
    
    if banner_file:
        embed.set_image(url=f"attachment://{banner_file.filename}")

    # Envoyer l'annonce dans tous les channels avec emoji préfixe
    for channel in announcement_channels:
        try:
            if banner_file:
                # Créer une nouvelle copie du fichier pour chaque envoi
                new_banner = discord.File(io.BytesIO(banner_data), filename="nouvelle_semaine.png")
                await channel.send(embed=embed.copy(), file=new_banner)
            else:
                await channel.send(embed=embed.copy())
        except:
            pass
    
    # Envoyer aussi dans le channel de logs
    log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
    if log_channel:
        try:
            if banner_file:
                new_banner = discord.File(io.BytesIO(banner_data), filename="nouvelle_semaine.png")
                await log_channel.send(embed=embed.copy(), file=new_banner)
            else:
                await log_channel.send(embed=embed.copy())
        except:
            pass
    
    embed_confirm = discord.Embed(
        title="🚑 ✅ SEMAINE RÉINITIALISÉE",
        description="✅ Tous les compteurs remis à 0\n✅ Tous les channels changés en 🔴\n✅ Message posté en logs\n\nC'est parti pour une nouvelle semaine ! 🚀",
        color=EMS_RED
    )
    embed_confirm.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed_confirm)

## Commandes de couleur supprimées (sync_colors, update_color)

# --- COMMANDE TAXI ---
@bot.tree.command(name="taxi", description="Affiche le compteur des tests d'aptitude taxi")
@app_commands.checks.has_permissions(administrator=True)
async def taxi(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        with open('taxi_stats.json', 'r', encoding='utf-8') as f:
            taxi_data = json.load(f)
    except:
        taxi_data = {"test_aptitude_taxi": 0}
    
    test_count = taxi_data.get("test_aptitude_taxi", 0)
    
    embed = discord.Embed(
        title="🚕 Tests d'Aptitude Taxi",
        description=f"**Nombre de tests complétés :** {test_count}",
        color=EMS_RED
    )
    embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="taxi_announce", description="Envoie manuellement l'annonce hebdomadaire taxi et reset les stats")
@app_commands.checks.has_permissions(administrator=True)
async def taxi_announce(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        await send_weekly_taxi_announcement()
        await interaction.followup.send("✅ Annonce hebdomadaire envoyée et compteurs réinitialisés !", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

# --- COMMANDE BURGERSHOT ---
@bot.tree.command(name="burgershot", description="Affiche le compteur des tests d'aptitude BurgerShot")
@app_commands.checks.has_permissions(administrator=True)
async def burgershot(interaction: discord.Interaction):
    await interaction.response.defer()
    
    burgershot_stats = load_burgershot_stats()
    count = burgershot_stats.get("count", 0)
    revenus = count * 300000
    
    embed = discord.Embed(
        title="🍔 Tests d'Aptitude BurgerShot",
        description=f"**Nombre de tests complétés :** {count}\n**Revenus générés :** ${revenus:,}",
        color=discord.Color.from_rgb(255, 165, 0)  # Orange
    )
    embed.add_field(name="💰 Tarif", value="300 000$ par test", inline=False)
    embed.set_footer(text="🍔 BurgerShot System")
    await interaction.followup.send(embed=embed)

# --- QUESTIONS DU CV ---
QUESTIONS = [
    "📄 **Candidature EMS**\nNom et Prénom ?",
    "🔹 **Informations personnelles**\nQuel est votre âge ?",
    "🚗 **Permis de conduire**\nAvez-vous le permis de conduire (si oui, le(s)quel(s) ?)",
    "⏳ **Présence en ville**\nDepuis quand êtes-vous en ville ?",
    "💼 **Expérience professionnelle**\nMétier actuelle ?",
    "📚 **Parcours**\nQuels métiers avez-vous déjà exercés ?",
    "🏥 **Compétences médicales**\nAvez-vous des compétences dans le domaine médical ?",
    "🔥 **Motivations**\nQuelles sont vos motivations à entrer chez les EMS ?",
    "⭐ **Pourquoi vous ?**\nPourquoi devrions-nous vous prendre et pas quelqu'un d'autre ?",
    "👍 **Qualités**\nDonnez-nous 3 qualités qui vous caractérisent",
    "⚠️ **Défauts**\nDonnez-nous 3 défauts qui vous caractérisent",
    "📅 **Disponibilités - Semaine**\nDu lundi au vendredi : [Horaire]",
    "📅 **Disponibilités - Week-end**\nWeek-end : [Horaire]"
]

# --- SYSTÈME DE CV ---
class ReviewView(discord.ui.View):
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.message = None

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.green, custom_id="accept_cv")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # DEFER IMMÉDIATEMENT - AVANT TOUT (garantit pas d'erreur d'interaction)
        await interaction.response.defer(ephemeral=True)
        
        # Vérifier les permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Permission refusée", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.target_user.id)
        
        if not member:
            await interaction.followup.send("❌ Le candidat n'est plus sur le serveur.", ephemeral=True)
            return
        
        # Désactiver les boutons
        self.disable_all_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        
        # Ajouter le rôle
        try:
            role = guild.get_role(config.get("ROLE_ATTENTE_ID"))
            if role:
                await member.add_roles(role)
        except:
            pass
        
        # Envoyer le DM
        try:
            await member.send(
                "🎉 **FÉLICITATIONS !**\n\n"
                "✅ Votre candidature a été **ACCEPTÉE** !\n\n"
                "Bienvenue dans la famille des **EMS** ! 🚑\n\n"
                "📝 **Prochaine étape :**\n"
                "Merci de mettre vos disponibilités ici :\n"
                "https://discord.com/channels/838102445083197470/1470742714604847124\n\n"
                "et nous nous chargeons du reste !\n\n"
                "Cordialement,\n**La Direction des EMS** 🚑"
            )
        except:
            pass
        
        # Envoyer les logs
        try:
            embed = discord.Embed(
                title="✅ CV ACCEPTÉ",
                description=f"**Candidat :** {member.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_RED
            )
            embed.add_field(name="✅ Statut", value="Candidature approuvée ✓", inline=False)
            embed.add_field(name="👤 Rôle attribué", value="Attente d'onboarding", inline=False)
            embed.set_footer(text="🚑 EMS System")
            
            # Envoyer dans le channel de logs CV (1458956197796515979)
            cv_log_channel = bot.get_channel(1458956197796515979)
            if cv_log_channel:
                  await cv_log_channel.send(embed=embed)
                  
                  # Chercher et copier le CV original
                  try:
                      cv_channel = bot.get_channel(1460755743228825641)
                      if cv_channel:
                          async for cv_msg in cv_channel.history(limit=200):
                              if cv_msg.embeds and member.display_name.lower() in str(cv_msg.embeds[0].title).lower():
                                  for cv_embed in cv_msg.embeds:
                                      await cv_log_channel.send(embed=cv_embed)
                                  break
                  except:
                      pass
              # Poster l'image du membre dans le channel 1460752929429520427
            image_channel = bot.get_channel(1460752929429520427)
            if image_channel and member.avatar:
                try:
                    avatar_embed = discord.Embed(
                        title=f"✅ {member.display_name}",
                        description=f"Accepté par {interaction.user.mention}",
                        color=EMS_RED
                    )
                    avatar_embed.set_image(url=member.avatar.url)
                    avatar_embed.set_footer(text="🚑 EMS System")
                    await image_channel.send(embed=avatar_embed)
                except:
                    pass
        except:
            pass
        
        # Confirmation à l'admin
        await interaction.followup.send(f"✅ **{member.display_name}** accepté avec succès", ephemeral=True)
        
        # Supprimer le message après 3 secondes
        try:
            if self.message:
                await asyncio.sleep(3)
                await self.message.delete()
        except:
            pass

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red, custom_id="refuse_cv")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        # DEFER IMMÉDIATEMENT - AVANT TOUT (garantit pas d'erreur d'interaction)
        await interaction.response.defer(ephemeral=True)
        
        # Vérifier les permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Permission refusée", ephemeral=True)
            return
        
        # Désactiver les boutons
        self.disable_all_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        
        # Envoyer le DM au candidat
        try:
            await self.target_user.send(
                "❌ **Candidature Refusée**\n\n"
                "Nous regrettons de vous informer que votre candidature n'a pas été retenue.\n\n"
                "Nous vous encourageons à postuler à nouveau dans le futur.\n\n"
                "Cordialement,\n**La Direction des EMS** 🚑"
            )
        except:
            pass
        
        # Envoyer le log
        try:
            # Envoyer dans le channel de logs CV (1458956197796515979)
            cv_log_channel = bot.get_channel(1458956197796515979)
            if cv_log_channel:
                embed = discord.Embed(
                    title="❌ CV REFUSÉ",
                    description=f"**Candidat :** {self.target_user.mention}\n**Validateur :** {interaction.user.mention}",
                    color=EMS_DARK_RED
                )
                embed.set_footer(text="🚑 EMS System")
                await cv_log_channel.send(embed=embed)
        except:
            pass
        
        # Confirmation à l'admin
        await interaction.followup.send("✅ CV refusé avec succès", ephemeral=True)
        
        # Supprimer le message après 3 secondes
        try:
            if self.message:
                await asyncio.sleep(3)
                await self.message.delete()
        except:
            pass
    
    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

class CVButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Dépose ton CV", style=discord.ButtonStyle.primary, emoji="📝", custom_id="start_cv")
    async def start_cv(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📋 Dossier en création...", ephemeral=True)
        
        guild = interaction.guild
        user_id = interaction.user.id
        
        # Vérifier si existe
        for ch in guild.text_channels:
            if ch.name == f"cv-{user_id}":
                await interaction.followup.send(f"❌ Dossier existe : {ch.mention}", ephemeral=True)
                return
        
        # Créer channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        try:
            channel = await guild.create_text_channel(
                f"cv-{user_id}",
                overwrites=overwrites,
                category=interaction.channel.category,
                topic=f"CV {interaction.user.name}"
            )
        except:
            await interaction.followup.send("❌ Erreur création", ephemeral=True)
            return
        
        await interaction.followup.send(f"📋 Channel créé : {channel.mention}", ephemeral=True)
        
        # Welcome
        welcome = discord.Embed(
            title="🚑 RECRUTEMENT EMS - FORMULAIRE DE CANDIDATURE",
            description=(
                f"Bienvenue **{interaction.user.mention}** ! 👋\n\n"
                f"Vous êtes sur le point de participer à notre processus de sélection pour l'équipe EMS.\n\n"
                f"**📋 Informations importantes :**\n"
                f"• {len(QUESTIONS)} questions à répondre\n"
                f"⏱️ 10 minutes par question\n"
                f"📝 Répondez de manière claire et détaillée\n"
                f"📸 Préparez vos documents (CV, diplômes, etc.)\n\n"
                f"**Bonne chance ! 💪**"
            ),
            color=EMS_RED
        )
        welcome.set_footer(text="🚑 EMS Management System | Let's go!")
        await channel.send(embed=welcome)
        await asyncio.sleep(2)
        
        # Questions
        answers = []
        user_fullname = None
        
        for i, question in enumerate(QUESTIONS, 1):
            q_embed = discord.Embed(
                title=f"❓ QUESTION {i}/{len(QUESTIONS)}",
                description=question,
                color=EMS_RED
            )
            q_embed.add_field(name="⏱️ Temps", value="Vous avez **10 minutes** pour répondre", inline=False)
            q_embed.set_footer(text="🚑 EMS System | Envoyez votre réponse ci-dessous")
            await channel.send(embed=q_embed)
            
            def check(m):
                return m.author == interaction.user and m.channel == channel
            
            try:
                msg = await bot.wait_for('message', check=check, timeout=600)
                
                if i == 1:
                    user_fullname = msg.content
                    try:
                        member = guild.get_member(user_id)
                        if member:
                            await member.edit(nick=user_fullname)
                            print(f"✅ Membre renommé: {interaction.user.name} -> {user_fullname}")
                        else:
                            print(f"❌ Membre non trouvé pour renommer: {user_id}")
                    except Exception as e:
                        print(f"❌ Erreur renommage membre: {e}")
                
                answers.append(f"**{question}**\n{msg.content}")
            except asyncio.TimeoutError:
                timeout_msg = discord.Embed(
                    title="⏱️ TEMPS ÉCOULÉ - FERMETURE AUTOMATIQUE",
                    description=(
                        "❌ **Aucune réponse reçue dans les 10 minutes.**\n\n"
                        "Votre dossier de candidature va être **fermé automatiquement**.\n\n"
                        "Si vous souhaitez postuler à nouveau, cliquez sur le bouton de candidature.\n\n"
                        "🚑 **Fermeture dans 5 secondes...**"
                    ),
                    color=EMS_DARK_RED
                )
                timeout_msg.set_footer(text="🚑 EMS System | Session expirée")
                try:
                    await channel.send(embed=timeout_msg)
                except:
                    pass
                await asyncio.sleep(5)
                try:
                    await channel.delete()
                except:
                    pass
                return
        
        # Documents
        docs = discord.Embed(
            title="📎 DERNIÈRE ÉTAPE",
            description=(
                "Merci d'avoir complété le formulaire ! 🎉\n\n"
                "**Il ne manque plus que :**\n"
                "🆔 Votre carte d'identité (IMAGE)\n"
                "🚗 Votre permis de conduire (IMAGE)\n\n"
                "⚠️ **IMPORTANT : Envoyez des IMAGES uniquement**\n\n"
                "Envoyez-les ci-dessous et nous nous en chargerons ! 🚑\n\n"
                "⏱️ Vous avez un temps illimité pour envoyer les documents."
            ),
            color=EMS_RED
        )
        docs.set_footer(text="🚑 EMS System | Envoyez les IMAGES ci-dessous")
        await channel.send(embed=docs)
        
        attachments = []
        downloaded_files = []
        
        def check_doc(m):
            return m.author == interaction.user and m.channel == channel
        
        # Boucle jusqu'à ce qu'au moins un document soit envoyé
        documents_received = False
        while not documents_received:
            try:
                msg = await bot.wait_for('message', check=check_doc, timeout=None)
                
                if msg.attachments:
                    # Documents trouvés, on peut continuer
                    for att in msg.attachments:
                        # Télécharger l'image
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(att.url) as resp:
                                    if resp.status == 200:
                                        data = await resp.read()
                                        downloaded_files.append(discord.File(io.BytesIO(data), filename=att.filename))
                                        attachments.append(att.url)
                        except:
                            attachments.append(att.url)
                    documents_received = True
                else:
                    # Pas de document, redemander
                    error_embed = discord.Embed(
                        title="❌ DOCUMENTS REQUIS",
                        description=(
                            "⚠️ **Aucun document détecté !**\n\n"
                            "Vous devez **obligatoirement** envoyer vos documents :\n"
                            "🆔 Carte d'identité (IMAGE)\n"
                            "🚗 Permis de conduire (IMAGE)\n\n"
                            "**Veuillez réessayer en envoyant vos images.**"
                        ),
                        color=EMS_DARK_RED
                    )
                    error_embed.set_footer(text="🚑 EMS System | Documents obligatoires")
                    await channel.send(embed=error_embed)
            except:
                pass
        
        confirm = discord.Embed(
            title="✅ CANDIDATURE COMPLÈTE",
            description=(
                "🎉 Excellent ! Nous avons reçu votre candidature complète !\n\n"
                f"**Documents reçus :** {len(attachments)}\n\n"
                "👀 **Prochaines étapes :**\n"
                "• La direction examinera votre candidature\n"
                "• Vous recevrez une réponse dans vos messages privés\n"
                "• N'hésitez pas à nous contacter en cas de questions\n\n"
                "⏱️ Ce channel se fermera dans **2 minutes**\n\n"
                "**Merci pour votre intérêt envers les EMS !** 🚑"
            ),
            color=EMS_RED
        )
        confirm.set_footer(text="🚑 EMS System | Bon courage !")
        await channel.send(embed=confirm)
        
        # Envoyer le DM au candidat
        try:
            await interaction.user.send(
                "🚑 **Candidature envoyée** 🚑\n\n"
                "Nous avons bien reçu votre candidature.\n\n"
                "Nous vous recontacterons bientôt.\n\n"
                "Merci pour votre intérêt ! 👨‍⚕️"
            )
        except:
            pass
        
        # Envoyer au channel CV (en arrière-plan pendant que le timer commence)
        cv_channel = bot.get_channel(1460755743228825641)
        if cv_channel:
            full_text = "\n\n".join(answers)
            cv_embed = discord.Embed(
                title=f"📋 CV - {user_fullname if user_fullname else interaction.user.name}",
                description=full_text[:2000],
                color=EMS_RED
            )
            
            cv_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            cv_embed.set_footer(text=f"🚑 EMS System | ID: {user_id}")
            
            view = ReviewView(interaction.user)
            
            # Ping direction directement dans le message du CV
            direction_role = guild.get_role(config.get("ROLE_DIRECTION_ID"))
            ping_content = direction_role.mention if direction_role and config.get("ROLE_DIRECTION_ID") != 0 else None
            
            # Envoyer l'embed avec les fichiers téléchargés
            try:
                if downloaded_files:
                    msg = await cv_channel.send(content=ping_content, embed=cv_embed, files=downloaded_files, view=view)
                else:
                    if attachments:
                        cv_embed.add_field(name="📎 Documents", value="\n".join([f"[Doc {i}]({url})" for i, url in enumerate(attachments, 1)]), inline=False)
                    msg = await cv_channel.send(content=ping_content, embed=cv_embed, view=view)
                view.message = msg
                print(f"✅ CV envoyé dans le channel {cv_channel.name} pour {interaction.user.name}")
            except Exception as e:
                print(f"❌ Erreur envoi CV: {e}")
        else:
            print(f"❌ Channel CV non trouvé (ID: 1460755743228825641)")
        
        # Fermer le channel après 2 minutes
        await asyncio.sleep(120)
        try:
            await channel.delete()
        except:
            pass

# --- NOUVEAU SYSTÈME CV (FORMULAIRECV) ---
class FormulaireCVValidation(discord.ui.View):
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.message = None

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.green, custom_id="accept_formulaire_cv")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Permission refusée", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.target_user.id)
        
        if not member:
            await interaction.followup.send("❌ Le candidat n'est plus sur le serveur.", ephemeral=True)
            return
        
        # Désactiver les boutons
        for item in self.children:
            item.disabled = True
        
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            pass
        
        # Ajouter le rôle 896103247096471613
        try:
            role = guild.get_role(896103247096471613)
            if role:
                await member.add_roles(role)
        except:
            pass
        
        # Envoyer le DM
        try:
            await member.send(
                "🎉 **FÉLICITATIONS !**\n\n"
                "✅ Votre candidature a été **ACCEPTÉE** !\n\n"
                "Bienvenue dans la famille des **EMS** ! 🚑\n\n"
                "📝 **Prochaine étape :**\n"
                "Merci de mettre vos disponibilités ici :\n"
                "https://discord.com/channels/838102445083197470/1470742714604847124\n\n"
                "et nous nous chargeons du reste !\n\n"
                "Cordialement,\n**La Direction des EMS** 🚑"
            )
        except:
            pass
        
        # Logs
        try:
            embed = discord.Embed(
                title="✅ CANDIDATURE ACCEPTÉE",
                description=f"**Candidat :** {member.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_RED
            )
            embed.set_footer(text="🚑 EMS System")
            
            # Envoyer dans le channel de logs CV (1458956197796515979)
            cv_log_channel = bot.get_channel(1458956197796515979)
            if cv_log_channel:
                  await cv_log_channel.send(embed=embed)
                  
                  # Chercher et copier le CV original
                  try:
                      cv_channel = bot.get_channel(1460755743228825641)
                      if cv_channel:
                          async for cv_msg in cv_channel.history(limit=200):
                              if cv_msg.embeds and member.display_name.lower() in str(cv_msg.embeds[0].title).lower():
                                  for cv_embed in cv_msg.embeds:
                                      await cv_log_channel.send(embed=cv_embed)
                                  break
                  except:
                      pass
              # Poster l'image du membre dans le channel 1460752929429520427
            image_channel = bot.get_channel(1460752929429520427)
            if image_channel and member.avatar:
                try:
                    avatar_embed = discord.Embed(
                        title=f"✅ {member.display_name}",
                        description=f"Accepté par {interaction.user.mention}",
                        color=EMS_RED
                    )
                    avatar_embed.set_image(url=member.avatar.url)
                    avatar_embed.set_footer(text="🚑 EMS System")
                    await image_channel.send(embed=avatar_embed)
                except:
                    pass
        except:
            pass
        
        await interaction.followup.send(f"✅ **{member.display_name}** accepté !", ephemeral=True)
        
        # Supprimer le message
        try:
            await asyncio.sleep(3)
            if self.message:
                await self.message.delete()
        except:
            pass

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red, custom_id="refuse_formulaire_cv")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Permission refusée", ephemeral=True)
            return
        
        # Désactiver les boutons
        for item in self.children:
            item.disabled = True
        
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            pass
        
        # DM candidat
        try:
            await self.target_user.send(
                "❌ **Candidature Refusée**\n\n"
                "Nous regrettons de vous informer que votre candidature n'a pas été retenue.\n\n"
                "Nous vous encourageons à postuler à nouveau dans le futur.\n\n"
                "Cordialement,\n**La Direction des EMS** 🚑"
            )
        except:
            pass
        
        # Log
        try:
            # Envoyer dans le channel de logs CV (1458956197796515979)
            cv_log_channel = bot.get_channel(1458956197796515979)
            if cv_log_channel:
                embed = discord.Embed(
                    title="❌ CANDIDATURE REFUSÉE",
                    description=f"**Candidat :** {self.target_user.mention}\n**Validateur :** {interaction.user.mention}",
                    color=EMS_DARK_RED
                )
                embed.set_footer(text="🚑 EMS System")
                await cv_log_channel.send(embed=embed)
        except:
            pass
        
        await interaction.followup.send("✅ CV refusé", ephemeral=True)
        
        # Supprimer le message
        try:
            await asyncio.sleep(3)
            if self.message:
                await self.message.delete()
        except:
            pass

class FormulaireCVButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Déposer ma candidature", style=discord.ButtonStyle.primary, custom_id="start_formulaire_cv")
    async def start_formulaire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📋 Création de votre dossier...", ephemeral=True)
        
        guild = interaction.guild
        user_id = interaction.user.id
        
        # Vérifier si existe
        for ch in guild.text_channels:
            if ch.name == f"candidature-{user_id}":
                await interaction.followup.send(f"❌ Vous avez déjà un dossier : {ch.mention}", ephemeral=True)
                return
        
        # Créer channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        try:
            channel = await guild.create_text_channel(
                f"candidature-{user_id}",
                overwrites=overwrites,
                category=interaction.channel.category
            )
        except:
            await interaction.followup.send("❌ Erreur lors de la création du channel", ephemeral=True)
            return
        
        await interaction.followup.send(f"✅ Votre dossier : {channel.mention}", ephemeral=True)
        
        # Message de bienvenue
        welcome = discord.Embed(
            title="🚑 FORMULAIRE DE CANDIDATURE EMS",
            description=(
                f"Bienvenue **{interaction.user.mention}** ! 👋\n\n"
                f"**📋 Informations :**\n"
                f"• {len(QUESTIONS)} questions\n"
                f"• 10 minutes par question\n"
                f"• Documents requis à la fin\n\n"
                f"**Bonne chance ! 💪**"
            ),
            color=EMS_RED
        )
        welcome.set_footer(text="🚑 EMS System")
        await channel.send(embed=welcome)
        await asyncio.sleep(2)
        
        # Questions
        answers = []
        user_fullname = None
        
        for i, question in enumerate(QUESTIONS, 1):
            q_embed = discord.Embed(
                title=f"❓ QUESTION {i}/{len(QUESTIONS)}",
                description=question,
                color=EMS_RED
            )
            q_embed.add_field(name="⏱️ Temps", value="10 minutes", inline=False)
            q_embed.set_footer(text="🚑 EMS System")
            await channel.send(embed=q_embed)
            
            def check(m):
                return m.author == interaction.user and m.channel == channel
            
            try:
                msg = await bot.wait_for('message', check=check, timeout=600)
                
                if i == 1:
                    user_fullname = msg.content
                
                answers.append(f"**{question}**\n{msg.content}")
            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(
                    title="⏱️ TEMPS ÉCOULÉ - FERMETURE AUTOMATIQUE",
                    description=(
                        "❌ **Aucune réponse reçue dans les 10 minutes.**\n\n"
                        "Votre dossier de candidature va être **fermé automatiquement**.\n\n"
                        "Si vous souhaitez postuler à nouveau, cliquez sur le bouton de candidature.\n\n"
                        "🚑 **Fermeture dans 5 secondes...**"
                    ),
                    color=EMS_DARK_RED
                )
                timeout_embed.set_footer(text="🚑 EMS System | Session expirée")
                await channel.send(embed=timeout_embed)
                await asyncio.sleep(5)
                try:
                    await channel.delete()
                except:
                    pass
                return
        
        # Documents
        docs_embed = discord.Embed(
            title="📎 DOCUMENTS REQUIS",
            description=(
                "Merci pour vos réponses ! 🎉\n\n"
                "**Il manque :**\n"
                "🆔 Carte d'identité\n"
                "🚗 Permis de conduire\n\n"
                "Envoyez-les maintenant !"
            ),
            color=EMS_RED
        )
        docs_embed.set_footer(text="🚑 EMS System")
        await channel.send(embed=docs_embed)
        
        attachments = []
        
        def check_doc(m):
            return m.author == interaction.user and m.channel == channel
        
        try:
            msg = await bot.wait_for('message', check=check_doc, timeout=None)
            
            if msg.attachments:
                for att in msg.attachments:
                    attachments.append(att.url)
            
            confirm_embed = discord.Embed(
                title="✅ CANDIDATURE COMPLÈTE",
                description=(
                    "🎉 Candidature reçue !\n\n"
                    f"**Documents :** {len(attachments)}\n\n"
                    "La direction va examiner votre dossier.\n"
                    "Vous recevrez une réponse en DM.\n\n"
                    "⏱️ Ce channel se fermera dans **2 minutes**\n\n"
                    "Merci ! 🚑"
                ),
                color=EMS_RED
            )
            confirm_embed.set_footer(text="🚑 EMS System")
            await channel.send(embed=confirm_embed)
            
            # DM candidat
            try:
                await interaction.user.send(
                    "🚑 **Candidature envoyée** 🚑\n\n"
                    "Nous avons bien reçu votre candidature.\n\n"
                    "Réponse prochainement.\n\n"
                    "Merci ! 👨‍⚕️"
                )
            except:
                pass
            
            # Envoyer au channel CV (pendant que le timer démarre)
            cv_channel = bot.get_channel(1460755743228825641)
            if cv_channel:
                full_text = "\n\n".join(answers)
                cv_embed = discord.Embed(
                    title=f"📋 CANDIDATURE - {user_fullname if user_fullname else interaction.user.name}",
                    description=full_text[:2000],
                    color=EMS_RED
                )
                
                if attachments:
                    cv_embed.add_field(name="📎 Documents", value="\n".join([f"[Doc {i}]({url})" for i, url in enumerate(attachments, 1)]), inline=False)
                
                cv_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
                cv_embed.set_footer(text=f"🚑 EMS System | ID: {user_id}")
                
                view = FormulaireCVValidation(interaction.user)
                
                # Ping direction
                direction_role = guild.get_role(config.get("ROLE_DIRECTION_ID"))
                ping_content = direction_role.mention if direction_role else None
                
                try:
                    msg = await cv_channel.send(content=ping_content, embed=cv_embed, view=view)
                    view.message = msg
                    print(f"✅ FormulaireCVButton: CV envoyé dans {cv_channel.name} pour {interaction.user.name}")
                except Exception as e:
                    print(f"❌ FormulaireCVButton: Erreur envoi CV: {e}")
            else:
                print(f"❌ FormulaireCVButton: Channel CV non trouvé (ID: 1460755743228825641)")
            
            # Fermer le channel après 2 minutes
            await asyncio.sleep(120)
            try:
                await channel.delete()
            except:
                pass
        except:
            # En cas d'erreur, fermer quand même après 2 min
            await asyncio.sleep(120)
            try:
                await channel.delete()
            except:
                pass

@bot.tree.command(name="setup_cv", description="Affiche le bouton de dépôt de CV")
@app_commands.checks.has_permissions(administrator=True)
async def setup_cv(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="🚑 RECRUTEMENT EMS",
        description=(
            "**Rejoignez notre équipe !**\n\n"
            "Cliquez sur le bouton ci-dessous pour déposer votre candidature.\n\n"
            "**📋 Processus de recrutement :**\n"
            "1️⃣ Cliquez sur le bouton\n"
            "2️⃣ Répondez aux 13 questions\n"
            "3️⃣ Envoyez vos documents (ID, permis)\n"
            "4️⃣ Attendez la validation de la direction\n\n"
            "**Bonne chance ! 🚑💪**"
        ),
        color=EMS_RED
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    embed.set_footer(text="🚑 EMS Management System")
    
    view = CVButton()
    
    try:
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("✅ Bouton de CV posté !", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

@bot.tree.command(name="formulairecv", description="Affiche le nouveau formulaire de candidature")
@app_commands.checks.has_permissions(administrator=True)
async def formulairecv(interaction: discord.Interaction):
    # Defer immédiatement pour éviter le timeout
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="🚑 RECRUTEMENT EMS",
        description=(
            "**Rejoignez notre équipe !**\n\n"
            "Cliquez sur le bouton pour déposer votre candidature.\n\n"
            "**📋 Processus :**\n"
            "1️⃣ Cliquez sur le bouton\n"
            "2️⃣ Répondez aux 13 questions\n"
            "3️⃣ Envoyez vos documents\n"
            "4️⃣ Attendez la validation\n\n"
            "**Bonne chance ! 🚑💪**"
        ),
        color=EMS_RED
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    embed.set_footer(text="🚑 EMS System")
    
    view = FormulaireCVButton()
    
    try:
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("✅ Formulaire posté !", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

# --- SYSTÈME DE RESET MEMBRE ---
class ResetMemberButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔄 Réinitialiser mon compte", style=discord.ButtonStyle.danger, custom_id="reset_member")
    async def reset_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user
        
        try:
            # Reset le pseudo
            try:
                await member.edit(nick=None)
            except:
                pass
            
            # Récupérer tous les rôles sauf @everyone et le rôle de base
            roles_to_remove = [role for role in member.roles if role.id != guild.default_role.id and role.id != ROLE_BASE_ID]
            
            # Retirer tous les rôles sauf le rôle de base
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Réinitialisation du compte")
            
            # Confirmation
            embed = discord.Embed(
                title="✅ COMPTE RÉINITIALISÉ",
                description=(
                    "Votre compte a été réinitialisé avec succès !\n\n"
                    "**Actions effectuées :**\n"
                    "✅ Pseudo réinitialisé\n"
                    f"✅ {len(roles_to_remove)} rôle(s) retiré(s)\n\n"
                    "Vous pouvez maintenant repartir de zéro ! 🚀"
                ),
                color=EMS_RED
            )
            embed.set_footer(text="🚑 EMS System")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Log
            log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
            if log_channel:
                log_embed = discord.Embed(
                    title="🔄 RÉINITIALISATION MEMBRE",
                    description=f"**Membre :** {member.mention}\n**Rôles retirés :** {len(roles_to_remove)}",
                    color=EMS_RED
                )
                log_embed.set_footer(text="🚑 EMS System")
                await log_channel.send(embed=log_embed)
                
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ ERREUR",
                description=f"Impossible de réinitialiser le compte :\n```{e}```",
                color=EMS_DARK_RED
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

@bot.tree.command(name="setup_reset", description="Affiche le bouton de réinitialisation")
@app_commands.checks.has_permissions(administrator=True)
async def setup_reset(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="🔄 RÉINITIALISATION DU COMPTE",
        description=(
            "**Attention : Action irréversible !**\n\n"
            "En cliquant sur le bouton ci-dessous, vous allez :\n\n"
            "🔸 **Réinitialiser votre pseudo**\n"
            "🔸 **Perdre tous vos rôles** (sauf le rôle de base)\n\n"
            "⚠️ **Cette action est définitive !**\n\n"
            "Utilisez cette option uniquement si vous souhaitez repartir de zéro."
        ),
        color=EMS_DARK_RED
    )
    embed.set_footer(text="🚑 EMS System | Réfléchissez bien avant de cliquer")
    
    view = ResetMemberButton()
    
    try:
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("✅ Bouton de réinitialisation posté !", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

# --- SYSTÈME DE GIVEAWAY ---
@bot.tree.command(name="giveaway", description="Créer un giveaway")
@app_commands.describe(
    montant="Montant de la récompense en $",
    gagnants="Nombre de gagnants",
    date="Date de fin (format: JJ/MM/AAAA)",
    heure="Heure de fin (format: HH:MM)"
)
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(
    interaction: discord.Interaction,
    montant: int,
    gagnants: int,
    date: str,
    heure: str
):
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Parser la date et l'heure
        date_parts = date.split('/')
        heure_parts = heure.split(':')
        
        if len(date_parts) != 3 or len(heure_parts) != 2:
            await interaction.followup.send("❌ Format invalide. Utilisez JJ/MM/AAAA pour la date et HH:MM pour l'heure", ephemeral=True)
            return
        
        day, month, year = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
        hour, minute = int(heure_parts[0]), int(heure_parts[1])
        
        end_time = datetime(year, month, day, hour, minute)
        
        # Vérifier que la date est dans le futur
        if end_time <= datetime.now():
            await interaction.followup.send("❌ La date de fin doit être dans le futur", ephemeral=True)
            return
        
        # Créer l'embed du giveaway
        timestamp = int(end_time.timestamp())
        
        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            description=(
                f"**💰 Récompense : {montant:,}$**\n\n"
                f"**🏆 Nombre de gagnants : {gagnants}**\n\n"
                f"**📅 Fin du giveaway : <t:{timestamp}:F>**\n"
                f"**⏰ Dans : <t:{timestamp}:R>**\n\n"
                f"**Comment participer ?**\n"
                f"Réagissez avec 🎉 pour participer !\n\n"
                f"Bonne chance à tous ! 🍀"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="🎉 Giveaway System")
        
        # Ping le rôle
        role = interaction.guild.get_role(GIVEAWAY_PING_ROLE_ID)
        ping_content = role.mention if role else None
        
        # Envoyer le message
        msg = await interaction.channel.send(content=ping_content, embed=embed)
        
        # Ajouter la réaction
        await msg.add_reaction("🎉")
        
        # Sauvegarder le giveaway
        giveaways = load_giveaways()
        giveaways[str(msg.id)] = {
            "channel_id": interaction.channel.id,
            "message_id": msg.id,
            "montant": montant,
            "gagnants": gagnants,
            "end_time": end_time.isoformat(),
            "host_id": interaction.user.id,
            "ended": False
        }
        save_giveaways(giveaways)
        
        await interaction.followup.send("✅ Giveaway créé avec succès !", ephemeral=True)
        
    except ValueError as e:
        await interaction.followup.send(f"❌ Erreur de format : {e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

# Tâche pour vérifier les giveaways actifs
@tasks.loop(seconds=30)
async def check_giveaways():
    """Vérifie les giveaways actifs et termine ceux qui sont expirés"""
    try:
        giveaways = load_giveaways()
        now = datetime.now()
        
        for msg_id, data in list(giveaways.items()):
            if data.get("ended", False):
                continue
            
            end_time = datetime.fromisoformat(data["end_time"])
            
            if now >= end_time:
                # Le giveaway est terminé
                channel = bot.get_channel(data["channel_id"])
                if not channel:
                    continue
                
                try:
                    message = await channel.fetch_message(data["message_id"])
                except:
                    continue
                
                # Récupérer les participants (ceux qui ont réagi avec 🎉)
                participants = []
                for reaction in message.reactions:
                    if str(reaction.emoji) == "🎉":
                        async for user in reaction.users():
                            if not user.bot:
                                participants.append(user)
                        break
                
                if len(participants) == 0:
                    # Aucun participant
                    embed = discord.Embed(
                        title="🎉 GIVEAWAY TERMINÉ",
                        description=(
                            f"**💰 Récompense : {data['montant']:,}$**\n\n"
                            f"❌ **Aucun participant !**\n\n"
                            f"Le giveaway n'a pas pu être complété."
                        ),
                        color=EMS_DARK_RED
                    )
                    await message.edit(embed=embed)
                else:
                    # Sélectionner les gagnants
                    import random
                    nb_gagnants = min(data["gagnants"], len(participants))
                    winners = random.sample(participants, nb_gagnants)
                    
                    # Créer l'embed des résultats
                    winners_mentions = "\n".join([f"🏆 {winner.mention}" for winner in winners])
                    
                    embed = discord.Embed(
                        title="🎉 GIVEAWAY TERMINÉ !",
                        description=(
                            f"**💰 Récompense : {data['montant']:,}$**\n\n"
                            f"**🏆 Gagnant(s) :**\n{winners_mentions}\n\n"
                            f"**Félicitations ! 🎊**"
                        ),
                        color=discord.Color.green()
                    )
                    embed.set_footer(text="🎉 Giveaway System")
                    await message.edit(embed=embed)
                    
                    # Annoncer les gagnants dans le channel
                    winners_pings = " ".join([winner.mention for winner in winners])
                    await channel.send(f"🎉 **Félicitations aux gagnants du giveaway !** 🎉\n\n{winners_pings}\n\n💰 Vous avez gagné **{data['montant']:,}$** !")
                    
                    # Envoyer un MP à l'hôte
                    host = bot.get_user(data["host_id"])
                    if host:
                        winners_list = "\n".join([f"• {winner.name} ({winner.id})" for winner in winners])
                        try:
                            await host.send(
                                f"🎉 **Giveaway terminé !**\n\n"
                                f"**Montant :** {data['montant']:,}$\n"
                                f"**Channel :** {channel.mention}\n\n"
                                f"**Gagnants ({nb_gagnants}) :**\n{winners_list}\n\n"
                                f"Les gagnants ont été annoncés dans le channel !"
                            )
                        except:
                            pass
                
                # Marquer comme terminé
                giveaways[msg_id]["ended"] = True
                save_giveaways(giveaways)
        
    except Exception as e:
        print(f"Erreur check_giveaways: {e}")

@check_giveaways.before_loop
async def before_check_giveaways():
    await bot.wait_until_ready()

# --- SYSTÈME DE DEMANDE DE RÔLE ---
class RoleRequestButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Demander un rôle", style=discord.ButtonStyle.primary, emoji="👮", custom_id="request_role")
    async def request_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📋 Traitement de votre demande...", ephemeral=True)
        
        guild = interaction.guild
        user_id = interaction.user.id
        
        # Créer un channel privé pour la demande
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        try:
            channel = await guild.create_text_channel(
                f"role-{user_id}",
                overwrites=overwrites,
                category=guild.get_channel(TICKET_CATEGORY_ID),
                topic=f"Demande de rôle - {interaction.user.name}"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la création du ticket : {e}", ephemeral=True)
            return
        
        await interaction.followup.send(f"✅ Ticket créé : {channel.mention}", ephemeral=True)
        
        # Message de bienvenue
        welcome = discord.Embed(
            title="👮 DEMANDE DE RÔLE",
            description=f"Bienvenue **{interaction.user.mention}** !\n\nVeuillez répondre aux questions suivantes pour obtenir votre rôle.",
            color=discord.Color.blue()
        )
        welcome.set_footer(text="🎯 Système de demande de rôle")
        await channel.send(embed=welcome)
        await asyncio.sleep(1)
        
        # Question 1 : Organisation
        q1 = discord.Embed(
            title="❓ QUESTION 1",
            description="**Quelle organisation rejoignez-vous ?**\n\nRépondez par :\n• `LSPD`\n• `BCSO`\n• `MARSHALL`\n• `TAXI`\n• `BURGERSHOT`",
            color=discord.Color.blue()
        )
        q1.set_footer(text="🎯 Système de demande de rôle")
        await channel.send(embed=q1)
        
        def check(m):
            return m.author == interaction.user and m.channel == channel
        
        # Attendre réponse organisation
        organization = None
        role_id = None
        prefix = None
        is_taxi = False
        is_burgershot = False
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=300)
            org_choice = msg.content.upper().strip()
            
            if org_choice == "LSPD":
                organization = "LSPD"
                role_id = ROLE_LSPD_ID
                prefix = "L"
            elif org_choice == "BCSO":
                organization = "BCSO"
                role_id = ROLE_BCSO_ID
                prefix = "B"
            elif org_choice == "MARSHALL":
                organization = "MARSHALL"
                role_id = ROLE_MARSHALL_ID
                prefix = "M"
            elif org_choice == "TAXI":
                organization = "TAXI"
                role_id = ROLE_TAXI_REQUEST_ID
                is_taxi = True
            elif org_choice == "BURGERSHOT":
                organization = "BURGERSHOT"
                role_id = BURGERSHOT_ROLE_ID
                is_burgershot = True
            else:
                error_msg = discord.Embed(
                    title="❌ ERREUR",
                    description="Organisation invalide. Le ticket va être fermé.",
                    color=discord.Color.red()
                )
                await channel.send(embed=error_msg)
                await asyncio.sleep(3)
                await channel.delete()
                return
            
            # Ajouter le rôle de l'organisation
            role = guild.get_role(role_id)
            if role:
                await interaction.user.add_roles(role)
            
            # Confirmation
            confirm_org = discord.Embed(
                title="✅ ORGANISATION CONFIRMÉE",
                description=f"Vous avez rejoint : **{organization}**\nRôle ajouté avec succès !",
                color=discord.Color.green()
            )
            await channel.send(embed=confirm_org)
            await asyncio.sleep(1)
            
        except asyncio.TimeoutError:
            timeout_msg = discord.Embed(
                title="⏱️ TEMPS ÉCOULÉ",
                description="Vous n'avez pas répondu à temps. Le ticket va être fermé.",
                color=discord.Color.red()
            )
            await channel.send(embed=timeout_msg)
            await asyncio.sleep(3)
            await channel.delete()
            return
        
        # Question 2 : Prénom + Nom
        question_num = 2
        q2 = discord.Embed(
            title=f"❓ QUESTION {question_num}",
            description="**Quel est votre prénom et nom ?**\n\nFormat : `Prénom Nom`\nExemple : `Paul Fera`",
            color=discord.Color.blue()
        )
        q2.set_footer(text="🎯 Système de demande de rôle")
        await channel.send(embed=q2)
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=300)
            full_name = msg.content.strip()
        except asyncio.TimeoutError:
            timeout_msg = discord.Embed(
                title="⏱️ TEMPS ÉCOULÉ",
                description="Vous n'avez pas répondu à temps. Le ticket va être fermé.",
                color=discord.Color.red()
            )
            await channel.send(embed=timeout_msg)
            await asyncio.sleep(3)
            await channel.delete()
            return
        
        # Question 3 : Matricule (sauf pour Taxi et BurgerShot)
        matricule = None
        if not is_taxi and not is_burgershot:
            question_num = 3
            q3 = discord.Embed(
                title=f"❓ QUESTION {question_num}",
                description="**Quel est votre matricule ?**\n\nFormat : `02`, `15`, etc.",
                color=discord.Color.blue()
            )
            q3.set_footer(text="🎯 Système de demande de rôle")
            await channel.send(embed=q3)
            
            try:
                msg = await bot.wait_for('message', check=check, timeout=300)
                matricule = msg.content.strip()
            except asyncio.TimeoutError:
                timeout_msg = discord.Embed(
                    title="⏱️ TEMPS ÉCOULÉ",
                    description="Vous n'avez pas répondu à temps. Le ticket va être fermé.",
                    color=discord.Color.red()
                )
                await channel.send(embed=timeout_msg)
                await asyncio.sleep(3)
                await channel.delete()
                return
        
        # Question 4 : Test d'aptitude
        question_num = 3 if (is_taxi or is_burgershot) else 4
        q4 = discord.Embed(
            title=f"❓ QUESTION {question_num}",
            description="**Avez-vous le test d'aptitude ?**\n\nRépondez par :\n• `oui`\n• `non`",
            color=discord.Color.blue()
        )
        q4.set_footer(text="🎯 Système de demande de rôle")
        await channel.send(embed=q4)
        
        has_test = False
        try:
            msg = await bot.wait_for('message', check=check, timeout=300)
            test_response = msg.content.lower().strip()
            
            if test_response in ["oui", "yes", "o", "y"]:
                has_test = True
            elif test_response in ["non", "no", "n"]:
                has_test = False
            else:
                error_msg = discord.Embed(
                    title="❌ ERREUR",
                    description="Réponse invalide. Le ticket va être fermé.",
                    color=discord.Color.red()
                )
                await channel.send(embed=error_msg)
                await asyncio.sleep(3)
                await channel.delete()
                return
        except asyncio.TimeoutError:
            timeout_msg = discord.Embed(
                title="⏱️ TEMPS ÉCOULÉ",
                description="Vous n'avez pas répondu à temps. Le ticket va être fermé.",
                color=discord.Color.red()
            )
            await channel.send(embed=timeout_msg)
            await asyncio.sleep(3)
            await channel.delete()
            return
        
        # Appliquer les changements
        # 1. Changer le pseudo
        if is_taxi or is_burgershot:
            new_nickname = full_name
        else:
            new_nickname = f"{prefix}.{matricule} {full_name}"
        
        try:
            await interaction.user.edit(nick=new_nickname)
        except Exception as e:
            print(f"Erreur changement pseudo: {e}")
        
        # 2. Ajouter le rôle si pas de test
        if not has_test:
            no_test_role = guild.get_role(ROLE_NO_TEST_ID)
            if no_test_role:
                try:
                    await interaction.user.add_roles(no_test_role)
                except Exception as e:
                    print(f"Erreur ajout rôle sans test: {e}")
        
        # Message de confirmation finale
        if is_taxi:
            final_msg = discord.Embed(
                title="✅ DEMANDE COMPLÉTÉE",
                description=(
                    f"**Votre profil a été configuré avec succès !**\n\n"
                    f"**Organisation :** {organization}\n"
                    f"**Pseudo :** `{new_nickname}`\n"
                    f"**Test d'aptitude :** {'✅ Oui' if has_test else '❌ Non'}\n\n"
                    f"Bienvenue dans l'équipe Taxi ! 🚕"
                ),
                color=discord.Color.green()
            )
        elif is_burgershot:
            final_msg = discord.Embed(
                title="✅ DEMANDE COMPLÉTÉE",
                description=(
                    f"**Votre profil a été configuré avec succès !**\n\n"
                    f"**Organisation :** {organization}\n"
                    f"**Pseudo :** `{new_nickname}`\n"
                    f"**Test d'aptitude :** {'✅ Oui' if has_test else '❌ Non'}\n\n"
                    f"Bienvenue chez BurgerShot ! 🍔"
                ),
                color=discord.Color.green()
            )
        else:
            final_msg = discord.Embed(
                title="✅ DEMANDE COMPLÉTÉE",
                description=(
                    f"**Votre profil a été configuré avec succès !**\n\n"
                    f"**Organisation :** {organization}\n"
                    f"**Pseudo :** `{new_nickname}`\n"
                    f"**Test d'aptitude :** {'✅ Oui' if has_test else '❌ Non'}\n\n"
                    f"Bienvenue dans l'équipe ! 🎉"
                ),
                color=discord.Color.green()
            )
        final_msg.set_footer(text="🎯 Système de demande de rôle")
        await channel.send(embed=final_msg)
        
        # Fermer le ticket après 10 secondes
        await asyncio.sleep(10)
        try:
            await channel.delete()
        except:
            pass

@bot.tree.command(name="setup_role_request", description="Affiche le bouton de demande de rôle")
@app_commands.checks.has_permissions(administrator=True)
async def setup_role_request(interaction: discord.Interaction):
    embed = discord.Embed(
        title="👮 DEMANDE DE RÔLE",
        description=(
            "**Obtenez votre rôle d'organisation !**\n\n"
            "Cliquez sur le bouton ci-dessous pour faire votre demande.\n\n"
            "**📋 Informations requises :**\n"
            "• Organisation (LSPD/BCSO/MARSHALL/TAXI/BURGERSHOT)\n"
            "• Prénom et nom\n"
            "• Matricule (sauf Taxi/BurgerShot)\n"
            "• Test d'aptitude (oui/non)\n\n"
            "**Le système configurera automatiquement votre profil !**"
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text="🎯 Système de demande de rôle")
    await interaction.channel.send(embed=embed, view=RoleRequestButton())
    await interaction.response.send_message("✅ Message de demande de rôle posté !", ephemeral=True)

# --- SYSTÈME DE TICKETS DE RENDEZ-VOUS ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Fermeture du ticket...", ephemeral=True)
        
        close_msg = discord.Embed(
            title="🔒 TICKET FERMÉ",
            description=f"Ce ticket a été fermé par {interaction.user.mention}.\nLe channel sera supprimé dans 5 secondes.",
            color=discord.Color.red()
        )
        await interaction.channel.send(embed=close_msg)
        
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception as e:
            print(f"Erreur suppression ticket: {e}")

class AppointmentButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Prendre rendez-vous", style=discord.ButtonStyle.green, emoji="📅", custom_id="appointment_ticket")
    async def create_appointment(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📅 Création de votre ticket...", ephemeral=True)
        
        guild = interaction.guild
        user_id = interaction.user.id
        
        # Vérifier si l'utilisateur a déjà un ticket ouvert
        for channel in guild.text_channels:
            if channel.name == f"rdv-{user_id}":
                await interaction.followup.send(f"❌ Vous avez déjà un ticket ouvert : {channel.mention}", ephemeral=True)
                return
        
        # Créer un channel pour le rendez-vous
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        try:
            channel = await guild.create_text_channel(
                f"rdv-{user_id}",
                overwrites=overwrites,
                category=guild.get_channel(TICKET_CATEGORY_ID),
                topic=f"Rendez-vous - {interaction.user.name}"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la création du ticket : {e}", ephemeral=True)
            return
        
        await interaction.followup.send(f"✅ Ticket créé : {channel.mention}", ephemeral=True)
        
        # Message de bienvenue avec bouton de fermeture
        welcome = discord.Embed(
            title="📅 PRISE DE RENDEZ-VOUS",
            description=(
                f"Bienvenue **{interaction.user.mention}** !\n\n"
                f"Merci d'avoir ouvert un ticket de rendez-vous.\n"
                f"Un membre de l'équipe vous répondra sous peu.\n\n"
                f"**En attendant, vous pouvez :**\n"
                f"• Expliquer la raison de votre demande\n"
                f"• Indiquer vos disponibilités\n"
                f"• Poser vos questions\n\n"
                f"Pour fermer ce ticket, cliquez sur le bouton ci-dessous."
            ),
            color=discord.Color.green()
        )
        welcome.set_footer(text="📅 Système de tickets")
        await channel.send(embed=welcome, view=CloseTicketView())

@bot.tree.command(name="setup_appointment", description="Affiche le bouton de prise de rendez-vous")
@app_commands.checks.has_permissions(administrator=True)
async def setup_appointment(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📅 PRISE DE RENDEZ-VOUS",
        description=(
            "**Besoin d'un rendez-vous ?**\n\n"
            "Cliquez sur le bouton ci-dessous pour ouvrir un ticket.\n\n"
            "**📋 Un membre de l'équipe vous répondra rapidement pour :**\n"
            "• Fixer une date et heure\n"
            "• Répondre à vos questions\n"
            "• Organiser votre rendez-vous\n\n"
            "**N'hésitez pas à nous contacter ! 📞**"
        ),
        color=discord.Color.green()
    )
    embed.set_footer(text="📅 Système de tickets")
    await interaction.channel.send(embed=embed, view=AppointmentButton())
    await interaction.response.send_message("✅ Message de prise de rendez-vous posté !", ephemeral=True)

@bot.event
async def on_error(event, *args, **kwargs):
    """Gestionnaire d'erreurs global"""
    import sys
    import traceback
    print(f"❌ Erreur dans {event}:", file=sys.stderr)
    traceback.print_exc()

@bot.event
async def on_message(message):
    """Compte les réas quand un utilisateur envoie une réa avec pièces jointes"""
    # Ignorer les messages du bot
    if message.author.bot:
        return
    
    # Ignorer les messages sans pièces jointes
    if not message.attachments:
        await bot.process_commands(message)
        return
    
    try:
        # Obtenir le channel et l'employé associé
        channel = message.channel
        if not channel or not channel.name:
            await bot.process_commands(message)
            return
        
        # Vérifier que c'est un channel EMS (commence par emoji)
        if not (channel.name and len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]):
            await bot.process_commands(message)
            return
        
        # Obtenir la clé employé du channel
        employee_key = get_channel_employee_key(channel)
        if not employee_key:
            await bot.process_commands(message)
            return
        
        # Charger les stats
        stats = load_stats()
        
        # Incrémenter le compteur
        if employee_key not in stats:
            stats[employee_key] = 0
        
        stats[employee_key] += 1
        current_count = stats[employee_key]
        
        # Sauvegarder les stats
        save_stats(stats)
        
        # Ajouter réaction ✅
        try:
            await message.add_reaction("✅")
        except:
            pass
        
        # Mettre à jour la couleur du channel si nécessaire
        try:
            current_emoji = channel.name[0]
            new_emoji = get_color_emoji(current_count)
            
            if current_emoji != new_emoji:
                new_channel_name = f"{new_emoji}{channel.name[1:]}"
                await channel.edit(name=new_channel_name)
        except:
            pass
        
        # Mettre à jour la description du channel
        try:
            emoji = get_color_emoji(current_count)
            
            # Vérifier les bonus (entre 21h et 23h)
            now = datetime.now()
            is_bonus_time = 21 <= now.hour < 23
            bonus_text = ""
            
            if is_bonus_time:
                if award_bonus(employee_key):
                    bonus_text = " 1M NEW"
                else:
                    bonus_text = " 1M"
            
            description = f"{emoji} {current_count}/100{bonus_text}"
            await channel.edit(topic=description)
        except:
            pass
        
        # Envoyer log
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            try:
                emoji = get_color_emoji(current_count)
                message_text = f"✅ **{employee_key}** | {current_count} réas"
                await log_channel.send(message_text)
            except:
                pass
    
    except Exception as e:
        print(f"❌ Erreur on_message: {e}")
    
    # Traiter les commandes slash
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'✅ Bot: {bot.user}')
    
    # Charger les stats existantes
    stats = load_stats()
    print(f'📊 Stats chargées: {len(stats)} employés, {sum(stats.values())} réas totales')
    
    # MISE À JOUR AUTOMATIQUE DES DESCRIPTIONS DES CHANNELS (avec bonus)
    try:
        guild = bot.get_guild(config["GUILD_ID"])
        if guild:
            updated_count = 0
            for key, value in stats.items():
                # Chercher le channel correspondant
                displayname = key.replace("-", " ").title()
                channel = discord.utils.get(guild.text_channels, name=displayname)
                
                if channel:
                    try:
                        emoji = get_color_emoji(value)
                        
                        # Ajouter les bonus si entre 21h-23h
                        bonus_text = ""
                        now = datetime.now()
                        if 21 <= now.hour < 23:
                            # C'est entre 21h et 23h
                            if award_bonus(key):  # Première réa de la journée
                                bonus_text = " 1M NEW"
                            else:
                                bonus_text = " 1M"
                        
                        description = f"{emoji} {value}/100{bonus_text}"
                        await channel.edit(topic=description)
                        updated_count += 1
                    except:
                        pass
            
            if updated_count > 0:
                print(f'✅ Descriptions mises à jour: {updated_count}/{len(stats)} channels')
    except Exception as e:
        print(f'⚠️ Erreur mise à jour descriptions: {e}')
    
    # Créer un backup des stats au démarrage
    if stats:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"stats_backup_{timestamp}.json"
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            print(f'💾 Backup créé: {backup_path}')
        except Exception as e:
            print(f'⚠️ Erreur backup: {e}')
    
    print('✅ Bot prêt - Sauvegarde automatique activée')

# --- TÂCHE AUTOMATISÉE HEBDOMADAIRE TAXI ---
@tasks.loop(hours=1)
async def weekly_taxi_announcement():
    """Vérifie si c'est samedi 19h et envoie l'annonce hebdomadaire"""
    now = datetime.now()
    
    # Vérifier si c'est samedi (weekday() == 5) et qu'il est 19h
    if now.weekday() == 5 and now.hour == 19:
        try:
            await send_weekly_taxi_announcement()
        except Exception as e:
            print(f"Erreur annonce taxi hebdo: {e}")

@weekly_taxi_announcement.before_loop
async def before_weekly_announcement():
    await bot.wait_until_ready()

# --- TÂCHE DE SAUVEGARDE AUTOMATIQUE ---
@tasks.loop(minutes=5)
async def auto_backup_stats():
    """Sauvegarde automatique des stats toutes les 5 minutes pour éviter toute perte de données"""
    try:
        stats = load_stats()
        # Force une sauvegarde avec backup
        atomic_write_json(STATS_FILE, stats, make_backup=True)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Sauvegarde automatique des stats effectuée ({len(stats)} employés, {sum(stats.values())} réas)")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur sauvegarde automatique: {e}")

@auto_backup_stats.before_loop
async def before_auto_backup():
    await bot.wait_until_ready()

async def send_weekly_taxi_announcement():
    """Envoie l'annonce hebdomadaire et réinitialise les compteurs"""
    guild = bot.get_guild(config.get("GUILD_ID"))
    if not guild:
        return
    
    taxi_channel = bot.get_channel(TAXI_CHANNEL_ID)
    if not taxi_channel:
        return
    
    # Charger les stats de la semaine
    taxi_stats = load_taxi_stats()
    count = taxi_stats.get("count", 0)
    revenus = count * 500000
    
    # Créer l'annonce
    embed = discord.Embed(
        title="🚕 RAPPORT HEBDOMADAIRE TAXI",
        description="**📊 Bilan de la semaine**\n\n",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="👥 Employés acceptés",
        value=f"```{count} employé(s)```",
        inline=False
    )
    
    embed.add_field(
        name="💰 Revenus générés",
        value=f"```{revenus:,.0f}$```".replace(",", " "),
        inline=False
    )
    
    embed.add_field(
        name="📈 Performance",
        value=f"Cette semaine, nous avons accepté **{count}** employé(s) !\n"
              f"Cela représente un revenu total de **{revenus:,.0f}$** 💵".replace(",", " "),
        inline=False
    )
    
    embed.set_footer(text="🚕 Taxi Management System | Nouvelle semaine qui commence !")
    embed.timestamp = datetime.now()
    
    # Ping les rôles de direction
    role_ems = guild.get_role(ROLE_DIRECTION_EMS_ID)
    role_taxi = guild.get_role(ROLE_DIRECTION_TAXI_ID)
    
    ping_text = ""
    if role_ems:
        ping_text += f"{role_ems.mention} "
    if role_taxi:
        ping_text += f"{role_taxi.mention}"
    
    # Envoyer l'annonce
    try:
        await taxi_channel.send(content=ping_text, embed=embed)
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'annonce taxi : {e}")
    
    # Réinitialiser les stats pour la nouvelle semaine
    reset_taxi_week()
    print(f"✅ Annonce hebdomadaire taxi envoyée et compteurs réinitialisés")


# --- GESTION DES CANAUX UTILISATEURS ---
def load_channel_map():
    return robust_load_json(CHANNEL_MAP_FILE, {})

def save_channel_map(data):
    atomic_write_json(CHANNEL_MAP_FILE, data)

def get_clean_name(member):
    """Récupère le nom sans le tag entre crochets"""
    display_name = member.display_name
    if ']' in display_name:
        try:
            return display_name.split(']')[1].strip()
        except IndexError:
            return display_name
    return display_name

# --- RÉCUPÉRATION DES STATS DEPUIS LES LOGS ---
async def sync_stats_from_logs():
    """Récupère les stats depuis le channel de logs pour éviter la perte de données au redémarrage"""
    try:
        LOGS_SYNC_CHANNEL_ID = 1458464678542970983
        log_channel = bot.get_channel(LOGS_SYNC_CHANNEL_ID)
        
        if not log_channel:
            print(f"❌ Channel de logs introuvable (ID: {LOGS_SYNC_CHANNEL_ID})")
            return
        
        print("🔄 Synchronisation des stats depuis les logs...")
        
        # Dictionnaire pour stocker les stats récupérées
        recovered_stats = {}
        
        # Lire les 1000 derniers messages du channel (limite Discord)
        async for message in log_channel.history(limit=1000):
            # Format attendu: "✅ **employee_key** | X réas"
            if message.content.startswith("✅ **") and " réas" in message.content:
                try:
                    # Extraire l'employé et le nombre de réas
                    parts = message.content.split("**")
                    if len(parts) >= 3:
                        employee_key = parts[1].strip()
                        
                        # Extraire le nombre de réas
                        rea_part = message.content.split("|")[1].strip()
                        rea_count = int(rea_part.split()[0])
                        
                        # Garder la valeur la plus récente (plus haute)
                        if employee_key not in recovered_stats or rea_count > recovered_stats[employee_key]:
                            recovered_stats[employee_key] = rea_count
                except Exception as e:
                    continue
        
        if recovered_stats:
            # Sauvegarder les stats récupérées
            save_stats(recovered_stats)
            print(f"✅ Stats synchronisées depuis les logs: {len(recovered_stats)} employés")
            
            # Afficher un résumé
            total_reas = sum(recovered_stats.values())
            print(f"📊 Total des réas récupérées: {total_reas}")
        else:
            print("⚠️ Aucune stat trouvée dans les logs")
            
    except Exception as e:
        print(f"❌ Erreur lors de la synchronisation des stats: {e}")

# --- COMMANDES DE MANAGEMENT EMS ---

@bot.tree.command(name="clean_channels", description="Supprime les préfixes de grade (emt-, int-, dir-, etc.) de tous les channels")
@app_commands.checks.has_permissions(administrator=True)
async def clean_channels(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    renamed_count = 0
    errors = []
    renamed_list = []
    
    # Parcourir tous les channels avec emoji
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]:
            try:
                # Extraire le nom actuel sans l'emoji
                current_name_without_emoji = channel.name[1:].strip() if len(channel.name) > 1 else channel.name
                
                # Normaliser pour obtenir le nom propre (sans préfixe)
                clean_employee_name = normalize_employee_key(current_name_without_emoji)
                
                # Nouveau nom: emoji + nom propre
                current_emoji = channel.name[0]
                new_name = f"{current_emoji}{clean_employee_name}"
                
                # Renommer seulement si différent
                if channel.name != new_name:
                    old_name = channel.name
                    await channel.edit(name=new_name)
                    renamed_count += 1
                    renamed_list.append(f"• `{old_name}` → `{new_name}`")
                    
            except Exception as e:
                errors.append(f"❌ {channel.name}: {str(e)[:50]}")
    
    # Message de confirmation
    embed = discord.Embed(
        title="🧹 NETTOYAGE DES CHANNELS",
        description=f"**{renamed_count} channel(s) renommé(s)**\n\nTous les préfixes de grade (emt-, int-, dir-, cds-, etc.) ont été supprimés.",
        color=EMS_RED
    )
    
    if renamed_list:
        # Afficher les 15 premiers
        display_list = renamed_list[:15]
        if len(renamed_list) > 15:
            display_list.append(f"... et {len(renamed_list) - 15} autres")
        embed.add_field(
            name="📝 Channels renommés",
            value="\n".join(display_list),
            inline=False
        )
    
    if errors:
        embed.add_field(
            name="⚠️ Erreurs",
            value="\n".join(errors[:10]),
            inline=False
        )
    
    embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="setup_categories", description="Crée automatiquement toutes les catégories pour les grades EMS")
@app_commands.checks.has_permissions(administrator=True)
async def setup_categories(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # ID de la catégorie cible (on veut positionner au-dessus)
    TARGET_CATEGORY_ID = 838110173368418325
    
    # Définir les catégories à créer (ordre inversé : DIR en haut, EMT en bas)
    grade_names = [
        ("DIR", "CATEGORY_DIR_ID"),
        ("CDS", "CATEGORY_CDS_ID"),
        ("MED", "CATEGORY_MED_ID"),
        ("INF", "CATEGORY_INF_ID"),
        ("ADS", "CATEGORY_ADS_ID"),
        ("INT", "CATEGORY_INT_ID"),
        ("EMT", "CATEGORY_EMT_ID")
    ]
    
    categories_data = load_categories()
    created = []
    created_categories = []
    errors = []
    
    for grade_name, key in grade_names:
        try:
            # Créer la catégorie
            category = await guild.create_category(name=grade_name)
            categories_data[key] = category.id
            created.append(f"✅ {grade_name}: {category.id}")
            created_categories.append(category)
        except Exception as e:
            errors.append(f"❌ {grade_name}: {e}")
    
    # Sauvegarder les IDs
    if created:
        save_categories(categories_data)
        
        # Recharger les variables globales
        global CATEGORY_EMT_ID, CATEGORY_INT_ID, CATEGORY_ADS_ID, CATEGORY_INF_ID, CATEGORY_MED_ID, CATEGORY_CDS_ID, CATEGORY_DIR_ID
        CATEGORY_EMT_ID = categories_data.get("CATEGORY_EMT_ID", 0)
        CATEGORY_INT_ID = categories_data.get("CATEGORY_INT_ID", 0)
        CATEGORY_ADS_ID = categories_data.get("CATEGORY_ADS_ID", 0)
        CATEGORY_INF_ID = categories_data.get("CATEGORY_INF_ID", 0)
        CATEGORY_MED_ID = categories_data.get("CATEGORY_MED_ID", 0)
        CATEGORY_CDS_ID = categories_data.get("CATEGORY_CDS_ID", 0)
        CATEGORY_DIR_ID = categories_data.get("CATEGORY_DIR_ID", 0)
        
        # Positionner les catégories au-dessus de la catégorie cible
        target_category = guild.get_channel(TARGET_CATEGORY_ID)
        if target_category and created_categories:
            try:
                # Obtenir la position de la catégorie cible
                target_position = target_category.position
                
                # Positionner chaque catégorie créée dans l'ordre, juste au-dessus
                for i, category in enumerate(created_categories):
                    new_position = target_position + i
                    try:
                        await category.edit(position=new_position)
                    except Exception as e:
                        errors.append(f"⚠️ Erreur positionnement {category.name}: {e}")
                
                created.append(f"📍 Catégories positionnées au-dessus de la catégorie cible")
            except Exception as e:
                errors.append(f"⚠️ Erreur positionnement global: {e}")
    
    # Préparer le message de réponse
    embed = discord.Embed(
        title="🏗️ Configuration des Catégories",
        description="Création et positionnement des catégories pour chaque grade EMS",
        color=EMS_RED
    )
    
    if created:
        embed.add_field(name="✅ Catégories créées et positionnées", value="\n".join(created), inline=False)
    
    if errors:
        embed.add_field(name="❌ Erreurs", value="\n".join(errors), inline=False)
    
    embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="employer", description="Recruter un EMS (Création channel, rôles, rename)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="Le membre à employer")
async def employer(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.defer()
    
    guild = interaction.guild
    clean_name = get_clean_name(membre)
    
    # 1. Gestion du Pseudo
    new_nickname = f"[EMT] {clean_name}"
    try:
        await membre.edit(nick=new_nickname)
    except Exception as e:
        print(f"Erreur changement pseudo {membre}: {e}")

    # 2. Gestion des Rôles
    roles_add_ids = [838102445095256068, 895047492784238652, 838102445095256070]
    role_remove_id = 896103247096471613
    
    roles_to_add = [guild.get_role(rid) for rid in roles_add_ids if guild.get_role(rid)]
    role_to_remove = guild.get_role(role_remove_id)
    
    if roles_to_add:
        await membre.add_roles(*roles_to_add)
    if role_to_remove:
        await membre.remove_roles(role_to_remove)

    # 3. Création du Channel dans la catégorie EMT (sans préfixe de grade, juste emoji + nom)
    # Forcer la catégorie à 1460041009453858826
    category = guild.get_channel(1460041009453858826)
    channel_name = f"🔴{clean_name.lower().replace(' ', '-')}"

    if category:
        # Permissions pour que le membre ait accès à son channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            membre: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # Créer le channel avec les permissions dans la catégorie
        new_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)

        await interaction.followup.send(f"✅ **{membre.mention}** a été employé avec succès !\n📛 Renommé en `{new_nickname}`\n📂 Dossier créé : {new_channel.mention}")
    else:
        await interaction.followup.send(f"⚠️ Catégorie EMT (1460041009453858826) introuvable, rôles et pseudo mis à jour mais pas le channel.")

@bot.tree.command(name="reset_names", description="Applique les tags de grade selon les rôles Discord")
@app_commands.describe(membre="Le membre dont mettre à jour le tag (optionnel, sinon tous)")
@app_commands.checks.has_permissions(administrator=True)
async def reset_names(interaction: discord.Interaction, membre: discord.Member = None):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # Mapping des rôles Discord vers les tags de grade (du plus élevé au plus bas)
    role_hierarchy = [
        (838102445095256071, "[DIR]"),   # Direction
        (1088570974603055195, "[CDS]"),  # Chef de Service
        (840288242547818507, "[MED]"),   # Médecin
        (894311352225656862, "[INF]"),   # Infirmier
        (1088116715998687273, "[ADS]"),  # Aide-Soignant
        (838102445095256069, "[INT]"),   # Intérimaire
        (895047492784238652, "[EMT]"),   # EMT
    ]
    
    def get_grade_tag(member):
        """Retourne le tag de grade le plus élevé du membre"""
        member_role_ids = [role.id for role in member.roles]
        for role_id, tag in role_hierarchy:
            if role_id in member_role_ids:
                return tag
        return None
    
    if membre:
        # Mettre à jour un seul membre
        clean_name = get_clean_name(membre)
        grade_tag = get_grade_tag(membre)
        
        if grade_tag:
            new_nickname = f"{grade_tag} {clean_name}"
            try:
                await membre.edit(nick=new_nickname)
                embed = discord.Embed(
                    title="✅ Pseudo mis à jour",
                    description=f"{membre.mention} → `{new_nickname}`",
                    color=EMS_RED
                )
                embed.set_footer(text="🚑 EMS System")
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ Erreur : {e}")
        else:
            await interaction.followup.send(f"❌ {membre.mention} n'a aucun rôle EMS reconnu.")
    else:
        # Mettre à jour tous les membres avec des rôles EMS
        updated = []
        errors = []
        skipped = []
        
        for member in guild.members:
            if member.bot:
                continue
            
            grade_tag = get_grade_tag(member)
            
            if grade_tag:
                clean_name = get_clean_name(member)
                new_nickname = f"{grade_tag} {clean_name}"
                
                # Vérifier si le pseudo est déjà correct
                if member.display_name == new_nickname:
                    skipped.append(member.display_name)
                    continue
                
                try:
                    await member.edit(nick=new_nickname)
                    updated.append(f"✅ {member.mention} → `{new_nickname}`")
                except Exception as e:
                    errors.append(f"❌ {member.display_name}: {str(e)}")
        
        # Créer l'embed de résultat
        embed = discord.Embed(
            title="🔄 Mise à jour des pseudos selon les rôles",
            color=EMS_RED
        )
        
        if updated:
            # Limiter à 10 pour ne pas dépasser la limite d'embed
            display_updated = updated[:10]
            if len(updated) > 10:
                display_updated.append(f"... et {len(updated) - 10} autres")
            embed.add_field(
                name=f"✅ Pseudos mis à jour ({len(updated)})",
                value="\n".join(display_updated),
                inline=False
            )
        
        if skipped:
            embed.add_field(
                name=f"⏭️ Déjà à jour ({len(skipped)})",
                value=f"{len(skipped)} membres avaient déjà le bon pseudo",
                inline=False
            )
        
        if not updated and not errors:
            embed.description = "Aucun membre EMS à mettre à jour."
        
        if errors:
            display_errors = errors[:5]
            if len(errors) > 5:
                display_errors.append(f"... et {len(errors) - 5} autres erreurs")
            embed.add_field(
                name=f"❌ Erreurs ({len(errors)})",
                value="\n".join(display_errors),
                inline=False
            )
        
        embed.set_footer(text="🚑 EMS System")
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="virer", description="Virer un employé (Retrait rôles, reset pseudo)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="Le membre à virer")
async def virer(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.defer()
    
    guild = interaction.guild
    clean_name = get_clean_name(membre)
    
    # 1. Gestion des Rôles (Nettoyage complet EMS + Ajout chômeur/civil)
    # Liste des rôles EMS connus à retirer pour être propre
    ems_roles_ids = [
        895047492784238652, 838102445095256069, 1088116715998687273, 
        894311352225656862, 840288242547818507, 838102445095256071, 
        1088570974603055195, 838102445095256068, 838102445095256070
    ]
    role_target_id = 838102445095256066 # Role à garder/ajouter
    
    roles_to_remove = [r for r in membre.roles if r.id in ems_roles_ids]
    role_to_add = guild.get_role(role_target_id)
    
    if roles_to_remove:
        await membre.remove_roles(*roles_to_remove)
    if role_to_add:
        await membre.add_roles(role_to_add)
        
    # 2. Reset Pseudo (Enlever pseudo du serveur = remettre le nom global ou juste enlever le tag)
    # On remet juste le clean_name ou None pour reset au username discord
    try:
        await membre.edit(nick=None) 
    except:
        pass # Si on peut pas, tant pis

    # 3. Envoyer un message privé au membre viré
    try:
        await membre.send(
            f"Cher **{clean_name}**,\n\n"
            f"Nous regrettons de vous informer que, suite à une décision interne, vous êtes désormais licencié de l'hôpital de Los Santos.\n\n"
            f"Cette décision a été prise après analyse de certains éléments qui ne sont pas en adéquation avec les valeurs et le fonctionnement de notre service.\n\n"
            f"Nous vous remercions pour l'intérêt que vous avez porté à notre organisation et vous souhaitons bonne continuation dans vos projets.\n\n"
            f"Cordialement,\n**La Direction des EMS.**"
        )
    except Exception as e:
        print(f"Erreur envoi DM licenciement: {e}")

    # 4. Supprimer le channel personnel de l'employé
    channel_deleted = False
    clean_name_normalized = normalize_employee_key(clean_name)

    # Chercher le channel par nom normalisé (nouveau format: emoji + nom sans préfixe)
    for channel in guild.text_channels:
        if channel.name and len(channel.name) > 1 and channel.name[0] in ["🔴", "🟠", "🟢"]:
            # Obtenir la clé employé du channel
            channel_employee_key = get_channel_employee_key(channel)

            # Comparer avec la clé employé normalisée
            if channel_employee_key == clean_name_normalized:
                # Envoyer le message AVANT de supprimer le channel
                await interaction.followup.send(f"🚫 **{clean_name}** a été viré.\nRôles retirés, pseudo réinitialisé et channel supprimé.")
                try:
                    await channel.delete()
                    channel_deleted = True
                    break
                except Exception as e:
                    print(f"Erreur suppression channel: {e}")
    if not channel_deleted:
        await interaction.followup.send(f"🚫 **{clean_name}** a été viré.\nRôles retirés et pseudo réinitialisé.\n⚠️ Aucun channel personnel trouvé.")

@bot.tree.command(name="up", description="Promouvoir un employé au rang suivant")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="Le membre à promouvoir")
async def up(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.defer()
    guild = interaction.guild
    member_roles_ids = [r.id for r in membre.roles]
    clean_name = get_clean_name(membre)
    
    # Mapping des transitions
    # (Role Actuel -> Role Suivant, Nouveau Prefix, Prefix Channel, Ancre/Cible move, Regex Cible)
    
    # IDs des Rôles
    R_EMT = 895047492784238652
    R_INT = 838102445095256069
    R_ADS = 1088116715998687273
    R_INF = 894311352225656862
    R_MED = 840288242547818507
    R_CDS = 838102445095256071
    R_DIR = 1088570974603055195
    
    # Logique de promotion
    next_step = None
    
    # Note: On check du plus haut vers le plus bas ou l'inverse ?
    # On check le role actuel.
    
    if R_EMT in member_roles_ids:
        # EMT -> INT
        next_step = {
            "remove": R_EMT, "add": R_INT, 
            "tag": "INT",
            "category_id": CATEGORY_INT_ID
        }
    elif R_INT in member_roles_ids:
        # INT -> ADS
        next_step = {
            "remove": R_INT, "add": R_ADS,
            "tag": "ADS",
            "category_id": CATEGORY_ADS_ID
        }
    elif R_ADS in member_roles_ids:
        # ADS -> INF
        next_step = {
            "remove": R_ADS, "add": R_INF,
            "tag": "INF",
            "category_id": CATEGORY_INF_ID
        }
    elif R_INF in member_roles_ids:
        # INF -> MED
        next_step = {
            "remove": R_INF, "add": R_MED,
            "tag": "MED",
            "category_id": CATEGORY_MED_ID
        }
    elif R_MED in member_roles_ids:
        # MED -> CDS
        next_step = {
            "remove": R_MED, "add": R_CDS,
            "tag": "CDS",
            "category_id": CATEGORY_CDS_ID
        }
    elif R_CDS in member_roles_ids:
        # CDS -> DIR
        next_step = {
            "remove": R_CDS, "add": R_DIR,
            "tag": "DIR",
            "category_id": CATEGORY_DIR_ID
        }
    else:
        await interaction.followup.send("❌ Ce membre n'a pas de grade évolutif connu ou est déjà au max.")
        return

    # Appliquer les changements
    
    # 1. Rôles
    await membre.remove_roles(guild.get_role(next_step["remove"]))
    await membre.add_roles(guild.get_role(next_step["add"]))
    
    # 2. Pseudo
    new_nick = f"[{next_step['tag']}] {clean_name}"
    try:
        await membre.edit(nick=new_nick)
    except:
        pass # Admin check
        
    # 3. Channel - Trouver le channel de l'employé et le déplacer (sans changer le nom, juste retirer le préfixe)
    channel = None
    
    # Chercher le channel de l'employé
    clean_name_normalized = clean_name.lower().replace(' ', '-')
    for ch in guild.text_channels:
        if ch.name and len(ch.name) > 1 and ch.name[0] in ["🔴", "🟠", "🟢"]:
            # Enlever l'emoji et normaliser
            ch_employee_key = get_channel_employee_key(ch)
            member_key = normalize_employee_key(clean_name)
            if ch_employee_key == member_key:
                channel = ch
                break
    
    chan_msg = ""
    if channel:
        # Nouveau nom sans préfixe de grade, juste l'emoji + nom
        current_emoji = channel.name[0] if channel.name and len(channel.name) > 0 else "🔴"
        new_chan_name = f"{current_emoji}{clean_name_normalized}"
        
        # Déplacer dans la nouvelle catégorie
        new_category_id = next_step.get("category_id")
        new_category = guild.get_channel(new_category_id) if new_category_id else None
        
        if new_category:
            try:
                await channel.edit(name=new_chan_name, category=new_category)
                chan_msg = f"\n📂 Dossier déplacé dans la catégorie {next_step['tag']} : {channel.mention}"
            except Exception as e:
                chan_msg = f"\n⚠️ Erreur déplacement dossier: {e}"
        else:
            try:
                await channel.edit(name=new_chan_name)
                chan_msg = f"\n📂 Dossier renommé : {channel.mention} (catégorie {next_step['tag']} introuvable)"
            except Exception as e:
                chan_msg = f"\n⚠️ Erreur renommage: {e}"

    await interaction.followup.send(f"📈 **Promotion effectuée pour {membre.mention}** !\nPassage au grade **{next_step['tag']}**.{chan_msg}")

@bot.tree.command(name="payes", description="Calcul et annonce des salaires de la semaine")
@app_commands.checks.has_permissions(administrator=True)
async def payes(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # 1. Demander l'image du coffre
    ask_embed = discord.Embed(
        title="💰 CALCUL DES SALAIRES",
        description="**📸 Envoyez une capture d'écran du coffre (état avant les paiements)**\n\nVous avez 2 minutes pour envoyer l'image.",
        color=EMS_RED
    )
    ask_embed.set_footer(text="🚑 EMS System | Système de paie")
    await interaction.followup.send(embed=ask_embed)
    
    def check_image(m):
        return m.author == interaction.user and m.channel == interaction.channel and len(m.attachments) > 0
    
    coffre_image_file = None
    try:
        msg_image = await bot.wait_for('message', check=check_image, timeout=120)
        coffre_image_url = msg_image.attachments[0].url
        
        # Télécharger l'image pour l'attacher au message (évite l'expiration)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(coffre_image_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        coffre_image_file = discord.File(io.BytesIO(image_data), filename="coffre.png")
        except Exception as e:
            print(f"Erreur téléchargement image coffre: {e}")
    except asyncio.TimeoutError:
        timeout_embed = discord.Embed(
            title="⏱️ TEMPS ÉCOULÉ",
            description="Vous n'avez pas envoyé l'image à temps. Commande annulée.",
            color=EMS_DARK_RED
        )
        await interaction.followup.send(embed=timeout_embed)
        return
    
    # 2. Charger les stats
    stats = load_stats()
    
    # 3. Calculer les salaires pour tous les membres
    salary_data = []
    total_payroll = 0
    
    direction_role = guild.get_role(ROLE_DIRECTION_EMS_ID)
    
    for member in guild.members:
        if member.bot:
            continue
        
        # Vérifier d'abord si le membre a le rôle DIRECTION
        has_direction_role = direction_role in member.roles if direction_role else False
        
        if has_direction_role:
            # DIRECTION: 9M fixe, pas de calcul avec réas
            clean_name = get_clean_name(member)
            salary = 9000000
            total_payroll += salary
            
            salary_data.append({
                "name": clean_name,
                "rea": 0,  # Pas affiché pour direction
                "grade": "DIRECTION",
                "total": salary
            })
            continue
        
        # Détecter le grade par tag dans le pseudo pour les autres
        nick = member.display_name.upper()
        grade = None
        rate = 0
        
        if "[DIR]" in nick:
            grade = "DIR"
            rate = 55000
        elif "[CDS]" in nick:
            grade = "CDS"
            rate = 50000
        elif "[MED]" in nick:
            grade = "MED"
            rate = 45000
        elif "[INF]" in nick:
            grade = "INF"
            rate = 40000
        elif "[ADS]" in nick:
            grade = "ADS"
            rate = 40000
        elif "[INT]" in nick:
            grade = "INT"
            rate = 35000
        elif "[EMT]" in nick:
            grade = "EMT"
            rate = 30000
        else:
            continue  # Pas un employé EMS
        
        # Récupérer les réas (0 si absent)
        employee_key = normalize_employee_key(member.display_name)
        rea_count = stats.get(employee_key, 0)
        
        # Calculer le salaire: base + bonus
        base_salary = rea_count * rate
        bonus = 0
        if rea_count > 50:
            bonus = ((rea_count - 50) // 10) * 150000
        salary = base_salary + bonus
        
        total_payroll += salary
        
        # Ajouter à la liste
        clean_name = get_clean_name(member)
        salary_data.append({
            "name": clean_name,
            "rea": rea_count,
            "grade": grade,
            "total": salary
        })
    
    # 4. Trier par salaire décroissant
    salary_data.sort(key=lambda x: x["total"], reverse=True)
    
    # 5. Diviser en plusieurs embeds (10 employés par page pour éviter dépassement)
    embeds_to_send = []
    employees_per_embed = 10
    
    for i in range(0, len(salary_data), employees_per_embed):
        chunk = salary_data[i:i + employees_per_embed]
        page_num = (i // employees_per_embed) + 1
        total_pages = (len(salary_data) + employees_per_embed - 1) // employees_per_embed
        
        # Créer un embed pour ce groupe
        if i == 0:
            # Premier embed avec image du coffre
            chunk_embed = discord.Embed(
                title="💰 PAIEMENT DES SALAIRES",
                description="**📊 Récapitulatif des salaires de la semaine**\n",
                color=EMS_RED
            )
            if coffre_image_file:
                chunk_embed.set_image(url=f"attachment://{coffre_image_file.filename}")
        else:
            # Embeds suivants
            chunk_embed = discord.Embed(
                title=f"💰 PAIEMENT DES SALAIRES (suite)",
                description=f"**Page {page_num}/{total_pages}**\n",
                color=EMS_RED
            )
        
        # Construire le tableau pour ce groupe
        salary_text = "```\n"
        salary_text += f"{'NOM':<16} | {'R':<3} | {'GRD':<3} | {'TOTAL':>10}\n"
        salary_text += "-" * 42 + "\n"
        
        for emp in chunk:
            name_display = emp['name'][:14]
            grade_display = emp['grade'][:3]
            salary_text += f"{name_display:<16} | {emp['rea']:<3} | {grade_display:<3} | {emp['total']:>10,}$\n".replace(",", " ")
        
        salary_text += "```"
        
        chunk_embed.add_field(name=f"📋 Liste (Page {page_num}/{total_pages})", value=salary_text, inline=False)
        
        # Ajouter le total uniquement sur le dernier embed
        if i + employees_per_embed >= len(salary_data):
            chunk_embed.add_field(
                name="💵 TOTAL À RETIRER",
                value=f"```{total_payroll:,}$```".replace(",", " "),
                inline=False
            )
            chunk_embed.set_footer(text="🚑 EMS System | Bonne paie à tous !")
            chunk_embed.timestamp = datetime.now()
        else:
            chunk_embed.set_footer(text=f"🚑 EMS System | Page {page_num}/{total_pages}")
        
        embeds_to_send.append(chunk_embed)
    
    # 6. Envoyer tous les embeds dans le channel de logs
    log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
    if log_channel:
        for idx, embed in enumerate(embeds_to_send):
            try:
                if idx == 0 and coffre_image_file:
                    # Premier embed avec image du coffre
                    await log_channel.send(embed=embed, file=coffre_image_file)
                else:
                    await log_channel.send(embed=embed)
            except Exception as e:
                print(f"Erreur envoi annonce salaires (page {idx+1}): {e}")
    
    # 7. Réinitialiser la semaine (comme /semaine)
    # Réinitialiser stats
    save_stats({})
    
    # Mettre tous les channels en 🔴
    announcement_channels = []
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]:
            new_name = f"🔴{channel.name[1:]}"
            try:
                await channel.edit(name=new_name)
                announcement_channels.append(channel)
            except:
                pass
    
    # Embed d'annonce de nouvelle semaine
    week_embed = discord.Embed(
        title="🚑 NOUVELLE SEMAINE !",
        description="**✅ Salaires payés et semaine réinitialisée**\n\n• Tous les compteurs remis à 0\n• Tous les channels en 🔴\n• C'est repartit de zéro !\n\n**Bonne chance à tous ! 💪**",
        color=EMS_RED
    )
    week_embed.set_image(url="https://media.discordapp.net/attachments/1432501937085087896/1457439823215460487/image.png?ex=695ea51b&is=695d539b&hm=73669ae578193fac7bb528589592facb8ffa94a53f6521f1fad68165e393d32c&=&format=webp&quality=lossless&width=1872&height=571")
    week_embed.set_footer(text="🚑 EMS System | Nouvelle semaine, nouveau challenge !")
    
    # Envoyer l'annonce dans tous les channels avec emoji
    for channel in announcement_channels:
        try:
            await channel.send(embed=week_embed.copy())
        except:
            pass
    
    # Envoyer aussi dans le channel de logs
    if log_channel:
        try:
            await log_channel.send(embed=week_embed.copy())
        except:
            pass
    
    # 8. Confirmer la commande
    confirm_embed = discord.Embed(
        title="✅ SALAIRES CALCULÉS ET ENVOYÉS",
        description=f"💰 **Total à payer :** {total_payroll:,}$\n📊 **Employés payés :** {len(salary_data)}\n✅ Semaine réinitialisée avec succès !".replace(",", " "),
        color=EMS_RED
    )
    confirm_embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=confirm_embed)

@bot.tree.command(name="payes_test", description="Test du calcul des salaires (sans reset ni annonce)")
@app_commands.checks.has_permissions(administrator=True)
async def payes_test(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    guild = interaction.guild
    
    # Charger les stats actuelles (sans les modifier)
    stats = load_stats()
    
    # Calculer les salaires pour tous les membres
    salary_data = []
    total_payroll = 0
    
    direction_role = guild.get_role(ROLE_DIRECTION_EMS_ID)
    
    for member in guild.members:
        if member.bot:
            continue
        
        # Vérifier si le membre a le rôle DIRECTION
        has_direction_role = direction_role in member.roles if direction_role else False
        
        if has_direction_role:
            # DIRECTION: 9M fixe
            clean_name = get_clean_name(member)
            salary = 9000000
            total_payroll += salary
            
            salary_data.append({
                "name": clean_name,
                "rea": 0,
                "grade": "DIRECTION",
                "total": salary
            })
            continue
        
        # Détecter le grade par tag dans le pseudo
        nick = member.display_name.upper()
        grade = None
        rate = 0
        
        if "[DIR]" in nick:
            grade = "DIR"
            rate = 55000
        elif "[CDS]" in nick:
            grade = "CDS"
            rate = 50000
        elif "[MED]" in nick:
            grade = "MED"
            rate = 45000
        elif "[INF]" in nick:
            grade = "INF"
            rate = 40000
        elif "[ADS]" in nick:
            grade = "ADS"
            rate = 40000
        elif "[INT]" in nick:
            grade = "INT"
            rate = 35000
        elif "[EMT]" in nick:
            grade = "EMT"
            rate = 30000
        else:
            continue
        
        # Récupérer les réas
        employee_key = normalize_employee_key(member.display_name)
        rea_count = stats.get(employee_key, 0)
        
        # Calculer le salaire
        base_salary = rea_count * rate
        bonus = 0
        if rea_count > 50:
            bonus = ((rea_count - 50) // 10) * 150000
        salary = base_salary + bonus
        
        total_payroll += salary
        
        clean_name = get_clean_name(member)
        salary_data.append({
            "name": clean_name,
            "rea": rea_count,
            "grade": grade,
            "total": salary
        })
    
    # Trier par salaire décroissant
    salary_data.sort(key=lambda x: x["total"], reverse=True)
    
    # Diviser les employés en groupes de 10 pour éviter les dépassements
    embeds_to_send = []
    employees_per_embed = 10
    
    for i in range(0, len(salary_data), employees_per_embed):
        chunk = salary_data[i:i + employees_per_embed]
        page_num = (i // employees_per_embed) + 1
        total_pages = (len(salary_data) + employees_per_embed - 1) // employees_per_embed
        
        # Créer un embed pour ce groupe
        if i == 0:
            # Premier embed avec titre principal
            chunk_embed = discord.Embed(
                title="💰 TEST - APERÇU DES SALAIRES",
                description="**📊 Simulation du calcul des salaires (rien n'est envoyé ou reset)**\n",
                color=EMS_RED
            )
        else:
            # Embeds suivants
            chunk_embed = discord.Embed(
                title=f"💰 APERÇU DES SALAIRES (suite)",
                description=f"**Page {page_num}/{total_pages}**\n",
                color=EMS_RED
            )
        
        # Construire le tableau pour ce groupe
        salary_text = "```\n"
        salary_text += f"{'NOM':<16} | {'R':<3} | {'GRD':<3} | {'TOTAL':>10}\n"
        salary_text += "-" * 42 + "\n"
        
        for emp in chunk:
            name_display = emp['name'][:14]
            grade_display = emp['grade'][:3]
            salary_text += f"{name_display:<16} | {emp['rea']:<3} | {grade_display:<3} | {emp['total']:>10,}$\n".replace(",", " ")
        
        salary_text += "```"
        
        chunk_embed.add_field(name=f"📋 Liste (Page {page_num}/{total_pages})", value=salary_text, inline=False)
        
        # Ajouter les stats uniquement sur le dernier embed
        if i + employees_per_embed >= len(salary_data):
            chunk_embed.add_field(
                name="💵 TOTAL À RETIRER",
                value=f"```{total_payroll:,}$```".replace(",", " "),
                inline=False
            )
            
            chunk_embed.add_field(
                name="📊 STATISTIQUES",
                value=f"**Employés :** {len(salary_data)}\n**Réas totales :** {sum(stats.values())}",
                inline=False
            )
        
        chunk_embed.set_footer(text=f"🚑 EMS System | Mode Test - Page {page_num}/{total_pages}")
        embeds_to_send.append(chunk_embed)
    
    # Envoyer tous les embeds
    for embed in embeds_to_send:
        await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="reorganize", description="Réorganise tous les channels EMS dans leurs catégories respectives")
@app_commands.checks.has_permissions(administrator=True)
async def reorganize(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # Vérifier que les catégories sont configurées
    if not all([CATEGORY_EMT_ID, CATEGORY_INT_ID, CATEGORY_ADS_ID, CATEGORY_INF_ID, CATEGORY_MED_ID, CATEGORY_CDS_ID, CATEGORY_DIR_ID]):
        await interaction.followup.send("❌ Veuillez d'abord configurer les catégories avec `/setup_categories` !")
        return
    
    # Mapping grade -> catégorie
    grade_to_category = {
        "emt": CATEGORY_EMT_ID,
        "int": CATEGORY_INT_ID,
        "ads": CATEGORY_ADS_ID,
        "inf": CATEGORY_INF_ID,
        "med": CATEGORY_MED_ID,
        "cds": CATEGORY_CDS_ID,
        "dir": CATEGORY_DIR_ID
    }
    
    moved = []
    errors = []
    skipped = []
    
    # Scanner tous les channels texte
    for channel in guild.text_channels:
        # Vérifier si c'est un channel EMS (commence par un emoji)
        if len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]:
            # Extraire le grade du nom du channel
            # Format attendu: 🔴emt-nom, 🟠int-nom, etc.
            channel_name_lower = channel.name.lower()
            
            found_grade = None
            for grade in grade_to_category.keys():
                # Chercher le grade dans le nom (après l'emoji)
                if f"{grade}-" in channel_name_lower or f"{grade} " in channel_name_lower:
                    found_grade = grade
                    break
            
            if found_grade:
                target_category_id = grade_to_category[found_grade]
                target_category = guild.get_channel(target_category_id)
                
                if target_category:
                    # Vérifier si le channel est déjà dans la bonne catégorie
                    if channel.category_id == target_category_id:
                        skipped.append(f"⏭️ {channel.mention} (déjà dans {found_grade.upper()})")
                    else:
                        try:
                            await channel.edit(category=target_category)
                            moved.append(f"✅ {channel.mention} → {found_grade.upper()}")
                        except Exception as e:
                            errors.append(f"❌ {channel.mention}: {e}")
                else:
                    errors.append(f"❌ {channel.mention}: Catégorie {found_grade.upper()} introuvable")
            else:
                skipped.append(f"⚠️ {channel.mention} (grade non identifié)")
    
    # Créer le message de réponse
    embed = discord.Embed(
        title="🔄 RÉORGANISATION DES CHANNELS",
        description="Déplacement automatique des channels dans leurs catégories respectives",
        color=EMS_RED
    )
    
    if moved:
        moved_text = "\n".join(moved[:25])  # Limiter à 25 pour ne pas dépasser la limite
        if len(moved) > 25:
            moved_text += f"\n... et {len(moved) - 25} autres"
        embed.add_field(name=f"✅ Déplacés ({len(moved)})", value=moved_text, inline=False)
    
    if skipped:
        skipped_text = "\n".join(skipped[:10])
        if len(skipped) > 10:
            skipped_text += f"\n... et {len(skipped) - 10} autres"
        embed.add_field(name=f"⏭️ Ignorés ({len(skipped)})", value=skipped_text, inline=False)
    
    if errors:
        errors_text = "\n".join(errors[:10])
        if len(errors) > 10:
            errors_text += f"\n... et {len(errors) - 10} autres"
        embed.add_field(name=f"❌ Erreurs ({len(errors)})", value=errors_text, inline=False)
    
    if not moved and not skipped and not errors:
        embed.description = "Aucun channel EMS trouvé à réorganiser."
    
    embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="synchronise", description="Synchronise les stats depuis les logs (hier 19h19)")
@app_commands.checks.has_permissions(administrator=True)
async def synchronise(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        LOGS_SYNC_CHANNEL_ID = 1458464678542970983
        log_channel = bot.get_channel(LOGS_SYNC_CHANNEL_ID)
        
        if not log_channel:
            await interaction.followup.send(f"❌ Channel de logs introuvable (ID: {LOGS_SYNC_CHANNEL_ID})")
            return
        
        # Calculer la date de hier 19h19
        now = datetime.now()
        yesterday_19h19 = now.replace(hour=19, minute=19, second=0, microsecond=0) - timedelta(days=1)
        
        embed_progress = discord.Embed(
            title="🔄 SYNCHRONISATION EN COURS",
            description=f"Lecture des messages depuis **{yesterday_19h19.strftime('%d/%m/%Y à %H:%M')}**...",
            color=EMS_RED
        )
        embed_progress.set_footer(text="🚑 EMS System")
        await interaction.followup.send(embed=embed_progress)
        
        # Charger les stats actuelles
        stats = load_stats()
        
        # Dictionnaire pour compter les +1 par employé
        increments = {}
        message_count = 0
        
        # Lire les messages depuis hier 19h19
        async for message in log_channel.history(after=yesterday_19h19, limit=None):
            # Format attendu: "✅ **employee_key** | X réas"
            if message.content.startswith("✅ **") and " réas" in message.content:
                try:
                    # Extraire l'employé
                    parts = message.content.split("**")
                    if len(parts) >= 3:
                        employee_key = parts[1].strip()
                        
                        # Incrémenter le compteur pour cet employé
                        if employee_key not in increments:
                            increments[employee_key] = 0
                        increments[employee_key] += 1
                        message_count += 1
                        
                except Exception as e:
                    continue
        
        # Appliquer les incréments aux stats
        if increments:
            for employee_key, count in increments.items():
                if employee_key not in stats:
                    stats[employee_key] = 0
                stats[employee_key] += count
            
            # Sauvegarder les stats
            save_stats(stats)
            
            # Créer l'embed de résultat
            embed_result = discord.Embed(
                title="✅ SYNCHRONISATION TERMINÉE",
                description=f"**{message_count} messages traités**\n**{len(increments)} employés mis à jour**",
                color=EMS_RED
            )
            
            # Afficher les modifications (limité à 25 champs)
            sorted_increments = sorted(increments.items(), key=lambda x: x[1], reverse=True)
            for i, (employee_key, count) in enumerate(sorted_increments[:25]):
                emoji = get_color_emoji(stats[employee_key])
                embed_result.add_field(
                    name=f"{emoji} {employee_key}",
                    value=f"+{count} → {stats[employee_key]}/150",
                    inline=True
                )
            
            if len(increments) > 25:
                embed_result.add_field(
                    name="...",
                    value=f"Et {len(increments) - 25} autres employés",
                    inline=False
                )
            
            embed_result.set_footer(text=f"🚑 EMS System | Synchronisé depuis {yesterday_19h19.strftime('%d/%m/%Y à %H:%M')}")
            await interaction.edit_original_response(embed=embed_result)
        else:
            embed_empty = discord.Embed(
                title="⚠️ AUCUNE DONNÉE",
                description=f"Aucun message de stats trouvé depuis **{yesterday_19h19.strftime('%d/%m/%Y à %H:%M')}**",
                color=EMS_RED
            )
            embed_empty.set_footer(text="🚑 EMS System")
            await interaction.edit_original_response(embed=embed_empty)
            
    except Exception as e:
        embed_error = discord.Embed(
            title="❌ ERREUR",
            description=f"Une erreur est survenue lors de la synchronisation:\n```{str(e)}```",
            color=discord.Color.red()
        )
        embed_error.set_footer(text="🚑 EMS System")
        await interaction.followup.send(embed=embed_error)

# --- COMMANDE STATS AVEC GRAPHIQUE ---
@bot.tree.command(name="stats", description="Affiche les statistiques avec graphique ASCII")
async def stats_command(interaction: discord.Interaction):
    """Affiche les stats complètes des réas avec graphique"""
    await interaction.response.defer()
    
    stats = load_stats()
    if not stats:
        await interaction.followup.send("❌ Aucune donnée disponible")
        return
    
    # Trier par réas décroissants
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    max_value = max(stats.values()) if stats else 100
    
    # Créer le graphique ASCII
    graph_text = "```\n"
    graph_text += "STATISTIQUES RÉAS\n"
    graph_text += "=" * 50 + "\n\n"
    
    for i, (key, value) in enumerate(sorted_stats, 1):
        emoji = get_color_emoji(value)
        bar_length = int((value / max(max_value, 100)) * 25)  # Max 25 caractères
        bar = "█" * bar_length + "░" * (25 - bar_length)
        
        # Normaliser le nom pour affichage
        display_name = key.replace("-", " ").title()
        graph_text += f"{i:2}. {emoji} {display_name:<20} │ {bar} │ {value}/100\n"
    
    graph_text += "\n" + "=" * 50 + "\n"
    graph_text += f"Total: {sum(stats.values())} réas | {len(stats)} employés\n```"
    
    # Créer l'embed
    embed = discord.Embed(
        title="📊 Statistiques EMS",
        description=graph_text,
        color=EMS_DARK_RED
    )
    embed.set_footer(text=f"Mise à jour: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    await interaction.followup.send(embed=embed)

# --- COMMANDE LEADERBOARD AVEC ANNONCE ---
@bot.tree.command(name="leaderboard", description="Affiche le top 5 et envoie une annonce")
async def leaderboard_command(interaction: discord.Interaction):
    """Affiche le leaderboard du top 5 et envoie une annonce motivante"""
    await interaction.response.defer()
    
    stats = load_stats()
    if not stats or len(stats) < 5:
        await interaction.followup.send("❌ Pas assez de données pour un leaderboard")
        return
    
    # Trier par réas décroissants
    top_5 = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Messages félicitations personnalisés
    felicitations = [
        "🥇 Félicitations pour la première place. Travail constant et très bonne implication.",
        "🥈 Très bon travail également, continue comme ça.",
        "🥉 Belle progression cette semaine.",
        "4️⃣ Bonne présence et bon investissement.",
        "5️⃣ Tu complètes le classement, continue tes efforts."
    ]
    
    # Créer l'embed du classement
    embed = discord.Embed(
        title="🏆 Annonce – Top 5 de la semaine",
        description="Voici le classement du Top 5 basé sur l'activité et le travail effectué :\n",
        color=discord.Color.gold()
    )
    
    for i, (key, value) in enumerate(top_5):
        display_name = key.replace("-", " ").title()
        emoji = get_color_emoji(value)
        embed.add_field(
            name=f"#{i+1} {emoji} {display_name}",
            value=f"**{value} réas**",
            inline=False
        )
    
    embed.add_field(
        name="",
        value="\n".join([
            f"{i+1}. {felicitations[i]}" 
            for i in range(5)
        ]),
        inline=False
    )
    
    embed.add_field(
        name="Bravo !",
        value="Bravo à vous cinq pour votre activité.\nPour les autres, continuez vos interventions et vous pourrez apparaître dans le prochain classement.",
        inline=False
    )
    
    embed.set_footer(text="🚑 EMS System | Leaderboard")
    
    # Envoyer dans le channel d'annonce avec ping du role
    try:
        channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
        role = interaction.guild.get_role(LEADERBOARD_ROLE_ID)
        
        if channel and role:
            # Message avec ping du role
            ping_msg = f"<@&{LEADERBOARD_ROLE_ID}>"
            await channel.send(ping_msg, embed=embed)
            await interaction.followup.send("✅ Annonce du leaderboard envoyée !")
        else:
            await interaction.followup.send("❌ Canal ou rôle non trouvé")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur leaderboard: {e}")
        await interaction.followup.send(f"❌ Erreur: {e}")

# --- MODAL POUR LES AVIS ---
class AvisModal(discord.ui.Modal, title="📝 Donner un Avis"):
    """Modal pour soumettre un avis sur un employé"""
    
    # Sélection de l'employé
    employee = discord.ui.TextInput(
        label="Employé concerné",
        placeholder="Sélectionnez l'employé...",
        required=True
    )
    
    # Notation (1-5 étoiles)
    stars = discord.ui.TextInput(
        label="Nombre d'étoiles (1-5)",
        placeholder="Entrez un chiffre de 1 à 5",
        required=True,
        min_length=1,
        max_length=1
    )
    
    # Raison (optionnel)
    raison = discord.ui.TextInput(
        label="Raison (optionnel)",
        placeholder="Décrivez votre avis...",
        required=False,
        style=discord.TextStyle.long,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Quand l'utilisateur soumet le formulaire"""
        try:
            # Valider les étoiles
            try:
                star_count = int(self.stars.value)
                if star_count < 1 or star_count > 5:
                    await interaction.response.send_message(
                        "❌ Le nombre d'étoiles doit être entre 1 et 5",
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "❌ Veuillez entrer un chiffre valide (1-5)",
                    ephemeral=True
                )
                return
            
            # Créer l'embed de l'avis
            embed = discord.Embed(
                title="⭐ Nouvel Avis Reçu",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="Employé", value=self.employee.value, inline=False)
            embed.add_field(name="Note", value="⭐" * star_count, inline=True)
            embed.add_field(name="Raison", value=self.raison.value or "Aucune raison donnée", inline=False)
            embed.add_field(name="Auteur", value=interaction.user.mention, inline=True)
            embed.set_footer(text=f"Avis soumis le {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
            
            # Envoyer dans le channel des avis
            avis_channel = bot.get_channel(AVIS_CHANNEL_ID)
            if avis_channel:
                await avis_channel.send(embed=embed)
            
            await interaction.response.send_message(
                "✅ Votre avis a été enregistré avec succès !",
                ephemeral=True
            )
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur avis: {e}")
            await interaction.response.send_message(
                f"❌ Erreur: {e}",
                ephemeral=True
            )

# --- BOUTON POUR DONNER UN AVIS ---
class AvisButton(discord.ui.View):
    """Bouton pour ouvrir le formulaire d'avis"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📝 Donner un Avis", style=discord.ButtonStyle.primary)
    async def avis_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ouvre le modal pour donner un avis"""
        
        # Construire la liste des employés
        stats = load_stats()
        employee_list = "\n".join([
            f"• {key.replace('-', ' ').title()}"
            for key in sorted(stats.keys())
        ])
        
        # Montrer la liste des employés dans le placeholder
        modal = AvisModal()
        modal.employee.placeholder = f"Exemples: {', '.join(list(stats.keys())[:3])}..."
        
        await interaction.response.send_modal(modal)

# --- COMMANDE AVIS ---
@bot.tree.command(name="avis", description="Envoie une annonce pour recueillir des avis sur les employés")
async def avis_command(interaction: discord.Interaction):
    """Lance une campagne d'avis pour les employés"""
    await interaction.response.defer()
    
    try:
        # Créer l'embed d'annonce
        embed = discord.Embed(
            title="📝 Campagne d'Avis - Vos Retours Sont Importants",
            description="Aidez-nous à améliorer notre équipe en partageant vos avis sur les employés.\n\n"
                       "**Comment ça fonctionne ?**\n"
                       "1️⃣ Appuyez sur le bouton ci-dessous\n"
                       "2️⃣ Sélectionnez un employé\n"
                       "3️⃣ Donnez une note de 1 à 5 étoiles\n"
                       "4️⃣ Laissez un commentaire (optionnel)\n\n"
                       "Vos avis sont importants pour l'évolution de chacun. Merci ! ✨",
            color=discord.Color.gold()
        )
        
        embed.set_footer(text="🚑 EMS System | Vos avis comptent")
        
        # Envoyer dans le channel des avis avec ping du role citoyen
        avis_channel = bot.get_channel(AVIS_CHANNEL_ID)
        if avis_channel:
            ping_msg = f"<@&{CITOYEN_ROLE_ID}>" if CITOYEN_ROLE_ID != 0 else ""
            await avis_channel.send(ping_msg, embed=embed, view=AvisButton())
            await interaction.followup.send("✅ Annonce des avis lancée !")
        else:
            await interaction.followup.send("❌ Channel des avis non trouvé")
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur avis command: {e}")
        await interaction.followup.send(f"❌ Erreur: {e}")

# --- MODAL POUR LES DISPONIBILITÉS ---
class DispoModal(discord.ui.Modal, title="📅 Mettre à Jour mes Disponibilités"):
    """Modal pour soumettre ses disponibilités"""
    
    # Disponibilités
    disponibilites = discord.ui.TextInput(
        label="Vos disponibilités",
        placeholder="Ex: Lundi 10h-18h, Mardi 14h-22h, Dimanche fermé",
        required=True,
        style=discord.TextStyle.long,
        max_length=500
    )
    
    # Notes (optionnel)
    notes = discord.ui.TextInput(
        label="Notes additionnelles (optionnel)",
        placeholder="Ex: Pas disponible le 8 mars, préférence horaires...",
        required=False,
        style=discord.TextStyle.long,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Quand l'utilisateur soumet ses disponibilités"""
        try:
            user_name = interaction.user.name
            
            # Créer l'embed de la dispo
            embed = discord.Embed(
                title="📅 Nouvelle Disponibilité Soumise",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Personne", value=f"{interaction.user.mention} ({user_name})", inline=False)
            embed.add_field(name="Disponibilités", value=self.disponibilites.value, inline=False)
            if self.notes.value:
                embed.add_field(name="Notes", value=self.notes.value, inline=False)
            embed.set_footer(text=f"Reçu le {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
            
            # Envoyer dans le channel de demande avec boutons de confirmation pour la direction
            request_channel = bot.get_channel(DISPO_REQUEST_CHANNEL_ID)
            if request_channel:
                # Créer les boutons de confirmation/refus
                view = discord.ui.View()
                confirm_btn = discord.ui.Button(label="✅ Confirmer", style=discord.ButtonStyle.green)
                refuse_btn = discord.ui.Button(label="❌ Refuser", style=discord.ButtonStyle.red)
                
                async def confirm_callback(interaction_confirm: discord.Interaction):
                    # Vérifier que seul la direction peut confirmer
                    if not any(role.id == DIRECTION_ROLE_ID for role in interaction_confirm.user.roles):
                        await interaction_confirm.response.send_message(
                            "❌ Seule la direction peut valider les disponibilités !",
                            ephemeral=True
                        )
                        return
                    
                    # Message de confirmation à la direction
                    embed_confirm = discord.Embed(
                        title="✅ Disponibilité Confirmée",
                        description=f"La dispo de {user_name} a été approuvée.\n\nEn attente de recrutement...",
                        color=discord.Color.green()
                    )
                    await interaction_confirm.response.send_message(embed=embed_confirm, ephemeral=True)
                    
                    # Envoyer un DM de rappel à l'utilisateur
                    try:
                        embed_dm = discord.Embed(
                            title="📅 ✅ Votre Disponibilité a été Confirmée",
                            description=f"Bonjour {user_name},\n\nVotre disponibilité a été validée par la direction !\n\nVos dispo:\n{self.disponibilites.value}",
                            color=discord.Color.green()
                        )
                        embed_dm.set_footer(text="🚑 EMS System | Rappel de confirmation")
                        
                        user = bot.get_user(interaction.user.id)
                        if user:
                            await user.send(embed=embed_dm)
                    except:
                        pass
                    
                    # Envoyer un message de recrutement dans le channel de recrutement
                    recruitment_channel = bot.get_channel(DISPO_CHANNEL_ID)
                    if recruitment_channel:
                        embed_recrutement = discord.Embed(
                            title="👤 Candidature Approuvée - Décision de Recrutement",
                            description=f"**{interaction.user.mention}** a été approuvé(e) par la direction.\n\n"
                                       f"Disponibilités:\n{self.disponibilites.value}",
                            color=discord.Color.blue()
                        )
                        
                        # Boutons Recruter/Refuser
                        recrutement_view = discord.ui.View()
                        recruter_btn = discord.ui.Button(label="✅ Recruter", style=discord.ButtonStyle.green)
                        refuser_btn = discord.ui.Button(label="❌ Refuser", style=discord.ButtonStyle.red)
                        
                        async def recruter_callback(interaction_recrutement: discord.Interaction):
                            # Vérifier que seul la direction peut recruter
                            if not any(role.id == DIRECTION_ROLE_ID for role in interaction_recrutement.user.roles):
                                await interaction_recrutement.response.send_message(
                                    "❌ Seule la direction peut recruter !",
                                    ephemeral=True
                                )
                                return
                            
                            try:
                                guild = bot.get_guild(config["GUILD_ID"])
                                member = guild.get_member(interaction.user.id)
                                
                                if member:
                                    # Retirer le rôle pending
                                    try:
                                        role_pending = guild.get_role(ROLE_PENDING_ID)
                                        if role_pending:
                                            await member.remove_roles(role_pending)
                                    except:
                                        pass
                                    
                                    # Ajouter les rôles EMS
                                    roles_to_add = [
                                        guild.get_role(ROLE_EMT_1),
                                        guild.get_role(ROLE_EMT_2),
                                        guild.get_role(ROLE_EMT_3)
                                    ]
                                    roles_to_add = [r for r in roles_to_add if r]
                                    
                                    if roles_to_add:
                                        await member.add_roles(*roles_to_add)
                                    
                                    # Ajouter le préfixe [EMT]
                                    try:
                                        new_nick = f"[EMT] {user_name}"
                                        await member.edit(nick=new_nick)
                                    except:
                                        pass
                                    
                                    # Message de confirmation
                                    embed_recrute = discord.Embed(
                                        title="✅ Recrutement Effectué",
                                        description=f"**{user_name}** a été recruté(e) en tant que **[EMT]**.",
                                        color=discord.Color.green()
                                    )
                                    await interaction_recrutement.response.send_message(embed=embed_recrute, ephemeral=True)
                                    
                                    # DM de bienvenue
                                    try:
                                        embed_welcome = discord.Embed(
                                            title="🎉 Bienvenue dans l'EMS !",
                                            description=f"Félicitations {user_name} !\n\nVous avez été recruté(e) en tant que **[EMT]**.\n\nVous pouvez maintenant accéder à tous les channels de l'EMS.",
                                            color=discord.Color.green()
                                        )
                                        user_obj = bot.get_user(interaction.user.id)
                                        if user_obj:
                                            await user_obj.send(embed=embed_welcome)
                                    except:
                                        pass
                                    
                                    # Ajouter réaction ✅
                                    if hasattr(interaction_recrutement.message, 'add_reaction'):
                                        await interaction_recrutement.message.add_reaction("✅")
                            except Exception as e:
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur recrutement: {e}")
                                await interaction_recrutement.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
                        
                        async def refuser_recrutement_callback(interaction_refus: discord.Interaction):
                            # Vérifier que seul la direction peut refuser
                            if not any(role.id == DIRECTION_ROLE_ID for role in interaction_refus.user.roles):
                                await interaction_refus.response.send_message(
                                    "❌ Seule la direction peut refuser !",
                                    ephemeral=True
                                )
                                return
                            
                            try:
                                guild = bot.get_guild(config["GUILD_ID"])
                                member = guild.get_member(interaction.user.id)
                                
                                if member:
                                    # Retirer tous les rôles EMS (sauf citoyen)
                                    for role in member.roles:
                                        if role.id in [ROLE_EMT_1, ROLE_EMT_2, ROLE_EMT_3, ROLE_PENDING_ID] and role.id != ROLE_CITOYEN:
                                            try:
                                                await member.remove_roles(role)
                                            except:
                                                pass
                                    
                                    # Retirer le préfixe [EMT] si présent
                                    try:
                                        if member.nick and member.nick.startswith("[EMT]"):
                                            await member.edit(nick=user_name)
                                    except:
                                        pass
                                    
                                    # Message de refus
                                    embed_refuse = discord.Embed(
                                        title="❌ Candidature Refusée",
                                        description=f"**{user_name}** a été refusé(e) au recrutement.",
                                        color=discord.Color.red()
                                    )
                                    await interaction_refus.response.send_message(embed=embed_refuse, ephemeral=True)
                                    
                                    # DM de refus
                                    try:
                                        embed_refuse_dm = discord.Embed(
                                            title="❌ Candidature Refusée",
                                            description=f"Nous sommes désolés {user_name},\n\nVotre candidature au recrutement EMS a été refusée.\n\nVous pouvez réessayer ultérieurement.",
                                            color=discord.Color.red()
                                        )
                                        user_obj = bot.get_user(interaction.user.id)
                                        if user_obj:
                                            await user_obj.send(embed=embed_refuse_dm)
                                    except:
                                        pass
                                    
                                    # Ajouter réaction ❌
                                    if hasattr(interaction_refus.message, 'add_reaction'):
                                        await interaction_refus.message.add_reaction("❌")
                            except Exception as e:
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur refus recrutement: {e}")
                                await interaction_refus.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
                        
                        recruter_btn.callback = recruter_callback
                        refuser_btn.callback = refuser_recrutement_callback
                        recrutement_view.add_item(recruter_btn)
                        recrutement_view.add_item(refuser_btn)
                        
                        await recruitment_channel.send(embed=embed_recrutement, view=recrutement_view)
                    
                    # Ajouter une réaction pour marquer comme confirmée
                    if hasattr(interaction_confirm.message, 'add_reaction'):
                        await interaction_confirm.message.add_reaction("✅")
                
                async def refuse_callback(interaction_refuse: discord.Interaction):
                    # Message de refus à la direction
                    embed_refuse = discord.Embed(
                        title="❌ Disponibilité Refusée",
                        description=f"La dispo de {user_name} a été déclinée.",
                        color=discord.Color.red()
                    )
                    await interaction_refuse.response.send_message(embed=embed_refuse, ephemeral=True)
                    
                    # Envoyer un DM de rappel/refus à l'utilisateur
                    try:
                        embed_dm = discord.Embed(
                            title="📅 ❌ Disponibilité Refusée",
                            description=f"Bonjour {user_name},\n\nVotre proposition de disponibilité a été refusée.\n\nVeuillez contacter la direction pour plus d'informations.",
                            color=discord.Color.red()
                        )
                        embed_dm.set_footer(text="🚑 EMS System | Avis de refus")
                        
                        user = bot.get_user(interaction.user.id)
                        if user:
                            await user.send(embed=embed_dm)
                    except:
                        pass
                    
                    # Ajouter une réaction pour marquer comme refusée
                    if hasattr(interaction_refuse.message, 'add_reaction'):
                        await interaction_refuse.message.add_reaction("❌")
                
                confirm_btn.callback = confirm_callback
                refuse_btn.callback = refuse_callback
                view.add_item(confirm_btn)
                view.add_item(refuse_btn)
                
                ping_msg = f"<@&{DIRECTION_ROLE_ID}>"
                await request_channel.send(ping_msg, embed=embed, view=view)
            
            await interaction.response.send_message(
                "✅ Vos disponibilités ont été soumises avec succès !",
                ephemeral=True
            )
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur dispo: {e}")
            await interaction.response.send_message(
                f"❌ Erreur: {e}",
                ephemeral=True
            )

# --- BOUTON POUR LES DISPONIBILITÉS ---
class DispoButton(discord.ui.View):
    """Bouton pour ouvrir le formulaire de disponibilités"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📅 Soumettre ma Dispo", style=discord.ButtonStyle.primary)
    async def dispo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ouvre le modal pour soumettre ses dispo"""
        await interaction.response.send_modal(DispoModal())

# --- COMMANDE DISPO ---
@bot.tree.command(name="dispo", description="Lance la campagne de disponibilités")
async def dispo_command(interaction: discord.Interaction):
    """Lance une campagne pour recueillir les disponibilités"""
    await interaction.response.defer()
    
    try:
        # Créer l'embed d'annonce
        embed = discord.Embed(
            title="📅 Mise à Jour des Disponibilités",
            description="Merci de mettre à jour vos disponibilités !\n\n"
                       "**Comment ça fonctionne ?**\n"
                       "1️⃣ Appuyez sur le bouton ci-dessous\n"
                       "2️⃣ Remplissez vos disponibilités\n"
                       "3️⃣ Ajoutez des notes si nécessaire\n"
                       "4️⃣ La direction confirmera ou refusera\n\n"
                       "Vos disponibilités nous aident à mieux organiser les plannings. Merci ! 📋",
            color=discord.Color.blue()
        )
        
        embed.set_footer(text="🚑 EMS System | Mettez à jour vos dispo")
        
        # Envoyer dans le channel des dispo avec ping du role citoyen
        dispo_channel = bot.get_channel(DISPO_CHANNEL_ID)
        if dispo_channel:
            ping_msg = f"<@&{CITOYEN_ROLE_ID}>"
            await dispo_channel.send(ping_msg, embed=embed, view=DispoButton())
            await interaction.followup.send("✅ Annonce des disponibilités lancée !")
        else:
            await interaction.followup.send("❌ Channel non trouvé")
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur dispo command: {e}")
        await interaction.followup.send(f"❌ Erreur: {e}")

@bot.event
async def on_message(message):
    """Compte les réas quand un utilisateur envoie une réa avec pièces jointes"""
    # Ignorer les messages du bot
    if message.author.bot:
        return
    
    # Ignorer les messages sans pièces jointes
    if not message.attachments:
        await bot.process_commands(message)
        return
    
    try:
        # Obtenir le channel et l'employé associé
        channel = message.channel
        if not channel or not channel.name:
            await bot.process_commands(message)
            return
        
        # Vérifier que c'est un channel EMS (commence par emoji)
        if not (channel.name and len(channel.name) > 0 and channel.name[0] in ["🔴", "🟠", "🟢"]):
            await bot.process_commands(message)
            return
        
        # Obtenir la clé employé du channel
        employee_key = get_channel_employee_key(channel)
        if not employee_key:
            await bot.process_commands(message)
            return
        
        # Charger les stats
        stats = load_stats()
        
        # Incrémenter le compteur
        if employee_key not in stats:
            stats[employee_key] = 0
        
        old_count = stats[employee_key]
        stats[employee_key] += 1
        current_count = stats[employee_key]
        
        # Sauvegarder les stats IMMÉDIATEMENT
        save_stats(stats)
        
        # Ajouter réaction ✅
        try:
            await message.add_reaction("✅")
        except:
            pass
        
        # Envoyer log
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            try:
                emoji = get_color_emoji(current_count)
                message_text = f"✅ **{employee_key}** | {current_count} réas"
                await log_channel.send(message_text)
                
                # --- MILESTONES & CONGRATULATIONS ---
                display_name = employee_key.replace("-", " ").title()
                
                # Milestone 50 réas
                if old_count < 50 and current_count >= 50:
                    embed_50 = discord.Embed(
                        title="🎯 50 réas atteints !",
                        description=f"Excellent travail **{display_name}** ! 🙌\n\n"
                                   f"Tu continues et tu atteindras le quota complet.\n"
                                   f"Reste motivé ! 💪",
                        color=discord.Color.orange()
                    )
                    embed_50.set_footer(text="🚑 EMS System | Continue comme ça !")
                    await log_channel.send(embed=embed_50)
                
                # Milestone 100 réas (QUOTA COMPLET)
                if old_count < 100 and current_count >= 100:
                    embed_100 = discord.Embed(
                        title="🏆 QUOTA COMPLET - 100 réas ! 🏆",
                        description=f"🎉 **{display_name}** a rempli le quota !\n\n"
                                   f"Tu as atteint l'objectif de 100 réas.\n"
                                   f"Continue comme ça, nous sommes fiers de ton activité ! 🌟\n\n"
                                   f"Des récompenses seront offertes aux plus actifs à la fin du mois.",
                        color=discord.Color.gold()
                    )
                    embed_100.set_footer(text="🚑 EMS System | Bravo !")
                    
                    # Envoyer avec ping du role
                    try:
                        role_mention = f"<@&838102445095256068>"
                        await log_channel.send(role_mention, embed=embed_100)
                    except:
                        await log_channel.send(embed=embed_100)
            except:
                pass
    
    except Exception as e:
        print(f"❌ Erreur on_message: {e}")
    
    # Traiter les commandes slash
    await bot.process_commands(message)

# --- TÂCHE DE MISE À JOUR DES DESCRIPTIONS AVEC DÉLAI ---
@tasks.loop(minutes=5)
async def update_descriptions_background():
    """Met à jour les descriptions de tous les channels EMS toutes les 5 minutes"""
    try:
        guild = bot.get_guild(config["GUILD_ID"])
        if not guild:
            return
        
        stats = load_stats()
        if not stats:
            return
        
        updated_count = 0
        skipped_count = 0
        
        for key, value in stats.items():
            try:
                # Chercher le channel EMS correspondant
                channel = None
                for ch in guild.text_channels:
                    if ch.name and len(ch.name) > 0 and ch.name[0] in ["🔴", "🟠", "🟢"]:
                        ch_employee_key = get_channel_employee_key(ch)
                        if ch_employee_key == key:
                            channel = ch
                            break
                
                if not channel:
                    continue
                
                # Calculer la nouvelle description
                new_emoji = get_color_emoji(value)
                current_emoji = channel.name[0]
                bonus_days = get_week_bonus_count(key)
                bonus_text = f" {bonus_days}M" if bonus_days > 0 else ""
                new_topic = f"{new_emoji} {value}/100{bonus_text}"
                
                # Vérifier si quelque chose a changé
                name_changed = current_emoji != new_emoji
                topic_changed = channel.topic != new_topic
                
                if not name_changed and not topic_changed:
                    skipped_count += 1
                    continue
                
                # Un seul appel API pour nom + description
                edit_args = {}
                if name_changed:
                    edit_args["name"] = f"{new_emoji}{channel.name[1:]}"
                if topic_changed:
                    edit_args["topic"] = new_topic
                
                await channel.edit(**edit_args)
                updated_count += 1
                
                # Délai de 4 secondes entre chaque channel modifié
                await asyncio.sleep(4)
                
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Erreur update {key}: {e}")
                await asyncio.sleep(5)  # Délai plus long en cas d'erreur
        
        if updated_count > 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Descriptions: {updated_count} modifiés, {skipped_count} inchangés")
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur descriptions: {e}")

@update_descriptions_background.before_loop
async def before_update_descriptions():
    await bot.wait_until_ready()
    await asyncio.sleep(15)  # Attendre 15s après connexion avant la première mise à jour

@bot.event
async def on_ready():
    stats = load_stats()
    total_reas = sum(stats.values()) if stats else 0
    
    print(f'✅ Bot connecté: {bot.user}')
    print(f'📊 {len(stats)} employés | {total_reas} réas totales')
    
    # Backup au démarrage
    if stats:
        try:
            atomic_write_json(STATS_FILE, stats, make_backup=True)
        except:
            pass
    
    # Démarrer les tâches si pas déjà en cours
    if not auto_backup_stats.is_running():
        auto_backup_stats.start()
    if not update_descriptions_background.is_running():
        update_descriptions_background.start()
    
    print(f'✅ Sauvegarde auto (5min) + Mise à jour descriptions (5min) activées')

# --- TÂCHE DE SAUVEGARDE AUTOMATIQUE ---
@tasks.loop(minutes=5)
async def auto_backup_stats():
    """Sauvegarde automatique des stats toutes les 5 minutes"""
    try:
        stats = load_stats()
        total_reas = sum(stats.values()) if stats else 0
        atomic_write_json(STATS_FILE, stats, make_backup=True)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 💾 Sauvegarde: {len(stats)} employés, {total_reas} réas")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erreur sauvegarde: {e}")

@auto_backup_stats.before_loop
async def before_auto_backup():
    await bot.wait_until_ready()

if __name__ == "__main__":
    if not config['TOKEN']:
        print("Erreur: TOKEN manquant. Vérifiez votre fichier config.json ou vos variables d'environnement.")
    else:
        import time
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f"🚀 Démarrage du bot EMS... (Tentative {retry_count + 1}/{max_retries})")
                bot.run(config['TOKEN'])
                break  # Si le bot s'arrête proprement, sortir de la boucle
            except KeyboardInterrupt:
                # 💾 SAUVEGARDE FINALE AVANT ARRÊT MANUEL
                try:
                    stats = load_stats()
                    atomic_write_json(STATS_FILE, stats, make_backup=True)
                    print(f"💾 Sauvegarde finale effectuée avant arrêt")
                except:
                    pass
                print("⏹️ Arrêt manuel du bot...")
                break
            except Exception as e:
                # 💾 SAUVEGARDE D'URGENCE EN CAS D'ERREUR
                try:
                    stats = load_stats()
                    atomic_write_json(STATS_FILE, stats, make_backup=True)
                    print(f"💾 Sauvegarde d'urgence effectuée")
                except:
                    pass
                
                retry_count += 1
                print(f"❌ Erreur critique: {e}")
                
                if retry_count < max_retries:
                    wait_time = min(30 * retry_count, 300)  # Max 5 minutes
                    print(f"🔄 Redémarrage automatique dans {wait_time} secondes...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ Nombre maximum de tentatives atteint ({max_retries}). Arrêt définitif.")
                    break























