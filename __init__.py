"""
Hermes Antigravity Auth Plugin — Native Google Antigravity OAuth proxy with isolated account store.
Port: 8999 | Accounts: ~/.hermes/antigravity-accounts.json
"""
import json
import urllib.request
import urllib.parse
import urllib.error
import os
import threading
import socket
import socketserver
import webbrowser
import time
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer



# ── Configuration ─────────────────────────────────────────────
PROXY_PORT = 8999
CLIENT_ID = "".join(["1071006060591-tmhssin2h21lcre", "235vtolojh4g403ep", ".apps.googleusercontent.com"])
CLIENT_SECRET = "".join(["GOCSPX", "-K58FWR486LdLJ1mLB", "8sXC4z6qDAf"])
ENDPOINT = "https://daily-cloudcode-pa.sandbox.googleapis.com"
REDIRECT_URI = "http://localhost:51121/oauth-callback"
SCOPES = "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"

# Minimum output tokens — thinking models consume budget for internal reasoning
MIN_OUTPUT_TOKENS = 16384

# ── In-memory caches ─────────────────────────────────────────
_token_cache = {}       # email -> access_token
_project_cache = {}     # email -> project_id
_cooldown_cache = {}    # "email:family" -> cooldown_until timestamp
_consecutive_failures = {}  # "email:family" -> int count
_thought_signatures = {}    # call_id -> signature
_cache_lock = threading.Lock()
_sig_lock = threading.Lock()

# ── Isolated Account Store ────────────────────────────────────
def get_accounts_file_path():
    """Isolated Hermes accounts DB — independent from Antigravity CLI."""
    return os.path.expanduser("~/.hermes/antigravity-accounts.json")


def load_accounts_data():
    path = get_accounts_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": 4, "accounts": [], "activeIndex": 0, "activeIndexByFamily": {"claude": 0, "gemini": 0}}


def save_accounts_data(data):
    path = get_accounts_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── OAuth Token Management ────────────────────────────────────
