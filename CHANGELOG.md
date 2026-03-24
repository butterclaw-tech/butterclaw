# Changelog

All notable changes to ButterClaw are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

---

## [0.1.1] — 2026-03-23

### Summary

52 patches across 4 files. Zero new dependencies. Full security audit, routing integration, and mobile responsiveness pass.

---

### index.html — 10 patches

#### Critical

| ID | Fix |
|----|-----|
| C1 | **XSS: DOM construction rewrite.** Log renderer rewritten from `innerHTML` to `createLogCard()` using `createElement` + `textContent` for all server-provided strings. |
| C2 | **Tailwind safelist.** All dynamic color classes (`red`, `amber`, `emerald`, `blue`) explicitly listed in `tailwind.config` so JIT purge doesn't strip them at build time. |
| C3 | **SSE reconnect with exponential backoff.** `onerror` no longer calls `close()` permanently. Replaced with exponential backoff reconnect (1s → 2s → 4s → … → 30s cap). Backoff resets on successful message receipt. |
| C4 | **Content Security Policy.** CSP `<meta>` tag added: `default-src 'self'`; `script-src`, `connect-src`, `style-src`, `img-src` locked to `self` + Tailwind CDN + `localhost:5000`. |

#### Medium

| ID | Fix |
|----|-----|
| M1 | **Shield toggle wired to API.** Button now POSTs `{enabled: bool}` to `/api/shield`. Previously CSS-only with no server communication. |
| M2 | **Settings sync on load.** On `DOMContentLoaded`, fetches `GET /api/settings` to sync paranoia slider value from server state. Falls back to `3` if server is offline. |
| M3 | **Mobile navigation.** Hamburger button (`md:hidden`), slide-in sidebar with CSS transform transition, backdrop overlay, and close button. |

#### Low

| ID | Fix |
|----|-----|
| L1 | Mock API key display now labeled `(Demo)` to prevent user confusion. |
| L2 | Paranoia modeBox switched from `innerHTML` to `createElement` + `textContent`. Content is local (not server data) — consistency fix. |

#### New Feature

| ID | Fix |
|----|-----|
| N1 | **Live connection badge.** Sidebar + header both poll `GET /api/health` every 30s. Three visual states: 🟢 connected (<2s RTT), 🟡 slow (>2s RTT), 🔴 disconnected. Uses `AbortController` with 5s timeout and `performance.now()` for latency measurement. Replaces hardcoded "Port 18789 Secured" emerald dot. |

---

### server.py — 20 patches (14 core + 6 routing integration)

#### Critical

| ID | Fix |
|----|-----|
| C1 | **CORS hardening.** Removed manual `Access-Control-Allow-Origin: *` header on `/api/stream`. Flask-CORS now handles all routes via `ALLOWED_ORIGINS` whitelist. |
| C2 | **Input validation on `/api/analyze`.** Validates `request.json` is not `None`, checks `threat_type` and `raw_data` are present and non-empty. Returns `400` with descriptive error on failure. |
| C3 | **Thread-safe global state.** `threading.Lock` (`_state_lock`) guards all mutable globals. 15 lock acquisitions across the codebase. |
| C4 | **SQLite error handling.** All database operations wrapped in `try/except sqlite3.Error` with proper HTTP error responses and logging. |

#### Medium

| ID | Fix |
|----|-----|
| M1 | Removed duplicate `total_logs_processed = 0` declaration that silently reset the counter after `init_db()`. |
| M2 | Removed dead `live_oopsie_logs = []` — populated but never read. |
| M3 | Removed dead `trigger_kill_switch` flag — set but never evaluated. |
| M4 | **Portable DB path.** `os.path.join(os.path.dirname(os.path.abspath(__file__)), 'butterclaw.db')` replaces bare filename. |
| M5 | Added `check_same_thread=False` on `sqlite3.connect()` for safe multi-threaded access. |
| M6 | Werkzeug log level changed from `ERROR` to `WARNING` — stops swallowing HTTP-level warnings. |

#### New Endpoints

| ID | Fix |
|----|-----|
| N1 | **`GET /api/settings`** returns `{level, shield_enabled, routing_mode, model, endpoint, gates}`. |
| N2 | **`POST /api/shield`** accepts `{enabled: bool}`, logs state change to DB, returns updated status. |

#### Low

| ID | Fix |
|----|-----|
| L1 | **Rate limiter.** `deque`-based sliding window, 10 requests/min on `/api/analyze`. Returns `429 Too Many Requests` with retry hint. |
| L2 | **Startup banner.** Prints version, DB path, paranoia level, routing mode, model, active gates, rate limit, and CORS origins on boot. |

#### Routing Integration (R-series)

