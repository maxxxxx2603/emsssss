from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import time
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
from io import BytesIO
import base64

app = Flask(__name__)

# Configuration - Utiliser le même DATA_DIR que main.py pour partager les fichiers
DATA_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ".")
if DATA_DIR != "." and not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

STATS_FILE = os.path.join(DATA_DIR, 'stats.json')
ABSENCE_FILE = os.path.join(DATA_DIR, 'absences.json')
SERVICE_FILE = os.path.join(DATA_DIR, 'services.json')
REUNION_FILE = os.path.join(DATA_DIR, 'reunion_announce.json')

def load_json(filepath, default=None):
    """Load JSON file safely"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
    except:
        pass
    return default or {}

def save_json(filepath, data):
    """Save JSON file safely"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

def normalize_name(name):
    """Normalize employee name"""
    return name.lower().strip().replace(' ', '-')

@app.route('/')
def index():
    """Main dashboard"""
    stats = load_json(STATS_FILE, {})
    absences = load_json(ABSENCE_FILE, {})
    
    # Get employees list
    employees = list(stats.keys())
    employees.sort(key=lambda x: stats[x], reverse=True)
    
    # Prepare data for template
    employee_data = []
    for emp in employees:
        rea_count = stats.get(emp, 0)
        is_absent = False
        
        # Check if absent today
        today = datetime.now().strftime("%Y-%m-%d")
        if emp in absences and today in absences[emp]:
            is_absent = True
        
        # Color based on count
        if rea_count >= 100:
            color = "green"
        elif rea_count >= 75:
            color = "orange"
        else:
            color = "red"
        
        employee_data.append({
            'name': emp.replace('-', ' ').title(),
            'count': rea_count,
            'color': color,
            'absent': is_absent
        })
    
    return render_template('dashboard.html', employees=employee_data, total_stats=sum(stats.values()))

@app.route('/api/stats')
def api_stats():
    """API endpoint for stats"""
    stats = load_json(STATS_FILE, {})
    return jsonify(stats)

@app.route('/api/absences')
def api_absences():
    """API endpoint for absences"""
    absences = load_json(ABSENCE_FILE, {})
    return jsonify(absences)

@app.route('/api/services')
def api_services():
    """API endpoint for services (heures de service par employé)"""
    services = load_json(SERVICE_FILE, {})
    return jsonify(services)

@app.route('/api/reunion')
def api_reunion():
    """Get reunion announcement"""
    reunion = load_json(REUNION_FILE, None)
    if reunion:
        return jsonify(reunion)
    return jsonify(None)

@app.route('/api/employee/<name>')
def api_employee(name):
    """Get specific employee data"""
    normalized = normalize_name(name)
    stats = load_json(STATS_FILE, {})
    absences = load_json(ABSENCE_FILE, {})
    
    # Find matching employee
    matching_key = None
    for key in stats.keys():
        if normalize_name(key) == normalized:
            matching_key = key
            break
    
    if not matching_key:
        return jsonify({'error': 'Employee not found'}), 404
    
    emp_absences = absences.get(matching_key, [])
    
    return jsonify({
        'name': matching_key,
        'reas': stats.get(matching_key, 0),
        'absences': emp_absences,
        'absent_today': datetime.now().strftime("%Y-%m-%d") in emp_absences
    })

@app.route('/api/absence/add', methods=['POST'])
def add_absence():
    """Endpoint supprimé - utilise /absence sur Discord directement"""
    return jsonify({'error': 'Endpoint supprimé. Utilisez /absence sur Discord'}), 404

@app.route('/api/absence/remove', methods=['POST'])
def remove_absence():
    """Endpoint supprimé - utilise /absence sur Discord directement"""
    return jsonify({'error': 'Endpoint supprimé. Utilisez /absence sur Discord'}), 404



@app.route('/api/charts/stats')
def chart_stats():
    """Generate and return stats chart as base64 image"""
    stats = load_json(STATS_FILE, {})
    
    if not stats:
        return jsonify({'error': 'No data available'}), 404
    
    # Sort by value
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    names = [name.replace('-', ' ').title() for name, _ in sorted_stats]
    values = [val for _, val in sorted_stats]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Create bar chart with colors based on quota
    colors = []
    for val in values:
        if val >= 100:
            colors.append('#2ecc71')  # Green
        elif val >= 75:
            colors.append('#f39c12')  # Orange
        else:
            colors.append('#e74c3c')  # Red
    
    bars = ax.barh(names, values, color=colors)
    
    # Add value labels
    for i, (bar, val) in enumerate(zip(bars, values)):
        ax.text(val + 2, bar.get_y() + bar.get_height()/2, 
               f'{val}/100', va='center', fontweight='bold')
    
    # Add quota line
    ax.axvline(x=100, color='green', linestyle='--', linewidth=2, alpha=0.7, label='Quota (100)')
    ax.axvline(x=75, color='orange', linestyle='--', linewidth=2, alpha=0.7, label='Min (75)')
    
    # Styling
    ax.set_xlabel('Nombre de Réanimations', fontsize=12, fontweight='bold')
    ax.set_title('📊 Statistiques EMS - Réanimations par Employé', fontsize=14, fontweight='bold')
    ax.set_xlim(0, max(values) * 1.15)
    ax.legend(loc='lower right')
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    
    # Convert to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    
    return jsonify({
        'image': f'data:image/png;base64,{image_base64}',
        'stats': dict(sorted_stats)
    })