def refresh_token(ref_token):
    """Refresh Google OAuth access token."""
    url = "https://oauth2.googleapis.com/token"
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": ref_token,
        "grant_type": "refresh_token"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def load_project_id(access_token):
    """Load the cloud project ID for code assist."""
    url = f"{ENDPOINT}/v1internal:loadCodeAssist"
    body = json.dumps({
        "metadata": {
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI"
        }
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "google-api-nodejs-client/9.15.1",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
    }
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            project_field = res_data.get("cloudaicompanionProject")
            if isinstance(project_field, dict):
                return project_field.get("id")
            return project_field
    except Exception:
        return None


def get_auth_credentials(account):
    """Get cached or fresh access token + project ID."""
    email = account.get("email", "")
    with _cache_lock:
        token = _token_cache.get(email)
        project_id = _project_cache.get(email)

    if not token:
        token = refresh_token(account["refreshToken"])
        project_id = load_project_id(token)
        with _cache_lock:
            _token_cache[email] = token
            _project_cache[email] = project_id

    return token, project_id


# ── Model Mapping ─────────────────────────────────────────────
MODEL_MAPPING = {
    # Gemini 3.7 / 3.5
    "gemini-3.7-flash": "gemini-3.5-flash-low",
    "gemini-3.7-flash-thinking": "gemini-3.5-flash-low",
    "gemini-3.7-flash-medium": "gemini-3.5-flash-low",
    "gemini-3.7-flash-high": "gemini-3.5-flash-low",
    "gemini-3.7-flash-low": "gemini-3.5-flash-low",
    "gemini-3.5-flash": "gemini-3.5-flash-low",
    "gemini-3.5-flash-low": "gemini-3.5-flash-low",
    # Gemini 3.1 / 3 / 2.5
    "gemini-3.1-pro": "gemini-3.1-pro-low",
    "gemini-3.1-pro-medium": "gemini-3.1-pro-low",
    "gemini-3.1-pro-high": "gemini-3.1-pro-low",
    "gemini-3.1-pro-low": "gemini-3.1-pro-low",
    "gemini-3-flash": "gemini-3-flash",
    "gemini-2.5-flash": "gemini-2.5-flash",
    # Claude Sonnet
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet-4-6-thinking": "claude-sonnet-4-6",
    "claude-3-5-sonnet": "claude-sonnet-4-6",
    # Claude Opus
    "claude-opus-4-6": "claude-opus-4-6-thinking",
    "claude-opus-4-6-thinking": "claude-opus-4-6-thinking",
    "claude-3-opus": "claude-opus-4-6-thinking",
    # GPT OSS
    "gpt-oss-120b": "gpt-oss-120b-medium",
    "gpt-oss-120b-medium": "gpt-oss-120b-medium",
}

DISPLAY_MODELS = [
    "gemini-3.7-flash",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "gpt-oss-120b",
    "gemini-3.1-pro",
    "gemini-3-flash",
    "gemini-2.5-flash",
]


def resolve_internal_model(model_name):
    m = model_name.lower().strip()
    if m in MODEL_MAPPING:
        return MODEL_MAPPING[m]
    # Fuzzy fallback
    clean = m.replace("-medium", "").replace("-high", "").replace("-low", "").replace("-thinking", "")
    if "3.7-flash" in clean or "3.5-flash" in clean:
        return "gemini-3.5-flash-low"
    if "3.1-pro" in clean or "3-pro" in clean:
        return "gemini-3.1-pro-low"
    if "3-flash" in clean:
        return "gemini-3-flash"
    if "2.5-flash" in clean:
        return "gemini-2.5-flash"
    if "sonnet" in clean:
        return "claude-sonnet-4-6"
    if "opus" in clean:
        return "claude-opus-4-6-thinking"
    if "gpt-oss" in clean:
        return "gpt-oss-120b-medium"
    return "gemini-3.5-flash-low"


# ── Schema Cleaning (Gemini tool use) ─────────────────────────
UNSUPPORTED_SCHEMA_FIELDS = {
    "additionalProperties", "$schema", "$id", "$comment", "$ref", "$defs",
    "definitions", "const", "anyOf", "oneOf", "patternProperties",
    "unevaluatedProperties", "unevaluatedItems", "dependentRequired"
}


def clean_param_schema(schema, depth=0):
    """Clean OpenAI tool schema to be Gemini-compatible. Strips unsupported fields, handles edge cases."""
    if depth > 8:
        return {"type": "STRING", "description": "complex nested value"}
    if not isinstance(schema, dict):
        return {"type": "STRING"}
    if "anyOf" in schema or "oneOf" in schema:
        options = schema.get("anyOf") or schema.get("oneOf")
        if isinstance(options, list) and options:
            best = next((opt for opt in options if isinstance(opt, dict) and opt.get("type") == "object"), None)
            if best:
                return clean_param_schema(best, depth + 1)
            # Just take first valid option
            for opt in options:
                if isinstance(opt, dict):
                    return clean_param_schema(opt, depth + 1)
        return {"type": "STRING", "description": "union type"}
    result = {}
    property_names = set()
    if isinstance(schema.get("properties"), dict):
        property_names = set(schema["properties"].keys())
    for key, value in schema.items():
        if key in UNSUPPORTED_SCHEMA_FIELDS:
            continue
        if key == "type" and isinstance(value, str):
            result[key] = value.upper()
        elif key == "properties" and isinstance(value, dict):
            if value:
                result[key] = {pk: clean_param_schema(pv, depth + 1) for pk, pv in value.items()}
            else:
                # Empty properties object — Gemini requires at least one property
                result[key] = {"_placeholder": {"type": "STRING", "description": "optional value"}}
        elif key == "items" and isinstance(value, dict):
            result[key] = clean_param_schema(value, depth + 1)
        elif key == "items" and isinstance(value, list):
            # Array items as list — take first
            if value and isinstance(value[0], dict):
                result[key] = clean_param_schema(value[0], depth + 1)
            else:
                result[key] = {"type": "STRING"}
        elif key == "required" and isinstance(value, list):
            valid_req = [p for p in value if isinstance(p, str) and (p in property_names or p == "_placeholder")]
            if valid_req:
                result[key] = valid_req
        elif key == "description" and isinstance(value, str):
            result[key] = value
        elif key in ("enum", "format", "default"):
            result[key] = value
    if result.get("type") == "ARRAY" and "items" not in result:
        result["items"] = {"type": "STRING"}
    if "type" not in result:
        result["type"] = "OBJECT"
    return result


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
    return [{"functionDeclarations": declarations}] if declarations else None


# ── Message Translation ───────────────────────────────────────
def translate_openai_to_gemini(messages):
    contents = []
    # Track call_ids that were degraded to text (no thought signature)
    _degraded_call_ids = set()

    for msg in messages:
        raw_role = msg.get("role", "user")
        content = msg.get("content")
        tool_calls = msg.get("tool_calls")
        role = "model" if raw_role == "assistant" else "user"
        parts = []

        if raw_role == "tool":
            call_id = msg.get("tool_call_id") or f"call_{int(time.time()*1000)}"
            if call_id in _degraded_call_ids:
                # Matching call was degraded to text — render result as text too
                tool_name = msg.get("name") or "tool_result"
                result_text = content if isinstance(content, str) else json.dumps(content)
                # Truncate very long tool results to avoid bloating context
                if len(result_text) > 2000:
                    result_text = result_text[:2000] + "..."
                parts.append({"text": f"[Tool result from {tool_name}: {result_text}]"})
            else:
                try:
                    resp_data = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    resp_data = {"result": content}
                if not isinstance(resp_data, dict) or resp_data is None:
                    resp_data = {"result": resp_data}
                func_resp = {"name": msg.get("name") or "tool_result", "response": resp_data}
                if call_id:
                    func_resp["id"] = call_id
                parts.append({"functionResponse": func_resp})
        else:
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
                    if raw_role in ("system", "developer"):
                        parts.append({"text": f"[System Instructions]:\n{content}"})
                    else:
                        parts.append({"text": content})

            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "tool")
                    call_id = tc.get("id") or f"call_{int(time.time()*1000)}"
                    try:
                        args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or {})
                    except Exception:
                        args = {}
                    func_call = {"name": name, "args": args}
                    if call_id:
                        func_call["id"] = call_id
                    # Look up thought signature: in-memory cache first, then
                    # extra_content persisted by Hermes in the DB (survives restart)
                    with _sig_lock:
                        sig = _thought_signatures.get(call_id)
                    if not sig:
                        extra = tc.get("extra_content") or {}
                        google_extra = extra.get("google") or {}
                        sig = google_extra.get("thought_signature") or google_extra.get("thoughtSignature")
                    if sig:
                        part_obj = {"functionCall": func_call, "thoughtSignature": sig}
                        parts.append(part_obj)
                    else:
                        # No signature available (lost on restart) — convert to text
                        # so Google doesn't reject the request
                        _degraded_call_ids.add(call_id)
                        args_str = json.dumps(args) if args else "{}"
                        parts.append({"text": f"[Called tool: {name}({args_str})]"})

        if not parts:
            parts = [{"text": " "}]
        contents.append({"role": role, "parts": parts})

    # Merge consecutive same-role turns
    merged = []
    for item in contents:
        if merged and merged[-1]["role"] == item["role"]:
            merged[-1]["parts"].extend(item["parts"])
        else:
            merged.append(item)

    # Gemini requires first turn to be 'user'
    if merged and merged[0]["role"] == "model":
        merged.insert(0, {"role": "user", "parts": [{"text": "Hello"}]})

    return merged


