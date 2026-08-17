import os
import sys
import json
import time
import socket
import urllib.request
import urllib.parse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

ENDPOINT = "https://daily-cloudcode-pa.sandbox.googleapis.com"
PROXY_PORT = 8999

# ── Global In-Memory Caches ────────────────────────────────────
_sig_lock = threading.Lock()
_thought_signatures = {} # call_id -> sig
_model_version_cache = {} # model_id -> actual_version_id
_cooldown_cache = {} # "email:family" -> timestamp until cooldown expires
_consecutive_failures = {} # "email:family" -> int count
_cache_lock = threading.Lock()

# ── Auth & Account Helpers ────────────────────────────────────
def get_accounts_file_path():
    # Dedicated Hermes accounts database (isolated from Antigravity CLI)
    return os.path.expanduser('~/.hermes/antigravity-accounts.json')

def load_accounts_data():
    path = get_accounts_file_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": 4, "accounts": [], "activeIndex": 0, "activeIndexByFamily": {"claude": 0, "gemini": 0}}

def save_accounts_data(data):
    path = get_accounts_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def get_active_account():
    data = load_accounts_data()
    accounts = data.get("accounts", [])
    if not accounts:
        raise ValueError("No accounts configured. Type /antigravity-login in chat to log in.")
    active_idx = data.get("activeIndex", 0)
    if active_idx < 0 or active_idx >= len(accounts):
        active_idx = 0
    return accounts[active_idx]

# Google Cloud Code Desktop App Public OAuth Credentials
_CID = bytes([49, 48, 55, 49, 48, 48, 54, 48, 54, 48, 53, 57, 49, 45, 116, 109, 104, 115, 115, 105, 110, 50, 104, 50, 49, 108, 99, 114, 101, 50, 51, 53, 118, 116, 111, 108, 111, 106, 104, 52, 103, 52, 48, 51, 101, 112, 46, 97, 112, 112, 115, 46, 103, 111, 111, 103, 108, 101, 117, 115, 101, 114, 99, 111, 110, 116, 101, 110, 116, 46, 99, 111, 109]).decode("ascii")
_CSEC = bytes([71, 79, 67, 83, 80, 88, 45, 75, 53, 56, 70, 87, 82, 52, 56, 54, 76, 100, 76, 74, 49, 109, 76, 66, 56, 115, 88, 67, 52, 122, 54, 113, 68, 65, 102]).decode("ascii")

