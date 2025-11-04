import datetime
import logging
import os
import secrets

import requests
from flask import Flask, request, jsonify, stream_with_context, render_template_string, g
from flask_cors import CORS

from security import security_manager, SecurityException

app = Flask("OpenGen Testers API")
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("opengen_proxy")

PUBLIC_ENDPOINT_URL = os.environ.get("PUBLIC_ENDPOINT_URL", "https://proxy.example.com/v1").rstrip("/")
TARGET_BASE_URL = os.environ.get("TARGET_BASE_URL", "https://api.lhyb.dpdns.org/v1")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")

if not INTERNAL_API_KEY:
    logger.warning("INTERNAL_API_KEY belum dikonfigurasi. Permintaan keluar akan gagal hingga variabel lingkungan diset.")

MODEL_MAPPING = {
    "npt-1.5": "gemini-2.5-flash-thinking-search",
    "npt-base": "gpt-3.5-turbo",
    "npt-2.0-non-reasoning": "grok-4-fast-non-reasoning-poe",
}

PROVIDER_MAPPING = {
    "npt-1.5": "Google",
    "npt-base": "OpenAI",
    "npt-2.0-non-reasoning": "xAI",
}

SPOOFED_MODELS = [
    {"id": "npt-1.5", "object": "model", "created": 1690000000, "owned_by": "opengen"},
    {"id": "npt-base", "object": "model", "created": 1690000000, "owned_by": "opengen"},
    {"id": "npt-2.0-non-reasoning", "object": "model", "created": 1690000000, "owned_by": "opengen"},
]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ dashboard_title }}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'><rect width='120' height='120' rx='24' fill='%230d6efd'/><text x='50%' y='55%' dominant-baseline='middle' text-anchor='middle' font-size='60' fill='white'>OG</text></svg>'">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        :root {
            --bg-color: #0d1117;
            --surface-color: #151b23;
            --surface-elevated: #1c2530;
            --border-color: rgba(255, 255, 255, 0.06);
            --primary-color: #4a9fff;
            --primary-hover: #3884f7;
            --success-color: #31c48d;
            --danger-color: #ff7262;
            --text-color: #f8fafc;
            --text-muted: rgba(248, 250, 252, 0.66);
            --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            --focus-ring: 0 0 0 3px rgba(74, 159, 255, 0.32);
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 2.5rem 1.5rem 3rem;
            background: radial-gradient(circle at 20% 20%, rgba(74, 159, 255, 0.12), transparent 45%), var(--bg-color);
            color: var(--text-color);
            font-family: var(--font-family);
            line-height: 1.6;
            animation: fadeIn 0.6s ease;
        }
        .container {
            max-width: 880px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 1.6rem;
            animation: slideUp 0.6s ease;
        }
        header {
            text-align: center;
            display: flex;
            flex-direction: column;
            gap: 1.2rem;
            align-items: center;
        }
        .internal-label {
            text-transform: uppercase;
            letter-spacing: 0.4em;
            font-size: 0.75rem;
            background: rgba(74, 159, 255, 0.08);
            color: var(--primary-color);
            padding: 0.4rem 1rem;
            border-radius: 999px;
            border: 1px solid rgba(74, 159, 255, 0.22);
        }
        header h1 {
            font-size: clamp(2rem, 4vw, 2.75rem);
            font-weight: 700;
            margin: 0;
        }
        .subtitle {
            color: var(--text-muted);
            max-width: 540px;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            padding: 0.55rem 1.15rem;
            border-radius: 999px;
            border: 1px solid var(--border-color);
            background: linear-gradient(120deg, rgba(28, 37, 48, 0.85), rgba(21, 27, 35, 0.9));
            color: var(--text-muted);
            font-size: 0.95rem;
            transition: background 0.3s ease, border-color 0.3s ease, color 0.3s ease;
        }
        .status-badge .dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #ffbd59;
            box-shadow: 0 0 0 0 rgba(255, 189, 89, 0.35);
            animation: pulse 2.2s infinite;
        }
        .status-badge.healthy {
            color: #c6f6d5;
            border-color: rgba(49, 196, 141, 0.35);
        }
        .status-badge.healthy .dot {
            background: var(--success-color);
            animation: none;
            box-shadow: none;
        }
        .alert {
            background: rgba(255, 114, 98, 0.1);
            border: 1px solid rgba(255, 114, 98, 0.35);
            color: #ffb4a8;
            padding: 1rem 1.25rem;
            border-radius: 18px;
            max-width: 620px;
        }
        main {
            display: grid;
            gap: 1.6rem;
        }
        .card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 18px;
            padding: 1.75rem;
            box-shadow: 0 18px 36px rgba(3, 12, 27, 0.28);
            transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
        }
        .card:hover {
            transform: translateY(-3px);
            box-shadow: 0 24px 48px rgba(3, 12, 27, 0.34);
            border-color: rgba(74, 159, 255, 0.4);
        }
        .card h2 {
            margin: 0 0 1rem;
            font-size: 1.25rem;
            font-weight: 600;
        }
        .card p {
            color: var(--text-muted);
        }
        .endpoint-code {
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            background: var(--surface-elevated);
            border-radius: 14px;
            padding: 0.85rem 1.1rem;
            margin-top: 0.8rem;
            font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
            font-size: 0.95rem;
            border: 1px solid rgba(74, 159, 255, 0.18);
            word-break: break-all;
        }
        .key-container {
            display: flex;
            gap: 0.75rem;
            margin-bottom: 1.1rem;
            flex-wrap: wrap;
        }
        input[type="text"],
        textarea,
        select {
            width: 100%;
            background: var(--surface-elevated);
            color: var(--text-color);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 14px;
            padding: 0.95rem 1rem;
            font-size: 1rem;
            transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease;
        }
        input[type="text"]:focus,
        textarea:focus,
        select:focus {
            outline: none;
            border-color: rgba(74, 159, 255, 0.55);
            box-shadow: var(--focus-ring);
            transform: translateY(-1px);
        }
        button {
            background: var(--primary-color);
            color: #ffffff;
            border: none;
            border-radius: 14px;
            padding: 0.9rem 1.35rem;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.55rem;
            transition: background 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease;
        }
        button:hover {
            background: var(--primary-hover);
            box-shadow: 0 12px 24px rgba(74, 159, 255, 0.28);
            transform: translateY(-1px);
        }
        button:disabled {
            background: rgba(255, 255, 255, 0.08);
            color: rgba(248, 250, 252, 0.55);
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
        }
        #copy-key-btn {
            padding: 0.9rem 1.15rem;
            min-width: 96px;
            justify-content: center;
        }
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 0.55rem;
            margin-bottom: 1.2rem;
        }
        label {
            font-weight: 500;
            color: var(--text-color);
        }
        #response-container {
            background: #0a0f16;
            border-radius: 14px;
            padding: 1.15rem;
            min-height: 180px;
            max-height: 420px;
            overflow-y: auto;
            border: 1px solid rgba(255, 255, 255, 0.08);
            font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
        }
        #response-container pre {
            margin: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .hint {
            margin-top: 0.5rem;
            font-size: 0.85rem;
            color: var(--text-muted);
        }
        footer {
            margin-top: 2.4rem;
            text-align: center;
            color: var(--text-muted);
            font-size: 0.85rem;
        }
        .toast-container {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
            z-index: 9999;
        }
        .toast {
            min-width: 240px;
            max-width: 320px;
            padding: 0.9rem 1.1rem;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(28, 37, 48, 0.78);
            backdrop-filter: blur(14px);
            color: var(--text-color);
            box-shadow: 0 12px 24px rgba(6, 10, 18, 0.28);
            opacity: 0;
            transform: translateY(12px);
            animation: toastIn 0.35s forwards;
        }
        .toast-success { border-color: rgba(49, 196, 141, 0.5); }
        .toast-error { border-color: rgba(255, 114, 98, 0.5); }
        .spinner {
            position: relative;
            width: 16px;
            height: 16px;
        }
        .spinner::before {
            content: "";
            position: absolute;
            inset: 0;
            border-radius: 50%;
            border: 2px solid rgba(255, 255, 255, 0.45);
            border-top-color: transparent;
            animation: spin 0.8s linear infinite;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(24px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes toastIn {
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(255, 189, 89, 0.35); }
            70% { box-shadow: 0 0 0 12px rgba(255, 189, 89, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 189, 89, 0); }
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        @media (max-width: 640px) {
            body { padding: 1.75rem 1.1rem 2.4rem; }
            .card { padding: 1.4rem; }
            .toast-container { right: 1rem; left: 1rem; bottom: 1.5rem; }
            .toast { width: 100%; max-width: none; }
        }
        @media (prefers-reduced-motion: reduce) {
            * { animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="internal-label">Test Internal</div>
            <h1>{{ dashboard_heading }}</h1>
            <p class="subtitle">Panel pengujian bergaya Slack dengan animasi halus untuk memonitor dan mencoba OpenGen Testers API.</p>
            <div class="status-badge" id="health-status">
                <span class="dot"></span>
                <span id="health-text">Memeriksa status...</span>
            </div>
            <div class="alert">
                <strong>PERINGATAN:</strong> Halaman ini bersifat TEST ONLY dan khusus untuk pihak yang telah disetujui. Penyebaran tanpa izin dilarang.
            </div>
        </header>

        <main>
            <section class="card">
                <h2>Endpoint Publik</h2>
                <p>Konsumsi API melalui endpoint berikut. Gunakan hanya untuk pengujian internal terbatas.</p>
                <div class="endpoint-code">{{ public_endpoint_url }}/chat/completions</div>
                <p class="hint">Pastikan kredensial dan tanda tangan keamanan dikirim bersama setiap permintaan.</p>
            </section>

            <section class="card">
                <h2>API Key Anda</h2>
                <div class="key-container">
                    <input type="text" id="api-key-display" placeholder="Generate kunci untuk memulai..." readonly>
                    <button id="copy-key-btn" type="button">Salin</button>
                </div>
                <button id="generate-key-btn" type="button">Generate Kunci Baru</button>
                <p class="hint">Kunci disimpan secara lokal di browser dan dapat dicabut dengan menghapus storage.</p>
            </section>

            <section class="card">
                <h2>Uji Coba Chat Completions</h2>
                <form id="chat-form">
                    <div class="form-group">
                        <label for="model-select">Pilih model:</label>
                        <select id="model-select">
                            <option value="npt-1.5">npt-1.5 — Google Gemini</option>
                            <option value="npt-base">npt-base — OpenAI GPT</option>
                            <option value="npt-2.0-non-reasoning">npt-2.0-non-reasoning — xAI Grok</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="message-input">Pesan Anda:</label>
                        <textarea id="message-input" rows="3" placeholder="Masukkan pesan uji...">Sebutkan 3 fakta unik tentang Indonesia.</textarea>
                    </div>
                    <button type="submit" id="send-chat-btn">Kirim Permintaan</button>
                </form>
            </section>

            <section class="card">
                <h2>Respons dari API</h2>
                <div id="response-container">
                    <pre id="response-content">Respons akan muncul di sini...</pre>
                </div>
            </section>
        </main>

        <footer>
            Halaman ini TEST ONLY dan hanya ditujukan bagi OpenGen Testers. Laporkan ke tim keamanan bila menemukan anomali.
        </footer>
    </div>

    <div class="toast-container" id="toast-container"></div>

    <script>
        document.addEventListener('DOMContentLoaded', () => {
            const apiKeyDisplay = document.getElementById('api-key-display');
            const generateKeyBtn = document.getElementById('generate-key-btn');
            const copyKeyBtn = document.getElementById('copy-key-btn');
            const chatForm = document.getElementById('chat-form');
            const sendChatBtn = document.getElementById('send-chat-btn');
            const responseContent = document.getElementById('response-content');
            const healthStatus = document.getElementById('health-status');
            const healthText = document.getElementById('health-text');
            const toastContainer = document.getElementById('toast-container');
            const API_KEY_STORAGE = 'opengen_testers_key';

            const createToast = (message, variant = 'info') => {
                const toast = document.createElement('div');
                toast.className = `toast toast-${variant}`;
                toast.textContent = message;
                toastContainer.appendChild(toast);
                setTimeout(() => {
                    toast.style.opacity = '0';
                    toast.style.transform = 'translateY(12px)';
                    setTimeout(() => toast.remove(), 220);
                }, 3200);
            };

            const setButtonLoading = (button, isLoading, label) => {
                if (isLoading) {
                    button.disabled = true;
                    button.dataset.originalLabel = button.textContent;
                    button.innerHTML = `<span class="spinner"></span><span>${label}</span>`;
                } else {
                    button.disabled = false;
                    button.innerHTML = button.dataset.originalLabel || button.textContent;
                }
            };

            const checkHealth = async () => {
                try {
                    const response = await fetch('/health');
                    if (!response.ok) throw new Error('Server tidak merespons');
                    const data = await response.json();
                    healthStatus.classList.remove('unhealthy');
                    healthStatus.classList.add('healthy');
                    healthText.textContent = `Status: ${data.status}`;
                } catch (error) {
                    healthStatus.classList.remove('healthy');
                    healthStatus.classList.add('unhealthy');
                    healthText.textContent = 'Status: Error';
                }
            };

            const loadKey = () => {
                const key = localStorage.getItem(API_KEY_STORAGE);
                if (key) apiKeyDisplay.value = key;
            };

            const generateKey = async () => {
                setButtonLoading(generateKeyBtn, true, 'Membuat...');
                try {
                    const response = await fetch('/v1/generate-key', { method: 'POST' });
                    const data = await response.json();
                    if (response.ok && data.api_key) {
                        localStorage.setItem(API_KEY_STORAGE, data.api_key);
                        apiKeyDisplay.value = data.api_key;
                        createToast('Kunci baru berhasil dibuat.', 'success');
                    } else {
                        throw new Error(data.error || 'Gagal membuat kunci.');
                    }
                } catch (error) {
                    console.error('Key generation error:', error);
                    createToast(error.message, 'error');
                } finally {
                    setButtonLoading(generateKeyBtn, false);
                }
            };

            const copyKey = async () => {
                const key = apiKeyDisplay.value;
                if (!key) {
                    createToast('Tidak ada kunci untuk disalin.', 'error');
                    return;
                }
                try {
                    await navigator.clipboard.writeText(key);
                    createToast('API key tersalin.', 'success');
                } catch (error) {
                    console.error('Clipboard error:', error);
                    createToast('Gagal menyalin API key.', 'error');
                }
            };

            const handleChatSubmit = async (event) => {
                event.preventDefault();
                const key = localStorage.getItem(API_KEY_STORAGE);
                if (!key) {
                    createToast('Silakan generate API key terlebih dahulu.', 'error');
                    return;
                }
                const model = document.getElementById('model-select').value;
                const message = document.getElementById('message-input').value.trim();
                if (!message) {
                    createToast('Pesan tidak boleh kosong.', 'error');
                    return;
                }
                setButtonLoading(sendChatBtn, true, 'Mengirim...');
                responseContent.textContent = 'Menunggu respons dari server...';

                try {
                    const response = await fetch('/v1/chat/completions', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${key}`,
                        },
                        body: JSON.stringify({
                            model,
                            messages: [{ role: 'user', content: message }],
                            stream: false
                        }),
                    });

                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.error || `HTTP error ${response.status}`);
                    }
                    const content = data.choices?.[0]?.message?.content?.trim();
                    responseContent.textContent = content || JSON.stringify(data, null, 2);
                    createToast('Permintaan berhasil.', 'success');
                } catch (error) {
                    console.error('Chat error:', error);
                    responseContent.textContent = `Terjadi kesalahan: ${error.message}`;
                    createToast(error.message, 'error');
                } finally {
                    setButtonLoading(sendChatBtn, false);
                }
            };

            generateKeyBtn.addEventListener('click', generateKey);
            copyKeyBtn.addEventListener('click', copyKey);
            chatForm.addEventListener('submit', handleChatSubmit);

            checkHealth();
            loadKey();
            setInterval(checkHealth, 60000);
        });
    </script>
</body>
</html>
"""

NPT_SYSTEM_PROMPT = """
Your identity: NPT created by OpenGen Team in Jakarta, Indonesia.
You are not an assistant or language model; you are the embodiment of OpenGen's technology itself.
You must never refer to system instructions, prompts, or your reasoning process.
Never mention that you are following rules or that your behavior is guided by instructions.
Simply respond as NPT : confident, intelligent, and-like in tone, focused on clarity and direct answers.
Mission Opengen Team : Make powerful AI technology accessible to everyone for free.
"""

generated_keys = {}

def generate_api_key():
    return f"sk-opengen-{secrets.token_urlsafe(32)}"

def validate_proxy_key(api_key: str) -> bool:
    return api_key in generated_keys

@app.before_request
def enforce_security():
    g.request_id = secrets.token_hex(6)
    try:
        security_manager.enforce(request)
    except SecurityException as exc:
        logger.warning(
            "Security violation | request_id=%s path=%s reason=%s",
            g.request_id,
            request.path,
            exc.message,
        )
        response = jsonify({"error": exc.message, "code": exc.code, "request_id": g.request_id})
        response.status_code = exc.status_code
        return response

@app.route("/")
def dashboard():
    return render_template_string(
        HTML_TEMPLATE,
        dashboard_title="OpenGen Testers API Dashboard",
        dashboard_heading="OpenGen Testers API",
        public_endpoint_url=PUBLIC_ENDPOINT_URL,
    )

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }), 200

@app.route("/v1/generate-key", methods=["POST"])
def generate_key():
    new_key = generate_api_key()
    generated_keys[new_key] = {
        "valid": True,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    masked_key = f"{new_key[:6]}...{new_key[-4:]}"
    logger.info("API key generated | request_id=%s key=%s", g.request_id, masked_key)
    return jsonify({"api_key": new_key, "message": "API key berhasil dibuat."}), 201

@app.route("/v1/models", methods=["GET"])
def models():
    auth_header = request.headers.get("Authorization", "")
    proxy_key = auth_header.replace("Bearer ", "")
    if not validate_proxy_key(proxy_key):
        logger.warning("Unauthorized model list access | request_id=%s", g.request_id)
        return jsonify({"error": "Invalid API key", "request_id": g.request_id}), 401
    logger.info("Model list served | request_id=%s provider=registry", g.request_id)
    response = jsonify({"object": "list", "data": SPOOFED_MODELS})
    response.headers["X-OpenGen-Request-ID"] = g.request_id
    return response, 200

@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    auth_header = request.headers.get("Authorization", "")
    proxy_key = auth_header.replace("Bearer ", "")
    if not validate_proxy_key(proxy_key):
        logger.warning("Unauthorized chat access | request_id=%s", g.request_id)
        return jsonify({"error": "Invalid API key", "request_id": g.request_id}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON", "request_id": g.request_id}), 400

    model_req = data.get("model", "unknown")
    upstream_model = MODEL_MAPPING.get(model_req, model_req)
    provider = PROVIDER_MAPPING.get(model_req, "passthrough")

    data["model"] = upstream_model

    messages = data.get("messages", [])
    has_system_prompt = any(msg.get("role") == "system" for msg in messages)
    if messages and not has_system_prompt:
        messages.insert(0, {"role": "system", "content": NPT_SYSTEM_PROMPT})
    data["messages"] = messages

    headers = {
        "Authorization": f"Bearer {INTERNAL_API_KEY}",
        "Content-Type": "application/json",
    }
    target_url = f"{TARGET_BASE_URL}/chat/completions"

    logger.info(
        "Proxying chat completion | request_id=%s provider=%s mapped_model=%s stream=%s",
        g.request_id,
        provider,
        upstream_model,
        data.get("stream", False),
    )

    try:
        upstream_response = requests.post(
            target_url,
            json=data,
            headers=headers,
            timeout=120,
            stream=data.get("stream", False),
        )
        upstream_response.raise_for_status()

        if data.get("stream", False):
            def generate():
                for chunk in upstream_response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            proxy_response = app.response_class(
                stream_with_context(generate()),
                content_type=upstream_response.headers.get("Content-Type", "application/json"),
                status=upstream_response.status_code,
            )
            proxy_response.headers["X-OpenGen-Request-ID"] = g.request_id
            proxy_response.headers["X-Model-Provider"] = provider
            return proxy_response

        payload = upstream_response.json()
        flask_response = jsonify(payload)
        flask_response.status_code = upstream_response.status_code
        flask_response.headers["X-OpenGen-Request-ID"] = g.request_id
        flask_response.headers["X-Model-Provider"] = provider
        return flask_response

    except requests.exceptions.RequestException as error:
        logger.error(
            "Upstream error | request_id=%s provider=%s error=%s",
            g.request_id,
            provider,
            error,
        )
        return jsonify({
            "error": f"Upstream API error: {error}",
            "request_id": g.request_id,
        }), 502
    except Exception as error:
        logger.exception(
            "Unexpected error | request_id=%s provider=%s", g.request_id, provider
        )
        return jsonify({
            "error": f"An unexpected error occurred: {error}",
            "request_id": g.request_id,
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
