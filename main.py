import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
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

# Configuration Taxi
TAXI_CHANNEL_ID = 1456000685190418514
TAXI_ROLE_ID = 1163206112355561472
ROLE_DIRECTION_EMS_ID = 838120186585940010
ROLE_DIRECTION_TAXI_ID = 1311787019546136596

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

def save_stats(stats):
    atomic_write_json(STATS_FILE, stats)

## Système de badges supprimé pour simplifier et fiabiliser le flux

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
    
    # Embed d'annonce de semaine
    embed = discord.Embed(
        title="🚑 NOUVELLE SEMAINE !",
        description="**✅ Réinitialisation complète de la semaine**\n\n• Tous les compteurs remis à 0\n• Tous les channels en 🔴\n• C'est repartit de zéro !\n\n**Bonne chance à tous ! 💪**",
        color=EMS_RED
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1432501937085087896/1457439823215460487/image.png?ex=695ea51b&is=695d539b&hm=73669ae578193fac7bb528589592facb8ffa94a53f6521f1fad68165e393d32c&=&format=webp&quality=lossless&width=1872&height=571")
    embed.set_footer(text="🚑 EMS System | Nouvelle semaine, nouveau challenge !")

    # Envoyer l'annonce dans tous les channels avec emoji préfixe
    for channel in announcement_channels:
        try:
            await channel.send(embed=embed.copy())
        except:
            pass
    
    # Envoyer aussi dans le channel de logs
    log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
    if log_channel:
        try:
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
                await interaction.user.send("✅ Candidature reçue !")
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
    await interaction.channel.send(embed=embed, view=CVButton())
    await interaction.response.send_message("✅ Message de recrutement posté !", ephemeral=True)

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
    if os.path.exists(CHANNEL_MAP_FILE):
        with open(CHANNEL_MAP_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_channel_map(data):
    with open(CHANNEL_MAP_FILE, 'w') as f:
        json.dump(data, f, indent=4)

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

    # 3. Création du Channel
    category_id = 1017849358366031922
    channel_anchor_id = 995847557567746058
    
    category = guild.get_channel(category_id)
    channel_name = f"🔴emt-{clean_name.lower().replace(' ', '-')}"
    
    if category:
        # Créer le channel
        new_channel = await guild.create_text_channel(name=channel_name, category=category)
        
        # Positionnement
        anchor_channel = guild.get_channel(channel_anchor_id)
        if anchor_channel:
             # On le met à la position de l'ancre (ce qui pousse l'ancre vers le bas)
            try:
                await new_channel.edit(position=anchor_channel.position)
            except Exception as e:
                print(f"Erreur positionnement channel: {e}")

        # Sauvegarde du mapping
        mapping = load_channel_map()
        mapping[str(membre.id)] = new_channel.id
        save_channel_map(mapping)
        
        await interaction.followup.send(f"✅ **{membre.mention}** a été employé avec succès !\n📛 Renommé en `{new_nickname}`\n📂 Dossier créé : {new_channel.mention}")
    else:
        await interaction.followup.send(f"⚠️ Catégorie introuvable, rôles et pseudo mis à jour mais pas le channel.")


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

    # Optionnel: On pourrait supprimer le channel s'il existe dans la map, 
    # mais la demande ne le spécifiait pas explicitement ("enleve son pseudo... garde seulement le role").
    
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
            "move_above_id": 1024094792780619836 # ID spécifique demandé
        }
    elif R_INT in member_roles_ids:
        # INT -> ADS
        next_step = {
            "remove": R_INT, "add": R_ADS,
            "tag": "ADS", "chan_prefix": "🔴ads",
            "move_above_prefix": "🔴int" # Au dessus des INT
        }
    elif R_ADS in member_roles_ids:
        # ADS -> INF
        next_step = {
            "remove": R_ADS, "add": R_INF,
            "tag": "INF", "chan_prefix": "🔴inf",
            "move_above_prefix": "🔴ads" # Au dessus des ADS
        }
    elif R_INF in member_roles_ids:
        # INF -> MED
        next_step = {
            "remove": R_INF, "add": R_MED,
            "tag": "MED", "chan_prefix": "🔴med",
            "move_above_prefix": "🔴inf"
        }
    elif R_MED in member_roles_ids:
        # MED -> CDS
        next_step = {
            "remove": R_MED, "add": R_CDS,
            "tag": "CDS", "chan_prefix": "🔴cds",
            "move_above_prefix": "🔴med"
        }
    elif R_CDS in member_roles_ids:
        # CDS -> DIR
        next_step = {
            "remove": R_CDS, "add": R_DIR,
            "tag": "DIR", "chan_prefix": "🔴dir",
            "move_above_prefix": "🔴cds"
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
        await channel.edit(name=new_chan_name)
        
        # Move
        target_pos = None
        
        # Cas 1: ID spécifique (EMT -> INT)
        if "move_above_id" in next_step:
            anchor = guild.get_channel(next_step["move_above_id"])
            if anchor:
                target_pos = anchor.position
                
        # Cas 2: Au dessus d'un groupe (prefix)
        elif "move_above_prefix" in next_step:
            # Trouver le channel le plus haut (position la plus petite) qui a ce prefixe
            category = channel.category
            if category:
                prefix = next_step["move_above_prefix"]
                # On cherche tous les channels avec ce prefixe
                targets = [c for c in category.channels if c.name.startswith(prefix)]
                if targets:
                    # On veut être au dessus d'eux, donc on prend le min position
                    target_pos = min(t.position for t in targets)
                else:
                    # S'il n'y a personne de ce grade en dessous, on essaye de se mettre
                    # juste en dessous du grade actuel (ex: on est passé INF, y'a pas d'ADS, ou se met en bas des INF ?)
                    # Simple fallback: on ne bouge pas si on trouve pas
                    pass

        if target_pos is not None:
            try:
                await channel.edit(position=target_pos)
                chan_msg = f"\n📂 Dossier déplacé et renommé : {channel.mention}"
            except Exception as e:
                chan_msg = f"\n⚠️ Erreur déplacement dossier: {e}"
        else:
            chan_msg = f"\n📂 Dossier renommé (position inchangée) : {channel.mention}"

    await interaction.followup.send(f"📈 **Promotion effectuée pour {membre.mention}** !\nPassage au grade **{next_step['tag']}**.{chan_msg}")

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

