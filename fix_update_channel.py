#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os

# Lire le fichier
with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Trouver et remplacer la fonction update_channel_description
output_lines = []
i = 0
while i < len(lines):
    if 'async def update_channel_description' in lines[i]:
        # Trouvé la fonction, on va la remplacer
        # D'abord on ajoute la ligne de définition
        output_lines.append(lines[i])
        i += 1
        
        # Ajouter les lignes jusqu'à la fin de try:
        while i < len(lines) and 'try:' not in lines[i]:
            output_lines.append(lines[i])
            i += 1
        
        output_lines.append(lines[i])  # try:
        i += 1
        
        # Remplacer le contenu
        new_func_body = '''        emoji = get_color_emoji(count)
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
'''
        
        output_lines.append(new_func_body)
        
        # Sauter les lignes de l'ancienne fonction
        while i < len(lines):
            if i + 1 < len(lines) and (lines[i+1].startswith('@') or lines[i+1].startswith('def ') or lines[i+1].startswith('async def ')):
                i += 1
                break
            if lines[i].strip() and not lines[i].startswith(' ' * 4) and not lines[i].startswith('\t'):
                break
            i += 1
    else:
        output_lines.append(lines[i])
        i += 1

# Écrire le fichier
with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(output_lines)

print("✅ Fonction update_channel_description mise à jour avec employee_key !")
