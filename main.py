import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import asyncio
import asyncio as _asyncio
import io
import base64
import time
import threading
import sys
import re as _re
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, send_file, request, render_template
from io import BytesIO
try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# Silencer les TimeoutError/NotFound sur toutes les interactions UI
async def _view_on_error(self, interaction, error, item):
    if not isinstance(error, (asyncio.TimeoutError, discord.errors.NotFound,
                               discord.errors.InteractionResponded)):
        print(f"[VIEW ERROR] {item}: {error}")
discord.ui.View.on_error = _view_on_error


def generate_debrief_chart(stats_list, title="DÃ©brief de la semaine"):
    """GÃ©nÃ¨re une image (bar chart) esthÃ©tique des rÃ©as par employÃ© pour l'annonce Discord.
    stats_list: [{'name': str, 'reas': int}, ...]
    Retourne un objet BytesIO (PNG) ou None si Pillow indisponible / liste vide."""
    if not _PIL_AVAILABLE or not stats_list:
        return None
    try:
        data = sorted(stats_list, key=lambda x: x['reas'], reverse=True)[:15]  # top 15 max pour lisibilitÃ©
        if not data:
            return None

        # Dimensions
        bar_h = 34
        gap = 10
        left_pad = 190
        right_pad = 60
        top_pad = 70
        bottom_pad = 30
        width = 760
        height = top_pad + len(data) * (bar_h + gap) + bottom_pad

        bg_color = (20, 20, 22)
        card_color = (30, 30, 34)
        red = (255, 59, 48)
        text_color = (255, 255, 255)
        sub_color = (150, 150, 155)

        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # Polices (fallback sur police par dÃ©faut si aucune TTF trouvÃ©e)
        def _load_font(size, bold=False):
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            ]
            for c_path in candidates:
                try:
                    return ImageFont.truetype(c_path, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        font_title = _load_font(26, bold=True)
        font_name = _load_font(16)
        font_value = _load_font(16, bold=True)

        # Titre
        draw.text((24, 24), f"ðŸ“‹ {title}", font=font_title, fill=text_color)

        max_reas = max((d['reas'] for d in data), default=1) or 1
        max_bar_width = width - left_pad - right_pad

        for i, d in enumerate(data):
            y = top_pad + i * (bar_h + gap)
            # Nom (tronquÃ© si trop long)
            name = d['name'][:22] + ('â€¦' if len(d['name']) > 22 else '')
            draw.text((24, y + bar_h//2 - 8), name, font=font_name, fill=text_color)

            # Fond de la barre (piste grise)
            draw.rounded_rectangle([left_pad, y, left_pad + max_bar_width, y + bar_h], radius=8, fill=card_color)

            # Barre rouge proportionnelle
            bar_width = max(6, int(max_bar_width * (d['reas'] / max_reas)))
            draw.rounded_rectangle([left_pad, y, left_pad + bar_width, y + bar_h], radius=8, fill=red)

            # Valeur Ã  droite de la barre
            draw.text((left_pad + max_bar_width + 12, y + bar_h//2 - 8), str(d['reas']), font=font_value, fill=text_color)

        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except Exception as _chart_err:
        print(f"Erreur generate_debrief_chart: {_chart_err}")
        return None


def make_ems_logo(size=64):
    """GÃ©nÃ¨re un petit logo EMS (croix blanche sur cercle rouge) directement en mÃ©moire."""
    logo_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    logo_draw = ImageDraw.Draw(logo_img)
    cx, cy, r = size/2, size/2, size/2 - 2
    logo_draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(190, 30, 30, 255))
    cross_w = size*0.16
    cross_len = size*0.62
    logo_draw.rounded_rectangle([cx-cross_w/2, cy-cross_len/2, cx+cross_w/2, cy+cross_len/2], radius=cross_w/3, fill=(255, 255, 255, 255))
    logo_draw.rounded_rectangle([cx-cross_len/2, cy-cross_w/2, cx+cross_len/2, cy+cross_w/2], radius=cross_w/3, fill=(255, 255, 255, 255))
    logo_draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(255, 255, 255, 200), width=2)
    return logo_img


_ATTESTATION_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')


def _attestation_font(size, bold=False, mono=False, script=False):
    """Charge une police EMBARQUÃ‰E dans le repo (fonts/) â€” indispensable car les polices
    systÃ¨me (DejaVu etc.) ne sont pas garanties prÃ©sentes sur l'environnement de dÃ©ploiement
    (Railway), ce qui causait un repli sur la police par dÃ©faut de Pillow qui ne gÃ¨re PAS
    correctement les caractÃ¨res accentuÃ©s (Ã©, Ã¨, Ã ...)."""
    if script:
        path = os.path.join(_ATTESTATION_FONTS_DIR, 'DancingScript-Bold.ttf')
    elif mono:
        path = os.path.join(_ATTESTATION_FONTS_DIR, 'DejaVuSansMono.ttf')
    elif bold:
        path = os.path.join(_ATTESTATION_FONTS_DIR, 'DejaVuSans-Bold.ttf')
    else:
        path = os.path.join(_ATTESTATION_FONTS_DIR, 'DejaVuSans.ttf')
    try:
        f = ImageFont.truetype(path, size)
        if script:
            try:
                f.set_variation_by_name('Bold')
            except Exception:
                pass
        return f
    except Exception as _font_err:
        print(f"Erreur chargement police {path}: {_font_err}")
        return ImageFont.load_default()


def generate_attestation_medicale(data):
    """GÃ©nÃ¨re l'image d'une attestation mÃ©dicale/rapport d'intervention officiel EMS,
    Ã  partir des infos saisies lors du remplissage d'un dossier patient.
    data attend: ref_doc, emetteur, destinataire, date_doc, nom, prenom, date_naissance,
    heure, lieu, motif, avis_intro, disposition, note (optionnel),
    praticien_nom, praticien_grade, praticien_prenom_sig, footer,
    photo_bytes (optionnel, bytes bruts de la carte d'identitÃ© â€” intÃ©grÃ©e sur le document).
    Retourne un BytesIO (PNG) ou None si Pillow indisponible."""
    if not _PIL_AVAILABLE:
        return None
    try:
        import math as _math

        W = 940
        PAD = 46
        BLACK = (25, 25, 28)
        GRAY = (120, 120, 125)
        LINE = (40, 40, 45)
        ACCENT = (178, 30, 30)
        SECTION_BG = (247, 247, 248)

        f_logo = _attestation_font(17, bold=True)
        f_logo_sub = _attestation_font(11)
        f_head_r = _attestation_font(11, bold=True)
        f_title = _attestation_font(16, bold=True)
        f_label = _attestation_font(12, bold=True)
        f_value = _attestation_font(12)
        f_section = _attestation_font(12, bold=True)
        f_body = _attestation_font(12)
        f_sig = _attestation_font(46, script=True)
        f_sig_sub_label = _attestation_font(10, bold=True)
        f_sig_sub = _attestation_font(11)
        f_footer = _attestation_font(9, bold=True)
        stamp_font = _attestation_font(11, bold=True)

        def wrap_text(draw, text, font, max_width):
            words = (text or '').split()
            lines = []
            cur = ""
            for w in words:
                test = (cur + " " + w).strip()
                if draw.textlength(test, font=font) <= max_width:
                    cur = test
                else:
                    if cur:
                        lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
            return lines or ['â€”']

        tmp_img = Image.new('RGB', (W, 100))
        tmp_draw = ImageDraw.Draw(tmp_img)
        motif_lines = wrap_text(tmp_draw, data.get('motif', ''), f_value, 400)
        avis_lines = wrap_text(tmp_draw, data.get('avis_intro', ''), f_body, W - 2*PAD - 40)
        note_lines = wrap_text(tmp_draw, data.get('note', ''), f_body, W-2*PAD-40) if data.get('note') else []

        H = 1250 + len(motif_lines)*16 + len(avis_lines)*18 + len(note_lines)*17
        img = Image.new('RGB', (W, H), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        y = PAD

        logo = make_ems_logo(46)
        img.paste(logo, (PAD, y-2), logo)
        draw.text((PAD+56, y), "CENTRE MÃ‰DICAL - EMS", font=f_logo, fill=BLACK)
        draw.text((PAD+56, y+22), "Emergency Medical Services Â· Los Santos", font=f_logo_sub, fill=GRAY)

        right_x = W - PAD
        lines_r = [
            ("LOS SANTOS MEDICAL CENTER", f_head_r),
            ("Central District, Pillbox Hill", f_logo_sub),
            ("Urgences: 911 / EMS", f_logo_sub),
            (f"RÃ©f Doc: {data.get('ref_doc','â€”')}", f_logo_sub),
        ]
        ry = y
        for txt, fnt in lines_r:
            w = draw.textlength(txt, font=fnt)
            draw.text((right_x - w, ry), txt, font=fnt, fill=BLACK if fnt == f_head_r else GRAY)
            ry += 15

        y += 60
        draw.line([(PAD, y), (W-PAD, y)], fill=ACCENT, width=2)
        y += 20

        draw.rounded_rectangle([PAD, y, W-PAD, y+38], radius=6, fill=(30, 30, 34))
        title = "RAPPORT D'INTERVENTION & ATTESTATION D'ARRÃŠT DE TRAVAIL"
        tw = draw.textlength(title, font=f_title)
        draw.text(((W-tw)/2, y+11), title, font=f_title, fill=(255, 255, 255))
        y += 38 + 16

        def section_label(text, yy):
            draw.text((PAD, yy), text, font=f_section, fill=ACCENT)
            return yy + 20

        def table_row(label, value, yy, h=32, width=None):
            w = width if width is not None else (W - 2*PAD)
            draw.rounded_rectangle([PAD, yy, PAD+w, yy+h], radius=5, outline=LINE, width=1)
            draw.line([(PAD+160, yy+2), (PAD+160, yy+h-2)], fill=(210, 210, 212), width=1)
            draw.text((PAD+12, yy+h/2-7), label, font=f_label, fill=BLACK)
            draw.text((PAD+172, yy+h/2-7), value or 'â€”', font=f_value, fill=BLACK)
            return yy + h + 6

        y = table_row("Ã‰METTEUR", data.get('emetteur', ''), y)
        y = table_row("DESTINATAIRE", data.get('destinataire', ''), y)
        y = table_row("DATE DU DOCUMENT", data.get('date_doc', ''), y)
        y += 14

        y = section_label("INFORMATIONS PATIENT", y)

        id_photo_bytes = data.get('photo_bytes')
        id_w, id_h = 132, 104
        patient_table_w = (W - 2*PAD)
        if id_photo_bytes:
            patient_table_w = (W - 2*PAD) - id_w - 16

        row_start_y = y
        y = table_row("Nom :", data.get('nom', ''), y, width=patient_table_w)
        y = table_row("PrÃ©nom :", data.get('prenom', ''), y, width=patient_table_w)
        y = table_row("Date de naissance :", data.get('date_naissance') or 'â€”', y, width=patient_table_w)

        if id_photo_bytes:
            try:
                id_img = Image.open(BytesIO(id_photo_bytes)).convert('RGB')
                src_ratio = id_img.width / id_img.height
                dst_ratio = id_w / id_h
                if src_ratio > dst_ratio:
                    new_w = int(id_img.height * dst_ratio)
                    left = (id_img.width - new_w) // 2
                    id_img = id_img.crop((left, 0, left + new_w, id_img.height))
                else:
                    new_h = int(id_img.width / dst_ratio)
                    top = (id_img.height - new_h) // 2
                    id_img = id_img.crop((0, top, id_img.width, top + new_h))
                id_img = id_img.resize((id_w, id_h))
                photo_x = PAD + patient_table_w + 16
                photo_y = row_start_y
                draw.rounded_rectangle([photo_x-3, photo_y-3, photo_x+id_w+3, photo_y+id_h+3], radius=6, outline=LINE, width=2)
                img.paste(id_img, (photo_x, photo_y))
                cap_font = _attestation_font(8, bold=True)
                cap = "PIÃˆCE D'IDENTITÃ‰"
                cw = draw.textlength(cap, font=cap_font)
                draw.text((photo_x + id_w/2 - cw/2, photo_y + id_h + 6), cap, font=cap_font, fill=GRAY)
            except Exception as _photo_err:
                print(f"Erreur intÃ©gration photo attestation: {_photo_err}")

        y += 14

        y = section_label("DÃ‰TAILS DE L'INTERVENTION", y)
        y = table_row("Heure de prise en charge :", data.get('heure', ''), y)
        y = table_row("Lieu de l'incident :", data.get('lieu', ''), y)

        mh = 32 + max(0, len(motif_lines)-1)*16
        draw.rounded_rectangle([PAD, y, W-PAD, y+mh], radius=5, outline=LINE, width=1)
        draw.line([(PAD+160, y+2), (PAD+160, y+mh-2)], fill=(210, 210, 212), width=1)
        draw.text((PAD+12, y+mh/2-7 if len(motif_lines) <= 1 else y+10), "Motif d'intervention :", font=f_label, fill=BLACK)
        my = y + (mh/2 - (len(motif_lines)*16)/2 + 2)
        for line in motif_lines:
            draw.text((PAD+172, my), line, font=f_value, fill=BLACK)
            my += 16
        y += mh + 20

        y = section_label("AVIS MÃ‰DICAL ET DISPOSITIONS", y)
        box_h = len(avis_lines)*18 + 24
        draw.rounded_rectangle([PAD, y, W-PAD, y+box_h], radius=6, fill=SECTION_BG, outline=(210, 210, 212), width=1)
        ty = y + 12
        for line in avis_lines:
            draw.text((PAD+16, ty), line, font=f_body, fill=BLACK)
            ty += 18
        y += box_h + 18

        disp_h = 48
        draw.rounded_rectangle([PAD, y, W-PAD, y+disp_h], radius=6, fill=(252, 238, 238), outline=ACCENT, width=2)
        dlines = wrap_text(draw, data.get('disposition', ''), f_label, W-2*PAD-30)
        dty = y + disp_h/2 - (len(dlines)*16)/2
        for line in dlines:
            dw = draw.textlength(line, font=f_label)
            draw.text(((W-dw)/2, dty), line, font=f_label, fill=ACCENT)
            dty += 16
        y += disp_h + 26

        if note_lines:
            draw.rounded_rectangle([PAD, y, W-PAD, y + len(note_lines)*17 + 22], radius=6, fill=SECTION_BG, outline=(210, 210, 212), width=1)
            ny = y + 11
            for line in note_lines:
                draw.text((PAD+14, ny), line, font=f_body, fill=BLACK)
                ny += 17
            y += len(note_lines)*17 + 22 + 26
        else:
            y += 8

        draw.line([(PAD, y), (PAD+220, y)], fill=(210, 210, 212), width=1)
        y += 14
        draw.text((PAD, y), "LE PRATICIEN RÃ‰FÃ‰RENT", font=f_sig_sub_label, fill=GRAY)
        y += 22
        draw.text((PAD-4, y-10), data.get('praticien_prenom_sig', ''), font=f_sig, fill=(35, 35, 90))
        y += 54
        draw.text((PAD, y), data.get('praticien_nom', ''), font=_attestation_font(13, bold=True), fill=BLACK)
        y += 18
        draw.text((PAD, y), data.get('praticien_grade', ''), font=f_sig_sub, fill=GRAY)

        cx, cy, r = W - PAD - 100, y - 40, 62
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=ACCENT, width=2)
        draw.ellipse([cx-r+7, cy-r+7, cx+r-7, cy+r-7], outline=ACCENT, width=1)
        label = "VALIDÃ‰ & CERTIFIÃ‰"
        lw = draw.textlength(label, font=stamp_font)
        draw.rectangle([cx-lw/2-6, cy-8, cx+lw/2+6, cy+8], outline=ACCENT, width=1)
        draw.text((cx-lw/2, cy-7), label, font=stamp_font, fill=ACCENT)
        n_dashes = 40
        for i in range(n_dashes):
            angle = 2*_math.pi*i/n_dashes
            x1 = cx + (r+3)*_math.cos(angle)
            y1 = cy + (r+3)*_math.sin(angle)
            x2 = cx + (r+7)*_math.cos(angle)
            y2 = cy + (r+7)*_math.sin(angle)
            draw.line([(x1, y1), (x2, y2)], fill=ACCENT, width=1)

        y += 70
        draw.line([(PAD, y), (W-PAD, y)], fill=(210, 210, 212), width=1)
        y += 14
        footer_lines = wrap_text(draw, data.get('footer', ''), f_footer, W-2*PAD)
        for line in footer_lines:
            fw = draw.textlength(line, font=f_footer)
            draw.text(((W-fw)/2, y), line, font=f_footer, fill=ACCENT)
            y += 12

        final = img.crop((0, 0, W, min(y+30, H)))
        buf = BytesIO()
        final.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except Exception as _att_err:
        print(f"Erreur generate_attestation_medicale: {_att_err}")
        return None


# ============================================================
# BILAN D'APTITUDE â€” Templates variÃ©s (pour Ã©viter le copier-coller)
# ============================================================
_PSYCHO_APTE = [
    "L'agent a passÃ© son Ã©valuation psychologique avec succÃ¨s. Il fait preuve d'un bon discernement, prÃ©sente un raisonnement clair et cohÃ©rent, et ne montre aucun signe d'anomalie sur le plan psychologique. Au vu des rÃ©sultats obtenus, rien ne s'oppose Ã  son aptitude Ã  exercer ses fonctions. {civ} {nom} possÃ¨de les qualitÃ©s requises pour devenir un excellent agent.",
    "Suite Ã  l'entretien psychologique menÃ© ce jour, {civ} {nom} dÃ©montre une stabilitÃ© Ã©motionnelle satisfaisante, une capacitÃ© d'analyse pertinente et un sens du jugement appropriÃ© Ã  la fonction. Aucun Ã©lÃ©ment ne remet en cause son aptitude psychologique Ã  exercer.",
    "L'Ã©valuation psychologique de {civ} {nom} n'a rÃ©vÃ©lÃ© aucune contre-indication. Le candidat fait preuve de calme, de rigueur et d'un raisonnement structurÃ©, autant de qualitÃ©s essentielles Ã  l'exercice de ses futures fonctions.",
    "AprÃ¨s un entretien approfondi, il ressort que {civ} {nom} prÃ©sente un profil psychologique compatible avec les exigences du poste : contrÃ´le de soi, clartÃ© d'esprit et absence de troubles dÃ©celables.",
    "L'entretien menÃ© avec {civ} {nom} met en Ã©vidence une bonne gestion du stress, une capacitÃ© d'adaptation solide et un jugement mesurÃ©. Aucune rÃ©serve psychologique n'est Ã  signaler.",
]
_PSYCHO_INAPTE = [
    "L'Ã©valuation psychologique de {civ} {nom} a mis en Ã©vidence des Ã©lÃ©ments incompatibles avec l'exercice de la fonction visÃ©e Ã  ce jour. Un suivi complÃ©mentaire est recommandÃ© avant toute nouvelle Ã©valuation.",
    "Suite Ã  l'entretien menÃ© ce jour, des rÃ©serves sÃ©rieuses ont Ã©tÃ© Ã©mises quant Ã  l'aptitude psychologique de {civ} {nom}. Il est recommandÃ© de ne pas valider sa prise de fonction en l'Ã©tat.",
    "L'examen psychologique de {civ} {nom} rÃ©vÃ¨le des signes d'instabilitÃ© incompatibles avec les exigences du poste actuellement. Une rÃ©Ã©valuation ultÃ©rieure pourra Ãªtre envisagÃ©e.",
]
_SANTE_APTE = [
    "Aptitude favorable. Une surveillance de routine est toutefois recommandÃ©e dans le cadre du suivi de l'agent, afin de s'assurer du maintien de son Ã©quilibre psychologique et de son aptitude Ã  exercer ses fonctions.",
    "L'examen mÃ©dical ne rÃ©vÃ¨le aucune contre-indication Ã  l'exercice de la fonction. Un contrÃ´le de routine annuel est conseillÃ© pour assurer un suivi optimal.",
    "Sur le plan physique, {civ} {nom} est jugÃ© apte sans rÃ©serve. Il est conseillÃ© de maintenir un suivi mÃ©dical rÃ©gulier conformÃ©ment aux protocoles standards.",
    "Bilan de santÃ© gÃ©nÃ©ral satisfaisant. Aucune restriction mÃ©dicale n'est Ã  signaler ; un suivi de routine reste nÃ©anmoins recommandÃ©.",
    "L'examen clinique de {civ} {nom} ne prÃ©sente aucune anomalie. La condition physique est jugÃ©e compatible avec les exigences du mÃ©tier, sous rÃ©serve d'un suivi mÃ©dical annuel.",
]
_SANTE_INAPTE = [
    "L'examen mÃ©dical rÃ©vÃ¨le des Ã©lÃ©ments nÃ©cessitant une prise en charge avant toute reprise d'activitÃ©. L'aptitude ne peut Ãªtre validÃ©e en l'Ã©tat.",
    "Des rÃ©serves mÃ©dicales ont Ã©tÃ© constatÃ©es lors du bilan de santÃ© de {civ} {nom}. Une nouvelle Ã©valuation est requise aprÃ¨s rÃ©tablissement.",
    "Sur le plan physique, {civ} {nom} prÃ©sente actuellement des contre-indications Ã  l'exercice de la fonction. Un suivi mÃ©dical est requis avant rÃ©Ã©valuation.",
]


def generate_aptitude_report(data):
    """GÃ©nÃ¨re l'image d'un bilan d'aptitude psychologique et mÃ©dicale (LSPD/BCSO),
    avec des textes variÃ©s Ã  chaque gÃ©nÃ©ration pour Ã©viter le copier-coller.
    data attend: org ('LSPD'|'BCSO'), matricule, nom_officier, civilite ('m'|'mme'),
    apte (bool), praticien_nom, praticien_grade, ref_doc, date_doc, photo_bytes (optionnel).
    Retourne un BytesIO (PNG) ou None si Pillow indisponible."""
    if not _PIL_AVAILABLE:
        return None
    try:
        import math as _math
        import random as _random

        W = 940
        PAD = 46
        BLACK = (25, 25, 28)
        GRAY = (120, 120, 125)
        LINE = (40, 40, 45)
        ACCENT = (178, 30, 30)
        SECTION_BG = (247, 247, 248)
        APTE = bool(data.get('apte'))
        STATUS_COLOR = (30, 140, 60) if APTE else (178, 30, 30)
        STATUS_BG = (232, 247, 236) if APTE else (252, 238, 238)

        f_logo = _attestation_font(17, bold=True)
        f_logo_sub = _attestation_font(11)
        f_head_r = _attestation_font(11, bold=True)
        f_title = _attestation_font(16, bold=True)
        f_label = _attestation_font(12, bold=True)
        f_value = _attestation_font(12)
        f_section = _attestation_font(12, bold=True)
        f_body = _attestation_font(12)
        f_sig = _attestation_font(46, script=True)
        f_sig_sub_label = _attestation_font(10, bold=True)
        f_sig_sub = _attestation_font(11)
        f_footer = _attestation_font(9, bold=True)
        f_status = _attestation_font(22, bold=True)

        def wrap_text(draw, text, font, max_width):
            words = (text or '').split()
            lines, cur = [], ""
            for w in words:
                test = (cur + " " + w).strip()
                if draw.textlength(test, font=font) <= max_width:
                    cur = test
                else:
                    if cur:
                        lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
            return lines or ['â€”']

        civ = 'Madame' if data.get('civilite') == 'mme' else 'Monsieur'
        nom_officier = data.get('nom_officier', '')
        psycho_text = _random.choice(_PSYCHO_APTE if APTE else _PSYCHO_INAPTE).format(civ=civ, nom=nom_officier)
        sante_text = _random.choice(_SANTE_APTE if APTE else _SANTE_INAPTE).format(civ=civ, nom=nom_officier)

        tmp_img = Image.new('RGB', (W, 100))
        tmp_draw = ImageDraw.Draw(tmp_img)
        psy_lines = wrap_text(tmp_draw, psycho_text, f_body, W - 2*PAD - 40)
        sante_lines = wrap_text(tmp_draw, sante_text, f_body, W - 2*PAD - 40)

        H = 1100 + len(psy_lines)*18 + len(sante_lines)*18
        img = Image.new('RGB', (W, H), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        y = PAD

        logo = make_ems_logo(46)
        img.paste(logo, (PAD, y-2), logo)
        draw.text((PAD+56, y), "CENTRE MÃ‰DICAL - EMS", font=f_logo, fill=BLACK)
        draw.text((PAD+56, y+22), "Bilan d'Aptitude Psychologique & MÃ©dicale", font=f_logo_sub, fill=GRAY)

        right_x = W - PAD
        org_label = "LOS SANTOS POLICE DEPARTMENT" if data.get('org') == 'LSPD' else "BLAINE COUNTY SHERIFF'S OFFICE"
        lines_r = [
            (org_label, f_head_r),
            (f"RÃ©f Doc: {data.get('ref_doc','â€”')}", f_logo_sub),
            (data.get('date_doc', ''), f_logo_sub),
        ]
        ry = y
        for txt, fnt in lines_r:
            w = draw.textlength(txt, font=fnt)
            draw.text((right_x - w, ry), txt, font=fnt, fill=BLACK if fnt == f_head_r else GRAY)
            ry += 15

        y += 60
        draw.line([(PAD, y), (W-PAD, y)], fill=ACCENT, width=2)
        y += 20

        title = "BILAN D'APTITUDE â€” Ã‰VALUATION PSYCHOLOGIQUE ET MÃ‰DICALE"
        draw.rounded_rectangle([PAD, y, W-PAD, y+38], radius=6, fill=(30, 30, 34))
        tw = draw.textlength(title, font=f_title)
        draw.text(((W-tw)/2, y+11), title, font=f_title, fill=(255, 255, 255))
        y += 38 + 16

        def section_label(text, yy):
            draw.text((PAD, yy), text, font=f_section, fill=ACCENT)
            return yy + 20

        def table_row(label, value, yy, h=32, width=None):
            w = width if width is not None else (W - 2*PAD)
            draw.rounded_rectangle([PAD, yy, PAD+w, yy+h], radius=5, outline=LINE, width=1)
            draw.line([(PAD+160, yy+2), (PAD+160, yy+h-2)], fill=(210, 210, 212), width=1)
            draw.text((PAD+12, yy+h/2-7), label, font=f_label, fill=BLACK)
            draw.text((PAD+172, yy+h/2-7), value or 'â€”', font=f_value, fill=BLACK)
            return yy + h + 6

        y = section_label("INFORMATIONS DE L'OFFICIER", y)
        id_w, id_h = 132, 104
        id_photo_bytes = data.get('photo_bytes')
        table_w = (W - 2*PAD) - id_w - 16 if id_photo_bytes else (W - 2*PAD)
        row_y = y
        y = table_row("Organisation :", org_label, y, width=table_w)
        y = table_row("Matricule :", data.get('matricule', ''), y, width=table_w)
        y = table_row("Nom de l'officier :", nom_officier, y, width=table_w)

        if id_photo_bytes:
            try:
                id_img = Image.open(BytesIO(id_photo_bytes)).convert('RGB')
                sr = id_img.width / id_img.height
                dr = id_w / id_h
                if sr > dr:
                    nw = int(id_img.height * dr)
                    l = (id_img.width - nw) // 2
                    id_img = id_img.crop((l, 0, l+nw, id_img.height))
                else:
                    nh = int(id_img.width / dr)
                    t = (id_img.height - nh) // 2
                    id_img = id_img.crop((0, t, id_img.width, t+nh))
                id_img = id_img.resize((id_w, id_h))
                px, py = PAD + table_w + 16, row_y
                draw.rounded_rectangle([px-3, py-3, px+id_w+3, py+id_h+3], radius=6, outline=LINE, width=2)
                img.paste(id_img, (px, py))
                cap_font = _attestation_font(8, bold=True)
                cap = "PIÃˆCE D'IDENTITÃ‰"
                cw = draw.textlength(cap, font=cap_font)
                draw.text((px + id_w/2 - cw/2, py + id_h + 6), cap, font=cap_font, fill=GRAY)
            except Exception as _e:
                print(f"Erreur photo bilan aptitude: {_e}")
        y += 14

        status_h = 50
        draw.rounded_rectangle([PAD, y, W-PAD, y+status_h], radius=8, fill=STATUS_BG, outline=STATUS_COLOR, width=2)
        status_txt = "âœ… APTE Ã€ EXERCER" if APTE else "â›” NON APTE Ã€ EXERCER"
        sw = draw.textlength(status_txt, font=f_status)
        draw.text(((W-sw)/2, y+status_h/2-13), status_txt, font=f_status, fill=STATUS_COLOR)
        y += status_h + 22

        y = section_label("BILAN PSYCHOLOGIQUE", y)
        bh = len(psy_lines)*18 + 24
        draw.rounded_rectangle([PAD, y, W-PAD, y+bh], radius=6, fill=SECTION_BG, outline=(210, 210, 212), width=1)
        ty = y + 12
        for l in psy_lines:
            draw.text((PAD+16, ty), l, font=f_body, fill=BLACK)
            ty += 18
        y += bh + 18

        y = section_label("BILAN DE SANTÃ‰", y)
        bh2 = len(sante_lines)*18 + 24
        draw.rounded_rectangle([PAD, y, W-PAD, y+bh2], radius=6, fill=SECTION_BG, outline=(210, 210, 212), width=1)
        ty = y + 12
        for l in sante_lines:
            draw.text((PAD+16, ty), l, font=f_body, fill=BLACK)
            ty += 18
        y += bh2 + 26

        draw.line([(PAD, y), (PAD+220, y)], fill=(210, 210, 212), width=1)
        y += 14
        draw.text((PAD, y), "LE PRATICIEN RÃ‰FÃ‰RENT", font=f_sig_sub_label, fill=GRAY)
        y += 22
        draw.text((PAD-4, y-10), data.get('praticien_nom', ''), font=f_sig, fill=(35, 35, 90))
        y += 54
        draw.text((PAD, y), data.get('praticien_nom', ''), font=_attestation_font(13, bold=True), fill=BLACK)
        y += 18
        draw.text((PAD, y), data.get('praticien_grade', ''), font=f_sig_sub, fill=GRAY)

        # Badge EMS (logo rond, en bas Ã  droite du document)
        badge_size = 110
        bx, by = W - PAD - badge_size, y - 70
        badge = make_ems_logo(badge_size)
        img.paste(badge, (bx, by), badge)
        bt_font = _attestation_font(9, bold=True)
        bt = "EMS LOS SANTOS"
        btw = draw.textlength(bt, font=bt_font)
        draw.text((bx + badge_size/2 - btw/2, by + badge_size + 4), bt, font=bt_font, fill=GRAY)

        y += 90
        draw.line([(PAD, y), (W-PAD, y)], fill=(210, 210, 212), width=1)
        y += 14
        footer = "DOCUMENT OFFICIEL EMS LOS SANTOS â€” RAPPORT D'APTITUDE CONFIDENTIEL â€” TOUTE FALSIFICATION EST PASSIBLE DE POURSUITES."
        for l in wrap_text(draw, footer, f_footer, W-2*PAD):
            fw = draw.textlength(l, font=f_footer)
            draw.text(((W-fw)/2, y), l, font=f_footer, fill=ACCENT)
            y += 12

        final = img.crop((0, 0, W, min(y+30, H)))
        buf = BytesIO()
        final.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except Exception as _apt_err:
        print(f"Erreur generate_aptitude_report: {_apt_err}")
        return None


# ============================================================
# DÃ‰TECTION IA â€” Analyse linguistique des rÃ©ponses CV
# ============================================================

# Marqueurs linguistiques typiques des textes IA en franÃ§ais
_IA_PATTERNS = [
    # Connecteurs trop formels / transitions IA typiques
    r"\ben effet\b", r"\bde plus\b", r"\bpar ailleurs\b", r"\bainsi\b",
    r"\btoutefois\b", r"\bnÃ©anmoins\b", r"\bcependant\b", r"\bnotamment\b",
    r"\ben outre\b", r"\bÃ©galement\b", r"\bpar consÃ©quent\b", r"\bdÃ¨s lors\b",
    r"\bil convient de\b", r"\bil est important de\b", r"\bdans ce cadre\b",
    r"\bdans cette optique\b", r"\bdans le but de\b", r"\bc'est pourquoi\b",
    r"\bÃ  cet Ã©gard\b", r"\ben ce sens\b", r"\bforce est de constater\b",
    r"\bil va sans dire\b", r"\bÃ  titre d'exemple\b", r"\bÃ  travers\b",
    r"\ben premier lieu\b", r"\ben second lieu\b", r"\bpremiÃ¨rement\b",
    r"\bdeuxiÃ¨mement\b", r"\btroisiÃ¨mement\b", r"\bpour conclure\b",
    r"\ben conclusion\b", r"\nen rÃ©sumÃ©\b", r"\ben somme\b",
    # Formules IA auto-rÃ©fÃ©rentielles
    r"\bien sÃ»r\b", r"\bsans aucun doute\b", r"\bla question est\b",
    r"\bje suis convaincu\b", r"\bje suis persuadÃ©\b", r"\bje suis dÃ©terminÃ©\b",
    r"\bfaire preuve de\b", r"\bm'Ã©panouir\b", r"\bcontribuer\b",
    r"\bm'investir pleinement\b", r"\bapporter ma pierre\b",
    r"\brelever les dÃ©fis\b", r"\bmettre Ã  profit\b",
    r"\bmon parcours\b.*\bm'a permis\b", r"\bforte de\b.*\bexpÃ©rience\b",
]

# Mots distinctifs trÃ¨s frÃ©quents dans les textes IA
_IA_KEYWORDS = [
    "passionnÃ©", "dÃ©vouÃ©", "rigoureux", "polyvalent", "dynamique",
    "compÃ©tences", "professionnel", "profil", "opportunitÃ©",
    "m'Ã©panouir", "m'investir", "collaborer", "synergie",
    "valeurs", "engagement", "enrichissant", "stimulant",
    "dÃ©velopper mes compÃ©tences", "rejoindre votre Ã©quipe",
    "votre organisation", "vos critÃ¨res", "votre structure",
]

def _detect_ia(text: str) -> dict:
    """
    Analyse un texte et retourne un score IA + les indices dÃ©tectÃ©s.
    Score: 0.0 (humain) Ã  1.0 (trÃ¨s probablement IA)
    """
    if not text or len(text.strip()) < 30:
        return {"score": 0.0, "indices": [], "verdict": "trop_court"}

    t = text.lower()
    score = 0.0
    indices = []

    # 1. Patterns linguistiques formels
    pattern_hits = 0
    for p in _IA_PATTERNS:
        if _re.search(p, t):
            pattern_hits += 1
    if pattern_hits >= 3:
        score += 0.35
        indices.append(f"{pattern_hits} connecteurs formels dÃ©tectÃ©s")
    elif pattern_hits >= 1:
        score += 0.10
        indices.append(f"{pattern_hits} connecteur(s) formel(s)")

    # 2. Mots-clÃ©s caractÃ©ristiques
    kw_hits = sum(1 for kw in _IA_KEYWORDS if kw in t)
    if kw_hits >= 4:
        score += 0.30
        indices.append(f"{kw_hits} mots-clÃ©s IA dÃ©tectÃ©s")
    elif kw_hits >= 2:
        score += 0.15
        indices.append(f"{kw_hits} mots-clÃ©s IA")

    # 3. Longueur et structure â€” l'IA Ã©crit souvent plus long et plus structurÃ©
    words = text.split()
    if len(words) > 80:
        score += 0.15
        indices.append(f"RÃ©ponse trÃ¨s longue ({len(words)} mots)")
    elif len(words) > 50:
        score += 0.05

    # 4. Phrases trÃ¨s longues (IA rarement utilise de courtes phrases)
    sentences = [s.strip() for s in _re.split(r'[.!?]', text) if s.strip()]
    if sentences:
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
        if avg_len > 20:
            score += 0.15
            indices.append(f"Phrases longues (moy. {avg_len:.0f} mots/phrase)")

    # 5. Absence de fautes / argot / abrÃ©viations â†’ trop parfait
    has_informal = bool(_re.search(r"\blol\b|\bsvp\b|\bpk\b|\bnn\b|\bbjr\b|\bslt\b|\bcc\b|\bdacc\b|\.{2,}|!{2,}|\?{2,}", t))
    if not has_informal and len(words) > 40:
        score += 0.05
        indices.append("Aucune marque d'Ã©criture informelle")

    # Plafonner Ã  1.0
    score = min(score, 1.0)

    if score >= 0.65:
        verdict = "ia_probable"
    elif score >= 0.35:
        verdict = "suspect"
    else:
        verdict = "humain"

    return {"score": round(score, 2), "indices": indices, "verdict": verdict}


_IA_WARNING_COUNTS: dict[int, int] = {}  # {user_id: nombre_avertissements}

PARIS_TZ = ZoneInfo("Europe/Paris")

def now_paris():
    return datetime.now(PARIS_TZ)

# Logger visible dans Railway (force stderr + flush)
def log(msg):
    ts = now_paris().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}', file=sys.stderr, flush=True)

# --- CONFIGURATION ---
# Support Ã  la fois config.json (local) et variables d'environnement (Railway)
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

# RÃ©pertoire de donnÃ©es persistant (volume Railway ou local)
DATA_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ".")
if DATA_DIR != "." and not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

STATS_FILE = os.path.join(DATA_DIR, 'stats.json')
TAXI_STATS_FILE = os.path.join(DATA_DIR, 'taxi_stats.json')
CHANNEL_MAP_FILE = os.path.join(DATA_DIR, 'channel_map.json')
CATEGORIES_FILE = os.path.join(DATA_DIR, 'categories.json')
BONUSES_WEEK_FILE = os.path.join(DATA_DIR, 'bonuses_week.json')
SERVICE_FILE = os.path.join(DATA_DIR, 'services.json')
DAILY_REAS_FILE = os.path.join(DATA_DIR, 'daily_reas.json')  # {"YYYY-MM-DD": {employee_key: count}}
EMBAUCHE_FILE = os.path.join(DATA_DIR, 'embauche.json')  # {employee_key: "YYYY-MM-DD"}
SERVICE_MSG_FILE = os.path.join(DATA_DIR, 'service_message.json')
AVERT_FILE_PATH = os.path.join(DATA_DIR, 'avertissements.json')
DISPATCH_HISTORY_FILE = os.path.join(DATA_DIR, 'dispatch_history.json')
FORMATIONS_FILE = os.path.join(DATA_DIR, 'formations.json')
VIRER_REMINDERS_FILE = os.path.join(DATA_DIR, 'virer_reminders.json')
CV_TRACKING_FILE = os.path.join(DATA_DIR, 'cv_tracking.json')
PROMO_HISTORY_FILE = os.path.join(DATA_DIR, 'promo_history.json')
PATIENTS_FILE = os.path.join(DATA_DIR, 'patients.json')
PATIENT_PHOTOS_DIR = os.path.join(DATA_DIR, 'patient_photos')
os.makedirs(PATIENT_PHOTOS_DIR, exist_ok=True)

def save_patient_photo(pid: str, data_uri: str) -> str:
    """DÃ©code une image data-URI base64 et la sauvegarde comme fichier sÃ©parÃ©
    (au lieu de la stocker dans patients.json, ce qui alourdirait ce fichier
    et ralentirait chaque lecture/Ã©criture). Retourne le nom de fichier relatif."""
    try:
        if not data_uri or not data_uri.startswith('data:'):
            return ''
        header, b64data = data_uri.split(',', 1)
        ext = 'png'
        if 'image/jpeg' in header or 'image/jpg' in header:
            ext = 'jpg'
        elif 'image/webp' in header:
            ext = 'webp'
        elif 'image/gif' in header:
            ext = 'gif'
        filename = f"{pid}.{ext}"
        filepath = os.path.join(PATIENT_PHOTOS_DIR, filename)
        raw = base64.b64decode(b64data)
        with open(filepath, 'wb') as f:
            f.write(raw)
        return filename
    except Exception as e:
        print(f"Erreur save_patient_photo: {e}")
        return ''

def delete_patient_photo(filename: str):
    if not filename:
        return
    try:
        filepath = os.path.join(PATIENT_PHOTOS_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Erreur delete_patient_photo: {e}")
PARRAINAGE_FILE = os.path.join(DATA_DIR, 'parrainage.json')
# {stagiaire_key: {parrain_key, parrain_nom, parrain_discord_id, date}}

def load_parrainage():
    return robust_load_json(PARRAINAGE_FILE, {})

def save_parrainage(data):
    atomic_write_json(PARRAINAGE_FILE, data)
WEEK_SNAPSHOT_FILE = os.path.join(DATA_DIR, 'week_snapshot.json')
# InstantanÃ© de la DERNIÃˆRE semaine juste avant le reset /semaine (rÃ©trocompat dashboard) :
# {week_key, stats, evening_reas, services, saved_at}
WEEK_HISTORY_FILE = os.path.join(DATA_DIR, 'week_history.json')
# Historique glissant des 8 derniÃ¨res semaines : {week_key: {stats, evening_reas, services, saved_at, finalized}}
WEEK_HISTORY_MAX = 8

def load_week_snapshot():
    return robust_load_json(WEEK_SNAPSHOT_FILE, {})

def save_week_snapshot(data):
    atomic_write_json(WEEK_SNAPSHOT_FILE, data)

def load_week_history():
    return robust_load_json(WEEK_HISTORY_FILE, {})

def save_week_to_history(week_key: str, snapshot_data: dict, finalized: bool = False):
    """Enregistre/actualise l'entrÃ©e d'une semaine dans l'historique glissant (8 semaines max).
    finalized=True quand c'est /semaine qui l'Ã©crit (donnÃ©es figÃ©es) ;
    finalized=False pour les auto-snapshots pÃ©riodiques de la semaine en cours (donnÃ©es provisoires)."""
    try:
        history = load_week_history()
        entry = dict(snapshot_data)
        entry['finalized'] = finalized
        history[week_key] = entry
        # Garder seulement les WEEK_HISTORY_MAX semaines les plus rÃ©centes
        if len(history) > WEEK_HISTORY_MAX:
            for old_key in sorted(history.keys())[:-WEEK_HISTORY_MAX]:
                del history[old_key]
        atomic_write_json(WEEK_HISTORY_FILE, history)
    except Exception as e:
        print(f"Erreur save_week_to_history: {e}")

def seed_last_week_data_once():
    """PrÃ©-remplit UNE FOIS l'historique de la semaine du 20/07/2026 avec les vraies donnÃ©es
    du bilan hebdomadaire (fournies manuellement), car le systÃ¨me de snapshot n'existait pas
    encore Ã  ce moment-lÃ . Ne fait rien si cette semaine est dÃ©jÃ  prÃ©sente dans l'historique."""
    SEED_WEEK_KEY = "2026-07-20"
    try:
        history = load_week_history()
        if SEED_WEEK_KEY in history:
            return  # dÃ©jÃ  prÃ©sent, ne rien faire (idempotent)

        seed_stats = {
            "sandia-carlo": 511, "toty-roberto": 417, "romain-romarin": 234, "kamelia-zoubida2": 200,
            "taris-mike": 178, "guapan-alvarez": 178, "adam-abdel-karim": 139, "alejandro-lopes": 124,
            "merino-antonio": 120, "emiliano-lopes": 110, "clara-ino": 100, "lyla-wlodarezyk": 82,
            "gustavo-pilguini": 82, "enzo-vitara": 68, "dereck-gaviria": 57, "smith-jason": 47,
            "aylan-trabuc": 43, "fÃ©lix-pÃ©rez": 43, "martine-joe": 26, "adam-donovan": 22,
            "kamÃ©lia-zoubida": 18, "malik-jhonson": 17, "adam-hernandez": 17, "mike-jimmy": 16,
            "carter-darius": 15, "herve-ferrari": 15, "james-board": 12, "fabrice-costa": 10,
            "muchachos-lopes": 10, "kaya-mehmet": 6, "cameron-wayne": 1, "meeko-risto": 1, "amina-koyim": 1,
        }
        seed_services = {
            "toty-roberto": {"total_hours": 38.27, "total_reas": 357, "sessions": 26},
            "sandia-carlo": {"total_hours": 30.13, "total_reas": 414, "sessions": 18},
            "kamelia-zoubida2": {"total_hours": 20.62, "total_reas": 166, "sessions": 21},
            "guapan-alvarez": {"total_hours": 18.43, "total_reas": 166, "sessions": 13},
            "romain-romarin": {"total_hours": 17.92, "total_reas": 173, "sessions": 13},
            "merino-antonio": {"total_hours": 14.83, "total_reas": 107, "sessions": 17},
            "adam-abdel-karim": {"total_hours": 13.77, "total_reas": 138, "sessions": 22},
            "clara-ino": {"total_hours": 13.58, "total_reas": 92, "sessions": 30},
            "taris-mike": {"total_hours": 11.82, "total_reas": 168, "sessions": 8},
            "alejandro-lopes": {"total_hours": 9.72, "total_reas": 124, "sessions": 4},
            "lyla-wlodarezyk": {"total_hours": 9.62, "total_reas": 80, "sessions": 11},
            "dereck-gaviria": {"total_hours": 9.38, "total_reas": 57, "sessions": 6},
            "enzo-vitara": {"total_hours": 9.0, "total_reas": 68, "sessions": 7},
            "emiliano-lopes": {"total_hours": 8.8, "total_reas": 110, "sessions": 5},
            "gustavo-pilguini": {"total_hours": 6.77, "total_reas": 72, "sessions": 6},
            "smith-jason": {"total_hours": 6.62, "total_reas": 46, "sessions": 7},
            "fÃ©lix-pÃ©rez": {"total_hours": 6.57, "total_reas": 43, "sessions": 4},
            "aylan-trabuc": {"total_hours": 3.78, "total_reas": 43, "sessions": 2},
            "adam-donovan": {"total_hours": 3.3, "total_reas": 12, "sessions": 4},
            "malik-jhonson": {"total_hours": 2.63, "total_reas": 17, "sessions": 6},
            "martine-joe": {"total_hours": 2.37, "total_reas": 26, "sessions": 2},
            "carter-darius": {"total_hours": 2.22, "total_reas": 15, "sessions": 5},
            "kaya-mehmet": {"total_hours": 1.73, "total_reas": 6, "sessions": 6},
            "james-board": {"total_hours": 1.63, "total_reas": 12, "sessions": 1},
            "mike-jimmy": {"total_hours": 1.42, "total_reas": 16, "sessions": 1},
            "adam-hernandez": {"total_hours": 1.38, "total_reas": 17, "sessions": 2},
            "muchachos-lopes": {"total_hours": 1.22, "total_reas": 10, "sessions": 1},
            "rico-alvarez": {"total_hours": 1.0, "total_reas": 0, "sessions": 2},
            "amina-koyim": {"total_hours": 0.55, "total_reas": 1, "sessions": 1},
            "herve-ferrari": {"total_hours": 0.52, "total_reas": 0, "sessions": 2},
            "kamÃ©lia-zoubida": {"total_hours": 0.45, "total_reas": 14, "sessions": 1},
        }
        seed_snapshot = {
            "week_key": SEED_WEEK_KEY,
            "stats": seed_stats,
            "evening_reas": {},  # non disponible pour cette semaine (pas encore trackÃ©e Ã  l'Ã©poque)
            "services": seed_services,
            "saved_at": now_paris().isoformat(),
        }
        save_week_to_history(SEED_WEEK_KEY, seed_snapshot, finalized=True)
        # Sert aussi de "week_snapshot" (derniÃ¨re semaine) tant qu'aucune vraie /semaine n'a encore tournÃ©
        if not load_week_snapshot().get('week_key'):
            save_week_snapshot(seed_snapshot)
        print(f"âœ… Semaine du {SEED_WEEK_KEY} prÃ©-remplie dans l'historique ({len(seed_stats)} employÃ©s, {sum(seed_stats.values())} rÃ©as)")
    except Exception as e:
        print(f"Erreur seed_last_week_data_once: {e}")
# {patient_id: {nom, prenom, photo (data URI base64), created, dossiers: [{date, symptome, description, examens, conseils, par}]}}

def load_patients():
    return robust_load_json(PATIENTS_FILE, {})

def save_patients(data):
    atomic_write_json(PATIENTS_FILE, data)
# {employee_key: [{from_grade, to_grade, date, par}]}

def load_promo_history():
    return robust_load_json(PROMO_HISTORY_FILE, {})

def save_promo_history(data):
    atomic_write_json(PROMO_HISTORY_FILE, data)

def promo_track(employee_key: str, from_grade: str, to_grade: str, par: str = 'Direction'):
    """Enregistre une promotion dans l'historique."""
    try:
        data = load_promo_history()
        if employee_key not in data:
            data[employee_key] = []
        data[employee_key].append({
            'from_grade': from_grade,
            'to_grade': to_grade,
            'date': now_paris().isoformat(),
            'par': par,
        })
        save_promo_history(data)
    except Exception as e:
        print(f"Erreur promo_track: {e}")
# {discord_id: {nom, date_depot, statut: pending|accepted|refused, raison_refus, discord_tag}}

def load_cv_tracking():
    return robust_load_json(CV_TRACKING_FILE, {})

def save_cv_tracking(data):
    atomic_write_json(CV_TRACKING_FILE, data)

def cv_track_add(user: discord.User, statut: str = 'pending', photos_b64: list = None, cv_text: str = None):
    """Ajoute ou met Ã  jour un CV dans le tracking (avec photos carte identitÃ©/permis et texte complet)."""
    try:
        data = load_cv_tracking()
        uid = str(user.id)
        data[uid] = {
            'nom': user.display_name,
            'discord_tag': str(user),
            'date_depot': now_paris().isoformat(),
            'statut': statut,
            'raison_refus': None,
            'photos': photos_b64 or [],
            'cv_text': cv_text or '',
        }
        save_cv_tracking(data)
    except Exception as e:
        print(f"Erreur cv_track_add: {e}")

def cv_track_update(user_id: str, statut: str, raison: str = None):
    """Met Ã  jour le statut d'un CV existant."""
    try:
        data = load_cv_tracking()
        if user_id in data:
            data[user_id]['statut'] = statut
            data[user_id]['date_action'] = now_paris().isoformat()
            if raison is not None:
                data[user_id]['raison_refus'] = raison
        save_cv_tracking(data)
    except Exception as e:
        print(f"Erreur cv_track_update: {e}")

# Services actifs en mÃ©moire: {user_id: {"start": datetime_iso, "last_rea": datetime_iso, "employee_key": str}}
active_services = {}
service_status_message_id = None  # ID du message de statut en temps rÃ©el

def load_service_message_id():
    """Charge l'ID du message PDS depuis le fichier"""
    data = robust_load_json(SERVICE_MSG_FILE, {})
    return data.get("message_id") if data else None

def save_service_message_id(msg_id):
    """Sauvegarde l'ID du message PDS dans un fichier"""
    atomic_write_json(SERVICE_MSG_FILE, {"message_id": msg_id})

# Configuration Taxi
TAXI_CHANNEL_ID = 1457304629456011264
TAXI_ROLE_ID = 1163206112355561472
ROLE_DIRECTION_EMS_ID = 838120186585940010
ROLE_DIRECTION_TAXI_ID = 1311787019546136596

# Configuration BurgerShot
BURGERSHOT_CHANNEL_ID = 1462099226166165588
BURGERSHOT_ROLE_ID = 1462097148995965041
BURGERSHOT_STATS_FILE = os.path.join(DATA_DIR, 'burgershot_stats.json')

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
ROLE_BASE_ID = 838102445095256066  # RÃ´le de base Ã  conserver
RESET_CHANNEL_ID = 1450938023033176247

# Configuration Leaderboard
LEADERBOARD_CHANNEL_ID = 1018904202971459644
LEADERBOARD_ROLE_ID = 838102445095256068

# Configuration Avis
AVIS_CHANNEL_ID = 1478910608228487255
CITOYEN_ROLE_ID = 838102445095256066

# Configuration Dispo
DISPO_REQUEST_CHANNEL_ID = 1478916243858915591  # Canal pour les demandes initiales
DISPO_CHANNEL_ID = 1478912686069780602  # Canal pour les dÃ©cisions de recrutement
DISPO_CONFIRMATION_ROLE_ID = 896103247096471613
DIRECTION_ROLE_ID = 838120186585940010  # RÃ´le direction pour validation dispo et recrutement
ROLE_PENDING_ID = 896103247096471613

# Liste unifiÃ©e des rÃ´les EMS Ã  retirer lors d'un licenciement
EMS_ROLE_IDS_TO_REMOVE = [
    895047492784238652,  # EMT
    838102445095256069,  # STG
    1088116715998687273, # ADS
    894311352225656862,  # INF
    840288242547818507,  # MED
    838102445095256071,  # CDS
    1528560704511148092, # PSY
    1528561040663777310, # CAD
    1088570974603055195, # DIR
    838102445095256068,  # Autre rÃ´le EMS 1
    838102445095256070,  # Autre rÃ´le EMS 2
]
ROLE_EMT_1 = 838102445095256070
ROLE_EMT_2 = 838102445095256068
ROLE_EMT_3 = 895047492784238652
ROLE_CITOYEN = 838102445095256068

# Configuration Giveaway
GIVEAWAY_PING_ROLE_ID = 838102445095256068  # RÃ´le Ã  ping pour les giveaways
GIVEAWAY_FILE = 'giveaways.json'

# --- FONCTIONS UTILITAIRES JSON ---
def atomic_write_json(path: str, data: dict, make_backup: bool = True, max_retries: int = 3):
    tmp_path = f"{path}.tmp"
    last_exc = Exception("atomic_write_json: aucune tentative effectuÃ©e")
    for attempt in range(1, max_retries + 1):
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # Ecrire/mettre Ã  jour une sauvegarde simple
            if make_backup:
                try:
                    with open(f"{path}.bak", 'w', encoding='utf-8') as bf:
                        json.dump(data, bf, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            os.replace(tmp_path, path)
            return  # SuccÃ¨s
        except Exception as e:
            last_exc = e
            # Nettoyage tmp si besoin
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            if attempt < max_retries:
                time.sleep(0.5 * attempt)
    raise last_exc

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

# Fonction pour charger les catÃ©gories
def load_categories():
    default = {
        "CATEGORY_EMT_ID": 1515101532746678332,
        "CATEGORY_STG_ID": 1515101531186397335,  # Stagiaire
        "CATEGORY_ADS_ID": 0,
        "CATEGORY_INF_ID": 0,
        "CATEGORY_PSY_ID": 1528562582804365312,  # Psychologue âœ“
        "CATEGORY_MED_ID": 0,
        "CATEGORY_CDS_ID": 0,               # Chef de Service
        "CATEGORY_CAD_ID": 1528562915458814053,  # Chef Adjoint [CAD]
        "CATEGORY_DIR_ID": 0
    }
    return robust_load_json(CATEGORIES_FILE, default)

def save_categories(cats):
    atomic_write_json(CATEGORIES_FILE, cats)

# Charger les catÃ©gories au dÃ©marrage
categories = load_categories()
CATEGORY_EMT_ID = categories.get("CATEGORY_EMT_ID", 1515101532746678332)
CATEGORY_STG_ID = categories.get("CATEGORY_STG_ID", 1515101531186397335)  # Stagiaire
CATEGORY_ADS_ID = categories.get("CATEGORY_ADS_ID", 0)
CATEGORY_INF_ID = categories.get("CATEGORY_INF_ID", 0)
CATEGORY_PSY_ID = categories.get("CATEGORY_PSY_ID", 1528562582804365312)  # Psychologue
CATEGORY_MED_ID = categories.get("CATEGORY_MED_ID", 0)
CATEGORY_CDS_ID = categories.get("CATEGORY_CDS_ID", 0)  # Chef de Service
CATEGORY_CAD_ID = categories.get("CATEGORY_CAD_ID", 1528562915458814053)  # Chef Adjoint
CATEGORY_DIR_ID = categories.get("CATEGORY_DIR_ID", 0)

# --- FICHIER BLACKLIST CV ---
BLACKLIST_CV_FILE = os.path.join(DATA_DIR, 'blacklist_cv.json')

def load_blacklist_cv():
    return robust_load_json(BLACKLIST_CV_FILE, {})

def save_blacklist_cv(data):
    atomic_write_json(BLACKLIST_CV_FILE, data)

def is_blacklisted_cv(user_id: int) -> dict | None:
    """Retourne les infos de blacklist si l'user est blacklistÃ© et le dÃ©lai pas encore passÃ©, sinon None."""
    bl = load_blacklist_cv()
    uid = str(user_id)
    if uid not in bl:
        return None
    entry = bl[uid]
    blacklisted_at = datetime.fromisoformat(entry["date"])
    if datetime.utcnow() - blacklisted_at < timedelta(weeks=1):
        return entry
    return None  # dÃ©lai passÃ© â†’ plus blacklistÃ©

# Cooldown pour rÃ©actions
processed_reactions = set()

# Compteur de rÃ©as nocturnes (21h-23h) en mÃ©moire: {"employee_key_YYYY-MM-DD": count}
EVENING_REAS_FILE = os.path.join(DATA_DIR, 'evening_reas.json')
evening_reas = robust_load_json(EVENING_REAS_FILE, {})  # persistÃ© sur disque, rÃ©siste aux redÃ©marrages

# Suivi des retraits du coffre sociÃ©tÃ©: {"username_YYYY-MM-DD": {"count": N, "items": [...]}}
coffre_tracking = {}

# --- COULEURS EMS ---
EMS_RED = discord.Color.from_rgb(220, 20, 60)
EMS_DARK_RED = discord.Color.from_rgb(178, 34, 52)

# --- MATRICULES ---
# Salons vocaux de service â€” IDs des divisions
SERVICE_VOICE_CHANNELS = {
    "Lincoln 01": 1524437901176213606,
    "Lincoln 02": 1524164049150148758,
    "Lincoln 03": 1526205015021064212,
    "Adam 01":    1524164183371808979,
    "Adam 02":    1524164284945272923,
    "Adam 03":    1524164340704608457,
    "Tango 01":   1524164435583832074,
    "Tango 02":   1524164468899315813,
    "Tango 03":   1524164510502490173,
    "Xray 01":    1524164629327122452,
    "Xray 02":    1524164668971679764,
    "Xray 03":    1524164701829861376,
}
SERVICE_VOICE_IDS = set(SERVICE_VOICE_CHANNELS.values())
WAITING_VOICE_ID = 896196296283660328  # Salon vocal de repos aprÃ¨s FDS
matricule_board_message_id = None  # ID du message embed dans le salon matricules
direction_matricules = {}  # {grade: {matricule_str: nom}} ex: {"DIR": {"01": "Jean Dupont"}}

# --- AVERTISSEMENTS ---
AVERT_CHANNEL_ID = 1524362855816761405
MATRICULE_CHANNEL_ID = 1524156209891119274
AVERT_ROLE_PING_ID = 699589324705890334
AVERT_FILE = AVERT_FILE_PATH
avert_board_message_id = None

def load_avertissements():
    return robust_load_json(AVERT_FILE, {})

def save_avertissements(data: dict):
    atomic_write_json(AVERT_FILE, data)

def get_avert_emoji(count: int) -> str:
    if count == 0:
        return "ðŸŸ¢"
    elif count == 1:
        return "ðŸŸ¡"
    elif count == 2:
        return "ðŸŸ "
    else:
        return "ðŸ”´"

_last_matricule_update = 0.0  # timestamp de la derniÃ¨re mise Ã  jour (debounce)

async def update_matricule_board(guild: discord.Guild):
    """Met Ã  jour (ou crÃ©e) l'embed des matricules dans le salon dÃ©diÃ©."""
    global matricule_board_message_id, _last_matricule_update
    # Debounce : ne pas spammer les 10 appels simultanÃ©s (ex: Ã  la fin de service)
    _now_ts = time.time()
    if _now_ts - _last_matricule_update < 30:
        return
    _last_matricule_update = _now_ts

    channel = guild.get_channel(MATRICULE_CHANNEL_ID)
    if not channel:
        return


    ROLE_EMS_ID = 838102445095256068
    role_ems = guild.get_role(ROLE_EMS_ID)

    grade_order  = ["DIR", "CAD", "CDS", "MED", "PSY", "INF", "ADS", "STG", "EMT"]
    grade_labels = {
        "DIR": "ðŸ‘” Directeur MÃ©dical",
        "CAD": "ðŸ¥ Chef Adjoint",
        "CDS": "ðŸ¥ Chef de Service",
        "MED": "âš•ï¸ MÃ©decin",
        "PSY": "ðŸ§  Psychologue",
        "INF": "ðŸ’‰ Infirmier",
        "ADS": "ðŸ©º Aide-Soignant",
        "STG": "ðŸ“‹ Stagiaire",
        "EMT": "ðŸš‘ EMT",
    }

    # {grade: {mat: nom}} et {grade: {mat: [nom1, nom2]}} pour doublons
    all_mats   = {g: {} for g in grade_order}
    doublons   = {g: {} for g in grade_order}

    members_to_scan = role_ems.members if role_ems else []
    for m in members_to_scan:
        if m.bot:
            continue
        match = _re.search(r'\[(\w+)\]\s+(\d{2})\s+(.+)', m.display_name)
        if match:
            grade = match.group(1)
            mat   = match.group(2)
            nom   = match.group(3).strip()
            if grade not in all_mats:
                all_mats[grade]  = {}
                doublons[grade]  = {}
            if mat in all_mats[grade]:
                if mat not in doublons[grade]:
                    doublons[grade][mat] = [all_mats[grade][mat]]
                doublons[grade][mat].append(nom)
            else:
                all_mats[grade][mat] = nom

    # Compter
    total_taken   = sum(len(v) for v in all_mats.values())
    total_doublons = sum(len(v) for v in doublons.values())
    alerte = f"\nâš ï¸ **{total_doublons} CONFLIT(S) DÃ‰TECTÃ‰(S) â€” Ã€ CORRIGER !**" if total_doublons else ""

    embed = discord.Embed(
        title="ðŸªª TABLEAU DES MATRICULES EMS",
        description=(
            f"**{total_taken}** matricule(s) attribuÃ©e(s)\n"
            f"ðŸ”´ = AttribuÃ©e Â· ðŸŸ¢ = Disponible Â· âš ï¸ = Conflit{alerte}\n\n"
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”"
        ),
        color=discord.Color.red() if total_doublons else EMS_RED
    )

    # Alerte doublons en haut
    if total_doublons:
        conflit_lines = []
        for grade, mats in doublons.items():
            for mat, noms_list in mats.items():
                all_noms = noms_list + ([all_mats[grade][mat]] if mat in all_mats[grade] else [])
                conflit_lines.append(f"âš ï¸ **[{grade}] {mat}** â†’ {', '.join(all_noms)}")
        embed.add_field(name="ðŸš¨ CONFLITS", value="\n".join(conflit_lines), inline=False)

    # Liste plate 01-99 : rouge si pris, vert si dispo
    all_taken = {}  # {mat: (grade, member_id)}
    all_dbl = {}    # {mat: [(grade, nom), ...]}
    for grade, mats in all_mats.items():
        for mat, nom in mats.items():
            if mat in all_taken:
                if mat not in all_dbl:
                    all_dbl[mat] = [all_taken[mat]]
                all_dbl[mat].append((grade, nom))
            else:
                all_taken[mat] = (grade, nom)
    for grade, dbl in doublons.items():
        for mat, noms in dbl.items():
            if mat not in all_dbl:
                all_dbl[mat] = []
            all_dbl[mat].extend([(grade, n) for n in noms])

    # Construire un mapping mat -> member pour les mentions
    mat_to_member = {}
    members_to_scan2 = role_ems.members if role_ems else []
    for m in members_to_scan2:
        if m.bot:
            continue
        match2 = _re.search(r'\[(\w+)\]\s+(\d{2})\s+(.+)', m.display_name)
        if match2:
            mat2 = match2.group(2)
            if mat2 not in mat_to_member:
                mat_to_member[mat2] = m.id

    lines = []
    for i in range(1, 100):
        mat = str(i).zfill(2)
        if mat in all_dbl:
            parts = ", ".join([f"[{g}] {n}" for g, n in all_dbl[mat]])
            lines.append(f"âš ï¸ **{mat}** â€” *CONFLIT : {parts}*")
        elif mat in all_taken:
            grade, nom = all_taken[mat]
            mid = mat_to_member.get(mat)
            mention = f"<@{mid}>" if mid else nom
            lines.append(f"ðŸ”´ **{mat}** â€” [{grade}] {mention}")
        else:
            lines.append(f"ðŸŸ¢ **{mat}** â€” *Disponible*")

    def chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    blocks = list(chunks(lines, 20))
    for idx, block in enumerate(blocks):
        embed.add_field(
            name="ðŸªª Matricules EMS" if idx == 0 else "â€‹",
            value="\n".join(block),
            inline=False
        )

    # Section direction manuelle
    if direction_matricules:
        dir_lines = []
        for grade in grade_order:
            if grade in direction_matricules and direction_matricules[grade]:
                dir_lines.append(f"**{grade_labels.get(grade, grade)}**")
                for mat, nom in sorted(direction_matricules[grade].items()):
                    dir_lines.append(f"  ðŸ”´ **{mat}** â€” {nom}")
        if dir_lines:
            embed.add_field(
                name="â­ Matricules Direction (manuel)",
                value="\n".join(dir_lines),
                inline=False
            )

    embed.set_footer(text="ðŸš‘ EMS System | Mis Ã  jour automatiquement")

    content = None

    # Envoyer ou Ã©diter le message
    try:
        if matricule_board_message_id:
            try:
                msg = await channel.fetch_message(matricule_board_message_id)
                await msg.edit(content=content, embed=embed)
                return
            except discord.NotFound:
                matricule_board_message_id = None

        async for old_msg in channel.history(limit=10):
            if old_msg.author == guild.me:
                try:
                    await old_msg.delete()
                except:
                    pass

        new_msg = await channel.send(content=content, embed=embed)
        matricule_board_message_id = new_msg.id
    except Exception as e:
        print(f"Erreur update_matricule_board: {e}")




# --- DISPATCH ---
DISPATCH_CHANNEL_ID = 1524513403048038512
dispatch_message_id = None
dispatch_active = False
dispatch_state = {}  # {user_id: div_name} â€” assignation courante de chaque employÃ©
dispatch_lock = asyncio.Lock()  # Verrou pour Ã©viter les race conditions
dispatch_history = robust_load_json(DISPATCH_HISTORY_FILE, [])  # [{date, display_name, division}]

DIVISIONS = [
    {"name": "Lincoln 01", "capacity": 1},
    {"name": "Lincoln 02", "capacity": 1},
    {"name": "Lincoln 03", "capacity": 1},
    {"name": "Adam 01",    "capacity": 2},
    {"name": "Adam 02",    "capacity": 2},
    {"name": "Adam 03",    "capacity": 2},
    {"name": "Tango 01",   "capacity": 3},
    {"name": "Tango 02",   "capacity": 3},
    {"name": "Tango 03",   "capacity": 3},
    {"name": "Xray 01",    "capacity": 4},
    {"name": "Xray 02",    "capacity": 4},
    {"name": "Xray 03",    "capacity": 4},
]

DIV_EMOJI = {
    "Lincoln": "ðŸš—",
    "Adam":    "ðŸš™",
    "Tango":   "ðŸš‘",
    "Xray":    "ðŸš’",
}



class TangoXrayRequestView(discord.ui.View):
    """Boutons Accepter/Refuser envoyÃ©s en DM Ã  la direction."""
    def __init__(self, requester_id: int, requester_name: str, guild_id: int, target_div: str):
        super().__init__(timeout=300)
        self.requester_id = requester_id
        self.requester_name = requester_name
        self.guild_id = guild_id
        self.target_div = target_div
        self.handled = False

    async def _disable_all(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="âœ… Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.handled:
            await interaction.response.send_message("Cette demande a dÃ©jÃ  Ã©tÃ© traitÃ©e.", ephemeral=True)
            return
        self.handled = True
        await interaction.response.defer()
        await self._disable_all(interaction)

        guild = bot.get_guild(self.guild_id)
        if not guild:
            return

        async with dispatch_lock:
            # Placer l'employÃ© dans la division
            dispatch_state[str(self.requester_id)] = self.target_div
            await _run_dispatch_locked(guild)

        # Notifier l'employÃ©
        member = guild.get_member(self.requester_id)
        if member:
            try:
                div_type = self.target_div.split()[0]
                emoji = {"Tango": "ðŸš‘", "Xray": "ðŸš’"}.get(div_type, "ðŸš—")
                await member.send(
                    f"âœ… Votre demande a Ã©tÃ© **acceptÃ©e** par la direction.\n"
                    f"Vous Ãªtes maintenant assignÃ© Ã  **{emoji} {self.target_div}** !"
                )
            except:
                pass

        await interaction.followup.send(
            f"âœ… **{self.requester_name}** a Ã©tÃ© affectÃ© Ã  **{self.target_div}**.",
            ephemeral=True
        )

    @discord.ui.button(label="âŒ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.handled:
            await interaction.response.send_message("Cette demande a dÃ©jÃ  Ã©tÃ© traitÃ©e.", ephemeral=True)
            return
        self.handled = True
        await interaction.response.defer()
        await self._disable_all(interaction)

        guild = bot.get_guild(self.guild_id)
        member = guild.get_member(self.requester_id) if guild else None
        if member:
            try:
                await member.send(
                    f"âŒ Votre demande de rejoindre **{self.target_div}** a Ã©tÃ© **refusÃ©e** par la direction."
                )
            except:
                pass

        await interaction.followup.send(
            f"âŒ Demande de **{self.requester_name}** refusÃ©e.",
            ephemeral=True
        )


class DispatchDivisionView(discord.ui.View):
    """Vue avec boutons de sÃ©lection de division pour le dispatch."""
    def __init__(self):
        super().__init__(timeout=None)

    async def _join_division(self, interaction: discord.Interaction, div_name: str, capacity: int):
        async with dispatch_lock:
            await self._join_division_locked(interaction, div_name, capacity)

    async def _join_division_locked(self, interaction: discord.Interaction, div_name: str, capacity: int):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user_id = str(interaction.user.id)

        # VÃ©rifier que l'employÃ© est en service
        if user_id not in active_services:
            await interaction.followup.send("âŒ Vous devez Ãªtre en service pour rejoindre une division.", ephemeral=True)
            return

        # VÃ©rifier si dÃ©jÃ  dans cette division
        if dispatch_state.get(user_id) == div_name:
            await interaction.followup.send(f"âœ… Vous Ãªtes dÃ©jÃ  dans **{div_name}**.", ephemeral=True)
            return

        # Compter les membres actuels dans la division
        current_members = [uid for uid, div in dispatch_state.items() if div == div_name]

        if len(current_members) >= capacity:
            await interaction.followup.send(
                f"âŒ **{div_name}** est dÃ©jÃ  pleine ({capacity}/{capacity} pers.).",
                ephemeral=True
            )
            return

        # Retirer de l'ancienne division si applicable
        old_div = dispatch_state.get(user_id)
        dispatch_state[user_id] = div_name

        await interaction.followup.send(
            f"âœ… Vous avez rejoint **{div_name}** !",
            ephemeral=True
        )

        # Mise Ã  jour embed dispatch
        await _run_dispatch_locked(guild)

        # Si la division est maintenant multi-personnes (Adam/Tango), notifier dans les channels
        new_members = [uid for uid, div in dispatch_state.items() if div == div_name]
        div_type = div_name.split()[0]

        if len(new_members) >= 2 and div_type in ["Adam", "Tango", "Xray"]:
            # Trouver les channels des membres de la division
            for member_uid in new_members:
                member = guild.get_member(int(member_uid))
                if not member:
                    continue
                clean = get_clean_name(member)
                clean_norm = normalize_employee_key(clean)
                for ch in guild.text_channels:
                    if ch.name and len(ch.name) > 1 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
                        if get_channel_employee_key(ch) == clean_norm:
                            coequipiers = [f"<@{uid}>" for uid in new_members if uid != member_uid]
                            co_str = " \u00b7 ".join(coequipiers)
                            await ch.send(
                                f"\U0001f91d Vous \u00eates en **{div_name}** avec {co_str}.\n"
                                f"\U0001f4ca Chaque r\u00e9a sera **compt\u00e9e pour toute la division**."
                            )
                            break

    @discord.ui.button(label="ðŸš— Lincoln 01", style=discord.ButtonStyle.secondary, custom_id="div_lincoln_01", row=0)
    async def lincoln_01(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_division(interaction, "Lincoln 01", 1)

    @discord.ui.button(label="ðŸš— Lincoln 02", style=discord.ButtonStyle.secondary, custom_id="div_lincoln_02", row=0)
    async def lincoln_02(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_division(interaction, "Lincoln 02", 1)

    @discord.ui.button(label="ðŸš— Lincoln 03", style=discord.ButtonStyle.secondary, custom_id="div_lincoln_03", row=0)
    async def lincoln_03(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_division(interaction, "Lincoln 03", 1)

    @discord.ui.button(label="ðŸš™ Adam 01", style=discord.ButtonStyle.primary, custom_id="div_adam_01", row=1)
    async def adam_01(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_division(interaction, "Adam 01", 2)

    @discord.ui.button(label="ðŸš™ Adam 02", style=discord.ButtonStyle.primary, custom_id="div_adam_02", row=1)
    async def adam_02(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_division(interaction, "Adam 02", 2)

    @discord.ui.button(label="ðŸš™ Adam 03", style=discord.ButtonStyle.primary, custom_id="div_adam_03", row=1)
    async def adam_03(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_division(interaction, "Adam 03", 2)

    @discord.ui.button(label="ðŸš‘ Tango / ðŸš’ Xray â†’ Demander direction", style=discord.ButtonStyle.danger, custom_id="div_tango_xray", row=2)
    async def tango_xray(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user_id = str(interaction.user.id)

        if user_id not in active_services:
            await interaction.followup.send("âŒ Vous devez Ãªtre en service.", ephemeral=True)
            return

        # DM direct Ã  la direction (user ID fixe)
        DIR_USER_ID = 699589324705890334
        dir_member = guild.get_member(DIR_USER_ID)
        if not dir_member:
            await interaction.followup.send("âŒ Impossible de joindre la direction.", ephemeral=True)
            return

        # Choisir la division Tango/Xray disponible
        groups = {}
        for uid, div in dispatch_state.items():
            groups.setdefault(div, []).append(uid)

        target_div = None
        for div_name, cap in [("Tango 01", 3), ("Tango 02", 3), ("Tango 03", 3), ("Xray 01", 4), ("Xray 02", 4), ("Xray 03", 4)]:
            if div_name not in groups or len(groups[div_name]) < cap:
                target_div = div_name
                break

        if not target_div:
            await interaction.followup.send("âŒ Toutes les divisions Tango/Xray sont pleines.", ephemeral=True)
            return

        # Envoyer dans le channel direction avec ping rÃ´le
        TANGO_REQUEST_CHANNEL_ID = 1485278000986587333
        TANGO_PING_ROLE_ID = 838120186585940010

        view = TangoXrayRequestView(
            requester_id=interaction.user.id,
            requester_name=interaction.user.display_name,
            guild_id=guild.id,
            target_div=target_div
        )

        request_embed = discord.Embed(
            title="ðŸ“‹ Demande d'affectation Tango/Xray",
            description=(
                f"**{interaction.user.display_name}** ({interaction.user.mention}) demande Ã  rejoindre **{target_div}**.\n\n"
                f"Il est actuellement en service.\n\n"
                f"Acceptez ou refusez cette demande :"
            ),
            color=EMS_RED
        )
        request_embed.set_footer(text="ðŸš‘ EMS System | Dispatch")

        tango_channel = guild.get_channel(TANGO_REQUEST_CHANNEL_ID)
        sent = False
        if tango_channel:
            try:
                direction_role = guild.get_role(TANGO_PING_ROLE_ID)
                ping_content = direction_role.mention if direction_role else ""
                await tango_channel.send(content=ping_content, embed=request_embed, view=view)
                sent = True
            except Exception as e:
                print(f"Erreur envoi tango channel: {e}")

        if sent:
            await interaction.followup.send(
                f"âœ… Demande envoyÃ©e Ã  la direction pour rejoindre **{target_div}**. En attente de validation.",
                ephemeral=True
            )
        else:
            await interaction.followup.send("âŒ Impossible de joindre la direction (channel introuvable).", ephemeral=True)



async def run_dispatch(guild: discord.Guild):
    """Met Ã  jour le dispatch en ajustant intelligemment les assignations existantes."""
    async with dispatch_lock:
        await _run_dispatch_locked(guild)

async def _run_dispatch_locked(guild: discord.Guild):
    global dispatch_message_id, dispatch_active, dispatch_state

    channel = guild.get_channel(DISPATCH_CHANNEL_ID)
    if not channel:
        return

    import random as _rnd2

    def _get_hour():
        try:
                return datetime.now(ZoneInfo("Europe/Paris")).hour
        except:
            from datetime import timezone, timedelta
            return datetime.now(timezone(timedelta(hours=2))).hour

    hour = _get_hour()
    current_ids = set(active_services.keys())
    count = len(current_ids)

    # Retirer les gens qui ont fait FDS
    for uid in list(dispatch_state.keys()):
        if uid not in current_ids:
            del dispatch_state[uid]

    # Construire l'ordre des divisions selon heure
    def make_divs():
        lincoln = [("Lincoln 01", 1), ("Lincoln 02", 1), ("Lincoln 03", 1)]
        adam    = [("Adam 01", 2), ("Adam 02", 2), ("Adam 03", 2)]
        tango   = [("Tango 01", 3), ("Tango 02", 3), ("Tango 03", 3)]
        xray    = [("Xray 01", 4), ("Xray 02", 4), ("Xray 03", 4)]
        for lst in [lincoln, adam, tango, xray]:
            _rnd2.shuffle(lst)
        if 6 <= hour < 12:
            return adam + tango + lincoln + xray
        elif 12 <= hour < 19:
            return adam + lincoln + tango + xray
        elif hour >= 19 or hour < 2:
            return lincoln + adam + tango + xray
        else:  # 2h-6h nuit
            return adam + lincoln + tango + xray

    all_divisions = make_divs()
    soir_ou_nuit = hour >= 19 or hour < 6

    def get_groups():
        g = {}
        for uid, div in dispatch_state.items():
            g.setdefault(div, []).append(uid)
        return g

    # Ne pas assigner automatiquement â€” l'employÃ© choisit via les boutons
    # Juste retirer ceux qui ont fait FDS (dÃ©jÃ  fait au-dessus)

    # Construire l'embed
    groups = get_groups()
    div_emojis = {"Lincoln": "ðŸš—", "Adam": "ðŸš™", "Tango": "ðŸš‘", "Xray": "ðŸš’"}

    if count == 0:
        embed = discord.Embed(
            title="ðŸš¨ DISPATCH EMS",
            description="Aucun employÃ© en service actuellement.\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”",
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text="ðŸš‘ EMS System | En attente de prise de service...")
    else:
        embed = discord.Embed(
            title="ðŸš¨ DISPATCH EMS",
            description=f"**{count} employÃ©(s) en service**\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”",
            color=EMS_RED
        )
        first_lincoln = next((d for d, _ in all_divisions if d.startswith("Lincoln") and d in groups), None)
        first_adam    = next((d for d, _ in all_divisions if d.startswith("Adam")    and d in groups), None)

        for div_name, cap in all_divisions:
            if div_name not in groups:
                continue
            group = groups[div_name]
            emoji = div_emojis.get(div_name.split()[0], "ðŸš—")
            mentions = " Â· ".join([f"<@{uid}>" for uid in group])
            extras = []
            if div_name == first_lincoln:
                extras.append("â˜Žï¸ PrioritÃ© appels tÃ©lÃ©phone")
            if div_name == first_adam:
                extras.append("ðŸ† PrioritÃ© KOTH")
            val = mentions + ("\n> " + " Â· ".join(extras) if extras else "")
            embed.add_field(name=f"{emoji} {div_name} ({len(group)}/{cap})", value=val, inline=False)

        embed.set_footer(text="ðŸš‘ EMS System | Mis Ã  jour automatiquement Â· /redispatch pour relancer")

    try:
        if dispatch_message_id:
            try:
                msg = await channel.fetch_message(dispatch_message_id)
                await msg.edit(content=None, embed=embed, view=DispatchDivisionView() if count > 0 else None)
                dispatch_active = count > 0
                return
            except discord.NotFound:
                dispatch_message_id = None
            except discord.Forbidden:
                print("Erreur dispatch: permissions insuffisantes pour Ã©diter le message")
                return

        async for old_msg in channel.history(limit=10):
            if old_msg.author == guild.me:
                try:
                    await old_msg.delete()
                except:
                    pass

        try:
            new_msg = await channel.send(content=None, embed=embed, view=DispatchDivisionView() if count > 0 else None)
            dispatch_message_id = new_msg.id
            dispatch_active = count > 0
        except discord.Forbidden:
            print("Erreur dispatch: pas la permission d'envoyer dans le salon dispatch")
        except Exception as e:
            print(f"Erreur dispatch envoi: {e}")
    except Exception as e:
        print(f"Erreur dispatch gÃ©nÃ©rale: {e}")

async def update_avert_board(guild: discord.Guild):
    """Met Ã  jour (ou crÃ©e) l'embed des avertissements dans le salon dÃ©diÃ©."""
    global avert_board_message_id

    channel = guild.get_channel(AVERT_CHANNEL_ID)
    if not channel:
        return

    data = load_avertissements()
    now = datetime.now(timezone.utc)

    # Purge des avertissements > 30 jours
    changed = False
    for user_id, averts in list(data.items()):
        fresh = []
        for av in averts:
            try:
                date = datetime.fromisoformat(av["date"])
                if (now - date).days < 30:
                    fresh.append(av)
            except:
                pass
        if len(fresh) != len(averts):
            changed = True
        data[user_id] = fresh
    if changed:
        save_avertissements(data)

    # RÃ©cupÃ©rer les membres avec le rÃ´le EMS
    role_ems = guild.get_role(838102445095256068)
    members_ems = role_ems.members if role_ems else []

    lines = []
    has_alerts = False
    for m in sorted(members_ems, key=lambda x: x.display_name):
        if m.bot:
            continue
        user_averts = data.get(str(m.id), [])
        count = len(user_averts)
        emoji = get_avert_emoji(count)
        clean = get_clean_name(m)
        if count == 0:
            lines.append(f"{emoji} **{clean}** â€” Aucun avertissement")
        else:
            raisons = " Â· ".join([av.get("raison", "?") for av in user_averts])
            lines.append(f"{emoji} **{clean}** â€” {count} avert. : {raisons}")
            if count >= 3:
                has_alerts = True

    if not lines:
        lines = ["*Aucun employÃ© trouvÃ©.*"]

    embed = discord.Embed(
        title="âš ï¸ TABLEAU DES AVERTISSEMENTS EMS",
        description=(
            "ðŸŸ¢ Aucun Â· ðŸŸ¡ 1 Â· ðŸŸ  2 Â· ðŸ”´ 3+\n"
            "Les avertissements se rÃ©initialisent automatiquement aprÃ¨s **30 jours**.\n"
            "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”"
        ),
        color=discord.Color.red() if has_alerts else EMS_RED
    )

    # DÃ©couper si trop long
    chunk_size = 20
    chunks_list = [lines[i:i+chunk_size] for i in range(0, len(lines), chunk_size)]
    for idx, chunk in enumerate(chunks_list):
        embed.add_field(
            name="ðŸ‘¥ EmployÃ©s" if idx == 0 else "â€‹",
            value="\n".join(chunk),
            inline=False
        )

    embed.set_footer(text=f"ðŸš‘ EMS System | Mis Ã  jour automatiquement Â· {now.strftime('%d/%m/%Y %H:%M')} UTC")

    try:
        if avert_board_message_id:
            try:
                msg = await channel.fetch_message(avert_board_message_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                avert_board_message_id = None

        async for old_msg in channel.history(limit=10):
            if old_msg.author == guild.me:
                try:
                    await old_msg.delete()
                except:
                    pass

        new_msg = await channel.send(embed=embed)
        avert_board_message_id = new_msg.id
    except Exception as e:
        print(f"Erreur update_avert_board: {e}")


# --- SETUP BOT ---
class EMSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            # Heartbeat plus tolÃ©rant pour rÃ©duire les dÃ©connexions (logs montrent ~3/h)
            heartbeat_timeout=150.0,
        )

    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(CVButton())
        # self.add_view(FormulaireCVButton())  # DÃ©sactivÃ© - on utilise l'ancien systÃ¨me
        self.add_view(RoleRequestButton())
        self.add_view(AppointmentButton())
        self.add_view(ResetMemberButton())
        self.add_view(ServiceView())
        # DÃ©marrer les tÃ¢ches automatisÃ©es
        weekly_taxi_announcement.start()
        check_giveaways.start()

bot = EMSBot()

# --- SUIVI DES RECONNEXIONS ---
BOT_START_TIME = None  # Sera fixÃ© dans on_ready (heure de connexion effective)
reconnect_count = 0
reconnect_timestamps = []  # Timestamps des reconnexions rÃ©centes (fenÃªtre glissante 1h)
RECONNECT_ALERT_THRESHOLD = 5   # Alerter si plus de 5 reconnexions en 1 heure
RECONNECT_WINDOW_SECONDS = 3600  # FenÃªtre glissante en secondes (1 heure)

# --- GESTION DES STATS ---
def load_stats():
    # Retourner juste ce qui est dans le fichier, sans valeurs par dÃ©faut
    data = robust_load_json(STATS_FILE, {})
    return data if data else {}

def save_stats(stats):
    atomic_write_json(STATS_FILE, stats)

# --- GESTION DES SERVICES ---
def load_services():
    """Charge l'historique des services (heures cumulÃ©es par employÃ©)"""
    return robust_load_json(SERVICE_FILE, {})

def save_services(data):
    atomic_write_json(SERVICE_FILE, data)

def add_service_hours(employee_key: str, hours: float, reas_count: int):
    """Ajoute des heures de service pour un employÃ©"""
    services = load_services()
    week = get_week_start()
    if week not in services:
        services[week] = {}
    if employee_key not in services[week]:
        services[week][employee_key] = {"total_hours": 0, "total_reas": 0, "sessions": 0}
    services[week][employee_key]["total_hours"] = round(services[week][employee_key]["total_hours"] + hours, 2)
    services[week][employee_key]["total_reas"] += reas_count
    services[week][employee_key]["sessions"] += 1
    save_services(services)

def add_daily_rea(employee_key: str, count: int = 1):
    """IncrÃ©mente le compteur de rÃ©as du jour pour un employÃ© (pour le graphique journalier du dashboard)"""
    try:
        daily = robust_load_json(DAILY_REAS_FILE, {})
        today_key = now_paris().strftime("%Y-%m-%d")
        if today_key not in daily:
            daily[today_key] = {}
        daily[today_key][employee_key] = daily[today_key].get(employee_key, 0) + count
        # Garder seulement les 120 derniers jours pour ne pas grossir indÃ©finiment
        if len(daily) > 120:
            for old_key in sorted(daily.keys())[:-120]:
                del daily[old_key]
        atomic_write_json(DAILY_REAS_FILE, daily)
    except Exception as _daily_err:
        print(f"Erreur add_daily_rea: {_daily_err}")

def set_embauche_date(employee_key: str):
    """Enregistre la date d'embauche d'un employÃ© (uniquement si pas dÃ©jÃ  dÃ©finie)"""
    try:
        emb = robust_load_json(EMBAUCHE_FILE, {})
        if employee_key not in emb:
            emb[employee_key] = now_paris().strftime("%Y-%m-%d")
            atomic_write_json(EMBAUCHE_FILE, emb)
    except Exception as _emb_err:
        print(f"Erreur set_embauche_date: {_emb_err}")

# --- GESTION DES BONUSES CUMULATIFS PAR SEMAINE ---
# Seuils d'inactivitÃ© (fin de service auto) configurables selon le moment de la journÃ©e.
# Chaque tuple = (heure_debut_incluse, heure_fin_exclue, minutes_avant_fin_auto)
# NOTE: le critÃ¨re "nombre de morts" n'est pas suivi par le bot actuellement â€” seul le moment
# de la journÃ©e est pris en compte ici. Si besoin de conditionner aussi sur les morts, il
# faudrait d'abord ajouter un tracking dÃ©diÃ© (pas encore existant).
INACTIVITY_THRESHOLDS = [
    (6, 14, 60),    # Matin (6h-14h) : plus calme, on laisse 1h avant fin auto
    (14, 20, 30),   # AprÃ¨s-midi (14h-20h) : 30 min (dÃ©faut)
    (20, 24, 30),   # Soir (20h-minuit) : 30 min
    (0, 6, 30),     # Nuit (0h-6h) : 30 min
]

def get_inactivity_threshold_seconds() -> int:
    """Retourne le dÃ©lai (en secondes) avant fin de service automatique,
    selon l'heure actuelle (Paris). Voir INACTIVITY_THRESHOLDS pour ajuster les plages."""
    current_hour = now_paris().hour
    for start_h, end_h, minutes in INACTIVITY_THRESHOLDS:
        if start_h <= current_hour < end_h:
            return minutes * 60
    return 1800  # fallback 30 min si aucune plage ne correspond

def get_week_start():
    """Retourne la date du lundi de cette semaine"""
    today = now_paris()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")

def load_bonuses_week():
    """Charge les bonuses cumulatifs de cette semaine"""
    if not os.path.exists(BONUSES_WEEK_FILE):
        return {}
    data = robust_load_json(BONUSES_WEEK_FILE, {})
    return data if data else {}

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
    now = now_paris()
    
    # VÃ©rifier que c'est entre 21h et 23h
    if not (21 <= now.hour < 23):
        return 0
    
    bonuses = load_bonuses_week()
    week_start = get_week_start()
    today = now.strftime("%Y-%m-%d")
    key = f"{employee_key}_{week_start}"
    
    # Initialiser la liste si elle n'existe pas
    if key not in bonuses:
        bonuses[key] = []
    
    # Ajouter la date d'aujourd'hui si pas dÃ©jÃ  prÃ©sente
    if today not in bonuses[key]:
        bonuses[key].append(today)
    
    # Sauvegarder
    save_bonuses_week(bonuses)
    
    # Retourner le nombre total de jours distincts
    return len(set(bonuses[key]))

def get_week_bonus_summary():
    """Retourne un rÃ©sumÃ© des bonuses cette semaine: {employee_key: bonus_count}"""
    bonuses = load_bonuses_week()
    week_start = get_week_start()
    result = {}
    
    for key, value in bonuses.items():
        if not isinstance(value, list):
            continue
        if key.endswith(f"_{week_start}"):
            employee_key = key.replace(f"_{week_start}", "")
            result[employee_key] = len(set(value))
    
    return result

def find_member_by_key(guild: discord.Guild, employee_key: str):
    # Trouve un membre Discord par son employee_key (lookup O(n) dans le cache)
    for m in guild.members:
        if not m.bot and normalize_employee_key(get_clean_name(m)) == employee_key:
            return m
    return None

def slugify_patient_id(text: str) -> str:
    """GÃ©nÃ¨re un slug strictement sÃ»r pour une URL (uniquement a-z, 0-9, tirets).
    Contrairement Ã  normalize_employee_key, retire TOUT caractÃ¨re spÃ©cial
    (?, #, /, &, %, etc.) qui casserait l'URL de l'API patients."""
    import re as _re_slug
    import unicodedata as _ud
    if not text:
        return "patient"
    s = text.strip().lower()
    # TranslittÃ©rer les accents (Ã© -> e, etc.) pour un slug propre
    s = _ud.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = _re_slug.sub(r'[^a-z0-9]+', '-', s)
    s = s.strip('-')
    return s or "patient"

def normalize_employee_key(name: str) -> str:
    """Normalise un identifiant d'employÃ© pour correspondre aux clÃ©s de stats.json.
    - met en minuscules
    - supprime les prÃ©fixes de rÃ´le (dir-, cds-, med-, int-, emt-, ads-, inf-, rh-, drh-)
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
    # Supprimer TOUS les prÃ©fixes de grade connus (avec tiret OU espace)
    # Ordre important: dir- avant drh- pour Ã©viter confusion
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
    # Boucler jusqu'Ã  ce qu'aucun prÃ©fixe ne soit dÃ©tectÃ© (au cas oÃ¹ il y en aurait plusieurs)
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
    # Supprimer tirets au dÃ©but/fin
    s = s.strip("-")
    return s

def load_channel_map():
    return robust_load_json(CHANNEL_MAP_FILE, {})

def save_channel_map(mapping: dict):
    atomic_write_json(CHANNEL_MAP_FILE, mapping)

def get_channel_employee_key(channel: discord.abc.GuildChannel) -> str:
    """Retourne la clÃ© employÃ© pour un channel donnÃ© en s'appuyant sur un mapping persistant.
    Si absente, la dÃ©duit du nom du channel et persiste le mapping.
    Force toujours la normalisation pour garantir la cohÃ©rence.
    """
    mapping = load_channel_map()
    
    # Extraire le nom du channel (enlever l'emoji couleur)
    raw = channel.name[1:].strip() if channel.name and len(channel.name) > 1 else channel.name
    # TOUJOURS normaliser le nom pour garantir la cohÃ©rence
    key = normalize_employee_key(raw or "")
    
    # VÃ©rifier si un mapping existe dÃ©jÃ  pour ce channel
    existing_key = mapping.get(str(channel.id))
    
    # Si le mapping existe MAIS la clÃ© est diffÃ©rente, mettre Ã  jour avec la clÃ© normalisÃ©e
    if existing_key != key:
        mapping[str(channel.id)] = key
        save_channel_map(mapping)
    
    return key

def extract_employee_name(channel_name):
    """Extrait le nom normalisÃ© de l'employÃ© Ã  partir du nom du channel (sans l'emoji)."""
    if len(channel_name) > 1:
        raw = channel_name[1:].strip()
        return normalize_employee_key(raw)
    return None

def get_color_emoji(count):
    """Retourne l'emoji couleur en fonction du nombre de rÃ©actions"""
    if count >= 100:
        return "ðŸŸ¢"
    elif count >= 75:
        return "ðŸŸ "
    else:
        return "ðŸ”´"

# --- GESTION DES STATS TAXI ---
def load_taxi_stats():
    return robust_load_json(TAXI_STATS_FILE, {"count": 0, "week_start": now_paris().isoformat()})

def save_taxi_stats(stats):
    atomic_write_json(TAXI_STATS_FILE, stats)

def reset_taxi_week():
    """RÃ©initialise les stats taxi pour la nouvelle semaine"""
    stats = {"count": 0, "week_start": now_paris().isoformat()}
    save_taxi_stats(stats)
    return stats

# --- GESTION DES STATS BURGERSHOT ---
def load_burgershot_stats():
    return robust_load_json(BURGERSHOT_STATS_FILE, {"count": 0, "week_start": now_paris().isoformat()})

def save_burgershot_stats(stats):
    atomic_write_json(BURGERSHOT_STATS_FILE, stats)

def reset_burgershot_week():
    """RÃ©initialise les stats BurgerShot pour la nouvelle semaine"""
    stats = {"count": 0, "week_start": now_paris().isoformat()}
    save_burgershot_stats(stats)
    return stats

# --- GESTION DES GIVEAWAYS ---
def load_giveaways():
    return robust_load_json(GIVEAWAY_FILE, {})

def save_giveaways(giveaways):
    atomic_write_json(GIVEAWAY_FILE, giveaways)

# --- SYSTEME DE RÃ‰ACTIONS ET COMPTAGE TAXI ---

def load_bonuses():
    """Charge les bonus journaliers (format: {'employee-key_YYYY-MM-DD': 1})"""
    data = robust_load_json(os.path.join(DATA_DIR, "bonuses.json"), {})
    return data if data else {}

def save_bonuses(bonuses):
    """Sauvegarde les bonus journaliers"""
    atomic_write_json(os.path.join(DATA_DIR, "bonuses.json"), bonuses, make_backup=True)

def get_today_bonus(employee_key: str) -> int:
    """Retourne le bonus total d'aujourd'hui pour cet employÃ© (0 ou 1M)"""
    bonuses = load_bonuses()
    today = now_paris().strftime("%Y-%m-%d")
    bonus_key = f"{employee_key}_{today}"
    # Retourne 1 si la clÃ© existe, sinon 0
    return 1 if bonus_key in bonuses else 0

def award_bonus(employee_key: str) -> bool:
    """Attribue le bonus 1M de la soirÃ©e si pas dÃ©jÃ  donnÃ© aujourd'hui"""
    bonuses = load_bonuses()
    today = now_paris().strftime("%Y-%m-%d")
    bonus_key = f"{employee_key}_{today}"
    
    if bonus_key not in bonuses:
        bonuses[bonus_key] = 1
        save_bonuses(bonuses)
        return True  # Bonus attribuÃ©
    return False  # Bonus dÃ©jÃ  reÃ§u

def get_total_bonuses(employee_key: str) -> int:
    """Retourne le nombre total de primes jamais reÃ§ues par cet employÃ©"""
    bonuses = load_bonuses()
    total = 0
    for key, value in bonuses.items():
        if key.startswith(f"{employee_key}_"):
            total += value
    return total

async def update_channel_description(channel: discord.TextChannel, count: int):
    """Met ï¿½ jour la description du channel avec rï¿½a et prime soir 1M"""
    try:
        emoji = get_color_emoji(count)
        employee_key = get_channel_employee_key(channel)
        
        if not employee_key:
            return
        
        # Toujours afficher le total des primes accumulÃ©es
        total_bonuses = get_total_bonuses(employee_key)
        bonus_text = f" | ðŸ’° {total_bonuses}M" if total_bonuses > 0 else ""

        description = f"{emoji} {count}/100{bonus_text}"
        await channel.edit(topic=description)
    except Exception as e:
        print(f"Erreur update_channel_description: {e}")
# (1er on_message supprimÃ© - fusionnÃ© dans le handler principal)

# --- COMMANDES ADMIN ---
@bot.tree.command(name="total", description="Affiche le total des rÃ©actions + primes")
@app_commands.checks.has_permissions(administrator=True)
async def total(interaction: discord.Interaction):
    await interaction.response.defer()
    
    stats = load_stats()
    
    if not stats:
        embed = discord.Embed(
            title="ðŸš‘ Statistiques",
            description="Aucune donnÃ©e",
            color=EMS_RED
        )
        embed.set_footer(text="ðŸš‘ EMS System")
        await interaction.followup.send(embed=embed)
        return
    
    # Regrouper les stats par nom normalisÃ© (sans prÃ©fixes de grade)
    grouped_stats = {}
    for name, count in stats.items():
        # Normaliser le nom pour supprimer les prÃ©fixes (dir-, cds-, etc.)
        normalized = normalize_employee_key(name)
        if normalized not in grouped_stats:
            grouped_stats[normalized] = 0
        grouped_stats[normalized] += count
    
    sorted_stats = sorted(grouped_stats.items(), key=lambda x: x[1], reverse=True)
    
    # CrÃ©er plusieurs embeds si nÃ©cessaire (25 champs max par embed)
    embeds = []
    current_embed = None
    field_count = 0
    
    for name, count in sorted_stats:
        if field_count >= 25:
            # Ajouter l'embed courant Ã  la liste AVANT de crÃ©er un nouveau
            embeds.append(current_embed)
            # CrÃ©er un nouvel embed
            current_embed = discord.Embed(
                title=f"ðŸš‘ ðŸ“Š Statistiques (suite)",
                color=EMS_RED
            )
            field_count = 0
        
        if current_embed is None:
            current_embed = discord.Embed(
                title="ðŸš‘ ðŸ“Š Statistiques",
                color=EMS_RED
            )
        
        emoji = get_color_emoji(count)
        # Afficher le nom joliment formatÃ©
        display_name = ' '.join([p.capitalize() for p in name.split('-')])
        # Ajouter les primes totales
        total_bonuses = get_total_bonuses(name)
        bonus_text = f" (+{total_bonuses}M primes)" if total_bonuses > 0 else ""
        current_embed.add_field(name=f"{emoji} {display_name}", value=f"{count}/100{bonus_text}", inline=False)
        field_count += 1
    
    # Ajouter le dernier embed avec le footer
    if current_embed:
        current_embed.set_footer(text="ðŸš‘ EMS System")
        embeds.append(current_embed)
    
    # Calculer le total des rÃ©actions et primes
    total_reactions = sum(grouped_stats.values())
    total_all_bonuses = sum(get_total_bonuses(name) for name, _ in grouped_stats.items())
    
    # Ajouter les heures de service
    services = load_services()
    week = get_week_start()
    week_services = services.get(week, {})
    
    # Ajouter un dernier embed avec le rÃ©sumÃ© avec heures
    summary_text = f"**Total des rÃ©actions :** `{total_reactions}` ðŸŽ¯\n**Total des primes :** `{total_all_bonuses}M` ðŸ’°"
    
    if week_services:
        summary_text += "\n\n**â±ï¸ Heures de service cette semaine :**\n"
        sorted_svc = sorted(week_services.items(), key=lambda x: x[1]['total_hours'], reverse=True)
        total_week_hours = 0
        for emp_key, data in sorted_svc:
            h = int(data['total_hours'])
            m = int((data['total_hours'] - h) * 60)
            display = emp_key.replace('-', ' ').title()
            summary_text += f"â€¢ **{display}** : `{h}h{m:02d}` ({data['total_reas']} rÃ©as / {data['sessions']} services)\n"
            total_week_hours += data['total_hours']
        # Ajouter le total des heures
        total_h = int(total_week_hours)
        total_m = int((total_week_hours - total_h) * 60)
        summary_text += f"\n**âž• TOTAL HEURES SEMAINE:** `{total_h}h{total_m:02d}`"
    
    # En service actuellement
    if active_services:
        summary_text += "\n**ðŸŸ¢ En service actuellement :**\n"
        for uid, svc in active_services.items():
            start_t = datetime.fromisoformat(svc['start'])
            mins = int((now_paris() - start_t).total_seconds() // 60)
            name = svc.get('display_name', svc['employee_key'])
            summary_text += f"â€¢ **{name}** (<@{uid}>) - {mins} min ({svc.get('reas_count', 0)} rÃ©as)\n"
    
    summary_embed = discord.Embed(
        title="ðŸ“Š RÃ‰SUMÃ‰ DE CETTE SEMAINE",
        description=summary_text,
        color=EMS_RED
    )
    summary_embed.set_footer(text="ðŸš‘ EMS System")
    embeds.append(summary_embed)
    
    # Envoyer tous les embeds
    for embed in embeds:
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="reset", description="RÃ©initialise les compteurs")
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction):
    await interaction.response.defer()
    save_stats({})
    
    embed = discord.Embed(
        title="ðŸš‘ âœ… RÃ©initialisation",
        description="Compteurs rÃ©initialisÃ©s",
        color=EMS_RED
    )
    embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="info", description="Envoie les informations EMS dans le channel dï¿½diï¿½")
@app_commands.checks.has_permissions(administrator=True)
async def info(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # Channel et rï¿½le cibles
    target_channel_id = 1306021673912238142
    ping_role_id = 838102445095256068

    target_channel = bot.get_channel(target_channel_id)
    if not target_channel:
        await interaction.followup.send(" Channel cible introuvable!", ephemeral=True)
        return

    role = interaction.guild.get_role(ping_role_id)
    role_mention = f"<@&{ping_role_id}>" if role else "@everyone"

    # Crï¿½er l'embed principal
    embed = discord.Embed(
        title=" :EMS: Frï¿½quence EMS : 9",
        description="Toutes les infos utiles ï¿½ savoir",
        color=EMS_RED
    )

    # Section conformitï¿½
    embed.add_field(
        name=" Conformitï¿½",
        value=(
            "Avant de dï¿½buter votre formation, assurez-vous d'ï¿½tre en conformitï¿½ avec le rï¿½glement intï¿½rieur. "
            "Ne pas respecter les rï¿½gles peut entraï¿½ner un licenciement sans frais.\n\n"
            "Vous devez reprï¿½senter l'institution publique mï¿½dicale des EMS avec sï¿½rieux et fiertï¿½."
        ),
        inline=False
    )

    # Section systï¿½me de paie
    embed.add_field(
        name=" Systï¿½me de Paie",
        value=(
            "La paye dï¿½pend du nombre de rï¿½animations effectuï¿½es.\n"
            " **Paye maximale :** jusqu'ï¿½ 10 000 000$ selon le nombre de rï¿½animations."
        ),
        inline=False
    )

    # Section quota
    embed.add_field(
        name=" Quota Hebdomadaire",
        value=(
            "**Chaque semaine, vous devez effectuer un minimum de 75 rï¿½animations.**\n\n"
            "** Systï¿½me de couleurs (ï¿½mojis) :**\n"
            " **Rouge** : Moins de 75 rï¿½animations\n"
            " **Orange** : 75 rï¿½animations (quota atteint)\n"
            " **Vert** : 100 rï¿½animations et plus (augmentation de grade)"
        ),
        inline=False
    )

    # Section prime soirï¿½e
    embed.add_field(
        name=" Prime d'Activitï¿½ Soirï¿½e",
        value=(
            "**Bonus 1M par soir entre 21h-23h**\n"
            " Effectuez au moins 1 rï¿½animation entre 21h et 23h\n"
            " Gagnez automatiquement +1M (primes ï¿½ la fin de la semaine)\n"
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
            "**Rï¿½animation :** Prï¿½levï¿½ automatiquement\n"
            "**Bandage :** 5 000 $"
        ),
        inline=False
    )

    # Section rï¿½gles importantes
    embed.add_field(
        name=" Rï¿½gles Importantes",
        value=(
            " Il est fortement recommandï¿½ d'ï¿½tre dans une radio Discord en service (Radio Chill)\n"
            " Toute erreur ou quota non respectï¿½ sera sanctionnï¿½\n"
            " Pas de vente de medikits ou bandages ï¿½ usage personnel, uniquement professionnel\n"
            "  **IMPORTANT : Envoyez la preuve (screenshot) de chaque rï¿½animation dï¿½s que vous rï¿½animez !**"
        ),
        inline=False
    )

    # Section captures d'ï¿½cran
    embed.add_field(
        name=" Captures d'ï¿½cran obligatoires",
        value="Voir les images ci-dessous",
        inline=False
    )

    embed.set_footer(text=" EMS System | Respectez ces rï¿½gles pour garantir votre carriï¿½re au sein des EMS")

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
    await interaction.followup.send(f" Informations EMS envoyï¿½es dans {target_channel.mention}!", ephemeral=True)
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
            title="ðŸ’¾ INFORMATIONS DE SAUVEGARDE",
            description="Ã‰tat actuel du systÃ¨me de statistiques",
            color=EMS_RED
        )
        
        embed.add_field(
            name="ðŸ“Š DonnÃ©es chargÃ©es",
            value=f"**EmployÃ©s enregistrÃ©s :** {len(stats)}\n**Total des rÃ©as :** {sum(stats.values())}",
            inline=False
        )
        
        embed.add_field(
            name="ðŸ“ Fichier stats.json",
            value=f"**Taille :** {file_size} octets\n**DerniÃ¨re modification :** {mod_datetime.strftime('%d/%m/%Y %H:%M:%S')}",
            inline=False
        )
        
        # Top 5
        if stats:
            top_5 = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:5]
            top_text = "\n".join([f"{get_color_emoji(count)} **{name}** : {count}" for name, count in top_5])
            embed.add_field(
                name="ðŸ† Top 5",
                value=top_text,
                inline=False
            )
        
        embed.add_field(
            name="âœ… Statut",
            value="**Sauvegarde automatique :** ActivÃ©e âœ“\n**Backup au dÃ©marrage :** ActivÃ© âœ“\n**SystÃ¨me :** OpÃ©rationnel",
            inline=False
        )
        
        embed.set_footer(text="ðŸš‘ EMS System | Les stats sont sauvegardÃ©es Ã  chaque modification")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="âŒ Erreur",
            description=f"Impossible de rÃ©cupÃ©rer les informations:\n```{e}```",
            color=EMS_DARK_RED
        )
        await interaction.followup.send(embed=error_embed)

@app_commands.checks.has_permissions(administrator=True)
async def sync_rea(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    stats = load_stats()
    
    synced_count = 0
    channels_synced = []
    
    # Parcourir tous les channels de rÃ©animation
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            channel_synced = 0
            
            # RÃ©cupÃ©rer l'employÃ© associÃ© au channel
            employee_key = get_channel_employee_key(channel)
            if not employee_key:
                continue
            
            # Chercher le dernier message de /semaine (NOUVELLE SEMAINE) pour ne traiter que les messages aprÃ¨s
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
            
            # RÃ©cupÃ©rer les messages (limitÃ© aux 100 derniers pour Ã©viter les timeouts)
            try:
                async for message in channel.history(limit=100):
                    # Si on a trouvÃ© un message de /semaine, ignorer les messages avant cette date
                    if last_semaine_date and message.created_at < last_semaine_date:
                        continue
                    
                    # VÃ©rifier si le message a des piÃ¨ces jointes
                    if not message.attachments or message.author.bot:
                        continue
                    
                    # VÃ©rifier si le bot a dÃ©jÃ  rÃ©agi avec âœ…
                    bot_reacted = False
                    for reaction in message.reactions:
                        if str(reaction.emoji) == "âœ…":
                            # VÃ©rifier si c'est le bot qui a rÃ©agi
                            async for user in reaction.users():
                                if user.id == bot.user.id:
                                    bot_reacted = True
                                    break
                            if bot_reacted:
                                break
                    
                    # Si le bot n'a pas encore rÃ©agi, traiter le message
                    if not bot_reacted:
                        # IncrÃ©menter le compteur
                        if employee_key not in stats:
                            stats[employee_key] = 0
                        
                        stats[employee_key] += 1
                        channel_synced += 1
                        synced_count += 1
                        
                        # Ajouter la rÃ©action
                        try:
                            await message.add_reaction("âœ…")
                        except:
                            pass
                        
                        # Envoyer log
                        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
                        if log_channel:
                            current_count = stats[employee_key]
                            emoji = get_color_emoji(current_count)
                            message_text = f"ðŸ”„ **{employee_key}** | {current_count} rÃ©as (sync)"
                            
                            try:
                                await log_channel.send(message_text)
                            except:
                                pass
            
            except Exception as e:
                print(f"Erreur sync channel {channel.name}: {e}")
                continue
            
            # Mettre Ã  jour la couleur du channel si des messages ont Ã©tÃ© synchronisÃ©s
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
            title="ðŸ”„ SYNCHRONISATION COMPLÃ‰TÃ‰E",
            description=f"**{synced_count} rÃ©animation(s) rÃ©cupÃ©rÃ©e(s) et ajoutÃ©e(s) aux quotas**",
            color=EMS_RED
        )
        
        if channels_synced:
            channels_text = "\n".join(channels_synced[:25])  # Limiter Ã  25 pour Ã©viter les embeds trop longs
            embed.add_field(name="ðŸ“Š Channels synchronisÃ©s", value=channels_text, inline=False)
        
        embed.add_field(
            name="âœ… Actions effectuÃ©es",
            value="â€¢ Messages cochÃ©s avec âœ…\nâ€¢ Compteurs mis Ã  jour\nâ€¢ Couleurs des channels actualisÃ©es\nâ€¢ Logs envoyÃ©s\nâ€¢ â±ï¸ Uniquement les rÃ©as aprÃ¨s /semaine",
            inline=False
        )
        embed.set_footer(text="ðŸš‘ EMS System | Synchronisation automatique")
    else:
        embed = discord.Embed(
            title="âœ… SYNCHRONISATION COMPLÃ‰TÃ‰E",
            description="Aucune rÃ©animation Ã  rattraper. Tous les messages ont dÃ©jÃ  Ã©tÃ© traitÃ©s !",
            color=EMS_RED
        )
        embed.set_footer(text="ðŸš‘ EMS System")
    
    await interaction.followup.send(embed=embed)

@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    member="Le membre Ã  mettre Ã  jour",
    value="La nouvelle valeur de rÃ©animations"
)
async def force_update(interaction: discord.Interaction, member: discord.Member, value: int):
    await interaction.response.defer()
    
    stats = load_stats()
    member_name = f"{member.name}".lower().replace(" ", "-")
    
    # Chercher la clÃ© dans stats
    found_key = None
    for key in stats.keys():
        if member.name.lower() in key or key.lower() in member.name.lower():
            found_key = key
            break
    
    if found_key:
        old_value = stats[found_key]
        stats[found_key] = value
        save_stats(stats)
        
        # Mettre Ã  jour la description du channel si applicable
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
            title="âœ… STATS MISES Ã€ JOUR",
            description=f"**{member.name}**\nAncienne valeur: `{old_value}`\nNouvelle valeur: `{value}`",
            color=EMS_RED
        )
        embed.set_footer(text="ðŸš‘ EMS System | Force Update")
    else:
        embed = discord.Embed(
            title="âŒ ERREUR",
            description=f"Impossible de trouver les stats de `{member.name}`",
            color=0xFF0000
        )
    
    await interaction.followup.send(embed=embed)

@app_commands.checks.has_permissions(administrator=True)
async def force_update_all(interaction: discord.Interaction):
    await interaction.response.defer()
    
    # Mise Ã  jour forcÃ©e de toutes les stats
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
    
    # Mettre Ã  jour les descriptions des channels
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
        title="âœ… TOUS LES STATS MIS Ã€ JOUR",
        description=f"**{len(new_stats)} employÃ©s mises Ã  jour**\n**{updated_count} channels descriptions mises Ã  jour**",
        color=EMS_RED
    )
    
    # Ajouter les dÃ©tails
    stats_text = "\n".join([f"`{k}`: {v}/100" for k, v in list(new_stats.items())[:10]])
    embed.add_field(name="Premiers 10 employÃ©s", value=stats_text, inline=False)
    embed.set_footer(text="ðŸš‘ EMS System | Force Update All")
    
    await interaction.followup.send(embed=embed)

@app_commands.checks.has_permissions(administrator=True)
async def fix_emojis(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    stats = load_stats()
    
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    
    # DÃ©lai entre chaque mise Ã  jour pour Ã©viter le rate limiting
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
                    # DÃ©lai pour Ã©viter le rate limiting
                    await asyncio.sleep(DELAY_BETWEEN_UPDATES)
                except Exception as e:
                    failed_count += 1
                    print(f"âŒ Erreur mise Ã  jour {key}: {e}")
            else:
                skipped_count += 1
                
        except Exception as e:
            failed_count += 1
            print(f"âŒ Erreur traitement {key}: {e}")
    
    embed = discord.Embed(
        title="âœ… CORRECTION DES EMOJIS COMPLÃ‰TÃ‰E",
        description=f"Mise Ã  jour des descriptions de salons",
        color=EMS_RED
    )
    embed.add_field(name="âœ… Mis Ã  jour", value=f"{updated_count} salons", inline=True)
    embed.add_field(name="â­ï¸ IgnorÃ©s", value=f"{skipped_count} salons", inline=True)
    embed.add_field(name="âŒ Erreurs", value=f"{failed_count} salons", inline=True)
    embed.set_footer(text="ðŸš‘ EMS System | Fix Emojis")
    
    await interaction.followup.send(embed=embed)

@app_commands.checks.has_permissions(administrator=True)
async def update_colors(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    stats = load_stats()
    
    updated_count = 0
    errors = []
    
    # Parcourir tous les channels avec emoji
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            try:
                # RÃ©cupÃ©rer la clÃ© employÃ©
                employee_key = get_channel_employee_key(channel)
                if not employee_key:
                    continue
                
                # RÃ©cupÃ©rer le compteur
                current_count = stats.get(employee_key, 0)
                
                # Calculer la nouvelle couleur
                new_emoji = get_color_emoji(current_count)
                current_emoji = channel.name[0]
                
                # Mettre Ã  jour si diffÃ©rent
                if current_emoji != new_emoji:
                    new_channel_name = f"{new_emoji}{channel.name[1:]}"
                    await channel.edit(name=new_channel_name)
                    updated_count += 1
                    
            except Exception as e:
                errors.append(f"âŒ {channel.name}: {str(e)[:50]}")
    
    # Message de confirmation
    embed = discord.Embed(
        title="ðŸŽ¨ MISE Ã€ JOUR DES COULEURS",
        description=f"**{updated_count} channel(s) mis Ã  jour**",
        color=EMS_RED
    )
    
    if errors:
        embed.add_field(
            name="âš ï¸ Erreurs",
            value="\n".join(errors[:10]),
            inline=False
        )
    
    embed.add_field(
        name="ðŸ“Š LÃ©gende",
        value="ðŸ”´ Moins de 50 rÃ©as\nðŸŸ  Entre 50 et 99 rÃ©as\nðŸŸ¢ 100 rÃ©as ou plus",
        inline=False
    )
    
    embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="semaine", description="RÃ©initialise la semaine - Remet tout Ã  0 et met en rouge")
@app_commands.checks.has_permissions(administrator=True)
async def semaine(interaction: discord.Interaction):
    global evening_reas
    await interaction.response.defer()
    
    guild = interaction.guild
    week_key = get_week_start()
    
    # 1) Bilan hebdomadaire avant reset
    pre_stats = load_stats()
    log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))

    if log_channel and pre_stats:
        ordered = sorted(pre_stats.items(), key=lambda kv: kv[1], reverse=True)

        def pretty_name(key: str) -> str:
            return ' '.join([p.capitalize() for p in key.split('-')])

        embeds = []
        current_embed = None
        field_count = 0
        page_index = 1
        total_reactions = sum(pre_stats.values())

        for name_key, count in ordered:
            if current_embed is None or field_count >= 25:
                if current_embed is not None:
                    current_embed.set_footer(text=f"ðŸš‘ EMS System | Page {page_index}")
                    embeds.append(current_embed)
                    page_index += 1
                current_embed = discord.Embed(
                    title="ðŸ“Š BILAN HEBDOMADAIRE EMS",
                    description="RÃ©capitulatif des rÃ©animations par employÃ© (semaine)",
                    color=EMS_RED
                )
                field_count = 0

            emoji = get_color_emoji(count)
            display_name = pretty_name(name_key)
            total_bonuses = get_total_bonuses(name_key)
            bonus_str = f" | ðŸ’° {total_bonuses}M primes" if total_bonuses > 0 else ""
            current_embed.add_field(
                name=f"{emoji} {display_name}",
                value=f"{count}/100{bonus_str}",
                inline=False
            )
            field_count += 1

        if current_embed is not None:
            current_embed.set_footer(text=f"ðŸš‘ EMS System | Page {page_index}")
            embeds.append(current_embed)

        # RÃ©sumÃ© heures de service
        svc_data = load_services()
        week_svc = svc_data.get(week_key, {})
        svc_summary = ""
        if week_svc:
            svc_summary = "\n\n**â±ï¸ Heures de service :**\n"
            sorted_svc = sorted(week_svc.items(), key=lambda x: x[1]['total_hours'], reverse=True)
            total_h_all = 0
            for emp_key, d in sorted_svc:
                h = int(d['total_hours'])
                m = int((d['total_hours'] - h) * 60)
                display = emp_key.replace('-', ' ').title()
                svc_summary += f"â€¢ **{display}** : {h}h{m:02d} ({d['total_reas']} rÃ©as / {d['sessions']} services)\n"
                total_h_all += d['total_hours']
            h_t = int(total_h_all)
            m_t = int((total_h_all - h_t) * 60)
            svc_summary += f"\n**Total heures :** {h_t}h{m_t:02d}"

        summary_embed = discord.Embed(
            title="ðŸ“Š RÃ‰SUMÃ‰ SEMAINE EMS",
            description=f"**Total rÃ©animations :** `{total_reactions}` ðŸŽ¯{svc_summary}",
            color=EMS_RED
        )
        summary_embed.set_footer(text="ðŸš‘ EMS System")
        embeds.append(summary_embed)

        for e in embeds:
            try:
                await log_channel.send(embed=e)
            except:
                pass

    # 1.5) Sauvegarder un instantanÃ© de la semaine AVANT tout reset,
    # pour que le rÃ©cap du dashboard (onglet RÃ©union) puisse toujours
    # afficher les infos de la semaine qui vient de se terminer,
    # mÃªme si /semaine a dÃ©jÃ  Ã©tÃ© lancÃ©e entre-temps.
    try:
        snapshot = {
            'week_key': week_key,
            'stats': dict(pre_stats),
            'evening_reas': dict(evening_reas),
            'services': load_services().get(week_key, {}),
            'saved_at': now_paris().isoformat(),
        }
        save_week_snapshot(snapshot)
        save_week_to_history(week_key, snapshot, finalized=True)
    except Exception as _snap_err:
        print(f"Erreur sauvegarde week_snapshot: {_snap_err}")

    # 2) Reset stats rÃ©as
    save_stats({})
    # Reset historique dispatch pour le dashboard
    dispatch_history.clear()
    coffre_tracking.clear()

    # 3) Reset primes soirÃ©e (evening_reas)
    evening_reas = {}
    atomic_write_json(EVENING_REAS_FILE, evening_reas)

    # 4) Reset primes quotidiennes (bonuses.json)
    save_bonuses({})

    # 5) Reset heures de service de la semaine
    svc_data_reset = load_services()
    if week_key in svc_data_reset:
        del svc_data_reset[week_key]
    save_services(svc_data_reset)

    # 6) Reset bonus semaine (bonuses_week.json)
    bonuses_week_reset = load_bonuses_week()
    keys_to_delete = [k for k in bonuses_week_reset if k.endswith(f"_{week_key}")]
    for k in keys_to_delete:
        del bonuses_week_reset[k]
    save_bonuses_week(bonuses_week_reset)

    # 7) Mettre tous les channels en ðŸ”´ 0/100
    announcement_channels = []
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            new_name = f"ðŸ”´{channel.name[1:]}"
            try:
                await channel.edit(name=new_name, topic="ðŸ”´ 0/100")
                announcement_channels.append(channel)
                await asyncio.sleep(2)
            except:
                pass

    # 8) BanniÃ¨re nouvelle semaine
    banner_url = "https://media.discordapp.net/attachments/1432501937085087896/1457439823215460487/image.png?ex=695ea51b&is=695d539b&hm=73669ae578193fac7bb528589592facb8ffa94a53f6521f1fad68165e393d32c&=&format=webp&quality=lossless&width=1872&height=571"
    banner_data = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(banner_url) as resp:
                if resp.status == 200:
                    banner_data = await resp.read()
    except Exception as e:
        print(f"Erreur banniÃ¨re: {e}")

    embed = discord.Embed(
        title="ðŸš‘ NOUVELLE SEMAINE !",
        description="**âœ… RÃ©initialisation complÃ¨te de la semaine**\n\nâ€¢ Tous les compteurs remis Ã  0\nâ€¢ Toutes les primes remises Ã  0\nâ€¢ Tous les channels en ðŸ”´\nâ€¢ C'est repartit de zÃ©ro !\n\n**Bonne chance Ã  tous ! ðŸ’ª**",
        color=EMS_RED
    )
    embed.set_footer(text="ðŸš‘ EMS System | Nouvelle semaine, nouveau challenge !")

    if banner_data:
        embed.set_image(url=f"attachment://nouvelle_semaine.png")

    for channel in announcement_channels:
        try:
            if banner_data:
                await channel.send(embed=discord.Embed.from_dict(embed.to_dict()), file=discord.File(io.BytesIO(banner_data), filename="nouvelle_semaine.png"))
            else:
                await channel.send(embed=discord.Embed.from_dict(embed.to_dict()))
        except:
            pass

    if log_channel:
        try:
            if banner_data:
                await log_channel.send(embed=discord.Embed.from_dict(embed.to_dict()), file=discord.File(io.BytesIO(banner_data), filename="nouvelle_semaine.png"))
            else:
                await log_channel.send(embed=discord.Embed.from_dict(embed.to_dict()))
        except:
            pass

    embed_confirm = discord.Embed(
        title="âœ… SEMAINE RÃ‰INITIALISÃ‰E",
        description=(
            "âœ… Stats rÃ©as remises Ã  0\n"
            "âœ… Primes quotidiennes remises Ã  0\n"
            "âœ… Primes semaine remises Ã  0\n"
            "âœ… Heures de service remises Ã  0\n"
            "âœ… Channels mis en ðŸ”´ 0/100\n"
            "âœ… Bilan postÃ© dans les logs\n\n"
            "C'est parti pour une nouvelle semaine ! ðŸš€"
        ),
        color=EMS_RED
    )
    embed_confirm.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed_confirm)
@app_commands.checks.has_permissions(administrator=True)
async def reset_silent(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # 1) RÃ©initialiser stats
    save_stats({})
    
    # RÃ©initialiser les heures de service de la semaine
    svc_data_reset = load_services()
    week_key = get_week_start()
    if week_key in svc_data_reset:
        del svc_data_reset[week_key]
    save_services(svc_data_reset)
    
    # RÃ©initialiser les bonus de la semaine
    bonuses_week_reset = load_bonuses_week()
    week_start = get_week_start()
    keys_to_delete = [k for k in bonuses_week_reset.keys() if k.endswith(f"_{week_start}")]
    for k in keys_to_delete:
        del bonuses_week_reset[k]
    save_bonuses_week(bonuses_week_reset)
    
    # Mettre Ã  jour les descriptions des channels Ã  ðŸ”´ 0/100 (sans changer les noms)
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            try:
                await channel.edit(topic="ðŸ”´ 0/100")
            except:
                pass
    
    # RÃ©pondre avec un simple message de confirmation
    embed_confirm = discord.Embed(
        title="ðŸš‘ âœ… RESET SILENCIEUX EFFECTUÃ‰",
        description="âœ… Tous les compteurs remis Ã  0\nâœ… Jean-dan: 15 rÃ©as\nâœ… Heures remises Ã  0\nâœ… Bonus remis Ã  0\nâœ… Descriptions remises Ã  ðŸ”´ 0/100",
        color=EMS_RED
    )
    embed_confirm.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed_confirm)

@app_commands.checks.has_permissions(administrator=True)
async def force_red(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    updated_count = 0
    
    # Parcourir tous les channels et remplacer l'emoji par ðŸ”´
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            # Remplacer le premier emoji par ðŸ”´
            new_name = f"ðŸ”´{channel.name[1:]}"
            try:
                await channel.edit(name=new_name)
                updated_count += 1
                await asyncio.sleep(2)  # DÃ©lai pour Ã©viter rate limit
            except Exception as e:
                print(f"Erreur mise Ã  jour {channel.name}: {e}")
    
    embed = discord.Embed(
        title="ðŸš‘ âœ… TOUS LES CHANNELS EN ROUGE",
        description=f"âœ… {updated_count} channels remis Ã  ðŸ”´",
        color=EMS_RED
    )
    embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed)

## Commandes de couleur supprimÃ©es (sync_colors, update_color)

# --- COMMANDE TAXI ---
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
        title="ðŸš• Tests d'Aptitude Taxi",
        description=f"**Nombre de tests complÃ©tÃ©s :** {test_count}",
        color=EMS_RED
    )
    embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed)

@app_commands.checks.has_permissions(administrator=True)
async def taxi_announce(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        await send_weekly_taxi_announcement()
        await interaction.followup.send("âœ… Annonce hebdomadaire envoyÃ©e et compteurs rÃ©initialisÃ©s !", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"âŒ Erreur : {e}", ephemeral=True)

# --- COMMANDE BURGERSHOT ---
@app_commands.checks.has_permissions(administrator=True)
async def burgershot(interaction: discord.Interaction):
    await interaction.response.defer()
    
    burgershot_stats = load_burgershot_stats()
    count = burgershot_stats.get("count", 0)
    revenus = count * 300000
    
    embed = discord.Embed(
        title="ðŸ” Tests d'Aptitude BurgerShot",
        description=f"**Nombre de tests complÃ©tÃ©s :** {count}\n**Revenus gÃ©nÃ©rÃ©s :** ${revenus:,}",
        color=discord.Color.from_rgb(255, 165, 0)  # Orange
    )
    embed.add_field(name="ðŸ’° Tarif", value="300 000$ par test", inline=False)
    embed.set_footer(text="ðŸ” BurgerShot System")
    await interaction.followup.send(embed=embed)

# --- QUESTIONS DU CV ---
QUESTIONS = [
    "ðŸ“„ **Candidature EMS**\nNom et PrÃ©nom ?",
    "ðŸ”¹ **Informations personnelles**\nQuel est votre Ã¢ge ?",
    "ðŸš— **Permis de conduire**\nAvez-vous le permis de conduire (si oui, le(s)quel(s) ?)",
    "â³ **PrÃ©sence en ville**\nDepuis quand Ãªtes-vous en ville ?",
    "ðŸ’¼ **ExpÃ©rience professionnelle**\nMÃ©tier actuelle ?",
    "ðŸ“š **Parcours**\nQuels mÃ©tiers avez-vous dÃ©jÃ  exercÃ©s ?",
    "ðŸ¥ **CompÃ©tences mÃ©dicales**\nAvez-vous des compÃ©tences dans le domaine mÃ©dical ?",
    "ðŸ”¥ **Motivations**\nQuelles sont vos motivations Ã  entrer chez les EMS ?",
    "â­ **Pourquoi vous ?**\nPourquoi devrions-nous vous prendre et pas quelqu'un d'autre ?",
    "ðŸ‘ **QualitÃ©s**\nDonnez-nous 3 qualitÃ©s qui vous caractÃ©risent",
    "âš ï¸ **DÃ©fauts**\nDonnez-nous 3 dÃ©fauts qui vous caractÃ©risent",
    "ðŸ“… **DisponibilitÃ©s - Semaine**\nDu lundi au vendredi : [Horaire]",
    "ðŸ“… **DisponibilitÃ©s - Week-end**\nWeek-end : [Horaire]"
]

# --- SYSTÃˆME DE CV ---
class ReviewView(discord.ui.View):
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.message = None

    @discord.ui.button(label="âœ… Accepter", style=discord.ButtonStyle.green, custom_id="accept_cv")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # DEFER IMMÃ‰DIATEMENT - AVANT TOUT (garantit pas d'erreur d'interaction)
        await interaction.response.defer(ephemeral=True)
        
        # VÃ©rifier les permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("âŒ Permission refusÃ©e", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.target_user.id)
        
        if not member:
            await interaction.followup.send("âŒ Le candidat n'est plus sur le serveur.", ephemeral=True)
            return
        
        # Ajouter le rÃ´le en attente
        try:
            role = guild.get_role(896103247096471613)
            if role:
                await member.add_roles(role)
        except Exception as e:
            print(f"[{now_paris().strftime('%H:%M:%S')}] âš ï¸ Erreur ajout rÃ´le CV: {e}")
        
        # DÃ©sactiver les boutons
        self.disable_all_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        
        # Envoyer le DM d'acceptation
        try:
            embed_accept = discord.Embed(
                title="ðŸŽ‰ FÃ‰LICITATIONS !",
                description="âœ… Votre candidature a Ã©tÃ© **ACCEPTÃ‰E** !\n\n"
                           "Bienvenue dans la famille des **EMS** ! ðŸš‘\n\n"
                           "ðŸ“ **Ã‰tape suivante :**\n"
                           "Merci de mettre vos disponibilitÃ©s dans le channel <#1482838723656941829>.\n\n"
                           "Nous nous chargerons de faire un recrutement.\n\n"
                           "Cordialement,\n**La Direction des EMS** ðŸš‘",
                color=discord.Color.green()
            )
            embed_accept.set_footer(text="ðŸš‘ EMS System | Direction")
            await member.send(embed=embed_accept)
        except Exception as e:
            print(f"[{now_paris().strftime('%H:%M:%S')}] âš ï¸ Erreur DM CV acceptÃ©: {e}")
            pass
        
        # Envoyer les logs
        try:
            embed = discord.Embed(
                title="âœ… CV ACCEPTÃ‰",
                description=f"**Candidat :** {member.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_RED
            )
            embed.add_field(name="âœ… Statut", value="Candidature approuvÃ©e âœ“", inline=False)
            embed.add_field(name="ðŸ‘¤ RÃ´le attribuÃ©", value="Attente d'onboarding", inline=False)
            embed.set_footer(text="ðŸš‘ EMS System")
            cv_track_update(str(self.target_user.id), 'accepted')
            
            # Envoyer dans le channel de logs CV (1458956197796515979)
            cv_log_channel = bot.get_channel(1458956197796515979)
            if cv_log_channel:
                await cv_log_channel.send(embed=embed)
                
                # Chercher et copier le CV original
                try:
                    cv_channel = bot.get_channel(1539697901540745317)
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
                        title=f"âœ… {member.display_name}",
                        description=f"AcceptÃ© par {interaction.user.mention}",
                        color=EMS_RED
                    )
                    avatar_embed.set_image(url=member.avatar.url)
                    avatar_embed.set_footer(text="ðŸš‘ EMS System")
                    await image_channel.send(embed=avatar_embed)
                except:
                    pass
        except:
            pass
        
        # Confirmation Ã  l'admin
        await interaction.followup.send(f"âœ… **{member.display_name}** acceptÃ© avec succÃ¨s", ephemeral=True)
        
        # Supprimer le message aprÃ¨s 3 secondes
        try:
            if self.message:
                await asyncio.sleep(3)
                await self.message.delete()
        except:
            pass

    @discord.ui.button(label="âŒ Refuser", style=discord.ButtonStyle.red, custom_id="refuse_cv")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        # DEFER IMMÃ‰DIATEMENT - AVANT TOUT (garantit pas d'erreur d'interaction)
        await interaction.response.defer(ephemeral=True)
        
        # VÃ©rifier les permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("âŒ Permission refusÃ©e", ephemeral=True)
            return
        
        # DÃ©sactiver les boutons
        self.disable_all_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        
        # Envoyer le DM au candidat
        try:
            await self.target_user.send(
                "âŒ **Candidature RefusÃ©e**\n\n"
                "Nous regrettons de vous informer que votre candidature n'a pas Ã©tÃ© retenue.\n\n"
                "Nous vous encourageons Ã  postuler Ã  nouveau dans le futur.\n\n"
                "Cordialement,\n**La Direction des EMS** ðŸš‘"
            )
        except:
            pass
        cv_track_update(str(self.target_user.id), 'refused', 'RefusÃ© par la direction')
        
        # Envoyer le log
        try:
            # Envoyer dans le channel de logs CV (1458956197796515979)
            cv_log_channel = bot.get_channel(1458956197796515979)
            if cv_log_channel:
                embed = discord.Embed(
                    title="âŒ CV REFUSÃ‰",
                    description=f"**Candidat :** {self.target_user.mention}\n**Validateur :** {interaction.user.mention}",
                    color=EMS_DARK_RED
                )
                embed.set_footer(text="ðŸš‘ EMS System")
                await cv_log_channel.send(embed=embed)
        except:
            pass
        
        # Confirmation Ã  l'admin
        await interaction.followup.send("âœ… CV refusÃ© avec succÃ¨s", ephemeral=True)
        
        # Supprimer le message aprÃ¨s 3 secondes
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

    @discord.ui.button(label="DÃ©pose ton CV", style=discord.ButtonStyle.primary, emoji="ðŸ“", custom_id="start_cv")
    async def start_cv(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ðŸ“‹ Dossier en crÃ©ation...", ephemeral=True)
        
        guild = interaction.guild
        user_id = interaction.user.id
        
        # VÃ©rifier si existe
        for ch in guild.text_channels:
            if ch.name == f"cv-{user_id}":
                await interaction.followup.send(f"âŒ Dossier existe : {ch.mention}", ephemeral=True)
                return
        
        # CrÃ©er channel
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
            await interaction.followup.send("âŒ Erreur crÃ©ation", ephemeral=True)
            return
        
        await interaction.followup.send(f"ðŸ“‹ Channel crÃ©Ã© : {channel.mention}", ephemeral=True)
        
        # Welcome
        welcome = discord.Embed(
            title="ðŸš‘ RECRUTEMENT EMS - FORMULAIRE DE CANDIDATURE",
            description=(
                f"Bienvenue **{interaction.user.mention}** ! ðŸ‘‹\n\n"
                f"Vous Ãªtes sur le point de participer Ã  notre processus de sÃ©lection pour l'Ã©quipe EMS.\n\n"
                f"**ðŸ“‹ Informations importantes :**\n"
                f"â€¢ {len(QUESTIONS)} questions Ã  rÃ©pondre\n"
                f"â±ï¸ 10 minutes par question\n"
                f"ðŸ“ RÃ©pondez de maniÃ¨re claire et dÃ©taillÃ©e\n"
                f"ðŸ“¸ PrÃ©parez vos documents (CV, diplÃ´mes, etc.)\n\n"
                f"**Bonne chance ! ðŸ’ª**"
            ),
            color=EMS_RED
        )
        welcome.set_footer(text="ðŸš‘ EMS Management System | Let's go!")
        await channel.send(embed=welcome)
        await asyncio.sleep(2)
        
        # Questions
        answers = []
        user_fullname = None
        
        for i, question in enumerate(QUESTIONS, 1):
            q_embed = discord.Embed(
                title=f"â“ QUESTION {i}/{len(QUESTIONS)}",
                description=question,
                color=EMS_RED
            )
            q_embed.add_field(name="â±ï¸ Temps", value="Vous avez **10 minutes** pour rÃ©pondre", inline=False)
            q_embed.set_footer(text="ðŸš‘ EMS System | Envoyez votre rÃ©ponse ci-dessous")
            for attempt in range(3):
                try:
                    await channel.send(embed=q_embed)
                    break
                except discord.errors.DiscordServerError:
                    if attempt < 2:
                        await asyncio.sleep(3)
                    else:
                        try:
                            await channel.send("âš ï¸ Discord rencontre des problÃ¨mes temporaires. Veuillez recliquer sur le bouton de candidature plus tard.")
                        except:
                            pass
                        return
            
            def check(m):
                return m.author == interaction.user and m.channel == channel
            
            try:
                msg = await bot.wait_for('message', check=check, timeout=600)
                
                if i == 1:
                    user_fullname = msg.content[:32]  # Limiter a 32 caracteres (limite Discord)
                    try:
                        member = guild.get_member(user_id)
                        if member:
                            await member.edit(nick=user_fullname)
                            print(f"âœ… Membre renommÃ©: {interaction.user.name} -> {user_fullname}")
                        else:
                            print(f"âŒ Membre non trouvÃ© pour renommer: {user_id}")
                    except Exception as e:
                        print(f"âŒ Erreur renommage membre: {e}")
                
                answers.append(f"**{question}**\n{msg.content}")

                # --- DÃ‰TECTION IA (questions 4+, pas nom/Ã¢ge/permis) ---
                if i >= 4:
                    analyse = _detect_ia(msg.content)
                    uid_int = interaction.user.id

                    if analyse["verdict"] == "ia_probable":
                        _IA_WARNING_COUNTS[uid_int] = _IA_WARNING_COUNTS.get(uid_int, 0) + 1
                        warn_count = _IA_WARNING_COUNTS[uid_int]

                        if warn_count >= 2:
                            ia_close = discord.Embed(
                                title="ðŸ¤– DÃ‰TECTION IA â€” FERMETURE AUTOMATIQUE",
                                description=(
                                    f"{interaction.user.mention} votre candidature a Ã©tÃ© **fermÃ©e automatiquement**.\n\n"
                                    "**Motif :** PrÃ©sence d'intelligence artificielle dÃ©tectÃ©e sur plusieurs rÃ©ponses.\n\n"
                                    "Les candidatures doivent Ãªtre **rÃ©digÃ©es personnellement**.\n"
                                    "L'utilisation d'IA est strictement interdite.\n\n"
                                    "â›” Ce channel sera supprimÃ© dans **10 secondes**."
                                ),
                                color=discord.Color.red()
                            )
                            ia_close.set_footer(text="ðŸš‘ EMS System | Candidature refusÃ©e automatiquement")
                            try:
                                await channel.send(embed=ia_close)
                            except:
                                pass
                            # Log dans le channel CV
                            cv_log = bot.get_channel(1539697901540745317)
                            if cv_log:
                                log_e = discord.Embed(
                                    title="ðŸ¤– CANDIDATURE FERMÃ‰E â€” IA",
                                    description=f"**{interaction.user.name}** (`{uid_int}`) fermÃ© pour usage d'IA.",
                                    color=discord.Color.red()
                                )
                                log_e.add_field(name="Indices", value="\n".join(analyse["indices"]) or "â€”", inline=False)
                                log_e.add_field(name="Score IA", value=f"{analyse['score']*100:.0f}%", inline=True)
                                try:
                                    await cv_log.send(embed=log_e)
                                except:
                                    pass
                            _IA_WARNING_COUNTS.pop(uid_int, None)
                            await asyncio.sleep(10)
                            try:
                                await channel.delete()
                            except:
                                pass
                            return
                        else:
                            ia_warn = discord.Embed(
                                title="âš ï¸ DÃ‰TECTION IA â€” Avertissement",
                                description=(
                                    f"{interaction.user.mention} notre systÃ¨me a dÃ©tectÃ© une possible utilisation d'**intelligence artificielle** dans votre rÃ©ponse.\n\n"
                                    "Les candidatures doivent Ãªtre **rÃ©digÃ©es entiÃ¨rement par vous-mÃªme**.\n\n"
                                    "âš ï¸ **En cas de nouvelle dÃ©tection, votre candidature sera fermÃ©e automatiquement.**"
                                ),
                                color=discord.Color.orange()
                            )
                            ia_warn.set_footer(text="ðŸš‘ EMS System | Avertissement 1/2")
                            try:
                                await channel.send(embed=ia_warn)
                            except:
                                pass
            except asyncio.TimeoutError:
                timeout_msg = discord.Embed(
                    title="â±ï¸ TEMPS Ã‰COULÃ‰ - FERMETURE AUTOMATIQUE",
                    description=(
                        "âŒ **Aucune rÃ©ponse reÃ§ue dans les 10 minutes.**\n\n"
                        "Votre dossier de candidature va Ãªtre **fermÃ© automatiquement**.\n\n"
                        "Si vous souhaitez postuler Ã  nouveau, cliquez sur le bouton de candidature.\n\n"
                        "ðŸš‘ **Fermeture dans 5 secondes...**"
                    ),
                    color=EMS_DARK_RED
                )
                timeout_msg.set_footer(text="ðŸš‘ EMS System | Session expirÃ©e")
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
            title="ðŸ“Ž DERNIÃˆRE Ã‰TAPE",
            description=(
                "Merci d'avoir complÃ©tÃ© le formulaire ! ðŸŽ‰\n\n"
                "**Il ne manque plus que :**\n"
                "ðŸ†” Votre carte d'identitÃ© (IMAGE)\n"
                "ðŸš— Votre permis de conduire (IMAGE)\n\n"
                "âš ï¸ **IMPORTANT : Envoyez des IMAGES uniquement**\n\n"
                "Envoyez-les ci-dessous et nous nous en chargerons ! ðŸš‘\n\n"
                "â±ï¸ Vous avez un temps illimitÃ© pour envoyer les documents."
            ),
            color=EMS_RED
        )
        docs.set_footer(text="ðŸš‘ EMS System | Envoyez les IMAGES ci-dessous")
        await channel.send(embed=docs)
        
        attachments = []
        downloaded_files = []
        photos_b64 = []  # pour le dashboard (carte identitÃ© / permis en base64)
        
        def check_doc(m):
            return m.author == interaction.user and m.channel == channel
        
        # Boucle jusqu'Ã  ce qu'au moins un document soit envoyÃ©
        documents_received = False
        while not documents_received:
            try:
                msg = await bot.wait_for('message', check=check_doc, timeout=None)
                
                if msg.attachments:
                    # Documents trouvÃ©s, on peut continuer
                    for att in msg.attachments:
                        # TÃ©lÃ©charger l'image
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(att.url) as resp:
                                    if resp.status == 200:
                                        data = await resp.read()
                                        downloaded_files.append(discord.File(io.BytesIO(data), filename=att.filename))
                                        attachments.append(att.url)
                                        # Encoder en base64 pour affichage dashboard (carte identitÃ© / permis)
                                        try:
                                            if len(data) < 5 * 1024 * 1024:  # limite 5 Mo par image
                                                ctype = att.content_type or 'image/png'
                                                b64 = base64.b64encode(data).decode('utf-8')
                                                photos_b64.append(f"data:{ctype};base64,{b64}")
                                        except Exception:
                                            pass
                        except:
                            attachments.append(att.url)
                    documents_received = True
                else:
                    # Pas de document, redemander
                    error_embed = discord.Embed(
                        title="âŒ DOCUMENTS REQUIS",
                        description=(
                            "âš ï¸ **Aucun document dÃ©tectÃ© !**\n\n"
                            "Vous devez **obligatoirement** envoyer vos documents :\n"
                            "ðŸ†” Carte d'identitÃ© (IMAGE)\n"
                            "ðŸš— Permis de conduire (IMAGE)\n\n"
                            "**Veuillez rÃ©essayer en envoyant vos images.**"
                        ),
                        color=EMS_DARK_RED
                    )
                    error_embed.set_footer(text="ðŸš‘ EMS System | Documents obligatoires")
                    await channel.send(embed=error_embed)
            except:
                pass
        
        confirm = discord.Embed(
            title="âœ… CANDIDATURE COMPLÃˆTE",
            description=(
                "ðŸŽ‰ Excellent ! Nous avons reÃ§u votre candidature complÃ¨te !\n\n"
                f"**Documents reÃ§us :** {len(attachments)}\n\n"
                "ðŸ‘€ **Prochaines Ã©tapes :**\n"
                "â€¢ La direction examinera votre candidature\n"
                "â€¢ Vous recevrez une rÃ©ponse dans vos messages privÃ©s\n"
                "â€¢ N'hÃ©sitez pas Ã  nous contacter en cas de questions\n\n"
                "â±ï¸ Ce channel se fermera dans **2 minutes**\n\n"
                "**Merci pour votre intÃ©rÃªt envers les EMS !** ðŸš‘"
            ),
            color=EMS_RED
        )
        confirm.set_footer(text="ðŸš‘ EMS System | Bon courage !")
        await channel.send(embed=confirm)
        
        # Envoyer le DM au candidat
        try:
            await interaction.user.send(
                "ðŸš‘ **Candidature envoyÃ©e** ðŸš‘\n\n"
                "Nous avons bien reÃ§u votre candidature.\n\n"
                "Nous vous recontacterons bientÃ´t.\n\n"
                "Merci pour votre intÃ©rÃªt ! ðŸ‘¨â€âš•ï¸"
            )
        except:
            pass
        
        # Envoyer au channel CV (en arriÃ¨re-plan pendant que le timer commence)
        cv_channel = bot.get_channel(1539697901540745317)
        if cv_channel:
            full_text = "\n\n".join(answers)
            cv_embed = discord.Embed(
                title=f"ðŸ“‹ CV - {user_fullname if user_fullname else interaction.user.name}",
                description=full_text[:2000],
                color=EMS_RED
            )
            
            cv_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            cv_embed.set_footer(text=f"ðŸš‘ EMS System | ID: {user_id}")
            
            view = ReviewView(interaction.user)
            
            # Ping direction directement dans le message du CV
            direction_role = guild.get_role(config.get("ROLE_DIRECTION_ID"))
            ping_content = direction_role.mention if direction_role and config.get("ROLE_DIRECTION_ID") != 0 else None
            
            # Envoyer l'embed avec les fichiers tÃ©lÃ©chargÃ©s
            try:
                if downloaded_files:
                    msg = await cv_channel.send(content=ping_content, embed=cv_embed, files=downloaded_files, view=view)
                else:
                    if attachments:
                        cv_embed.add_field(name="ðŸ“Ž Documents", value="\n".join([f"[Doc {i}]({url})" for i, url in enumerate(attachments, 1)]), inline=False)
                    msg = await cv_channel.send(content=ping_content, embed=cv_embed, view=view)
                view.message = msg
                cv_track_add(interaction.user, 'pending', photos_b64=photos_b64, cv_text=full_text)
                print(f"âœ… CV envoyÃ© dans le channel {cv_channel.name} pour {interaction.user.name}")
            except Exception as e:
                print(f"âŒ Erreur envoi CV: {e}")
        else:
            print(f"âŒ Channel CV non trouvÃ© (ID: 1539697901540745317)")
        
        # Fermer le channel aprÃ¨s 2 minutes
        await asyncio.sleep(120)
        try:
            await channel.delete()
        except:
            pass

# --- NOUVEAU SYSTÃˆME CV (FORMULAIRECV) ---
class FormulaireCVValidation(discord.ui.View):
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.message = None

    @discord.ui.button(label="âœ… Accepter", style=discord.ButtonStyle.green, custom_id="accept_formulaire_cv")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("âŒ Permission refusÃ©e", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.target_user.id)
        
        if not member:
            await interaction.followup.send("âŒ Le candidat n'est plus sur le serveur.", ephemeral=True)
            return
        
        # DÃ©sactiver les boutons
        for item in self.children:
            item.disabled = True
        
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            pass
        
        # Ajouter le rÃ´le 896103247096471613
        try:
            role = guild.get_role(896103247096471613)
            if role:
                await member.add_roles(role)
        except:
            pass
        
        # Envoyer le DM
        try:
            await member.send(
                "ðŸŽ‰ **FÃ‰LICITATIONS !**\n\n"
                "âœ… Votre candidature a Ã©tÃ© **ACCEPTÃ‰E** !\n\n"
                "Bienvenue dans la famille des **EMS** ! ðŸš‘\n\n"
                "ðŸ“ **Ã‰tape suivante :**\n"
                "Merci de mettre vos disponibilitÃ©s dans le channel <#1482838723656941829>.\n\n"
                "Nous nous chargerons de faire un recrutement.\n\n"
                "Cordialement,\n**La Direction des EMS** ðŸš‘"
            )
        except:
            pass
        
        # Logs
        try:
            embed = discord.Embed(
                title="âœ… CANDIDATURE ACCEPTÃ‰E",
                description=f"**Candidat :** {member.mention}\n**Validateur :** {interaction.user.mention}",
                color=EMS_RED
            )
            embed.set_footer(text="ðŸš‘ EMS System")
            
            # Envoyer dans le channel de logs CV (1458956197796515979)
            cv_log_channel = bot.get_channel(1458956197796515979)
            if cv_log_channel:
                await cv_log_channel.send(embed=embed)
                
                # Chercher et copier le CV original
                try:
                    cv_channel = bot.get_channel(1539697901540745317)
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
                        title=f"âœ… {member.display_name}",
                        description=f"AcceptÃ© par {interaction.user.mention}",
                        color=EMS_RED
                    )
                    avatar_embed.set_image(url=member.avatar.url)
                    avatar_embed.set_footer(text="ðŸš‘ EMS System")
                    await image_channel.send(embed=avatar_embed)
                except:
                    pass
        except:
            pass
        
        await interaction.followup.send(f"âœ… **{member.display_name}** acceptÃ© !", ephemeral=True)
        
        # Supprimer le message
        try:
            await asyncio.sleep(3)
            if self.message:
                await self.message.delete()
        except:
            pass

    @discord.ui.button(label="âŒ Refuser", style=discord.ButtonStyle.red, custom_id="refuse_formulaire_cv")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("âŒ Permission refusÃ©e", ephemeral=True)
            return
        
        # DÃ©sactiver les boutons
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
                "âŒ **Candidature RefusÃ©e**\n\n"
                "Nous regrettons de vous informer que votre candidature n'a pas Ã©tÃ© retenue.\n\n"
                "Vous pourrez re-postuler dans **1 semaine**.\n\n"
                "Cordialement,\n**La Direction des EMS** ðŸš‘"
            )
        except:
            pass

        # â”€â”€ BLACKLIST CV automatique sur refus â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        try:
            bl = load_blacklist_cv()
            bl[str(self.target_user.id)] = {
                "date": datetime.utcnow().isoformat(),
                "raison": "Candidature refusÃ©e par la direction",
                "blacklisted_by": str(interaction.user.id),
            }
            save_blacklist_cv(bl)
        except Exception as _bl_err:
            print(f"Erreur blacklist CV refus: {_bl_err}")
        # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

        # Log
        try:
            # Envoyer dans le channel de logs CV (1458956197796515979)
            cv_log_channel = bot.get_channel(1458956197796515979)
            if cv_log_channel:
                embed = discord.Embed(
                    title="âŒ CANDIDATURE REFUSÃ‰E + BLACKLIST",
                    description=f"**Candidat :** {self.target_user.mention}\n**Validateur :** {interaction.user.mention}\nðŸš« BlacklistÃ© 1 semaine automatiquement.",
                    color=EMS_DARK_RED
                )
                embed.set_footer(text="ðŸš‘ EMS System")
                await cv_log_channel.send(embed=embed)
        except:
            pass

        await interaction.followup.send("âœ… CV refusÃ© â€” candidat blacklistÃ© 1 semaine automatiquement.", ephemeral=True)
        
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

    @discord.ui.button(label="ðŸ“ DÃ©poser ma candidature", style=discord.ButtonStyle.primary, custom_id="start_formulaire_cv")
    async def start_formulaire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ðŸ“‹ VÃ©rification en cours...", ephemeral=True)

        guild = interaction.guild
        user_id = interaction.user.id

        # â”€â”€ VÃ‰RIFICATION BLACKLIST CV â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        bl_entry = is_blacklisted_cv(user_id)
        if bl_entry:
            blacklisted_at = datetime.fromisoformat(bl_entry["date"])
            unlock_at = blacklisted_at + timedelta(weeks=1)
            remaining = unlock_at - datetime.utcnow()
            days_left = remaining.days
            hours_left = remaining.seconds // 3600
            raison = bl_entry.get("raison", "Non prÃ©cisÃ©e")
            await interaction.followup.send(
                f"ðŸš« **Candidature refusÃ©e â€” Blacklist CV**\n\n"
                f"Votre candidature a Ã©tÃ© **refusÃ©e ou votre contrat a Ã©tÃ© rÃ©siliÃ©** et vous Ãªtes actuellement "
                f"sur liste noire.\n\n"
                f"**Raison :** {raison}\n"
                f"**DÃ©blocage dans :** {days_left}j {hours_left}h\n\n"
                f"Vous pourrez re-postuler aprÃ¨s ce dÃ©lai.",
                ephemeral=True
            )
            return
        # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

        # VÃ©rifier si existe
        for ch in guild.text_channels:
            if ch.name == f"candidature-{user_id}":
                await interaction.followup.send(f"âŒ Vous avez dÃ©jÃ  un dossier : {ch.mention}", ephemeral=True)
                return
        
        # CrÃ©er channel
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
            await interaction.followup.send("âŒ Erreur lors de la crÃ©ation du channel", ephemeral=True)
            return
        
        await interaction.followup.send(f"âœ… Votre dossier : {channel.mention}", ephemeral=True)
        
        # Message de bienvenue
        welcome = discord.Embed(
            title="ðŸš‘ FORMULAIRE DE CANDIDATURE EMS",
            description=(
                f"Bienvenue **{interaction.user.mention}** ! ðŸ‘‹\n\n"
                f"**ðŸ“‹ Informations :**\n"
                f"â€¢ {len(QUESTIONS)} questions\n"
                f"â€¢ 10 minutes par question\n"
                f"â€¢ Documents requis Ã  la fin\n\n"
                f"**Bonne chance ! ðŸ’ª**"
            ),
            color=EMS_RED
        )
        welcome.set_footer(text="ðŸš‘ EMS System")
        await channel.send(embed=welcome)
        await asyncio.sleep(2)
        
        # Questions
        answers = []
        user_fullname = None
        
        for i, question in enumerate(QUESTIONS, 1):
            q_embed = discord.Embed(
                title=f"â“ QUESTION {i}/{len(QUESTIONS)}",
                description=question,
                color=EMS_RED
            )
            q_embed.add_field(name="â±ï¸ Temps", value="10 minutes", inline=False)
            q_embed.set_footer(text="ðŸš‘ EMS System")
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
                    title="â±ï¸ TEMPS Ã‰COULÃ‰ - FERMETURE AUTOMATIQUE",
                    description=(
                        "âŒ **Aucune rÃ©ponse reÃ§ue dans les 10 minutes.**\n\n"
                        "Votre dossier de candidature va Ãªtre **fermÃ© automatiquement**.\n\n"
                        "Si vous souhaitez postuler Ã  nouveau, cliquez sur le bouton de candidature.\n\n"
                        "ðŸš‘ **Fermeture dans 5 secondes...**"
                    ),
                    color=EMS_DARK_RED
                )
                timeout_embed.set_footer(text="ðŸš‘ EMS System | Session expirÃ©e")
                await channel.send(embed=timeout_embed)
                await asyncio.sleep(5)
                try:
                    await channel.delete()
                except:
                    pass
                return
        
        # Documents
        docs_embed = discord.Embed(
            title="ðŸ“Ž DOCUMENTS REQUIS",
            description=(
                "Merci pour vos rÃ©ponses ! ðŸŽ‰\n\n"
                "**Il manque :**\n"
                "ðŸ†” Carte d'identitÃ©\n"
                "ðŸš— Permis de conduire\n\n"
                "Envoyez-les maintenant !"
            ),
            color=EMS_RED
        )
        docs_embed.set_footer(text="ðŸš‘ EMS System")
        await channel.send(embed=docs_embed)
        
        attachments = []
        photos_b64 = []
        
        def check_doc(m):
            return m.author == interaction.user and m.channel == channel
        
        try:
            msg = await bot.wait_for('message', check=check_doc, timeout=None)
            
            if msg.attachments:
                for att in msg.attachments:
                    attachments.append(att.url)
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(att.url) as resp:
                                if resp.status == 200:
                                    data = await resp.read()
                                    if len(data) < 5 * 1024 * 1024:
                                        ctype = att.content_type or 'image/png'
                                        b64 = base64.b64encode(data).decode('utf-8')
                                        photos_b64.append(f"data:{ctype};base64,{b64}")
                    except Exception:
                        pass
            
            confirm_embed = discord.Embed(
                title="âœ… CANDIDATURE COMPLÃˆTE",
                description=(
                    "ðŸŽ‰ Candidature reÃ§ue !\n\n"
                    f"**Documents :** {len(attachments)}\n\n"
                    "La direction va examiner votre dossier.\n"
                    "Vous recevrez une rÃ©ponse en DM.\n\n"
                    "â±ï¸ Ce channel se fermera dans **2 minutes**\n\n"
                    "Merci ! ðŸš‘"
                ),
                color=EMS_RED
            )
            confirm_embed.set_footer(text="ðŸš‘ EMS System")
            await channel.send(embed=confirm_embed)
            
            # DM candidat
            try:
                await interaction.user.send(
                    "ðŸš‘ **Candidature envoyÃ©e** ðŸš‘\n\n"
                    "Nous avons bien reÃ§u votre candidature.\n\n"
                    "RÃ©ponse prochainement.\n\n"
                    "Merci ! ðŸ‘¨â€âš•ï¸"
                )
            except:
                pass
            
            # Envoyer au channel CV (pendant que le timer dÃ©marre)
            cv_channel = bot.get_channel(1539697901540745317)
            if cv_channel:
                full_text = "\n\n".join(answers)
                cv_embed = discord.Embed(
                    title=f"ðŸ“‹ CANDIDATURE - {user_fullname if user_fullname else interaction.user.name}",
                    description=full_text[:2000],
                    color=EMS_RED
                )
                
                if attachments:
                    cv_embed.add_field(name="ðŸ“Ž Documents", value="\n".join([f"[Doc {i}]({url})" for i, url in enumerate(attachments, 1)]), inline=False)
                
                cv_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
                cv_embed.set_footer(text=f"ðŸš‘ EMS System | ID: {user_id}")
                
                view = FormulaireCVValidation(interaction.user)
                
                # Ping direction
                direction_role = guild.get_role(config.get("ROLE_DIRECTION_ID"))
                ping_content = direction_role.mention if direction_role else None
                
                try:
                    msg = await cv_channel.send(content=ping_content, embed=cv_embed, view=view)
                    view.message = msg
                    cv_track_add(interaction.user, 'pending', photos_b64=photos_b64, cv_text=full_text)
                    print(f"âœ… FormulaireCVButton: CV envoyÃ© dans {cv_channel.name} pour {interaction.user.name}")
                except Exception as e:
                    print(f"âŒ FormulaireCVButton: Erreur envoi CV: {e}")
            else:
                print(f"âŒ FormulaireCVButton: Channel CV non trouvÃ© (ID: 1539697901540745317)")
            
            # Fermer le channel aprÃ¨s 2 minutes
            await asyncio.sleep(120)
            try:
                await channel.delete()
            except:
                pass
        except:
            # En cas d'erreur, fermer quand mÃªme aprÃ¨s 2 min
            await asyncio.sleep(120)
            try:
                await channel.delete()
            except:
                pass

@bot.tree.command(name="setup_cv", description="Affiche le bouton de dÃ©pÃ´t de CV")
@app_commands.checks.has_permissions(administrator=True)
async def setup_cv(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="ðŸš‘ RECRUTEMENT EMS",
        description=(
            "**Rejoignez notre Ã©quipe !**\n\n"
            "Cliquez sur le bouton ci-dessous pour dÃ©poser votre candidature.\n\n"
            "**ðŸ“‹ Processus de recrutement :**\n"
            "1ï¸âƒ£ Cliquez sur le bouton\n"
            "2ï¸âƒ£ RÃ©pondez aux 13 questions\n"
            "3ï¸âƒ£ Envoyez vos documents (ID, permis)\n"
            "4ï¸âƒ£ Attendez la validation de la direction\n\n"
            "**Bonne chance ! ðŸš‘ðŸ’ª**"
        ),
        color=EMS_RED
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    embed.set_footer(text="ðŸš‘ EMS Management System")
    
    view = CVButton()
    
    try:
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("âœ… Bouton de CV postÃ© !", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"âŒ Erreur: {e}", ephemeral=True)

@bot.tree.command(name="formulairecv", description="Affiche le nouveau formulaire de candidature")
@app_commands.checks.has_permissions(administrator=True)
async def formulairecv(interaction: discord.Interaction):
    # Defer immÃ©diatement pour Ã©viter le timeout
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="ðŸš‘ RECRUTEMENT EMS",
        description=(
            "**Rejoignez notre Ã©quipe !**\n\n"
            "Cliquez sur le bouton pour dÃ©poser votre candidature.\n\n"
            "**ðŸ“‹ Processus :**\n"
            "1ï¸âƒ£ Cliquez sur le bouton\n"
            "2ï¸âƒ£ RÃ©pondez aux 13 questions\n"
            "3ï¸âƒ£ Envoyez vos documents\n"
            "4ï¸âƒ£ Attendez la validation\n\n"
            "**Bonne chance ! ðŸš‘ðŸ’ª**"
        ),
        color=EMS_RED
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    embed.set_footer(text="ðŸš‘ EMS System")
    
    view = FormulaireCVButton()
    
    try:
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("âœ… Formulaire postÃ© !", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"âŒ Erreur: {e}", ephemeral=True)

# --- SYSTÃˆME DE RESET MEMBRE ---
class ResetMemberButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ðŸ”„ RÃ©initialiser mon compte", style=discord.ButtonStyle.danger, custom_id="reset_member")
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
            
            # RÃ©cupÃ©rer tous les rÃ´les sauf @everyone et le rÃ´le de base
            roles_to_remove = [role for role in member.roles if role.id != guild.default_role.id and role.id != ROLE_BASE_ID]
            
            # Retirer tous les rÃ´les sauf le rÃ´le de base
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="RÃ©initialisation du compte")
            
            # Confirmation
            embed = discord.Embed(
                title="âœ… COMPTE RÃ‰INITIALISÃ‰",
                description=(
                    "Votre compte a Ã©tÃ© rÃ©initialisÃ© avec succÃ¨s !\n\n"
                    "**Actions effectuÃ©es :**\n"
                    "âœ… Pseudo rÃ©initialisÃ©\n"
                    f"âœ… {len(roles_to_remove)} rÃ´le(s) retirÃ©(s)\n\n"
                    "Vous pouvez maintenant repartir de zÃ©ro ! ðŸš€"
                ),
                color=EMS_RED
            )
            embed.set_footer(text="ðŸš‘ EMS System")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Log
            log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
            if log_channel:
                log_embed = discord.Embed(
                    title="ðŸ”„ RÃ‰INITIALISATION MEMBRE",
                    description=f"**Membre :** {member.mention}\n**RÃ´les retirÃ©s :** {len(roles_to_remove)}",
                    color=EMS_RED
                )
                log_embed.set_footer(text="ðŸš‘ EMS System")
                await log_channel.send(embed=log_embed)
                
        except Exception as e:
            error_embed = discord.Embed(
                title="âŒ ERREUR",
                description=f"Impossible de rÃ©initialiser le compte :\n```{e}```",
                color=EMS_DARK_RED
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

@bot.tree.command(name="setup_reset", description="Affiche le bouton de rÃ©initialisation")
@app_commands.checks.has_permissions(administrator=True)
async def setup_reset(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="ðŸ”„ RÃ‰INITIALISATION DU COMPTE",
        description=(
            "**Attention : Action irrÃ©versible !**\n\n"
            "En cliquant sur le bouton ci-dessous, vous allez :\n\n"
            "ðŸ”¸ **RÃ©initialiser votre pseudo**\n"
            "ðŸ”¸ **Perdre tous vos rÃ´les** (sauf le rÃ´le de base)\n\n"
            "âš ï¸ **Cette action est dÃ©finitive !**\n\n"
            "Utilisez cette option uniquement si vous souhaitez repartir de zÃ©ro."
        ),
        color=EMS_DARK_RED
    )
    embed.set_footer(text="ðŸš‘ EMS System | RÃ©flÃ©chissez bien avant de cliquer")
    
    view = ResetMemberButton()
    
    try:
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("âœ… Bouton de rÃ©initialisation postÃ© !", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"âŒ Erreur : {e}", ephemeral=True)

# --- SYSTÃˆME DE GIVEAWAY ---
@bot.tree.command(name="giveaway", description="CrÃ©er un giveaway")
@app_commands.describe(
    montant="Montant de la rÃ©compense en $",
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
            await interaction.followup.send("âŒ Format invalide. Utilisez JJ/MM/AAAA pour la date et HH:MM pour l'heure", ephemeral=True)
            return
        
        day, month, year = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
        hour, minute = int(heure_parts[0]), int(heure_parts[1])
        
        end_time = datetime(year, month, day, hour, minute)
        
        # VÃ©rifier que la date est dans le futur
        if end_time <= now_paris():
            await interaction.followup.send("âŒ La date de fin doit Ãªtre dans le futur", ephemeral=True)
            return
        
        # CrÃ©er l'embed du giveaway
        timestamp = int(end_time.timestamp())
        
        embed = discord.Embed(
            title="ðŸŽ‰ GIVEAWAY ðŸŽ‰",
            description=(
                f"**ðŸ’° RÃ©compense : {montant:,}$**\n\n"
                f"**ðŸ† Nombre de gagnants : {gagnants}**\n\n"
                f"**ðŸ“… Fin du giveaway : <t:{timestamp}:F>**\n"
                f"**â° Dans : <t:{timestamp}:R>**\n\n"
                f"**Comment participer ?**\n"
                f"RÃ©agissez avec ðŸŽ‰ pour participer !\n\n"
                f"Bonne chance Ã  tous ! ðŸ€"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="ðŸŽ‰ Giveaway System")
        
        # Ping le rÃ´le
        role = interaction.guild.get_role(GIVEAWAY_PING_ROLE_ID)
        ping_content = role.mention if role else None
        
        # Envoyer le message
        msg = await interaction.channel.send(content=ping_content, embed=embed)
        
        # Ajouter la rÃ©action
        await msg.add_reaction("ðŸŽ‰")
        
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
        
        await interaction.followup.send("âœ… Giveaway crÃ©Ã© avec succÃ¨s !", ephemeral=True)
        
    except ValueError as e:
        await interaction.followup.send(f"âŒ Erreur de format : {e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"âŒ Erreur : {e}", ephemeral=True)

# TÃ¢che pour vÃ©rifier les giveaways actifs
@tasks.loop(seconds=30)
async def check_giveaways():
    """VÃ©rifie les giveaways actifs et termine ceux qui sont expirÃ©s"""
    try:
        giveaways = load_giveaways()
        if not giveaways:
            return  # Aucun giveaway actif â†’ sortie rapide
        now = now_paris()
        
        for msg_id, data in list(giveaways.items()):
            if data.get("ended", False):
                continue
            
            end_time = datetime.fromisoformat(data["end_time"])
            
            if now >= end_time:
                # Le giveaway est terminÃ©
                channel = bot.get_channel(data["channel_id"])
                if not channel:
                    continue
                
                try:
                    message = await channel.fetch_message(data["message_id"])
                except:
                    continue
                
                # RÃ©cupÃ©rer les participants (ceux qui ont rÃ©agi avec ðŸŽ‰)
                participants = []
                for reaction in message.reactions:
                    if str(reaction.emoji) == "ðŸŽ‰":
                        async for user in reaction.users():
                            if not user.bot:
                                participants.append(user)
                        break
                
                if len(participants) == 0:
                    # Aucun participant
                    embed = discord.Embed(
                        title="ðŸŽ‰ GIVEAWAY TERMINÃ‰",
                        description=(
                            f"**ðŸ’° RÃ©compense : {data['montant']:,}$**\n\n"
                            f"âŒ **Aucun participant !**\n\n"
                            f"Le giveaway n'a pas pu Ãªtre complÃ©tÃ©."
                        ),
                        color=EMS_DARK_RED
                    )
                    await message.edit(embed=embed)
                else:
                    # SÃ©lectionner les gagnants
                    import random
                    nb_gagnants = min(data["gagnants"], len(participants))
                    winners = random.sample(participants, nb_gagnants)
                    
                    # CrÃ©er l'embed des rÃ©sultats
                    winners_mentions = "\n".join([f"ðŸ† {winner.mention}" for winner in winners])
                    
                    embed = discord.Embed(
                        title="ðŸŽ‰ GIVEAWAY TERMINÃ‰ !",
                        description=(
                            f"**ðŸ’° RÃ©compense : {data['montant']:,}$**\n\n"
                            f"**ðŸ† Gagnant(s) :**\n{winners_mentions}\n\n"
                            f"**FÃ©licitations ! ðŸŽŠ**"
                        ),
                        color=discord.Color.green()
                    )
                    embed.set_footer(text="ðŸŽ‰ Giveaway System")
                    await message.edit(embed=embed)
                    
                    # Annoncer les gagnants dans le channel
                    winners_pings = " ".join([winner.mention for winner in winners])
                    await channel.send(f"ðŸŽ‰ **FÃ©licitations aux gagnants du giveaway !** ðŸŽ‰\n\n{winners_pings}\n\nðŸ’° Vous avez gagnÃ© **{data['montant']:,}$** !")
                    
                    # Envoyer un MP Ã  l'hÃ´te
                    host = bot.get_user(data["host_id"])
                    if host:
                        winners_list = "\n".join([f"â€¢ {winner.name} ({winner.id})" for winner in winners])
                        try:
                            await host.send(
                                f"ðŸŽ‰ **Giveaway terminÃ© !**\n\n"
                                f"**Montant :** {data['montant']:,}$\n"
                                f"**Channel :** {channel.mention}\n\n"
                                f"**Gagnants ({nb_gagnants}) :**\n{winners_list}\n\n"
                                f"Les gagnants ont Ã©tÃ© annoncÃ©s dans le channel !"
                            )
                        except:
                            pass
                
                # Marquer comme terminÃ©
                giveaways[msg_id]["ended"] = True
                save_giveaways(giveaways)
        
    except Exception as e:
        print(f"Erreur check_giveaways: {e}")

@check_giveaways.before_loop
async def before_check_giveaways():
    await bot.wait_until_ready()

# --- SYSTÃˆME DE DEMANDE DE RÃ”LE ---
class RoleRequestButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Demander un rÃ´le", style=discord.ButtonStyle.primary, emoji="ðŸ‘®", custom_id="request_role")
    async def request_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ðŸ“‹ Traitement de votre demande...", ephemeral=True)
        
        guild = interaction.guild
        user_id = interaction.user.id
        
        # CrÃ©er un channel privÃ© pour la demande
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
                topic=f"Demande de rÃ´le - {interaction.user.name}"
            )
        except Exception as e:
            await interaction.followup.send(f"âŒ Erreur lors de la crÃ©ation du ticket : {e}", ephemeral=True)
            return
        
        await interaction.followup.send(f"âœ… Ticket crÃ©Ã© : {channel.mention}", ephemeral=True)
        
        # Message de bienvenue
        welcome = discord.Embed(
            title="ðŸ‘® DEMANDE DE RÃ”LE",
            description=f"Bienvenue **{interaction.user.mention}** !\n\nVeuillez rÃ©pondre aux questions suivantes pour obtenir votre rÃ´le.",
            color=discord.Color.blue()
        )
        welcome.set_footer(text="ðŸŽ¯ SystÃ¨me de demande de rÃ´le")
        await channel.send(embed=welcome)
        await asyncio.sleep(1)
        
        # Question 1 : Organisation
        q1 = discord.Embed(
            title="â“ QUESTION 1",
            description="**Quelle organisation rejoignez-vous ?**\n\nRÃ©pondez par :\nâ€¢ `LSPD`\nâ€¢ `BCSO`\nâ€¢ `MARSHALL`\nâ€¢ `TAXI`\nâ€¢ `BURGERSHOT`",
            color=discord.Color.blue()
        )
        q1.set_footer(text="ðŸŽ¯ SystÃ¨me de demande de rÃ´le")
        await channel.send(embed=q1)
        
        def check(m):
            return m.author == interaction.user and m.channel == channel
        
        # Attendre rÃ©ponse organisation
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
                    title="âŒ ERREUR",
                    description="Organisation invalide. Le ticket va Ãªtre fermÃ©.",
                    color=discord.Color.red()
                )
                await channel.send(embed=error_msg)
                await asyncio.sleep(3)
                await channel.delete()
                return
            
            # Ajouter le rÃ´le de l'organisation
            role = guild.get_role(role_id)
            if role:
                await interaction.user.add_roles(role)
            
            # Confirmation
            confirm_org = discord.Embed(
                title="âœ… ORGANISATION CONFIRMÃ‰E",
                description=f"Vous avez rejoint : **{organization}**\nRÃ´le ajoutÃ© avec succÃ¨s !",
                color=discord.Color.green()
            )
            await channel.send(embed=confirm_org)
            await asyncio.sleep(1)
            
        except asyncio.TimeoutError:
            timeout_msg = discord.Embed(
                title="â±ï¸ TEMPS Ã‰COULÃ‰",
                description="Vous n'avez pas rÃ©pondu Ã  temps. Le ticket va Ãªtre fermÃ©.",
                color=discord.Color.red()
            )
            await channel.send(embed=timeout_msg)
            await asyncio.sleep(3)
            await channel.delete()
            return
        
        # Question 2 : PrÃ©nom + Nom
        question_num = 2
        q2 = discord.Embed(
            title=f"â“ QUESTION {question_num}",
            description="**Quel est votre prÃ©nom et nom ?**\n\nFormat : `PrÃ©nom Nom`\nExemple : `Paul Fera`",
            color=discord.Color.blue()
        )
        q2.set_footer(text="ðŸŽ¯ SystÃ¨me de demande de rÃ´le")
        await channel.send(embed=q2)
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=300)
            full_name = msg.content.strip()
        except asyncio.TimeoutError:
            timeout_msg = discord.Embed(
                title="â±ï¸ TEMPS Ã‰COULÃ‰",
                description="Vous n'avez pas rÃ©pondu Ã  temps. Le ticket va Ãªtre fermÃ©.",
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
                title=f"â“ QUESTION {question_num}",
                description="**Quel est votre matricule ?**\n\nFormat : `02`, `15`, etc.",
                color=discord.Color.blue()
            )
            q3.set_footer(text="ðŸŽ¯ SystÃ¨me de demande de rÃ´le")
            await channel.send(embed=q3)
            
            try:
                msg = await bot.wait_for('message', check=check, timeout=300)
                matricule = msg.content.strip()
            except asyncio.TimeoutError:
                timeout_msg = discord.Embed(
                    title="â±ï¸ TEMPS Ã‰COULÃ‰",
                    description="Vous n'avez pas rÃ©pondu Ã  temps. Le ticket va Ãªtre fermÃ©.",
                    color=discord.Color.red()
                )
                await channel.send(embed=timeout_msg)
                await asyncio.sleep(3)
                await channel.delete()
                return
        
        # Question 4 : Test d'aptitude
        question_num = 3 if (is_taxi or is_burgershot) else 4
        q4 = discord.Embed(
            title=f"â“ QUESTION {question_num}",
            description="**Avez-vous le test d'aptitude ?**\n\nRÃ©pondez par :\nâ€¢ `oui`\nâ€¢ `non`",
            color=discord.Color.blue()
        )
        q4.set_footer(text="ðŸŽ¯ SystÃ¨me de demande de rÃ´le")
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
                    title="âŒ ERREUR",
                    description="RÃ©ponse invalide. Le ticket va Ãªtre fermÃ©.",
                    color=discord.Color.red()
                )
                await channel.send(embed=error_msg)
                await asyncio.sleep(3)
                await channel.delete()
                return
        except asyncio.TimeoutError:
            timeout_msg = discord.Embed(
                title="â±ï¸ TEMPS Ã‰COULÃ‰",
                description="Vous n'avez pas rÃ©pondu Ã  temps. Le ticket va Ãªtre fermÃ©.",
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
        
        # 2. Ajouter le rÃ´le si pas de test
        if not has_test:
            no_test_role = guild.get_role(ROLE_NO_TEST_ID)
            if no_test_role:
                try:
                    await interaction.user.add_roles(no_test_role)
                except Exception as e:
                    print(f"Erreur ajout rÃ´le sans test: {e}")
        
        # Message de confirmation finale
        if is_taxi:
            final_msg = discord.Embed(
                title="âœ… DEMANDE COMPLÃ‰TÃ‰E",
                description=(
                    f"**Votre profil a Ã©tÃ© configurÃ© avec succÃ¨s !**\n\n"
                    f"**Organisation :** {organization}\n"
                    f"**Pseudo :** `{new_nickname}`\n"
                    f"**Test d'aptitude :** {'âœ… Oui' if has_test else 'âŒ Non'}\n\n"
                    f"Bienvenue dans l'Ã©quipe Taxi ! ðŸš•"
                ),
                color=discord.Color.green()
            )
        elif is_burgershot:
            final_msg = discord.Embed(
                title="âœ… DEMANDE COMPLÃ‰TÃ‰E",
                description=(
                    f"**Votre profil a Ã©tÃ© configurÃ© avec succÃ¨s !**\n\n"
                    f"**Organisation :** {organization}\n"
                    f"**Pseudo :** `{new_nickname}`\n"
                    f"**Test d'aptitude :** {'âœ… Oui' if has_test else 'âŒ Non'}\n\n"
                    f"Bienvenue chez BurgerShot ! ðŸ”"
                ),
                color=discord.Color.green()
            )
        else:
            final_msg = discord.Embed(
                title="âœ… DEMANDE COMPLÃ‰TÃ‰E",
                description=(
                    f"**Votre profil a Ã©tÃ© configurÃ© avec succÃ¨s !**\n\n"
                    f"**Organisation :** {organization}\n"
                    f"**Pseudo :** `{new_nickname}`\n"
                    f"**Test d'aptitude :** {'âœ… Oui' if has_test else 'âŒ Non'}\n\n"
                    f"Bienvenue dans l'Ã©quipe ! ðŸŽ‰"
                ),
                color=discord.Color.green()
            )
        final_msg.set_footer(text="ðŸŽ¯ SystÃ¨me de demande de rÃ´le")
        await channel.send(embed=final_msg)
        
        # Fermer le ticket aprÃ¨s 10 secondes
        await asyncio.sleep(10)
        try:
            await channel.delete()
        except:
            pass

@bot.tree.command(name="setup_role_request", description="Affiche le bouton de demande de rÃ´le")
@app_commands.checks.has_permissions(administrator=True)
async def setup_role_request(interaction: discord.Interaction):
    embed = discord.Embed(
        title="ðŸ‘® DEMANDE DE RÃ”LE",
        description=(
            "**Obtenez votre rÃ´le d'organisation !**\n\n"
            "Cliquez sur le bouton ci-dessous pour faire votre demande.\n\n"
            "**ðŸ“‹ Informations requises :**\n"
            "â€¢ Organisation (LSPD/BCSO/MARSHALL/TAXI/BURGERSHOT)\n"
            "â€¢ PrÃ©nom et nom\n"
            "â€¢ Matricule (sauf Taxi/BurgerShot)\n"
            "â€¢ Test d'aptitude (oui/non)\n\n"
            "**Le systÃ¨me configurera automatiquement votre profil !**"
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text="ðŸŽ¯ SystÃ¨me de demande de rÃ´le")
    await interaction.channel.send(embed=embed, view=RoleRequestButton())
    await interaction.response.send_message("âœ… Message de demande de rÃ´le postÃ© !", ephemeral=True)

# --- SYSTÃˆME DE TICKETS DE RENDEZ-VOUS ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, emoji="ðŸ”’", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ðŸ”’ Fermeture du ticket...", ephemeral=True)
        
        close_msg = discord.Embed(
            title="ðŸ”’ TICKET FERMÃ‰",
            description=f"Ce ticket a Ã©tÃ© fermÃ© par {interaction.user.mention}.\nLe channel sera supprimÃ© dans 5 secondes.",
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

    @discord.ui.button(label="Prendre rendez-vous", style=discord.ButtonStyle.green, emoji="ðŸ“…", custom_id="appointment_ticket")
    async def create_appointment(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ðŸ“… CrÃ©ation de votre ticket...", ephemeral=True)
        
        guild = interaction.guild
        user_id = interaction.user.id
        
        # VÃ©rifier si l'utilisateur a dÃ©jÃ  un ticket ouvert
        for channel in guild.text_channels:
            if channel.name == f"rdv-{user_id}":
                await interaction.followup.send(f"âŒ Vous avez dÃ©jÃ  un ticket ouvert : {channel.mention}", ephemeral=True)
                return
        
        # CrÃ©er un channel pour le rendez-vous
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
            await interaction.followup.send(f"âŒ Erreur lors de la crÃ©ation du ticket : {e}", ephemeral=True)
            return
        
        await interaction.followup.send(f"âœ… Ticket crÃ©Ã© : {channel.mention}", ephemeral=True)
        
        # Message de bienvenue avec bouton de fermeture
        welcome = discord.Embed(
            title="ðŸ“… PRISE DE RENDEZ-VOUS",
            description=(
                f"Bienvenue **{interaction.user.mention}** !\n\n"
                f"Merci d'avoir ouvert un ticket de rendez-vous.\n"
                f"Un membre de l'Ã©quipe vous rÃ©pondra sous peu.\n\n"
                f"**En attendant, vous pouvez :**\n"
                f"â€¢ Expliquer la raison de votre demande\n"
                f"â€¢ Indiquer vos disponibilitÃ©s\n"
                f"â€¢ Poser vos questions\n\n"
                f"Pour fermer ce ticket, cliquez sur le bouton ci-dessous."
            ),
            color=discord.Color.green()
        )
        welcome.set_footer(text="ðŸ“… SystÃ¨me de tickets")
        await channel.send(embed=welcome, view=CloseTicketView())

@bot.tree.command(name="setup_appointment", description="Affiche le bouton de prise de rendez-vous")
@app_commands.checks.has_permissions(administrator=True)
async def setup_appointment(interaction: discord.Interaction):
    embed = discord.Embed(
        title="ðŸ“… PRISE DE RENDEZ-VOUS",
        description=(
            "**Besoin d'un rendez-vous ?**\n\n"
            "Cliquez sur le bouton ci-dessous pour ouvrir un ticket.\n\n"
            "**ðŸ“‹ Un membre de l'Ã©quipe vous rÃ©pondra rapidement pour :**\n"
            "â€¢ Fixer une date et heure\n"
            "â€¢ RÃ©pondre Ã  vos questions\n"
            "â€¢ Organiser votre rendez-vous\n\n"
            "**N'hÃ©sitez pas Ã  nous contacter ! ðŸ“ž**"
        ),
        color=discord.Color.green()
    )
    embed.set_footer(text="ðŸ“… SystÃ¨me de tickets")
    await interaction.channel.send(embed=embed, view=AppointmentButton())
    await interaction.response.send_message("âœ… Message de prise de rendez-vous postÃ© !", ephemeral=True)

@bot.event
async def on_error(event, *args, **kwargs):
    """Gestionnaire d'erreurs global amÃ©liorÃ©"""
    import traceback
    ts = now_paris().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] âŒ Erreur dans l'Ã©vÃ©nement '{event}':", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)

@bot.event
async def on_disconnect():
    """Logge les dÃ©connexions du bot"""
    ts = now_paris().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] âš ï¸ Bot dÃ©connectÃ© de Discord")

@bot.event
async def on_resumed():
    """Logge les reconnexions et alerte en cas de reconnexions excessives"""
    global reconnect_count, reconnect_timestamps
    ts = now_paris().strftime('%Y-%m-%d %H:%M:%S')
    now = now_paris()
    reconnect_count += 1
    reconnect_timestamps.append(now)
    # Purger les timestamps hors de la fenÃªtre glissante
    reconnect_timestamps = [t for t in reconnect_timestamps if (now - t).total_seconds() < RECONNECT_WINDOW_SECONDS]
    recent_count = len(reconnect_timestamps)
    print(f"[{ts}] ðŸ”„ Session reprise (reconnexion #{reconnect_count}, {recent_count} en 1h)")
    if recent_count >= RECONNECT_ALERT_THRESHOLD:
        print(f"[{ts}] ðŸš¨ ALERTE: {recent_count} reconnexions en moins d'1 heure - problÃ¨me de stabilitÃ© dÃ©tectÃ©")

# (2e on_message + 1er on_ready supprimÃ©s - fusionnÃ©s dans les handlers principaux)

# --- TÃ‚CHE AUTOMATISÃ‰E HEBDOMADAIRE TAXI ---
@tasks.loop(hours=1)
async def weekly_taxi_announcement():
    """VÃ©rifie si c'est samedi 19h et envoie l'annonce hebdomadaire"""
    now = now_paris()
    
    # VÃ©rifier si c'est samedi (weekday() == 5) et qu'il est 19h
    if now.weekday() == 5 and now.hour == 19:
        try:
            await send_weekly_taxi_announcement()
        except Exception as e:
            print(f"Erreur annonce taxi hebdo: {e}")

@weekly_taxi_announcement.before_loop
async def before_weekly_announcement():
    await bot.wait_until_ready()

# (1er auto_backup_stats supprimÃ© - doublon du handler principal)

async def send_weekly_taxi_announcement():
    """Envoie l'annonce hebdomadaire SIMPLE et rÃ©initialise les compteurs"""
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
    
    # Message SIMPLE et DIRECT
    message = f"ðŸš• **RAPPORT TAXI - Nouvelle Semaine**\n\n"
    message += f"âœ… EmployÃ©s acceptÃ©s: **{count}**\n"
    message += f"ðŸ’° Revenus: **{revenus:,.0f}$**\n\n"
    message += f"Nouvelle semaine commence maintenant! ðŸŽ¯"
    
    # Envoyer le message simple
    try:
        await taxi_channel.send(message)
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'annonce taxi : {e}")
    
    # RÃ©initialiser les stats pour la nouvelle semaine
    reset_taxi_week()
    print(f"âœ… Annonce hebdomadaire taxi envoyÃ©e")


# --- GESTION DES CANAUX UTILISATEURS ---
def get_clean_name(member):
    """RÃ©cupÃ¨re le nom sans le tag entre crochets ni la matricule"""
    display_name = member.display_name
    if ']' in display_name:
        try:
            after_bracket = display_name.split(']')[1].strip()
            # Retirer la matricule (2 chiffres en dÃ©but)
            after_bracket = _re.sub(r'^\d{2}\s*', '', after_bracket).strip()
            return after_bracket
        except IndexError:
            return display_name
    return display_name

# --- RÃ‰CUPÃ‰RATION DES STATS DEPUIS LES LOGS ---
async def sync_stats_from_logs():
    """RÃ©cupÃ¨re les stats depuis le channel de logs pour Ã©viter la perte de donnÃ©es au redÃ©marrage"""
    try:
        LOGS_SYNC_CHANNEL_ID = 1458464678542970983
        log_channel = bot.get_channel(LOGS_SYNC_CHANNEL_ID)
        
        if not log_channel:
            print(f"âŒ Channel de logs introuvable (ID: {LOGS_SYNC_CHANNEL_ID})")
            return
        
        print("ðŸ”„ Synchronisation des stats depuis les logs...")
        
        # Dictionnaire pour stocker les stats rÃ©cupÃ©rÃ©es
        recovered_stats = {}
        
        # Lire les 1000 derniers messages du channel (limite Discord)
        async for message in log_channel.history(limit=1000):
            # Format attendu: "âœ… **employee_key** | X rÃ©as"
            if message.content.startswith("âœ… **") and " rÃ©as" in message.content:
                try:
                    # Extraire l'employÃ© et le nombre de rÃ©as
                    parts = message.content.split("**")
                    if len(parts) >= 3:
                        employee_key = parts[1].strip()
                        
                        # Extraire le nombre de rÃ©as
                        rea_part = message.content.split("|")[1].strip()
                        rea_count = int(rea_part.split()[0])
                        
                        # Garder la valeur la plus rÃ©cente (plus haute)
                        if employee_key not in recovered_stats or rea_count > recovered_stats[employee_key]:
                            recovered_stats[employee_key] = rea_count
                except Exception as e:
                    continue
        
        if recovered_stats:
            # Sauvegarder les stats rÃ©cupÃ©rÃ©es
            save_stats(recovered_stats)
            print(f"âœ… Stats synchronisÃ©es depuis les logs: {len(recovered_stats)} employÃ©s")
            
            # Afficher un rÃ©sumÃ©
            total_reas = sum(recovered_stats.values())
            print(f"ðŸ“Š Total des rÃ©as rÃ©cupÃ©rÃ©es: {total_reas}")
        else:
            print("âš ï¸ Aucune stat trouvÃ©e dans les logs")
            
    except Exception as e:
        print(f"âŒ Erreur lors de la synchronisation des stats: {e}")

# --- COMMANDES DE MANAGEMENT EMS ---

@app_commands.checks.has_permissions(administrator=True)
async def clean_channels(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    renamed_count = 0
    errors = []
    renamed_list = []
    
    # Parcourir tous les channels avec emoji
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            try:
                # Extraire le nom actuel sans l'emoji
                current_name_without_emoji = channel.name[1:].strip() if len(channel.name) > 1 else channel.name
                
                # Normaliser pour obtenir le nom propre (sans prÃ©fixe)
                clean_employee_name = normalize_employee_key(current_name_without_emoji)
                
                # Nouveau nom: emoji + nom propre
                current_emoji = channel.name[0]
                new_name = f"{current_emoji}{clean_employee_name}"
                
                # Renommer seulement si diffÃ©rent
                if channel.name != new_name:
                    old_name = channel.name
                    await channel.edit(name=new_name)
                    renamed_count += 1
                    renamed_list.append(f"â€¢ `{old_name}` â†’ `{new_name}`")
                    
            except Exception as e:
                errors.append(f"âŒ {channel.name}: {str(e)[:50]}")
    
    # Message de confirmation
    embed = discord.Embed(
        title="ðŸ§¹ NETTOYAGE DES CHANNELS",
        description=f"**{renamed_count} channel(s) renommÃ©(s)**\n\nTous les prÃ©fixes de grade (emt-, int-, dir-, cds-, etc.) ont Ã©tÃ© supprimÃ©s.",
        color=EMS_RED
    )
    
    if renamed_list:
        # Afficher les 15 premiers
        display_list = renamed_list[:15]
        if len(renamed_list) > 15:
            display_list.append(f"... et {len(renamed_list) - 15} autres")
        embed.add_field(
            name="ðŸ“ Channels renommÃ©s",
            value="\n".join(display_list),
            inline=False
        )
    
    if errors:
        embed.add_field(
            name="âš ï¸ Erreurs",
            value="\n".join(errors[:10]),
            inline=False
        )
    
    embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed)

@app_commands.checks.has_permissions(administrator=True)
async def setup_categories(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # ID de la catÃ©gorie cible (on veut positionner au-dessus)
    TARGET_CATEGORY_ID = 838110173368418325
    
    # DÃ©finir les catÃ©gories Ã  crÃ©er (ordre inversÃ© : DIR en haut, EMT en bas)
    grade_names = [
        ("DIR", "CATEGORY_DIR_ID"),
        ("CDS", "CATEGORY_CDS_ID"),
        ("MED", "CATEGORY_MED_ID"),
        ("PSY", "CATEGORY_PSY_ID"),
        ("INF", "CATEGORY_INF_ID"),
        ("ADS", "CATEGORY_ADS_ID"),
        ("STG", "CATEGORY_STG_ID"),
        ("EMT", "CATEGORY_EMT_ID")
    ]
    
    categories_data = load_categories()
    created = []
    created_categories = []
    errors = []
    
    for grade_name, key in grade_names:
        try:
            # CrÃ©er la catÃ©gorie
            category = await guild.create_category(name=grade_name)
            categories_data[key] = category.id
            created.append(f"âœ… {grade_name}: {category.id}")
            created_categories.append(category)
        except Exception as e:
            errors.append(f"âŒ {grade_name}: {e}")
    
    # Sauvegarder les IDs
    if created:
        save_categories(categories_data)
        
        # Recharger les variables globales
        global CATEGORY_EMT_ID, CATEGORY_STG_ID, CATEGORY_ADS_ID, CATEGORY_INF_ID, CATEGORY_PSY_ID, CATEGORY_MED_ID, CATEGORY_CDS_ID, CATEGORY_CAD_ID, CATEGORY_DIR_ID
        CATEGORY_EMT_ID = categories_data.get("CATEGORY_EMT_ID", 0)
        CATEGORY_STG_ID = categories_data.get("CATEGORY_STG_ID", 0)
        CATEGORY_ADS_ID = categories_data.get("CATEGORY_ADS_ID", 0)
        CATEGORY_INF_ID = categories_data.get("CATEGORY_INF_ID", 0)
        CATEGORY_PSY_ID = categories_data.get("CATEGORY_PSY_ID", 0)
        CATEGORY_MED_ID = categories_data.get("CATEGORY_MED_ID", 0)
        CATEGORY_CDS_ID = categories_data.get("CATEGORY_CDS_ID", 0)
        CATEGORY_CAD_ID = categories_data.get("CATEGORY_CAD_ID", 0)
        CATEGORY_DIR_ID = categories_data.get("CATEGORY_DIR_ID", 0)
        
        # Positionner les catÃ©gories au-dessus de la catÃ©gorie cible
        target_category = guild.get_channel(TARGET_CATEGORY_ID)
        if target_category and created_categories:
            try:
                # Obtenir la position de la catÃ©gorie cible
                target_position = target_category.position
                
                # Positionner chaque catÃ©gorie crÃ©Ã©e dans l'ordre, juste au-dessus
                for i, category in enumerate(created_categories):
                    new_position = target_position + i
                    try:
                        await category.edit(position=new_position)
                    except Exception as e:
                        errors.append(f"âš ï¸ Erreur positionnement {category.name}: {e}")
                
                created.append(f"ðŸ“ CatÃ©gories positionnÃ©es au-dessus de la catÃ©gorie cible")
            except Exception as e:
                errors.append(f"âš ï¸ Erreur positionnement global: {e}")
    
    # PrÃ©parer le message de rÃ©ponse
    embed = discord.Embed(
        title="ðŸ—ï¸ Configuration des CatÃ©gories",
        description="CrÃ©ation et positionnement des catÃ©gories pour chaque grade EMS",
        color=EMS_RED
    )
    
    if created:
        embed.add_field(name="âœ… CatÃ©gories crÃ©Ã©es et positionnÃ©es", value="\n".join(created), inline=False)
    
    if errors:
        embed.add_field(name="âŒ Erreurs", value="\n".join(errors), inline=False)
    
    embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed)

# --- CHECK PERSONNALISÃ‰ POUR EMPLOYER ---
async def employer_check(interaction: discord.Interaction) -> bool:
    """VÃ©rifie que l'utilisateur est admin OU a le rÃ´le 891765632717164596"""
    if interaction.user.guild_permissions.administrator:
        return True
    role = interaction.guild.get_role(891765632717164596)
    if role and role in interaction.user.roles:
        return True
    raise app_commands.MissingPermissions(['administrator'])

@bot.tree.command(name="set_categorie_emt", description="DÃ©finit la catÃ©gorie EMT (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_categorie_emt(interaction: discord.Interaction, categorie: discord.CategoryChannel):
    global CATEGORY_EMT_ID
    categories_data = load_categories()
    categories_data["CATEGORY_EMT_ID"] = categorie.id
    save_categories(categories_data)
    CATEGORY_EMT_ID = categorie.id
    await interaction.response.send_message(
        f"âœ… CatÃ©gorie EMT dÃ©finie sur **{categorie.name}** (`{categorie.id}`).",
        ephemeral=True
    )


@bot.tree.command(name="employer", description="Recruter un EMS (CrÃ©ation channel, rÃ´les, rename)")
@app_commands.check(employer_check)
@app_commands.describe(
    membre="Le membre Ã  employer",
    matricule="Matricule EMT (0 Ã  100, ex: 5 â†’ 05)"
)
async def employer(interaction: discord.Interaction, membre: discord.Member, matricule: app_commands.Range[int, 1, 99]):
    await interaction.response.defer()
    
    guild = interaction.guild
    clean_name = get_clean_name(membre)
    matricule_str = str(matricule).zfill(2)

    # VÃ©rifier si la matricule est dÃ©jÃ  utilisÃ©e par n'importe quel employÃ© EMS
    ROLE_EMS_ID = 838102445095256068
    role_ems = guild.get_role(ROLE_EMS_ID)
    members_to_scan = role_ems.members if role_ems else guild.members
    for m in members_to_scan:
        if m.id == membre.id or m.bot:
            continue
        match = _re.search(r'\[(\w+)\]\s+(\d{2})\b', m.display_name)
        if match and match.group(2) == matricule_str:
            grade_pris = match.group(1)
            await interaction.followup.send(
                f"âŒ La matricule **{matricule_str}** est dÃ©jÃ  prise par **{m.display_name}** ({grade_pris}).\n"
                f"Veuillez choisir une autre matricule entre **01** et **99**.",
                ephemeral=True
            )
            return
    
    # 1. Gestion du Pseudo
    new_nickname = f"[EMT] {matricule_str} {clean_name}"
    try:
        await membre.edit(nick=new_nickname)
    except Exception as e:
        print(f"Erreur changement pseudo {membre}: {e}")

    # 2. Gestion des RÃ´les
    roles_add_ids = [838102445095256068, 895047492784238652, 838102445095256070]
    role_remove_id = 896103247096471613
    
    roles_to_add = [guild.get_role(rid) for rid in roles_add_ids if guild.get_role(rid)]
    role_to_remove = guild.get_role(role_remove_id)
    
    if roles_to_add:
        await membre.add_roles(*roles_to_add)
    if role_to_remove:
        await membre.remove_roles(role_to_remove)

    # 3. CrÃ©ation du Channel dans la catÃ©gorie EMT (sans matricule dans le nom du channel)
    category = guild.get_channel(CATEGORY_EMT_ID)
    channel_name = f"ðŸ”´{clean_name.lower().replace(' ', '-')}"

    if category:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            membre: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        new_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
        await interaction.followup.send(
            f"âœ… **{membre.mention}** a Ã©tÃ© employÃ© avec succÃ¨s !\n"
            f"ðŸ“› RenommÃ© en `{new_nickname}`\n"
            f"ðŸªª Matricule : **{matricule_str}**\n"
            f"ðŸ“‚ Dossier crÃ©Ã© : {new_channel.mention}"
        )
        await update_matricule_board(guild)
        # Envoyer dans le channel formation
        formation_ch = guild.get_channel(991076525904367616)
        if formation_ch:
            await formation_ch.send(
                f"â†’ formation premier soin [EMT {clean_name}]"
            )
    else:
        await interaction.followup.send(f"âš ï¸ CatÃ©gorie EMT introuvable, rÃ´les et pseudo mis Ã  jour mais pas le channel.")


@bot.tree.command(name="matricule", description="Modifier votre propre matricule EMS")
@app_commands.describe(
    matricule="Nouvelle matricule (0 Ã  100, ex: 5 â†’ 05)"
)
async def set_matricule(interaction: discord.Interaction, matricule: app_commands.Range[int, 1, 99]):
    await interaction.response.defer(ephemeral=True)

    ROLE_MATRICULE_ID = 838102445095256068
    member_role_ids = [r.id for r in interaction.user.roles]

    if ROLE_MATRICULE_ID not in member_role_ids:
        await interaction.followup.send(
            "âŒ Vous n'avez pas la permission d'utiliser cette commande.",
            ephemeral=True
        )
        return

    membre = interaction.user
    display_name = membre.display_name
    matricule_str = str(matricule).zfill(2)

    # DÃ©tecter le grade depuis le pseudo actuel
    grade_tags = ["DIR", "CDS", "MED", "PSY", "INF", "ADS", "STG", "EMT"]
    grade_found = None
    for tag in grade_tags:
        if f"[{tag}]" in display_name:
            grade_found = tag
            break

    if not grade_found:
        await interaction.followup.send(
            f"âŒ Impossible de dÃ©tecter le grade de **{membre.display_name}**.\n"
            f"Le pseudo doit contenir un tag de grade comme `[EMT]`, `[STG]`, `[PSY]`, etc.",
            ephemeral=True
        )
        return

    # VÃ©rifier si la matricule est dÃ©jÃ  utilisÃ©e par n'importe quel employÃ© EMS
    ROLE_EMS_ID = 838102445095256068
    role_ems_check = interaction.guild.get_role(ROLE_EMS_ID)
    members_to_scan = role_ems_check.members if role_ems_check else interaction.guild.members
    for m in members_to_scan:
        if m.id == membre.id or m.bot:
            continue
        match = _re.search(r'\[(\w+)\]\s+(\d{2})\b', m.display_name)
        if match and match.group(2) == matricule_str:
            grade_pris = match.group(1)
            await interaction.followup.send(
                f"âŒ La matricule **{matricule_str}** est dÃ©jÃ  prise par **{m.display_name}** ({grade_pris}).\n"
                f"Veuillez choisir une autre matricule entre **01** et **99**.",
                ephemeral=True
            )
            return

    # Extraire le nom propre : supprimer [GRADE] et l'ancienne matricule si prÃ©sente
    clean = display_name
    clean = clean.replace(f"[{grade_found}]", "").strip()
    # Supprimer l'ancienne matricule genre "05 " en dÃ©but
    clean = _re.sub(r'^\d{2}\s*', '', clean).strip()

    new_nickname = f"[{grade_found}] {matricule_str} {clean}"

    try:
        await membre.edit(nick=new_nickname)
        await interaction.followup.send(
            f"âœ… Matricule mise Ã  jour pour **{membre.mention}**\n"
            f"ðŸ“› Nouveau pseudo : `{new_nickname}`",
            ephemeral=True
        )
        await update_matricule_board(interaction.guild)
    except Exception as e:
        await interaction.followup.send(
            f"âŒ Erreur lors de la modification du pseudo : `{e}`",
            ephemeral=True
        )


@bot.tree.command(name="matricules_check", description="Afficher toutes les matricules attribuÃ©es et mettre Ã  jour le tableau")
@app_commands.checks.has_permissions(administrator=True)
async def matricules_check(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild

    # Collecter toutes les matricules depuis les pseudos
    emt_pris = {}    # {grade: {mat: (mention, nom)}}
    doublons = {}    # {grade: {mat: [(mention, nom), ...]}}

    for m in guild.members:
        if m.bot:
            continue
        match = _re.search(r'\[(\w+)\]\s+(\d{2})\s+(.+)', m.display_name)
        if match:
            grade = match.group(1)
            mat = match.group(2)
            nom = match.group(3).strip()
            if grade not in emt_pris:
                emt_pris[grade] = {}
                doublons[grade] = {}
            if mat in emt_pris[grade]:
                # Doublon
                if mat not in doublons[grade]:
                    doublons[grade][mat] = [emt_pris[grade][mat]]
                doublons[grade][mat].append((m.mention, nom))
            else:
                emt_pris[grade][mat] = (m.mention, nom)

    # Ajouter les matricules direction manuelles
    for grade, mats in direction_matricules.items():
        if grade not in emt_pris:
            emt_pris[grade] = {}
        for mat, nom in mats.items():
            emt_pris[grade][mat] = (None, f"{nom} *(direction)*")

    if not emt_pris:
        await interaction.followup.send("âœ… Aucune matricule attribuÃ©e pour l'instant.", ephemeral=True)
        return

    grade_labels = {
        "EMT": "ðŸš‘ EMT",
        "STG": "ðŸ“‹ Stagiaire",
        "ADS": "ðŸ©º Aide-Soignant",
        "INF": "ðŸ’‰ Infirmier",
        "PSY": "ðŸ§  Psychologue",
        "MED": "âš•ï¸ MÃ©decin",
        "CDS": "ðŸ¥ Chef de Service",
        "CAD": "ðŸ¥ Chef Adjoint",
        "DIR": "ðŸ‘” Directeur MÃ©dical",
    }
    grade_order = ["EMT", "STG", "ADS", "INF", "PSY", "MED", "CDS", "CAD", "DIR"]

    total_doublons = sum(len(v) for v in doublons.values() if v)

    embed = discord.Embed(
        title="ðŸªª Matricules attribuÃ©es",
        color=discord.Color.red() if total_doublons else EMS_RED
    )

    # Alerte doublons en haut
    if total_doublons:
        conflit_lines = []
        for grade, mats in doublons.items():
            for mat, entries in mats.items():
                pings = " Â· ".join([f"{mention}" if mention else nom for mention, nom in entries])
                conflit_lines.append(f"âš ï¸ **{mat}** ({grade}) â†’ {pings}")
        embed.add_field(
            name=f"ðŸš¨ {total_doublons} CONFLIT(S) DÃ‰TECTÃ‰(S)",
            value="\n".join(conflit_lines),
            inline=False
        )

    total = 0
    for grade in grade_order:
        if grade not in emt_pris:
            continue
        mats = emt_pris[grade]
        total += len(mats)
        lines = []
        for mat, (mention, nom) in sorted(mats.items()):
            if mention:
                lines.append(f"**{mat}** â€” {mention}")
            else:
                lines.append(f"**{mat}** â€” {nom}")
        embed.add_field(
            name=f"{grade_labels.get(grade, grade)} ({len(mats)})",
            value="\n".join(lines),
            inline=False
        )

    embed.set_footer(text=f"ðŸš‘ EMS System | {total} matricule(s) attribuÃ©e(s) au total")

    # Collecter toutes les vraies mentions pour les afficher proprement
    all_mentions = []
    for grade in grade_order:
        if grade not in emt_pris:
            continue
        for mat, (mention, nom) in sorted(emt_pris[grade].items()):
            if mention:
                all_mentions.append(f"**{mat}** {mention}")

    await interaction.followup.send(embed=embed, ephemeral=True)
    if all_mentions:
        await interaction.followup.send(
            "ðŸ“‹ **RÃ©cap mentions :**\n" + " Â· ".join(all_mentions),
            ephemeral=True
        )

    # Mettre Ã  jour le tableau public en mÃªme temps
    await update_matricule_board(guild)



@bot.tree.command(name="matricules_direction", description="GÃ©rer les matricules de la direction et grades supÃ©rieurs (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    action="Ajouter ou retirer une matricule",
    grade="Grade concernÃ©",
    matricule="NumÃ©ro de matricule (0 Ã  100, ex: 5 â†’ 05)",
    nom="Nom complet de la personne (ex: Jean Dupont)"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="Ajouter", value="add"),
        app_commands.Choice(name="Retirer", value="remove"),
    ],
    grade=[
        app_commands.Choice(name="ðŸ‘” Directeur MÃ©dical (DIR)", value="DIR"),
        app_commands.Choice(name="ðŸ¥ Chef Adjoint (CAD)", value="CAD"),
        app_commands.Choice(name="ðŸ¥ Chef de Service (CDS)", value="CDS"),
        app_commands.Choice(name="âš•ï¸ MÃ©decin (MED)", value="MED"),
        app_commands.Choice(name="ðŸ§  Psychologue (PSY)", value="PSY"),
        app_commands.Choice(name="ðŸ’‰ Infirmier (INF)", value="INF"),
        app_commands.Choice(name="ðŸ©º Aide-Soignant (ADS)", value="ADS"),
        app_commands.Choice(name="ðŸ“‹ Stagiaire (STG)", value="STG"),
    ]
)
async def matricules_direction(
    interaction: discord.Interaction,
    action: str,
    grade: str,
    matricule: app_commands.Range[int, 1, 99],
    nom: str = None
):
    await interaction.response.defer(ephemeral=True)
    global direction_matricules

    matricule_str = str(matricule).zfill(2)

    if action == "add":
        if not nom:
            await interaction.followup.send("âŒ Veuillez prÃ©ciser le nom de la personne.", ephemeral=True)
            return
        if grade not in direction_matricules:
            direction_matricules[grade] = {}
        # VÃ©rifier doublon dans ce grade
        if matricule_str in direction_matricules[grade]:
            await interaction.followup.send(
                f"âŒ La matricule **{matricule_str}** est dÃ©jÃ  attribuÃ©e Ã  **{direction_matricules[grade][matricule_str]}** ({grade}).",
                ephemeral=True
            )
            return
        direction_matricules[grade][matricule_str] = nom
        await interaction.followup.send(
            f"âœ… Matricule **{matricule_str}** attribuÃ©e Ã  **{nom}** ({grade}).",
            ephemeral=True
        )

    elif action == "remove":
        if grade not in direction_matricules or matricule_str not in direction_matricules[grade]:
            await interaction.followup.send(
                f"âŒ La matricule **{matricule_str}** ({grade}) est introuvable.",
                ephemeral=True
            )
            return
        ancien = direction_matricules[grade].pop(matricule_str)
        await interaction.followup.send(
            f"âœ… Matricule **{matricule_str}** ({grade}) retirÃ©e (Ã©tait : {ancien}).",
            ephemeral=True
        )

    await update_matricule_board(interaction.guild)



@app_commands.describe(membre="Le membre dont mettre Ã  jour le tag (optionnel, sinon tous)")
@app_commands.checks.has_permissions(administrator=True)
async def reset_names(interaction: discord.Interaction, membre: discord.Member = None):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # Mapping des rÃ´les Discord vers les tags de grade (du plus Ã©levÃ© au plus bas)
    role_hierarchy = [
        (1088570974603055195, "[DIR]"),  # Directeur MÃ©dical
        (1528561040663777310, "[CAD]"),  # Chef Adjoint
        (838102445095256071, "[CDS]"),   # Chef de Service
        (840288242547818507, "[MED]"),   # MÃ©decin
        (1528560704511148092, "[PSY]"),  # Psychologue
        (894311352225656862, "[INF]"),   # Infirmier
        (1088116715998687273, "[ADS]"),  # Aide-Soignant
        (838102445095256069, "[STG]"),   # Stagiaire
        (895047492784238652, "[EMT]"),   # EMT
    ]
    
    def get_grade_tag(member):
        """Retourne le tag de grade le plus Ã©levÃ© du membre"""
        member_role_ids = [role.id for role in member.roles]
        for role_id, tag in role_hierarchy:
            if role_id in member_role_ids:
                return tag
        return None
    
    if membre:
        # Mettre Ã  jour un seul membre
        clean_name = get_clean_name(membre)
        grade_tag = get_grade_tag(membre)
        
        if grade_tag:
            new_nickname = f"{grade_tag} {clean_name}"
            try:
                await membre.edit(nick=new_nickname)
                embed = discord.Embed(
                    title="âœ… Pseudo mis Ã  jour",
                    description=f"{membre.mention} â†’ `{new_nickname}`",
                    color=EMS_RED
                )
                embed.set_footer(text="ðŸš‘ EMS System")
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"âŒ Erreur : {e}")
        else:
            await interaction.followup.send(f"âŒ {membre.mention} n'a aucun rÃ´le EMS reconnu.")
    else:
        # Mettre Ã  jour tous les membres avec des rÃ´les EMS
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
                
                # VÃ©rifier si le pseudo est dÃ©jÃ  correct
                if member.display_name == new_nickname:
                    skipped.append(member.display_name)
                    continue
                
                try:
                    await member.edit(nick=new_nickname)
                    updated.append(f"âœ… {member.mention} â†’ `{new_nickname}`")
                except Exception as e:
                    errors.append(f"âŒ {member.display_name}: {str(e)}")
        
        # CrÃ©er l'embed de rÃ©sultat
        embed = discord.Embed(
            title="ðŸ”„ Mise Ã  jour des pseudos selon les rÃ´les",
            color=EMS_RED
        )
        
        if updated:
            # Limiter Ã  10 pour ne pas dÃ©passer la limite d'embed
            display_updated = updated[:10]
            if len(updated) > 10:
                display_updated.append(f"... et {len(updated) - 10} autres")
            embed.add_field(
                name=f"âœ… Pseudos mis Ã  jour ({len(updated)})",
                value="\n".join(display_updated),
                inline=False
            )
        
        if skipped:
            embed.add_field(
                name=f"â­ï¸ DÃ©jÃ  Ã  jour ({len(skipped)})",
                value=f"{len(skipped)} membres avaient dÃ©jÃ  le bon pseudo",
                inline=False
            )
        
        if not updated and not errors:
            embed.description = "Aucun membre EMS Ã  mettre Ã  jour."
        
        if errors:
            display_errors = errors[:5]
            if len(errors) > 5:
                display_errors.append(f"... et {len(errors) - 5} autres erreurs")
            embed.add_field(
                name=f"âŒ Erreurs ({len(errors)})",
                value="\n".join(display_errors),
                inline=False
            )
        
        embed.set_footer(text="ðŸš‘ EMS System")
        await interaction.followup.send(embed=embed)

class AutreRaisonModal(discord.ui.Modal, title="âœï¸ Raison du licenciement"):
    raison = discord.ui.TextInput(
        label="PrÃ©cisez la raison",
        placeholder="Expliquez ici la raison du licenciement...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, membre: discord.Member):
        super().__init__()
        self.membre = membre

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await executer_virement(interaction, self.membre, raison_type="autres", raison_custom=self.raison.value)


class RaisonVireSelect(discord.ui.Select):
    def __init__(self, membre: discord.Member):
        self.membre = membre
        options = [
            discord.SelectOption(label="InactivitÃ©", value="inactivite", emoji="â³", description="Absence prolongÃ©e sans justification"),
            discord.SelectOption(label="Erreur professionnelle", value="erreur_pro", emoji="âš ï¸", description="Faute grave dans l'exercice des fonctions"),
            discord.SelectOption(label="Autres", value="autres", emoji="ðŸ“", description="PrÃ©ciser la raison manuellement"),
        ]
        super().__init__(placeholder="SÃ©lectionner la raison du licenciement...", options=options)

    async def callback(self, interaction: discord.Interaction):
        choix = self.values[0]
        if choix == "autres":
            await interaction.response.send_modal(AutreRaisonModal(self.membre))
        else:
            await interaction.response.defer()
            await executer_virement(interaction, self.membre, raison_type=choix)


class RaisonVireView(discord.ui.View):
    def __init__(self, membre: discord.Member):
        super().__init__(timeout=60)
        self.add_item(RaisonVireSelect(membre))


async def executer_virement(interaction: discord.Interaction, membre: discord.Member, raison_type: str, raison_custom: str = None):
    guild = interaction.guild
    clean_name = get_clean_name(membre)

    # Messages DM selon la raison
    if raison_type == "inactivite":
        raison_dm = (
            f"Cher **{clean_name}**,\n\n"
            f"Nous avons le regret de vous informer que votre contrat au sein de l'HÃ´pital de Los Santos a Ã©tÃ© rÃ©siliÃ© en raison d'une **inactivitÃ© prolongÃ©e** et non justifiÃ©e.\n\n"
            f"MalgrÃ© les attentes fixÃ©es en termes de prÃ©sence et d'investissement, votre absence rÃ©pÃ©tÃ©e n'est pas compatible avec les exigences de notre service.\n\n"
            f"Nous vous remercions pour votre passage parmi nous et vous souhaitons bonne continuation.\n\n"
            f"Cordialement,\n**La Direction des EMS.**"
        )
        raison_label = "â³ InactivitÃ© prolongÃ©e"
    elif raison_type == "erreur_pro":
        raison_dm = (
            f"Cher **{clean_name}**,\n\n"
            f"Nous avons le regret de vous informer que votre contrat au sein de l'HÃ´pital de Los Santos a Ã©tÃ© rÃ©siliÃ© suite Ã  une **erreur professionnelle grave**.\n\n"
            f"Cette dÃ©cision fait suite Ã  une analyse approfondie des faits constatÃ©s, jugÃ©s incompatibles avec les valeurs, les protocoles et les standards de notre service mÃ©dical.\n\n"
            f"Nous vous remercions pour votre engagement passÃ© et vous souhaitons bonne continuation dans vos projets.\n\n"
            f"Cordialement,\n**La Direction des EMS.**"
        )
        raison_label = "âš ï¸ Erreur professionnelle"
    else:
        raison_dm = (
            f"Cher **{clean_name}**,\n\n"
            f"Nous avons le regret de vous informer que votre contrat au sein de l'HÃ´pital de Los Santos a Ã©tÃ© rÃ©siliÃ©.\n\n"
            f"**Motif :** {raison_custom}\n\n"
            f"Nous vous remercions pour votre passage parmi nous et vous souhaitons bonne continuation.\n\n"
            f"Cordialement,\n**La Direction des EMS.**"
        )
        raison_label = f"ðŸ“ {raison_custom}"

    # 1. RÃ´les
    role_target_id = 838102445095256066
    roles_to_remove = [r for r in membre.roles if r.id in EMS_ROLE_IDS_TO_REMOVE]
    role_to_add = guild.get_role(role_target_id)
    if roles_to_remove:
        await membre.remove_roles(*roles_to_remove)
    if role_to_add:
        await membre.add_roles(role_to_add)

    # 2. Reset pseudo
    try:
        await membre.edit(nick=None)
    except:
        pass

    # 3. DM
    try:
        await membre.send(raison_dm)
    except Exception as e:
        print(f"Erreur envoi DM licenciement: {e}")

    # 4. Supprimer le channel
    channel_deleted = False
    clean_name_normalized = normalize_employee_key(clean_name)
    for channel in guild.text_channels:
        if channel.name and len(channel.name) > 1 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            channel_employee_key = get_channel_employee_key(channel)
            if channel_employee_key == clean_name_normalized:
                await interaction.followup.send(
                    f"ðŸš« **{clean_name}** a Ã©tÃ© licenciÃ©.\n"
                    f"**Motif :** {raison_label}\n"
                    f"RÃ´les retirÃ©s, pseudo rÃ©initialisÃ© et channel supprimÃ©."
                )
                try:
                    await channel.delete()
                    channel_deleted = True
                    break
                except Exception as e:
                    print(f"Erreur suppression channel: {e}")
    if not channel_deleted:
        await interaction.followup.send(
            f"ðŸš« **{clean_name}** a Ã©tÃ© licenciÃ©.\n"
            f"**Motif :** {raison_label}\n"
            f"RÃ´les retirÃ©s et pseudo rÃ©initialisÃ©.\nâš ï¸ Aucun channel personnel trouvÃ©."
        )

    # Rappel permissions In-Game
    # Enregistrer rappel dashboard (retrait perms IG)
    grade_m2 = _re.search(r'\[(\w+)\]', membre.display_name)
    emp_grade2 = grade_m2.group(1) if grade_m2 else ''
    try:
        vr_data = robust_load_json(VIRER_REMINDERS_FILE, [])
        vr_data.append({
            'id': str(int(time.time() * 1000)),
            'name': clean_name,
            'grade': emp_grade2,
            'date': now_paris().strftime('%d/%m %H:%M'),
        })
        atomic_write_json(VIRER_REMINDERS_FILE, vr_data)
    except Exception:
        pass

    ig_embed = discord.Embed(
        title="ðŸŽ® Permissions In-Game Ã  retirer",
        color=discord.Color.from_rgb(255, 59, 48),
        description=(
            f"**{clean_name}** vient d'Ãªtre licenciÃ©(e).\n\n"
            f"**âžœ Retirez le rÃ´le EMS In-Game (FiveM) pour :**\n"
            f"```\n{clean_name}\n```"
        )
    )
    ig_embed.set_footer(text="ðŸš‘ Los Santos EMS â€” Action manuelle requise")
    try:
        await interaction.channel.send(embed=ig_embed)
    except Exception:
        pass

    # â”€â”€ BLACKLIST CV automatique sur licenciement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        bl = load_blacklist_cv()
        bl[str(membre.id)] = {
            "date": datetime.utcnow().isoformat(),
            "raison": f"Licenciement â€” {raison_label}",
            "blacklisted_by": str(interaction.user.id),
        }
        save_blacklist_cv(bl)
    except Exception as _bl_err:
        print(f"Erreur blacklist CV virer: {_bl_err}")
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    await update_matricule_board(guild)


@bot.tree.command(name="virer", description="Virer un employÃ© (Retrait rÃ´les, reset pseudo)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="Le nom du membre Ã  virer")
async def virer(interaction: discord.Interaction, membre: str):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    
    # Chercher le membre par nom (display_name ou user.name)
    target_member = None
    search_term = membre.lower().strip()
    
    for m in guild.members:
        if search_term in get_clean_name(m).lower() or search_term in m.display_name.lower() or search_term in m.name.lower():
            target_member = m
            break
    
    if not target_member:
        await interaction.followup.send(f"âŒ Membre '{membre}' introuvable.", ephemeral=True)
        return
    
    view = RaisonVireView(target_member)
    await interaction.followup.send(
        f"âš ï¸ Vous Ãªtes sur le point de licencier **{get_clean_name(target_member)}**.\n"
        f"SÃ©lectionnez la raison du licenciement :",
        view=view,
        ephemeral=True
    )

@bot.tree.command(name="up", description="Promouvoir un employÃ© au rang suivant")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="Le membre Ã  promouvoir")
async def up(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.defer()
    guild = interaction.guild
    member_roles_ids = [r.id for r in membre.roles]
    clean_name = get_clean_name(membre)
    
    # Mapping des transitions
    # (Role Actuel -> Role Suivant, Nouveau Prefix, Prefix Channel, Ancre/Cible move, Regex Cible)
    
    # IDs des RÃ´les
    # HiÃ©rarchie : EMT â†’ STG â†’ ADS â†’ INF â†’ PSY â†’ MED â†’ CDS (Chef de Service) â†’ CAD (Chef Adjoint) â†’ DIR (Directeur MÃ©dical)
    R_EMT = 895047492784238652
    R_STG = 838102445095256069   # Stagiaire
    R_ADS = 1088116715998687273
    R_INF = 894311352225656862
    R_PSY = 1528560704511148092  # Psychologue
    R_MED = 840288242547818507
    R_CDS = 838102445095256071   # Chef de Service
    R_CAD = 1528561040663777310  # Chef Adjoint
    R_DIR = 1088570974603055195  # Directeur MÃ©dical

    # Logique de promotion â€” du plus bas au plus haut
    next_step = None

    # Pour distinguer STG de PSY (mÃªme ID pour l'instant), on se base sur le tag pseudo
    has_psy_tag = "[PSY]" in membre.display_name.upper()
    has_stg_tag = "[STG]" in membre.display_name.upper() or "[INT]" in membre.display_name.upper()
    has_inf_tag = "[INF]" in membre.display_name.upper()

    if R_EMT in member_roles_ids and not any(r in member_roles_ids for r in [R_ADS, R_INF, R_MED, R_CDS, R_DIR]):
        # EMT -> STG
        next_step = {
            "remove": R_EMT, "add": R_STG,
            "tag": "STG",
            "category_id": CATEGORY_STG_ID
        }
    elif R_STG in member_roles_ids and has_stg_tag and R_ADS not in member_roles_ids:
        # STG -> ADS
        next_step = {
            "remove": R_STG, "add": R_ADS,
            "tag": "ADS",
            "category_id": CATEGORY_ADS_ID
        }
    elif R_ADS in member_roles_ids and R_INF not in member_roles_ids:
        # ADS -> INF
        next_step = {
            "remove": R_ADS, "add": R_INF,
            "tag": "INF",
            "category_id": CATEGORY_INF_ID
        }
    elif R_INF in member_roles_ids and has_inf_tag and R_MED not in member_roles_ids:
        # INF -> PSY
        next_step = {
            "remove": R_INF, "add": R_PSY,
            "tag": "PSY",
            "category_id": CATEGORY_PSY_ID
        }
    elif R_PSY in member_roles_ids and has_psy_tag and R_MED not in member_roles_ids:
        # PSY -> MED
        next_step = {
            "remove": R_PSY, "add": R_MED,
            "tag": "MED",
            "category_id": CATEGORY_MED_ID
        }
    elif R_MED in member_roles_ids and R_CDS not in member_roles_ids and R_CAD not in member_roles_ids:
        # MED -> CDS (Chef de Service)
        next_step = {
            "remove": R_MED, "add": R_CDS,
            "tag": "CDS",
            "category_id": CATEGORY_CDS_ID
        }
    elif R_CDS in member_roles_ids and R_CAD not in member_roles_ids:
        # CDS -> CAD (Chef Adjoint)
        next_step = {
            "remove": R_CDS, "add": R_CAD,
            "tag": "CAD",
            "category_id": CATEGORY_CAD_ID
        }
    elif R_CAD in member_roles_ids and R_DIR not in member_roles_ids:
        # CAD -> DIR (Directeur MÃ©dical)
        next_step = {
            "remove": R_CAD, "add": R_DIR,
            "tag": "DIR",
            "category_id": CATEGORY_DIR_ID
        }
    else:
        await interaction.followup.send("âŒ Ce membre n'a pas de grade Ã©volutif connu ou est dÃ©jÃ  au maximum (Directeur MÃ©dical).")
        return

    # Appliquer les changements
    
    # 1. RÃ´les
    await membre.remove_roles(guild.get_role(next_step["remove"]))
    await membre.add_roles(guild.get_role(next_step["add"]))
    
    # 2. Pseudo â€” conserver la matricule si prÃ©sente
    mat_match = _re.search(r'\]\s+(\d{2})\s+', membre.display_name)
    matricule_str = mat_match.group(1) if mat_match else None

    if matricule_str:
        new_nick = f"[{next_step['tag']}] {matricule_str} {clean_name}"
    else:
        new_nick = f"[{next_step['tag']}] {clean_name}"
    try:
        await membre.edit(nick=new_nick)
    except:
        pass
        
    # 3. Channel - Trouver le channel de l'employÃ© et le dÃ©placer (sans changer le nom, juste retirer le prÃ©fixe)
    channel = None
    
    # Chercher le channel de l'employÃ©
    clean_name_normalized = clean_name.lower().replace(' ', '-')
    for ch in guild.text_channels:
        if ch.name and len(ch.name) > 1 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            # Enlever l'emoji et normaliser
            ch_employee_key = get_channel_employee_key(ch)
            member_key = normalize_employee_key(clean_name)
            if ch_employee_key == member_key:
                channel = ch
                break
    
    chan_msg = ""
    if channel:
        # Nouveau nom sans prÃ©fixe de grade, juste l'emoji + nom
        current_emoji = channel.name[0] if channel.name and len(channel.name) > 0 else "ðŸ”´"
        new_chan_name = f"{current_emoji}{clean_name_normalized}"
        
        # DÃ©placer dans la nouvelle catÃ©gorie
        new_category_id = next_step.get("category_id")
        new_category = guild.get_channel(new_category_id) if new_category_id else None
        
        if new_category:
            try:
                await channel.edit(name=new_chan_name, category=new_category)
                chan_msg = f"\nðŸ“‚ Dossier dÃ©placÃ© dans la catÃ©gorie {next_step['tag']} : {channel.mention}"
            except Exception as e:
                chan_msg = f"\nâš ï¸ Erreur dÃ©placement dossier: {e}"
        else:
            try:
                await channel.edit(name=new_chan_name)
                chan_msg = f"\nðŸ“‚ Dossier renommÃ© : {channel.mention} (catÃ©gorie {next_step['tag']} introuvable)"
            except Exception as e:
                chan_msg = f"\nâš ï¸ Erreur renommage: {e}"

    # Tracker la promotion dans l'historique
    try:
        m_grade = _re.search(r'\[(\w+)\]', membre.display_name)
        from_grade = m_grade.group(1) if m_grade else 'inconnu'
        emp_key_up = normalize_employee_key(clean_name)
        promo_track(emp_key_up, from_grade, next_step['tag'], str(interaction.user))
    except Exception as _pt_err:
        print(f"Erreur tracking promo: {_pt_err}")

    await interaction.followup.send(f"ðŸ“ˆ **Promotion effectuÃ©e pour {membre.mention}** !\nPassage au grade **{next_step['tag']}**.{chan_msg}")

@app_commands.checks.has_permissions(administrator=True)
async def payes(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # 1. Demander l'image du coffre
    ask_embed = discord.Embed(
        title="ðŸ’° CALCUL DES SALAIRES",
        description="**ðŸ“¸ Envoyez une capture d'Ã©cran du coffre (Ã©tat avant les paiements)**\n\nVous avez 2 minutes pour envoyer l'image.",
        color=EMS_RED
    )
    ask_embed.set_footer(text="ðŸš‘ EMS System | SystÃ¨me de paie")
    await interaction.followup.send(embed=ask_embed)
    
    def check_image(m):
        return m.author == interaction.user and m.channel == interaction.channel and len(m.attachments) > 0
    
    coffre_image_file = None
    try:
        msg_image = await bot.wait_for('message', check=check_image, timeout=120)
        coffre_image_url = msg_image.attachments[0].url
        
        # TÃ©lÃ©charger l'image pour l'attacher au message (Ã©vite l'expiration)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(coffre_image_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        coffre_image_file = discord.File(io.BytesIO(image_data), filename="coffre.png")
        except Exception as e:
            print(f"Erreur tÃ©lÃ©chargement image coffre: {e}")
    except asyncio.TimeoutError:
        timeout_embed = discord.Embed(
            title="â±ï¸ TEMPS Ã‰COULÃ‰",
            description="Vous n'avez pas envoyÃ© l'image Ã  temps. Commande annulÃ©e.",
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
        
        # VÃ©rifier d'abord si le membre a le rÃ´le DIRECTION
        has_direction_role = direction_role in member.roles if direction_role else False
        
        if has_direction_role:
            # DIRECTION: 9M fixe, pas de calcul avec rÃ©as
            clean_name = get_clean_name(member)
            salary = 9000000
            total_payroll += salary
            
            salary_data.append({
                "name": clean_name,
                "rea": 0,  # Pas affichÃ© pour direction
                "grade": "DIRECTION",
                "total": salary
            })
            continue
        
        # DÃ©tecter le grade par tag dans le pseudo pour les autres
        nick = member.display_name.upper()
        grade = None
        rate = 0
        
        if "[DIR]" in nick:
            grade = "DIR"
            rate = 55000
        elif "[CAD]" in nick:
            grade = "CAD"
            rate = 52000
        elif "[CDS]" in nick:
            grade = "CDS"
            rate = 50000
        elif "[MED]" in nick:
            grade = "MED"
            rate = 45000
        elif "[INF]" in nick:
            grade = "INF"
            rate = 40000
        elif "[PSY]" in nick:
            grade = "PSY"
            rate = 42000
        elif "[ADS]" in nick:
            grade = "ADS"
            rate = 40000
        elif "[STG]" in nick or "[INT]" in nick:
            grade = "STG"
            rate = 35000
        elif "[EMT]" in nick:
            grade = "EMT"
            rate = 30000
        else:
            continue  # Pas un employÃ© EMS
        
        # RÃ©cupÃ©rer les rÃ©as (0 si absent)
        employee_key = normalize_employee_key(member.display_name)
        rea_count = stats.get(employee_key, 0)
        
        # Calculer le salaire: base + bonus
        base_salary = rea_count * rate
        bonus = 0
        if rea_count > 50:
            bonus = ((rea_count - 50) // 10) * 150000
        salary = base_salary + bonus
        
        total_payroll += salary
        
        # Ajouter Ã  la liste
        clean_name = get_clean_name(member)
        salary_data.append({
            "name": clean_name,
            "rea": rea_count,
            "grade": grade,
            "total": salary
        })
    
    # 4. Trier par salaire dÃ©croissant
    salary_data.sort(key=lambda x: x["total"], reverse=True)
    
    # 5. Diviser en plusieurs embeds (10 employÃ©s par page pour Ã©viter dÃ©passement)
    embeds_to_send = []
    employees_per_embed = 10
    
    for i in range(0, len(salary_data), employees_per_embed):
        chunk = salary_data[i:i + employees_per_embed]
        page_num = (i // employees_per_embed) + 1
        total_pages = (len(salary_data) + employees_per_embed - 1) // employees_per_embed
        
        # CrÃ©er un embed pour ce groupe
        if i == 0:
            # Premier embed avec image du coffre
            chunk_embed = discord.Embed(
                title="ðŸ’° PAIEMENT DES SALAIRES",
                description="**ðŸ“Š RÃ©capitulatif des salaires de la semaine**\n",
                color=EMS_RED
            )
            if coffre_image_file:
                chunk_embed.set_image(url=f"attachment://{coffre_image_file.filename}")
        else:
            # Embeds suivants
            chunk_embed = discord.Embed(
                title=f"ðŸ’° PAIEMENT DES SALAIRES (suite)",
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
        
        chunk_embed.add_field(name=f"ðŸ“‹ Liste (Page {page_num}/{total_pages})", value=salary_text, inline=False)
        
        # Ajouter le total uniquement sur le dernier embed
        if i + employees_per_embed >= len(salary_data):
            chunk_embed.add_field(
                name="ðŸ’µ TOTAL Ã€ RETIRER",
                value=f"```{total_payroll:,}$```".replace(",", " "),
                inline=False
            )
            chunk_embed.set_footer(text="ðŸš‘ EMS System | Bonne paie Ã  tous !")
            chunk_embed.timestamp = now_paris()
        else:
            chunk_embed.set_footer(text=f"ðŸš‘ EMS System | Page {page_num}/{total_pages}")
        
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
                # Delai pour eviter le rate limiting Discord
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"Erreur envoi annonce salaires (page {idx+1}): {e}")
    
    # 7. RÃ©initialiser la semaine (comme /semaine)
    # RÃ©initialiser stats
    save_stats({})
    
    # RÃ©initialiser les primes du soir
    global evening_reas
    evening_reas = {}
    atomic_write_json(EVENING_REAS_FILE, evening_reas)
    
    # Mettre tous les channels en ðŸ”´
    announcement_channels = []
    for channel in guild.text_channels:
        if len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            new_name = f"ðŸ”´{channel.name[1:]}"
            try:
                await channel.edit(name=new_name)
                announcement_channels.append(channel)
            except:
                pass
    
    # Embed d'annonce de nouvelle semaine
    week_embed = discord.Embed(
        title="ðŸš‘ NOUVELLE SEMAINE !",
        description="**âœ… Salaires payÃ©s et semaine rÃ©initialisÃ©e**\n\nâ€¢ Tous les compteurs remis Ã  0\nâ€¢ Tous les channels en ðŸ”´\nâ€¢ C'est repartit de zÃ©ro !\n\n**Bonne chance Ã  tous ! ðŸ’ª**",
        color=EMS_RED
    )
    week_embed.set_image(url="https://media.discordapp.net/attachments/1432501937085087896/1457439823215460487/image.png?ex=695ea51b&is=695d539b&hm=73669ae578193fac7bb528589592facb8ffa94a53f6521f1fad68165e393d32c&=&format=webp&quality=lossless&width=1872&height=571")
    week_embed.set_footer(text="ðŸš‘ EMS System | Nouvelle semaine, nouveau challenge !")
    
    # Envoyer l'annonce dans tous les channels avec emoji
    for channel in announcement_channels:
        try:
            await channel.send(embed=week_discord.Embed.from_dict(embed.to_dict()))
        except:
            pass
    
    # Envoyer aussi dans le channel de logs
    if log_channel:
        try:
            await log_channel.send(embed=week_discord.Embed.from_dict(embed.to_dict()))
        except:
            pass
    
    # 8. Confirmer la commande
    confirm_embed = discord.Embed(
        title="âœ… SALAIRES CALCULÃ‰S ET ENVOYÃ‰S",
        description=f"ðŸ’° **Total Ã  payer :** {total_payroll:,}$\nðŸ“Š **EmployÃ©s payÃ©s :** {len(salary_data)}\nâœ… Semaine rÃ©initialisÃ©e avec succÃ¨s !".replace(",", " "),
        color=EMS_RED
    )
    confirm_embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=confirm_embed)

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
        
        # VÃ©rifier si le membre a le rÃ´le DIRECTION
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
        
        # DÃ©tecter le grade par tag dans le pseudo
        nick = member.display_name.upper()
        grade = None
        rate = 0
        
        if "[DIR]" in nick:
            grade = "DIR"
            rate = 55000
        elif "[CAD]" in nick:
            grade = "CAD"
            rate = 52000
        elif "[CDS]" in nick:
            grade = "CDS"
            rate = 50000
        elif "[MED]" in nick:
            grade = "MED"
            rate = 45000
        elif "[INF]" in nick:
            grade = "INF"
            rate = 40000
        elif "[PSY]" in nick:
            grade = "PSY"
            rate = 42000
        elif "[ADS]" in nick:
            grade = "ADS"
            rate = 40000
        elif "[STG]" in nick or "[INT]" in nick:
            grade = "STG"
            rate = 35000
        elif "[EMT]" in nick:
            grade = "EMT"
            rate = 30000
        else:
            continue
        
        # RÃ©cupÃ©rer les rÃ©as
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
    
    # Trier par salaire dÃ©croissant
    salary_data.sort(key=lambda x: x["total"], reverse=True)
    
    # Diviser les employÃ©s en groupes de 10 pour Ã©viter les dÃ©passements
    embeds_to_send = []
    employees_per_embed = 10
    
    for i in range(0, len(salary_data), employees_per_embed):
        chunk = salary_data[i:i + employees_per_embed]
        page_num = (i // employees_per_embed) + 1
        total_pages = (len(salary_data) + employees_per_embed - 1) // employees_per_embed
        
        # CrÃ©er un embed pour ce groupe
        if i == 0:
            # Premier embed avec titre principal
            chunk_embed = discord.Embed(
                title="ðŸ’° TEST - APERÃ‡U DES SALAIRES",
                description="**ðŸ“Š Simulation du calcul des salaires (rien n'est envoyÃ© ou reset)**\n",
                color=EMS_RED
            )
        else:
            # Embeds suivants
            chunk_embed = discord.Embed(
                title=f"ðŸ’° APERÃ‡U DES SALAIRES (suite)",
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
        
        chunk_embed.add_field(name=f"ðŸ“‹ Liste (Page {page_num}/{total_pages})", value=salary_text, inline=False)
        
        # Ajouter les stats uniquement sur le dernier embed
        if i + employees_per_embed >= len(salary_data):
            chunk_embed.add_field(
                name="ðŸ’µ TOTAL Ã€ RETIRER",
                value=f"```{total_payroll:,}$```".replace(",", " "),
                inline=False
            )
            
            chunk_embed.add_field(
                name="ðŸ“Š STATISTIQUES",
                value=f"**EmployÃ©s :** {len(salary_data)}\n**RÃ©as totales :** {sum(stats.values())}",
                inline=False
            )
        
        chunk_embed.set_footer(text=f"ðŸš‘ EMS System | Mode Test - Page {page_num}/{total_pages}")
        embeds_to_send.append(chunk_embed)
    
    # Envoyer tous les embeds
    for embed in embeds_to_send:
        await interaction.followup.send(embed=embed, ephemeral=True)

@app_commands.checks.has_permissions(administrator=True)
async def reorganize(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    
    # VÃ©rifier que les catÃ©gories sont configurÃ©es
    if not all([CATEGORY_EMT_ID, CATEGORY_STG_ID, CATEGORY_ADS_ID, CATEGORY_INF_ID, CATEGORY_PSY_ID, CATEGORY_MED_ID, CATEGORY_CDS_ID, CATEGORY_CAD_ID, CATEGORY_DIR_ID]):
        await interaction.followup.send("âŒ Veuillez d'abord configurer les catÃ©gories avec `/setup_categories` !")
        return
    
    # Mapping grade -> catÃ©gorie
    grade_to_category = {
        "emt": CATEGORY_EMT_ID,
        "stg": CATEGORY_STG_ID,
        "int": CATEGORY_STG_ID,   # CompatibilitÃ© anciens channels [INT]
        "ads": CATEGORY_ADS_ID,
        "inf": CATEGORY_INF_ID,
        "psy": CATEGORY_PSY_ID,
        "med": CATEGORY_MED_ID,
        "cds": CATEGORY_CDS_ID,
        "dir": CATEGORY_DIR_ID
    }
    
    moved = []
    errors = []
    skipped = []
    
    # IDs des rÃ´les de grade
    role_to_grade = {
        895047492784238652: "emt",   # R_EMT
        838102445095256069: "stg",   # R_STG Stagiaire
        1088116715998687273: "ads",  # R_ADS
        894311352225656862: "inf",   # R_INF
        1528560704511148092: "psy",  # R_PSY Psychologue
        840288242547818507: "med",   # R_MED
        1528561040663777310: "cad",  # Chef Adjoint
        838102445095256071: "cds",   # Chef de Service
        1088570974603055195: "dir",  # R_DIR Directeur MÃ©dical
    }
    
    # Scanner tous les channels texte
    for channel in guild.text_channels:
        # VÃ©rifier si c'est un channel EMS (commence par un emoji)
        if len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            # Trouver le membre correspondant au channel via son nom
            ch_employee_key = get_channel_employee_key(channel)
            
            found_grade = None
            for member in guild.members:
                member_key = normalize_employee_key(get_clean_name(member))
                if member_key == ch_employee_key:
                    # Trouver le grade via les rÃ´les du membre
                    for role in member.roles:
                        if role.id in role_to_grade:
                            found_grade = role_to_grade[role.id]
                            break
                    break
            
            if found_grade:
                target_category_id = grade_to_category[found_grade]
                target_category = guild.get_channel(target_category_id)
                
                if target_category:
                    # VÃ©rifier si le channel est dÃ©jÃ  dans la bonne catÃ©gorie
                    if channel.category_id == target_category_id:
                        skipped.append(f"â­ï¸ {channel.mention} (dÃ©jÃ  dans {found_grade.upper()})")
                    else:
                        try:
                            await channel.edit(category=target_category)
                            moved.append(f"âœ… {channel.mention} â†’ {found_grade.upper()}")
                        except Exception as e:
                            errors.append(f"âŒ {channel.mention}: {e}")
                else:
                    errors.append(f"âŒ {channel.mention}: CatÃ©gorie {found_grade.upper()} introuvable")
            else:
                skipped.append(f"âš ï¸ {channel.mention} (grade non identifiÃ©)")
    
    # CrÃ©er le message de rÃ©ponse
    embed = discord.Embed(
        title="ðŸ”„ RÃ‰ORGANISATION DES CHANNELS",
        description="DÃ©placement automatique des channels dans leurs catÃ©gories respectives",
        color=EMS_RED
    )
    
    if moved:
        moved_text = "\n".join(moved[:25])  # Limiter Ã  25 pour ne pas dÃ©passer la limite
        if len(moved) > 25:
            moved_text += f"\n... et {len(moved) - 25} autres"
        embed.add_field(name=f"âœ… DÃ©placÃ©s ({len(moved)})", value=moved_text, inline=False)
    
    if skipped:
        skipped_text = "\n".join(skipped[:10])
        if len(skipped) > 10:
            skipped_text += f"\n... et {len(skipped) - 10} autres"
        embed.add_field(name=f"â­ï¸ IgnorÃ©s ({len(skipped)})", value=skipped_text, inline=False)
    
    if errors:
        errors_text = "\n".join(errors[:10])
        if len(errors) > 10:
            errors_text += f"\n... et {len(errors) - 10} autres"
        embed.add_field(name=f"âŒ Erreurs ({len(errors)})", value=errors_text, inline=False)
    
    if not moved and not skipped and not errors:
        embed.description = "Aucun channel EMS trouvÃ© Ã  rÃ©organiser."
    
    embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=embed)

@app_commands.checks.has_permissions(administrator=True)
async def synchronise(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        LOGS_SYNC_CHANNEL_ID = 1458464678542970983
        log_channel = bot.get_channel(LOGS_SYNC_CHANNEL_ID)
        
        if not log_channel:
            await interaction.followup.send(f"âŒ Channel de logs introuvable (ID: {LOGS_SYNC_CHANNEL_ID})")
            return
        
        # Calculer la date de hier 19h19
        now = now_paris()
        yesterday_19h19 = now.replace(hour=19, minute=19, second=0, microsecond=0) - timedelta(days=1)
        
        embed_progress = discord.Embed(
            title="ðŸ”„ SYNCHRONISATION EN COURS",
            description=f"Lecture des messages depuis **{yesterday_19h19.strftime('%d/%m/%Y Ã  %H:%M')}**...",
            color=EMS_RED
        )
        embed_progress.set_footer(text="ðŸš‘ EMS System")
        await interaction.followup.send(embed=embed_progress)
        
        # Charger les stats actuelles
        stats = load_stats()
        
        # Dictionnaire pour compter les +1 par employÃ©
        increments = {}
        message_count = 0
        
        # Lire les messages depuis hier 19h19
        async for message in log_channel.history(after=yesterday_19h19, limit=None):
            # Format attendu: "âœ… **employee_key** | X rÃ©as"
            if message.content.startswith("âœ… **") and " rÃ©as" in message.content:
                try:
                    # Extraire l'employÃ©
                    parts = message.content.split("**")
                    if len(parts) >= 3:
                        employee_key = parts[1].strip()
                        
                        # IncrÃ©menter le compteur pour cet employÃ©
                        if employee_key not in increments:
                            increments[employee_key] = 0
                        increments[employee_key] += 1
                        message_count += 1
                        
                except Exception as e:
                    continue
        
        # Appliquer les incrÃ©ments aux stats
        if increments:
            for employee_key, count in increments.items():
                if employee_key not in stats:
                    stats[employee_key] = 0
                stats[employee_key] += count
            
            # Sauvegarder les stats
            save_stats(stats)
            
            # CrÃ©er l'embed de rÃ©sultat
            embed_result = discord.Embed(
                title="âœ… SYNCHRONISATION TERMINÃ‰E",
                description=f"**{message_count} messages traitÃ©s**\n**{len(increments)} employÃ©s mis Ã  jour**",
                color=EMS_RED
            )
            
            # Afficher les modifications (limitÃ© Ã  25 champs)
            sorted_increments = sorted(increments.items(), key=lambda x: x[1], reverse=True)
            for i, (employee_key, count) in enumerate(sorted_increments[:25]):
                emoji = get_color_emoji(stats[employee_key])
                embed_result.add_field(
                    name=f"{emoji} {employee_key}",
                    value=f"+{count} â†’ {stats[employee_key]}/150",
                    inline=True
                )
            
            if len(increments) > 25:
                embed_result.add_field(
                    name="...",
                    value=f"Et {len(increments) - 25} autres employÃ©s",
                    inline=False
                )
            
            embed_result.set_footer(text=f"ðŸš‘ EMS System | SynchronisÃ© depuis {yesterday_19h19.strftime('%d/%m/%Y Ã  %H:%M')}")
            await interaction.edit_original_response(embed=embed_result)
        else:
            embed_empty = discord.Embed(
                title="âš ï¸ AUCUNE DONNÃ‰E",
                description=f"Aucun message de stats trouvÃ© depuis **{yesterday_19h19.strftime('%d/%m/%Y Ã  %H:%M')}**",
                color=EMS_RED
            )
            embed_empty.set_footer(text="ðŸš‘ EMS System")
            await interaction.edit_original_response(embed=embed_empty)
            
    except Exception as e:
        embed_error = discord.Embed(
            title="âŒ ERREUR",
            description=f"Une erreur est survenue lors de la synchronisation:\n```{str(e)}```",
            color=discord.Color.red()
        )
        embed_error.set_footer(text="ðŸš‘ EMS System")
        await interaction.followup.send(embed=embed_error)

# Totaux officiels au 19 aoÃ»t 2026 â€” utilisÃ©s par /remise
_REMISE_STATS = {
    "aya-perez": 408, "romain-romarin": 304, "alexendre-hunter": 182,
    "jose-de-maria": 154, "ytuka-labranche": 126, "teddy-coffe": 116,
    "lucas-moreau": 86, "clara-ino": 68, "thomas-lesner": 38,
    "elden-wallace": 36, "bart-junior": 32, "noah-kyo": 26,
    "amine-gouiri": 26, "ilyes-bentaleb": 26, "iss-montana": 2,
    "paul-fera": 2, "nollan-lopez": 2, "jackson-white": 2,
}

@bot.tree.command(name="remise", description="Remet les stats Ã  jour (totaux officiels) et met Ã  jour les channels")
@app_commands.checks.has_permissions(administrator=True)
async def remise(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    if not guild:
        await interaction.followup.send("âŒ Commande utilisable uniquement dans le serveur.", ephemeral=True)
        return

    # 1) Ã‰craser stats.json avec les totaux officiels
    save_stats(dict(_REMISE_STATS))

    # 2) Mettre Ã  jour les channels (emoji + description)
    updated, skipped = 0, 0
    for ch in guild.text_channels:
        if not ch.name or ch.name[0] not in ("ðŸ”´", "ðŸŸ ", "ðŸŸ¢"):
            continue
        key = get_channel_employee_key(ch)
        if key not in _REMISE_STATS:
            skipped += 1
            continue
        count = _REMISE_STATS[key]
        new_emoji = get_color_emoji(count)
        new_topic = f"{new_emoji} {count}/100"
        edit_args = {}
        if ch.name[0] != new_emoji:
            edit_args["name"] = f"{new_emoji}{ch.name[1:]}"
        if ch.topic != new_topic:
            edit_args["topic"] = new_topic
        if edit_args:
            try:
                await ch.edit(**edit_args)
                await asyncio.sleep(2)  # rate-limit Discord
                updated += 1
            except Exception as e:
                print(f"[remise] Erreur {key}: {repr(e)}")
        else:
            skipped += 1

    embed = discord.Embed(
        title="âœ… Remise Ã  jour effectuÃ©e",
        color=discord.Color.green()
    )
    embed.add_field(name="Channels mis Ã  jour", value=str(updated), inline=True)
    embed.add_field(name="InchangÃ©s / non trouvÃ©s", value=str(skipped), inline=True)
    embed.add_field(
        name="Totaux injectÃ©s",
        value="\n".join(f"{k.replace('-', ' ').title()} â†’ **{v}**" for k, v in sorted(_REMISE_STATS.items(), key=lambda x: -x[1])),
        inline=False
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# --- COMMANDE /REA - STATS PERSONNELLES ---
@bot.tree.command(name="rea", description="Affiche vos statistiques personnelles")
async def rea(interaction: discord.Interaction):
    """Affiche les stats de l'utilisateur avec graphique ASCII"""
    await interaction.response.defer(ephemeral=True)
    
    # RÃ©cupÃ©rer la clÃ© employÃ©
    user_display_name = interaction.user.display_name
    employee_key = normalize_employee_key(user_display_name)
    
    if not employee_key:
        await interaction.followup.send("âŒ Impossible de dÃ©terminer votre clÃ© employÃ©", ephemeral=True)
        return
    
    # Charger les donnÃ©es
    stats = load_stats()
    services = load_services()
    bonuses = load_bonuses()
    
    # RÃ©cupÃ©rer les stats de l'employÃ©
    current_reas = stats.get(employee_key, 0)
    total_bonuses = get_total_bonuses(employee_key)
    
    # RÃ©cupÃ©rer les heures de service
    week_key = get_week_start()
    week_services = services.get(week_key, {})
    week_data = week_services.get(employee_key, {})
    hours = week_data.get('total_hours', 0)
    reas_this_week = week_data.get('total_reas', 0)
    sessions = week_data.get('sessions', 0)
    
    # Formater les heures
    h = int(hours)
    m = int((hours - h) * 60)
    
    # CrÃ©er l'embed principal
    embed = discord.Embed(
        title=f"ðŸ“Š MES STATISTIQUES - {employee_key.upper().replace('-', ' ')}",
        color=EMS_RED
    )
    
    # Indicateur de progression
    emoji = get_color_emoji(current_reas)
    progression_bar = "â–ˆ" * (current_reas // 5) + "â–‘" * ((100 - current_reas) // 5)
    
    embed.add_field(
        name="ðŸŽ¯ RÃ‰ANIMATIONS TOTALES",
        value=f"{emoji} **{current_reas}/100**\n`{progression_bar}` ({current_reas}%)",
        inline=False
    )
    
    # Heures de service cette semaine
    embed.add_field(
        name="â±ï¸ HEURES DE SERVICE (SEMAINE)",
        value=f"**âŒš Total:** `{h}h{m:02d}`\n**ðŸš‘ RÃ©as:** `{reas_this_week}` rÃ©a(s)\n**ðŸ“ Sessions:** `{sessions}` session(s)",
        inline=False
    )
    
    # Moyenne par session
    if sessions > 0:
        avg_reas = reas_this_week / sessions
        embed.add_field(
            name="ðŸ“ˆ MOYENNES",
            value=f"**RÃ©as/session:** `{avg_reas:.1f}`\n**Temps/session:** `{(hours / sessions):.2f}h`",
            inline=False
        )
    
    # Graphique ASCII horizontal simple
    if current_reas > 0 or sessions > 0:
        graph_text = "```\n"
        graph_text += "PROGRESSION VERS 100 RÃ‰AS:\n"
        graph_text += progression_bar + f" {current_reas}/100\n"
        graph_text += "```"
        embed.add_field(
            name="ðŸ“‰ GRAPHIQUE",
            value=graph_text,
            inline=False
        )
    
    embed.set_footer(text="ðŸš‘ EMS System | Bonne chance!")
    embed.timestamp = now_paris()
    
    await interaction.followup.send(embed=embed, ephemeral=True)

# --- COMMANDE ANNONCE /REA ---
@app_commands.checks.has_permissions(administrator=True)
async def annonce_rea_command(interaction: discord.Interaction):
    """Poste une annonce expliquant comment utiliser /rea"""
    await interaction.response.defer()
    
    embed = discord.Embed(
        title="ðŸ“Š NOUVELLE COMMANDE: /rea",
        description="Consultez vos statistiques personnelles en temps rÃ©el!",
        color=discord.Color.from_rgb(220, 20, 60)
    )
    
    embed.add_field(
        name="ðŸŽ¯ Qu'est-ce que /rea?",
        value="La commande `/rea` vous permet de voir **Ã  tout moment** vos statistiques personnelles de rÃ©animations, heures de service, et progress vers votre quota.",
        inline=False
    )
    
    embed.add_field(
        name="ðŸ“‹ Informations affichÃ©es:",
        value="âœ… Nombre total de rÃ©as (progress vers 100)\nâœ… Heures de service cette semaine\nâœ… Nombre de services effectuÃ©s\nâœ… Moyennes (rÃ©as par session, heures par session)\nâœ… Barre de progression ASCII\nâœ… Indicateur couleur (ðŸ”´ðŸŸ ðŸŸ¢)",
        inline=False
    )
    
    embed.add_field(
        name="ðŸ’¡ Comment utiliser?",
        value="Tapez simplement `/rea` n'importe oÃ¹ sur le serveur\n*Le rÃ©sultat ne sera visible que par vous (message Ã©phÃ©mÃ¨re)*",
        inline=False
    )
    
    embed.add_field(
        name="ðŸ“ˆ Exemple de rÃ©sultat:",
        value="```\nðŸŽ¯ RÃ‰ANIMATIONS TOTALES\nðŸŸ  54/100\nâ–ˆâ–ˆâ–ˆâ–ˆâ–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘ (54%)\n\nâ±ï¸ HEURES DE SERVICE (SEMAINE)\nâŒš Total: 5h55\nðŸš‘ RÃ©as: 324 rÃ©a(s)\nðŸ“ Sessions: 13 session(s)\n```",
        inline=False
    )
    
    embed.add_field(
        name="ðŸŽ¨ LÃ©gende des couleurs:",
        value="ðŸ”´ **ROUGE** = Moins de 50 rÃ©as\nðŸŸ  **ORANGE** = Entre 50 et 99 rÃ©as\nðŸŸ¢ **VERT** = 100 rÃ©as ou plus",
        inline=False
    )
    
    embed.add_field(
        name="âš¡ Conseils:",
        value="â€¢ Utilisez `/rea` rÃ©guliÃ¨rement pour suivre votre progress\nâ€¢ VÃ©rifiez votre position dans le classement\nâ€¢ Communiquez sur vos stats avec vos collÃ¨gues\nâ€¢ Travaillez ensemble pour atteindre les quotas!",
        inline=False
    )
    
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1458228261166518293/1458240230001086524/ambulance-emoji.png")
    embed.set_footer(text="ðŸš‘ EMS System | Version 2.0")
    embed.timestamp = now_paris()
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="cv", description="Ajoute des rÃ©animations (Ã  utiliser dans votre channel personnel)")
@app_commands.describe(nombre="Nombre de rÃ©as Ã  ajouter")
@app_commands.checks.has_permissions(administrator=True)
async def cv_command(interaction: discord.Interaction, nombre: int):
    """Ajoute des rÃ©as depuis le channel personnel"""
    await interaction.response.defer(ephemeral=True)
    
    # VÃ©rifier que c'est dans un channel EMS
    channel = interaction.channel
    if not channel or not (channel.name and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]):
        await interaction.followup.send("âŒ Cette commande ne fonctionne que dans votre channel personnel EMS", ephemeral=True)
        return
    
    if nombre <= 0 or nombre > 500:
        await interaction.followup.send("âŒ Le nombre doit Ãªtre entre 1 et 500", ephemeral=True)
        return
    
    # RÃ©cupÃ©rer la clÃ© employÃ©
    employee_key = get_channel_employee_key(channel)
    if not employee_key:
        await interaction.followup.send("âŒ Impossible de dÃ©terminer votre clÃ© employÃ©", ephemeral=True)
        return
    
    # Charger et mettre Ã  jour les stats
    stats = load_stats()
    old_value = stats.get(employee_key, 0)
    new_value = old_value + nombre
    stats[employee_key] = new_value
    save_stats(stats)
    
    # Envoyer la confirmation
    emoji = get_color_emoji(new_value)
    embed = discord.Embed(
        title="âœ… RÃ‰AS AJOUTÃ‰ES",
        description=f"**+{nombre} rÃ©as** pour {employee_key.replace('-', ' ').title()}",
        color=EMS_RED
    )
    embed.add_field(
        name="ðŸ“Š Progression",
        value=f"Avant: {old_value}/100\nAprÃ¨s: {new_value}/100 {emoji}",
        inline=False
    )
    embed.set_footer(text="ðŸš‘ EMS System | Stats mises Ã  jour")
    embed.timestamp = now_paris()
    
    await interaction.followup.send(embed=embed, ephemeral=True)
    
    # Mettre Ã  jour la description du channel
    try:
        new_emoji = get_color_emoji(new_value)
        description = f"{new_emoji} {new_value}/100"
        await channel.edit(topic=description)
    except:
        pass

# --- COMMANDE RETRAIT - RETIRER DES RÃ‰AS ---
@bot.tree.command(name="retrait", description="Retire des rÃ©animations (corrections/erreurs)")
@app_commands.describe(nombre="Nombre de rÃ©as Ã  retirer")
@app_commands.checks.has_permissions(administrator=True)
async def retrait_command(interaction: discord.Interaction, nombre: int):
    """Retire des rÃ©as depuis le channel personnel"""
    await interaction.response.defer(ephemeral=True)
    
    # VÃ©rifier que c'est dans un channel EMS
    channel = interaction.channel
    if not channel or not (channel.name and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]):
        await interaction.followup.send("âŒ Cette commande ne fonctionne que dans votre channel personnel EMS", ephemeral=True)
        return
    
    if nombre <= 0 or nombre > 500:
        await interaction.followup.send("âŒ Le nombre doit Ãªtre entre 1 et 500", ephemeral=True)
        return
    
    # RÃ©cupÃ©rer la clÃ© employÃ©
    employee_key = get_channel_employee_key(channel)
    if not employee_key:
        await interaction.followup.send("âŒ Impossible de dÃ©terminer votre clÃ© employÃ©", ephemeral=True)
        return
    
    # Charger et mettre Ã  jour les stats
    stats = load_stats()
    old_value = stats.get(employee_key, 0)
    new_value = max(0, old_value - nombre)  # Ne pas descendre en dessous de 0
    actual_removed = old_value - new_value
    stats[employee_key] = new_value
    save_stats(stats)
    
    # Envoyer la confirmation
    emoji = get_color_emoji(new_value)
    embed = discord.Embed(
        title="ðŸ”´ RÃ‰AS RETIRÃ‰ES",
        description=f"**-{actual_removed} rÃ©as** pour {employee_key.replace('-', ' ').title()}",
        color=discord.Color.from_rgb(255, 100, 100)
    )
    embed.add_field(
        name="ðŸ“Š Progression",
        value=f"Avant: {old_value}/100\nAprÃ¨s: {new_value}/100 {emoji}",
        inline=False
    )
    if actual_removed < nombre:
        embed.add_field(
            name="âš ï¸ Note",
            value=f"Seul {actual_removed} rÃ©as ont pu Ãªtre retirÃ©(es) (limite 0 minimum)",
            inline=False
        )
    embed.set_footer(text="ðŸš‘ EMS System | Correction effectuÃ©e")
    embed.timestamp = now_paris()
    
    await interaction.followup.send(embed=embed, ephemeral=True)
    
    # Mettre Ã  jour la description du channel
    try:
        new_emoji = get_color_emoji(new_value)
        description = f"{new_emoji} {new_value}/100"
        await channel.edit(topic=description)
    except:
        pass

# --- COMMANDE PRIME (AJOUT/RETRAIT MANUEL) ---
@bot.tree.command(name="prime", description="Ajoute ou enlÃ¨ve des primes manuellement (admin)")
@app_commands.describe(
    employe="Nom de l'employÃ© (ex: samara-ezio)",
    nombre="Nombre de primes Ã  ajouter (nÃ©gatif pour enlever, ex: -2)"
)
@app_commands.checks.has_permissions(administrator=True)
async def prime(interaction: discord.Interaction, employe: str, nombre: int):
    """Ajoute ou enlÃ¨ve manuellement des primes pour un employÃ©"""
    await interaction.response.defer(ephemeral=True)
    
    # Normaliser le nom de l'employÃ©
    employee_key = normalize_employee_key(employe)
    
    if not employee_key:
        await interaction.followup.send("âŒ Nom d'employÃ© invalide", ephemeral=True)
        return
    
    if nombre == 0 or abs(nombre) > 100:
        await interaction.followup.send("âŒ Le nombre doit Ãªtre entre -100 et 100 (pas 0)", ephemeral=True)
        return
    
    # Charger les primes
    bonuses = load_bonuses()
    today = now_paris().strftime("%Y-%m-%d")
    
    # DÃ©terminer l'action
    if nombre > 0:
        # --- AJOUTER DES PRIMES ---
        added_count = 0
        for i in range(nombre):
            bonus_key = f"{employee_key}_{today}_{i}"  # ClÃ© unique pour Ã©viter les doublons
            if bonus_key not in bonuses:
                bonuses[bonus_key] = 1
                added_count += 1
        
        action_text = "AJOUTÃ‰ES"
        count_change = added_count
    else:
        # --- ENLEVER DES PRIMES ---
        primes_to_remove = abs(nombre)
        removed_count = 0
        
        # Trouver et supprimer les primes de cet employÃ©
        keys_to_delete = []
        for key in bonuses.keys():
            if key.startswith(f"{employee_key}_"):
                keys_to_delete.append(key)
                removed_count += 1
                if removed_count >= primes_to_remove:
                    break
        
        for key in keys_to_delete:
            del bonuses[key]
        
        action_text = "SUPPRIMÃ‰ES"
        count_change = removed_count
    
    # Sauvegarder
    save_bonuses(bonuses)
    
    # RÃ©cupÃ©rer le total des primes
    total_bonuses = get_total_bonuses(employee_key)
    
    # Envoyer la confirmation
    embed = discord.Embed(
        title=f"ðŸ’° PRIMES {action_text}",
        description=f"{'**+' if nombre > 0 else '**-'}{count_change} prime(s)** pour {employee_key.replace('-', ' ').title()}",
        color=discord.Color.from_rgb(255, 200, 0) if nombre > 0 else discord.Color.from_rgb(255, 100, 100)
    )
    embed.add_field(
        name="ðŸ“Š Total des primes",
        value=f"**{total_bonuses}M** primes accumulÃ©es",
        inline=False
    )
    action_desc = "ajoutÃ©e(s) manuellement" if nombre > 0 else "supprimÃ©e(s) manuellement"
    embed.set_footer(text=f"ðŸš‘ EMS System | Prime(s) {action_desc}")
    embed.timestamp = now_paris()
    
    await interaction.followup.send(embed=embed, ephemeral=True)

# --- COMMANDE STATS AVEC GRAPHIQUE ---
@bot.tree.command(name="stats", description="Affiche les statistiques avec graphique ASCII")
@app_commands.checks.has_permissions(administrator=True)
async def stats_command(interaction: discord.Interaction):
    """Affiche les stats complÃ¨tes des rÃ©as avec graphique"""
    await interaction.response.defer()
    
    stats = load_stats()
    if not stats:
        await interaction.followup.send("âŒ Aucune donnÃ©e disponible")
        return
    
    # Trier par rÃ©as dÃ©croissants
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    max_value = max(stats.values()) if stats else 100
    
    # CrÃ©er le graphique ASCII
    graph_text = "```\n"
    graph_text += "STATISTIQUES RÃ‰AS\n"
    graph_text += "=" * 50 + "\n\n"
    
    for i, (key, value) in enumerate(sorted_stats, 1):
        emoji = get_color_emoji(value)
        bar_length = int((value / max(max_value, 100)) * 25)  # Max 25 caractÃ¨res
        bar = "â–ˆ" * bar_length + "â–‘" * (25 - bar_length)
        
        # Normaliser le nom pour affichage
        display_name = key.replace("-", " ").title()
        graph_text += f"{i:2}. {emoji} {display_name:<20} â”‚ {bar} â”‚ {value}/100\n"
    
    graph_text += "\n" + "=" * 50 + "\n"
    graph_text += f"Total: {sum(stats.values())} rÃ©as | {len(stats)} employÃ©s\n```"
    
    # CrÃ©er l'embed
    embed = discord.Embed(
        title="ðŸ“Š Statistiques EMS",
        description=graph_text,
        color=EMS_DARK_RED
    )
    
    # Ajouter les heures de service
    services = load_services()
    week = get_week_start()
    week_services = services.get(week, {})
    if week_services:
        svc_text = ""
        sorted_svc = sorted(week_services.items(), key=lambda x: x[1]['total_hours'], reverse=True)
        for emp_key, data in sorted_svc:
            h = int(data['total_hours'])
            m = int((data['total_hours'] - h) * 60)
            display = emp_key.replace('-', ' ').title()
            svc_text += f"â€¢ **{display}** : {h}h{m:02d} ({data['total_reas']} rÃ©as)\n"
        embed.add_field(name="â±ï¸ Heures de service", value=svc_text, inline=False)
    
    if active_services:
        en_svc = ""
        for uid, svc in active_services.items():
            start_t = datetime.fromisoformat(svc['start'])
            mins = int((now_paris() - start_t).total_seconds() // 60)
            en_svc += f"â€¢ **{svc['employee_key']}** - {mins} min\n"
        embed.add_field(name="ðŸŸ¢ En service", value=en_svc, inline=False)
    
    embed.set_footer(text=f"Mise Ã  jour: {now_paris().strftime('%d/%m/%Y %H:%M')}")
    
    await interaction.followup.send(embed=embed)

# --- COMMANDE LEADERBOARD AVEC ANNONCE ---

# --- MODAL POUR LES AVIS ---
class AvisModal(discord.ui.Modal, title="ðŸ“ Donner un Avis"):
    """Modal pour soumettre un avis sur un employÃ©"""
    
    # SÃ©lection de l'employÃ©
    employee = discord.ui.TextInput(
        label="EmployÃ© concernÃ©",
        placeholder="SÃ©lectionnez l'employÃ©...",
        required=True
    )
    
    # Notation (1-5 Ã©toiles)
    stars = discord.ui.TextInput(
        label="Nombre d'Ã©toiles (1-5)",
        placeholder="Entrez un chiffre de 1 Ã  5",
        required=True,
        min_length=1,
        max_length=1
    )
    
    # Raison (optionnel)
    raison = discord.ui.TextInput(
        label="Raison (optionnel)",
        placeholder="DÃ©crivez votre avis...",
        required=False,
        style=discord.TextStyle.long,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Quand l'utilisateur soumet le formulaire"""
        try:
            # Valider les Ã©toiles
            try:
                star_count = int(self.stars.value)
                if star_count < 1 or star_count > 5:
                    await interaction.response.send_message(
                        "âŒ Le nombre d'Ã©toiles doit Ãªtre entre 1 et 5",
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "âŒ Veuillez entrer un chiffre valide (1-5)",
                    ephemeral=True
                )
                return
            
            # CrÃ©er l'embed de l'avis
            embed = discord.Embed(
                title="â­ Nouvel Avis ReÃ§u",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="EmployÃ©", value=self.employee.value, inline=False)
            embed.add_field(name="Note", value="â­" * star_count, inline=True)
            embed.add_field(name="Raison", value=self.raison.value or "Aucune raison donnÃ©e", inline=False)
            embed.add_field(name="Auteur", value=interaction.user.mention, inline=True)
            embed.set_footer(text=f"Avis soumis le {now_paris().strftime('%d/%m/%Y Ã  %H:%M')}")
            
            # Envoyer dans le channel des avis
            avis_channel = bot.get_channel(AVIS_CHANNEL_ID)
            if avis_channel:
                await avis_channel.send(embed=embed)
            
            await interaction.response.send_message(
                "âœ… Votre avis a Ã©tÃ© enregistrÃ© avec succÃ¨s !",
                ephemeral=True
            )
        except Exception as e:
            print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur avis: {e}")
            await interaction.response.send_message(
                f"âŒ Erreur: {e}",
                ephemeral=True
            )

# --- BOUTON POUR DONNER UN AVIS ---
class AvisButton(discord.ui.View):
    """Bouton pour ouvrir le formulaire d'avis"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="ðŸ“ Donner un Avis", style=discord.ButtonStyle.primary)
    async def avis_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ouvre le modal pour donner un avis"""
        
        # Construire la liste des employÃ©s
        stats = load_stats()
        employee_list = "\n".join([
            f"â€¢ {key.replace('-', ' ').title()}"
            for key in sorted(stats.keys())
        ])
        
        # Montrer la liste des employÃ©s dans le placeholder
        modal = AvisModal()
        modal.employee.placeholder = f"Exemples: {', '.join(list(stats.keys())[:3])}..."
        
        await interaction.response.send_modal(modal)

# --- COMMANDE AVIS ---
@bot.tree.command(name="avis", description="Envoie une annonce pour recueillir des avis sur les employÃ©s")
@app_commands.checks.has_permissions(administrator=True)
async def avis_command(interaction: discord.Interaction):
    """Lance une campagne d'avis pour les employÃ©s"""
    await interaction.response.defer()
    
    try:
        # CrÃ©er l'embed d'annonce
        embed = discord.Embed(
            title="ðŸ“ Campagne d'Avis - Vos Retours Sont Importants",
            description="Aidez-nous Ã  amÃ©liorer notre Ã©quipe en partageant vos avis sur les employÃ©s.\n\n"
                       "**Comment Ã§a fonctionne ?**\n"
                       "1ï¸âƒ£ Appuyez sur le bouton ci-dessous\n"
                       "2ï¸âƒ£ SÃ©lectionnez un employÃ©\n"
                       "3ï¸âƒ£ Donnez une note de 1 Ã  5 Ã©toiles\n"
                       "4ï¸âƒ£ Laissez un commentaire (optionnel)\n\n"
                       "Vos avis sont importants pour l'Ã©volution de chacun. Merci ! âœ¨",
            color=discord.Color.gold()
        )
        
        embed.set_footer(text="ðŸš‘ EMS System | Vos avis comptent")
        
        # Envoyer dans le channel des avis avec ping du role citoyen
        avis_channel = bot.get_channel(AVIS_CHANNEL_ID)
        if avis_channel:
            ping_msg = f"<@&{CITOYEN_ROLE_ID}>" if CITOYEN_ROLE_ID != 0 else ""
            await avis_channel.send(ping_msg, embed=embed, view=AvisButton())
            await interaction.followup.send("âœ… Annonce des avis lancÃ©e !")
        else:
            await interaction.followup.send("âŒ Channel des avis non trouvÃ©")
        
    except Exception as e:
        print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur avis command: {e}")
        await interaction.followup.send(f"âŒ Erreur: {e}")

# --- MODAL POUR LES DISPONIBILITÃ‰S (CV) ---
class CVDispoModal(discord.ui.Modal, title="ðŸ“… Indiquer mes DisponibilitÃ©s"):
    """Modal pour soumettre ses disponibilitÃ©s aprÃ¨s acceptation CV"""
    
    def __init__(self, target_user):
        super().__init__()
        self.target_user = target_user
    
    # DisponibilitÃ©s
    disponibilites = discord.ui.TextInput(
        label="Vos disponibilitÃ©s",
        placeholder="Ex: Lundi 10h-18h, Mardi 14h-22h, Dimanche fermÃ©",
        required=True,
        style=discord.TextStyle.long,
        max_length=500
    )
    
    # Notes (optionnel)
    notes = discord.ui.TextInput(
        label="Notes additionnelles (optionnel)",
        placeholder="Ex: Pas disponible le 8 mars, prÃ©fÃ©rence horaires...",
        required=False,
        style=discord.TextStyle.long,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Quand l'utilisateur soumet ses dispo aprÃ¨s acceptation CV"""
        try:
            # RÃ©cupÃ©rer le pseudonyme du serveur (pas le nom Discord)
            guild = bot.get_guild(config["GUILD_ID"])
            member = guild.get_member(self.target_user.id)
            user_name = member.display_name if member else self.target_user.name
            
            # CrÃ©er l'embed de la dispo
            embed = discord.Embed(
                title="ðŸ“… Nouvelle DisponibilitÃ© Soumise (CV acceptÃ©)",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Personne", value=f"{self.target_user.mention} ({user_name})", inline=False)
            embed.add_field(name="DisponibilitÃ©s", value=self.disponibilites.value, inline=False)
            if self.notes.value:
                embed.add_field(name="Notes", value=self.notes.value, inline=False)
            embed.set_footer(text=f"ReÃ§u le {now_paris().strftime('%d/%m/%Y Ã  %H:%M')}")
            
            # Envoyer dans le channel de demande avec boutons de confirmation pour la direction
            request_channel = bot.get_channel(DISPO_REQUEST_CHANNEL_ID)
            if request_channel:
                # CrÃ©er les boutons de confirmation/refus
                view = discord.ui.View()
                confirm_btn = discord.ui.Button(label="âœ… Confirmer", style=discord.ButtonStyle.green)
                refuse_btn = discord.ui.Button(label="âŒ Refuser", style=discord.ButtonStyle.red)
                
                async def confirm_callback(interaction_confirm: discord.Interaction):
                    # DEFER IMMÃ‰DIATEMENT pour Ã©viter le timeout
                    await interaction_confirm.response.defer()
                    
                    # VÃ©rifier que seul la direction peut confirmer
                    if not any(role.id == DIRECTION_ROLE_ID for role in interaction_confirm.user.roles):
                        await interaction_confirm.followup.send(
                            "âŒ Seule la direction peut valider les disponibilitÃ©s !",
                            ephemeral=True
                        )
                        return
                    
                    # DÃ©sactiver les boutons
                    confirm_btn.disabled = True
                    refuse_btn.disabled = True
                    await interaction_confirm.message.edit(view=view)
                    
                    # Envoyer un DM de confirmation
                    try:
                        embed_dm = discord.Embed(
                            title="ðŸ“… âœ… Vos DisponibilitÃ©s ont Ã©tÃ© ConfirmÃ©es",
                            description=f"Bonjour {user_name},\n\nVos disponibilitÃ©s ont Ã©tÃ© validÃ©es par la direction !\n\nVos dispo:\n{self.disponibilites.value}\n\nEn attente de recrutement...",
                            color=discord.Color.green()
                        )
                        embed_dm.set_footer(text="ðŸš‘ EMS System | Confirmation dispo")
                        
                        user = bot.get_user(self.target_user.id)
                        if user:
                            await user.send(embed=embed_dm)
                    except:
                        pass
                    
                    # Envoyer un message de recrutement dans le channel de recrutement
                    recruitment_channel = bot.get_channel(DISPO_CHANNEL_ID)
                    if recruitment_channel:
                        embed_recrutement = discord.Embed(
                            title="ðŸ‘¤ Candidature ApprouvÃ©e - DÃ©cision de Recrutement",
                            description=f"**{self.target_user.mention}** a Ã©tÃ© approuvÃ©(e) par la direction (CV + Dispo).\n\n"
                                       f"DisponibilitÃ©s:\n{self.disponibilites.value}",
                            color=discord.Color.blue()
                        )
                        
                        # Boutons Recruter/Refuser
                        recrutement_view = discord.ui.View()
                        recruter_btn = discord.ui.Button(label="âœ… Recruter", style=discord.ButtonStyle.green)
                        refuser_btn = discord.ui.Button(label="âŒ Refuser", style=discord.ButtonStyle.red)
                        
                        async def recruter_callback(interaction_recrutement: discord.Interaction):
                            # DEFER IMMÃ‰DIATEMENT pour Ã©viter le timeout (3 secondes)
                            await interaction_recrutement.response.defer()
                            
                            # VÃ©rifier que seul la direction peut recruter
                            if not any(role.id == DIRECTION_ROLE_ID for role in interaction_recrutement.user.roles):
                                await interaction_recrutement.followup.send(
                                    "âŒ Seule la direction peut recruter !",
                                    ephemeral=True
                                )
                                return
                            
                            try:
                                guild = bot.get_guild(config["GUILD_ID"])
                                member = guild.get_member(self.target_user.id)
                                
                                if member:
                                    # Enregistrer la date d'embauche
                                    try:
                                        set_embauche_date(normalize_employee_key(member.display_name))
                                    except Exception:
                                        pass

                                    # Retirer le rÃ´le pending
                                    try:
                                        role_pending = guild.get_role(ROLE_PENDING_ID)
                                        if role_pending:
                                            await member.remove_roles(role_pending)
                                    except:
                                        pass
                                    
                                    # Ajouter les rÃ´les EMS
                                    roles_to_add = [
                                        guild.get_role(ROLE_EMT_1),
                                        guild.get_role(ROLE_EMT_2),
                                        guild.get_role(ROLE_EMT_3)
                                    ]
                                    roles_to_add = [r for r in roles_to_add if r]
                                    
                                    if roles_to_add:
                                        await member.add_roles(*roles_to_add)

                                    # Attribuer automatiquement les formations Scout et Alamo Ã  l'embauche EMT
                                    try:
                                        auto_formation_roles = [
                                            guild.get_role(1528837812793901207),  # Formation Scout
                                            guild.get_role(1528838179061367015),  # Formation Alamo
                                        ]
                                        auto_formation_roles = [r for r in auto_formation_roles if r]
                                        if auto_formation_roles:
                                            await member.add_roles(*auto_formation_roles)
                                    except Exception as _af_err:
                                        print(f"Erreur attribution formations auto EMT: {_af_err}")

                                    # Ajouter le prÃ©fixe [EMT]
                                    try:
                                        new_nick = f"[EMT] {user_name}"
                                        await member.edit(nick=new_nick)
                                    except:
                                        pass
                                    
                                    # CrÃ©er le channel privÃ© avec emoji + nom dans la catÃ©gorie
                                    try:
                                        category = guild.get_channel(CATEGORY_EMT_ID)
                                        
                                        channel_name = f"ðŸ”´{user_name.lower().replace(' ', '-')}"
                                        
                                        # Obtenir les permissions pour le channel
                                        overwrites = {
                                            guild.default_role: discord.PermissionOverwrite(view_channel=False),
                                            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                                            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                                        }
                                        
                                        # CrÃ©er le channel dans la catÃ©gorie
                                        new_channel = await guild.create_text_channel(
                                            channel_name,
                                            overwrites=overwrites,
                                            category=category
                                        )
                                        
                                        # Message de bienvenue dans le channel avec mention
                                        embed_channel = discord.Embed(
                                            title=f"ðŸŽ‰ Bienvenue {user_name} !",
                                            description=f"Bienvenue dans ton channel personnel.\n\nTu as Ã©tÃ© recrutÃ©(e) en tant que **[EMT]**.\n\nVoici tes disponibilitÃ©s:\n{self.disponibilites.value}",
                                            color=discord.Color.green()
                                        )
                                        await new_channel.send(f"{member.mention}", embed=embed_channel)
                                    except Exception as e:
                                        print(f"[{now_paris().strftime('%H:%M:%S')}] âš ï¸ Erreur crÃ©ation channel: {e}")
                                    
                                    # Message de confirmation
                                    embed_recrute = discord.Embed(
                                        title="âœ… Recrutement EffectuÃ©",
                                        description=f"**{user_name}** a Ã©tÃ© recrutÃ©(e) en tant que **[EMT]**.",
                                        color=discord.Color.green()
                                    )
                                    await interaction_recrutement.followup.send(embed=embed_recrute, ephemeral=True)
                                    
                                    # DM de bienvenue
                                    try:
                                        embed_welcome = discord.Embed(
                                            title="ðŸŽ‰ Bienvenue dans l'EMS !",
                                            description=f"FÃ©licitations {user_name} !\n\nVous avez Ã©tÃ© recrutÃ©(e) en tant que **[EMT]**.\n\nUn channel privÃ© a Ã©tÃ© crÃ©Ã© pour vous : **{channel_name}**",
                                            color=discord.Color.green()
                                        )
                                        user_obj = bot.get_user(self.target_user.id)
                                        if user_obj:
                                            await user_obj.send(embed=embed_welcome)
                                    except:
                                        pass
                                    
                                    # DÃ©sactiver les boutons
                                    recruter_btn.disabled = True
                                    refuser_btn.disabled = True
                                    await interaction_recrutement.message.edit(view=recrutement_view)
                                    
                                    # Ajouter rÃ©action âœ…
                                    if hasattr(interaction_recrutement.message, 'add_reaction'):
                                        await interaction_recrutement.message.add_reaction("âœ…")
                            except Exception as e:
                                print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur recrutement: {e}")
                                await interaction_recrutement.followup.send(f"âŒ Erreur: {e}", ephemeral=True)
                        
                        async def refuser_recrutement_callback(interaction_refus: discord.Interaction):
                            # DEFER IMMÃ‰DIATEMENT pour Ã©viter le timeout
                            await interaction_refus.response.defer()
                            
                            # VÃ©rifier que seul la direction peut refuser
                            if not any(role.id == DIRECTION_ROLE_ID for role in interaction_refus.user.roles):
                                await interaction_refus.followup.send(
                                    "âŒ Seule la direction peut refuser !",
                                    ephemeral=True
                                )
                                return
                            
                            try:
                                guild = bot.get_guild(config["GUILD_ID"])
                                member = guild.get_member(self.target_user.id)
                                
                                if member:
                                    # Retirer tous les rÃ´les sauf citoyen
                                    for role in member.roles:
                                        if role.id in [ROLE_EMT_1, ROLE_EMT_2, ROLE_EMT_3, ROLE_PENDING_ID] and role.id != ROLE_CITOYEN:
                                            try:
                                                await member.remove_roles(role)
                                            except:
                                                pass
                                    
                                    # Retirer le pseudo du serveur
                                    try:
                                        await member.edit(nick=None)
                                    except:
                                        pass
                                    
                                    # Message de refus
                                    embed_refuse = discord.Embed(
                                        title="âŒ Candidature RefusÃ©e",
                                        description=f"**{user_name}** a Ã©tÃ© refusÃ©(e) au recrutement.",
                                        color=discord.Color.red()
                                    )
                                    await interaction_refus.followup.send(embed=embed_refuse, ephemeral=True)
                                    
                                    # DM de refus
                                    try:
                                        embed_refuse_dm = discord.Embed(
                                            title="âŒ Candidature RefusÃ©e",
                                            description=f"Nous sommes dÃ©solÃ©s {user_name},\n\nVotre candidature au recrutement EMS a Ã©tÃ© refusÃ©e.\n\nVous pourrez rÃ©essayer dans 1 semaine.",
                                            color=discord.Color.red()
                                        )
                                        user_obj = bot.get_user(self.target_user.id)
                                        if user_obj:
                                            await user_obj.send(embed=embed_refuse_dm)
                                    except:
                                        pass

                                    # Blacklist CV automatique sur refus dispo
                                    try:
                                        bl = load_blacklist_cv()
                                        bl[str(self.target_user.id)] = {
                                            "date": datetime.utcnow().isoformat(),
                                            "raison": "Candidature refusÃ©e par la direction (dispo)",
                                            "blacklisted_by": str(interaction_refus.user.id),
                                        }
                                        save_blacklist_cv(bl)
                                    except Exception as _bl2:
                                        print(f"Erreur blacklist CV refus dispo: {_bl2}")

                                    # DÃ©sactiver les boutons
                                    recruter_btn.disabled = True
                                    refuser_btn.disabled = True
                                    await interaction_refus.message.edit(view=recrutement_view)
                                    
                                    # Ajouter rÃ©action âŒ
                                    if hasattr(interaction_refus.message, 'add_reaction'):
                                        await interaction_refus.message.add_reaction("âŒ")
                            except Exception as e:
                                print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur refus recrutement: {e}")
                                await interaction_refus.followup.send(f"âŒ Erreur: {e}", ephemeral=True)
                        
                        recruter_btn.callback = recruter_callback
                        refuser_btn.callback = refuser_recrutement_callback
                        recrutement_view.add_item(recruter_btn)
                        recrutement_view.add_item(refuser_btn)
                        
                        # Ping la personne qui a soumis la dispo et celle qui a acceptÃ©
                        ping_msg = f"{self.target_user.mention} {interaction_confirm.user.mention}"
                        await recruitment_channel.send(ping_msg, embed=embed_recrutement, view=recrutement_view)
                    
                    # Ajouter une rÃ©action pour marquer comme confirmÃ©e
                    if hasattr(interaction_confirm.message, 'add_reaction'):
                        await interaction_confirm.message.add_reaction("âœ…")
                
                async def refuse_callback(interaction_refuse: discord.Interaction):
                    # DEFER IMMÃ‰DIATEMENT pour Ã©viter le timeout
                    await interaction_refuse.response.defer()
                    
                    # VÃ©rifier que seul la direction peut refuser
                    if not any(role.id == DIRECTION_ROLE_ID for role in interaction_refuse.user.roles):
                        await interaction_refuse.followup.send(
                            "âŒ Seule la direction peut refuser !",
                            ephemeral=True
                        )
                        return
                    
                    # Message de refus Ã  la direction
                    embed_refuse = discord.Embed(
                        title="âŒ DisponibilitÃ©s RefusÃ©es",
                        description=f"Les dispo de {user_name} ont Ã©tÃ© dÃ©clinÃ©es.",
                        color=discord.Color.red()
                    )
                    await interaction_refuse.followup.send(embed=embed_refuse, ephemeral=True)
                    
                    # DÃ©sactiver les boutons
                    confirm_btn.disabled = True
                    refuse_btn.disabled = True
                    await interaction_refuse.message.edit(view=view)
                    
                    # Envoyer un DM de rappel/refus Ã  l'utilisateur
                    try:
                        embed_dm = discord.Embed(
                            title="ðŸ“… âŒ DisponibilitÃ©s RefusÃ©es",
                            description=f"Bonjour {user_name},\n\nVos disponibilitÃ©s ont Ã©tÃ© refusÃ©es.\n\nVeuillez cliquer sur le bouton pour les remettre Ã  jour.",
                            color=discord.Color.red()
                        )
                        embed_dm.set_footer(text="ðŸš‘ EMS System | Nouvelle tentative")
                        
                        # CrÃ©er une classe pour le bouton retry
                        class RetryDispoButton(discord.ui.View):
                            def __init__(self):
                                super().__init__(timeout=None)
                            
                            @discord.ui.button(label="ðŸ“… Remettre mes DisponibilitÃ©s", style=discord.ButtonStyle.primary)
                            async def retry_dispo_button(self, btn_interaction: discord.Interaction, btn: discord.ui.Button):
                                """Ouvre le modal pour remettre ses dispo"""
                                modal = CVDispoModal(target_user=self.target_user)
                                await btn_interaction.response.send_modal(modal)
                        
                        retry_view = RetryDispoButton()
                        retry_view.target_user = self.target_user
                        user = bot.get_user(self.target_user.id)
                        if user:
                            await user.send(embed=embed_dm, view=retry_view)
                    except:
                        pass
                    
                    # Ajouter une rÃ©action pour marquer comme refusÃ©e
                    if hasattr(interaction_refuse.message, 'add_reaction'):
                        await interaction_refuse.message.add_reaction("âŒ")
                
                confirm_btn.callback = confirm_callback
                refuse_btn.callback = refuse_callback
                view.add_item(confirm_btn)
                view.add_item(refuse_btn)
                
                ping_msg = f"<@&{DIRECTION_ROLE_ID}>"
                await request_channel.send(ping_msg, embed=embed, view=view)
            
            await interaction.response.send_message(
                "âœ… Vos disponibilitÃ©s ont Ã©tÃ© soumises avec succÃ¨s !",
                ephemeral=True
            )
        except Exception as e:
            print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur dispo CV: {e}")
            await interaction.response.send_message(
                f"âŒ Erreur: {e}",
                ephemeral=True
            )

# --- MODAL POUR LES DISPONIBILITÃ‰S ---
class DispoModal(discord.ui.Modal, title="ðŸ“… Mettre Ã  Jour mes DisponibilitÃ©s"):
    """Modal pour soumettre ses disponibilitÃ©s"""
    
    # DisponibilitÃ©s
    disponibilites = discord.ui.TextInput(
        label="Vos disponibilitÃ©s",
        placeholder="Ex: Lundi 10h-18h, Mardi 14h-22h, Dimanche fermÃ©",
        required=True,
        style=discord.TextStyle.long,
        max_length=500
    )
    
    # Notes (optionnel)
    notes = discord.ui.TextInput(
        label="Notes additionnelles (optionnel)",
        placeholder="Ex: Pas disponible le 8 mars, prÃ©fÃ©rence horaires...",
        required=False,
        style=discord.TextStyle.long,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Quand l'utilisateur soumet ses disponibilitÃ©s"""
        try:
            # RÃ©cupÃ©rer le pseudonyme du serveur (pas le nom Discord)
            guild = bot.get_guild(config["GUILD_ID"])
            member = guild.get_member(interaction.user.id)
            user_name = member.display_name if member else interaction.user.name
            
            # CrÃ©er l'embed de la dispo
            embed = discord.Embed(
                title="ðŸ“… Nouvelle DisponibilitÃ© Soumise",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Personne", value=f"{interaction.user.mention} ({user_name})", inline=False)
            embed.add_field(name="DisponibilitÃ©s", value=self.disponibilites.value, inline=False)
            if self.notes.value:
                embed.add_field(name="Notes", value=self.notes.value, inline=False)
            embed.set_footer(text=f"ReÃ§u le {now_paris().strftime('%d/%m/%Y Ã  %H:%M')}")
            
            # Envoyer dans le channel de demande avec boutons de confirmation pour la direction
            request_channel = bot.get_channel(DISPO_REQUEST_CHANNEL_ID)
            if request_channel:
                # CrÃ©er les boutons de confirmation/refus
                view = discord.ui.View()
                confirm_btn = discord.ui.Button(label="âœ… Confirmer", style=discord.ButtonStyle.green)
                refuse_btn = discord.ui.Button(label="âŒ Refuser", style=discord.ButtonStyle.red)
                
                async def confirm_callback(interaction_confirm: discord.Interaction):
                    # DEFER IMMÃ‰DIATEMENT pour Ã©viter le timeout
                    await interaction_confirm.response.defer()
                    
                    # VÃ©rifier que seul la direction peut confirmer
                    if not any(role.id == DIRECTION_ROLE_ID for role in interaction_confirm.user.roles):
                        await interaction_confirm.followup.send(
                            "âŒ Seule la direction peut valider les disponibilitÃ©s !",
                            ephemeral=True
                        )
                        return
                    
                    # Message de confirmation Ã  la direction
                    embed_confirm = discord.Embed(
                        title="âœ… DisponibilitÃ© ConfirmÃ©e",
                        description=f"La dispo de {user_name} a Ã©tÃ© approuvÃ©e.\n\nEn attente de recrutement...",
                        color=discord.Color.green()
                    )
                    await interaction_confirm.followup.send(embed=embed_confirm, ephemeral=True)
                    
                    # DÃ©sactiver les boutons
                    confirm_btn.disabled = True
                    refuse_btn.disabled = True
                    await interaction_confirm.message.edit(view=view)
                    
                    # Envoyer un DM de rappel Ã  l'utilisateur
                    try:
                        embed_dm = discord.Embed(
                            title="ðŸ“… âœ… Votre DisponibilitÃ© a Ã©tÃ© ConfirmÃ©e",
                            description=f"Bonjour {user_name},\n\nVotre disponibilitÃ© a Ã©tÃ© validÃ©e par la direction !\n\nVos dispo:\n{self.disponibilites.value}",
                            color=discord.Color.green()
                        )
                        embed_dm.set_footer(text="ðŸš‘ EMS System | Rappel de confirmation")
                        
                        user = bot.get_user(interaction.user.id)
                        if user:
                            await user.send(embed=embed_dm)
                    except:
                        pass
                    
                    # Envoyer un message de recrutement dans le channel de recrutement
                    recruitment_channel = bot.get_channel(DISPO_CHANNEL_ID)
                    if recruitment_channel:
                        embed_recrutement = discord.Embed(
                            title="ðŸ‘¤ Candidature ApprouvÃ©e - DÃ©cision de Recrutement",
                            description=f"**{interaction.user.mention}** a Ã©tÃ© approuvÃ©(e) par la direction.\n\n"
                                       f"DisponibilitÃ©s:\n{self.disponibilites.value}",
                            color=discord.Color.blue()
                        )
                        
                        # Boutons Recruter/Refuser
                        recrutement_view = discord.ui.View()
                        recruter_btn = discord.ui.Button(label="âœ… Recruter", style=discord.ButtonStyle.green)
                        refuser_btn = discord.ui.Button(label="âŒ Refuser", style=discord.ButtonStyle.red)
                        
                        async def recruter_callback(interaction_recrutement: discord.Interaction):
                            # DEFER IMMÃ‰DIATEMENT pour Ã©viter le timeout
                            await interaction_recrutement.response.defer()
                            
                            # VÃ©rifier que seul la direction peut recruter
                            if not any(role.id == DIRECTION_ROLE_ID for role in interaction_recrutement.user.roles):
                                await interaction_recrutement.followup.send(
                                    "âŒ Seule la direction peut recruter !",
                                    ephemeral=True
                                )
                                return
                            
                            try:
                                guild = bot.get_guild(config["GUILD_ID"])
                                member = guild.get_member(interaction.user.id)
                                
                                if member:
                                    # Enregistrer la date d'embauche
                                    try:
                                        set_embauche_date(normalize_employee_key(member.display_name))
                                    except Exception:
                                        pass

                                    # Retirer le rÃ´le pending
                                    try:
                                        role_pending = guild.get_role(ROLE_PENDING_ID)
                                        if role_pending:
                                            await member.remove_roles(role_pending)
                                    except:
                                        pass
                                    
                                    # Ajouter les rÃ´les EMS
                                    roles_to_add = [
                                        guild.get_role(ROLE_EMT_1),
                                        guild.get_role(ROLE_EMT_2),
                                        guild.get_role(ROLE_EMT_3)
                                    ]
                                    roles_to_add = [r for r in roles_to_add if r]
                                    
                                    if roles_to_add:
                                        await member.add_roles(*roles_to_add)

                                    # Attribuer automatiquement les formations Scout et Alamo Ã  l'embauche EMT
                                    try:
                                        auto_formation_roles = [
                                            guild.get_role(1528837812793901207),  # Formation Scout
                                            guild.get_role(1528838179061367015),  # Formation Alamo
                                        ]
                                        auto_formation_roles = [r for r in auto_formation_roles if r]
                                        if auto_formation_roles:
                                            await member.add_roles(*auto_formation_roles)
                                    except Exception as _af_err:
                                        print(f"Erreur attribution formations auto EMT: {_af_err}")

                                    # Ajouter le prÃ©fixe [EMT]
                                    try:
                                        new_nick = f"[EMT] {user_name}"
                                        await member.edit(nick=new_nick)
                                    except:
                                        pass
                                    
                                    # CrÃ©er le channel privÃ© avec emoji + nom dans la catÃ©gorie
                                    try:
                                        category = guild.get_channel(CATEGORY_EMT_ID)
                                        
                                        channel_name = f"ðŸ”´{user_name.lower().replace(' ', '-')}"
                                        
                                        # Obtenir les permissions pour le channel
                                        overwrites = {
                                            guild.default_role: discord.PermissionOverwrite(view_channel=False),
                                            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                                            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                                        }
                                        
                                        # CrÃ©er le channel dans la catÃ©gorie
                                        new_channel = await guild.create_text_channel(
                                            channel_name,
                                            overwrites=overwrites,
                                            category=category
                                        )
                                        
                                        # Message de bienvenue dans le channel
                                        embed_channel = discord.Embed(
                                            title=f"ðŸŽ‰ Bienvenue {user_name} !",
                                            description=f"Bienvenue dans ton channel personnel.\n\nTu as Ã©tÃ© recrutÃ©(e) en tant que **[EMT]**.\n\nVoici tes disponibilitÃ©s:\n{self.disponibilites.value}",
                                            color=discord.Color.green()
                                        )
                                        await new_channel.send(embed=embed_channel)
                                    except Exception as e:
                                        print(f"[{now_paris().strftime('%H:%M:%S')}] âš ï¸ Erreur crÃ©ation channel: {e}")
                                    
                                    # Message de confirmation
                                    embed_recrute = discord.Embed(
                                        title="âœ… Recrutement EffectuÃ©",
                                        description=f"**{user_name}** a Ã©tÃ© recrutÃ©(e) en tant que **[EMT]**.",
                                        color=discord.Color.green()
                                    )
                                    await interaction_recrutement.followup.send(embed=embed_recrute, ephemeral=True)
                                    
                                    # DM de bienvenue
                                    try:
                                        embed_welcome = discord.Embed(
                                            title="ðŸŽ‰ Bienvenue dans l'EMS !",
                                            description=f"FÃ©licitations {user_name} !\n\nVous avez Ã©tÃ© recrutÃ©(e) en tant que **[EMT]**.\n\nUn channel privÃ© a Ã©tÃ© crÃ©Ã© pour vous : **{channel_name}**",
                                            color=discord.Color.green()
                                        )
                                        user_obj = bot.get_user(interaction.user.id)
                                        if user_obj:
                                            await user_obj.send(embed=embed_welcome)
                                    except:
                                        pass
                                    
                                    # DÃ©sactiver les boutons
                                    recruter_btn.disabled = True
                                    refuser_btn.disabled = True
                                    await interaction_recrutement.message.edit(view=recrutement_view)
                                    
                                    # Ajouter rÃ©action âœ…
                                    if hasattr(interaction_recrutement.message, 'add_reaction'):
                                        await interaction_recrutement.message.add_reaction("âœ…")
                            except Exception as e:
                                print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur recrutement: {e}")
                                await interaction_recrutement.followup.send(f"âŒ Erreur: {e}", ephemeral=True)
                        
                        async def refuser_recrutement_callback(interaction_refus: discord.Interaction):
                            # DEFER IMMÃ‰DIATEMENT pour Ã©viter le timeout
                            await interaction_refus.response.defer()
                            
                            # VÃ©rifier que seul la direction peut refuser
                            if not any(role.id == DIRECTION_ROLE_ID for role in interaction_refus.user.roles):
                                await interaction_refus.followup.send(
                                    "âŒ Seule la direction peut refuser !",
                                    ephemeral=True
                                )
                                return
                            
                            try:
                                guild = bot.get_guild(config["GUILD_ID"])
                                member = guild.get_member(interaction.user.id)
                                
                                if member:
                                    # Retirer tous les rÃ´les EMS (sauf citoyen)
                                    for role in member.roles:
                                        if role.id in [ROLE_EMT_1, ROLE_EMT_2, ROLE_EMT_3, ROLE_PENDING_ID] and role.id != ROLE_CITOYEN:
                                            try:
                                                await member.remove_roles(role)
                                            except:
                                                pass
                                    
                                    # Retirer le prÃ©fixe [EMT] et le pseudo du serveur
                                    try:
                                        await member.edit(nick=None)
                                    except:
                                        pass
                                    
                                    # Message de refus
                                    embed_refuse = discord.Embed(
                                        title="âŒ Candidature RefusÃ©e",
                                        description=f"**{user_name}** a Ã©tÃ© refusÃ©(e) au recrutement.",
                                        color=discord.Color.red()
                                    )
                                    await interaction_refus.followup.send(embed=embed_refuse, ephemeral=True)
                                    
                                    # DM de refus
                                    try:
                                        embed_refuse_dm = discord.Embed(
                                            title="âŒ Candidature RefusÃ©e",
                                            description=f"Nous sommes dÃ©solÃ©s {user_name},\n\nVotre candidature au recrutement EMS a Ã©tÃ© refusÃ©e.\n\nVous pourrez rÃ©essayer dans 1 semaine.",
                                            color=discord.Color.red()
                                        )
                                        user_obj = bot.get_user(interaction.user.id)
                                        if user_obj:
                                            await user_obj.send(embed=embed_refuse_dm)
                                    except:
                                        pass

                                    # Blacklist CV automatique (second formulaire)
                                    try:
                                        bl = load_blacklist_cv()
                                        bl[str(interaction.user.id)] = {
                                            "date": datetime.utcnow().isoformat(),
                                            "raison": "Candidature refusÃ©e par la direction (formulaire CV)",
                                            "blacklisted_by": str(interaction_refus.user.id),
                                        }
                                        save_blacklist_cv(bl)
                                    except Exception as _bl3:
                                        print(f"Erreur blacklist CV refus formulaire: {_bl3}")

                                    # DÃ©sactiver les boutons
                                    recruter_btn.disabled = True
                                    refuser_btn.disabled = True
                                    await interaction_refus.message.edit(view=recrutement_view)
                                    
                                    # Ajouter rÃ©action âŒ
                                    if hasattr(interaction_refus.message, 'add_reaction'):
                                        await interaction_refus.message.add_reaction("âŒ")
                            except Exception as e:
                                print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur refus recrutement: {e}")
                                await interaction_refus.followup.send(f"âŒ Erreur: {e}", ephemeral=True)
                        
                        recruter_btn.callback = recruter_callback
                        refuser_btn.callback = refuser_recrutement_callback
                        recrutement_view.add_item(recruter_btn)
                        recrutement_view.add_item(refuser_btn)
                        
                        await recruitment_channel.send(embed=embed_recrutement, view=recrutement_view)
                    
                    # Ajouter une rÃ©action pour marquer comme confirmÃ©e
                    if hasattr(interaction_confirm.message, 'add_reaction'):
                        await interaction_confirm.message.add_reaction("âœ…")
                
                async def refuse_callback(interaction_refuse: discord.Interaction):
                    # DEFER IMMÃ‰DIATEMENT pour Ã©viter le timeout
                    await interaction_refuse.response.defer()
                    
                    # Message de refus Ã  la direction
                    embed_refuse = discord.Embed(
                        title="âŒ DisponibilitÃ© RefusÃ©e",
                        description=f"La dispo de {user_name} a Ã©tÃ© dÃ©clinÃ©e.",
                        color=discord.Color.red()
                    )
                    await interaction_refuse.followup.send(embed=embed_refuse, ephemeral=True)
                    
                    # DÃ©sactiver les boutons
                    confirm_btn.disabled = True
                    refuse_btn.disabled = True
                    await interaction_refuse.message.edit(view=view)
                    
                    # Envoyer un DM de rappel/refus Ã  l'utilisateur
                    try:
                        embed_dm = discord.Embed(
                            title="ðŸ“… âŒ DisponibilitÃ© RefusÃ©e",
                            description=f"Bonjour {user_name},\n\nVotre proposition de disponibilitÃ© a Ã©tÃ© refusÃ©e.\n\nVeuillez contacter la direction pour plus d'informations.",
                            color=discord.Color.red()
                        )
                        embed_dm.set_footer(text="ðŸš‘ EMS System | Avis de refus")
                        
                        user = bot.get_user(interaction.user.id)
                        if user:
                            await user.send(embed=embed_dm)
                    except:
                        pass
                    
                    # Ajouter une rÃ©action pour marquer comme refusÃ©e
                    if hasattr(interaction_refuse.message, 'add_reaction'):
                        await interaction_refuse.message.add_reaction("âŒ")
                
                confirm_btn.callback = confirm_callback
                refuse_btn.callback = refuse_callback
                view.add_item(confirm_btn)
                view.add_item(refuse_btn)
                
                ping_msg = f"<@&{DIRECTION_ROLE_ID}>"
                await request_channel.send(ping_msg, embed=embed, view=view)
            
            await interaction.response.send_message(
                "âœ… Vos disponibilitÃ©s ont Ã©tÃ© soumises avec succÃ¨s !",
                ephemeral=True
            )
        except Exception as e:
            print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur dispo: {e}")
            await interaction.response.send_message(
                f"âŒ Erreur: {e}",
                ephemeral=True
            )

# --- BOUTON POUR LES DISPONIBILITÃ‰S ---
class DispoButton(discord.ui.View):
    """Bouton pour ouvrir le formulaire de disponibilitÃ©s"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="ðŸ“… Soumettre ma Dispo", style=discord.ButtonStyle.primary)
    async def dispo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ouvre le modal pour soumettre ses dispo"""
        await interaction.response.send_modal(DispoModal())

# --- COMMANDE DISPO ---

ESX_SOCIETY_CHANNEL_ID = 1267921697420345424
ESX_SOCIETY_ROLE_ID = 838102445095256068

# Fichiers partagÃ©s avec Flask (mÃªme process, mÃªme DATA_DIR)
_TEST_LOGS_FILE   = os.path.join(DATA_DIR, 'test_logs.json')
_TEST_ERRORS_FILE = os.path.join(DATA_DIR, 'test_errors.json')
_TEST_REA_FILE    = os.path.join(DATA_DIR, 'test_rea.json')
_TEST_MAP_FILE    = os.path.join(DATA_DIR, 'test_license_map.json')  # license â†’ nom rÃ©el
_TEST_META_FILE   = os.path.join(DATA_DIR, 'test_meta.json')         # last_reset, etc.
_TEST_MAX = 500
_test_lock = __import__('threading').Lock()

# Mapping titres embed -> type interne
_ESX_TITLE_MAP = {
    "vente": "vente",
    "vente importante": "vente_importante",
    "ventes (rÃ©cap)": "vente",   # rÃ©cap de plusieurs ventes = on compte chaque 100k
    "prise de service": "prise_service",
    "fin de service": "fin_service",
}

def _parse_esx_embed(embed):
    """Parse un embed esx_society et retourne un dict de donnÃ©es ou None."""
    # Le titre peut avoir un emoji avant le texte : 'ðŸŸ¢ Prise de service'
    title = (embed.title or "").strip().lower()
    # Supprimer tout caractÃ¨re non-ascii devant le titre (emojis, etc.)
    title_clean = title.encode('ascii', 'ignore').decode('ascii').strip()
    log_type = None
    for key, val in _ESX_TITLE_MAP.items():
        if key in title_clean or key in title:
            log_type = val
            break
    if log_type is None:
        return None, f"Titre embed non reconnu: '{embed.title}'"

    fields = {f.name.strip().lower(): f.value.strip() for f in embed.fields}

    # Extraire la license depuis le champ "identifiant"
    identifiant_raw = fields.get("identifiant", "")
    # Peut contenir des backticks : `license:xxxx`
    license_val = identifiant_raw.strip("`").strip()

    joueur = fields.get("joueur", "")
    societe = fields.get("sociÃ©tÃ©", fields.get("societe", ""))
    employee = fields.get("employÃ©", fields.get("employe", ""))

    # Validation basique
    if not license_val.startswith("license:"):
        return None, f"License invalide: '{license_val}'"
    if societe.lower() != "ems":
        return None, f"SociÃ©tÃ© ignorÃ©e (pas EMS): '{societe}'"

    result = {
        "type": log_type,
        "societe": societe,
        "joueur": joueur,
        "employee": employee,
        "license": license_val,
        "raw_title": embed.title or "",
        "role_ok": False,
        "montant": 0,
        "ventes": 0,
        "periode": 0,
        "origine": "",
    }

    if log_type in ("vente", "vente_importante"):
        # Montant: "100 000 $" -> 100000
        montant_raw = fields.get("montant", "0").replace(" ", "").replace("$", "").replace(",", "")
        try:
            result["montant"] = int(montant_raw)
        except Exception:
            result["montant"] = 0
        ventes_raw = fields.get("ventes", "1")
        try:
            result["ventes"] = int(ventes_raw)
        except Exception:
            result["ventes"] = 1
        periode_raw = fields.get("pÃ©riode", fields.get("periode", "0")).replace("min", "").strip()
        try:
            result["periode"] = int(periode_raw)
        except Exception:
            result["periode"] = 0
        result["origine"] = fields.get("origine", "addon_account")

    return result, None


def _ingest_log(endpoint_path, payload):
    """Ã‰criture synchrone â€” appelÃ©e uniquement depuis run_in_executor (thread pool)."""
    try:
        if endpoint_path.endswith('/logs/ingest'):
            filepath = _TEST_LOGS_FILE
        elif endpoint_path.endswith('/errors/ingest'):
            filepath = _TEST_ERRORS_FILE
        else:
            return
        with _test_lock:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = []
            data.insert(0, payload)
            data = data[:_TEST_MAX]
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ESX_INGEST] Erreur Ã©criture {endpoint_path}: {e}")


def _test_read(filepath, default):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default() if callable(default) else default


def _test_write(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ESX] Erreur Ã©criture {filepath}: {e}")


def _process_esx_sync(parsed, ts, is_error=False, error_payload=None):
    """Tout l'I/O fichier en une seule fonction sync â†’ exÃ©cutÃ©e dans un thread via run_in_executor."""
    if is_error:
        _ingest_log("/api/test/errors/ingest", error_payload)
        return

    license_key = parsed.get("license", "")

    # PDS â†’ mettre Ã  jour le mapping license â†’ nom rÃ©el
    if parsed.get("type") == "prise_service" and license_key:
        nom_pds = parsed.get("employee") or parsed.get("joueur", "")
        with _test_lock:
            lmap = _test_read(_TEST_MAP_FILE, {})
            lmap[license_key] = {
                "joueur":   parsed.get("joueur", ""),
                "employee": parsed.get("employee", ""),
                "nom":      nom_pds,
                "last_pds": ts,
            }
            _test_write(_TEST_MAP_FILE, lmap)

            # Fusionner l'entrÃ©e nom-clÃ© (import) avec l'entrÃ©e license si elle existe
            rea_data = _test_read(_TEST_REA_FILE, {})
            nom_key = nom_pds.lower().replace(' ', '-')
            if nom_key in rea_data and license_key not in rea_data:
                entry = rea_data.pop(nom_key)
                entry['license'] = license_key
                entry['nom'] = nom_pds
                rea_data[license_key] = entry
                _test_write(_TEST_REA_FILE, rea_data)
                print(f"[ESX] PDS : {nom_pds} (fusion {nom_key} â†’ license)")
            elif license_key in rea_data and nom_key in rea_data:
                # Les deux existent, fusionner les rÃ©as
                rea_data[license_key]['reas'] += rea_data[nom_key].get('reas', 0)
                rea_data[license_key]['history'] = rea_data[nom_key].get('history', []) + rea_data[license_key]['history']
                rea_data[license_key]['nom'] = nom_pds
                del rea_data[nom_key]
                _test_write(_TEST_REA_FILE, rea_data)
                print(f"[ESX] PDS : {nom_pds} (fusion doublon)")
            else:
                print(f"[ESX] PDS : {nom_pds}")

    # Enrichir avec le nom rÃ©el
    with _test_lock:
        lmap = _test_read(_TEST_MAP_FILE, {})
    parsed["nom_reel"] = lmap.get(license_key, {}).get("nom") or parsed.get("joueur", "")

    _ingest_log("/api/test/logs/ingest", parsed)

    # Comptage rÃ©as : vente 100k = +1 rÃ©a, seulement si PDS connue
    montant = parsed.get("montant", 0)
    nb_reas = montant // 100000
    if parsed.get("type") in ("vente", "vente_importante") and nb_reas >= 1 and license_key:
        with _test_lock:
            lmap2 = _test_read(_TEST_MAP_FILE, {})
            if license_key not in lmap2:
                print(f"[ESX] IgnorÃ© (pas de PDS) : {parsed.get('joueur')}")
            else:
                nom = lmap2[license_key].get("nom") or parsed.get("joueur", license_key)
                rea_data = _test_read(_TEST_REA_FILE, {})
                if license_key not in rea_data:
                    rea_data[license_key] = {"nom": nom, "license": license_key, "reas": 0, "history": []}
                else:
                    if nom:
                        rea_data[license_key]["nom"] = nom
                rea_data[license_key]["reas"] += nb_reas
                rea_data[license_key]["history"].insert(0, {
                    "action": "add", "amount": nb_reas,
                    "note": f"Auto â€” {parsed.get('raw_title','')} ({montant:,}$)",
                    "timestamp": ts,
                })
                _test_write(_TEST_REA_FILE, rea_data)
                print(f"[ESX] +{nb_reas} rÃ©a(s) pour {nom}")


# Titres esx_society connus mais non traitÃ©s â€” silence total
_ESX_IGNORED_TITLES = {"facture refusÃ©e", "licenciement", "embauche", "promotion", "dÃ©mission", "sanction"}

async def _handle_esx_society_message(message):
    """Capture et parse les messages esx_society dans le channel logs."""
    if not message.embeds:
        return

    loop = asyncio.get_event_loop()

    for embed in message.embeds:
        parsed, error = _parse_esx_embed(embed)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        raw_fields = {f.name: f.value for f in embed.fields}

        if error or parsed is None:
            # Ignorer silencieusement les titres connus mais non traitÃ©s
            title_low = (embed.title or "").lower()
            if any(t in title_low for t in _ESX_IGNORED_TITLES):
                continue
            err_payload = {
                "reason": error or "Parse Ã©chouÃ©",
                "raw_title": embed.title or "",
                "raw_fields": raw_fields,
                "joueur": raw_fields.get("Joueur", ""),
                "license": raw_fields.get("Identifiant", "").strip("`").strip(),
                "timestamp": ts,
            }
            await loop.run_in_executor(None, _process_esx_sync, None, ts, True, err_payload)
            continue

        parsed["id"] = int(time.time() * 1000)
        parsed["timestamp"] = ts
        parsed["source"] = "discord_bot"
        parsed["role_ok"] = True

        # Tout l'I/O dans un thread â€” ne bloque plus l'event loop
        await loop.run_in_executor(None, _process_esx_sync, parsed, ts, False, None)


@bot.event
async def on_message(message):
    """Handler principal des messages - comptage rÃ©as, taxi, burgershot"""

    # --- CAPTURE LOGS ESX_SOCIETY (webhook OU bot) ---
    # esx_society envoie via webhook : webhook_id est dÃ©fini, author.bot peut Ãªtre False
    _is_esx_channel = message.channel.id == ESX_SOCIETY_CHANNEL_ID
    _is_webhook = getattr(message, 'webhook_id', None) is not None
    _is_bot = message.author.bot
    if _is_esx_channel and (_is_webhook or _is_bot):
        await _handle_esx_society_message(message)

    # Ignorer les bots et les DM immÃ©diatement (early exit O(1))
    if message.author.bot:
        return
    if message.guild is None:
        await bot.process_commands(message)
        return

    # --- SURVEILLANCE COFFRE SOCIÃ‰TÃ‰ ---
    if message.channel.id == 1267921697420345424:
        content = message.content or ""
        # Ignorer les messages PDS (service) â€” ils contiennent ces mots clÃ©s
        pds_keywords = ["fin de service", "prise de service", "esx_society", "employÃ©", "identifiant", "license:"]
        is_pds = any(kw in content.lower() for kw in pds_keywords)
        # Parser uniquement les messages de retrait : "vient de rÃ©cupÃ©rer xN item"
        match = _re.search(r"l'utilisateur \*\*(.+?)\*\* vient de rÃ©cupÃ©rer x(\d+) (.+?) dans la sociÃ©tÃ©", content, _re.IGNORECASE)
        if match and not is_pds:
            username = match.group(1).strip()
            qty = int(match.group(2))
            item = match.group(3).strip()
            today_str = now_paris().strftime("%Y-%m-%d")
            track_key = f"{username}_{today_str}"

            if track_key not in coffre_tracking:
                coffre_tracking[track_key] = {"count": 0, "items": [], "by_item": {}}
            if "by_item" not in coffre_tracking[track_key]:
                coffre_tracking[track_key]["by_item"] = {}

            coffre_tracking[track_key]["count"] += qty
            coffre_tracking[track_key]["items"].append(f"x{qty} {item}")
            item_key = item.lower().strip()
            coffre_tracking[track_key]["by_item"][item_key] = coffre_tracking[track_key]["by_item"].get(item_key, 0) + qty
            total = coffre_tracking[track_key]["count"]
            item_exceeded = any(v > 5 for v in coffre_tracking[track_key]["by_item"].values())

            if item_exceeded:
                alert_channel = bot.get_channel(1452842321996677253)
                if alert_channel:
                    items_list = "\n".join(f"â€¢ {i}" for i in coffre_tracking[track_key]["items"])
                    embed = discord.Embed(
                        title="ðŸš¨ ALERTE COFFRE SOCIÃ‰TÃ‰",
                        description=f"**{username}** a retirÃ© **{total} items** du coffre aujourd'hui !",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="ðŸ“¦ Items retirÃ©s (total)", value=items_list, inline=False)
                    embed.add_field(name="ðŸ• Dernier retrait", value=f"x{qty} {item}", inline=True)
                    embed.add_field(name="ðŸ“Š Total du jour", value=f"**{total} items**", inline=True)
                    embed.set_footer(text=f"ðŸš‘ EMS System | {now_paris().strftime('%d/%m/%Y %H:%M')}")
                    try:
                        await alert_channel.send(content="<@&838102445095256068>", embed=embed)
                    except Exception as e:
                        print(f"Erreur alerte coffre: {e}")

    # Ignorer les messages du bot pour le reste
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    # --- COMPTAGE TAXI ---
    if message.channel.id == TAXI_CHANNEL_ID:
        if any(role.id == TAXI_ROLE_ID for role in getattr(message.author, "roles", [])):
            try:
                await message.add_reaction("âœ…")
            except:
                pass
            taxi_stats = load_taxi_stats()
            taxi_stats["count"] += 1
            save_taxi_stats(taxi_stats)
    
    # --- COMPTAGE BURGERSHOT ---
    if message.channel.id == BURGERSHOT_CHANNEL_ID:
        if message.attachments:
            try:
                await message.add_reaction("âœ…")
            except:
                pass
            burgershot_stats = load_burgershot_stats()
            burgershot_stats["count"] += 1
            save_burgershot_stats(burgershot_stats)
    
    # Ignorer les messages sans piÃ¨ces jointes pour le reste
    if not message.attachments:
        await bot.process_commands(message)
        return
    
    try:
        # Obtenir le channel et l'employÃ© associÃ©
        channel = message.channel
        if not channel or not channel.name:
            await bot.process_commands(message)
            return
        
        # VÃ©rifier que c'est un channel EMS (commence par emoji)
        if not (channel.name and len(channel.name) > 0 and channel.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]):
            await bot.process_commands(message)
            return
        
        # Obtenir la clÃ© employÃ© du channel
        employee_key = get_channel_employee_key(channel)
        if not employee_key:
            await bot.process_commands(message)
            return
        
        # --- VÃ‰RIFICATION SERVICE ACTIF ---
        user_id = str(message.author.id)
        if user_id not in active_services:
            try:
                await message.reply(
                    "âŒ **Tu dois prendre ton service avant d'envoyer des rÃ©as !**\n"
                    "Va dans <#1413994272616611880> et clique sur **ðŸŸ¢ Prise de Service**.",
                    delete_after=10
                )
                await message.add_reaction("â›”")
            except:
                pass
            await bot.process_commands(message)
            return
        
        # Mettre Ã  jour la derniÃ¨re rÃ©a et le compteur de service
        # VÃ©rifier que l'employÃ© a choisi une division
        if user_id not in dispatch_state:
            try:
                await message.reply(
                    "âŒ **Tu dois choisir ta division avant d'envoyer des rÃ©as !**\n"
                    f"Va dans le salon dispatch et sÃ©lectionne ta division via les boutons.",
                    delete_after=60
                )
                await message.add_reaction("â›”")
            except:
                pass
            await bot.process_commands(message)
            return

        # VÃ©rifier que l'employÃ© est dans le bon vocal de sa division
        user_div = dispatch_state.get(user_id)
        expected_vocal_id = SERVICE_VOICE_CHANNELS.get(user_div)
        member_voice = message.author.voice
        if expected_vocal_id and (not member_voice or member_voice.channel.id != expected_vocal_id):
            # VÃ©rifier si l'employÃ© est dans un autre vocal de service valide (ex: Ã©tait dans Lincoln et a changÃ© de division)
            in_any_service_vocal = member_voice and member_voice.channel.id in SERVICE_VOICE_IDS
            if not in_any_service_vocal:
                try:
                    expected_channel = message.guild.get_channel(expected_vocal_id)
                    vocal_name = expected_channel.name if expected_channel else user_div
                    await message.reply(
                        f"âŒ **Tu dois Ãªtre dans le vocal de ta division pour envoyer des rÃ©as !**\n"
                        f"Rejoins le vocal **{vocal_name}** pour continuer.",
                        delete_after=60
                    )
                    await message.add_reaction("â›”")
                except:
                    pass
                await bot.process_commands(message)
                return
        active_services[user_id]["last_rea"] = now_paris().isoformat()
        active_services[user_id]["reas_count"] = active_services[user_id].get("reas_count", 0) + 1

        # Mettre Ã  jour le fichier de suivi d'activitÃ© rÃ©a (pour alerte inactivitÃ©)
        try:
            emp_key = active_services[user_id].get("employee_key", "")
            if emp_key:
                last_activity = robust_load_json(REA_INACTIVITY_FILE, {})
                last_activity[emp_key] = now_paris().isoformat()
                atomic_write_json(REA_INACTIVITY_FILE, last_activity)
                # RÃ©initialiser alerte si l'employÃ© avait Ã©tÃ© alertÃ©
                alerted = robust_load_json(REA_INACTIVITY_ALERTED_FILE, {})
                if emp_key in alerted:
                    del alerted[emp_key]
                    atomic_write_json(REA_INACTIVITY_ALERTED_FILE, alerted)
                # Tracking journalier (graphique dashboard)
                add_daily_rea(emp_key, 1)
        except Exception as _rea_track_err:
            pass

        # Partager la rÃ©a avec les coÃ©quipiers de la mÃªme division (Adam/Tango/Xray)
        user_div = dispatch_state.get(user_id)
        if user_div and not user_div.startswith("Lincoln"):
            coequipiers = [uid for uid, div in dispatch_state.items() if div == user_div and uid != user_id]
            if coequipiers:
                for co_uid in coequipiers:
                    if co_uid in active_services:
                        active_services[co_uid]["last_rea"] = now_paris().isoformat()
                        active_services[co_uid]["reas_count"] = active_services[co_uid].get("reas_count", 0) + 1
                        co_emp_key = active_services[co_uid].get("employee_key", "")
                        if co_emp_key:
                            add_daily_rea(co_emp_key, 1)

                # Log rÃ©a partagÃ©e
                log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
                if log_channel:
                    all_names = [get_clean_name(message.author)] + [get_clean_name(message.guild.get_member(int(uid))) for uid in coequipiers if message.guild.get_member(int(uid))]
                    try:
                        await log_channel.send(
                            f"ðŸ¤ **RÃ©a partagÃ©e** â€” **{user_div}** : {' + '.join(all_names)}"
                        )
                    except:
                        pass

                # Un seul message dans le channel de chaque coÃ©quipier (sans ping)
                sender_name = get_clean_name(message.author)
                for target_uid in coequipiers:
                    target_member = message.guild.get_member(int(target_uid))
                    if not target_member:
                        continue
                    target_name = get_clean_name(target_member)
                    co_key_check = active_services.get(target_uid, {}).get("employee_key", "")
                    target_clean_norm = normalize_employee_key(target_name)
                    for ch in message.guild.text_channels:
                        if ch.name and len(ch.name) > 1 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
                            if get_channel_employee_key(ch) in [target_clean_norm, co_key_check]:
                                try:
                                    await ch.send(
                                        f"âž• **+1 rÃ©a** comptÃ©e pour **{target_name}** par **{sender_name}** ({user_div})"
                                    )
                                except:
                                    pass
                                break

        # --- PRIME SOIRÃ‰E : 10 rÃ©as entre 21h-23h ---
        current_hour = now_paris().hour
        if 21 <= current_hour < 23:
            today_str = now_paris().strftime("%Y-%m-%d")
            evening_key = f"{employee_key}_{today_str}"
            evening_reas[evening_key] = evening_reas.get(evening_key, 0) + 1
            atomic_write_json(EVENING_REAS_FILE, evening_reas)
            if evening_reas[evening_key] == 10:
                if award_bonus(employee_key):
                    try:
                        await message.channel.send(
                            f"ðŸ’° **Prime soirÃ©e dÃ©bloquÃ©e !** 10 rÃ©as entre 21h-23h â€” **+1M** attribuÃ© Ã  {employee_key.replace('-', ' ').title()} !",
                            delete_after=30
                        )
                    except:
                        pass
        
        # Charger les stats
        # Charger les stats fraÃ®ches et incrÃ©menter atomiquement
        stats = load_stats()

        # IncrÃ©menter le compteur de l'envoyeur
        if employee_key not in stats:
            stats[employee_key] = 0
        old_count = stats[employee_key]
        stats[employee_key] += 1
        current_count = stats[employee_key]

        # IncrÃ©menter aussi les stats des coÃ©quipiers de division
        user_div2 = dispatch_state.get(user_id)
        if user_div2 and not user_div2.startswith("Lincoln"):
            coequipiers2 = [uid for uid, div in dispatch_state.items() if div == user_div2 and uid != user_id]
            for co_uid in coequipiers2:
                co_member = message.guild.get_member(int(co_uid))
                if not co_member:
                    continue
                co_key = active_services.get(co_uid, {}).get("employee_key")
                if not co_key:
                    continue
                if co_key not in stats:
                    stats[co_key] = 0
                stats[co_key] += 1
                # Pas d'Ã©dition de channel ici â€” la tÃ¢che pÃ©riodique s'en charge

        # Sauvegarder TOUT en une seule fois
        save_stats(stats)

        # Ajouter rÃ©action âœ… (indÃ©pendant du reste)
        for attempt in range(3):
            try:
                await message.add_reaction("âœ…")
                break
            except discord.errors.HTTPException as e:
                if e.status == 429:  # Rate limited
                    await asyncio.sleep(e.retry_after if hasattr(e, 'retry_after') else 1)
                else:
                    break
            except:
                break

        # Envoyer log (indÃ©pendant)
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            try:
                emoji = get_color_emoji(current_count)
                message_text = f"âœ… **{employee_key}** | {current_count} rÃ©as"
                await log_channel.send(message_text)
                
                # --- MILESTONES & CONGRATULATIONS ---
                display_name = employee_key.replace("-", " ").title()
                
                # Milestone 50 rÃ©as
                if old_count < 50 and current_count >= 50:
                    embed_50 = discord.Embed(
                        title="ðŸŽ¯ 50 rÃ©as atteints !",
                        description=f"Excellent travail **{display_name}** ! ðŸ™Œ\n\n"
                                   f"Tu continues et tu atteindras le quota complet.\n"
                                   f"Reste motivÃ© ! ðŸ’ª",
                        color=discord.Color.orange()
                    )
                    embed_50.set_footer(text="ðŸš‘ EMS System | Continue comme Ã§a !")
                    await message.channel.send(embed=embed_50)
                
                # Milestone 100 rÃ©as (QUOTA COMPLET)
                if old_count < 100 and current_count >= 100:
                    embed_100 = discord.Embed(
                        title="ðŸ† QUOTA COMPLET - 100 rÃ©as ! ðŸ†",
                        description=f"ðŸŽ‰ **{display_name}** a rempli le quota !\n\n"
                                   f"Tu as atteint l'objectif de 100 rÃ©as.\n"
                                   f"Continue comme Ã§a, nous sommes fiers de ton activitÃ© ! ðŸŒŸ\n\n"
                                   f"Des rÃ©compenses seront offertes aux plus actifs Ã  la fin du mois.",
                        color=discord.Color.gold()
                    )
                    embed_100.set_footer(text="ðŸš‘ EMS System | Bravo !")
                    
                    # Envoyer dans le channel employÃ© avec ping
                    try:
                        role_mention = f"<@&838102445095256068>"
                        await message.channel.send(role_mention, embed=embed_100)
                    except:
                        await message.channel.send(embed=embed_100)
            except:
                pass
    
    except Exception as e:
        print(f"âŒ Erreur on_message: {e}")
    
    # Traiter les commandes slash
    await bot.process_commands(message)

# --- SYSTÃˆME DE PRISE DE SERVICE ---
SERVICE_CHANNEL_ID = 1413994272616611880

def build_status_embed():
    """Construit l'embed de statut des services en direct"""
    if active_services:
        lines = []
        for uid, svc in active_services.items():
            start_t = datetime.fromisoformat(svc['start'])
            delta = now_paris() - start_t
            total_min = int(delta.total_seconds() // 60)
            h = total_min // 60
            m = total_min % 60
            duree = f"{h}h{m:02d}" if h > 0 else f"{m} min"
            reas = svc.get('reas_count', 0)
            name = svc.get('display_name', svc['employee_key'])
            lines.append(f"ðŸŸ¢ **{name}** (<@{uid}>) â€” en service depuis **{duree}** ({reas} rÃ©as)")
        
        status_text = "\n".join(lines)
    else:
        status_text = "*Aucun employÃ© en service actuellement.*"
    return status_text

def build_service_embed():
    """Construit l'embed complet prise de service + statut en direct"""
    status_text = build_status_embed()
    
    embed = discord.Embed(
        title="ðŸš‘ PRISE DE SERVICE EMS",
        description=(
            "**Bienvenue dans le systÃ¨me de prise de service !**\n\n"
            "ðŸ“‹ **Comment Ã§a marche ?**\n"
            "1ï¸âƒ£ Clique sur **ðŸŸ¢ Prise de Service** avant de commencer tes rÃ©as\n"
            "2ï¸âƒ£ Envoie tes rÃ©as normalement dans ton channel\n"
            "3ï¸âƒ£ Clique sur **ðŸ”´ Fin de Service** quand tu as terminÃ©\n\n"
            "âš ï¸ **Important :**\n"
            "â€¢ Tu **dois** prendre ton service avant d'envoyer des rÃ©as\n"
            "â€¢ AprÃ¨s **30 min** sans rÃ©a, ton service sera terminÃ© automatiquement\n"
            "â€¢ La direction peut consulter les heures avec `/services`\n\n"
            "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
            f"ðŸ“¡ **EMPLOYÃ‰S EN SERVICE :**\n{status_text}\n\n"
            f"*DerniÃ¨re mise Ã  jour : {now_paris().strftime('%H:%M:%S')}*"
        ),
        color=EMS_RED
    )
    embed.set_footer(text="ðŸš‘ EMS System | Prise de Service")
    return embed

last_pds_update = datetime.min.replace(tzinfo=PARIS_TZ)

async def update_service_status(force=False):
    """Met Ã  jour le message de prise de service avec le statut en temps rÃ©el"""
    global service_status_message_id, last_pds_update
    # Cooldown de 30 secondes pour Ã©viter les rate limits (bypassÃ© si force=True)
    if not force and (now_paris() - last_pds_update).total_seconds() < 30:
        return
    try:
        channel = bot.get_channel(SERVICE_CHANNEL_ID)
        if not channel:
            return
        
        if service_status_message_id:
            try:
                msg = await channel.fetch_message(service_status_message_id)
                await msg.edit(embed=build_service_embed())
                last_pds_update = now_paris()
                return
            except discord.NotFound:
                service_status_message_id = None
    except Exception as e:
        print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur update_service_status: {e}")


class DispatchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ðŸ†˜ Demande de renfort", style=discord.ButtonStyle.danger, custom_id="dispatch_renfort")
    async def renfort(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        role_ems = guild.get_role(838102445095256068)
        role_ping = role_ems.mention if role_ems else ""

        renfort_channel = guild.get_channel(1483380822424682506)
        if renfort_channel:
            await renfort_channel.send(
                f"ðŸ†˜ {role_ping} â€” **{interaction.user.display_name}** a demandÃ© du **renfort** !\n"
                f"Prenez votre service si possible.",
                allowed_mentions=discord.AllowedMentions(roles=True)
            )

        await interaction.followup.send(
            "âœ… Demande de renfort envoyÃ©e !",
            ephemeral=True
        )

class ServiceView(discord.ui.View):
    """Vue persistante avec boutons Prise / Fin de service"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="ðŸŸ¢ Prise de Service", style=discord.ButtonStyle.green, custom_id="prise_service")
    async def prise_service(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        
        # DÃ©jÃ  en service ?
        if user_id in active_services:
            start = datetime.fromisoformat(active_services[user_id]["start"])
            minutes = int((now_paris() - start).total_seconds() // 60)
            await interaction.response.send_message(
                f"âš ï¸ Tu es dÃ©jÃ  en service depuis **{minutes} min** !\n"
                f"Clique sur **ðŸ”´ Fin de Service** pour terminer.",
                ephemeral=True
            )
            return
        
        # Trouver le channel EMS
        guild = interaction.guild
        employee_key = None
        for ch in guild.text_channels:
            if ch.name and len(ch.name) > 0 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
                ch_key = get_channel_employee_key(ch)
                if ch_key:
                    perms = ch.permissions_for(interaction.user)
                    if perms.send_messages and not ch.permissions_for(guild.default_role).view_channel:
                        employee_key = ch_key
                        break
        
        if not employee_key:
            await interaction.response.send_message(
                "âŒ Impossible de trouver ton channel EMS. Contacte la direction.",
                ephemeral=True
            )
            return
        
        now = now_paris()
        clean_name = get_clean_name(interaction.user)
        active_services[user_id] = {
            "start": now.isoformat(),
            "last_rea": now.isoformat(),
            "employee_key": employee_key,
            "display_name": clean_name,
            "reas_count": 0
        }

        # Enregistrer dans l'historique dispatch
        dispatch_history.append({
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "display_name": clean_name,
            "employee_key": employee_key,
            "division": dispatch_state.get(user_id, "â€”")
        })
        if len(dispatch_history) > 500:
            dispatch_history.pop(0)
        try:
            atomic_write_json(DISPATCH_HISTORY_FILE, dispatch_history)
        except Exception:
            pass

        # Ajouter le rÃ´le "En Service"
        role_en_service = interaction.guild.get_role(1524175137908457543)
        if role_en_service:
            try:
                await interaction.user.add_roles(role_en_service)
            except:
                pass
        
        # Log
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            try:
                embed = discord.Embed(
                    title="ðŸŸ¢ Prise de Service",
                    description=f"**{interaction.user.display_name}** ({interaction.user.mention}) a pris son service.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"ðŸš‘ EMS System | {now.strftime('%H:%M')}")
                await log_channel.send(embed=embed)
            except:
                pass
        
        try:
            await interaction.response.send_message(
                f"âœ… **Service commencÃ© !** ðŸŸ¢\n\n"
                f"Tu peux maintenant envoyer tes rÃ©as.\n"
                f"â±ï¸ Fin de service auto aprÃ¨s **30 min** sans rÃ©a.\n"
                f"Clique sur **ðŸ”´ Fin de Service** pour terminer.",
                ephemeral=True
            )
        except (discord.errors.NotFound, discord.errors.InteractionResponded, asyncio.TimeoutError, Exception):
            pass
        
        # Mettre Ã  jour le statut en temps rÃ©el
        await update_service_status(force=True)
        for g in bot.guilds:
            await run_dispatch(g)

        # Message dans dispatch pour inviter Ã  choisir une division
        dispatch_channel = interaction.guild.get_channel(DISPATCH_CHANNEL_ID)
        if dispatch_channel:
            await dispatch_channel.send(
                f"ðŸŸ¢ {interaction.user.mention} vient de prendre son service â€” **Choisissez votre division** via les boutons ci-dessus !",
                delete_after=30
            )
    
    @discord.ui.button(label="ðŸ”´ Fin de Service", style=discord.ButtonStyle.red, custom_id="fin_service")
    async def fin_service(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        
        if user_id not in active_services:
            await interaction.response.send_message(
                "âŒ Tu n'es pas en service ! Clique sur **ðŸŸ¢ Prise de Service** pour commencer.",
                ephemeral=True
            )
            return
        
        service = active_services.pop(user_id)
        start = datetime.fromisoformat(service["start"])
        end = now_paris()
        duree = end - start
        hours = round(duree.total_seconds() / 3600, 2)
        minutes = int(duree.total_seconds() // 60)
        reas = service.get("reas_count", 0)
        employee_key = service["employee_key"]
        
        # Enregistrer les heures
        add_service_hours(employee_key, hours, reas)

        # Retirer le rÃ´le "En Service"
        role_en_service = interaction.guild.get_role(1524175137908457543)
        if role_en_service:
            try:
                await interaction.user.remove_roles(role_en_service)
            except:
                pass

        # DÃ©placer du vocal de service vers le salon d'attente
        if interaction.user.voice and interaction.user.voice.channel:
            if interaction.user.voice.channel.id in SERVICE_VOICE_IDS:
                try:
                    waiting_channel = interaction.guild.get_channel(WAITING_VOICE_ID)
                    if waiting_channel:
                        await interaction.user.move_to(waiting_channel)
                    else:
                        await interaction.user.move_to(None)
                except:
                    pass
        log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
        if log_channel:
            try:
                embed = discord.Embed(
                    title="ðŸ”´ Fin de Service",
                    description=f"**{interaction.user.display_name}** ({interaction.user.mention}) a terminÃ© son service.",
                    color=discord.Color.red()
                )
                embed.add_field(name="â±ï¸ DurÃ©e", value=f"{minutes} min", inline=True)
                embed.add_field(name="ðŸš‘ RÃ©as", value=f"{reas}", inline=True)
                embed.set_footer(text=f"ðŸš‘ EMS System | {end.strftime('%H:%M')}")
                await log_channel.send(embed=embed)
            except:
                pass
        
        try:
            await interaction.response.send_message(
                f"âœ… **Service terminÃ© !** ðŸ”´\n\n"
                f"â±ï¸ DurÃ©e : **{minutes} min**\n"
                f"ðŸš‘ RÃ©as effectuÃ©es : **{reas}**\n\n"
                f"Merci pour ton service !",
                ephemeral=True
            )
        except (discord.errors.NotFound, discord.errors.InteractionResponded, asyncio.TimeoutError, Exception):
            pass
        
        # Mettre Ã  jour le statut en temps rÃ©el
        await update_service_status(force=True)

        # Retirer du dispatch et mettre Ã  jour
        user_id_str = str(interaction.user.id)
        if user_id_str in dispatch_state:
            del dispatch_state[user_id_str]
        for g in bot.guilds:
            await run_dispatch(g)


class AnnonceRoleModal(discord.ui.Modal, title="ðŸ“¢ RÃ´le Ã  mentionner"):
    role_input = discord.ui.TextInput(
        label="ID du rÃ´le (laisser vide = aucun ping)",
        placeholder="Ex: 838102445095256068 ou laisser vide",
        required=False,
        max_length=50
    )

    def __init__(self, contenu: str, target_channel):
        super().__init__()
        self.contenu = contenu
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        content_ping = None
        role_input = self.role_input.value.strip()
        if role_input:
            try:
                role = guild.get_role(int(role_input))
                if role:
                    content_ping = role.mention
                else:
                    await interaction.followup.send(
                        f"âš ï¸ RÃ´le `{role_input}` introuvable, annonce envoyÃ©e sans ping.",
                        ephemeral=True
                    )
            except ValueError:
                await interaction.followup.send(
                    "âš ï¸ ID invalide, annonce envoyÃ©e sans ping.",
                    ephemeral=True
                )

        embed = discord.Embed(description=self.contenu, color=EMS_RED)
        embed.set_footer(text=f"ðŸ“¢ Annonce EMS | {interaction.user.display_name}")

        try:
            await self.target_channel.send(
                content=content_ping,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )
            await interaction.followup.send(
                f"âœ… Annonce envoyÃ©e dans {self.target_channel.mention} !",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"âŒ Pas la permission d'envoyer dans {self.target_channel.mention}.",
                ephemeral=True
            )


class AnnonceSalonView(discord.ui.View):
    """Vue avec select pour choisir le salon."""
    def __init__(self, contenu: str, guild: discord.Guild):
        super().__init__(timeout=120)
        self.contenu = contenu

        # Construire les options (max 25) avec les salons texte
        options = []
        for ch in guild.text_channels[:25]:
            options.append(discord.SelectOption(
                label=f"#{ch.name}"[:100],
                value=str(ch.id),
                description=f"ID: {ch.id}"
            ))

        select = discord.ui.Select(
            placeholder="Choisissez le salon...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.salon_selected
        self.add_item(select)
        self.guild = guild

    async def salon_selected(self, interaction: discord.Interaction):
        channel_id = int(interaction.data["values"][0])
        target_channel = self.guild.get_channel(channel_id)
        if not target_channel:
            await interaction.response.send_message("âŒ Salon introuvable.", ephemeral=True)
            return
        await interaction.response.send_modal(AnnonceRoleModal(self.contenu, target_channel))


class AnnonceModal(discord.ui.Modal, title="ðŸ“¢ RÃ©diger l'annonce"):
    contenu = discord.ui.TextInput(
        label="Contenu de l'annonce",
        placeholder="Ã‰crivez votre annonce ici...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        view = AnnonceSalonView(self.contenu.value, interaction.guild)
        await interaction.response.send_message(
            "**Ã‰tape 2/3** â€” Choisissez le salon oÃ¹ envoyer l'annonce :",
            view=view,
            ephemeral=True
        )




CATEGORY_INDISPO_ID = 1524182164336279682

GRADE_TO_CATEGORY = {
    "EMT": "CATEGORY_EMT_ID",
    "STG": "CATEGORY_STG_ID",
    "INT": "CATEGORY_STG_ID",
    "ADS": "CATEGORY_ADS_ID",
    "INF": "CATEGORY_INF_ID",
    "PSY": "CATEGORY_PSY_ID",
    "MED": "CATEGORY_MED_ID",
    "CDS": "CATEGORY_CDS_ID",
    "CAD": "CATEGORY_CAD_ID",
    "DIR": "CATEGORY_DIR_ID",
}


@bot.tree.command(name="indisponible", description="Mettre un employÃ© en indisponibilitÃ© (dÃ©place son channel)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="L'employÃ© Ã  mettre en indisponibilitÃ©")
async def indisponible(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    clean_name = get_clean_name(membre)
    clean_name_normalized = normalize_employee_key(clean_name)

    # Trouver la catÃ©gorie indispo
    category_indispo = guild.get_channel(CATEGORY_INDISPO_ID)
    if not category_indispo:
        await interaction.followup.send("âŒ CatÃ©gorie indisponible introuvable (`1524182164336279682`).", ephemeral=True)
        return

    # Trouver le channel de l'employÃ©
    channel_found = None
    for ch in guild.text_channels:
        if ch.name and len(ch.name) > 1 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
            if get_channel_employee_key(ch) == clean_name_normalized:
                channel_found = ch
                break

    if not channel_found:
        await interaction.followup.send(
            f"âŒ Aucun channel trouvÃ© pour **{clean_name}**.",
            ephemeral=True
        )
        return

    # DÃ©placer dans la catÃ©gorie indispo
    try:
        await channel_found.edit(category=category_indispo)
    except Exception as e:
        await interaction.followup.send(f"âŒ Erreur lors du dÃ©placement : `{e}`", ephemeral=True)
        return

    # Ping la personne dans son channel
    try:
        await channel_found.send(
            f"â¸ï¸ {membre.mention} â€” Votre channel a Ã©tÃ© mis en **indisponibilitÃ©** par la direction.\n"
            f"Vous serez recontactÃ© lors de votre retour."
        )
    except:
        pass

    await interaction.followup.send(
        f"âœ… **{clean_name}** est dÃ©sormais en indisponibilitÃ©.\n"
        f"ðŸ“‚ Channel dÃ©placÃ© : {channel_found.mention}",
        ephemeral=True
    )


@bot.tree.command(name="reouverture", description="Remettre un employÃ© en activitÃ© (remet son channel dans la bonne catÃ©gorie)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="L'employÃ© Ã  rÃ©activer")
async def reouverture(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    clean_name = get_clean_name(membre)
    clean_name_normalized = normalize_employee_key(clean_name)

    # DÃ©tecter le grade depuis le pseudo
    grade_found = None
    for tag in ["DIR", "CAD", "CDS", "MED", "PSY", "INF", "ADS", "STG", "INT", "EMT"]:
        if f"[{tag}]" in membre.display_name:
            grade_found = tag
            break

    if not grade_found:
        await interaction.followup.send(
            f"âŒ Impossible de dÃ©tecter le grade de **{membre.display_name}**.",
            ephemeral=True
        )
        return

    # RÃ©cupÃ©rer la bonne catÃ©gorie selon le grade
    cat_key = GRADE_TO_CATEGORY.get(grade_found)
    categories_data = load_categories()
    cat_id = categories_data.get(cat_key, 0)
    category_target = guild.get_channel(cat_id) if cat_id else None

    if not category_target:
        await interaction.followup.send(
            f"âŒ CatÃ©gorie pour le grade **{grade_found}** introuvable. VÃ©rifie la config des catÃ©gories.",
            ephemeral=True
        )
        return

    # Trouver le channel dans la catÃ©gorie indispo
    channel_found = None
    category_indispo = guild.get_channel(CATEGORY_INDISPO_ID)
    if category_indispo:
        for ch in category_indispo.text_channels:
            if ch.name and len(ch.name) > 1 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
                if get_channel_employee_key(ch) == clean_name_normalized:
                    channel_found = ch
                    break

    # Si pas trouvÃ© en indispo, chercher partout
    if not channel_found:
        for ch in guild.text_channels:
            if ch.name and len(ch.name) > 1 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
                if get_channel_employee_key(ch) == clean_name_normalized:
                    channel_found = ch
                    break

    if not channel_found:
        await interaction.followup.send(
            f"âŒ Aucun channel trouvÃ© pour **{clean_name}**.",
            ephemeral=True
        )
        return

    # Remettre dans la bonne catÃ©gorie
    try:
        await channel_found.edit(category=category_target)
    except Exception as e:
        await interaction.followup.send(f"âŒ Erreur lors du dÃ©placement : `{e}`", ephemeral=True)
        return

    # Ping la personne
    try:
        await channel_found.send(
            f"âœ… {membre.mention} â€” Bienvenue de retour ! Votre channel a Ã©tÃ© rÃ©activÃ© par la direction."
        )
    except:
        pass

    await interaction.followup.send(
        f"âœ… **{clean_name}** est de retour en activitÃ©.\n"
        f"ðŸ“‚ Channel remis dans **{category_target.name}** : {channel_found.mention}",
        ephemeral=True
    )


@bot.tree.command(name="setup_avertissements", description="Envoyer le tableau des avertissements dans le salon dÃ©diÃ© (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_avertissements(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    global avert_board_message_id
    avert_board_message_id = None  # Force la recrÃ©ation
    await update_avert_board(interaction.guild)
    await interaction.followup.send("âœ… Tableau des avertissements envoyÃ© !", ephemeral=True)


@bot.tree.command(name="avertissement", description="Donner un avertissement Ã  un employÃ© EMS (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    membre="L'employÃ© concernÃ©",
    raison="Raison de l'avertissement"
)
async def avertissement(interaction: discord.Interaction, membre: discord.Member, raison: str):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    data = load_avertissements()
    user_id = str(membre.id)
    now = datetime.now(timezone.utc)

    # Purge des anciens (>30j) pour cet employÃ©
    existing = data.get(user_id, [])
    existing = [av for av in existing if (now - datetime.fromisoformat(av["date"])).days < 30]

    # Ajouter le nouvel avertissement
    existing.append({
        "raison": raison,
        "date": now.isoformat(),
        "par": interaction.user.display_name
    })
    data[user_id] = existing
    save_avertissements(data)

    count = len(existing)
    emoji = get_avert_emoji(count)
    clean = get_clean_name(membre)

    # DM Ã  l'employÃ©
    try:
        dm_embed = discord.Embed(
            title="âš ï¸ Avertissement â€” Los Santos EMS",
            color=get_avert_emoji(count) == "ðŸ”´" and discord.Color.red() or discord.Color.orange() if count >= 2 else discord.Color.yellow(),
            description=(
                f"Vous avez reÃ§u un **avertissement officiel** de la direction des EMS.\n\n"
                f"**Motif :** {raison}\n"
                f"**DÃ©livrÃ© par :** {interaction.user.display_name}\n"
                f"**Avertissements actifs :** {count}/3\n\n"
                f"{'âš ï¸ Attention : vous avez atteint la limite. Des mesures disciplinaires pourront Ãªtre prises.' if count >= 3 else 'Tout avertissement supplÃ©mentaire pourra entraÃ®ner des sanctions.'}\n\n"
                f"*Les avertissements sont automatiquement annulÃ©s aprÃ¨s 30 jours.*"
            )
        )
        dm_embed.set_footer(text="ðŸš‘ Los Santos Fire & Medical Department")
        await membre.send(embed=dm_embed)
    except:
        pass

    # Alerte direction si 3+
    if count >= 3:
        role_ping = guild.get_role(AVERT_ROLE_PING_ID)
        ping_str = role_ping.mention if role_ping else ""
        avert_channel = guild.get_channel(AVERT_CHANNEL_ID)
        if avert_channel:
            alert_embed = discord.Embed(
                title="ðŸš¨ Alerte â€” 3Ã¨me Avertissement",
                color=discord.Color.red(),
                description=(
                    f"**{clean}** vient de recevoir son **{count}Ã¨me avertissement**.\n\n"
                    f"**Motif :** {raison}\n"
                    f"**DÃ©livrÃ© par :** {interaction.user.display_name}\n\n"
                    f"Une action disciplinaire est recommandÃ©e."
                )
            )
            alert_embed.set_footer(text="ðŸš‘ EMS System")
            await avert_channel.send(
                content=ping_str,
                embed=alert_embed,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )

    confirm_embed = discord.Embed(
        title=f"{emoji} Avertissement enregistrÃ©",
        color=discord.Color.red() if count >= 3 else discord.Color.orange() if count == 2 else discord.Color.yellow(),
        description=(
            f"**EmployÃ© :** {membre.mention}\n"
            f"**Motif :** {raison}\n"
            f"**Avertissements actifs :** {count}/3"
        )
    )
    confirm_embed.set_footer(text="ðŸš‘ EMS System")
    await interaction.followup.send(embed=confirm_embed, ephemeral=True)

    await update_avert_board(guild)


@bot.tree.command(name="retirer_avertissement", description="Retirer un avertissement d'un employÃ© EMS (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="L'employÃ© concernÃ©")
async def retirer_avertissement(interaction: discord.Interaction, membre: discord.Member):
    await interaction.response.defer(ephemeral=True)

    data = load_avertissements()
    user_id = str(membre.id)
    now = datetime.now(timezone.utc)
    existing = data.get(user_id, [])
    existing = [av for av in existing if (now - datetime.fromisoformat(av["date"])).days < 30]

    if not existing:
        await interaction.followup.send(
            f"âœ… **{get_clean_name(membre)}** n'a aucun avertissement actif.",
            ephemeral=True
        )
        return

    # Retirer le plus ancien
    existing.pop(0)
    data[user_id] = existing
    save_avertissements(data)

    await interaction.followup.send(
        f"âœ… Avertissement retirÃ© pour **{get_clean_name(membre)}**.\n"
        f"**Restants :** {len(existing)}/3",
        ephemeral=True
    )
    await update_avert_board(interaction.guild)


@bot.tree.command(name="redispatch", description="Forcer un nouveau dispatch des employÃ©s en service")
@app_commands.checks.has_permissions(administrator=True)
async def redispatch(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    global dispatch_message_id
    dispatch_message_id = None  # Force recrÃ©ation
    await run_dispatch(interaction.guild)
    count = len(active_services)
    if count < 4:
        await interaction.followup.send(
            f"âš ï¸ Seulement **{count}** employÃ©(s) en service. Il en faut au minimum **4** pour lancer un dispatch.",
            ephemeral=True
        )
    else:
        await interaction.followup.send("âœ… Dispatch relancÃ© !", ephemeral=True)


@bot.tree.command(name="annonce", description="Envoyer une annonce dans un salon (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def annonce_command(interaction: discord.Interaction):
    await interaction.response.send_modal(AnnonceModal())


@bot.tree.command(name="prise", description="Envoie l'annonce de prise de service avec boutons")
@app_commands.checks.has_permissions(administrator=True)
async def prise_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    service_channel = bot.get_channel(SERVICE_CHANNEL_ID)
    if not service_channel:
        await interaction.followup.send("âŒ Channel de service introuvable.", ephemeral=True)
        return
    
    embed = build_service_embed()
    
    msg = await service_channel.send(content="<@&838102445095256068>", embed=embed, view=ServiceView())
    
    global service_status_message_id
    service_status_message_id = msg.id
    save_service_message_id(msg.id)
    
    await interaction.followup.send("âœ… Annonce de prise de service envoyÃ©e !", ephemeral=True)

@app_commands.checks.has_permissions(administrator=True)
async def services_command(interaction: discord.Interaction):
    await interaction.response.defer()
    
    services = load_services()
    week = get_week_start()
    week_data = services.get(week, {})
    
    if not week_data:
        await interaction.followup.send(
            embed=discord.Embed(
                title="ðŸ“Š Services de la Semaine",
                description="Aucun service enregistrÃ© cette semaine.",
                color=EMS_RED
            )
        )
        return
    
    # Trier par heures dÃ©croissantes
    sorted_employees = sorted(week_data.items(), key=lambda x: x[1]["total_hours"], reverse=True)
    
    embed = discord.Embed(
        title=f"ðŸ“Š Services - Semaine du {week}",
        color=EMS_RED
    )
    
    total_hours_all = 0
    total_reas_all = 0
    
    for employee_key, data in sorted_employees:
        hours = data["total_hours"]
        reas = data["total_reas"]
        sessions = data["sessions"]
        total_hours_all += hours
        total_reas_all += reas
        
        h = int(hours)
        m = int((hours - h) * 60)
        display_name = employee_key.replace("-", " ").title()
        
        embed.add_field(
            name=f"ðŸ‘¤ {display_name}",
            value=f"â±ï¸ {h}h{m:02d} | ðŸš‘ {reas} rÃ©as | ðŸ“‹ {sessions} services",
            inline=False
        )
    
    # En service actuellement
    en_service = []
    for uid, svc in active_services.items():
        start = datetime.fromisoformat(svc["start"])
        minutes = int((now_paris() - start).total_seconds() // 60)
        en_service.append(f"â€¢ **{svc['employee_key']}** - {minutes} min (ðŸš‘ {svc.get('reas_count', 0)} rÃ©as)")
    
    if en_service:
        embed.add_field(
            name="ðŸŸ¢ En service actuellement",
            value="\n".join(en_service),
            inline=False
        )
    
    h_total = int(total_hours_all)
    m_total = int((total_hours_all - h_total) * 60)
    embed.set_footer(text=f"ðŸš‘ EMS System | Total: {h_total}h{m_total:02d} - {total_reas_all} rÃ©as")
    
    await interaction.followup.send(embed=embed)

# --- TÃ‚CHE AUTO FIN DE SERVICE (20 MIN SANS RÃ‰A) ---
@tasks.loop(minutes=2)
async def check_inactive_services():
    """VÃ©rifie toutes les 2 min si un employÃ© n'a pas envoyÃ© de rÃ©a depuis 20 min"""
    try:
        # Purge du set processed_reactions pour Ã©viter une croissance infinie en mÃ©moire
        global processed_reactions
        if len(processed_reactions) > 5000:
            processed_reactions = set()

        now = now_paris()
        to_remove = []
        
        threshold_seconds = get_inactivity_threshold_seconds()  # variable selon l'heure (voir INACTIVITY_THRESHOLDS)
        for user_id, service in active_services.items():
            try:
                last_rea = datetime.fromisoformat(service["last_rea"])
                if (now - last_rea).total_seconds() >= threshold_seconds:
                    to_remove.append(user_id)
            except (ValueError, KeyError):
                pass  # Service mal formÃ©, ignorer
        
        for user_id in to_remove:
            service = active_services.pop(user_id)
            start = datetime.fromisoformat(service["start"])
            end = now
            duree = end - start
            hours = round(duree.total_seconds() / 3600, 2)
            minutes = int(duree.total_seconds() // 60)
            reas = service.get("reas_count", 0)
            employee_key = service["employee_key"]
            
            # Enregistrer les heures
            add_service_hours(employee_key, hours, reas)

            # Retirer le rÃ´le "En Service" + kick vocal
            try:
                guild_auto = bot.get_guild(config["GUILD_ID"])
                if guild_auto:
                    member_auto = guild_auto.get_member(int(user_id))
                    role_en_service = guild_auto.get_role(1524175137908457543)
                    if member_auto and role_en_service:
                        await member_auto.remove_roles(role_en_service)
                    if member_auto and member_auto.voice and member_auto.voice.channel:
                        if member_auto.voice.channel.id in SERVICE_VOICE_IDS:
                            waiting_channel = guild_auto.get_channel(WAITING_VOICE_ID)
                            if waiting_channel:
                                await member_auto.move_to(waiting_channel)
                            else:
                                await member_auto.move_to(None)
            except:
                pass
            
            # Log dans le channel de logs
            log_channel = bot.get_channel(config.get("LOGS_CHANNEL_ID"))
            if log_channel:
                try:
                    embed = discord.Embed(
                        title="â° Fin de Service Automatique",
                        description=f"**{employee_key}** - Service terminÃ© automatiquement (30 min sans rÃ©a).",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="â±ï¸ DurÃ©e", value=f"{minutes} min", inline=True)
                    embed.add_field(name="ðŸš‘ RÃ©as", value=f"{reas}", inline=True)
                    embed.set_footer(text=f"ðŸš‘ EMS System | {end.strftime('%H:%M')}")
                    await log_channel.send(embed=embed)
                except:
                    pass
            
            # DM Ã  l'utilisateur
            try:
                guild = bot.get_guild(config["GUILD_ID"])
                if guild:
                    member = guild.get_member(int(user_id))
                    if member:
                        await member.send(
                            f"â° **Fin de service automatique**\n\n"
                            f"Ton service a Ã©tÃ© terminÃ© automatiquement car tu n'as pas envoyÃ© de rÃ©a depuis 30 minutes.\n\n"
                            f"â±ï¸ DurÃ©e : **{minutes} min**\n"
                            f"ðŸš‘ RÃ©as : **{reas}**"
                        )
            except:
                pass
        
        if to_remove:
            print(f"[{now.strftime('%H:%M:%S')}] â° Fin de service auto: {len(to_remove)} employÃ©(s)")
            await update_service_status(force=True)
            for g in bot.guilds:
                await run_dispatch(g)
    
    except Exception as e:
        print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur check_inactive_services: {e}")

@check_inactive_services.before_loop
async def before_check_inactive():
    await bot.wait_until_ready()

# --- TÃ‚CHE AUTO REFRESH MESSAGE PDS ---
@tasks.loop(minutes=5)
async def refresh_service_message():
    """RafraÃ®chit le message PDS toutes les 5 minutes (seulement si quelqu'un est en service)"""
    global service_status_message_id, last_pds_update
    try:
        if not service_status_message_id:
            return
        
        # Ne rafraÃ®chir que s'il y a des gens en service
        if not active_services:
            return
        
        channel = bot.get_channel(SERVICE_CHANNEL_ID)
        if not channel:
            return
        
        try:
            msg = await channel.fetch_message(service_status_message_id)
            await msg.edit(embed=build_service_embed())
            last_pds_update = now_paris()
        except discord.NotFound:
            service_status_message_id = None
            save_service_message_id(None)
    except Exception as e:
        if e: print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur refresh PDS: {repr(e)}")

@refresh_service_message.before_loop
async def before_refresh_service():
    await bot.wait_until_ready()
    await asyncio.sleep(30)

# --- TÃ‚CHE DE MISE Ã€ JOUR DES DESCRIPTIONS AVEC DÃ‰LAI ---
@tasks.loop(minutes=10)
async def update_descriptions_background():
    """Met Ã  jour les descriptions de tous les channels EMS toutes les 5 minutes"""
    try:
        guild = bot.get_guild(config["GUILD_ID"])
        if not guild:
            return
        
        stats = load_stats()
        if not stats:
            return
        
        updated_count = 0
        skipped_count = 0

        # Construire l'index une seule fois (O(n) au lieu de O(nÂ²))
        channel_index = {}
        for ch in guild.text_channels:
            if ch.name and len(ch.name) > 0 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
                channel_index[get_channel_employee_key(ch)] = ch

        for key, value in stats.items():
            try:
                # Lookup O(1) grÃ¢ce Ã  l'index
                channel = channel_index.get(key)
                if not channel:
                    continue
                
                # Calculer la nouvelle description
                new_emoji = get_color_emoji(value)
                current_emoji = channel.name[0]
                bonus_days = get_week_bonus_count(key)
                bonus_text = f" {bonus_days}M" if bonus_days > 0 else ""
                new_topic = f"{new_emoji} {value}/100{bonus_text}"
                
                # VÃ©rifier si quelque chose a changÃ©
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
                
                # DÃ©lai de 35 secondes entre chaque channel modifiÃ© (rate limit Discord: 2 PATCH/10min/channel)
                await asyncio.sleep(35)
                
            except Exception as e:
                if e:
                    print(f"[{now_paris().strftime('%H:%M:%S')}] âš ï¸ Erreur update {key}: {repr(e)}")
                await asyncio.sleep(60)
        
        if updated_count > 0:
            print(f"[{now_paris().strftime('%H:%M:%S')}] ðŸ”„ Descriptions: {updated_count} modifiÃ©s, {skipped_count} inchangÃ©s")
        
    except Exception as e:
        print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur descriptions: {e}")

@update_descriptions_background.before_loop
async def before_update_descriptions():
    await bot.wait_until_ready()
    await asyncio.sleep(180)  # Attendre 3 min aprÃ¨s connexion avant la premiÃ¨re mise Ã  jour

@bot.event
async def on_ready():
    global BOT_START_TIME
    if BOT_START_TIME is None:
        BOT_START_TIME = now_paris()
    # Fix catÃ©gorie EMT
    global CATEGORY_EMT_ID
    cats = load_categories()
    cats["CATEGORY_EMT_ID"] = 1482044597822689388
    save_categories(cats)
    CATEGORY_EMT_ID = 1482044597822689388
    
    stats = load_stats()
    total_reas = sum(stats.values()) if stats else 0
    
    log(f'ðŸ“‚ DATA_DIR = {DATA_DIR}')
    log(f'âœ… Bot connectÃ©: {bot.user}')
    log(f'ðŸ“Š {len(stats)} employÃ©s | {total_reas} rÃ©as totales')
    
    # Recharger l'ID du message PDS persistant
    global service_status_message_id
    saved_msg_id = load_service_message_id()
    if saved_msg_id:
        service_status_message_id = saved_msg_id
        log(f'ðŸ“¡ Message PDS rechargÃ©: {saved_msg_id}')
    
    # Enregistrer la vue persistante pour les boutons
    bot.add_view(ServiceView())
    bot.add_view(DispatchView())
    bot.add_view(DispatchDivisionView())
    
    # DÃ©marrer les tÃ¢ches si pas dÃ©jÃ  en cours
    if not auto_backup_stats.is_running():
        auto_backup_stats.start()
    if not update_descriptions_background.is_running():
        update_descriptions_background.start()
    if not check_inactive_services.is_running():
        check_inactive_services.start()
    if not refresh_service_message.is_running():
        refresh_service_message.start()
    if not check_rea_inactivity.is_running():
        check_rea_inactivity.start()
    if not auto_snapshot_current_week.is_running():
        auto_snapshot_current_week.start()

    # PrÃ©-remplir les donnÃ©es de la semaine du 20/07 (une seule fois, idempotent)
    seed_last_week_data_once()
    
    # Initialiser le tableau des matricules
    for g in bot.guilds:
        try:
            await update_matricule_board(g)
        except Exception as e:
            log(f'âŒ Erreur mise Ã  jour matricules: {e}')
    
    log(f'âœ… Sauvegarde auto (5min) + Mise Ã  jour descriptions (10min) + Check services (2min) + Refresh PDS (5min) activÃ©es')

    # Initialiser le tableau des avertissements
    for g in bot.guilds:
        await update_avert_board(g)

    # Initialiser le dispatch
    for g in bot.guilds:
        await run_dispatch(g)
    
    print(f'âœ… Sauvegarde auto (5min) + Mise Ã  jour descriptions (10min) + Check services (2min) + Refresh PDS (5min) activÃ©es')


@bot.tree.command(name="parrain", description="Associe un parrain Ã  un stagiaire (accÃ¨s Ã  son channel pour vÃ©rif)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(stagiaire="Le stagiaire Ã  parrainer", parrain="Le parrain/mentor")
async def parrain(interaction: discord.Interaction, stagiaire: discord.Member, parrain: discord.Member):
    await interaction.response.defer()
    guild = interaction.guild

    stagiaire_clean = get_clean_name(stagiaire)
    parrain_clean = get_clean_name(parrain)
    stagiaire_key = normalize_employee_key(stagiaire_clean)
    parrain_key = normalize_employee_key(parrain_clean)

    # Sauvegarder l'association
    data = load_parrainage()
    data[stagiaire_key] = {
        'parrain_key': parrain_key,
        'parrain_nom': parrain_clean,
        'parrain_discord_id': str(parrain.id),
        'stagiaire_nom': stagiaire_clean,
        'date': now_paris().isoformat(),
    }
    save_parrainage(data)

    # Donner l'accÃ¨s au channel personnel du stagiaire pour que le parrain puisse vÃ©rifier
    channel_found = None
    for ch in guild.text_channels:
        if ch.name and len(ch.name) > 1 and ch.name[0] in ['ðŸ”´', 'ðŸŸ ', 'ðŸŸ¢']:
            if get_channel_employee_key(ch) == stagiaire_key:
                channel_found = ch
                break

    if channel_found:
        try:
            await channel_found.set_permissions(parrain, view_channel=True, send_messages=True, read_message_history=True)
        except Exception as e:
            print(f"Erreur permission channel parrainage: {e}")

    embed = discord.Embed(
        title="ðŸŽ“ Parrainage Ã©tabli",
        description=(
            f"**{parrain.mention}** est maintenant le parrain de **{stagiaire.mention}**.\n\n"
            f"{'âœ… AccÃ¨s accordÃ© au channel personnel du stagiaire.' if channel_found else 'âš ï¸ Channel du stagiaire introuvable â€” accÃ¨s non accordÃ© automatiquement.'}"
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text="ðŸš‘ EMS System | Mentorat")
    await interaction.followup.send(embed=embed)

    # DM aux deux
    try:
        await stagiaire.send(f"ðŸŽ“ Tu as Ã©tÃ© mis en binÃ´me avec **{parrain_clean}** comme mentor ! N'hÃ©site pas Ã  lui poser tes questions.")
    except:
        pass
    try:
        await parrain.send(f"ðŸŽ“ Tu es maintenant le parrain/mentor de **{stagiaire_clean}**. Tu as accÃ¨s Ã  son channel personnel pour vÃ©rifier ses rÃ©as.")
    except:
        pass


@bot.tree.command(name="retirer_parrain", description="Retire l'association de parrainage d'un stagiaire")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(stagiaire="Le stagiaire dont on retire le parrain")
async def retirer_parrain(interaction: discord.Interaction, stagiaire: discord.Member):
    await interaction.response.defer()
    guild = interaction.guild
    stagiaire_key = normalize_employee_key(get_clean_name(stagiaire))

    data = load_parrainage()
    if stagiaire_key not in data:
        await interaction.followup.send("âŒ Ce stagiaire n'a pas de parrain enregistrÃ©.")
        return

    old_parrain_id = data[stagiaire_key].get('parrain_discord_id')
    del data[stagiaire_key]
    save_parrainage(data)

    # Retirer l'accÃ¨s au channel
    if old_parrain_id:
        try:
            old_parrain_member = guild.get_member(int(old_parrain_id))
            if old_parrain_member:
                for ch in guild.text_channels:
                    if ch.name and len(ch.name) > 1 and ch.name[0] in ['ðŸ”´', 'ðŸŸ ', 'ðŸŸ¢']:
                        if get_channel_employee_key(ch) == stagiaire_key:
                            await ch.set_permissions(old_parrain_member, overwrite=None)
                            break
        except Exception as e:
            print(f"Erreur retrait permission parrainage: {e}")

    await interaction.followup.send(f"âœ… Parrainage retirÃ© pour **{get_clean_name(stagiaire)}**.")


@bot.tree.command(name="repair_keys", description="Fusionne les anciennes clÃ©s employÃ© cassÃ©es vers les clÃ©s propres actuelles (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(dry_run="True = simulation sans changement (dÃ©faut), False = applique vraiment")
async def repair_keys(interaction: discord.Interaction, dry_run: bool = True):
    """
    RÃ©pare les fichiers stats.json, absences.json, formations.json, daily_reas.json,
    embauche.json et promo_history.json qui peuvent contenir des clÃ©s employÃ©
    hÃ©ritÃ©es d'anciennes versions du bot (ex: 'psy-claire-foo' au lieu de 'claire-foo').

    Fonctionne en comparant chaque clÃ© stockÃ©e Ã  la liste des clÃ©s canoniques
    actuellement calculÃ©es depuis les pseudos Discord rÃ©els des membres.
    """
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    # 1. Construire les clÃ©s canoniques actuelles (basÃ©es sur les pseudos Discord rÃ©els)
    canonical_keys = set()
    for member in guild.members:
        if member.bot:
            continue
        match = _re.search(r'\[(\w+)\]\s+(\d{2})\s+(.+)', member.display_name)
        if match:
            nom = match.group(3).strip()
        else:
            nom = member.display_name
        k = normalize_employee_key(nom)
        if k:
            canonical_keys.add(k)

    KNOWN_EXTRA_PREFIXES = ['pdg-', 'cpdg-', 'cad-', 'psy-', 'stg-', 'dir-', 'cds-', 'med-', 'inf-', 'ads-', 'int-', 'emt-', 'drh-', 'rh-']

    def find_canonical(old_key):
        if old_key in canonical_keys:
            return old_key
        stripped = old_key
        changed = True
        while changed:
            changed = False
            for p in KNOWN_EXTRA_PREFIXES:
                if stripped.startswith(p) and stripped[len(p):] :
                    stripped = stripped[len(p):]
                    changed = True
                    break
        if stripped in canonical_keys:
            return stripped
        # Suffix match : l'ancienne clÃ© se termine par une clÃ© canonique connue
        for ck in canonical_keys:
            if old_key.endswith(ck) and old_key != ck and len(ck) >= 4:
                return ck
        return old_key  # rien trouvÃ©, on garde tel quel

    report_lines = []
    total_changes = 0

    # 2. STATS_FILE â€” {key: int}
    stats = robust_load_json(STATS_FILE, {})
    new_stats = {}
    stats_changes = []
    for old_k, v in stats.items():
        new_k = find_canonical(old_k)
        if new_k != old_k:
            stats_changes.append(f"`{old_k}` ({v}) â†’ `{new_k}`")
            total_changes += 1
        new_stats[new_k] = new_stats.get(new_k, 0) + v
    if stats_changes:
        report_lines.append(f"**ðŸ“Š stats.json** ({len(stats_changes)} clÃ©s)\n" + "\n".join(f"â€¢ {l}" for l in stats_changes[:10]))
        if not dry_run:
            atomic_write_json(STATS_FILE, new_stats)

    # 3. ABSENCE_FILE â€” {key: {date: {...}}}
    absences = robust_load_json(ABSENCE_FILE, {})
    new_abs = {}
    abs_changes = []
    for old_k, v in absences.items():
        new_k = find_canonical(old_k)
        if new_k != old_k:
            abs_changes.append(f"`{old_k}` â†’ `{new_k}`")
            total_changes += 1
        if new_k not in new_abs:
            new_abs[new_k] = {}
        new_abs[new_k].update(v)
    if abs_changes:
        report_lines.append(f"**ðŸ“‹ absences.json** ({len(abs_changes)} clÃ©s)\n" + "\n".join(f"â€¢ {l}" for l in abs_changes[:10]))
        if not dry_run:
            atomic_write_json(ABSENCE_FILE, new_abs)

    # 4. FORMATIONS_FILE â€” {key: [str,...]}
    formations = robust_load_json(FORMATIONS_FILE, {})
    new_forms = {}
    forms_changes = []
    for old_k, v in formations.items():
        new_k = find_canonical(old_k)
        if new_k != old_k:
            forms_changes.append(f"`{old_k}` â†’ `{new_k}`")
            total_changes += 1
        if new_k not in new_forms:
            new_forms[new_k] = []
        for item in v:
            if item not in new_forms[new_k]:
                new_forms[new_k].append(item)
    if forms_changes:
        report_lines.append(f"**ðŸŽ“ formations.json** ({len(forms_changes)} clÃ©s)\n" + "\n".join(f"â€¢ {l}" for l in forms_changes[:10]))
        if not dry_run:
            atomic_write_json(FORMATIONS_FILE, new_forms)

    # 5. DAILY_REAS_FILE â€” {date: {key: int}}
    daily = robust_load_json(DAILY_REAS_FILE, {})
    daily_changes_count = 0
    new_daily = {}
    for date_k, day_data in daily.items():
        new_day = {}
        for old_k, v in day_data.items():
            new_k = find_canonical(old_k)
            if new_k != old_k:
                daily_changes_count += 1
                total_changes += 1
            new_day[new_k] = new_day.get(new_k, 0) + v
        new_daily[date_k] = new_day
    if daily_changes_count:
        report_lines.append(f"**ðŸ“ˆ daily_reas.json** ({daily_changes_count} clÃ©s fusionnÃ©es)")
        if not dry_run:
            atomic_write_json(DAILY_REAS_FILE, new_daily)

    # 6. EMBAUCHE_FILE â€” {key: date_str}
    embauche = robust_load_json(EMBAUCHE_FILE, {})
    new_emb = {}
    emb_changes = []
    for old_k, v in embauche.items():
        new_k = find_canonical(old_k)
        if new_k != old_k:
            emb_changes.append(f"`{old_k}` â†’ `{new_k}`")
            total_changes += 1
        if new_k not in new_emb:
            new_emb[new_k] = v
    if emb_changes:
        report_lines.append(f"**ðŸŸ¢ embauche.json** ({len(emb_changes)} clÃ©s)\n" + "\n".join(f"â€¢ {l}" for l in emb_changes[:10]))
        if not dry_run:
            atomic_write_json(EMBAUCHE_FILE, new_emb)

    # 7. PROMO_HISTORY_FILE â€” {key: [dict,...]}
    promos = robust_load_json(PROMO_HISTORY_FILE, {})
    new_promos = {}
    promo_changes = []
    for old_k, v in promos.items():
        new_k = find_canonical(old_k)
        if new_k != old_k:
            promo_changes.append(f"`{old_k}` â†’ `{new_k}`")
            total_changes += 1
        if new_k not in new_promos:
            new_promos[new_k] = []
        new_promos[new_k].extend(v)
    if promo_changes:
        report_lines.append(f"**ðŸ“ˆ promo_history.json** ({len(promo_changes)} clÃ©s)\n" + "\n".join(f"â€¢ {l}" for l in promo_changes[:10]))
        if not dry_run:
            atomic_write_json(PROMO_HISTORY_FILE, new_promos)

    # Rapport
    mode = "ðŸ” **SIMULATION** â€” aucun changement appliquÃ©" if dry_run else "âœ… **RÃ‰PARATION APPLIQUÃ‰E**"
    embed = discord.Embed(
        title=f"{'ðŸ”' if dry_run else 'âœ…'} RÃ©paration des clÃ©s employÃ©",
        description=f"{mode}\n\n**{total_changes} clÃ©(s)** au total dÃ©tectÃ©e(s) comme obsolÃ¨te(s)/mal formÃ©e(s).",
        color=discord.Color.orange() if dry_run else discord.Color.green()
    )
    if report_lines:
        for line in report_lines[:6]:
            title, _, body = line.partition("\n")
            embed.add_field(name=title.strip('*'), value=body[:1000] or "â€”", inline=False)
    else:
        embed.add_field(name="âœ… Aucun problÃ¨me dÃ©tectÃ©", value="Toutes les clÃ©s sont dÃ©jÃ  propres et cohÃ©rentes.", inline=False)

    embed.set_footer(text=f"{'SimulÃ©' if dry_run else 'AppliquÃ©'} â€” {total_changes} clÃ©(s) concernÃ©e(s)")
    embed.timestamp = now_paris()

    if dry_run and total_changes > 0:
        embed.description += "\n\n> ðŸ’¡ Lance `/repair_keys dry_run:False` pour appliquer rÃ©ellement les corrections."

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="migration_grades", description="Migre les pseudos [INT]â†’[STG] et attribue le rÃ´le PSY aux membres qui ont le tag [PSY] (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(dry_run="True = simulation sans changement (dÃ©faut), False = applique vraiment")
async def migration_grades(interaction: discord.Interaction, dry_run: bool = True):
    """
    HiÃ©rarchie : EMT â†’ Stagiaire â†’ Aide-Soignant â†’ Infirmier â†’ Psychologue â†’ MÃ©decin â†’ Chef Adjoint â†’ Directeur MÃ©dical

    Ce que fait cette commande :
    1. Renomme les pseudos [INT] xx Nom â†’ [STG] xx Nom  (rÃ´le Discord inchangÃ©)
    2. Donne le rÃ´le Psychologue aux membres qui ont [PSY] dans leur pseudo mais pas le bon rÃ´le Discord
    3. Ne touche PAS aux [CDS] â€” ils gardent leur grade (Chef Adjoint)
    """
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    # IDs des rÃ´les corrects
    R_PSY = 1528560704511148092   # RÃ´le Psychologue
    R_INF = 894311352225656862    # Infirmier (retirÃ© quand passage PSY)
    CAT_PSY = 1528562582804365312 # CatÃ©gorie Psychologue

    int_to_stg = []   # membres dont le pseudo contient [INT]
    psy_no_role = []  # membres avec tag [PSY] mais sans rÃ´le PSY
    errors = []

    for member in guild.members:
        if member.bot:
            continue
        nick = member.display_name
        member_role_ids = {r.id for r in member.roles}

        # 1. [INT] dans le pseudo â†’ renommer en [STG]
        if "[INT]" in nick.upper():
            
            new_nick = _re.sub(r"(?i)\[INT\]", "[STG]", nick)
            int_to_stg.append({"member": member, "old": nick, "new": new_nick})
            if not dry_run:
                try:
                    await member.edit(nick=new_nick)
                except Exception as e:
                    errors.append(f"Renommage `{nick}`: {e}")

        # 2. Tag [PSY] dans le pseudo mais pas le rÃ´le PSY Discord
        if "[PSY]" in nick.upper() and R_PSY not in member_role_ids:
            psy_no_role.append({"member": member, "nick": nick})
            if not dry_run:
                try:
                    role_psy = guild.get_role(R_PSY)
                    role_inf = guild.get_role(R_INF)
                    # Retirer rÃ´le INF si prÃ©sent (PSY remplace INF dans la hiÃ©rarchie)
                    if role_inf and R_INF in member_role_ids:
                        await member.remove_roles(role_inf)
                    if role_psy:
                        await member.add_roles(role_psy)
                    # DÃ©placer le channel dans catÃ©gorie PSY
                    clean_norm = normalize_employee_key(get_clean_name(member))
                    new_cat = guild.get_channel(CAT_PSY)
                    for ch in guild.text_channels:
                        if ch.name and len(ch.name) > 1 and ch.name[0] in ["ðŸ”´", "ðŸŸ ", "ðŸŸ¢"]:
                            if get_channel_employee_key(ch) == clean_norm:
                                try:
                                    await ch.edit(category=new_cat)
                                except:
                                    pass
                                break
                except Exception as e:
                    errors.append(f"RÃ´le PSY `{nick}`: {e}")

    # Rapport
    mode = "ðŸ” **SIMULATION** â€” aucun changement appliquÃ©" if dry_run else "âœ… **MIGRATION APPLIQUÃ‰E**"
    embed = discord.Embed(
        title=f"{'ðŸ”' if dry_run else 'âœ…'} Migration des grades EMS",
        description=f"{mode}\n\n**HiÃ©rarchie :** EMT â†’ STG â†’ ADS â†’ INF â†’ PSY â†’ MED â†’ CDS â†’ CAD â†’ DIR",
        color=discord.Color.orange() if dry_run else discord.Color.green()
    )

    # Section [INT] â†’ [STG]
    if int_to_stg:
        val = "\n".join(f"â€¢ `{r['old']}` â†’ `{r['new']}`" for r in int_to_stg[:15])
        if len(int_to_stg) > 15:
            val += f"\n_â€¦et {len(int_to_stg)-15} autres_"
        embed.add_field(name=f"ðŸ“‹ [INT] â†’ [STG] ({len(int_to_stg)} membres)", value=val, inline=False)
    else:
        embed.add_field(name="ðŸ“‹ [INT] â†’ [STG]", value="âœ… Aucun pseudo [INT] trouvÃ©", inline=False)

    # Section PSY
    if psy_no_role:
        val = "\n".join(f"â€¢ {r['member'].mention} â€” `{r['nick']}`" for r in psy_no_role[:10])
        embed.add_field(name=f"ðŸ§  [PSY] sans rÃ´le PSY ({len(psy_no_role)} membres)", value=val, inline=False)
    else:
        embed.add_field(name="ðŸ§  [PSY] sans rÃ´le PSY", value="âœ… Tous les PSY ont le bon rÃ´le", inline=False)

    # CDS â€” info seulement, pas de changement
    embed.add_field(
        name="ðŸ¥ Chef Adjoint [CDS]",
        value="âœ… Non touchÃ© â€” les membres [CDS] gardent leur grade intact",
        inline=False
    )

    if errors:
        embed.add_field(name=f"âŒ Erreurs ({len(errors)})", value="\n".join(errors[:5]), inline=False)

    total = len(int_to_stg) + len(psy_no_role)
    embed.set_footer(text=f"{'SimulÃ©' if dry_run else 'AppliquÃ©'} â€” {total} membre(s) concernÃ©(s)")
    embed.timestamp = now_paris()

    if dry_run and total > 0:
        embed.description += "\n\n> ðŸ’¡ Lance `/migration_grades dry_run:False` pour appliquer."
    elif dry_run and total == 0:
        embed.description += "\n\nâœ… Rien Ã  migrer, tout est dÃ©jÃ  Ã  jour !"

    await interaction.followup.send(embed=embed, ephemeral=True)
    if not dry_run:
        await update_matricule_board(guild)


# --- COMMANDE /blacklist_cv ---

@bot.tree.command(name="blacklist_cv", description="GÃ©rer la blacklist des candidatures CV (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    action="Ajouter ou retirer de la blacklist",
    membre="Membre Ã  blacklister / dÃ©bloquer",
    raison="Raison de la blacklist"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Ajouter Ã  la blacklist", value="add"),
    app_commands.Choice(name="Retirer de la blacklist", value="remove"),
    app_commands.Choice(name="Voir la blacklist", value="list"),
])
async def blacklist_cv_cmd(
    interaction: discord.Interaction,
    action: str,
    membre: discord.Member = None,
    raison: str = "Non prÃ©cisÃ©e"
):
    await interaction.response.defer(ephemeral=True)
    bl = load_blacklist_cv()

    if action == "add":
        if not membre:
            await interaction.followup.send("âŒ Tu dois mentionner un membre.", ephemeral=True)
            return
        bl[str(membre.id)] = {
            "date": datetime.utcnow().isoformat(),
            "raison": raison,
            "blacklisted_by": str(interaction.user.id),
        }
        save_blacklist_cv(bl)
        await interaction.followup.send(
            f"ðŸš« **{membre.display_name}** ajoutÃ© Ã  la blacklist CV.\n"
            f"Raison : {raison}\nDÃ©blocage automatique dans 1 semaine.",
            ephemeral=True
        )
        try:
            await membre.send(
                f"ðŸš« **Blacklist CV â€” EMS**\n\n"
                f"Vous avez Ã©tÃ© ajoutÃ© Ã  la liste noire des candidatures EMS.\n"
                f"**Raison :** {raison}\n"
                f"Vous pourrez re-postuler dans **1 semaine**."
            )
        except:
            pass

    elif action == "remove":
        if not membre:
            await interaction.followup.send("âŒ Tu dois mentionner un membre.", ephemeral=True)
            return
        uid = str(membre.id)
        if uid in bl:
            del bl[uid]
            save_blacklist_cv(bl)
            await interaction.followup.send(f"âœ… **{membre.display_name}** retirÃ© de la blacklist CV.", ephemeral=True)
        else:
            await interaction.followup.send(f"â„¹ï¸ **{membre.display_name}** n'est pas dans la blacklist.", ephemeral=True)

    elif action == "list":
        if not bl:
            await interaction.followup.send("âœ… Aucune blacklist CV active.", ephemeral=True)
            return
        lines = []
        now = datetime.utcnow()
        for uid, entry in list(bl.items()):
            bl_date = datetime.fromisoformat(entry["date"])
            unlock = bl_date + timedelta(weeks=1)
            still_bl = now < unlock
            member_obj = interaction.guild.get_member(int(uid))
            name = member_obj.display_name if member_obj else f"ID:{uid}"
            remaining = max(unlock - now, timedelta(0))
            status = f"â³ {remaining.days}j {remaining.seconds//3600}h restants" if still_bl else "âœ… DÃ©lai expirÃ©"
            lines.append(f"â€¢ **{name}** â€” {entry.get('raison', '?')} â€” {status}")
        embed = discord.Embed(
            title="ðŸš« Blacklist CV",
            description="\n".join(lines[:20]),
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


# --- ALERTE INACTIVITÃ‰ RÃ‰A (3-5 jours sans rÃ©a) ---
REA_INACTIVITY_FILE = os.path.join(DATA_DIR, 'rea_last_activity.json')
REA_INACTIVITY_ALERTED_FILE = os.path.join(DATA_DIR, 'rea_inactivity_alerted.json')
REA_INACTIVITY_CHANNEL_ID = 1485278000986587333  # Channel direction
REA_INACTIVITY_ROLE_ID = 838120186585940010       # RÃ´le direction
REA_INACTIVITY_DAYS = 4                           # Seuil : 4 jours sans rÃ©a

@tasks.loop(hours=6)
async def auto_snapshot_current_week():
    """Sauvegarde pÃ©riodique (toutes les 6h) d'un instantanÃ© PROVISOIRE de la semaine en cours
    dans l'historique multi-semaines, pour ne jamais perdre plus de quelques heures de donnÃ©es
    mÃªme en cas de crash/redÃ©marrage avant que /semaine soit lancÃ©e."""
    try:
        week_key = get_week_start()
        current_stats = load_stats()
        snapshot = {
            'week_key': week_key,
            'stats': dict(current_stats),
            'evening_reas': dict(evening_reas),
            'services': load_services().get(week_key, {}),
            'saved_at': now_paris().isoformat(),
        }
        save_week_to_history(week_key, snapshot, finalized=False)
        print(f"[{now_paris().strftime('%H:%M:%S')}] ðŸ“¸ Auto-snapshot semaine en cours ({week_key}) sauvegardÃ©")
    except Exception as e:
        print(f"Erreur auto_snapshot_current_week: {e}")


@tasks.loop(hours=6)
async def check_rea_inactivity():
    """VÃ©rifie toutes les 6h si un employÃ© n'a pas fait de rÃ©a depuis REA_INACTIVITY_DAYS jours.
    Envoie une alerte dans le channel direction et ping le rÃ´le direction, une seule fois par pÃ©riode."""
    try:
        stats = load_stats()
        if not stats:
            return

        last_activity = robust_load_json(REA_INACTIVITY_FILE, {})
        alerted = robust_load_json(REA_INACTIVITY_ALERTED_FILE, {})

        now = now_paris()
        threshold = timedelta(days=REA_INACTIVITY_DAYS)
        newly_alerted = []

        for emp_key, rea_count in stats.items():
            if rea_count == 0:
                continue  # Jamais fait de rÃ©a â€” pas encore suivi

            last_str = last_activity.get(emp_key)
            if not last_str:
                continue  # Pas de date d'activitÃ© enregistrÃ©e

            try:
                last_dt = datetime.fromisoformat(last_str)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=ZoneInfo("Europe/Paris"))
            except:
                continue

            delta = now - last_dt
            if delta < threshold:
                # Actif â€” rÃ©initialiser l'alerte si elle avait Ã©tÃ© envoyÃ©e
                if emp_key in alerted:
                    del alerted[emp_key]
                continue

            if emp_key in alerted:
                continue  # DÃ©jÃ  alertÃ© pour cette pÃ©riode

            newly_alerted.append((emp_key, delta))
            alerted[emp_key] = now.isoformat()

        atomic_write_json(REA_INACTIVITY_ALERTED_FILE, alerted)

        if not newly_alerted:
            return

        # Envoyer une seule alerte groupÃ©e dans le channel direction
        for guild in bot.guilds:
            channel = guild.get_channel(REA_INACTIVITY_CHANNEL_ID)
            if not channel:
                continue
            direction_role = guild.get_role(REA_INACTIVITY_ROLE_ID)
            ping = direction_role.mention if direction_role else ""

            lines = []
            for emp_key, delta in newly_alerted:
                jours = delta.days
                display = emp_key.replace("-", " ").title()
                lines.append(f"â€¢ **{display}** â€” {jours} jours sans rÃ©animation")

            embed = discord.Embed(
                title="âš ï¸ Alerte InactivitÃ© â€” RÃ©animations",
                description=(
                    f"Les employÃ©s suivants n'ont pas effectuÃ© de rÃ©animation depuis plus de **{REA_INACTIVITY_DAYS} jours** :\n\n"
                    + "\n".join(lines)
                ),
                color=discord.Color.orange()
            )
            embed.set_footer(text="ðŸš‘ EMS System | Alerte automatique")
            embed.timestamp = now
            await channel.send(content=ping, embed=embed)

    except Exception as e:
        print(f"[check_rea_inactivity] âŒ Erreur: {e}")

@check_rea_inactivity.before_loop
async def before_check_rea_inactivity():
    await bot.wait_until_ready()

# --- COMMANDE /absence - SIMPLE ET DIRECTE ---
ABSENCE_FILE = os.path.join(DATA_DIR, 'absences.json')
ABSENCE_LOG_CHANNEL = 1523355492368515222

def load_absences():
    """Charge les absences du fichier"""
    return robust_load_json(ABSENCE_FILE, {})

def save_absences(data):
    """Sauvegarde les absences"""
    atomic_write_json(ABSENCE_FILE, data)

def parse_date_short(date_str: str) -> str:
    """Convertit jj/mm en YYYY-MM-DD avec l'annÃ©e courante"""
    parts = date_str.strip().split('/')
    if len(parts) == 2:
        day, month = parts
        year = datetime.now().year
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    raise ValueError(f"Format invalide: {date_str}")

def fmt_date_display(date_iso: str) -> str:
    """Convertit YYYY-MM-DD en jj/mm"""
    try:
        parts = date_iso.split('-')
        return f"{parts[2]}/{parts[1]}"
    except:
        return date_iso

@bot.tree.command(name="absence", description="DÃ©clarer une absence (format date: jj/mm)")
@app_commands.describe(
    membre="Membre Ã  marquer absent (mention)",
    date_debut="Date de dÃ©but (ex: 15/07)",
    date_retour="Date de retour (ex: 20/07) - optionnel",
    raison="Raison de l'absence"
)
async def declare_absence(
    interaction: discord.Interaction,
    membre: discord.Member,
    date_debut: str,
    raison: str,
    date_retour: str = None,
):
    """Enregistrer une absence directement dans le fichier et loguer"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Convertir les dates jj/mm â†’ YYYY-MM-DD
        date_debut_iso = parse_date_short(date_debut)
        date_retour_iso = parse_date_short(date_retour) if date_retour else None
        
        # Normaliser le nom depuis le pseudo Discord
        employee_key = normalize_employee_key(membre.display_name)
        if not employee_key:
            await interaction.followup.send("âŒ Impossible de normaliser le nom de cet employÃ©", ephemeral=True)
            return
        
        # Charger les absences
        absences = load_absences()
        
        if employee_key not in absences:
            absences[employee_key] = {}
        
        # CrÃ©er l'enregistrement
        absence_record = {
            'date_debut': date_debut_iso,
            'raison': raison,
        }
        if date_retour_iso:
            absence_record['date_retour'] = date_retour_iso
        
        absences[employee_key][date_debut_iso] = absence_record
        save_absences(absences)
        
        # Confirmation Ã  l'auteur
        await interaction.followup.send(
            f"âœ… Absence enregistrÃ©e pour {membre.mention} â€” {date_debut}/{date_retour or '?'} â€” {raison}",
            ephemeral=True
        )
        
        # Log dans le channel dÃ©diÃ©
        log_channel = bot.get_channel(ABSENCE_LOG_CHANNEL)
        if log_channel:
            date_display = date_debut
            if date_retour:
                date_display += f" â†’ {date_retour}"
            log_msg = f"ðŸ“‹ **Absence dÃ©clarÃ©e**\n{membre.mention} â€” **{date_display}** â€” {raison}"
            await log_channel.send(log_msg)
        
    except ValueError as e:
        await interaction.followup.send(f"âŒ Format de date invalide. Utilise jj/mm (ex: 15/07)\n{e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"âŒ Erreur: {str(e)}", ephemeral=True)

# --- LOG DE CHAQUE COMMANDE UTILISÃ‰E ---
COMMAND_LOG_CHANNEL_ID = 1494003170299613254

@bot.listen('on_interaction')
async def log_all_commands(interaction: discord.Interaction):
    """Log chaque commande slash utilisÃ©e dans le channel dÃ©diÃ©"""
    # Ne logger que les commandes slash (type 2 = application command)
    if interaction.type != discord.InteractionType.application_command:
        return
    try:
        log_channel = bot.get_channel(COMMAND_LOG_CHANNEL_ID)
        if log_channel:
            ts = now_paris().strftime('%d/%m/%Y %H:%M:%S')
            user = interaction.user
            channel_mention = interaction.channel.mention if interaction.channel else "DM"
            cmd_name = interaction.command.name if interaction.command else interaction.data.get("name", "?")
            params = ""
            if interaction.namespace:
                params_list = [f"{k}={v}" for k, v in vars(interaction.namespace).items() if v is not None]
                if params_list:
                    params = " | Params: " + ", ".join(params_list)
            embed = discord.Embed(
                title="ðŸ“‹ Commande utilisÃ©e",
                description=f"**/{cmd_name}**{params}",
                color=discord.Color.blue()
            )
            embed.add_field(name="ðŸ‘¤ Utilisateur", value=f"{user.mention} (`{user.name}`, ID: `{user.id}`)", inline=False)
            embed.add_field(name="ðŸ“ Channel", value=channel_mention, inline=True)
            embed.add_field(name="ðŸ• Date", value=ts, inline=True)
            embed.set_footer(text="ðŸ“‹ Log des commandes")
            await log_channel.send(embed=embed)
    except Exception as e:
        print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur log commande: {e}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Gestionnaire d'erreurs pour les commandes slash"""
    if isinstance(error, app_commands.MissingPermissions):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("âŒ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
            else:
                await interaction.followup.send("âŒ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
        except:
            pass
    else:
        print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur commande /{interaction.command.name if interaction.command else '?'}: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("âŒ Une erreur est survenue.", ephemeral=True)
            else:
                await interaction.followup.send("âŒ Une erreur est survenue.", ephemeral=True)
        except:
            pass

# --- TÃ‚CHE DE SAUVEGARDE AUTOMATIQUE ---
@tasks.loop(minutes=5)
async def auto_backup_stats():
    """Sauvegarde automatique des stats toutes les 5 minutes"""
    try:
        # Utiliser la variable stats en mÃ©moire directement (Ã©vite une lecture disque inutile)
        global stats_data
        try:
            _stats = stats_data
        except NameError:
            _stats = load_stats()
        total_reas = sum(_stats.values()) if _stats else 0
        atomic_write_json(STATS_FILE, _stats, make_backup=True)
        print(f"[{now_paris().strftime('%H:%M:%S')}] ðŸ’¾ Sauvegarde: {len(_stats)} employÃ©s, {total_reas} rÃ©as")
    except Exception as e:
        print(f"[{now_paris().strftime('%H:%M:%S')}] âŒ Erreur sauvegarde: {e}")

@auto_backup_stats.before_loop
async def before_auto_backup():
    await bot.wait_until_ready()

if __name__ == "__main__":
    # --- SERVEUR WEB DASHBOARD ---
    web_app = Flask(__name__, static_folder=None)
    
    # DÃ©sactiver les logs des requÃªtes HTTP (trop de bruit)
    import logging
    log_werkzeug = logging.getLogger('werkzeug')
    log_werkzeug.setLevel(logging.ERROR)
    
    @web_app.route('/')
    def index():
        return send_file(os.path.join(os.path.dirname(__file__), 'dashboard.html'))

    @web_app.route('/api/data')
    def api_data():
        try:
            stats = robust_load_json(STATS_FILE, {})
            services = robust_load_json(SERVICE_FILE, {})
            avertissements = robust_load_json(AVERT_FILE, {})
            absences = robust_load_json(ABSENCE_FILE, {})

                # Construire une map employee_key -> {grade, display_name, discord_id, role_ids}
            EMS_ROLE_GRADES = {
                895047492784238652: 'EMT',
                838102445095256069: 'STG',  # Stagiaire
                1528560704511148092: 'PSY',  # Psychologue
                1528561040663777310: 'CAD',  # Chef Adjoint [CAD]
                1088116715998687273: 'ADS',
                894311352225656862: 'INF',
                840288242547818507: 'MED',
                838102445095256071: 'CDS',   # Chef de Service
                1088570974603055195: 'DIR',
                1206320774978474054: 'CPDG',  # Co-PDG
                917156484335403100: 'RH',
                838102445103775747: 'DRH',
                838102445103775752: 'PDG',
            }
            # Raffinage : si le tag pseudo contient [PSY], on override le grade
            # (car PSY et STG partagent le mÃªme rÃ´le Discord pour l'instant)
            employee_info = {}
            for guild in bot.guilds:
                for member in guild.members:
                    if member.bot:
                        continue
                    member_role_ids = {r.id for r in member.roles}
                    member_role_strs = [str(r.id) for r in member.roles]
                    match = _re.search(r'\[(\w+)\]\s+(\d{2})\s+(.+)', member.display_name)
                    if match:
                        grade = match.group(1).upper()
                        matricule = match.group(2)
                        nom = match.group(3).strip()
                    else:
                        grade = None
                        for role_id_int, role_grade in EMS_ROLE_GRADES.items():
                            if role_id_int in member_role_ids:
                                grade = role_grade
                                break
                        if not grade:
                            continue
                        matricule = 'â€”'
                        nom = member.display_name
                    # Override grade PSY/STG si tag pseudo prÃ©sent (mÃªme rÃ´le Discord)
                    disp_upper = member.display_name.upper()
                    if '[PSY]' in disp_upper:
                        grade = 'PSY'
                    elif '[CAD]' in disp_upper:
                        grade = 'CAD'
                    elif '[STG]' in disp_upper and grade == 'STG':
                        grade = 'STG'
                    # Normalisation
                    if grade == 'INT':
                        grade = 'STG'
                    key = normalize_employee_key(nom)
                    employee_info[key] = {
                        'grade': grade,
                        'matricule': matricule,
                        'display_name': nom,
                        'discord_id': str(member.id),
                        'role_ids': member_role_strs,
                    }

                # Matricules: {mat: {grade, nom, key}}
            mat_map = {}
            for key, info in employee_info.items():
                mat_map[info['matricule']] = {
                    'grade': info['grade'],
                    'nom': info['display_name'],
                    'key': key,
                }

            # AgrÃ©ger evening_reas (clÃ© "employee_key_YYYY-MM-DD") par employÃ©
            evening_reas_summary = {}
            for ev_key, count in evening_reas.items():
                emp_key = ev_key.rsplit('_', 1)[0]
                evening_reas_summary[emp_key] = evening_reas_summary.get(emp_key, 0) + count

            return jsonify({
                'stats': stats,
                'services': services,
                'active_services': {k: {**v, 'discord_id': k} for k, v in active_services.items()},
                'avertissements': robust_load_json(AVERT_FILE, {}),
                'matricules': direction_matricules,
                'dispatch': dispatch_state,
                'employee_info': employee_info,
                'mat_map': mat_map,
                'coffre': coffre_tracking,
                'dispatch_history': dispatch_history[-200:],
                'formations': robust_load_json(FORMATIONS_FILE, {}),
                'virer_reminders': robust_load_json(VIRER_REMINDERS_FILE, []),
                'bonuses_week': get_week_bonus_summary(),
                'absences': absences,
                'daily_reas': robust_load_json(DAILY_REAS_FILE, {}),
                'embauche': robust_load_json(EMBAUCHE_FILE, {}),
                'server_date': now_paris().strftime('%Y-%m-%d'),
                'cv_tracking': robust_load_json(CV_TRACKING_FILE, {}),
                'blacklist_cv': robust_load_json(BLACKLIST_CV_FILE, {}),
                'promo_history': robust_load_json(PROMO_HISTORY_FILE, {}),
                'rea_last_activity': robust_load_json(REA_INACTIVITY_FILE, {}),
                'rea_alerted': robust_load_json(REA_INACTIVITY_ALERTED_FILE, {}),
                'evening_reas_summary': evening_reas_summary,
                'week_snapshot': load_week_snapshot(),
                'week_history': load_week_history(),
                'parrainage': load_parrainage(),
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

        # Shared state for dashboard (reunion, coffre deletions)
    shared_state = {
        'reunion_pos': [],
        'reunion_neg': [],
        'coffre_deleted': [],
        'concours': {'active': False},
        'primes': {},
    }

    @web_app.route('/manifest.json')
    def pwa_manifest():
        """Manifest PWA pour l'installation sur Ã©cran d'accueil (iPhone/Android)."""
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, 'manifest.json')
        if os.path.exists(path):
            return send_file(path, mimetype='application/manifest+json')
        return "Non trouvÃ©", 404

    @web_app.route('/icon-<size>.png')
    def pwa_icon(size):
        """IcÃ´nes de l'app pour l'Ã©cran d'accueil (180, 192, 512, 1024)."""
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, 'static_icons', f'icon-{size}.png')
        if os.path.exists(path):
            return send_file(path, mimetype='image/png')
        return "Non trouvÃ©", 404

    @web_app.route('/service-worker.js')
    def pwa_service_worker():
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'service-worker.js')
        return send_file(path, mimetype='application/javascript')

    @web_app.route('/aptitude')
    def aptitude_page():
        """Site de gÃ©nÃ©ration de bilans d'aptitude LSPD/BCSO."""
        pub_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aptitude.html')
        if os.path.exists(pub_path):
            return send_file(pub_path)
        fallback = os.path.join(os.getcwd(), 'aptitude.html')
        if os.path.exists(fallback):
            return send_file(fallback)
        return "Page non trouvÃ©e", 404

    @web_app.route('/api/aptitude/generate', methods=['POST'])
    def api_aptitude_generate():
        """GÃ©nÃ¨re un bilan d'aptitude (image) et l'envoie dans le channel LSPD ou BCSO."""
        try:
            data = request.get_json() or {}
            org = (data.get('org') or '').strip().upper()
            matricule = (data.get('matricule') or '').strip()
            nom_officier = (data.get('nom_officier') or '').strip()
            civilite = (data.get('civilite') or 'm').strip()
            apte = bool(data.get('apte'))
            praticien_nom = (data.get('praticien_nom') or '').strip()
            praticien_grade = (data.get('praticien_grade') or '').strip()
            photo_data_uri = data.get('photo', '')

            if org not in ('LSPD', 'BCSO'):
                return jsonify({'ok': False, 'error': 'Organisation invalide (LSPD ou BCSO requis)'}), 400
            if not matricule or not nom_officier or not praticien_nom or not praticien_grade:
                return jsonify({'ok': False, 'error': "Matricule, nom de l'officier et infos praticien requis"}), 400

            photo_bytes = None
            if photo_data_uri and photo_data_uri.startswith('data:'):
                try:
                    _, b64data = photo_data_uri.split(',', 1)
                    photo_bytes = base64.b64decode(b64data)
                except Exception as _decode_err:
                    print(f"Erreur dÃ©codage photo aptitude: {_decode_err}")

            report_data = {
                'org': org,
                'matricule': matricule,
                'nom_officier': nom_officier,
                'civilite': civilite,
                'apte': apte,
                'praticien_nom': praticien_nom,
                'praticien_grade': praticien_grade,
                'ref_doc': f"EMS-APT-{now_paris().strftime('%Y%m%d-%H%M')}",
                'date_doc': now_paris().strftime('%d/%m/%Y'),
                'photo_bytes': photo_bytes,
            }

            img_buf = generate_aptitude_report(report_data)
            if not img_buf:
                return jsonify({'ok': False, 'error': "GÃ©nÃ©ration de l'image indisponible (Pillow manquant)"}), 500

            CHANNEL_LSPD = 1158372479971115009
            CHANNEL_BCSO = 1297607904790188143
            target_channel_id = CHANNEL_LSPD if org == 'LSPD' else CHANNEL_BCSO

            async def send_report():
                for guild in bot.guilds:
                    ch = guild.get_channel(target_channel_id)
                    if not ch:
                        continue
                    img_buf.seek(0)
                    file = discord.File(img_buf, filename=f"bilan_aptitude_{matricule}.png")
                    statut_txt = "âœ… APTE" if apte else "â›” NON APTE"
                    await ch.send(
                        content=f"ðŸ“‹ **Nouveau bilan d'aptitude** â€” {nom_officier} (Matricule {matricule}) â€” {statut_txt}",
                        file=file
                    )
                    return True
                return False

            future = _asyncio.run_coroutine_threadsafe(send_report(), bot.loop)
            sent = future.result(timeout=15)

            return jsonify({'ok': True, 'sent_to_discord': sent})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/patients')
    def patients_page():
        """Page de gestion des dossiers mÃ©dicaux patients"""
        pub_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'patients.html')
        if os.path.exists(pub_path):
            return send_file(pub_path)
        fallback = os.path.join(os.getcwd(), 'patients.html')
        if os.path.exists(fallback):
            return send_file(fallback)
        return "Page non trouvÃ©e", 404

    @web_app.route('/api/patients/list', methods=['GET'])
    def api_patients_list():
        try:
            patients = load_patients()
            q = (request.args.get('q') or '').strip().lower()
            results = []
            for pid, p in patients.items():
                nom = p.get('nom', '')
                prenom = p.get('prenom', '')
                full = f"{prenom} {nom}".strip().lower()
                if q and q not in full:
                    continue
                results.append({
                    'id': pid,
                    'nom': nom,
                    'prenom': prenom,
                    'created': p.get('created', ''),
                    'dossiers_count': len(p.get('dossiers', [])),
                })
            results.sort(key=lambda x: (x['nom'] + x['prenom']).lower())
            return jsonify({'ok': True, 'patients': results})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/patients/create', methods=['POST'])
    def api_patients_create():
        try:
            data = request.get_json()
            nom = (data.get('nom') or '').strip()
            prenom = (data.get('prenom') or '').strip()
            date_naissance = (data.get('date_naissance') or '').strip()
            photo = data.get('photo', '')  # data URI base64, optionnel

            if not nom or not prenom:
                return jsonify({'ok': False, 'error': 'Nom et prÃ©nom requis'}), 400

            patients = load_patients()
            import uuid as _uuid
            pid = f"{slugify_patient_id(prenom + ' ' + nom)}-{_uuid.uuid4().hex[:6]}"

            photo_filename = save_patient_photo(pid, photo) if photo else ''

            patients[pid] = {
                'nom': nom,
                'prenom': prenom,
                'date_naissance': date_naissance,
                'photo_filename': photo_filename,  # fichier sÃ©parÃ©, pas de base64 dans le JSON
                'created': now_paris().isoformat(),
                'dossiers': [],
            }
            save_patients(patients)
            return jsonify({'ok': True, 'id': pid})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/patients/photo/<filename>', methods=['GET'])
    def api_patients_photo(filename):
        """Sert l'image d'un patient depuis le disque (pas depuis le JSON)."""
        try:
            safe_name = os.path.basename(filename)  # Ã©vite tout path traversal
            filepath = os.path.join(PATIENT_PHOTOS_DIR, safe_name)
            if os.path.exists(filepath):
                return send_file(filepath)
            return "Photo non trouvÃ©e", 404
        except Exception as e:
            return str(e), 500

    @web_app.route('/api/patients/<pid>', methods=['GET'])
    def api_patients_get(pid):
        try:
            patients = load_patients()
            if pid not in patients:
                return jsonify({'ok': False, 'error': 'Patient introuvable'}), 404
            p = dict(patients[pid])
            photo_filename = p.get('photo_filename', '')
            p['photo_url'] = f"/api/patients/photo/{photo_filename}" if photo_filename else ''
            return jsonify({'ok': True, 'patient': {**p, 'id': pid}})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/patients/<pid>/attestation', methods=['POST'])
    def api_patients_attestation(pid):
        """GÃ©nÃ¨re une attestation mÃ©dicale officielle (image) et l'envoie dans le channel Discord dÃ©diÃ©."""
        try:
            patients = load_patients()
            if pid not in patients:
                return jsonify({'ok': False, 'error': 'Patient introuvable'}), 404
            p = patients[pid]

            data = request.get_json() or {}
            lieu = (data.get('lieu') or '').strip()
            heure = (data.get('heure') or '').strip()
            motif = (data.get('motif') or '').strip()
            disposition_type = (data.get('disposition_type') or 'repos').strip()
            duree = (data.get('duree') or '').strip()
            destinataire = (data.get('destinataire') or '').strip()
            praticien_nom = (data.get('praticien_nom') or '').strip()
            praticien_grade = (data.get('praticien_grade') or '').strip()
            note = (data.get('note') or '').strip()
            photo_data_uri = data.get('photo', '')  # nouvelle photo carte identitÃ©, optionnelle (data URI base64)

            if not motif or not praticien_nom:
                return jsonify({'ok': False, 'error': 'Motif et praticien requis'}), 400

            nom = p.get('nom', '')
            prenom = p.get('prenom', '')
            date_naissance = p.get('date_naissance', '')
            today_str = now_paris().strftime('%d/%m/%Y')
            ref_doc = f"EMS-{now_paris().strftime('%Y-%m%d')}-{pid[-4:].upper()}"

            # DÃ©terminer la photo Ã  intÃ©grer sur le document :
            # 1) une nouvelle photo envoyÃ©e avec ce formulaire (prioritaire)
            # 2) sinon la photo dÃ©jÃ  enregistrÃ©e sur la fiche du patient
            photo_bytes = None
            new_photo_filename = None
            if photo_data_uri and photo_data_uri.startswith('data:'):
                try:
                    _, b64data = photo_data_uri.split(',', 1)
                    photo_bytes = base64.b64decode(b64data)
                    # On en profite pour la sauvegarder comme photo du patient si elle n'en a pas encore
                    if not p.get('photo_filename'):
                        new_photo_filename = save_patient_photo(pid, photo_data_uri)
                except Exception as _decode_err:
                    print(f"Erreur dÃ©codage photo attestation: {_decode_err}")
            elif p.get('photo_filename'):
                try:
                    existing_path = os.path.join(PATIENT_PHOTOS_DIR, p['photo_filename'])
                    if os.path.exists(existing_path):
                        with open(existing_path, 'rb') as _f:
                            photo_bytes = _f.read()
                except Exception as _read_err:
                    print(f"Erreur lecture photo existante: {_read_err}")

            if new_photo_filename:
                patients[pid]['photo_filename'] = new_photo_filename
                save_patients(patients)
                p = patients[pid]

            if disposition_type == 'inapte':
                disposition = f"{'Monsieur' if data.get('civilite')!='mme' else 'Madame'} {prenom} {nom} est dÃ©clarÃ©{'e' if data.get('civilite')=='mme' else ''} INAPTE AU TRAVAIL {duree or 'pour la journÃ©e du ' + today_str}."
            elif disposition_type == 'apte':
                disposition = f"{'Monsieur' if data.get('civilite')!='mme' else 'Madame'} {prenom} {nom} est dÃ©clarÃ©{'e' if data.get('civilite')=='mme' else ''} APTE Ã€ REPRENDRE LE TRAVAIL {duree or 'Ã  compter du ' + today_str}."
            else:
                disposition = f"{'Monsieur' if data.get('civilite')!='mme' else 'Madame'} {prenom} {nom} doit observer un repos mÃ©dical {duree or ('pour la journÃ©e du ' + today_str)}."

            avis_intro = (
                f"Je soussignÃ©, {praticien_nom}, {praticien_grade}, certifie avoir pris en charge "
                f"{'le sieur' if data.get('civilite')!='mme' else 'la dame'} {prenom} {nom}"
                f"{' Ã  la suite de : ' + motif if motif else ''}. "
                f"Au vu des blessures/symptÃ´mes constatÃ©s et par mesure de sÃ©curitÃ© mÃ©dicale, "
                f"les dispositions suivantes ont Ã©tÃ© prises."
            )

            att_data = {
                'ref_doc': ref_doc,
                'emetteur': f"{praticien_nom}, {praticien_grade}",
                'destinataire': destinataire or 'â€”',
                'date_doc': today_str,
                'nom': nom.upper(),
                'prenom': prenom,
                'date_naissance': date_naissance,
                'heure': heure or today_str,
                'lieu': lieu or 'â€”',
                'motif': motif,
                'avis_intro': avis_intro,
                'disposition': disposition,
                'note': note,
                'praticien_nom': praticien_nom,
                'praticien_grade': praticien_grade,
                'praticien_prenom_sig': praticien_nom,
                'footer': f"DOCUMENT OFFICIEL EMS LOS SANTOS â€” DOCUMENT RP{' Ã€ DESTINATION EXCLUSIVE DE ' + destinataire.upper() if destinataire else ''} â€” TOUTE FALSIFICATION EST PASSIBLE DE POURSUITES.",
                'photo_bytes': photo_bytes,
            }

            img_buf = generate_attestation_medicale(att_data)
            if not img_buf:
                return jsonify({'ok': False, 'error': "GÃ©nÃ©ration de l'image indisponible (Pillow manquant)"}), 500

            # Sauvegarder aussi une trace dans le dossier du patient
            patients[pid].setdefault('dossiers', []).append({
                'date': now_paris().isoformat(),
                'symptome': motif,
                'description': f"Attestation gÃ©nÃ©rÃ©e â€” {disposition}",
                'examens': '',
                'conseils': note,
                'par': praticien_nom,
            })
            save_patients(patients)

            async def send_attestation():
                CHANNEL_ID = 1531700699010826250
                for guild in bot.guilds:
                    ch = guild.get_channel(CHANNEL_ID)
                    if not ch:
                        continue
                    img_buf.seek(0)
                    file = discord.File(img_buf, filename=f"attestation_{pid}.png")
                    await ch.send(
                        content=f"ðŸ“„ **Nouvelle attestation mÃ©dicale** â€” {prenom} {nom}",
                        file=file
                    )
                    return True
                return False

            future = _asyncio.run_coroutine_threadsafe(send_attestation(), bot.loop)
            sent = future.result(timeout=15)

            return jsonify({'ok': True, 'sent_to_discord': sent})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/patients/<pid>/dossier', methods=['POST'])
    def api_patients_add_dossier(pid):
        try:
            patients = load_patients()
            if pid not in patients:
                return jsonify({'ok': False, 'error': 'Patient introuvable'}), 404

            data = request.get_json()
            symptome = (data.get('symptome') or '').strip()
            description = (data.get('description') or '').strip()
            examens = (data.get('examens') or '').strip()
            conseils = (data.get('conseils') or '').strip()
            par = (data.get('par') or '').strip()

            if not (symptome or description or examens or conseils):
                return jsonify({'ok': False, 'error': 'Au moins un champ requis'}), 400

            entry = {
                'date': now_paris().isoformat(),
                'symptome': symptome,
                'description': description,
                'examens': examens,
                'conseils': conseils,
                'par': par,
            }
            patients[pid].setdefault('dossiers', []).append(entry)
            save_patients(patients)
            return jsonify({'ok': True, 'dossiers': patients[pid]['dossiers']})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/patients/<pid>', methods=['DELETE'])
    def api_patients_delete(pid):
        try:
            patients = load_patients()
            if pid in patients:
                delete_patient_photo(patients[pid].get('photo_filename', ''))
                del patients[pid]
                save_patients(patients)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/patients/<pid>', methods=['PUT'])
    def api_patients_edit(pid):
        """Modifie les infos de base d'un patient (nom, prÃ©nom, photo)."""
        try:
            patients = load_patients()
            if pid not in patients:
                return jsonify({'ok': False, 'error': 'Patient introuvable'}), 404

            data = request.get_json()
            nom = (data.get('nom') or '').strip()
            prenom = (data.get('prenom') or '').strip()
            date_naissance = data.get('date_naissance', None)
            photo = data.get('photo', None)  # None = ne pas changer la photo, '' = supprimer la photo

            if not nom or not prenom:
                return jsonify({'ok': False, 'error': 'Nom et prÃ©nom requis'}), 400

            patients[pid]['nom'] = nom
            patients[pid]['prenom'] = prenom
            if date_naissance is not None:
                patients[pid]['date_naissance'] = date_naissance.strip()
            if photo:  # nouvelle photo fournie (data URI)
                delete_patient_photo(patients[pid].get('photo_filename', ''))
                patients[pid]['photo_filename'] = save_patient_photo(pid, photo)
            elif photo == '':  # explicitement vidÃ©e
                delete_patient_photo(patients[pid].get('photo_filename', ''))
                patients[pid]['photo_filename'] = ''
            save_patients(patients)
            p = dict(patients[pid])
            photo_filename = p.get('photo_filename', '')
            p['photo_url'] = f"/api/patients/photo/{photo_filename}" if photo_filename else ''
            return jsonify({'ok': True, 'patient': {**p, 'id': pid}})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/patients/<pid>/dossier/<int:idx>', methods=['PUT'])
    def api_patients_edit_dossier(pid, idx):
        """Modifie une entrÃ©e mÃ©dicale prÃ©cise d'un patient."""
        try:
            patients = load_patients()
            if pid not in patients:
                return jsonify({'ok': False, 'error': 'Patient introuvable'}), 404
            dossiers = patients[pid].get('dossiers', [])
            if idx < 0 or idx >= len(dossiers):
                return jsonify({'ok': False, 'error': 'EntrÃ©e introuvable'}), 404

            data = request.get_json()
            for field in ('symptome', 'description', 'examens', 'conseils'):
                if field in data:
                    dossiers[idx][field] = (data.get(field) or '').strip()
            save_patients(patients)
            return jsonify({'ok': True, 'dossiers': dossiers})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/patients/<pid>/dossier/<int:idx>', methods=['DELETE'])
    def api_patients_delete_dossier(pid, idx):
        """Supprime une entrÃ©e mÃ©dicale prÃ©cise d'un patient."""
        try:
            patients = load_patients()
            if pid not in patients:
                return jsonify({'ok': False, 'error': 'Patient introuvable'}), 404
            dossiers = patients[pid].get('dossiers', [])
            if idx < 0 or idx >= len(dossiers):
                return jsonify({'ok': False, 'error': 'EntrÃ©e introuvable'}), 404
            dossiers.pop(idx)
            patients[pid]['dossiers'] = dossiers
            save_patients(patients)
            return jsonify({'ok': True, 'dossiers': dossiers})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/reunion')
    def reunion_public():
        """Page publique anonyme de prÃ©paration de rÃ©union"""
        pub_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reunion_public.html')
        if os.path.exists(pub_path):
            return send_file(pub_path)
        # Fallback : mÃªme dossier courant
        fallback = os.path.join(os.getcwd(), 'reunion_public.html')
        if os.path.exists(fallback):
            return send_file(fallback)
        return "Page non trouvÃ©e", 404

    @web_app.route('/api/reunion_public', methods=['GET'])
    def reunion_public_get():
        """Retourne seulement les points positifs/nÃ©gatifs de la rÃ©union (anonyme)"""
        return jsonify({
            'pos': shared_state.get('reunion_pos', []),
            'neg': shared_state.get('reunion_neg', []),
        })

    @web_app.route('/api/reunion_public', methods=['POST'])
    def reunion_public_post():
        """Ajoute un point (anonyme) Ã  la liste de rÃ©union"""
        try:
            data = request.get_json()
            typ = data.get('type', '')   # 'pos' ou 'neg'
            text = data.get('text', '').strip()
            if typ not in ('pos', 'neg') or not text or len(text) > 300:
                return jsonify({'ok': False, 'error': 'ParamÃ¨tres invalides'}), 400
            key = 'reunion_pos' if typ == 'pos' else 'reunion_neg'
            shared_state.setdefault(key, [])
            shared_state[key].append(text)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/shared', methods=['GET'])
    def get_shared():
        return jsonify(shared_state)

    @web_app.route('/api/shared', methods=['POST'])
    def set_shared():
        try:
            data = request.get_json()
            if data:
                shared_state.update(data)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @web_app.route('/api/coffre_delete', methods=['POST'])
    def coffre_delete():
        try:
            data = request.get_json()
            key = data.get('key', '')
            if key in coffre_tracking:
                del coffre_tracking[key]
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @web_app.route('/api/ping_employee', methods=['POST'])
    def ping_employee():
        try:
            data = request.get_json()
            key = data.get('key', '')
            discord_id = data.get('discord_id', '')

            async def do_ping():
                for guild in bot.guilds:
                    member = None
                    if discord_id:
                        try:
                            member = guild.get_member(int(discord_id))
                        except:
                            pass
                    if not member:
                        for m in guild.members:
                            if normalize_employee_key(get_clean_name(m)) == key:
                                member = m
                                break
                    if not member:
                        continue
                        # Trouver le channel de l'employÃ©
                    clean_norm = normalize_employee_key(get_clean_name(member))
                    for ch in guild.text_channels:
                        if ch.name and len(ch.name) > 1 and ch.name[0] in ['ðŸ”´','ðŸŸ ','ðŸŸ¢']:
                            if get_channel_employee_key(ch) == clean_norm:
                                await ch.send(
                                    f"âš ï¸ {member.mention} â€” La direction vous demande de **remonter votre activitÃ©**.\n"
                                    f"Votre quota de rÃ©as est insuffisant. Sans amÃ©lioration, un avertissement pourra Ãªtre Ã©mis."
                                )
                                break

            _asyncio.run_coroutine_threadsafe(do_ping(), bot.loop)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @web_app.route('/api/formation', methods=['POST'])
    def api_formation():
        try:
            data = request.get_json()
            key = data.get('key', '')
            fname = data.get('formation', '')
            grade = data.get('grade', '')
            discord_id = data.get('discord_id', '')
            roles = data.get('roles', [])  # Array of role IDs
            action = data.get('action', 'add')  # 'add' ou 'remove'

                # Sauvegarder dans formations.json
            formations = robust_load_json(FORMATIONS_FILE, {})
            if action == 'add':
                if key not in formations:
                    formations[key] = []
                if fname not in formations[key]:
                    formations[key].append(fname)
            else:
                if key in formations:
                    formations[key] = [f for f in formations[key] if f != fname]
            atomic_write_json(FORMATIONS_FILE, formations)

            async def do_formation():
                FORMATION_LOG_CHANNEL = 991076525904367616
                for guild in bot.guilds:
                    member = None
                    if discord_id:
                        try:
                            member = guild.get_member(int(discord_id))
                        except:
                            pass
                    if not member:
                        for m in guild.members:
                            if m.bot:
                                continue
                            if normalize_employee_key(get_clean_name(m)) == key:
                                member = m
                                break

                        # Appliquer les rÃ´les s'ils existent
                    if roles and member:
                        try:
                            for role_id in roles:
                                role = guild.get_role(int(role_id))
                                if role:
                                    if action == 'add':
                                        if role not in member.roles:
                                            await member.add_roles(role)
                                    else:
                                        if role in member.roles:
                                            await member.remove_roles(role)
                        except Exception as e:
                            print(f'Erreur rÃ´le formation {role_id}: {e}')

                        # Log dans le channel de formations
                    log_ch = guild.get_channel(FORMATION_LOG_CHANNEL)
                    if log_ch and member:
                        clean = get_clean_name(member)
                        if action == 'add':
                            msg = f'â†’ formation {fname.lower()} [{grade}] {clean}'
                            try:
                                await log_ch.send(msg)
                            except Exception as e:
                                print(f'Erreur log formation: {e}')
                        else:
                                # Supprimer les messages concernant cette formation
                            try:
                                search_pattern = f'formation {fname.lower()} [{grade}] {clean}'
                                async for message in log_ch.history(limit=100):
                                    if search_pattern in message.content.lower():
                                        await message.delete()
                                        break
                            except Exception as e:
                                print(f'Erreur suppression message formation: {e}')
                    return True
                return False

            future = _asyncio.run_coroutine_threadsafe(do_formation(), bot.loop)
            future.result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/convocation', methods=['POST'])
    def api_convocation():
        try:
            data = request.get_json()
            discord_id = data.get('discord_id', '')
            nom = data.get('nom', 'EmployÃ©')
            heure = data.get('heure', '14h00')

            async def do_convocation():
                for guild in bot.guilds:
                    try:
                        user_id = int(discord_id)
                        member = guild.get_member(user_id)
                        if member:
                                # Envoyer un DM
                            try:
                                await member.send(f"ðŸ“ž **Convocation**\n\nTu dois te prÃ©senter Ã  l'accueil Ã  **{heure}**.")
                            except:
                                pass
                            return True
                    except:
                        continue
                return False

            future = _asyncio.run_coroutine_threadsafe(do_convocation(), bot.loop)
            future.result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/dismiss_reminder', methods=['POST'])
    def api_dismiss_reminder():
        try:
            data = request.get_json()
            rid = str(data.get('id', ''))
            reminders = robust_load_json(VIRER_REMINDERS_FILE, [])
            reminders = [r for r in reminders if str(r.get('id', '')) != rid]
            atomic_write_json(VIRER_REMINDERS_FILE, reminders)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/mettre_en_garde', methods=['POST'])
    def api_mettre_en_garde():
        try:
            data = request.get_json()
            key = data.get('key', '')
            message = data.get('message', '').strip()
            if not message:
                return jsonify({'ok': False, 'error': 'Message vide'})

            async def do_garde():
                for guild in bot.guilds:
                    member = None
                    for m in guild.members:
                        if m.bot:
                            continue
                        if normalize_employee_key(get_clean_name(m)) == key:
                            member = m
                            break
                    for ch in guild.text_channels:
                        if ch.name and len(ch.name) > 1 and ch.name[0] in ['\U0001f534', '\U0001f7e0', '\U0001f7e2']:
                            if get_channel_employee_key(ch) == key:
                                embed = discord.Embed(
                                    title="âš ï¸ Mise en garde â€” Los Santos EMS",
                                    color=discord.Color.from_rgb(255, 159, 10),
                                    description=(
                                        f"{message}\n\n"
                                        f"*Ce message est une mise en garde informelle de la direction.*"
                                    )
                                )
                                embed.set_footer(text="ðŸš‘ Direction â€” Los Santos EMS")
                                mention = member.mention if member else ''
                                await ch.send(content=mention, embed=embed)
                                return True
                return False

            future = _asyncio.run_coroutine_threadsafe(do_garde(), bot.loop)
            result = future.result(timeout=10)
            if result:
                return jsonify({'ok': True})
            else:
                return jsonify({'ok': False, 'error': 'Channel introuvable'})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/convoquer', methods=['POST'])
    def api_convoquer():
        try:
            
            data = request.get_json()
            key = data.get('key', '')
            heure = data.get('heure', '')
            message_extra = data.get('message', '').strip()

            async def do_convoquer():
                for guild in bot.guilds:
                        # Trouver le membre correspondant
                    member = None
                    for m in guild.members:
                        if m.bot:
                            continue
                        if normalize_employee_key(get_clean_name(m)) == key:
                            member = m
                            break
                        # Trouver le channel personnel
                    clean_norm = key
                    for ch in guild.text_channels:
                        if ch.name and len(ch.name) > 1 and ch.name[0] in ['\U0001f534', '\U0001f7e0', '\U0001f7e2']:
                            if get_channel_employee_key(ch) == clean_norm:
                                embed = discord.Embed(
                                    title="ðŸ“‹ Convocation â€” Los Santos EMS",
                                    color=discord.Color.from_rgb(255, 59, 48),
                                    description=(
                                        f"Vous Ãªtes convoquÃ©(e) Ã  vous prÃ©senter Ã  "
                                        f"**l'HÃ´pital de Los Santos â€” Accueil** Ã  **{heure}**."
                                        + (f"\n\n**Motif :** {message_extra}" if message_extra else "")
                                        + "\n\n*Merci d'Ãªtre prÃ©sent(e) Ã  l'heure indiquÃ©e.*"
                                    )
                                )
                                embed.set_footer(text="ðŸš‘ Direction â€” Los Santos EMS")
                                mention = member.mention if member else ''
                                await ch.send(content=mention, embed=embed)
                                return True
                return False

            future = _asyncio.run_coroutine_threadsafe(do_convoquer(), bot.loop)
            result = future.result(timeout=10)
            if result:
                return jsonify({'ok': True})
            else:
                return jsonify({'ok': False, 'error': 'Channel introuvable pour cet employÃ©'})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/absence_add', methods=['POST'])
    def api_absence_add():
        try:
            data = request.get_json()
            key = data.get('key', '')
            discord_id = data.get('discord_id', '')
            date_debut = data.get('date_debut', '')  # format YYYY-MM-DD
            date_retour = data.get('date_retour', '') or None
            raison = data.get('raison', 'â€”')
            if not key or not date_debut:
                return jsonify({'ok': False, 'error': 'EmployÃ© ou date manquant'}), 400

            absences = load_absences()
            if key not in absences:
                absences[key] = {}
            record = {'date_debut': date_debut, 'raison': raison}
            if date_retour:
                record['date_retour'] = date_retour
            absences[key][date_debut] = record
            save_absences(absences)

            async def do_log():
                for guild in bot.guilds:
                    member = None
                    if discord_id:
                        try:
                            member = guild.get_member(int(discord_id))
                        except:
                            pass
                    if not member:
                        for m in guild.members:
                            if not m.bot and normalize_employee_key(get_clean_name(m)) == key:
                                member = m
                                break
                    log_channel = bot.get_channel(ABSENCE_LOG_CHANNEL)
                    if log_channel:
                        date_display = date_debut
                        if date_retour:
                            date_display += f" â†’ {date_retour}"
                        mention = member.mention if member else key.replace('-', ' ').title()
                        await log_channel.send(f"ðŸ“‹ **Absence dÃ©clarÃ©e (via dashboard)**\n{mention} â€” **{date_display}** â€” {raison}")
                    return

            future = _asyncio.run_coroutine_threadsafe(do_log(), bot.loop)
            future.result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/avert_add', methods=['POST'])
    def api_avert_add():
        try:
            data = request.get_json()
            key = data.get('key', '')
            discord_id = data.get('discord_id', '')
            raison = data.get('raison', '').strip()
            if not discord_id or not raison:
                return jsonify({'ok': False, 'error': 'EmployÃ© ou raison manquant'}), 400

            avert_data = load_avertissements()
            now = datetime.now(timezone.utc)
            existing = avert_data.get(discord_id, [])
            existing = [av for av in existing if (now - datetime.fromisoformat(av["date"])).days < 30]
            existing.append({
                "raison": raison,
                "date": now.isoformat(),
                "par": "Direction (dashboard)"
            })
            avert_data[discord_id] = existing
            save_avertissements(avert_data)
            count = len(existing)

            async def do_notify():
                for guild in bot.guilds:
                    member = None
                    try:
                        member = guild.get_member(int(discord_id))
                    except:
                        pass
                    if not member:
                        continue
                    clean = get_clean_name(member)
                    try:
                        dm_embed = discord.Embed(
                            title="âš ï¸ Avertissement â€” Los Santos EMS",
                            color=discord.Color.red() if count >= 3 else discord.Color.orange() if count == 2 else discord.Color.yellow(),
                            description=(
                                f"Vous avez reÃ§u un **avertissement officiel** de la direction des EMS.\n\n"
                                f"**Motif :** {raison}\n"
                                f"**Avertissements actifs :** {count}/3\n\n"
                                f"{'âš ï¸ Attention : vous avez atteint la limite. Des mesures disciplinaires pourront Ãªtre prises.' if count >= 3 else 'Tout avertissement supplÃ©mentaire pourra entraÃ®ner des sanctions.'}\n\n"
                                f"*Les avertissements sont automatiquement annulÃ©s aprÃ¨s 30 jours.*"
                            )
                        )
                        dm_embed.set_footer(text="ðŸš‘ Los Santos Fire & Medical Department")
                        await member.send(embed=dm_embed)
                    except:
                        pass

                    if count >= 3:
                        role_ping = guild.get_role(AVERT_ROLE_PING_ID)
                        ping_str = role_ping.mention if role_ping else ""
                        avert_channel = guild.get_channel(AVERT_CHANNEL_ID)
                        if avert_channel:
                            alert_embed = discord.Embed(
                                title="ðŸš¨ Alerte â€” 3Ã¨me Avertissement",
                                color=discord.Color.red(),
                                description=(
                                    f"**{clean}** vient de recevoir son **{count}Ã¨me avertissement**.\n\n"
                                    f"**Motif :** {raison}\n"
                                    f"**DÃ©livrÃ© par :** Direction (dashboard)\n\n"
                                    f"Une action disciplinaire est recommandÃ©e."
                                )
                            )
                            alert_embed.set_footer(text="ðŸš‘ EMS System")
                            await avert_channel.send(content=ping_str, embed=alert_embed, allowed_mentions=discord.AllowedMentions(roles=True))
                    try:
                        await update_avert_board(guild)
                    except:
                        pass
                    return

            future = _asyncio.run_coroutine_threadsafe(do_notify(), bot.loop)
            future.result(timeout=10)
            return jsonify({'ok': True, 'count': count})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/avert_remove', methods=['POST'])
    def api_avert_remove():
        try:
            data = request.get_json()
            discord_id = data.get('discord_id', '')
            if not discord_id:
                return jsonify({'ok': False, 'error': 'discord_id manquant'}), 400

            avert_data = load_avertissements()
            now = datetime.now(timezone.utc)
            existing = avert_data.get(discord_id, [])
            existing = [av for av in existing if (now - datetime.fromisoformat(av["date"])).days < 30]
            if not existing:
                return jsonify({'ok': False, 'error': 'Aucun avertissement actif'})
            existing.pop(0)
            avert_data[discord_id] = existing
            save_avertissements(avert_data)

            async def do_board():
                for guild in bot.guilds:
                    try:
                        await update_avert_board(guild)
                    except:
                        pass
                    return

            future = _asyncio.run_coroutine_threadsafe(do_board(), bot.loop)
            future.result(timeout=10)
            return jsonify({'ok': True, 'count': len(existing)})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/send_message', methods=['POST'])
    def api_send_message():
        try:
            data = request.get_json()
            key = data.get('key', '')
            discord_id = data.get('discord_id', '')
            message = data.get('message', '').strip()
            if not message:
                return jsonify({'ok': False, 'error': 'Message vide'}), 400

            async def do_send():
                for guild in bot.guilds:
                    member = None
                    if discord_id:
                        try:
                            member = guild.get_member(int(discord_id))
                        except:
                            pass
                    if not member:
                        for m in guild.members:
                            if not m.bot and normalize_employee_key(get_clean_name(m)) == key:
                                member = m
                                break
                    if not member:
                        continue
                    clean_norm = normalize_employee_key(get_clean_name(member))
                    for ch in guild.text_channels:
                        if ch.name and len(ch.name) > 1 and ch.name[0] in ['\U0001f534', '\U0001f7e0', '\U0001f7e2']:
                            if get_channel_employee_key(ch) == clean_norm:
                                embed = discord.Embed(
                                    title="âœ‰ï¸ Message de la direction â€” Los Santos EMS",
                                    color=discord.Color.blue(),
                                    description=message
                                )
                                embed.set_footer(text="ðŸš‘ Direction â€” Los Santos EMS")
                                await ch.send(content=member.mention, embed=embed)
                                return True
                return False

            future = _asyncio.run_coroutine_threadsafe(do_send(), bot.loop)
            result = future.result(timeout=10)
            if result:
                return jsonify({'ok': True})
            else:
                return jsonify({'ok': False, 'error': 'Channel introuvable pour cet employÃ©'})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/virer_employee', methods=['POST'])
    def api_virer_employee():
        try:
            data = request.get_json()
            key = data.get('key', '')
            discord_id = data.get('discord_id', '')
            raison_type = data.get('raison_type', 'autre')  # inactivite | erreur_pro | autre
            raison_custom = data.get('raison_custom', '').strip()

            if not discord_id and not key:
                return jsonify({'ok': False, 'error': 'EmployÃ© introuvable'}), 400

            if raison_type == 'autre' and not raison_custom:
                return jsonify({'ok': False, 'error': 'Raison personnalisÃ©e manquante'}), 400

            async def do_virer():
                for guild in bot.guilds:
                    member = None
                    if discord_id:
                        try:
                            member = guild.get_member(int(discord_id))
                        except:
                            pass
                    if not member:
                        for m in guild.members:
                            if not m.bot and normalize_employee_key(get_clean_name(m)) == key:
                                member = m
                                break
                    if not member:
                        return False, 'Membre Discord introuvable'

                    clean_name = get_clean_name(member)

                    # Messages DM
                    if raison_type == 'inactivite':
                        raison_dm = (
                            f"Cher **{clean_name}**,\n\n"
                            f"Nous avons le regret de vous informer que votre contrat au sein de l'HÃ´pital de Los Santos a Ã©tÃ© rÃ©siliÃ© en raison d'une **inactivitÃ© prolongÃ©e** et non justifiÃ©e.\n\n"
                            f"MalgrÃ© les attentes fixÃ©es en termes de prÃ©sence et d'investissement, votre absence rÃ©pÃ©tÃ©e n'est pas compatible avec les exigences de notre service.\n\n"
                            f"Nous vous remercions pour votre passage parmi nous et vous souhaitons bonne continuation.\n\n"
                            f"Cordialement,\n**La Direction des EMS.**"
                        )
                        raison_label = "â³ InactivitÃ© prolongÃ©e"
                    elif raison_type == 'erreur_pro':
                        raison_dm = (
                            f"Cher **{clean_name}**,\n\n"
                            f"Nous avons le regret de vous informer que votre contrat au sein de l'HÃ´pital de Los Santos a Ã©tÃ© rÃ©siliÃ© suite Ã  une **erreur professionnelle grave**.\n\n"
                            f"Cette dÃ©cision fait suite Ã  une analyse approfondie des faits constatÃ©s, jugÃ©s incompatibles avec les valeurs, les protocoles et les standards de notre service mÃ©dical.\n\n"
                            f"Nous vous remercions pour votre engagement passÃ© et vous souhaitons bonne continuation dans vos projets.\n\n"
                            f"Cordialement,\n**La Direction des EMS.**"
                        )
                        raison_label = "âš ï¸ Erreur professionnelle"
                    else:
                        raison_dm = (
                            f"Cher **{clean_name}**,\n\n"
                            f"Nous avons le regret de vous informer que votre contrat au sein de l'HÃ´pital de Los Santos a Ã©tÃ© rÃ©siliÃ©.\n\n"
                            f"**Motif :** {raison_custom}\n\n"
                            f"Nous vous remercions pour votre passage parmi nous et vous souhaitons bonne continuation.\n\n"
                            f"Cordialement,\n**La Direction des EMS.**"
                        )
                        raison_label = f"ðŸ“ {raison_custom}"

                    # 1. RÃ´les
                    role_target_id = 838102445095256066
                    roles_to_remove = [r for r in member.roles if r.id in EMS_ROLE_IDS_TO_REMOVE]
                    role_to_add = guild.get_role(role_target_id)
                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove)
                    if role_to_add:
                        await member.add_roles(role_to_add)

                    # 2. Reset pseudo
                    try:
                        await member.edit(nick=None)
                    except:
                        pass

                    # 3. DM
                    try:
                        await member.send(raison_dm)
                    except:
                        pass

                    # 4. Supprimer channel
                    clean_name_norm = normalize_employee_key(clean_name)
                    channel_deleted = False
                    for ch in guild.text_channels:
                        if ch.name and len(ch.name) > 1 and ch.name[0] in ['\U0001f534', '\U0001f7e0', '\U0001f7e2']:
                            if get_channel_employee_key(ch) == clean_name_norm:
                                try:
                                    await ch.delete()
                                    channel_deleted = True
                                except Exception as e:
                                    print(f"Erreur suppression channel: {e}")
                                break

                    # 5. Blacklist CV
                    try:
                        bl = load_blacklist_cv()
                        bl[str(member.id)] = {
                            "date": datetime.utcnow().isoformat(),
                            "raison": f"Licenciement â€” {raison_label}",
                            "blacklisted_by": "dashboard",
                        }
                        save_blacklist_cv(bl)
                    except Exception as _bl_err:
                        print(f"Erreur blacklist CV: {_bl_err}")

                    # 6. Rappel dashboard virer
                    grade_match = _re.search(r'\[(\w+)\]', member.display_name)
                    emp_grade = grade_match.group(1) if grade_match else ''
                    try:
                        vr_data = robust_load_json(VIRER_REMINDERS_FILE, [])
                        vr_data.append({
                            'id': str(int(time.time() * 1000)),
                            'name': clean_name,
                            'grade': emp_grade,
                            'date': now_paris().strftime('%d/%m %H:%M'),
                        })
                        atomic_write_json(VIRER_REMINDERS_FILE, vr_data)
                    except:
                        pass

                    # 7. Mise Ã  jour board matricules
                    try:
                        await update_matricule_board(guild)
                    except:
                        pass

                    return True, f"{raison_label} | channel {'supprimÃ©' if channel_deleted else 'non trouvÃ©'}"

                return False, 'Serveur Discord introuvable'

            future = _asyncio.run_coroutine_threadsafe(do_virer(), bot.loop)
            ok, msg = future.result(timeout=20)
            if ok:
                return jsonify({'ok': True, 'msg': msg})
            else:
                return jsonify({'ok': False, 'error': msg})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/cv_action', methods=['POST'])
    def api_cv_action():
        """Accepter ou refuser un CV depuis le dashboard."""
        try:
            data = request.get_json()
            discord_id = data.get('discord_id', '')
            action = data.get('action', '')  # 'accept' | 'refuse' | 'blacklist_remove'
            raison = data.get('raison', '').strip()

            if not discord_id or action not in ('accept', 'refuse', 'blacklist_remove'):
                return jsonify({'ok': False, 'error': 'ParamÃ¨tres invalides'}), 400

            if action == 'blacklist_remove':
                bl = load_blacklist_cv()
                if discord_id in bl:
                    del bl[discord_id]
                    save_blacklist_cv(bl)
                return jsonify({'ok': True})

            async def do_cv_action():
                for guild in bot.guilds:
                    member = None
                    try:
                        member = guild.get_member(int(discord_id))
                    except:
                        pass
                    if not member:
                        return False, 'Membre Discord introuvable'

                    if action == 'accept':
                        try:
                            role = guild.get_role(ROLE_PENDING_ID)
                            if role:
                                await member.add_roles(role)
                        except:
                            pass
                        try:
                            embed_accept = discord.Embed(
                                title="ðŸŽ‰ FÃ‰LICITATIONS !",
                                description=(
                                    "âœ… Votre candidature a Ã©tÃ© **ACCEPTÃ‰E** !\n\n"
                                    "Bienvenue dans la famille des **EMS** ! ðŸš‘\n\n"
                                    "ðŸ“ **Ã‰tape suivante :**\n"
                                    "Merci de mettre vos disponibilitÃ©s dans le channel <#1482838723656941829>.\n\n"
                                    "Nous nous chargerons de faire un recrutement.\n\n"
                                    "Cordialement,\n**La Direction des EMS** ðŸš‘"
                                ),
                                color=discord.Color.green()
                            )
                            embed_accept.set_footer(text="ðŸš‘ EMS System | Direction")
                            await member.send(embed=embed_accept)
                        except:
                            pass
                        cv_track_update(discord_id, 'accepted')
                        return True, 'CV acceptÃ©'

                    elif action == 'refuse':
                        raison_finale = raison or 'Candidature non retenue'
                        try:
                            await member.send(
                                f"âŒ **Candidature RefusÃ©e**\n\n"
                                f"Nous regrettons de vous informer que votre candidature n'a pas Ã©tÃ© retenue.\n\n"
                                f"**Motif :** {raison_finale}\n\n"
                                f"Nous vous encourageons Ã  postuler Ã  nouveau dans le futur.\n\n"
                                f"Cordialement,\n**La Direction des EMS** ðŸš‘"
                            )
                        except:
                            pass
                        # Blacklist CV 1 semaine
                        bl = load_blacklist_cv()
                        bl[discord_id] = {
                            "date": datetime.utcnow().isoformat(),
                            "raison": raison_finale,
                            "blacklisted_by": "dashboard",
                        }
                        save_blacklist_cv(bl)
                        cv_track_update(discord_id, 'refused', raison_finale)
                        return True, 'CV refusÃ© + blacklist 1 semaine'

                return False, 'Serveur Discord introuvable'

            future = _asyncio.run_coroutine_threadsafe(do_cv_action(), bot.loop)
            ok, msg = future.result(timeout=10)
            if ok:
                return jsonify({'ok': True, 'msg': msg})
            else:
                return jsonify({'ok': False, 'error': msg})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/sync_cv', methods=['POST'])
    def api_sync_cv():
        """Lit le channel CV Discord et remplit cv_tracking.json rÃ©troactivement."""
        try:

            async def do_sync():
                results = {'added': 0, 'skipped': 0, 'errors': 0}
                cv_channel = bot.get_channel(1539697901540745317)
                if not cv_channel:
                    return False, 'Channel CV introuvable (ID 1539697901540745317)', results

                data = load_cv_tracking()
                # Lire les 300 derniers messages du channel CV
                async for msg in cv_channel.history(limit=300, oldest_first=False):
                    try:
                        for emb in msg.embeds:
                            footer = emb.footer.text if emb.footer else ''
                            # Extraire l'ID depuis "ðŸš‘ EMS System | ID: 123456789"
                            id_match = _re.search(r'ID:\s*(\d+)', footer)
                            if not id_match:
                                continue
                            uid = id_match.group(1)
                            if uid in data:
                                results['skipped'] += 1
                                continue
                            # Extraire le nom depuis le titre "ðŸ“‹ CV - Nom PrÃ©nom"
                            title = emb.title or ''
                            nom_match = _re.match(r'ðŸ“‹ CV\s*[-â€“]\s*(.+)', title)
                            nom = nom_match.group(1).strip() if nom_match else f'Candidat {uid}'
                            # DÃ©terminer le statut Ã  partir des boutons dÃ©sactivÃ©s si possible
                            statut = 'pending'
                            for comp in (msg.components or []):
                                for btn in getattr(comp, 'children', []):
                                    lbl = getattr(btn, 'label', '')
                                    if 'Accepter' in lbl and getattr(btn, 'disabled', False):
                                        statut = 'accepted'
                                    elif 'Refuser' in lbl and getattr(btn, 'disabled', False):
                                        if statut != 'accepted':
                                            statut = 'refused'
                            # Discord user pour le tag
                            discord_tag = f'ID:{uid}'
                            try:
                                user = await bot.fetch_user(int(uid))
                                discord_tag = str(user)
                                nom = user.display_name or nom
                            except:
                                pass
                            data[uid] = {
                                'nom': nom,
                                'discord_tag': discord_tag,
                                'date_depot': msg.created_at.isoformat(),
                                'statut': statut,
                                'raison_refus': None,
                                'imported': True,
                            }
                            results['added'] += 1
                    except Exception as _e:
                        results['errors'] += 1
                        continue

                save_cv_tracking(data)
                return True, f"Import terminÃ© : {results['added']} ajoutÃ©s, {results['skipped']} dÃ©jÃ  prÃ©sents, {results['errors']} erreurs", results

            future = _asyncio.run_coroutine_threadsafe(do_sync(), bot.loop)
            ok, msg, results = future.result(timeout=60)
            if ok:
                return jsonify({'ok': True, 'msg': msg, 'results': results})
            else:
                return jsonify({'ok': False, 'error': msg})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/bot_health', methods=['GET'])
    def api_bot_health():
        """Etat de sante du bot : uptime, reconnexions, taille des fichiers de donnees."""
        try:
            now = now_paris()
            uptime_seconds = (now - BOT_START_TIME).total_seconds() if BOT_START_TIME else 0
            recent_reconnects = [t for t in reconnect_timestamps if (now - t).total_seconds() < 3600]

            data_files = [
                ('stats.json', STATS_FILE),
                ('services.json', SERVICE_FILE),
                ('absences.json', ABSENCE_FILE),
                ('avertissements.json', AVERT_FILE),
                ('daily_reas.json', DAILY_REAS_FILE),
                ('evening_reas.json', EVENING_REAS_FILE),
                ('week_snapshot.json', WEEK_SNAPSHOT_FILE),
                ('week_history.json', WEEK_HISTORY_FILE),
                ('formations.json', FORMATIONS_FILE),
                ('embauche.json', EMBAUCHE_FILE),
                ('cv_tracking.json', CV_TRACKING_FILE),
                ('promo_history.json', PROMO_HISTORY_FILE),
                ('patients.json', PATIENTS_FILE),
            ]
            files_report = []
            for label, path in data_files:
                try:
                    if os.path.exists(path):
                        size_bytes = os.path.getsize(path)
                        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
                        files_report.append({
                            'name': label,
                            'exists': True,
                            'size_kb': round(size_bytes / 1024, 2),
                            'last_modified': mtime.isoformat(),
                        })
                    else:
                        files_report.append({'name': label, 'exists': False, 'size_kb': 0, 'last_modified': None})
                except Exception:
                    files_report.append({'name': label, 'exists': False, 'size_kb': 0, 'last_modified': None})

            return jsonify({
                'ok': True,
                'bot_start_time': BOT_START_TIME.isoformat() if BOT_START_TIME else None,
                'uptime_seconds': uptime_seconds,
                'reconnect_count_total': reconnect_count,
                'reconnect_count_last_hour': len(recent_reconnects),
                'guilds_connected': len(bot.guilds),
                'latency_ms': round(bot.latency * 1000, 1) if bot.latency else None,
                'files': files_report,
                'server_time': now.isoformat(),
            })
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/debug_employees', methods=['GET'])
    def api_debug_employees():
        """Diagnostic complet : pourquoi employee_info est vide ou incomplet."""
        try:
            report = {
                'bot_guilds_count': len(bot.guilds),
                'guilds': [],
            }
            EMS_ROLE_GRADES_IDS = {
                895047492784238652: 'EMT',
                838102445095256069: 'STG',
                1528560704511148092: 'PSY',
                1528561040663777310: 'CAD',
                1088116715998687273: 'ADS',
                894311352225656862: 'INF',
                840288242547818507: 'MED',
                838102445095256071: 'CDS',
                1088570974603055195: 'DIR',
                1206320774978474054: 'CPDG',
                917156484335403100: 'RH',
                838102445103775747: 'DRH',
                838102445103775752: 'PDG',
            }
            BASE_EMS_ROLE_ID = 838102445095256068  # rÃ´le que tous les EMS ont

            for guild in bot.guilds:
                members_list = list(guild.members)
                guild_report = {
                    'guild_name': guild.name,
                    'guild_id': guild.id,
                    'total_members_cached': len(members_list),
                    'total_non_bot_members': sum(1 for m in members_list if not m.bot),
                    'chunked': guild.chunked,
                    'member_count_from_discord': guild.member_count,
                    'sample_members': [],
                }
                # Prendre un Ã©chantillon de 15 membres non-bot pour diagnostic dÃ©taillÃ©
                non_bot = [m for m in members_list if not m.bot][:15]
                for m in non_bot:
                    role_ids = [r.id for r in m.roles]
                    match = _re.search(r'\[(\w+)\]\s+(\d{2})\s+(.+)', m.display_name)
                    matched_role_grade = None
                    for rid, g in EMS_ROLE_GRADES_IDS.items():
                        if rid in role_ids:
                            matched_role_grade = g
                            break
                    has_base_ems_role = BASE_EMS_ROLE_ID in role_ids
                    guild_report['sample_members'].append({
                        'display_name': m.display_name,
                        'role_ids': role_ids,
                        'role_names': [r.name for r in m.roles],
                        'matches_format_regex': bool(match),
                        'regex_captured_grade': match.group(1) if match else None,
                        'matched_known_role_id_grade': matched_role_grade,
                        'has_base_ems_role': has_base_ems_role,
                        'would_be_included': bool(match) or matched_role_grade is not None,
                    })
                report['guilds'].append(guild_report)

            return jsonify(report)
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

    @web_app.route('/api/parrainage/remove', methods=['POST'])
    def api_parrainage_remove():
        """Retire l'association parrain/stagiaire, rÃ©voque l'accÃ¨s au channel."""
        try:
            data = request.get_json()
            stagiaire_key = data.get('stagiaire_key', '')
            if not stagiaire_key:
                return jsonify({'ok': False, 'error': 'ClÃ© stagiaire manquante'}), 400

            parrainage = load_parrainage()
            if stagiaire_key not in parrainage:
                return jsonify({'ok': False, 'error': "Ce stagiaire n'a pas de parrain enregistrÃ©"}), 404

            old_parrain_id = parrainage[stagiaire_key].get('parrain_discord_id')
            del parrainage[stagiaire_key]
            save_parrainage(parrainage)

            async def revoke_access():
                for guild in bot.guilds:
                    if old_parrain_id:
                        try:
                            old_parrain_member = guild.get_member(int(old_parrain_id))
                            if old_parrain_member:
                                for ch in guild.text_channels:
                                    if ch.name and len(ch.name) > 1 and ch.name[0] in ['ðŸ”´', 'ðŸŸ ', 'ðŸŸ¢']:
                                        if get_channel_employee_key(ch) == stagiaire_key:
                                            await ch.set_permissions(old_parrain_member, overwrite=None)
                                            break
                        except Exception as e:
                            print(f"Erreur retrait permission parrainage (web): {e}")
                    return

            future = _asyncio.run_coroutine_threadsafe(revoke_access(), bot.loop)
            future.result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/repair_keys', methods=['POST'])
    def api_repair_keys():
        """RÃ©pare les clÃ©s employÃ© cassÃ©es dans tous les fichiers JSON (fusion vers clÃ©s canoniques actuelles)."""
        try:
            data = request.get_json() or {}
            dry_run = data.get('dry_run', True)

            canonical_keys = set()
            for guild in bot.guilds:
                for member in guild.members:
                    if member.bot:
                        continue
                    match = _re.search(r'\[(\w+)\]\s+(\d{2})\s+(.+)', member.display_name)
                    nom = match.group(3).strip() if match else member.display_name
                    k = normalize_employee_key(nom)
                    if k:
                        canonical_keys.add(k)

            KNOWN_EXTRA_PREFIXES = ['pdg-', 'cpdg-', 'cad-', 'psy-', 'stg-', 'dir-', 'cds-', 'med-', 'inf-', 'ads-', 'int-', 'emt-', 'drh-', 'rh-']

            def find_canonical(old_key):
                if old_key in canonical_keys:
                    return old_key
                stripped = old_key
                changed = True
                while changed:
                    changed = False
                    for p in KNOWN_EXTRA_PREFIXES:
                        if stripped.startswith(p) and stripped[len(p):]:
                            stripped = stripped[len(p):]
                            changed = True
                            break
                if stripped in canonical_keys:
                    return stripped
                for ck in canonical_keys:
                    if old_key.endswith(ck) and old_key != ck and len(ck) >= 4:
                        return ck
                return old_key

            results = {}
            total_changes = 0

            stats = robust_load_json(STATS_FILE, {})
            new_stats = {}
            stats_changes = 0
            for old_k, v in stats.items():
                new_k = find_canonical(old_k)
                if new_k != old_k:
                    stats_changes += 1
                new_stats[new_k] = new_stats.get(new_k, 0) + v
            if stats_changes:
                results['stats'] = stats_changes
                total_changes += stats_changes
                if not dry_run:
                    atomic_write_json(STATS_FILE, new_stats)

            absences = robust_load_json(ABSENCE_FILE, {})
            new_abs = {}
            abs_changes = 0
            for old_k, v in absences.items():
                new_k = find_canonical(old_k)
                if new_k != old_k:
                    abs_changes += 1
                new_abs.setdefault(new_k, {}).update(v)
            if abs_changes:
                results['absences'] = abs_changes
                total_changes += abs_changes
                if not dry_run:
                    atomic_write_json(ABSENCE_FILE, new_abs)

            formations = robust_load_json(FORMATIONS_FILE, {})
            new_forms = {}
            forms_changes = 0
            for old_k, v in formations.items():
                new_k = find_canonical(old_k)
                if new_k != old_k:
                    forms_changes += 1
                lst = new_forms.setdefault(new_k, [])
                for item in v:
                    if item not in lst:
                        lst.append(item)
            if forms_changes:
                results['formations'] = forms_changes
                total_changes += forms_changes
                if not dry_run:
                    atomic_write_json(FORMATIONS_FILE, new_forms)

            daily = robust_load_json(DAILY_REAS_FILE, {})
            new_daily = {}
            daily_changes = 0
            for date_k, day_data in daily.items():
                new_day = {}
                for old_k, v in day_data.items():
                    new_k = find_canonical(old_k)
                    if new_k != old_k:
                        daily_changes += 1
                    new_day[new_k] = new_day.get(new_k, 0) + v
                new_daily[date_k] = new_day
            if daily_changes:
                results['daily_reas'] = daily_changes
                total_changes += daily_changes
                if not dry_run:
                    atomic_write_json(DAILY_REAS_FILE, new_daily)

            embauche = robust_load_json(EMBAUCHE_FILE, {})
            new_emb = {}
            emb_changes = 0
            for old_k, v in embauche.items():
                new_k = find_canonical(old_k)
                if new_k != old_k:
                    emb_changes += 1
                new_emb.setdefault(new_k, v)
            if emb_changes:
                results['embauche'] = emb_changes
                total_changes += emb_changes
                if not dry_run:
                    atomic_write_json(EMBAUCHE_FILE, new_emb)

            promos = robust_load_json(PROMO_HISTORY_FILE, {})
            new_promos = {}
            promo_changes = 0
            for old_k, v in promos.items():
                new_k = find_canonical(old_k)
                if new_k != old_k:
                    promo_changes += 1
                new_promos.setdefault(new_k, []).extend(v)
            if promo_changes:
                results['promo_history'] = promo_changes
                total_changes += promo_changes
                if not dry_run:
                    atomic_write_json(PROMO_HISTORY_FILE, new_promos)

            return jsonify({'ok': True, 'dry_run': dry_run, 'total_changes': total_changes, 'details': results})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/update-pwds', methods=['POST'])
    def api_update_pwds():
        try:
            data = request.get_json()
            pwds = data.get('pwds', [])
            if not isinstance(pwds, list):
                return jsonify({'ok': False, 'error': 'pwds doit Ãªtre une liste'}), 400
                # Stocker les mots de passe dans le fichier de donnÃ©es
            pwds_file = os.path.join(DATA_DIR, 'api_pwds.json')
            atomic_write_json(pwds_file, {'pwds': pwds, 'updated': now_paris().isoformat()})
            return jsonify({'ok': True, 'count': len(pwds)})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/reset-all', methods=['POST'])
    def api_reset_all():
        try:
                # RÃ©initialiser tous les fichiers de donnÃ©es
            atomic_write_json(STATS_FILE, {})
            atomic_write_json(TAXI_STATS_FILE, {})
            atomic_write_json(SERVICE_FILE, {})
            atomic_write_json(BONUSES_WEEK_FILE, {})
            atomic_write_json(AVERT_FILE_PATH, {})
            atomic_write_json(DISPATCH_HISTORY_FILE, [])
            atomic_write_json(FORMATIONS_FILE, {})
            atomic_write_json(SERVICE_MSG_FILE, {})
                
            return jsonify({'ok': True, 'message': 'Toutes les donnÃ©es ont Ã©tÃ© rÃ©initialisÃ©es'})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/reunion_announce', methods=['POST'])
    def api_reunion_announce():
        try:
            data = request.get_json()
            jour = data.get('jour', '').strip()
            heure = data.get('heure', '').strip()
            
            if not jour or not heure:
                return jsonify({'ok': False, 'error': 'Jour et heure requis'}), 400

            # Sauvegarder le message simple sur le site
            REUNION_FILE = os.path.join(DATA_DIR, 'reunion_announce.json')
            reunion_data = {
                'jour': jour,
                'heure': heure,
                'timestamp': datetime.now(PARIS_TZ).isoformat(),
                'message': f"RÃ©union des EMS ce {jour} Ã  {heure}"
            }
            atomic_write_json(REUNION_FILE, reunion_data)

            async def send_announce():
                REUNION_CHANNEL = 1482843520254611653
                REUNION_ROLE = 838102445095256068
                ABSENCE_CHANNEL = 1523355492368515222
                
                for guild in bot.guilds:
                    ch = guild.get_channel(REUNION_CHANNEL)
                    if not ch:
                        continue
                    
                    role = guild.get_role(REUNION_ROLE)
                    role_mention = role.mention if role else f"<@&{REUNION_ROLE}>"
                    
                    # Message SIMPLE et DIRECT
                    message = f"""{role_mention}

Bonjour Ã  tous

La rÃ©union des EMS se tiendra ce {jour} Ã  {heure} au rooftop

La fin de semaine se fera Ã  20h30, les payes suivront Ã©galement la rÃ©union

Je vous demanderai de prendre votre fin de service dÃ¨s 20h45 !

PS : la rÃ©union est importante et obligatoire pour tous. Donc si vous ne pouvez pas Ãªtre lÃ  merci de mettre une absence sur le canal <#{ABSENCE_CHANNEL}> , sous peine d'avertissements

Merci de TOUS cocher ce message par âœ… ou âŒ pour nous faire savoir si vous serez prÃ©sent ou non

Bien Ã  vous tous,
La direction des EMS"""
                    
                    msg = await ch.send(message)
                    await msg.add_reaction('âœ…')
                    await msg.add_reaction('âŒ')
                    return True
                return False

            future = _asyncio.run_coroutine_threadsafe(send_announce(), bot.loop)
            result = future.result(timeout=10)
            
            if result:
                return jsonify({'ok': True, 'message': 'Annonce envoyÃ©e'})
            else:
                return jsonify({'ok': False, 'error': 'Channel non trouvÃ©'}), 500
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @web_app.route('/api/debrief_send', methods=['POST'])
    def api_debrief_send():
        """Envoie le dÃ©brief hebdomadaire (remarques/payes/promotions par employÃ©) dans le channel rÃ©union."""
        try:
            data = request.get_json()
            entries = data.get('entries', [])  # [{name, grade, remark, pay, rankup}]
            all_stats = data.get('allStats', [])  # [{name, reas}] pour le graphique, tout le monde
            entries = [e for e in entries if (e.get('remark') or '').strip() or (e.get('pay') or '').strip() or (e.get('rankup') or '').strip()]

            if not entries:
                return jsonify({'ok': False, 'error': "Aucune remarque, paye ou promotion saisie"}), 400

            chart_buf = generate_debrief_chart(all_stats, title=f"DÃ©brief de la semaine")

            async def send_debrief():
                DEBRIEF_CHANNEL = 1482843520254611653
                DEBRIEF_ROLE = 838102445095256068

                for guild in bot.guilds:
                    ch = guild.get_channel(DEBRIEF_CHANNEL)
                    if not ch:
                        continue
                    role = guild.get_role(DEBRIEF_ROLE)
                    role_mention = role.mention if role else f"<@&{DEBRIEF_ROLE}>"

                    date_str = now_paris().strftime('%d/%m/%Y')
                    lines = [f"ðŸ“‹ **DÃ©brief de la semaine â€” Los Santos EMS** ({date_str})", ""]
                    for e in entries:
                        name = e.get('name', 'EmployÃ©')
                        grade = e.get('grade', '')
                        remark = (e.get('remark') or '').strip()
                        pay = (e.get('pay') or '').strip()
                        rankup = (e.get('rankup') or '').strip()

                        header = f"**{name}**" + (f" [{grade}]" if grade else "")
                        lines.append(header)
                        if remark:
                            lines.append(f"ðŸ“ {remark}")
                        if pay:
                            lines.append(f"ðŸ’° Paye : **{pay}**")
                        if rankup:
                            lines.append(f"ðŸ“ˆ Promotion : **{rankup}**")
                        lines.append("")  # ligne vide entre chaque employÃ©

                    # DÃ©couper en messages de 2000 caractÃ¨res max (limite Discord)
                    # Le ping du rÃ´le est rÃ©servÃ© (comptÃ© Ã  part) pour Ãªtre ajoutÃ© sur CHAQUE message
                    ping_prefix = f"{role_mention}\n\n"
                    max_body_len = 1900 - len(ping_prefix)
                    full_text = "\n".join(lines)
                    messages_to_send = []
                    current_chunk = ""
                    for line in full_text.split("\n"):
                        if len(current_chunk) + len(line) + 1 > max_body_len:
                            messages_to_send.append(current_chunk)
                            current_chunk = ""
                        current_chunk += line + "\n"
                    if current_chunk.strip():
                        messages_to_send.append(current_chunk)

                    for msg_text in messages_to_send:
                        full_msg = ping_prefix + msg_text
                        await ch.send(content=full_msg, allowed_mentions=discord.AllowedMentions(roles=True))
                        await asyncio.sleep(0.5)

                    # Image du graphique envoyÃ©e en tout dernier
                    if chart_buf:
                        chart_buf.seek(0)
                        file = discord.File(chart_buf, filename="debrief_chart.png")
                        await ch.send(file=file)

                    return True
                return False

            future = _asyncio.run_coroutine_threadsafe(send_debrief(), bot.loop)
            result = future.result(timeout=20)

            if result:
                return jsonify({'ok': True, 'count': len(entries)})
            else:
                return jsonify({'ok': False, 'error': 'Channel non trouvÃ©'}), 500
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500


    # ============ ROUTES DE TEST - GESTION DES LOGS ============

    # ============ ROUTES /test ============
    _wt_logs   = _TEST_LOGS_FILE
    _wt_errors = _TEST_ERRORS_FILE
    _wt_rea    = _TEST_REA_FILE
    _wt_map    = _TEST_MAP_FILE
    _wt_meta   = _TEST_META_FILE

    load_json = _test_read
    save_json = _test_write

    @web_app.route('/test')
    def test_logs_page():
        return render_template('test_logs.html')

    @web_app.route('/api/test/logs', methods=['GET', 'DELETE'])
    def api_test_logs():
        if request.method == 'GET':
            logs = load_json(_wt_logs, [])
            log_type = request.args.get('type')
            if log_type:
                logs = [l for l in logs if l.get('type') == log_type]
            return jsonify({'logs': logs, 'total': len(logs)})
        log_id = request.args.get('id')
        if not log_id:
            return jsonify({'error': 'ID requis'}), 400
        logs = load_json(_wt_logs, [])
        logs = [l for l in logs if str(l.get('id')) != str(log_id)]
        save_json(_wt_logs, logs)
        return jsonify({'status': 'success'})

    @web_app.route('/api/test/errors', methods=['GET', 'DELETE'])
    def api_test_errors():
        if request.method == 'GET':
            errors = load_json(_wt_errors, [])
            return jsonify({'errors': errors, 'total': len(errors)})
        save_json(_wt_errors, [])
        return jsonify({'status': 'success'})

    @web_app.route('/api/test/license-map')
    def api_test_license_map():
        return jsonify({'map': load_json(_wt_map, {})})

    @web_app.route('/api/test/rea', methods=['GET'])
    def api_test_rea_list():
        return jsonify({'rea': load_json(_wt_rea, {})})

    @web_app.route('/api/test/rea/add', methods=['POST'])
    def api_test_rea_add():
        data = request.get_json(silent=True) or {}
        nom = (data.get('nom') or data.get('joueur') or '').strip()
        license_key = (data.get('license') or '').strip()
        if not nom and not license_key:
            return jsonify({'error': 'Nom ou license requis'}), 400
        amount = max(1, int(data.get('amount', 1)))
        key = license_key or nom.lower()
        rea_data = load_json(_wt_rea, {})
        if key not in rea_data:
            rea_data[key] = {'nom': nom, 'license': license_key, 'reas': 0, 'history': []}
        if nom: rea_data[key]['nom'] = nom
        if license_key: rea_data[key]['license'] = license_key
        rea_data[key]['reas'] += amount
        rea_data[key]['history'].insert(0, {'action': 'add', 'amount': amount, 'note': data.get('note', ''), 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        save_json(_wt_rea, rea_data)
        return jsonify({'status': 'success', 'reas': rea_data[key]['reas']})

    @web_app.route('/api/test/rea/remove', methods=['POST'])
    def api_test_rea_remove():
        data = request.get_json(silent=True) or {}
        key = (data.get('license') or data.get('joueur') or data.get('nom') or '').strip()
        if not key:
            return jsonify({'error': 'License ou nom requis'}), 400
        amount = max(1, int(data.get('amount', 1)))
        rea_data = load_json(_wt_rea, {})
        # Chercher par license d'abord, puis par nom
        if key not in rea_data:
            key = next((k for k, v in rea_data.items() if v.get('nom','').lower() == key.lower()), None)
        if not key or key not in rea_data:
            return jsonify({'error': 'Joueur introuvable'}), 404
        rea_data[key]['reas'] = max(0, rea_data[key]['reas'] - amount)
        rea_data[key]['history'].insert(0, {'action': 'remove', 'amount': amount, 'note': data.get('note', ''), 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        save_json(_wt_rea, rea_data)
        return jsonify({'status': 'success', 'reas': rea_data[key]['reas']})

    @web_app.route('/api/test/rea/delete', methods=['POST'])
    def api_test_rea_delete():
        data = request.get_json(silent=True) or {}
        key = (data.get('license') or data.get('joueur') or data.get('nom') or '').strip()
        rea_data = load_json(_wt_rea, {})
        if key in rea_data:
            del rea_data[key]
        else:
            key = next((k for k, v in rea_data.items() if v.get('nom','').lower() == key.lower()), None)
            if key:
                del rea_data[key]
        save_json(_wt_rea, rea_data)
        return jsonify({'status': 'success'})

    @web_app.route('/api/test/rea/set', methods=['POST'])
    def api_test_rea_set():
        """DÃ©finir directement le total de rÃ©as d'un joueur (Ã©crase l'ancien)."""
        data = request.get_json(silent=True) or {}
        key = (data.get('license') or data.get('nom') or '').strip()
        total = int(data.get('total', 0))
        if not key:
            return jsonify({'error': 'License ou nom requis'}), 400
        if total < 0:
            return jsonify({'error': 'Total invalide'}), 400
        rea_data = load_json(_wt_rea, {})
        if key not in rea_data:
            rea_data[key] = {'nom': data.get('nom', key), 'license': data.get('license', ''), 'reas': 0, 'history': []}
        ancien = rea_data[key]['reas']
        rea_data[key]['reas'] = total
        if data.get('nom'): rea_data[key]['nom'] = data['nom']
        if data.get('license'): rea_data[key]['license'] = data['license']
        rea_data[key]['history'].insert(0, {
            'action': 'set',
            'amount': total,
            'note': f"DÃ©finition manuelle (ancien: {ancien})",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        save_json(_wt_rea, rea_data)
        return jsonify({'status': 'success', 'reas': total})

    @web_app.route('/api/test/import-stats', methods=['POST'])
    def api_test_import_stats():
        stats = load_json(STATS_FILE, {})
        if not stats:
            return jsonify({'error': 'stats.json vide ou introuvable'}), 404
        lmap = load_json(_wt_map, {})

        # Index license â†’ nom_key du stats (dans les deux sens)
        name_to_lic = {}
        for lic, info in lmap.items():
            for field in ('employee', 'joueur'):
                nk = (info.get(field) or '').lower().replace(' ', '-')
                if nk:
                    name_to_lic[nk] = lic

        rea_data = load_json(_wt_rea, {})
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        imported = 0
        for nom_key, count in stats.items():
            lic = name_to_lic.get(nom_key, '')
            nom_display = lmap.get(lic, {}).get('nom') or nom_key.replace('-', ' ').title()
            key = lic or nom_key
            ancien = rea_data.get(key, {}).get('reas', 0)
            # Si l'entrÃ©e nom-clÃ© existe ET qu'on a maintenant une license, fusionner
            if lic and nom_key in rea_data and lic not in rea_data:
                old_entry = rea_data.pop(nom_key)
                ancien = old_entry.get('reas', 0)
            elif lic and nom_key in rea_data and lic in rea_data:
                # Doublon : additionner puis supprimer l'ancienne clÃ© nom
                rea_data[lic]['reas'] += rea_data[nom_key].get('reas', 0)
                rea_data[lic]['history'] = rea_data[nom_key].get('history', []) + rea_data[lic].get('history', [])
                rea_data[lic]['nom'] = nom_display
                del rea_data[nom_key]
                imported += 1
                continue
            rea_data[key] = {
                'nom': nom_display,
                'license': lic,
                'reas': int(count),
                'history': [{'action': 'import', 'amount': int(count), 'note': f'Import stats.json (ancien: {ancien})', 'timestamp': ts}]
                           + rea_data.get(key, {}).get('history', []),
            }
            imported += 1
        save_json(_wt_rea, rea_data)
        return jsonify({'status': 'success', 'imported': imported, 'total_joueurs': len(rea_data)})

    @web_app.route('/api/test/rea/fix-keys', methods=['POST'])
    def api_test_rea_fix_keys():
        """Fusionne toutes les entrÃ©es nom-clÃ© avec leur license correspondante."""
        lmap = load_json(_wt_map, {})
        name_to_lic = {}
        for lic, info in lmap.items():
            for field in ('employee', 'joueur'):
                nk = (info.get(field) or '').lower().replace(' ', '-')
                if nk:
                    name_to_lic[nk] = lic

        rea_data = load_json(_wt_rea, {})
        merged = 0
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for nom_key in list(rea_data.keys()):
            if nom_key.startswith('license:'):
                continue
            lic = name_to_lic.get(nom_key)
            if not lic:
                continue
            entry = rea_data[nom_key]
            nom_display = lmap[lic].get('nom') or entry.get('nom', nom_key.replace('-', ' ').title())
            if lic in rea_data:
                # Doublon : additionner
                rea_data[lic]['reas'] += entry.get('reas', 0)
                rea_data[lic]['history'] = entry.get('history', []) + rea_data[lic].get('history', [])
                rea_data[lic]['nom'] = nom_display
            else:
                rea_data[lic] = {**entry, 'license': lic, 'nom': nom_display}
            del rea_data[nom_key]
            merged += 1
        save_json(_wt_rea, rea_data)
        return jsonify({'status': 'success', 'merged': merged, 'total': len(rea_data)})

    @web_app.route('/api/test/reset-week', methods=['POST'])
    def api_test_reset_week():
        """Marque un reset hebdomadaire : archive les rÃ©as et repart Ã  zÃ©ro."""
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rea_data = load_json(_wt_rea, {})
        # Archive dans meta
        meta = load_json(_wt_meta, {})
        meta['last_reset'] = ts
        meta['archived_reas'] = meta.get('archived_reas', [])
        if rea_data:
            meta['archived_reas'].insert(0, {'reset_at': ts, 'reas': dict(rea_data)})
            meta['archived_reas'] = meta['archived_reas'][:10]  # garder 10 resets max
        save_json(_wt_meta, meta)
        save_json(_wt_rea, {})
        return jsonify({'status': 'success', 'reset_at': ts})

    @web_app.route('/api/test/meta')
    def api_test_meta():
        meta = load_json(_wt_meta, {})
        return jsonify({'meta': meta})

    @web_app.route('/api/test/stats')
    def api_test_stats():
        logs     = load_json(_wt_logs, [])
        errors   = load_json(_wt_errors, [])
        rea_data = load_json(_wt_rea, {})
        meta     = load_json(_wt_meta, {})
        ventes   = [l for l in logs if l.get('type') in ('vente', 'vente_importante')]
        return jsonify({
            'total_logs':         len(logs),
            'total_ventes':       len(ventes),
            'total_services_in':  len([l for l in logs if l.get('type') == 'prise_service']),
            'total_services_out': len([l for l in logs if l.get('type') == 'fin_service']),
            'montant_total':      sum(l.get('montant', 0) for l in ventes),
            'total_errors':       len(errors),
            'total_reas':         sum(v.get('reas', 0) for v in rea_data.values()),
            'joueurs_rea':        len(rea_data),
            'last_reset':         meta.get('last_reset', 'â€”'),
        })

    @web_app.route('/api/test/clear', methods=['POST'])
    def api_test_clear():
        target = (request.get_json(silent=True) or {}).get('target', 'all')
        if target in ('logs', 'all'):   save_json(_wt_logs, [])
        if target in ('errors', 'all'): save_json(_wt_errors, [])
        if target in ('rea', 'all'):    save_json(_wt_rea, {})
        if target == 'all':             save_json(_wt_map, {})
        return jsonify({'status': 'success', 'cleared': target})

    # ============ FIN DES ROUTES DE TEST ============

    def run_web():
        port = int(os.environ.get('PORT', 8080))
        web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    print(f"ðŸŒ Dashboard web dÃ©marrÃ© sur le port {os.environ.get('PORT', 8080)}")

    import time
    max_retries = 5
    retry_count = 0
    
    if config['TOKEN']:
        while retry_count < max_retries:
            try:
                print(f"ðŸš€ DÃ©marrage du bot EMS... (Tentative {retry_count + 1}/{max_retries})")
                bot.run(config['TOKEN'])
                break  # Si le bot s'arrÃªte proprement, sortir de la boucle
            except KeyboardInterrupt:
                    # ðŸ’¾ SAUVEGARDE FINALE AVANT ARRÃŠT MANUEL
                try:
                    stats = load_stats()
                    atomic_write_json(STATS_FILE, stats, make_backup=True)
                    print(f"ðŸ’¾ Sauvegarde finale effectuÃ©e avant arrÃªt")
                except:
                    pass
                print("â¹ï¸ ArrÃªt manuel du bot...")
                break
            except Exception as e:
                    # ðŸ’¾ SAUVEGARDE D'URGENCE EN CAS D'ERREUR
                try:
                    stats = load_stats()
                    atomic_write_json(STATS_FILE, stats, make_backup=True)
                    print(f"ðŸ’¾ Sauvegarde d'urgence effectuÃ©e")
                except:
                    pass
                
                retry_count += 1
                print(f"âŒ Erreur critique: {e}")
                
                if retry_count < max_retries:
                    wait_time = min(30 * retry_count, 300)  # Max 5 minutes
                    print(f"ðŸ”„ RedÃ©marrage automatique dans {wait_time} secondes...")
                    time.sleep(wait_time)
                else:
                    print(f"âŒ Nombre maximum de tentatives atteint ({max_retries}). ArrÃªt dÃ©finitif.")
                    break

























