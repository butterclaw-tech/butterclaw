# 📡 ButterClaw API Reference

ButterClaw features a comprehensive REST API with 43 routes, protected by a 3-tier Role-Based Access Control (RBAC) system using HMAC-SHA256 API keys and session tokens.

## Endpoints by Module

### Auth Endpoints (v0.6.0)
| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | public | Exchange API key for session token |
| POST | `/api/auth/logout` | any | Clear session cookie |
| GET | `/api/auth/whoami` | any | Current identity |
| GET | `/api/auth/keys` | admin | List all API keys |
| POST | `/api/auth/keys` | admin | Create new API key |
| DELETE | `/api/auth/keys/<id>` | admin | Revoke API key |
| DELETE | `/api/auth/keys/<id>/purge` | admin | Permanently delete key |

### Policy Endpoints (v0.6.1)
| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| GET | `/api/policies` | viewer | List all policies |
| POST | `/api/policies` | admin | Create policy |
| GET | `/api/policies/<id>` | viewer | Get policy |
| PUT | `/api/policies/<id>` | admin | Update policy |
| DELETE | `/api/policies/<id>` | admin | Delete policy |
| POST | `/api/policies/<id>/toggle` | admin | Enable/disable |
| POST | `/api/policies/dry-run` | operator | Test payload against policies |
| GET | `/api/policies/events` | viewer | Query policy event log |

### Alert Endpoints (v0.6.2)
| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| GET | `/api/alerts/channels` | viewer | List channels |
| POST | `/api/alerts/channels` | admin | Create channel |
| PUT | `/api/alerts/channels/<id>` | admin | Update channel |
| DELETE | `/api/alerts/channels/<id>` | admin | Delete channel (cascade) |
| POST | `/api/alerts/channels/<id>/toggle` | admin | Enable/disable |
| POST | `/api/alerts/channels/<id>/test` | operator | Send test alert |
| GET | `/api/alerts/rules` | viewer | List rules |
| POST | `/api/alerts/rules` | admin | Create rule |
| PUT | `/api/alerts/rules/<id>` | admin | Update rule |
| DELETE | `/api/alerts/rules/<id>` | admin | Delete rule |
| POST | `/api/alerts/rules/<id>/toggle` | admin | Enable/disable |
| GET | `/api/alerts/history` | viewer | Query alert history |
| GET | `/api/alerts/status` | viewer | Alert system summary |

### Core Endpoints
| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| POST | `/api/analyze` | operator | Analyze threat payload |
| GET | `/api/health` | public | System health + instance info |
| GET | `/api/config` | admin | Resolved config (redacted secrets) |
| GET | `/api/stream` | viewer | SSE event stream |
| GET | `/api/logs` | viewer | Query log history |

### MCP Endpoints (v0.5.0+)
| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| GET | `/api/mcp/tools` | viewer | List available MCP tools |
| POST | `/api/mcp/restart` | admin | Restart MCP process |
| GET | `/api/mcp/status` | viewer | MCP process health |
| GET | `/api/events` | viewer | Query event ledger |
| GET | `/api/events/count` | viewer | Event ledger count |
| GET | `/api/settings` | viewer | Server settings |

### Vault & OAuth Endpoints (v0.5.x)
| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| POST | `/api/rotate-keys` | admin | Manual Gibson Kill Switch |
| GET | `/api/vault/status` | viewer | Vault health status |
| GET | `/api/vault/credentials` | operator | List stored credentials |
| POST | `/api/vault/credentials` | admin | Store new credential |
| DELETE | `/api/vault/credentials/<name>` | admin | Delete credential |
| GET | `/api/oauth/providers` | viewer | List OAuth providers |
| POST | `/api/oauth/start/<provider>` | operator | Start OAuth flow |
| GET | `/api/oauth/callback` | public | OAuth callback handler |
| GET | `/api/oauth/tokens` | operator | List OAuth tokens |
| DELETE | `/api/oauth/tokens/<provider>` | admin | Delete OAuth token |