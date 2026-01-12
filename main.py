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

# Configuration Taxi
TAXI_CHANNEL_ID = 1457304629456011264
TAXI_ROLE_ID = 1163206112355561472
ROLE_DIRECTION_EMS_ID = 838120186585940010
ROLE_DIRECTION_TAXI_ID = 1311787019546136596

# Configuration Tickets
ROLE_REQUEST_CHANNEL_ID = 1450938023033176247
APPOINTMENT_CHANNEL_ID = 1415783172163244132
TICKET_CATEGORY_ID = 840364236189335553
ROLE_LSPD_ID = 1070687458825601115
ROLE_BCSO_ID = 1070374792450027560
ROLE_MARSHALL_ID = 1365068483074855045
ROLE_NO_TEST_ID = 1163524216688230591

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
        self.add_view(RoleRequestButton())
        self.add_view(AppointmentButton())
        # Démarrer la tâche automatisée pour les annonces taxi
        weekly_taxi_announcement.start()

bot = EMSBot()

# --- GESTION DES STATS ---
def load_stats():
    if not os.path.exists(STATS_FILE):
        return {}
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            data = f.read().strip()
            if not data:
                return {}
            return json.loads(data)
    except:
        return {}

def save_stats(stats):
    atomic_write_json(STATS_FILE, stats)

def normalize_employee_key(name: str) -> str:
    """Normalise un identifiant d'employé pour correspondre aux clés de stats.json.
    - met en minuscules
    - supprime les préfixes de rôle (emt-, int-, cds-, rh-, drh-, med-, ads-)
    - remplace les espaces par des tirets
    - retire les crochets/espaces parasites
    """
    if not name:
        return ""
    s = name.strip().lower()
    # Retirer crochets type [emt] ou [rh]
    for br in ["[emt]", "[int]", "[cds]", "[rh]", "[drh]", "[med]", "[ads]"]:
        s = s.replace(br, "")
    s = s.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    s = s.replace("_", "-")
    # Supprimer les préfixes connus suivis d'un espace ou d'un tiret
    prefixes = ["emt-", "emt ", "int-", "int ", "cds-", "cds ", "rh-", "rh ", "drh-", "drh ", "med-", "med ", "ads-", "ads "]
    for p in prefixes:
        if s.startswith(p):
            s = s[len(p):]
            break
    # Normaliser espaces -> tirets
    s = "-".join(filter(None, s.replace("/", " ").replace("|", " ").split()))
    # Nettoyer tirets multiples
    while "--" in s:
        s = s.replace("--", "-")
    return s

def load_channel_map():
    return robust_load_json(CHANNEL_MAP_FILE, {})

def save_channel_map(mapping: dict):
    atomic_write_json(CHANNEL_MAP_FILE, mapping)

def get_channel_employee_key(channel: discord.abc.GuildChannel) -> str:
    """Retourne la clé employé pour un channel donné en s'appuyant sur un mapping persistant.
    Si absente, la déduit du nom du channel et persiste le mapping.
    """
    mapping = load_channel_map()
    key = mapping.get(str(channel.id))
    if key:
        return key
    # Déduire via le nom du channel
    raw = channel.name[1:].strip() if channel.name and len(channel.name) > 1 else channel.name
    key = normalize_employee_key(raw or "")
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
    elif count >= 50:
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

