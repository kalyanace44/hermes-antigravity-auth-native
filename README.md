# Hermes Antigravity Auth (`hermes-antigravity-auth-native`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hermes Agent](https://img.shields.io/badge/Hermes-Plugin-blue.svg)](https://hermesagent.com)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-green.svg)](https://cloud.google.com)

> Native Hermes Agent plugin to authenticate with Google Antigravity (Google Cloud Code PA) and query **Gemini 3.7 Flash**, **Claude 4.6 Sonnet**, **Claude Opus 4.6**, and **GPT-OSS 120B** directly using your Google account pool.

---

## ✨ Key Improvements in `hermes-antigravity-auth-native`

- ⚡ **Zero-Latency Stream Unbuffered SSE**: Fixes the upstream Google HTTP keep-alive connection hang by immediately terminating and closing streams upon `finishReason` or `tool_calls`.
- 🛠️ **Rock-Solid Tool Calling Schema**: Sanitizes and normalizes OpenAI-format parameter schemas to uppercase JSON types (`OBJECT`, `STRING`, `ARRAY`), stripping unsupported `$schema` and `additionalProperties` keywords that trigger upstream HTTP 400 rejections.
- 🧠 **Multi-Turn `thoughtSignature` Resolution**: Prevents Google 400 rejections during multi-turn agent tool executions by cleanly separating tool action tags in conversation history.
- 🔒 **Account Isolation**: Completely decouples Hermes's OAuth accounts (`~/.hermes/antigravity-accounts.json`) from Antigravity CLI's default configuration, preventing session conflicts and platform path bugs.
- 🗂️ **Deduplicated Model List**: Eliminates duplicate `-thinking` UI rows while preserving full dynamic reasoning effort control (`Low`, `Med`, `High`, `Max`) in the Hermes model selector.

---

## 🤖 Supported Models

| Model Name in Hermes | Architecture / Family | Features |
|---|---|---|
| `gemini-3.7-flash` | Gemini 3.7 Flash | Hybrid reasoning, coding, high speed |
| `claude-sonnet-4-6` | Anthropic Claude 4.6 Sonnet | High intelligence, software engineering |
| `claude-opus-4-6` | Anthropic Claude 4.6 Opus | Deep reasoning & architecture planning |
| `claude-3-5-sonnet` | Claude 3.5 Sonnet | Reliable coding baseline |
| `claude-3-opus` | Claude 3 Opus | Complex logic & system design |
| `gpt-oss-120b` | GPT-OSS 120B | Open-weight frontier reasoning |
| `gemini-3.1-pro` | Gemini 3.1 Pro | Deep analysis & multimodal tasks |
| `gemini-3-flash` | Gemini 3 Flash | Ultra-fast utility model |
| `gemini-2.5-flash` | Gemini 2.5 Flash | Lightweight low-latency model |

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

## 🔑 Account Management

Inside the Hermes chat window:

1. **Log in with any Google account**:
   ```text
   /antigravity-login
   ```
2. **List and switch accounts**:
   ```text
   /antigravity-accounts
   ```

---

## 🔍 Architecture Overview

```
┌─────────────────┐       OpenAI SSE Stream        ┌────────────────────────┐
│  Hermes Agent   │  ────────────────────────────> │ Antigravity Plugin     │
│  (Desktop / CLI)│  <──────────────────────────── │ (Port 8999 Proxy)      │
└─────────────────┘                                └───────────┬────────────┘
                                                               │
                                          OAuth2 Token Pool &  │
                                          Schema Normalizer    ▼
                                                   ┌────────────────────────┐
                                                   │  Google Cloud Code PA  │
                                                   │  (Gemini & Claude)     │
                                                   └────────────────────────┘
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
