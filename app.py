# github_key_manager.py
import os
import time
import json
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import threading
import schedule

# ===== CONFIGURAÇÕES =====
# No seu código Python
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
REPO_NAME = "natividadepedro0404-sudo/api2"  # Ex: "joao/keys-bot"
BRANCH = "main"

# Arquivos no repositório
HIGHLIGHTS_FILE = "keys_higlights.txt"
MIDLIGHTS_FILE = "keys_midlights.txt"
EXPIRED_FILE = "expired_keys.txt"
KEYS_DB_FILE = "keys_database.json"

# Configurações de expiração
KEY_DURATION_HOURS = 24  # Tempo padrão de expiração em horas
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'dark040816')

# Inicializar Flask
app = Flask(__name__)
CORS(app)

# ===== FUNÇÕES DO GITHUB =====
def get_github_content(file_path):
    """Pega o conteúdo de um arquivo do GitHub"""
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            content = response.json()
            import base64
            decoded = base64.b64decode(content['content']).decode('utf-8')
            return decoded, content['sha']
        return None, None
    except Exception as e:
        print(f"Erro ao ler {file_path}: {e}")
        return None, None

def update_github_file(file_path, content, commit_message):
    """Atualiza um arquivo no GitHub"""
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Verificar se arquivo já existe
    existing_content, sha = get_github_content(file_path)
    
    import base64
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    
    data = {
        "message": commit_message,
        "content": encoded_content,
        "branch": BRANCH
    }
    
    if sha:
        data["sha"] = sha
    
    try:
        response = requests.put(url, headers=headers, json=data)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"Erro ao atualizar {file_path}: {e}")
        return False

# ===== GERENCIAMENTO DE KEYS =====
def load_keys_database():
    """Carrega o banco de dados de keys"""
    content, _ = get_github_content(KEYS_DB_FILE)
    if content:
        try:
            return json.loads(content)
        except:
            return {}
    return {}

def save_keys_database(db):
    """Salva o banco de dados de keys"""
    content = json.dumps(db, indent=2, default=str)
    return update_github_file(KEYS_DB_FILE, content, "Update keys database")

def add_key(key, key_type, duration_hours=KEY_DURATION_HOURS):
    """Adiciona uma nova key"""
    db = load_keys_database()
    
    if key in db:
        return False, "Key já existe"
    
    now = datetime.now()
    db[key] = {
        "type": key_type,  # "HIGHLIGHTS" ou "MIDLIGHTS"
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=duration_hours)).isoformat(),
        "active": True
    }
    
    if not save_keys_database(db):
        return False, "Erro ao salvar no GitHub"
    
    # Adicionar ao arquivo txt apropriado
    txt_file = HIGHLIGHTS_FILE if key_type == "HIGHLIGHTS" else MIDLIGHTS_FILE
    current_content, _ = get_github_content(txt_file)
    new_content = current_content + key + "\n" if current_content else key + "\n"
    
    if not update_github_file(txt_file, new_content, f"Add key: {key}"):
        return False, "Erro ao adicionar ao arquivo txt"
    
    return True, f"Key {key} adicionada com sucesso! Expira em {duration_hours} horas"

def remove_key(key):
    """Remove uma key (move para expired)"""
    db = load_keys_database()
    
    if key not in db:
        return False, "Key não encontrada"
    
    db[key]["active"] = False
    db[key]["expired_at"] = datetime.now().isoformat()
    
    if not save_keys_database(db):
        return False, "Erro ao salvar no GitHub"
    
    # Remover dos arquivos txt
    key_type = db[key]["type"]
    txt_file = HIGHLIGHTS_FILE if key_type == "HIGHLIGHTS" else MIDLIGHTS_FILE
    current_content, _ = get_github_content(txt_file)
    
    if current_content:
        lines = current_content.splitlines()
        new_lines = [line for line in lines if line != key]
        new_content = "\n".join(new_lines)
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        
        update_github_file(txt_file, new_content, f"Remove key: {key}")
    
    # Adicionar ao expired
    expired_content, _ = get_github_content(EXPIRED_FILE)
    expired_line = f"{key} - {datetime.now().isoformat()} - {key_type}\n"
    new_expired = expired_content + expired_line if expired_content else expired_line
    update_github_file(EXPIRED_FILE, new_expired, f"Expired key: {key}")
    
    return True, f"Key {key} removida"

def check_key(key):
    """Verifica se uma key é válida"""
    db = load_keys_database()
    
    if key not in db:
        return False, None, "Key não encontrada"
    
    key_data = db[key]
    
    if not key_data.get("active", True):
        return False, None, "Key inativa"
    
    expires_at = datetime.fromisoformat(key_data["expires_at"])
    
    if datetime.now() > expires_at:
        # Key expirada, remover automaticamente
        remove_key(key)
        return False, None, "Key expirada"
    
    return True, key_data["type"], "Key válida"