# --- SYSTEME DE RÉACTIONS ET COMPTAGE TAXI ---
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

    if not message.attachments or not message.channel.name:
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
@bot.tree.command(name="total", description="Affiche le total des réactions")
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
    
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    
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
        current_embed.add_field(name=f"{emoji} {name}", value=f"{count}/100", inline=False)
        field_count += 1
    
    # Ajouter le dernier embed avec le footer
    if current_embed:
        current_embed.set_footer(text="🚑 EMS System")
        embeds.append(current_embed)
    
    # Calculer le total des réactions
    total_reactions = sum(stats.values())
    
    # Ajouter un dernier embed avec le résumé
    summary_embed = discord.Embed(
        title="📊 RÉSUMÉ DE CETTE SEMAINE",
        description=f"**Total des réactions :** `{total_reactions}` 🎯",
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
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = guild.get_member(self.target_user.id)
        
        if not member:
            await interaction.followup.send("❌ Le candidat n'est plus sur le serveur.", ephemeral=True)
            return
        
        # Répondre immédiatement pour éviter timeout
        await interaction.followup.send(f"✅ **{member.display_name}** accepté ! Traitement en cours...", ephemeral=True)
        
        role = guild.get_role(config.get("ROLE_ATTENTE_ID"))
        
        # Ajouter rôle
        if role:
            try:
                await member.add_roles(role)
            except Exception as e:
                print(f"Erreur ajout rôle: {e}")
        
        # DM
        try:
            await member.send(
                f"🎉 **FÉLICITATIONS !**\n\n"
                f"✅ Votre candidature a été **ACCEPTÉE** !\n\n"
                f"Bienvenue dans la famille des **EMS** ! 🚑\n\n"
                f"📝 **Prochaine étape :**\n"
                f"Merci de mettre vos disponibilités ici :\n"
                f"https://discord.com/channels/838102445083197470/1451553241065193555\n\n"
                f"et nous nous chargeons du reste !\n\n"
                f"Cordialement,\n**La Direction des EMS** 🚑"
            )
        except Exception as e:
            print(f"Erreur DM acceptation: {e}")
        
        # Log dans le channel de logs
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            embed = discord.Embed(
                title="✅ CV ACCEPTÉ",
                description=f"**Candidat :** {member.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_RED
            )
            embed.add_field(name="✅ Statut", value="Candidature approuvée ✓", inline=False)
            embed.add_field(name="👤 Rôle attribué", value="Attente d'onboarding", inline=False)
            embed.set_footer(text="🚑 EMS System")
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"Erreur log acceptation: {e}")
        
        # Envoyer aussi dans le channel CV
        cv_channel = bot.get_channel(config.get("CV_CHANNEL_ID"))
        if cv_channel:
            embed = discord.Embed(
                title="✅ CV ACCEPTÉ",
                description=f"**Candidat :** {member.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_RED
            )
            embed.add_field(name="✅ Statut", value="Candidature approuvée ✓", inline=False)
            embed.add_field(name="👤 Rôle attribué", value="Attente d'onboarding", inline=False)
            embed.set_footer(text="🚑 EMS System")
            try:
                await cv_channel.send(embed=embed)
            except Exception as e:
                print(f"Erreur CV channel acceptation: {e}")
        
        # Envoyer dans le channel de logs CV acceptés
        cv_accepted_log = bot.get_channel(config.get("CV_ACCEPTED_LOG_CHANNEL_ID"))
        if cv_accepted_log:
            embed = discord.Embed(
                title="✅ CV ACCEPTÉ",
                description=f"**Candidat :** {member.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_RED
            )
            embed.add_field(name="✅ Statut", value="Candidature approuvée ✓", inline=False)
            embed.add_field(name="👤 Rôle attribué", value="Attente d'onboarding", inline=False)
            embed.set_footer(text="🚑 EMS System")
            try:
                await cv_accepted_log.send(embed=embed)
            except Exception as e:
                print(f"Erreur logs CV acceptés: {e}")
        
        # Désactiver et supprimer le message
        self.disable_all_items()
        if self.message:
            try:
                await self.message.delete()
            except Exception as e:
                print(f"Erreur suppression message CV accepté: {e}")

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red, custom_id="refuse_cv")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # DM au candidat
        try:
            await self.target_user.send(
                f"❌ **Candidature Refusée**\n\n"
                f"Nous regrettons de vous informer que votre candidature n'a pas été retenue.\n\n"
                f"Nous vous encourageons à postuler à nouveau dans le futur.\n\n"
                f"Cordialement,\n**La Direction des EMS** 🚑"
            )
        except:
            pass
        
        # Log
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            embed = discord.Embed(
                title="❌ CV REFUSÉ",
                description=f"**Candidat :** {self.target_user.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_DARK_RED
            )
            embed.set_footer(text="🚑 EMS System")
            try:
                await log_channel.send(embed=embed)
            except:
                pass
        
        # Désactiver et supprimer le message
        self.disable_all_items()
        if self.message:
            try:
                await self.message.delete()
            except Exception as e:
                print(f"Erreur suppression message CV refusé: {e}")
        
        await interaction.followup.send(f"✅ {self.target_user.mention} refusé et message supprimé", ephemeral=True)
    
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
                    except:
                        pass
                
                answers.append(f"**{question}**\n{msg.content}")
            except asyncio.TimeoutError:
                timeout_msg = discord.Embed(
                    title="⏱️ TEMPS ÉCOULÉ",
                    description="Vous n'avez pas répondu à temps. Le dossier va être fermé.",
                    color=EMS_DARK_RED
                )
                timeout_msg.set_footer(text="🚑 EMS System")
                try:
                    await channel.send(embed=timeout_msg)
                except:
                    pass
                await asyncio.sleep(3)
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
                "🆔 Votre carte d'identité\n"
                "🚗 Votre permis de conduire\n\n"
                "Envoyez-les ci-dessous et nous nous en chargerons ! 🚑\n\n"
                "⏱️ Vous avez un temps illimité pour envoyer les documents."
            ),
            color=EMS_RED
        )
        docs.set_footer(text="🚑 EMS System | Envoyez les fichiers ci-dessous")
        await channel.send(embed=docs)
        
        attachments = []
        
        def check_doc(m):
            return m.author == interaction.user and m.channel == channel
        
        try:
            msg = await bot.wait_for('message', check=check_doc, timeout=None)
            
            if msg.attachments:
                for att in msg.attachments:
                    attachments.append(att.url)
            
            confirm = discord.Embed(
                title="✅ CANDIDATURE COMPLÈTE",
                description=(
                    "🎉 Excellent ! Nous avons reçu votre candidature complète !\n\n"
                    f"**Documents reçus :** {len(attachments)}\n\n"
                    "👀 **Prochaines étapes :**\n"
                    "• La direction examinera votre candidature\n"
                    "• Vous recevrez une réponse dans vos messages privés\n"
                    "• N'hésitez pas à nous contacter en cas de questions\n\n"
                    "**Merci pour votre intérêt envers les EMS !** 🚑"
                ),
                color=EMS_RED
            )
            confirm.set_footer(text="🚑 EMS System | Bon courage !")
            await channel.send(embed=confirm)
            
            try:
                await interaction.user.send(
                    "🚑 **Candidature envoyée** 🚑\n\n"
                    "Nous avons bien reçu votre candidature.\n\n"
                    "Nous vous recontacterons bientôt.\n\n"
                    "Merci pour votre intérêt ! 👨‍⚕️"
                )
            except:
                pass
        except:
            pass
        
        # Envoyer au channel CV
        cv_channel = bot.get_channel(config.get("CV_CHANNEL_ID"))
        if cv_channel:
            full_text = "\n\n".join(answers)
            cv_embed = discord.Embed(
                title=f"📋 CV - {user_fullname if user_fullname else interaction.user.name}",
                description=full_text[:2000],
                color=EMS_RED
            )
            
            if attachments:
                cv_embed.add_field(name="📎", value="\n".join([f"[Doc {i}]({url})" for i, url in enumerate(attachments, 1)]), inline=False)
            
            cv_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            cv_embed.set_footer(text=f"🚑 EMS System | ID: {user_id}")
            
            view = ReviewView(interaction.user)
            
            # Ping direction directement dans le message du CV
            direction_role = guild.get_role(config.get("ROLE_DIRECTION_ID"))
            ping_content = direction_role.mention if direction_role and config.get("ROLE_DIRECTION_ID") != 0 else None
            
            msg = await cv_channel.send(content=ping_content, embed=cv_embed, view=view)
            view.message = msg
        
        # Nettoyer
        await asyncio.sleep(120)
        try:
            await channel.delete()
        except:
            pass