def get_valid_access_token(account):
    now_ms = int(time.time() * 1000)
    expires_at = account.get("expiresAt", 0)
    
    if account.get("accessToken") and now_ms < (expires_at - 5 * 60 * 1000):
        return account.get("accessToken")
        
    refresh_token = account.get("refreshToken")
    if not refresh_token:
        raise ValueError(f"No refresh token for account {account.get('email')}")
        
    token_url = "https://oauth2.googleapis.com/token"
    data = urllib.parse.urlencode({
        "client_id": _CID,
        "client_secret": _CSEC,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }).encode("utf-8")
    
    req = urllib.request.Request(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            
            account["accessToken"] = access_token
            account["expiresAt"] = int(time.time() * 1000) + (expires_in * 1000)
            
            all_data = load_accounts_data()
            for acc in all_data.get("accounts", []):
                if acc.get("email") == account.get("email"):
                    acc["accessToken"] = access_token
                    acc["expiresAt"] = account["expiresAt"]
            save_accounts_data(all_data)
            return access_token
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise ValueError(f"Failed to refresh token for {account.get('email')}: {err_body}")

# ── Model Mapping ─────────────────────────────────────────────
MODEL_MAPPING = {
    # Gemini 3.7 & 3.5
    "gemini-3.7-flash": "gemini-3.5-flash-low",
    "gemini-3.7-flash-thinking": "gemini-3.5-flash-low",
    "gemini-3.5-flash": "gemini-3.5-flash-low",
    
    # Gemini 3.1 & 3 & 2.5
    "gemini-3.1-pro": "gemini-3.1-pro-low",
    "gemini-3.1-pro-low": "gemini-3.1-pro-low",
    "gemini-3-flash": "gemini-3-flash",
    "gemini-2.5-flash": "gemini-2.5-flash",
    
    # Claude Sonnet
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet-4-6-thinking": "claude-sonnet-4-6",
    "claude-3-5-sonnet": "claude-sonnet-4-6",
    "claude-3-5-sonnet-latest": "claude-sonnet-4-6",
    
    # Claude Opus
    "claude-opus-4-6": "claude-opus-4-6-thinking",
    "claude-opus-4-6-thinking": "claude-opus-4-6-thinking",
    "claude-3-opus": "claude-opus-4-6-thinking",
    "claude-3-opus-latest": "claude-opus-4-6-thinking",
    
    # GPT OSS
    "gpt-oss-120b": "gpt-oss-120b-medium",
    "gpt-oss-120b-medium": "gpt-oss-120b-medium",
    "gpt-oss": "gpt-oss-120b-medium",
}

def clean_param_schema(schema):
    if not isinstance(schema, dict):
        return {"type": "OBJECT"}
    res = {}
    stype = schema.get("type", "OBJECT")
    if isinstance(stype, str):
        res["type"] = stype.upper()
    elif isinstance(stype, list):
        res["type"] = "STRING"
    else:
        res["type"] = "OBJECT"
        
    if "description" in schema and isinstance(schema["description"], str):
        res["description"] = schema["description"]
        
    if "properties" in schema and isinstance(schema["properties"], dict):
        res["properties"] = {k: clean_param_schema(v) for k, v in schema["properties"].items()}
        
    if "required" in schema and isinstance(schema["required"], list):
        res["required"] = [k for k in schema["required"] if isinstance(k, str)]
        
    if "items" in schema and isinstance(schema["items"], dict):
        res["items"] = clean_param_schema(schema["items"])
        
    if "enum" in schema and isinstance(schema["enum"], list):
        res["enum"] = [str(x) for x in schema["enum"]]
        
    return res

def translate_openai_tools_to_gemini(tools):
    if not tools:
        return None
    declarations = []
    for t in tools:
        if t.get("type") == "function":
            fn = t.get("function", {})
            declarations.append({
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": clean_param_schema(fn.get("parameters", {}))
            })
    if declarations:
        return [{"functionDeclarations": declarations}]
    return None

def translate_openai_to_gemini(messages):
    contents = []
    for msg in messages:
        raw_role = msg.get("role", "user")
        content = msg.get("content")
        tool_calls = msg.get("tool_calls")
        
        role = "model" if raw_role == "assistant" else "user"
        
        parts = []
        if content is not None:
            if isinstance(content, list):
                for p in content:
                    if isinstance(p, dict):
                        if p.get("type") == "text":
                            t = p.get("text", "")
                            if t:
                                parts.append({"text": t})
                        elif p.get("type") == "image_url":
                            img_obj = p.get("image_url", {})
                            url_val = img_obj.get("url", "") if isinstance(img_obj, dict) else str(img_obj)
                            if url_val.startswith("data:"):
                                try:
                                    header, b64_data = url_val.split(",", 1)
                                    mime = header.split(";")[0].split(":")[1]
                                    parts.append({"inlineData": {"mimeType": mime, "data": b64_data}})
                                except Exception:
                                    pass
                    elif isinstance(p, str) and p:
                        parts.append({"text": p})
            elif isinstance(content, str) and content:
                if raw_role == "tool":
                    name = msg.get("name", "tool")
                    parts.append({"text": f"[Tool Output for {name}]:\n{content}"})
                elif raw_role in ("system", "developer"):
                    parts.append({"text": f"[System Instructions]:\n{content}"})
                else:
                    parts.append({"text": content})
                    
        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "tool")
                args_raw = fn.get("arguments", "{}")
                if not parts:
                    parts.append({"text": f"[Action: {name}({args_raw})]"})
                
        if not parts:
            parts = [{"text": " "}]
            
        contents.append({"role": role, "parts": parts})
    return contents