def list_keys():
    """Lista todas as keys ativas"""
    db = load_keys_database()
    active_keys = []
    
    for key, data in db.items():
        if data.get("active", True):
            expires_at = datetime.fromisoformat(data["expires_at"])
            if datetime.now() < expires_at:
                active_keys.append({
                    "key": key,
                    "type": data["type"],
                    "created_at": data["created_at"],
                    "expires_at": data["expires_at"]
                })
    
    return active_keys

def cleanup_expired_keys():
    """Limpa keys expiradas automaticamente"""
    print(f"[{datetime.now()}] Verificando keys expiradas...")
    db = load_keys_database()
    removed_count = 0
    
    for key, data in db.items():
        if data.get("active", True):
            expires_at = datetime.fromisoformat(data["expires_at"])
            if datetime.now() > expires_at:
                remove_key(key)
                removed_count += 1
                print(f"  - Key expirada removida: {key}")
    
    if removed_count > 0:
        print(f"✅ {removed_count} keys expiradas removidas")
    else:
        print("✅ Nenhuma key expirada encontrada")

# ===== ENDPOINTS DA API =====
@app.route('/verify-key', methods=['POST'])
def verify_key():
    """Endpoint para verificar key"""
    try:
        data = request.json
        key = data.get('key')
        
        if not key:
            return jsonify({"status": "error", "message": "No key provided"}), 400
        
        valid, key_type, message = check_key(key)
        
        return jsonify({
            "status": "success" if valid else "error",
            "valid": valid,
            "key_type": key_type if valid else None,
            "message": message
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/add-key', methods=['POST'])
def add_key_endpoint():
    """Endpoint para adicionar keys"""
    try:
        data = request.json
        admin_key = data.get('admin_key')
        
        if admin_key != ADMIN_PASSWORD:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        key = data.get('key')
        key_type = data.get('key_type')
        duration = data.get('duration_hours', KEY_DURATION_HOURS)
        
        if not key or not key_type:
            return jsonify({"status": "error", "message": "Key and key_type required"}), 400
        
        if key_type not in ["HIGHLIGHTS", "MIDLIGHTS"]:
            return jsonify({"status": "error", "message": "Invalid key_type"}), 400
        
        success, message = add_key(key, key_type, duration)
        
        return jsonify({
            "status": "success" if success else "error",
            "message": message
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/remove-key', methods=['POST'])
def remove_key_endpoint():
    """Endpoint para remover key"""
    try:
        data = request.json
        admin_key = data.get('admin_key')
        
        if admin_key != ADMIN_PASSWORD:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        key = data.get('key')
        
        if not key:
            return jsonify({"status": "error", "message": "No key provided"}), 400
        
        success, message = remove_key(key)
        
        return jsonify({
            "status": "success" if success else "error",
            "message": message
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/list-keys', methods=['GET'])
def list_keys_endpoint():
    """Lista todas as keys ativas"""
    admin_key = request.headers.get('X-Admin-Key')
    
    if admin_key != ADMIN_PASSWORD:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    keys = list_keys()
    return jsonify({"status": "success", "keys": keys})

@app.route('/get-brainrots', methods=['GET'])
def get_brainrots():
    """Endpoint para o menu buscar brainrots"""
    # Aqui você integra com seu banco de dados de brainrots
    # Por enquanto retorna exemplo
    return jsonify({
        "status": "success",
        "brainrots": []
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/admin', methods=['GET'])
def admin_panel():
    """Serve o painel administrativo"""
    return send_from_directory('.', 'admin.html')

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Brainrot Scanner - Key Manager",
        "endpoints": {
            "verify_key": "POST /verify-key",
            "add_key": "POST /add-key",
            "remove_key": "POST /remove-key",
            "list_keys": "GET /list-keys",
            "admin_panel": "GET /admin",
            "health": "GET /health"
        }
    })

# ===== MAIN =====
def run_scheduler():
    """Executa o agendador em background"""
    while True:
        schedule.run_pending()
        time.sleep(60)

# No final do arquivo, substitua a parte do main por:

if __name__ == '__main__':
    import os
    
    print("🚀 BRAINROT SCANNER - KEY MANAGER")
    print("=" * 50)
    
    # Agendar limpeza automática
    schedule.every(1).hours.do(cleanup_expired_keys)
    cleanup_expired_keys()
    
    # Iniciar scheduler em thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Para produção no Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