@bot.tree.command(name="setup_cv", description="Affiche le bouton CV")
@app_commands.checks.has_permissions(administrator=True)
async def setup_cv(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚑 RECRUTEMENT EMS",
        description=(
            "**Rejoignez notre équipe d'urgentistes !**\n\n"
            "Vous souhaitez intégrer une équipe dynamique et professionnelle ? "
            "Cliquez sur le bouton ci-dessous pour déposer votre candidature !\n\n"
            "**📋 Le processus :**\n"
            "1️⃣ Cliquez sur \"Dépose ton CV\"\n"
            "2️⃣ Répondez à 13 questions détaillées\n"
            "3️⃣ Envoyez vos documents\n"
            "4️⃣ Attendez la validation de la direction\n\n"
            "**✨ Nous cherchons :** Des candidats motivés, professionnels et passionnés par le secteur médical !\n\n"
            "**Bonne chance ! 🚑💪**"
        ),
        color=EMS_RED
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    embed.set_footer(text="🚑 EMS Management System | Votre avenir commence ici")

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
            title="❓ QUESTION 1/4",
            description="**Quelle organisation rejoignez-vous ?**\n\nRépondez par :\n• `LSPD`\n• `BCSO`\n• `MARSHALL`",
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
        q2 = discord.Embed(
            title="❓ QUESTION 2/4",
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
        
        # Question 3 : Matricule
        q3 = discord.Embed(
            title="❓ QUESTION 3/4",
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
        q4 = discord.Embed(
            title="❓ QUESTION 4/4",
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
            "• Organisation (LSPD/BCSO/MARSHALL)\n"
            "• Prénom et nom\n"
            "• Matricule\n"
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
async def on_ready():
    print(f'✅ Bot: {bot.user}')
    stats = load_stats()
    print(f'📊 Stats: {stats if stats else "Aucune"}')
    # Synchronisation des couleurs au démarrage supprimée

# --- TÂCHE AUTOMATISÉE HEBDOMADAIRE TAXI ---
@tasks.loop(hours=1)
async def weekly_taxi_announcement():
    """Vérifie si c'est samedi 19h et envoie l'annonce hebdomadaire"""
    now = datetime.now()
    
    # Vérifier si c'est samedi (weekday() == 5) et qu'il est 19h
    if now.weekday() == 5 and now.hour == 19:
        await send_weekly_taxi_announcement()

@weekly_taxi_announcement.before_loop
async def before_weekly_announcement():
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

# --- COMMANDES DE MANAGEMENT EMS ---

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

    # 3. Création du Channel dans la catégorie EMT
    category_emt = guild.get_channel(CATEGORY_EMT_ID) if CATEGORY_EMT_ID else None
    channel_name = f"🔴emt-{clean_name.lower().replace(' ', '-')}"
    
    if category_emt:
        # Permissions pour que le membre ait accès à son channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            membre: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        # Créer le channel avec les permissions dans la catégorie EMT
        new_channel = await guild.create_text_channel(name=channel_name, category=category_emt, overwrites=overwrites)

        # Sauvegarde du mapping
        mapping = load_channel_map()
        mapping[str(membre.id)] = new_channel.id
        save_channel_map(mapping)
        
        await interaction.followup.send(f"✅ **{membre.mention}** a été employé avec succès !\n📛 Renommé en `{new_nickname}`\n📂 Dossier créé : {new_channel.mention} dans la catégorie EMT")
    else:
        await interaction.followup.send(f"⚠️ Catégorie EMT introuvable (ID: {CATEGORY_EMT_ID}), rôles et pseudo mis à jour mais pas le channel.")


@bot.tree.command(name="virer", description="Virer un employé (Retrait rôles, reset pseudo)")
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
    mapping = load_channel_map()
    chan_id = mapping.get(str(membre.id))
    channel_deleted = False
    
    if chan_id:
        channel = guild.get_channel(int(chan_id))
        if channel:
            try:
                await channel.delete()
                # Retirer l'entrée du mapping
                del mapping[str(membre.id)]
                save_channel_map(mapping)
                channel_deleted = True
            except Exception as e:
                print(f"Erreur suppression channel: {e}")
    
    if channel_deleted:
        await interaction.followup.send(f"🚫 **{clean_name}** a été viré.\nRôles retirés, pseudo réinitialisé et channel supprimé.")
    else:
        await interaction.followup.send(f"🚫 **{clean_name}** a été viré.\nRôles retirés et pseudo réinitialisé.")

@bot.tree.command(name="up", description="Promouvoir un employé au rang suivant")
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
            "tag": "INT", "chan_prefix": "🔴int",
            "category_id": CATEGORY_INT_ID
        }
    elif R_INT in member_roles_ids:
        # INT -> ADS
        next_step = {
            "remove": R_INT, "add": R_ADS,
            "tag": "ADS", "chan_prefix": "🔴ads",
            "category_id": CATEGORY_ADS_ID
        }
    elif R_ADS in member_roles_ids:
        # ADS -> INF
        next_step = {
            "remove": R_ADS, "add": R_INF,
            "tag": "INF", "chan_prefix": "🔴inf",
            "category_id": CATEGORY_INF_ID
        }
    elif R_INF in member_roles_ids:
        # INF -> MED
        next_step = {
            "remove": R_INF, "add": R_MED,
            "tag": "MED", "chan_prefix": "🔴med",
            "category_id": CATEGORY_MED_ID
        }
    elif R_MED in member_roles_ids:
        # MED -> CDS
        next_step = {
            "remove": R_MED, "add": R_CDS,
            "tag": "CDS", "chan_prefix": "🔴cds",
            "category_id": CATEGORY_CDS_ID
        }
    elif R_CDS in member_roles_ids:
        # CDS -> DIR
        next_step = {
            "remove": R_CDS, "add": R_DIR,
            "tag": "DIR", "chan_prefix": "🔴dir",
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
        
    # 3. Channel
    mapping = load_channel_map()
    chan_id = mapping.get(str(membre.id))
    channel = guild.get_channel(chan_id) if chan_id else None
    
    chan_msg = ""
    if channel:
        # Rename
        new_chan_name = f"{next_step['chan_prefix']}-{clean_name.lower().replace(' ', '-')}"
        
        # Déplacer dans la nouvelle catégorie
        new_category_id = next_step.get("category_id")
        new_category = guild.get_channel(new_category_id) if new_category_id else None
        
        if new_category:
            try:
                await channel.edit(name=new_chan_name, category=new_category)
                chan_msg = f"\n📂 Dossier déplacé dans la catégorie {next_step['tag']} et renommé : {channel.mention}"
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
    
    # 5. Créer l'annonce des salaires
    announcement_embed = discord.Embed(
        title="💰 PAIEMENT DES SALAIRES",
        description="**📊 Récapitulatif des salaires de la semaine**\n",
        color=EMS_RED
    )
    
    # Ajouter l'image du coffre (si téléchargée avec succès)
    if coffre_image_file:
        announcement_embed.set_image(url=f"attachment://{coffre_image_file.filename}")
    
    # Construire le tableau des salaires
    salary_text = "```\n"
    salary_text += f"{'NOM':<20} | {'RÉAS':<5} | {'GRADE':<10} | {'TOTAL':>15}\n"
    salary_text += "-" * 65 + "\n"
    
    for emp in salary_data:
        name_display = emp['name'][:18]  # Limiter à 18 caractères
        salary_text += f"{name_display:<20} | {emp['rea']:<5} | {emp['grade']:<10} | {emp['total']:>15,}$\n".replace(",", " ")
    
    salary_text += "```"
    
    # Ajouter au embed (diviser si trop long)
    if len(salary_text) <= 1024:
        announcement_embed.add_field(name="📋 Liste des salaires", value=salary_text, inline=False)
    else:
        # Diviser en plusieurs embeds si nécessaire
        chunks = []
        current_chunk = "```\n"
        current_chunk += f"{'NOM':<20} | {'RÉAS':<5} | {'GRADE':<10} | {'TOTAL':>15}\n"
        current_chunk += "-" * 65 + "\n"
        
        for emp in salary_data:
            line = f"{emp['name'][:18]:<20} | {emp['rea']:<5} | {emp['grade']:<10} | {emp['total']:>15,}$\n".replace(",", " ")
            if len(current_chunk) + len(line) + 3 > 1020:  # 1024 - "```"
                current_chunk += "```"
                chunks.append(current_chunk)
                current_chunk = "```\n" + line
            else:
                current_chunk += line
        
        current_chunk += "```"
        chunks.append(current_chunk)
        
        for i, chunk in enumerate(chunks):
            announcement_embed.add_field(name=f"📋 Liste des salaires ({i+1}/{len(chunks)})", value=chunk, inline=False)
    
    # Ajouter le total à retirer
    announcement_embed.add_field(
        name="💵 TOTAL À RETIRER DU COFFRE",
        value=f"```{total_payroll:,}$```".replace(",", " "),
        inline=False
    )
    
    announcement_embed.set_footer(text="🚑 EMS System | Bonne paie à tous !")
    announcement_embed.timestamp = datetime.now()
    
    # 6. Envoyer dans le channel de logs
    log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
    if log_channel:
        try:
            if coffre_image_file:
                # Attacher l'image téléchargée
                await log_channel.send(embed=announcement_embed, file=coffre_image_file)
            else:
                # Fallback si le téléchargement a échoué
                await log_channel.send(embed=announcement_embed)
        except Exception as e:
            print(f"Erreur envoi annonce salaires : {e}")
    
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
    
    # Créer l'aperçu (uniquement visible par l'admin)
    preview_embed = discord.Embed(
        title="💰 TEST - APERÇU DES SALAIRES",
        description="**📊 Simulation du calcul des salaires (rien n'est envoyé ou reset)**\n",
        color=EMS_RED
    )
    
    # Construire le tableau (limité à 15 employés pour rester sous 1024 caractères)
    salary_text = "```\n"
    salary_text += f"{'NOM':<18} | {'RÉAS':<4} | {'GRADE':<6} | {'TOTAL':>12}\n"
    salary_text += "-" * 50 + "\n"
    
    for emp in salary_data[:15]:  # Limiter à 15 pour éviter dépassement
        name_display = emp['name'][:16]
        grade_display = emp['grade'][:6]
        salary_text += f"{name_display:<18} | {emp['rea']:<4} | {grade_display:<6} | {emp['total']:>12,}$\n".replace(",", " ")
    
    if len(salary_data) > 15:
        salary_text += f"\n... et {len(salary_data) - 15} autres employés\n"
    
    salary_text += "```"
    
    preview_embed.add_field(name="📋 Liste des salaires (Top 15)", value=salary_text, inline=False)
    
    preview_embed.add_field(
        name="💵 TOTAL À RETIRER DU COFFRE",
        value=f"```{total_payroll:,}$```".replace(",", " "),
        inline=False
    )
    
    preview_embed.add_field(
        name="📊 STATISTIQUES",
        value=f"**Employés payés :** {len(salary_data)}\n**Total semaine :** {sum(stats.values())} réanimations",
        inline=False
    )
    
    preview_embed.set_footer(text="🚑 EMS System | Mode Test - Aucune modification effectuée")
    
    await interaction.followup.send(embed=preview_embed, ephemeral=True)
    confirm_embed.set_footer(text="🚑 EMS System")
    await interaction.followup.send(embed=confirm_embed)

@bot.tree.command(name="help", description="Affiche toutes les commandes et fonctionnalités du bot")
async def help_command(interaction: discord.Interaction):
    await interaction.response.defer()
    
    # Embed principal
    main_embed = discord.Embed(
        title="🚑 EMS MANAGEMENT SYSTEM - GUIDE COMPLET",
        description="Bienvenue dans le système de gestion EMS ! Voici toutes les fonctionnalités disponibles.",
        color=EMS_RED
    )
    main_embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    
    # Embed Système de Réanimations
    rea_embed = discord.Embed(
        title="📊 SYSTÈME DE RÉANIMATIONS",
        description="Comptage automatique des réanimations par employé",
        color=EMS_RED
    )
    rea_embed.add_field(
        name="📸 Comment ça marche ?",
        value="• Envoyez une image dans votre channel personnel (🔴, 🟠, 🟢)\n"
              "• Le bot ajoute automatiquement ✅\n"
              "• Votre compteur augmente de +1\n"
              "• La couleur du channel change selon vos performances",
        inline=False
    )
    rea_embed.add_field(
        name="🎨 Couleurs des channels",
        value="🔴 **Rouge** : 0-49 réas\n🟠 **Orange** : 50-99 réas\n🟢 **Vert** : 100+ réas",
        inline=False
    )
    
    # Embed Commandes Admin
    admin_embed = discord.Embed(
        title="👨‍💼 GESTION DU PERSONNEL",
        description="Commandes pour gérer les employés EMS",
        color=EMS_RED
    )
    admin_embed.add_field(
        name="/employer @membre",
        value="📋 Recrute un nouvel employé\n• Renomme en [EMT] Nom\n• Ajoute les rôles EMS\n• Crée un channel personnel\n• Place dans la catégorie EMT",
        inline=False
    )
    admin_embed.add_field(
        name="/up @membre",
        value="📈 Promotion au grade supérieur\n• EMT → INT → ADS → INF → MED → CDS → DIR\n• Change le tag du pseudo\n• Déplace le channel dans la bonne catégorie",
        inline=False
    )
    admin_embed.add_field(
        name="/virer @membre",
        value="🚫 Licencie un employé\n• Retire tous les rôles EMS\n• Reset le pseudo\n• Envoie un message privé de licenciement",
        inline=False
    )
    
    # Embed Statistiques
    stats_embed = discord.Embed(
        title="📊 STATISTIQUES & PAIES",
        description="Commandes pour consulter et gérer les stats et salaires",
        color=EMS_RED
    )
    stats_embed.add_field(
        name="/total",
        value="📈 Affiche toutes les statistiques de la semaine\n• Liste tous les employés\n• Nombre de réanimations par personne\n• Total général",
        inline=False
    )
    stats_embed.add_field(
        name="/payes",
        value="💰 **Calcul et annonce des salaires**\n• Demande une image du coffre\n• Calcule automatiquement les salaires :\n  - Direction : 9M fixe\n  - Autres : 30k-55k par réa selon grade\n  - Bonus : 150k par tranche de 10 réas au-dessus de 50\n• Affiche le total à retirer\n• Réinitialise la semaine automatiquement",
        inline=False
    )
    stats_embed.add_field(
        name="/semaine",
        value="🔄 Réinitialise la semaine complète\n• Envoie le bilan hebdomadaire dans les logs\n• Remet tous les compteurs à 0\n• Change tous les channels en 🔴\n• Annonce la nouvelle semaine avec bannière",
        inline=False
    )
    stats_embed.add_field(
        name="/reset",
        value="♻️ Réinitialise uniquement les compteurs\n(Sans bilan ni annonce)",
        inline=False
    )
    
    # Embed CV
    cv_embed = discord.Embed(
        title="📝 SYSTÈME DE RECRUTEMENT",
        description="Gestion automatique des candidatures",
        color=EMS_RED
    )
    cv_embed.add_field(
        name="/setup_cv",
        value="🎯 Affiche le bouton de candidature\n• Les candidats cliquent pour postuler\n• 13 questions automatiques\n• Upload de documents\n• Validation par la direction",
        inline=False
    )
    cv_embed.add_field(
        name="🔄 Processus automatique",
        value="• Channel privé créé pour chaque candidat\n• Questions posées une par une\n• 10 minutes par question\n• CV envoyé à la direction\n• Boutons ✅ Accepter / ❌ Refuser",
        inline=False
    )
    
    # Embed Taxi
    taxi_embed = discord.Embed(
        title="🚕 SYSTÈME TAXI",
        description="Comptage des tests d'aptitude taxi",
        color=discord.Color.gold()
    )
    taxi_embed.add_field(
        name="📊 Fonctionnement",
        value="• Réaction automatique ✅ sur chaque message dans le channel taxi\n"
              "• Comptage automatique des tests\n"
              "• Rapport hebdomadaire automatique (samedi 19h)\n"
              "• Calcul des revenus (500 000$ par test)",
        inline=False
    )
    taxi_embed.add_field(
        name="/taxi",
        value="📈 Affiche le compteur actuel des tests",
        inline=False
    )
    taxi_embed.add_field(
        name="/taxi_announce",
        value="📣 Envoie manuellement le rapport hebdomadaire",
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
        value="🔨 Crée automatiquement toutes les catégories\n• DIR, CDS, MED, INF, ADS, INT, EMT\n• Positionne au bon endroit\n• Sauvegarde les IDs pour les autres commandes",
        inline=False
    )
    cat_embed.add_field(
        name="/reorganize",
        value="🔄 Réorganise tous les channels existants\n• Scanne tous les channels EMS\n• Détecte le grade (emt-, int-, etc.)\n• Déplace dans la bonne catégorie\n• Rapport détaillé des changements",
        inline=False
    )
    
    # Embed Footer
    footer_embed = discord.Embed(
        title="ℹ️ INFORMATIONS",
        description=(
            "**🔐 Permissions requises :**\n"
            "La plupart des commandes nécessitent les permissions administrateur.\n\n"
            "**📞 Support :**\n"
            "En cas de problème, contactez la direction.\n\n"
            "**🔄 Mises à jour :**\n"
            "Le bot est automatiquement mis à jour via GitHub."
        ),
        color=EMS_RED
    )
    footer_embed.set_footer(text="🚑 EMS Management System | Développé avec ❤️")
    
    # Envoyer tous les embeds
    embeds = [main_embed, rea_embed, admin_embed, stats_embed, cv_embed, taxi_embed, cat_embed, footer_embed]
    for embed in embeds:
        await interaction.followup.send(embed=embed)

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

if __name__ == "__main__":
    if not config['TOKEN']:
        print("Erreur: TOKEN manquant. Vérifiez votre fichier config.json ou vos variables d'environnement.")
    else:
        try:
            bot.run(config['TOKEN'])
        except KeyboardInterrupt:
            print("Arrêt...")
        except Exception as e:
            print(f"Erreur: {e}")

