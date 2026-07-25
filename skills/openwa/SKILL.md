---
name: openwa
description: OpenWA self-hosted WhatsApp API Gateway — full operational and reference guide. Covers install (Docker/OrbStack), boot, pairing a WhatsApp number via QR, enabling the MCP server (full mode, 39 tools), minting API keys, wiring Claude/Cursor/ZCode clients, calling tools, on/off, the REST API, webhooks + Socket.IO events, configuration, the 3-role auth model, SDKs, architecture, and 13 gotchas. Use when the user says "set up openwa", "boot openwa", "install openwa", "pair my whatsapp number", "enable openwa mcp", "add openwa to zcode/claude/cursor", "send a whatsapp message via openwa", or wants to drive WhatsApp programmatically. Also use when working in the OpenWA repo, code hits port 2785, builds the openwa-api Docker service, sends X-API-Key headers with owa_k1_ keys, subscribes to message.received/message.ack/session.status webhooks, or toggles DATABASE_TYPE/QUEUE_ENABLED/REDIS_ENABLED/ENGINE_TYPE.
---

# OpenWA

OpenWA is a self-hosted, open-source WhatsApp API Gateway (MIT, NestJS 11 / TypeScript / Node 22). It wraps an unofficial WhatsApp engine (Baileys or whatsapp-web.js) behind a REST API on port `2785`, ships a React dashboard, and supports multi-session WhatsApp automation with MCP tools, webhooks, Socket.IO real-time events, pluggable storage/cache/database, and a plugin hook system.

**⚠️ Ban risk is real.** The engines speak the unofficial WhatsApp multidevice protocol. Never pair a primary number — use a burner. Protocol-level detection tightened through 2025.

This is the comprehensive single skill. Deep-dive details live in `references/` — read them when this file points to one.

## Product surface

| Component | Port | Role |
|---|---|---|
| `openwa-api` (NestJS) | `2785` | REST + WebSocket + webhook dispatcher + MCP server + bundled dashboard |
| `docker-proxy` (tecnativa) | `2375` internal | Socket-proxy sidecar — only container touching `/var/run/docker.sock` |

Dashboard + Swagger (on the API port): `http://127.0.0.1:2785/` and `http://127.0.0.1:2785/api/docs`.

## When to use

- First-time setup → start at **1. Prerequisites**.
- Pair a WhatsApp number → **3. Pair**.
- Enable MCP / drive WhatsApp from an LLM → **4. MCP**.
- Send a message → **5. Tools** or **6. REST**.
- Real-time events → **7. Webhooks + Socket.IO**.
- On/off → **On/off**.
- Hit a weird behaviour → **12. Gotchas**.

---

# SETUP RUNBOOK

## 1. Prerequisites — Docker or OrbStack

OpenWA is Docker-native. One runtime required.

**macOS — OrbStack (lighter than Docker Desktop):**
```bash
brew install --cask orbstack
open -a OrbStack        # GUI first-run: accept license + VM setup (~1 min)
orbctl status           # → "Running"
docker version          # → client + server versions match
```

Alternatives: Docker Desktop (`brew install --cask docker`), Colima (`brew install docker colima && colima start`).

Verify before moving on: `docker version` shows both client and server.

## 2. Boot OpenWA

Assumes the OpenWA repo cloned at `./openwa` in the workspace.

```bash
cd openwa
cp .env.minimal .env
```

**Edit `.env` — pin the Baileys engine** (default whatsapp-web.js needs Chromium; Baileys is single-process, ~10× lighter):
```diff
- ENGINE_TYPE=whatsapp-web.js
+ ENGINE_TYPE=baileys
```

**Optional** (auto-resume paired sessions on container start):
```
AUTO_START_SESSIONS=true
```

Boot + verify:
```bash
docker compose up -d docker-proxy openwa-api
sleep 20
curl -s http://127.0.0.1:2785/api/health/ready
# → {"status":"ok","details":{"mainDatabase":{"status":"up"},"dataDatabase":{"status":"up"}}}
```

**Extract the seeded admin key** (created on first run, plaintext shown once):
```bash
docker compose exec -T openwa-api cat /app/data/.api-key
# → owa_k1_<...>   save this — admin powers across all sessions
```

⚠️ **Dev-mode gotcha:** in `NODE_ENV=development` the bootstrap key is the literal string `dev-admin-key`. Never expose dev mode to the internet.

## 3. Pair a WhatsApp number

⚠️ **Use a burner number.** Pairing a primary account risks a ban.