@app.route('/api/charts/absence')
def chart_absence():
    """Generate and return absence chart as base64 image"""
    absences = load_json(ABSENCE_FILE, {})
    
    if not absences:
        return jsonify({'error': 'No absence data'}), 404
    
    # Count absences per employee
    absence_counts = {}
    for emp, dates_dict in absences.items():
        # Handle both old format (list) and new format (dict)
        if isinstance(dates_dict, dict):
            absence_counts[emp] = len(dates_dict)  # Count keys
        else:
            absence_counts[emp] = len(dates_dict)  # Count list items
    
    # Sort by count
    sorted_absences = sorted(absence_counts.items(), key=lambda x: x[1], reverse=True)[:15]  # Top 15
    names = [name.replace('-', ' ').title() for name, _ in sorted_absences]
    values = [val for _, val in sorted_absences]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Create bar chart
    bars = ax.barh(names, values, color='#3498db')
    
    # Add value labels
    for bar, val in zip(bars, values):
        ax.text(val + 0.1, bar.get_y() + bar.get_height()/2, 
               f'{val}', va='center', fontweight='bold')
    
    # Styling
    ax.set_xlabel('Nombre d\'Absences', fontsize=12, fontweight='bold')
    ax.set_title('📊 Absences par Employé (Top 15)', fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    
    # Convert to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    
    return jsonify({
        'image': f'data:image/png;base64,{image_base64}',
        'data': dict(sorted_absences)
    })


@app.route('/employees')
def employees_page():
    """Employees page with absences management"""
    stats = load_json(STATS_FILE, {})
    absences = load_json(ABSENCE_FILE, {})
    
    employee_list = []
    for emp in sorted(stats.keys()):
        rea_count = stats[emp]
        emp_absences_data = absences.get(emp, {})
        
        # Handle both old format (list) and new format (dict)
        if isinstance(emp_absences_data, list):
            # Old format - convert to new
            emp_absences_display = [
                {'date_debut': d, 'date_retour': '', 'raison': ''} 
                for d in emp_absences_data
            ]
        else:
            # New format - dict with date_debut as key
            emp_absences_display = [
                {
                    'date_debut': k,
                    'date_retour': v.get('date_retour', ''),
                    'raison': v.get('raison', '')
                }
                for k, v in sorted(emp_absences_data.items(), reverse=True)
            ]
        
        # Check if absent today
        today = datetime.now().strftime("%Y-%m-%d")
        is_absent = today in emp_absences_data if isinstance(emp_absences_data, dict) else today in emp_absences_data
        
        employee_list.append({
            'name': emp.replace('-', ' ').title(),
            'key': emp,
            'reas': rea_count,
            'absences_count': len(emp_absences_display),
            'absent_today': is_absent,
            'recent_absences': emp_absences_display[:7],
            'all_absences': emp_absences_display
        })
    
    return render_template('employees.html', employees=employee_list)

# ============ ROUTES DE TEST - GESTION DES LOGS ESX_SOCIETY ============

TEST_LOGS_FILE  = os.path.join(DATA_DIR, 'test_logs.json')
TEST_ERRORS_FILE = os.path.join(DATA_DIR, 'test_errors.json')
TEST_REA_FILE   = os.path.join(DATA_DIR, 'test_rea.json')


@app.route('/test')
def test_logs_page():
    """Page de test - logs esx_society en temps réel"""
    return render_template('test_logs.html')


@app.route('/api/test/logs', methods=['GET', 'DELETE'])
def api_test_logs():
    """GET: récupérer les logs valides. DELETE: supprimer une log par id."""
    if request.method == 'GET':
        logs = load_json(TEST_LOGS_FILE, [])
        log_type = request.args.get('type')
        if log_type:
            logs = [l for l in logs if l.get('type') == log_type]
        return jsonify({'logs': logs, 'total': len(logs)})

    # DELETE
    log_id = request.args.get('id')
    if not log_id:
        return jsonify({'error': 'ID requis'}), 400
    logs = load_json(TEST_LOGS_FILE, [])
    logs = [l for l in logs if str(l.get('id')) != str(log_id)]
    if save_json(TEST_LOGS_FILE, logs):
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Erreur sauvegarde'}), 500


@app.route('/api/test/errors', methods=['GET', 'DELETE'])
def api_test_errors():
    """GET: erreurs/rejets. DELETE: vider les erreurs."""
    if request.method == 'GET':
        errors = load_json(TEST_ERRORS_FILE, [])
        return jsonify({'errors': errors, 'total': len(errors)})
    # DELETE - vider
    save_json(TEST_ERRORS_FILE, [])
    return jsonify({'status': 'success'})


# ---- GESTION MANUELLE DES RÉAS ----

@app.route('/api/test/rea', methods=['GET'])
def api_test_rea_list():
    """Lister les réas manuelles enregistrées."""
    rea_data = load_json(TEST_REA_FILE, {})
    return jsonify({'rea': rea_data})


@app.route('/api/test/rea/add', methods=['POST'])
def api_test_rea_add():
    """Ajouter une réa manuelle à un joueur."""
    data = request.get_json(silent=True) or {}
    joueur = (data.get('joueur') or '').strip()
    license_key = (data.get('license') or '').strip()
    amount = int(data.get('amount', 1))
    note = (data.get('note') or '').strip()

    if not joueur:
        return jsonify({'error': 'Joueur requis'}), 400
    if amount < 1:
        return jsonify({'error': 'Montant invalide'}), 400

    rea_data = load_json(TEST_REA_FILE, {})
    key = joueur.lower()
    if key not in rea_data:
        rea_data[key] = {'joueur': joueur, 'license': license_key, 'reas': 0, 'history': []}
    rea_data[key]['reas'] += amount
    rea_data[key]['history'].insert(0, {
        'action': 'add',
        'amount': amount,
        'note': note,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })
    if license_key:
        rea_data[key]['license'] = license_key
    save_json(TEST_REA_FILE, rea_data)
    return jsonify({'status': 'success', 'reas': rea_data[key]['reas']})


@app.route('/api/test/rea/remove', methods=['POST'])
def api_test_rea_remove():
    """Retirer une réa manuelle à un joueur."""
    data = request.get_json(silent=True) or {}
    joueur = (data.get('joueur') or '').strip()
    amount = int(data.get('amount', 1))
    note = (data.get('note') or '').strip()

    if not joueur:
        return jsonify({'error': 'Joueur requis'}), 400

    rea_data = load_json(TEST_REA_FILE, {})
    key = joueur.lower()
    if key not in rea_data:
        return jsonify({'error': 'Joueur introuvable'}), 404

    rea_data[key]['reas'] = max(0, rea_data[key]['reas'] - amount)
    rea_data[key]['history'].insert(0, {
        'action': 'remove',
        'amount': amount,
        'note': note,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })
    save_json(TEST_REA_FILE, rea_data)
    return jsonify({'status': 'success', 'reas': rea_data[key]['reas']})


@app.route('/api/test/rea/delete', methods=['POST'])
def api_test_rea_delete():
    """Supprimer complètement un joueur de la liste réa."""
    data = request.get_json(silent=True) or {}
    joueur = (data.get('joueur') or '').strip()
    if not joueur:
        return jsonify({'error': 'Joueur requis'}), 400
    rea_data = load_json(TEST_REA_FILE, {})
    key = joueur.lower()
    if key in rea_data:
        del rea_data[key]
        save_json(TEST_REA_FILE, rea_data)
    return jsonify({'status': 'success'})


@app.route('/api/test/stats')
def api_test_stats():
    """Statistiques globales de la page /test."""
    logs = load_json(TEST_LOGS_FILE, [])
    errors = load_json(TEST_ERRORS_FILE, [])
    rea_data = load_json(TEST_REA_FILE, {})

    ventes = [l for l in logs if l.get('type') in ('vente', 'vente_importante')]
    services_in = [l for l in logs if l.get('type') == 'prise_service']
    services_out = [l for l in logs if l.get('type') == 'fin_service']
    montant_total = sum(l.get('montant', 0) for l in ventes)
    total_reas_manual = sum(v.get('reas', 0) for v in rea_data.values())

    return jsonify({
        'total_logs': len(logs),
        'total_ventes': len(ventes),
        'total_services_in': len(services_in),
        'total_services_out': len(services_out),
        'montant_total': montant_total,
        'total_errors': len(errors),
        'total_reas_manual': total_reas_manual,
        'joueurs_rea': len(rea_data),
    })


@app.route('/api/test/clear', methods=['POST'])
def api_test_clear():
    """Effacer logs, erreurs ou tout selon le paramètre 'target'."""
    target = (request.get_json(silent=True) or {}).get('target', 'all')
    if target in ('logs', 'all'):
        save_json(TEST_LOGS_FILE, [])
    if target in ('errors', 'all'):
        save_json(TEST_ERRORS_FILE, [])
    if target in ('rea', 'all'):
        save_json(TEST_REA_FILE, {})
    return jsonify({'status': 'success', 'cleared': target})


# ============ FIN DES ROUTES DE TEST ============

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