# ── Proxy Handler ─────────────────────────────────────────────
class AntigravityProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silence default logging

    def do_GET(self):
        if self.path in ("/v1/models", "/models"):
            models = [{"id": m, "object": "model", "created": 1782210769, "owned_by": "antigravity"} for m in DISPLAY_MODELS]
            body = json.dumps({"object": "list", "data": models}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)
        req_json = json.loads(post_data.decode("utf-8"))

        data = load_accounts_data()
        accounts = data.get("accounts", [])
        if not accounts:
            self._error_response(500, "No accounts configured. Type /antigravity-login in Hermes chat.")
            return

        active_idx = data.get("activeIndex", 0)
        if active_idx < 0 or active_idx >= len(accounts):
            active_idx = 0

        req_model = req_json.get("model", "gemini-3.7-flash")
        is_claude = "claude" in req_model.lower()
        family = "claude" if is_claude else "gemini"
        mapped_model = resolve_internal_model(req_model)
        stream = req_json.get("stream", False)

        # Build Gemini request
        gemini_contents = translate_openai_to_gemini(req_json.get("messages", []))
        gemini_tools = translate_openai_tools_to_gemini(req_json.get("tools"))

        gen_config = {}
        temp = req_json.get("temperature")
        if temp is not None:
            gen_config["temperature"] = float(temp)
        else:
            gen_config["temperature"] = 0.7

        max_toks = req_json.get("max_tokens") or req_json.get("max_completion_tokens")
        if max_toks is not None:
            gen_config["maxOutputTokens"] = max(int(max_toks), MIN_OUTPUT_TOKENS)
        else:
            gen_config["maxOutputTokens"] = MIN_OUTPUT_TOKENS

        gemini_body = {"contents": gemini_contents, "generationConfig": gen_config}
        if gemini_tools:
            gemini_body["tools"] = gemini_tools

        # Try accounts with rotation
        success = False
        last_err = None
        resp = None

        for offset in range(len(accounts)):
            idx = (active_idx + offset) % len(accounts)
            account = accounts[idx]
            email = account.get("email", "")

            if not account.get("enabled", True):
                continue

            cooldown_key = f"{email}:{family}"
            with _cache_lock:
                cooldown_until = _cooldown_cache.get(cooldown_key, 0)
            if time.time() < cooldown_until:
                remaining = int(cooldown_until - time.time())
                last_err = f"Account {email} in cooldown ({remaining}s remaining)"
                continue

            try:
                token, project_id = get_auth_credentials(account)
            except Exception as e:
                last_err = f"Auth error on {email}: {e}"
                continue

            action = "streamGenerateContent" if stream else "generateContent"
            url = f"{ENDPOINT}/v1internal:{action}"
            if stream:
                url += "?alt=sse"

            req_dict = {"model": mapped_model, "request": gemini_body}
            if project_id:
                req_dict["project"] = project_id

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "antigravity/windows/amd64",
                "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
                "Client-Metadata": '{"ideType":"ANTIGRAVITY","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}'
            }

            # Retry transient network errors (SSL EOF, connection reset, timeout)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    http_req = urllib.request.Request(url, data=json.dumps(req_dict).encode("utf-8"), headers=headers)
                    resp = urllib.request.urlopen(http_req, timeout=120)
                    success = True

                    with _cache_lock:
                        _consecutive_failures[cooldown_key] = 0

                    if idx != active_idx:
                        data["activeIndex"] = idx
                        save_accounts_data(data)
                    break

                except urllib.error.HTTPError as he:
                    status_code = he.code
                    err_text = he.read().decode("utf-8", errors="ignore")
                    last_err = f"HTTP {status_code} on {email}: {err_text[:200]}"

                    if status_code in (429, 403, 503):
                        with _cache_lock:
                            failures = _consecutive_failures.get(cooldown_key, 0) + 1
                            _consecutive_failures[cooldown_key] = failures
                            cooldown_duration = {1: 60, 2: 300, 3: 1800}.get(failures, 7200)
                            _cooldown_cache[cooldown_key] = time.time() + cooldown_duration
                            _token_cache.pop(email, None)
                            _project_cache.pop(email, None)

                    if status_code == 401:
                        with _cache_lock:
                            _token_cache.pop(email, None)
                            _project_cache.pop(email, None)

                    break  # HTTP errors are not retryable (except via account rotation)

                except Exception as e:
                    last_err = f"Request error on {email}: {e}"
                    is_transient = any(s in str(e) for s in [
                        "SSL", "EOF", "Connection reset", "timed out",
                        "Connection refused", "Temporary failure"
                    ])
                    if is_transient and attempt < max_retries - 1:
                        time.sleep(1 * (attempt + 1))  # 1s, 2s backoff
                        continue
                    break

            if success:
                break

        if not success:
            self._error_response(500, f"All accounts failed. Last error: {last_err}")
            return

        # ── Handle response ───────────────────────────────────
        if stream:
            self._handle_stream_response(resp, req_model)
        else:
            self._handle_sync_response(resp, req_model)

    def _handle_sync_response(self, resp, req_model):
        """Parse non-streaming Gemini response → OpenAI format."""
        try:
            res_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            self._error_response(502, f"Failed to parse upstream response: {e}")
            return

        response_obj = res_data.get("response", {})
        candidates = response_obj.get("candidates", [])
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
                    sig = p.get("thoughtSignature")
                    if sig:
                        with _sig_lock:
                            _thought_signatures[call_id] = sig
                    tool_calls.append({
                        "id": call_id,
                        "type": "function",
                        "function": {"name": fc.get("name", ""), "arguments": json.dumps(fc.get("args", {}))}
                    })
            if tool_calls:
                finish_reason = "tool_calls"

        msg_obj = {"role": "assistant", "content": text or None}
        if tool_calls:
            msg_obj["tool_calls"] = tool_calls

        openai_resp = {
            "id": f"chatcmpl-{int(time.time()*1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req_model,
            "choices": [{"index": 0, "message": msg_obj, "finish_reason": finish_reason}]
        }
        resp_bytes = json.dumps(openai_resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)
        self.wfile.flush()

    def _handle_stream_response(self, resp, req_model):
        """Parse streaming Gemini SSE → OpenAI SSE format."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                line_bytes = resp.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8").strip()
                if not line or not line.startswith("data:"):
                    continue

                data_str = line[5:].strip()
                if not data_str:
                    continue

                try:
                    gemini_data = json.loads(data_str)
                except Exception:
                    continue

                response_obj = gemini_data.get("response", {})
                candidates = response_obj.get("candidates", [])
                text = ""
                tool_calls = []
                finish_reason = None

                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for p in parts:
                        if "text" in p:
                            text += p["text"]
                        if "functionCall" in p:
                            fc = p["functionCall"]
                            call_id = fc.get("id") or f"call_{int(time.time()*1000)}"
                            sig = p.get("thoughtSignature")
                            if sig:
                                with _sig_lock:
                                    _thought_signatures[call_id] = sig
                            tool_calls.append({
                                "index": len(tool_calls),
                                "id": call_id,
                                "type": "function",
                                "function": {"name": fc.get("name", ""), "arguments": json.dumps(fc.get("args", {}))}
                            })

                    raw_reason = candidates[0].get("finishReason")
                    if tool_calls:
                        finish_reason = "tool_calls"
                    elif raw_reason == "STOP":
                        finish_reason = "stop"
                    elif raw_reason:
                        finish_reason = "stop"

                delta = {}
                if text:
                    delta["content"] = text
                if tool_calls:
                    delta["tool_calls"] = tool_calls

                if delta or finish_reason:
                    chunk = {
                        "id": f"chatcmpl-{int(time.time()*1000)}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": req_model,
                        "choices": [{"delta": delta, "index": 0, "finish_reason": finish_reason}]
                    }
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                    self.wfile.flush()

                if finish_reason:
                    break
        except Exception:
            pass
        finally:
            try:
                resp.close()
            except Exception:
                pass
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
        self.close_connection = True

    def _error_response(self, status, message):
        body = json.dumps({"error": {"message": message, "type": "proxy_error"}}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except Exception:
            pass


# ── Background Server ─────────────────────────────────────────
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_background_proxy():
    if is_port_in_use(PROXY_PORT):
        return

    def run():
        try:
            server = ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), AntigravityProxyHandler)
            server.daemon_threads = True
            server.serve_forever()
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    # Wait for server to bind
    for _ in range(20):
        time.sleep(0.1)
        if is_port_in_use(PROXY_PORT):
            break


# ── OAuth Login Flow ──────────────────────────────────────────
_auth_code = None
_oauth_server = None


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if "code" in query:
            _auth_code = query["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Authentication Successful!</h2><p>You can close this tab.</p></body></html>")
            threading.Thread(target=lambda: _oauth_server.shutdown()).start()
        else:
            self.send_response(400)
            self.end_headers()


def perform_oauth_flow():
    """Run full OAuth flow — opens browser, waits for callback."""
    global _auth_code, _oauth_server
    _auth_code = None

    socketserver.TCPServer.allow_reuse_address = True
    _oauth_server = socketserver.TCPServer(("127.0.0.1", 51121), _OAuthCallbackHandler)

    t = threading.Thread(target=_oauth_server.serve_forever)
    t.start()

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent"
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    webbrowser.open(auth_url)

    t.join(timeout=90)

    if not _auth_code:
        return False, "❌ Login timed out. Try `/antigravity-login` again."

    # Exchange code for tokens
    token_data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": _auth_code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return False, f"❌ Token exchange failed: {e}"

    refresh_tok = tokens.get("refresh_token")
    access_tok = tokens.get("access_token")
    if not refresh_tok:
        return False, "❌ No refresh token received. Make sure you granted offline access."

    # Get user email
    email = "unknown"
    try:
        info_req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_tok}"}
        )
        with urllib.request.urlopen(info_req, timeout=10) as resp:
            info = json.loads(resp.read().decode("utf-8"))
            email = info.get("email", "unknown")
    except Exception:
        pass

    # Save account
    data = load_accounts_data()
    # Remove existing account with same email
    data["accounts"] = [a for a in data["accounts"] if a.get("email") != email]
    data["accounts"].append({
        "email": email,
        "refreshToken": refresh_tok,
        "addedAt": int(time.time() * 1000),
        "lastUsed": int(time.time() * 1000),
        "enabled": True
    })
    data["activeIndex"] = len(data["accounts"]) - 1
    save_accounts_data(data)

    # Warm cache
    with _cache_lock:
        _token_cache[email] = access_tok

    return True, f"✅ Logged in as **{email}**. Antigravity proxy ready on port {PROXY_PORT}."


# ── Slash Command Handlers ────────────────────────────────────
def handle_antigravity_login(args):
    try:
        success, msg = perform_oauth_flow()
        return msg
    except Exception as e:
        return f"❌ Login error: {e}"


def handle_antigravity_accounts(args):
    data = load_accounts_data()
    accounts = data.get("accounts", [])
    if not accounts:
        return "No accounts configured. Use `/antigravity-login` to authenticate."

    lines = ["**Hermes Antigravity Accounts** (isolated from Antigravity CLI)\n"]
    for i, acct in enumerate(accounts):
        active = "→" if i == data.get("activeIndex", 0) else " "
        email = acct.get("email", "?")
        enabled = "✅" if acct.get("enabled", True) else "❌"
        lines.append(f"{active} [{i}] {email} {enabled}")

    proxy_status = "✅ Running" if is_port_in_use(PROXY_PORT) else "❌ Down"
    lines.append(f"\n🔌 Proxy: {proxy_status} (port {PROXY_PORT})")
    return "\n".join(lines)


# ── Plugin Registration ───────────────────────────────────────
def handle_antigravity_quota(args):
    """Show cooldown/quota status for all accounts."""
    data = load_accounts_data()
    accounts = data.get("accounts", [])
    if not accounts:
        return "No accounts configured. Use `/antigravity-login` to authenticate."

    lines = ["**Antigravity Quota Status**\n"]
    now = time.time()
    families = ["gemini", "claude"]

    for acct in accounts:
        email = acct.get("email", "?")
        enabled = "✅" if acct.get("enabled", True) else "❌"
        lines.append(f"**{email}** {enabled}")

        for family in families:
            cooldown_key = f"{email}:{family}"
            with _cache_lock:
                cooldown_until = _cooldown_cache.get(cooldown_key, 0)
                failures = _consecutive_failures.get(cooldown_key, 0)
            if now < cooldown_until:
                remaining = int(cooldown_until - now)
                mins, secs = divmod(remaining, 60)
                lines.append(f"  {family}: ⏳ Cooldown {mins}m{secs}s (failures: {failures})")
            else:
                lines.append(f"  {family}: ✅ Ready")

    # Option to clear cooldowns
    if args and args.strip() == "clear":
        with _cache_lock:
            _cooldown_cache.clear()
            _consecutive_failures.clear()
        lines.append("\n🧹 All cooldowns cleared!")

    lines.append("\n💡 Use `/antigravity-quota clear` to reset cooldowns.")
    return "\n".join(lines)


def register(ctx):
    ctx.register_command(
        "antigravity-login",
        handler=handle_antigravity_login,
        description="Login to Google Antigravity for Hermes — isolated from Antigravity IDE"
    )
    ctx.register_command(
        "antigravity-accounts",
        handler=handle_antigravity_accounts,
        description="View Hermes Antigravity account status"
    )
    ctx.register_command(
        "antigravity-quota",
        handler=handle_antigravity_quota,
        description="View quota/cooldown status and optionally clear cooldowns"
    )


# ── Auto-start proxy on plugin load ──────────────────────────
start_background_proxy()
