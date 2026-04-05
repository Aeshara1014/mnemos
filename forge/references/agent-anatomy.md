# Agent Anatomy

## Directory Structure

```
~/.openclaw/
├── openclaw.json                          # Global config (agents.list, bindings, etc.)
├── agents/
│   └── <agent-id>/
│       └── agent/
│           ├── auth-profiles.json         # Credentials (API keys, OAuth tokens)
│           └── models.json                # Provider endpoints and custom model defs

~/clawd-<agent-name>/                      # Agent workspace
├── .env                                   # Environment variables (API keys)
├── .openclaw/
│   └── workspace-state.json               # Onboarding state
├── SOUL.md                                # Who the agent is (personality, essence)
├── IDENTITY.md                            # How the agent operates (capabilities, boundaries)
├── MEMORY.md                              # What the agent remembers (persistent knowledge)
├── USER.md                                # About the human collaborator
├── AGENTS.md                              # Multi-agent coordination config
├── TOOLS.md                               # Custom tool definitions
├── HEARTBEAT.md                           # Periodic task configuration
└── memory/                                # Runtime memory directory
    └── active-context.md                  # Cross-session context
```

## Config Registration (openclaw.json)

### agents.list entry
```json
{
  "id": "<agent-id>",
  "name": "<display-name>",
  "model": "<provider/model-name>",
  "workspace": "/Users/rileycoyote/clawd-<name>"
}
```

### Telegram binding (optional)
```json
{
  "agentId": "<agent-id>",
  "match": {
    "channel": "telegram",
    "accountId": "<telegram-account-id>"
  }
}
```

### Telegram account (optional)
Under `channels.telegram.accounts`:
```json
{
  "<account-id>": {
    "enabled": true,
    "dmPolicy": "pairing",
    "botToken": "<telegram-bot-token>",
    "groupPolicy": "open",
    "streaming": "partial"
  }
}
```

## auth-profiles.json

```json
{
  "version": 1,
  "profiles": {
    "openrouter:manual": {
      "type": "api_key",
      "provider": "openrouter",
      "key": "<openrouter-api-key>"
    }
  },
  "lastGood": {},
  "usageStats": {}
}
```

## models.json (OpenRouter routing)

For each provider in the model constellation, create an entry that points to OpenRouter:

```json
{
  "providers": {
    "<provider>": {
      "baseUrl": "https://openrouter.ai/api/v1",
      "apiKey": "<openrouter-api-key>",
      "models": []
    },
    "openrouter": {
      "baseUrl": "https://openrouter.ai/api/v1",
      "api": "openai-completions",
      "models": [],
      "apiKey": "OPENROUTER_API_KEY"
    }
  }
}
```

## .env

```bash
OPENROUTER_API_KEY=<key>
GEMINI_API_KEY=<key>
```
