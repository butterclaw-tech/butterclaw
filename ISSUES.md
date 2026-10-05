### Issue 1: The Security/Regex Target

**Title:** `[good first issue] Add default regex signatures for known MCP exfiltration patterns`

**Description:**

```markdown
**Context:**
ButterClaw's Policy Engine (`policy_engine.py`) currently uses deterministic guardrails to evaluate LLM traffic before it hits the execution layer. While the engine supports `regex_match`, we currently lack a robust, default library of regex signatures for catching modern Prompt Injection and Cross-Site WebSocket Hijacking (CSWH) exfiltration attempts.

**The Goal:**
We need to compile a starter pack of JSON-native regex rules that operators can easily import to catch common unautclated or suspicious processes attempting to leak data via MCP tool calls. 

**Where to Start:**
1. Look at the 16 safe condition operators defined in `policy_engine.py`.
2. Draft a `default_signatures.json` file in the root directory containing 3-5 regex patterns targeting obvious exfiltration vectors (e.g., catching `curl` or `wget` commands piping environment variables, or base64 encoded strings in URL parameters).
3. Update the `README.md` with a quick snippet on how users can import these rules.

**Why this is a good first issue:**
Requires zero deep knowledge of the ButterClaw backend architecture. Perfect for security researchers, AppSec engineers, or anyone who loves writing bulletproof regex. 

```

### Issue 2: The Pure Python Target

**Title:** `[good first issue] Expand Alert Dispatcher with Telegram push notification support`

**Description:**

```markdown
**Context:**
The Alert Dispatcher (`alert_dispatcher.py`) currently routes threat notifications through 5 channels: Webhook, Discord, ntfy, SMTP, and Gotify. We want to add Telegram as the 6th official channel to give operators more flexibility for receiving mobile alerts when the Sentinel catches anomalous traffic.

**The Goal:**
Implement a new Telegram channel routing class within the dispatcher that formats and sends the alert payload to a Telegram Bot API.

**Where to Start:**
1. Open `alert_dispatcher.py` and review the existing channel classes (e.g., `DiscordChannel` or `GotifyChannel`). 
2. Create a new `TelegramChannel` class that accepts a Bot Token and a Chat ID.
3. Map the ButterClaw severity levels (CRITICAL, WARNING, INFO) to appropriate Telegram emojis (🔴, 🟡, 🟢) in the message formatting.
4. Ensure the implementation uses the standard Python `requests` library (we maintain a strict zero-bloat philosophy—no external Telegram SDKs!).

**Why this is a good first issue:**
Highly isolated Python task. You only need to touch one file (`alert_dispatcher.py`), and you can test it locally using the `/api/alerts/channels/<id>/test` endpoint without needing to trigger the full AI Brain.

```

### Issue 3: The DevOps/Logging Target

**Title:** `[good first issue] Standardize Nginx logging format for future CLI dashboard parsing`

**Description:**

```markdown
**Context:**
In ButterClaw v0.6.4, we fully isolated the application backend by routing all traffic through an Nginx reverse proxy. Currently, the `nginx/butterclaw.conf` uses the default Nginx logging format. As we move toward building a live CLI visualizer for the SOC, we need the Nginx access logs formatted as structured JSON so our backend can ingest them cleanly.

**The Goal:**
Update the Nginx configuration to output access logs in a structured JSON format that tracks the incoming IP, request path, status code, and upstream response time.

**Where to Start:**
1. Open `nginx/butterclaw.conf`.
2. Define a new `log_format` block using JSON key-value pairs. 
3. Apply this new format to the `access_log` directive.
4. Run `docker compose restart nginx` to test the output in your terminal.

**Why this is a good first issue:**
Great for DevOps/Sysadmin contributors. It requires no Python or AI knowledge, just solid Nginx configuration skills. It directly lays the groundwork for our upcoming v0.7 roadmap features.

```