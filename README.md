# Hermes Antigravity Auth (`hermes-antigravity-auth-native`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hermes Agent](https://img.shields.io/badge/Hermes-Plugin-blue.svg)](https://hermesagent.com)

> Native Hermes Agent plugin for **Google Antigravity** (Gemini 3.7, Claude Sonnet/Opus, GPT-OSS) with an **isolated account store** that never interferes with your Antigravity CLI/IDE sessions.

---

## ✨ Features

- 🔒 **Isolated Account Store**: `~/.hermes/antigravity-accounts.json` — independent from Antigravity CLI
- 🚀 **Self-Healing Proxy**: Auto-starts on port `8999` when Hermes loads
- 🔄 **Account Rotation**: Automatic failover with cooldown on rate limits
- 🧠 **Thinking Model Fix**: Enforces minimum 16384 output tokens so thinking models don't starve
- ⚡ **SSE Streaming**: Real-time token streaming with sub-100ms first-token
- 🛠️ **Tool Use Support**: Full function calling with thoughtSignature preservation

---

## 🤖 Supported Models

| Model | Backend |
|-------|---------|
| `gemini-3.7-flash` | Gemini 3.5 Flash (thinking) |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 |
| `claude-opus-4-6` | Claude Opus 4.6 (thinking) |
| `gpt-oss-120b` | GPT OSS 120B |
| `gemini-3.1-pro` | Gemini 3.1 Pro |
| `gemini-3-flash` | Gemini 3 Flash |
| `gemini-2.5-flash` | Gemini 2.5 Flash |

---

## 💬 Slash Commands

| Command | Description |
|---------|-------------|
| `/antigravity-login` | OAuth login via browser — stores refresh token in isolated store |
| `/antigravity-accounts` | View account status, proxy health |

---

## 📦 Quick Installation

### Option 1: One-Line Installer (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/kalyanace44/hermes-antigravity-auth-native/main/install.sh | bash
```

### Option 2: Clone and Install

```bash
git clone https://github.com/kalyanace44/hermes-antigravity-auth-native.git
cd hermes-antigravity-auth-native
chmod +x install.sh && ./install.sh
```

---

## 🔍 Architecture

```
┌─────────────────┐       OpenAI-compatible API       ┌────────────────────────┐
│  Hermes Agent   │  ──────────────────────────────> │  Antigravity Plugin    │
│  (Desktop/CLI)  │  <────────────────────────────── │  (Port 8999)           │
└─────────────────┘                                   └───────────┬────────────┘
                                                                  │
                                         Google OAuth + Refresh   │ (Isolated Store:
                                         Token from JSON file     │  ~/.hermes/antigravity-accounts.json)
                                                                  ▼
                                                      ┌────────────────────────┐
                                                      │  Google Antigravity    │
                                                      │  (daily-cloudcode API) │
                                                      └────────────────────────┘
```

---

## 🛠️ Verification

```bash
curl http://127.0.0.1:8999/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mock" \
  -d '{"model": "gemini-3.7-flash", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE).