```bash
KEY="<admin key>"
# 1. Create
curl -s -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name":"burner"}' http://127.0.0.1:2785/api/sessions
# → {"id":"<SESSION_UUID>",...}  save the id

SID="<session uuid>"

# 2. Start (spawns the engine socket)
curl -s -X POST -H "X-API-Key: $KEY" http://127.0.0.1:2785/api/sessions/$SID/start

# 3. Wait + fetch QR
sleep 8
curl -s -H "X-API-Key: $KEY" http://127.0.0.1:2785/api/sessions/$SID/qr
# → {"qrCode":"data:image/png;base64,...","status":"qr_ready"}  (QR rotates ~every 20s)
```

Scan via dashboard (http://127.0.0.1:2785/ → Sessions → `burner`) or save the base64 to a PNG. On the burner phone's WhatsApp: **Settings → Linked Devices → Link a Device → scan.**

Verify: `curl -s -H "X-API-Key: $KEY" http://127.0.0.1:2785/api/sessions/$SID` → status `ready`, phone populated.

⚠️ **Disconnect gotcha:** any `docker compose up -d` that changes env **recreates** the container and kills the in-memory engine socket → session drops to `disconnected`. Auth creds persist in the volume, so resume works (dashboard → Resume, or `POST /api/sessions/$SID/start`). `docker compose stop`/`start` (not `down`/`up`) avoids recreate but still drops the live socket — engines are in-memory. `AUTO_START_SESSIONS=true` makes resume automatic.

---

# MCP — drive WhatsApp from an LLM

The MCP server exposes WhatsApp as tools an LLM (Claude/Cursor/ZCode) can call. **Default off.** Full mode = 39 tools (24 read + 17 write).

## 4a. Forward MCP env vars to the container

`docker-compose.yml` does NOT forward MCP vars by default. Add to `openwa-api.environment` (before `DOCKER_HOST`):
```yaml
      - MCP_ENABLED=${MCP_ENABLED:-}
      - MCP_READONLY=${MCP_READONLY:-}
      - MCP_RATE_LIMIT_MAX=${MCP_RATE_LIMIT_MAX:-}
      - MCP_RATE_LIMIT_WINDOW_MS=${MCP_RATE_LIMIT_WINDOW_MS:-}
      - MCP_IP_RATE_LIMIT_MAX=${MCP_IP_RATE_LIMIT_MAX:-}
      - MCP_IP_RATE_LIMIT_WINDOW_MS=${MCP_IP_RATE_LIMIT_WINDOW_MS:-}
```

## 4b. Enable in `.env`

Append to `openwa/.env`:
```
MCP_ENABLED=true       # strict string equality — yes/1 are REJECTED at boot
MCP_READONLY=false     # only the exact value "false" unlocks the 17 write tools
```

## 4c. Recreate + verify

```bash
cd openwa
docker compose up -d openwa-api     # recreate picks up new env (session drops — resume after)
docker compose logs openwa-api | grep -i "MCP server mounted"
# → "MCP server mounted at POST /mcp (39 tools)"
```
Then resume the session (see disconnect gotcha above).

## 4d. Mint a dedicated MCP key

Don't reuse the admin key. Mint an **OPERATOR** key scoped to the one session:
```bash
ADMIN="<admin key>"; SID="<session uuid>"
curl -s -X POST -H "X-API-Key: $ADMIN" -H "Content-Type: application/json" \
  -d "{\"name\":\"mcp-client\",\"role\":\"operator\",\"allowedSessions\":[\"$SID\"]}" \
  http://127.0.0.1:2785/api/auth/api-keys
# → {...,"key":"owa_k1_<SAVE_THIS>"}  (plaintext shown once)
```

**Why OPERATOR + session-scoped:** all 17 write tools require OPERATOR. Scoping means a leaked key can't touch other sessions. **Do NOT set `allowedIps` on this key** — MCP passes `clientIp=undefined`, and IP-allowlisted keys fail closed (rejected) over MCP.

## 4e. Wire the client

**Claude Code / Cursor** — workspace-root `.mcp.json` (auto-discovered):
```json
{
  "mcpServers": {
    "openwa": {
      "type": "http",
      "url": "http://localhost:2785/mcp",
      "headers": { "Authorization": "Bearer owa_k1_<YOUR_KEY>" }
    }
  }
}
```

**ZCode** — does NOT auto-discover workspace `.mcp.json`. Add the same entry under `mcp.servers` in `~/.zcode/cli/config.json`.

**Restart the client** after adding — MCP servers connect at session start, not mid-session. Add `.mcp.json` to `.gitignore` (contains a secret).

## 4f. Smoke-test the MCP endpoint

```bash
KEY="<mcp-client key>"
curl -s -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  http://127.0.0.1:2785/mcp | grep -o '"name":"[^"]*"' | wc -l
# → 39
```

## 5. MCP tools

Tools appear as `mcp__openwa__<ToolName>` once the client connects. All take `sessionId` (the UUID, not the name).

### Read tools (no confirmation)

| Domain | Tools |
|---|---|
| Session | `SessionFindAll`, `SessionFindOne`, `SessionGetChats`, `SessionGetStats` |
| Message | `MessageList` (DB), `MessageHistory` (live WA), `MessageGetReactions` |
| Contact | `ContactFindAll`, `ContactFindOne`, `ContactCheckNumber`, `ContactResolvePhone`, `ContactGetProfilePicture` |
| Group | `GroupFindAll`, `GroupFindOne`, `GroupGetInviteCode` |
| Webhook | `WebhooksList`, `WebhookFindBySession`, `WebhookFindOne` |

### Write tools — ⚠️ confirmation required on sends

Every send/forward/react tool: **show the user the resolved recipient (name + JID) and the exact message text, and get an explicit yes before firing.** Wrong-number sends are irreversible and leak confidential data. This rule is behavioral — enforce it even if no doc asks for it.

| Domain | Tools |
|---|---|
| Message send | `MessageSendText`, `MessageSendImage`, `MessageSendVideo`, `MessageSendAudio` (`ptt`=voice note), `MessageSendDocument`, `MessageSendSticker`, `MessageSendLocation`, `MessageSendContact`, `MessageSendTemplate` |
| Message ops | `MessageReply`, `MessageForward`, `MessageReact` |
| Session ops | `SessionMarkChatRead`, `SessionMarkChatUnread`, `SessionSendChatState` (typing indicator) |
| Contact | `ContactBlock`, `ContactUnblock` |
| Group | `GroupCreate`, `GroupAddParticipants`, `GroupSetSubject`, `GroupSetDescription` (last two flagged destructive) |

Chat-id formats: `<phone>@c.us` (DM), `<id>@g.us` (group), `<id>@newsletter` (channel). Wrong format = **silent failure**.

---

# REST API

Global prefix `/api`. Everything except `/api/health*` and `/api/docs` requires `X-API-Key`.

## Key routes (session-scoped under `/sessions/:sessionId/...`)

| Domain | Routes | Role |
|---|---|---|
| Sessions | `POST /sessions`, `GET /sessions`, `GET/:id`, `DELETE/:id`, `POST/:id/start`, `POST/:id/stop`, `GET/:id/qr`, `GET/:id/groups`, `GET /sessions/stats/overview` | create/start/stop/delete = OPERATOR |
| Messages | `send-text`, `send-image`, `send-video`, `send-audio`, `send-document`, `send-location`, `send-contact`, `send-sticker`, `reply`, `forward`, `react`, `delete`, `send-bulk` + `GET /batch/:batchId[/cancel]` | OPERATOR |
| Webhooks | `POST/GET/PUT/DELETE` under `/sessions/:sessionId/webhooks` + `POST/:id/test` | OPERATOR |
| API keys | `POST/GET/GET:id/PUT:id/DELETE:id/POST:id/revoke` under `/auth/api-keys` | **ADMIN** |
| Health | `GET /health`, `/health/live`, `/health/ready` | public |
| Auth probe | `GET /auth/validate` (header `X-API-Key`) | none |
| Other | contacts, groups, labels, channels, status, catalog, infra, settings, stats, audit | mixed |

Authoritative shapes: controllers + auto-published OpenAPI at `/api/docs` (UI) and `/api/docs-json` (raw — feed to `openapi-generator-cli` for SDK regen). Full route table: [references/rest-api.md](references/rest-api.md).

## Message send bodies

```http
POST /api/sessions/:sessionId/messages/send-text   {chatId, text}
POST /api/sessions/:sessionId/messages/send-image   {chatId, url|base64, caption?}
POST /api/sessions/:sessionId/messages/send-audio   {chatId, url|base64, ptt?}   # ptt=true = voice note
POST /api/sessions/:sessionId/messages/send-location {chatId, latitude, longitude, name?, address?}
POST /api/sessions/:sessionId/messages/reply         {chatId, quotedMessageId, text}
POST /api/sessions/:sessionId/messages/react         {messageId, emoji}
```

**Send returns when queued to engine, not delivered.** Track via `message.ack` events: status **1=sent, 2=delivered, 3=read**.

---

# Webhooks + Socket.IO

## Event taxonomy (11 + `*`)

`message.received`, `message.sent`, `message.ack` (status 1/2/3), `message.revoked`, `session.status`, `session.qr` (rotates ~20s), `session.authenticated`, `session.disconnected`, `group.join`, `group.leave`, `group.update`, plus `*` for all.

## Webhooks — per-session, signed, retried

Created **per session** (`POST /api/sessions/:sessionId/webhooks` `{url, events[], secret?, headers?}`). Scope is per-session — to deliver one event to N URLs, create N webhook rows.

Headers on every delivery:

| Header | Meaning |
|---|---|
| `X-OpenWA-Event` | Event name |
| `X-OpenWA-Delivery-Id` | Unique per delivery attempt |
| `X-OpenWA-Idempotency-Key` | Stable per (event × subject) — **consumer dedupe key** |
| `X-OpenWA-Retry-Count` | `0` first attempt, then `attemptsMade` |
| `X-OpenWA-Signature` | `sha256=<hex hmac>` of **raw JSON body** using `webhook.secret` |

**HMAC verifies against the RAW body, not parsed JSON.** Use `express.raw({type:'application/json'})` (Node) or read `await req.body()` bytes (Python) before parsing. Full verify code in Node + Python: [references/webhooks-and-events.md](references/webhooks-and-events.md).

Retries only work with queue: `WEBHOOK_MAX_RETRIES=3`, `WEBHOOK_RETRY_DELAY=5000`, `WEBHOOK_TIMEOUT=10000`. **`QUEUE_ENABLED=false` (default) → single-shot sync dispatch, no retry.**

## Socket.IO `/events` — NOT stock emit

Custom JSON envelope under the generic `'message'` event (biggest consumer gotcha):

```javascript
import { io } from 'socket.io-client';
const sock = io('http://127.0.0.1:2785/events', { auth: { apiKey: KEY } });
sock.emit('message', { type: 'subscribe', sessionId: '*', events: ['message.received'] });
sock.on('message', (msg) => {
  // msg.type === 'subscribed' | 'unsubscribed' | 'event' | 'error' | 'pong'
  if (msg.type === 'event') handle(msg.data);
});
// keep-alive: ping every 30s
setInterval(() => sock.emit('message', { type: 'ping' }), 30_000);
```

Client→server: `{type:'subscribe'|'unsubscribe'|'ping', sessionId?, events?, requestId?}` (sessionId/events may be `'*'`).
Server→client: `{type:'subscribed'|'unsubscribed'|'event'|'error'|'pong', event?, data?, ...}`.

---

# Configuration

## Env precedence (highest wins)

```
process.env  >  ./.env  >  ./data/.env.generated
```

`.env.generated` is what the dashboard Infra page writes — **lowest** precedence, not highest. To make a dashboard-saved value win, remove the key from process env + `.env`.

## Key vars

| Var | Default | Note |
|---|---|---|
| `PORT` | `2785` | API + dashboard + MCP |
| `NODE_ENV` | `production` | `development` → bootstrap key is literal `dev-admin-key` |
| `ENGINE_TYPE` | `whatsapp-web.js` | `baileys` = no Chromium, ~10× lighter |
| `AUTO_START_SESSIONS` | `false` | `true` = auto-resume paired sessions on container start |
| `DATABASE_TYPE` | `sqlite` | `postgres` for prod. `main` connection always SQLite |
| `DATABASE_SYNCHRONIZE` | `true` (sqlite) / `false` (pg) | **Never `true` on Postgres** — use `npm run migration:run:prod` |
| `STORAGE_TYPE` | `local` | `s3` for S3/MinIO (`STORAGE_S3_FORCE_PATH_STYLE=true` for MinIO) |
| `REDIS_ENABLED` | `false` | `true` for distributed throttler + BullMQ |
| `QUEUE_ENABLED` | `false` | **Required for webhook retries.** Else sync single-shot |
| `PLUGINS_ENABLED` | `true` | scans `PLUGINS_DIR` (default `./plugins`) |
| `MCP_ENABLED` | `false` | strict `"true"` only. `MCP_READONLY=false` unlocks writes |
| `CORS_ORIGINS` | `*` | Lock down for prod (permissive with credentials = key-stuff risk) |
| `LOG_LEVEL` | `info` | `debug` for verbose |

Full env reference: [references/configuration.md](references/configuration.md).

## Dual database

- **`main`** — always SQLite. Stores API keys + audit log. Node-local; don't migrate it.
- **`data`** — SQLite or Postgres. Stores sessions, messages, webhooks.

Switching `data` to Postgres does NOT move API keys (they're in `main`). Multi-node = per-node key sets unless you share `main.sqlite` (risky).

---

# Auth model

## 3 roles

| Role | Allows |
|---|---|
| `VIEWER` | read-only |
| `OPERATOR` | read + session CRUD + send + webhook CRUD |
| `ADMIN` | OPERATOR + API-key CRUD |

Writes gated by `@RequireRole(OPERATOR\|ADMIN)`; reads default to any active key.

## Key lifecycle

- Plaintext returned **only on creation** — lose it → revoke + recreate.
- Entity: `{id, name, keyHash, keyPrefix, role, allowedIps?, allowedSessions?, isActive, expiresAt?, lastUsedAt?, usageCount}`.
- Hard delete: `DELETE /:id`. Soft revoke: `POST /:id/revoke` (sets `isActive=false`).
- Probe without consuming a real endpoint: `curl -i -H "X-API-Key: $KEY" http://localhost:2785/api/auth/validate` → `{valid:true, role:"OPERATOR"}`.

## Public endpoints (no key)

`/api/health`, `/api/health/live`, `/api/health/ready`, `/api/docs`.

---

# SDKs

**Typed surface is narrow** — `@openwa/sdk` (JS) only wraps sessions + `sendText`. Everything else → raw `fetch` with `X-API-Key`, or regenerate a full client from the OpenAPI spec.

```typescript
import { OpenWAClient } from '@openwa/sdk';
const client = new OpenWAClient({ baseUrl: 'http://localhost:2785', apiKey: KEY });
await client.sessions.create({ name: 'bot-1' });
await client.sessions.start(id);
await client.messages.sendText(id, { chatId: '628123456789@c.us', text: 'hi' });
```

Python: `pip install -e sdk/python/openwa` — same shape (`wa.sessions.create(...)`, `wa.messages.send_text(...)`).

Regen a full client from `/api/docs-json`:
```bash
npx @openapitools/openapi-generator-cli generate \
  -i http://localhost:2785/api/docs-json -g typescript-fetch -o ./generated/openwa-client
```

Full SDK + n8n patterns: [references/sdk.md](references/sdk.md).

---

# Architecture

## Pluggability boundaries

- **`IWhatsAppEngine`** — abstracts the WhatsApp engine; Baileys/whatsapp-web.js swapped via `ENGINE_TYPE`. Selected in `engine.factory.ts`.
- **`StorageService`** — local-fs or S3/MinIO via `STORAGE_TYPE`.
- **`CacheService`** — in-memory or Redis via `REDIS_ENABLED`.
- **Plugin hooks** — 4 hook points: `message:sending` (can `{block:true}`), `message:sent`, `message:received`, `session:status`.
- **Queue gating** — `QueueModule` only imported when `QUEUE_ENABLED === 'true'`.

## Capacity (per node, whatsapp-web.js engine)

| vCPU/RAM | Concurrent sessions |
|---|---|
| 2/4 GB | 3–6 |
| 4/8 GB | 8–15 |
| 8/16 GB | 20–30 |

~80–150 MB RSS per session. Baileys is single-process, far lighter. Cross-limit symptoms: Chromium crashes, `QR_READY` takes minutes, engine timeouts.

## Scaling

Engines Map is per-process — one pod handles all sessions, or shard with session-id affinity at the LB. `openwa-data` must be a PVC `ReadWriteOnce`. **No cross-process lock** on the engines Map: two nodes starting the same session id fight over the WA auth dir → at least one fails.

Full module map + multi-node recipe: [references/architecture.md](references/architecture.md).

---

# Gotchas (13)

1. **`.env.generated` is LOWEST precedence** — dashboard saves don't override Docker `environment:` blocks.
2. **Every API restart force-disconnects sessions** (`session.service.ts`) — READY/INITIALIZING/QR_READY/AUTHENTICATING → DISCONNECTED. Auth persists; usually no fresh QR. Must `POST /sessions/:id/start` to resume.
3. **`QUEUE_ENABLED=false` (default) → no webhook retries** — sync single-shot dispatch.
4. **`synchronize:true` on Postgres is a footgun** — `migrationsRun: !synchronize` (inverted). Set `DATABASE_SYNCHRONIZE=false` + run migrations.
5. **API keys live in `main` SQLite, not `data` DB** — switching `data` to Postgres doesn't move them. Backup must include `main.sqlite`.
6. **`phone`/`pushName` are `null` until `READY`** — filtering by `?phone=` won't match CREATED/QR_READY/AUTHENTICATING.
7. **Chat-id format is unforgiving — wrong format = SILENT failure** — `<phone>@c.us` (digits only, country code, no `+`, no leading zero), `<id>@g.us` (opaque, get from `GET /sessions/:id/groups`). Don't trust send until `message.ack` status ≥ 2.
8. **Chromium non-negotiable for whatsapp-web.js** — Dockerfile hard-codes `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium`. Baileys doesn't need it.
9. **CORS is permissive by default** (`CORS_ORIGINS=*`) — any browser page can key-stuff. Lock origins, scope keys with `allowedIps` (but not on MCP keys — see 4d).
10. **Dev bootstrap key is the literal string `dev-admin-key`** in `NODE_ENV=development`.
11. **`WebhookService` shares the API process** — sync dispatch runs on the request thread; slow receiver delays the engine event loop.
12. **`engines` Map has no cross-process lock** — two nodes starting the same session id fight over the WA auth dir.
13. **Docker socket mount required by default** — `modules/docker` introspects the stack via `/var/run/docker.sock:ro`. Set `DOCKER_ENABLED=false` + remove mount if not in Docker.

Full annotated list with file:line: [references/gotchas.md](references/gotchas.md).

---

# On/off

**Daily pause/resume (keep pairing):**
```bash
cd openwa
docker compose stop openwa-api      # pause
docker compose start openwa-api     # resume (auto-reconnects if AUTO_START_SESSIONS=true)
```

**Stop the whole VM (saves most RAM):** OrbStack menu-bar → Quit, or `orbctl stop`. Restart: open OrbStack.app.

**Auto-start at login:** OrbStack Settings → "Start at login" ON. Containers have `restart: unless-stopped`. Login = OpenWA live.

**Avoid `docker compose down` for daily use** — recreates containers (slower, forces session resume). Use `stop`/`start`.

**Wipe everything (re-pair required):**
```bash
docker compose down -v       # -v deletes volumes = pairing creds gone
```

---

# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Health endpoint not 200 | `docker compose ps`, `docker compose logs openwa-api --tail 50` |
| `MCP_ENABLED=yes` ignored | Strict equality — must be exactly `true`. Same for `MCP_READONLY=false` |
| MCP key rejected (401) but works on REST | Key has `allowedIps` — fails closed over MCP. Mint a key without `allowedIps` |
| Session stuck `disconnected` after restart | Engines are in-memory. Dashboard → Resume, or `POST /api/sessions/$SID/start`. Set `AUTO_START_SESSIONS=true` |
| `tools/list` returns 24 not 39 | `MCP_READONLY` unset or not exactly `false`. Set `MCP_READONLY=false` + recreate |
| Send returns 201 but no delivery | Chat-id format wrong. Silent failure — check format |
| Tools not in client after `.mcp.json` | Client connects MCP at session start — **restart the client**. ZCode: also add to `~/.zcode/cli/config.json` |
| Webhook fires once then never | `QUEUE_ENABLED=false` (default) → single-shot. Set `REDIS_ENABLED=true` + `QUEUE_ENABLED=true` |
| Dashboard save has no effect | `.env.generated` is lowest precedence — remove the key from `.env` or process env |

---

# References

| File | Deep dive |
|---|---|
| [references/architecture.md](references/architecture.md) | Module map, engine interface contract, plugin loader, multi-node recipe |
| [references/configuration.md](references/configuration.md) | Full env-var reference with defaults, `.env.minimal`, dual-DB diagram |
| [references/deployment.md](references/deployment.md) | Dockerfile stages, compose profiles, Traefik, K8s probes, volumes |
| [references/operation.md](references/operation.md) | Auth guard internals, QR bootstrap script, capacity table, dashboard internals |
| [references/rest-api.md](references/rest-api.md) | Full controller→route catalog with bodies + role gating |
| [references/sdk.md](references/sdk.md) | JS/TS + Python client usage, raw fetch fallback, n8n integration |
| [references/webhooks-and-events.md](references/webhooks-and-events.md) | HMAC verify code, WS envelope protocol, retry/idempotency matrix |
| [references/gotchas.md](references/gotchas.md) | All 13 gotchas with file:line citations |