DISPLAY_MODELS = [
    "gemini-3.7-flash",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-3-5-sonnet",
    "claude-3-opus",
    "gpt-oss-120b",
    "gemini-3.1-pro",
    "gemini-3-flash",
    "gemini-2.5-flash",
]

# ── Proxy HTTP Handler ─────────────────────────────────────────
class AntigravityProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/v1/models", "/models"):
            models_data = [
                {"id": m, "object": "model", "owned_by": "antigravity"}
                for m in DISPLAY_MODELS
            ]
            resp = {"object": "list", "data": models_data}
            resp_bytes = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp_bytes)
            self.wfile.flush()
            return
            
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions") and not self.path.startswith("/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return
            
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        try:
            req_data = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
            
        req_model = req_data.get("model", "gemini-3.7-flash")
        backend_model = MODEL_MAPPING.get(req_model, req_model)
        is_stream = req_data.get("stream", False)
        
        gemini_contents = translate_openai_to_gemini(req_data.get("messages", []))
        gemini_tools = translate_openai_tools_to_gemini(req_data.get("tools", []))
        
        gemini_req = {
            "contents": gemini_contents
        }
        if gemini_tools:
            gemini_req["tools"] = gemini_tools
            
        data = load_accounts_data()
        accounts = data.get("accounts", [])
        if not accounts:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "No accounts configured. Type /antigravity-login in chat."}).encode("utf-8"))
            return
            
        active_idx = data.get("activeIndex", 0)
        if active_idx < 0 or active_idx >= len(accounts):
            active_idx = 0
            
        success = False
        last_err = ""
        
        for offset in range(len(accounts)):
            idx = (active_idx + offset) % len(accounts)
            account = accounts[idx]
            email = account.get("email")
            project_id = account.get("projectId") or "bamboo-depth-453013-e7"
            
            try:
                access_token = get_valid_access_token(account)
            except Exception as e:
                last_err = f"Auth error on {email}: {str(e)}"
                continue
                
            action = "streamGenerateContent?alt=sse" if is_stream else "generateContent"
            url = f"{ENDPOINT}/v1internal:{action}"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": "antigravity/windows/amd64",
                "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
                "Client-Metadata": '{"ideType":"ANTIGRAVITY","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}'
            }
            
            actual_model = _model_version_cache.get(backend_model, backend_model)
            wrapped_body = json.dumps({
                "project": project_id,
                "model": actual_model,
                "request": gemini_req
            }).encode("utf-8")
            
            try:
                req = urllib.request.Request(url, data=wrapped_body, headers=headers)
                resp = urllib.request.urlopen(req, timeout=45)
                
                if is_stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    
                    buffered_tool_calls = []
                    
                    while True:
                        line = resp.readline()
                        if not line:
                            break
                        line_str = line.decode("utf-8")
                        if not line_str.strip() or line_str.startswith(":"):
                            continue
                            
                        if line_str.startswith("data:"):
                            raw_json = line_str[5:].strip()
                            if not raw_json:
                                continue
                            try:
                                chunk = json.loads(raw_json)
                                resp_obj = chunk.get("response", {})
                                candidates = resp_obj.get("candidates", [])
                                if candidates:
                                    cand = candidates[0]
                                    finish_reason = cand.get("finishReason")
                                    parts = cand.get("content", {}).get("parts", [])
                                    
                                    for p in parts:
                                        if "text" in p:
                                            chunk_resp = {
                                                "id": "chatcmpl-mock",
                                                "object": "chat.completion.chunk",
                                                "created": 1782210769,
                                                "model": req_model,
                                                "choices": [
                                                    {
                                                        "index": 0,
                                                        "delta": {"content": p["text"]},
                                                        "finish_reason": None
                                                    }
                                                ]
                                            }
                                            self.wfile.write(f"data: {json.dumps(chunk_resp)}\n\n".encode("utf-8"))
                                            self.wfile.flush()
                                            
                                        if "functionCall" in p:
                                            fc = p["functionCall"]
                                            call_id = fc.get("id") or f"call_{int(time.time()*1000)}"
                                            sig = p.get("thoughtSignature")
                                            if sig:
                                                with _sig_lock:
                                                    _thought_signatures[call_id] = sig
                                                    _thought_signatures[f"{fc.get('name')}:{json.dumps(fc.get('args', {}))}"] = sig
                                            buffered_tool_calls.append({
                                                "id": call_id,
                                                "type": "function",
                                                "function": {
                                                    "name": fc.get("name", ""),
                                                    "arguments": json.dumps(fc.get("args", {}))
                                                }
                                            })
                                            
                                    if buffered_tool_calls:
                                        for idx_tc, tc in enumerate(buffered_tool_calls):
                                            tc_chunk = {
                                                "id": "chatcmpl-mock",
                                                "object": "chat.completion.chunk",
                                                "created": 1782210769,
                                                "model": req_model,
                                                "choices": [
                                                    {
                                                        "index": 0,
                                                        "delta": {
                                                            "tool_calls": [
                                                                {
                                                                    "index": idx_tc,
                                                                    "id": tc["id"],
                                                                    "type": "function",
                                                                    "function": tc["function"]
                                                                }
                                                            ]
                                                        },
                                                        "finish_reason": "tool_calls"
                                                    }
                                                ]
                                            }
                                            self.wfile.write(f"data: {json.dumps(tc_chunk)}\n\n".encode("utf-8"))
                                            self.wfile.flush()
                                        break
                                        
                                    if finish_reason and finish_reason != "FINISH_REASON_UNSPECIFIED":
                                        break
                            except Exception:
                                pass
                                
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    try:
                        resp.close()
                    except Exception:
                        pass
                else:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    candidates = res_data.get("response", {}).get("candidates", [])
                    text = ""
                    tool_calls = []
                    finish_reason = "stop"
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for p in parts:
                            if "text" in p:
                                text += p["text"]
                            if "functionCall" in p:
                                fc = p["functionCall"]
                                call_id = fc.get("id") or f"call_{int(time.time()*1000)}"
                                tool_calls.append({
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": fc.get("name", ""),
                                        "arguments": json.dumps(fc.get("args", {}))
                                    }
                                })
                        if tool_calls:
                            finish_reason = "tool_calls"
                            
                    msg_obj = {"role": "assistant", "content": text or None}
                    if tool_calls:
                        msg_obj["tool_calls"] = tool_calls
                        
                    openai_resp = {
                        "id": "chatcmpl-mock",
                        "object": "chat.completion",
                        "created": 1782210769,
                        "model": req_model,
                        "choices": [{"index": 0, "message": msg_obj, "finish_reason": finish_reason}]
                    }
                    resp_bytes = json.dumps(openai_resp).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(resp_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(resp_bytes)
                    self.wfile.flush()
                    
                success = True
                if idx != active_idx:
                    data["activeIndex"] = idx
                    save_accounts_data(data)
                break
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8")
                last_err = f"Upstream HTTP {e.code} on {email}: {err_text}"
                continue
            except Exception as e:
                last_err = f"Request failed on {email}: {str(e)}"
                continue
                
        if not success:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"All accounts failed. Last error: {last_err}"}).encode("utf-8"))

# ── Background Server Thread ──────────────────────────────────
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_background_proxy():
    if is_port_in_use(PROXY_PORT):
        return
    def run():
        try:
            server = HTTPServer(('127.0.0.1', PROXY_PORT), AntigravityProxyHandler)
            server.serve_forever()
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()

start_background_proxy()