| ID | Fix |
|----|-----|
| R1 | **`GET /api/health`** endpoint — returns `{"status": "ok", "version": "0.1.1"}` for connection badge polling. |
| R2 | `MODEL_NAME` constant replaced with mutable `model_name` global. Read under lock as `active_model`. |
| R3 | **Routing mode support.** `routing_mode` (`"local"` / `"remote"`) + `remote_endpoint` string. `_resolve_ollama_url()` returns correct inference URL. `_validate_endpoint_url()` checks scheme + netloc. |
| R4 | **Gate states.** `gate_states` dict with 4 boolean keys (`sig_scan`, `origin_ctx`, `intent`, `kill_sw`). `VALID_GATE_KEYS` frozenset rejects unknown keys. |
| R5 | **`/api/settings` POST accepts partial updates** for `level`, `routing_mode`, `model`, `endpoint`, `gates` — each field validated independently. |
| R6 | **Gate-aware analysis.** `ask_guardian_agent()` builds `gate_context` string listing active/inactive gates in the system prompt. `kill_sw` DISARMED suppresses SIGKILL verdict → returns `ALERT | Kill Switch Disarmed` instead. |

---

### watcher.py — 8 patches

#### Critical

| ID | Fix |
|----|-----|
| C1 | **Log rotation detection.** `get_file_identity()` returns `(st_ino, st_size)`. Main loop detects truncation (`pos > size`) and inode change, reopens file handle from position 0. |
| C2 | **Sanitizer rewrite.** Old whitelist `[^a-zA-Z0-9\s\.\-\"\/:\\_]` replaced with targeted blacklist `` [$`{}<>\|;!] `` — preserves `[]()=?&#@+,:` needed for valid log content. |
| C3 | **Retry queue.** `deque(maxlen=100)` for failed dispatches. `flush_retry_queue()` runs before new reads. Pops front on success, stops on first failure. Handles `429` gracefully. |

#### Medium

| ID | Fix |
|----|-----|
| M1 | Typo fix: `"Autclator going dark"` → `"Automator going dark"`. |
| M2 | **Structured logging.** All `print()` calls replaced with `logging` module. Zero bare prints (AST-verified). |
| M3 | POST timeout reduced from `60s` → `10s` to prevent blocking on unresponsive server. |
| M4 | **PID lock file.** Writes `watcher.pid`, checks `os.kill(pid, 0)` for liveness, cleans stale files, registers `atexit` cleanup. |

#### Low

| ID | Fix |
|----|-----|
| L1 | **`--replay` flag** via `argparse`. Default: tail mode (`seek(0, 2)`). Replay mode: `seek(0)` — reads full log from top. |

---

### routing.html — 14 patches (rebuilt from cosmetic placeholder)

#### Critical

| ID | Fix |
|----|-----|
| C1 | **Live test ping.** Was `Math.random()` generating fake 12–45ms values. Now `fetch()` to `{endpoint}/api/health` with `performance.now()` RTT measurement, `AbortController` 5s timeout, and 5 visual states (idle → testing → success → slow → error). |
| C2 | **Model selector.** `id="modelSelect"` with `<option value>` for Ollama model names (`phi3.5`, `llama3.2:3b`, `mistral:7b`). Wired to Save Configuration payload. |
| C3 | **Save Configuration wired to API.** Button POSTs `{routing_mode, model, endpoint}` to `/api/settings`. Page load fetches `GET /api/settings` to populate all fields from server state. |
| C4 | **CSP meta tag + Tailwind safelist.** Mirrors `index.html` security posture. |

#### Medium

| ID | Fix |
|----|-----|
| M1 | **Mobile navigation.** Hamburger button + slide-in sidebar + backdrop overlay. Matches `index.html` pattern. |
| M2 | **Dynamic logic gates UI.** JS `GATES` array, `buildGateRow()` DOM construction, click-to-toggle with visual feedback, `saveGateStates()` POST to `/api/settings`. |
| M3 | **Live connection badge.** `checkConnection()` pings `GET /api/health` every 30s. Three states: 🟢 emerald (connected), 🟡 amber (slow), 🔴 red (disconnected). |
| M4 | **Full nav bar.** 4 items matching `index.html`: Shield Status, ButterVault, Oopsie Logs, VPS Brain Routing. |
| M5 | `setPingBtnState()` uses `createElement` + `textContent` instead of `innerHTML`. |

#### Future-Prep

| ID | Fix |
|----|-----|
| F1 | **MCP Connections card.** URL input + transport selector (SSE/stdio). Disabled with "Coming Soon v0.2" badge. |
| F2 | **Routing Mode card.** Local (Ollama) / Remote (VPS) toggle. Endpoint input auto-disables in local mode. |
| F3 | Version footer: `ButterClaw v0.1.1`. |

#### Low

| ID | Fix |
|----|-----|
| L1 | **URL validation.** `new URL()` on blur with ✓/✗ inline feedback. |
| L2 | SVG chevron overlay on both `<select>` elements for consistent cross-browser styling. |

---

## [0.1.0] — Initial Release

- Prototype dashboard (`index.html`)
- Flask API server (`server.py`)
- Log watcher daemon (`watcher.py`)
- Cosmetic routing placeholder (`routing.html`)
- Ollama + Phi-3 local inference
- SQLite short-term memory
- SSE log streaming
