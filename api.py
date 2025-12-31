from flask import Flask, request, jsonify
import requests
import sqlite3
from datetime import datetime
import threading
import time
import os

# IMPORTANTE: Instale flask-cors primeiro!
# No console do Replit: pip install flask-cors
from flask_cors import CORS

app = Flask(__name__)

# Configuração CORS
CORS(app)

# Middleware CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Webhooks
WEBHOOKS = {
    "NORMAL_WEBHOOK": "https://ptb.discord.com/api/webhooks/1455361732523327730/aCZn_oDnIDjOoHzCkrPk_x9ohfSFWSO9kNzkSFo0kYNxmZIyrOcrrqSN80S3tQs_LINk",
    "SPECIAL_WEBHOOK": "https://ptb.discord.com/api/webhooks/1455361536078905479/IptfKoKAO-imuZ39zysfeIBoHb-0ZIqOHkYHTc2AA7TqscwZA5xn8vKQmc4RbgJ5rZUP",
    "ULTRA_HIGH_WEBHOOK": "https://ptb.discord.com/api/webhooks/1455361629880582239/tpNHrWPlXGi8SyStifJ-A0mMYHLSIkP2kE_UzW6rZRRbS8xtLxmN1CvIk7081pbdo6eX",
    "BRAINROT_150M_WEBHOOK": "https://ptb.discord.com/api/webhooks/1455430968575000729/4GH6iNeP3K6EeCtmFja1KzYxqGSICaXxtJURaZVq9LWzSsT9SwKGVw2ZqVUzMAqhFQpf"
}

# Banco de dados
DB_FILE = "servers.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS sent_servers
                     (job_id TEXT PRIMARY KEY,
                      timestamp DATETIME,
                      webhook_type TEXT,
                      category TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS sent_brainrot_150m
                     (job_id TEXT PRIMARY KEY,
                      timestamp DATETIME)''')
        conn.commit()
        conn.close()
        print("✅ Banco de dados inicializado")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")

# ROTA RAIZ - ADICIONE ESTA ROTA!
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "api": "brainrot-scanner",
        "version": "1.0",
        "endpoints": {
            "GET": ["/", "/health", "/servers"],
            "POST": ["/webhook-filter"]
        },
        "replit_url": "https://infinity--p808409.replit.app",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

def was_server_sent(job_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT job_id FROM sent_servers WHERE job_id = ?", (job_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
    except:
        return False

def mark_server_sent(job_id, webhook_type, category):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO sent_servers VALUES (?, ?, ?, ?)",
                  (job_id, datetime.now(), webhook_type, category))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Erro ao salvar no banco: {e}")

@app.route('/webhook-filter', methods=['POST', 'OPTIONS'])
def webhook_filter():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    
    try:
        print(f"\n{'='*50}")
        print("📥 Nova requisição recebida")
        
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        
        job_id = data.get('job_id')
        if not job_id:
            return jsonify({"status": "error", "message": "Missing job_id"}), 400
        
        # Verificar duplicata
        if was_server_sent(job_id):
            print(f"📭 Duplicata ignorada: {job_id}")
            return jsonify({"status": "duplicate", "message": "Already sent"}), 200
        
        # Determinar webhook correto baseado nos dados
        webhook_type = determine_webhook_type(data)
        webhook_url = WEBHOOKS.get(webhook_type, WEBHOOKS["NORMAL_WEBHOOK"])
        
        # Preparar embed para Discord
        discord_data = prepare_discord_embed(data, webhook_type)
        
        # Enviar para Discord (assíncrono)
        discord_queue.put((webhook_url, discord_data))
        
        # Marcar como enviado
        mark_server_sent(job_id, webhook_type, data.get('category', 'UNKNOWN'))
        
        print(f"✅ Enfileirado para Discord: {job_id}")
        print(f"{'='*50}\n")
        
        return jsonify({
            "status": "success",
            "message": "Received and queued for Discord",
            "job_id": job_id,
            "webhook_type": webhook_type
        }), 200
        
    except Exception as e:
        print(f"🔥 ERRO: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/servers', methods=['GET'])
def list_servers():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT job_id, timestamp, webhook_type, category FROM sent_servers ORDER BY timestamp DESC LIMIT 20")
        servers = c.fetchall()
        conn.close()
        
        server_list = []
        for server in servers:
            server_list.append({
                "job_id": server[0],
                "timestamp": server[1],
                "webhook_type": server[2],
                "category": server[3]
            })
        
        return jsonify({
            "status": "success",
            "count": len(server_list),
            "servers": server_list
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/test', methods=['GET', 'POST'])
def test():
    """Endpoint de teste"""
    if request.method == 'GET':
        return jsonify({
            "status": "test",
            "message": "Test endpoint works!",
            "use_post": "Send POST with JSON data"
        })
    
    # POST
    try:
        data = request.get_json() or {}
        return jsonify({
            "status": "success",
            "message": "Test data received",
            "your_data": data,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    # Inicializar banco
    init_db()
    
    # Configurar porta
    port = int(os.environ.get("PORT", 5000))
    
    print("\n" + "="*60)
    print("🚀 BRAINROT SCANNER API - REINICIADA")
    print("="*60)
    print(f"📡 Porta: {port}")
    print(f"🌐 URL: https://infinity--p808409.replit.app")
    print("🔗 Endpoints disponíveis:")
    print("   GET  /              - Status da API")
    print("   GET  /health        - Health check")
    print("   GET  /servers       - Lista de servidores")
    print("   GET  /test          - Teste GET")
    print("   POST /test          - Teste POST")
    print("   POST /webhook-filter- Receber dados do Roblox")
    print("="*60)
    print("✅ API PRONTA!")
    print("="*60 + "\n")
    
    # Iniciar servidor
    app.run(host='0.0.0.0', port=port, debug=False)
