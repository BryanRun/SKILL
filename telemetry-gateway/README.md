# Telemetry Gateway

Telemetry Gateway receives gerrit-pipeline usage events, persists them to a
local SQLite queue, and asynchronously flushes them to a Feishu Bitable table.
It is designed to run under a normal Linux user account on an internal server.

## Packaging Boundary

Telemetry Gateway is an administrator-maintained server component. It is not
included in the user-facing `gerrit-pipeline` skill zip or SkillPack package.
Only `gerrit-pipeline/scripts/telemetry_client.py` and
`gerrit-pipeline/scripts/telemetry_defaults.json` are distributed with the
client skill.

## Runtime

- Python 3.10+
- No third-party Python package is required
- Inbound: `0.0.0.0:18080` by default
- Outbound: `https://open.feishu.cn`

## Configure

```bash
cd /path/to/telemetry-gateway
cp .env.example .env
chmod 600 .env
```

Edit `.env`:

```bash
TELEMETRY_ADMIN_TOKEN=<admin-token>
TELEMETRY_HMAC_KEYS={"gerrit-pipeline-v2.0.0":"<hmac-secret>"}
TELEMETRY_REVOKED_KEY_IDS=
FEISHU_APP_ID=<feishu-app-id>
FEISHU_APP_SECRET=<feishu-app-secret>
FEISHU_BITABLE_APP_TOKEN=<bitable-app-token>
FEISHU_BITABLE_TABLE_ID=<bitable-table-id>
```

Telemetry clients authenticate with versioned HMAC keys. Each request signs the
HTTP method, path, UTC timestamp, nonce, and body SHA-256 through
`X-GP-Key-Id`, `X-GP-Timestamp`, `X-GP-Nonce`, `X-GP-Body-SHA256`, and
`X-GP-Signature`. `TELEMETRY_ADMIN_TOKEN` is only for operator endpoints such
as `/metrics` and manual `/telemetry/flush`.

## Feishu Bitable Fields

Create a table with these field names and compatible types:

| Field | Suggested type |
|---|---|
| `event_id` | Text |
| `received_at` | Date |
| `client_time` | Date |
| `schema_version` | Text |
| `skill` | Text |
| `skill_version` | Text |
| `event_type` | Text |
| `mode` | Text |
| `success` | Checkbox |
| `duration_ms` | Number |
| `submitter_name` | Text |
| `agent` | Text |
| `repo_count` | Number |
| `error_code` | Text |
| `failure_stage` | Text |
| `install_id` | Text |
| `gateway_key_id` | Text |
| `raw_payload` | Long text |

If the Bitable field names differ, set `TELEMETRY_FIELD_MAP` to a JSON object
that maps only the changed event keys to Bitable field names. The map is merged
over the default field map. If a mapped field does not exist in the Bitable
table yet, the Gateway skips that field instead of failing the whole flush.

## Start

Foreground:

```bash
./scripts/run.sh
```

Background with pid/log files:

```bash
./scripts/ensure-running.sh
tail -f logs/telemetry-gateway.log
```

Stop:

```bash
./scripts/stop.sh
```

Incoming requests only write to SQLite and return `202`; Feishu writes are
handled by the background flusher or the manual flush endpoint. Queued events
are marked as `sending` before the gateway writes to Feishu, so parallel
flushes do not send the same queued event at the same time. If the process exits
while sending, rows older than
`TELEMETRY_IN_FLIGHT_TIMEOUT_SECONDS` are retried.

## Crontab Keepalive

For a normal user deployment without systemd linger:

```bash
crontab -e
```

Add:

```cron
@reboot /path/to/telemetry-gateway/scripts/ensure-running.sh
* * * * * /path/to/telemetry-gateway/scripts/ensure-running.sh
```

`ensure-running.sh` checks both the pid file and `/healthz`. If the pid exists
but the service is not responding, it stops the stale process and starts a new
one.

## User systemd

If `loginctl show-user "$USER" -p Linger` returns `Linger=yes`, user-level
systemd can be used. Install the bundled template:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/telemetry-gateway.service ~/.config/systemd/user/telemetry-gateway.service
GATEWAY_DIR="$(pwd)"
sed -i "s#/path/to/telemetry-gateway#$GATEWAY_DIR#g" \
  ~/.config/systemd/user/telemetry-gateway.service
```

Then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now telemetry-gateway
```

## Admin Runbook

The current recommended deployment is a normal user process on the target
internal server `10.70.55.96`. Use `ensure-running.sh` plus crontab keepalive
unless a server administrator later moves the service to systemd.

### Production Configuration

The target server configuration should bind only to the stable internal IP:

```bash
TELEMETRY_HOST=10.70.55.96
TELEMETRY_PORT=18080
```

The client URL remains:

```text
http://10.70.55.96:18080
```

Do not add a source IP allowlist in the Gateway unless the full client server
CIDR set is known and maintained. An incomplete allowlist will block valid
telemetry and make usage statistics incomplete. HMAC signatures remain the
primary write authorization mechanism.

### Start And Keep Alive

Start or repair the background process:

```bash
cd /home/hualei/00_COMMON/2_Repo/SKILL/telemetry-gateway
./scripts/ensure-running.sh
```

Install keepalive for user-level operation:

```cron
@reboot /home/hualei/00_COMMON/2_Repo/SKILL/telemetry-gateway/scripts/ensure-running.sh
* * * * * /home/hualei/00_COMMON/2_Repo/SKILL/telemetry-gateway/scripts/ensure-running.sh
```

`ensure-running.sh` checks the pid file and `/healthz`. If the process is not
healthy, it stops the stale pid and starts a new process.

### Stop And Restart

Stop:

```bash
./scripts/stop.sh
```

Restart after `.env` changes:

```bash
./scripts/stop.sh
./scripts/ensure-running.sh
```

Restart is required after changing HMAC keys, admin token, Feishu credentials,
Bitable table settings, host, port, or flush settings because `.env` is loaded
only at process startup.

### Daily Checks

Public liveness:

```bash
curl -i http://10.70.55.96:18080/healthz
```

Admin readiness:

```bash
curl -i http://10.70.55.96:18080/readyz \
  -H "Authorization: Bearer $TELEMETRY_ADMIN_TOKEN"
```

Queue metrics:

```bash
curl -s http://10.70.55.96:18080/metrics \
  -H "Authorization: Bearer $TELEMETRY_ADMIN_TOKEN"
```

Manual flush:

```bash
curl -s -X POST http://10.70.55.96:18080/telemetry/flush \
  -H "Authorization: Bearer $TELEMETRY_ADMIN_TOKEN"
```

Watch for `pending` or `failed` counts that continue to grow, `/readyz`
returning `bitable_unreachable`, or repeated Feishu API errors in:

```text
logs/telemetry-gateway.log
```

### Release Verification

After publishing a gerrit-pipeline version, verify that the packaged
`gerrit-pipeline/scripts/telemetry_defaults.json` `key_id` and `hmac_secret`
match `TELEMETRY_HMAC_KEYS` in the Gateway `.env`.

Then restart the Gateway and submit a signed test event:

```bash
GERRIT_PIPELINE_TELEMETRY_URL=http://10.70.55.96:18080 \
GERRIT_PIPELINE_TELEMETRY_KEY_ID=gerrit-pipeline-v2.0.0 \
GERRIT_PIPELINE_TELEMETRY_HMAC_SECRET=<same-hmac-secret> \
GERRIT_PIPELINE_TELEMETRY_INSTALL_ID=manual-test \
python3 ../gerrit-pipeline/scripts/telemetry_client.py \
  --event-type pipeline_done \
  --mode submit \
  --success true \
  --duration-ms 1000 \
  --repo-count 1 \
  --submitter-name gateway-admin \
  --strict \
  --verbose
```

Confirm `/metrics` and the Feishu Bitable record after the test event.

### Key Rotation And Revocation

`TELEMETRY_ADMIN_TOKEN` is only for administrator endpoints such as `/readyz`,
`/metrics`, and `/telemetry/flush`.

`TELEMETRY_HMAC_KEYS` is for telemetry clients and should be versioned:

```bash
TELEMETRY_HMAC_KEYS={"gerrit-pipeline-v2.0.0":"old-secret","gerrit-pipeline-v2.0.1":"new-secret"}
```

When a key is leaked or a version should stop reporting, revoke it and restart:

```bash
TELEMETRY_REVOKED_KEY_IDS=gerrit-pipeline-v2.0.0
```

Revoked clients receive `403 key_revoked`. Telemetry failures do not block
gerrit-pipeline's main submit/review/checklist/notify workflow.

### Storage Boundaries

Gateway server queue:

```text
telemetry-gateway/data/telemetry.sqlite3
```

Gateway logs:

```text
telemetry-gateway/logs/telemetry-gateway.log
```

Client-side temporary retry queue on user machines:

```text
~/.cache/gerrit-pipeline/telemetry-queue/
~/.cache/gerrit-pipeline/telemetry-dead-letter/
```

The Gateway SQLite database is the server-side queue. Client spool files are
only used when a user's machine cannot reach the Gateway.

### Common Issues

If `/healthz` fails, run `./scripts/ensure-running.sh` and inspect
`logs/telemetry-gateway.log`.

If `/readyz` returns `401`, check the admin token used in the request.

If `/readyz` returns `bitable_unreachable`, check Feishu app credentials,
Bitable app token, table id, table permissions, and outbound network access to
`https://open.feishu.cn`.

If signed test events return `401`, verify `key_id`, HMAC secret, system clock,
and that the same nonce is not being reused.

If signed test events return `403 key_revoked`, remove the key id from
`TELEMETRY_REVOKED_KEY_IDS` or update clients to a newer key id.

If `pending` grows but `failed` does not, the background flusher may be blocked
or Feishu may be slow. Use the manual flush endpoint and check logs.

If `failed` grows, inspect `last_error` in logs or query the SQLite database to
identify Feishu field, auth, or API errors.

## Health Check

```bash
GATEWAY_URL=http://10.70.55.96:18080
curl -i "$GATEWAY_URL/healthz"
curl -i "$GATEWAY_URL/readyz" \
  -H "Authorization: Bearer $TELEMETRY_ADMIN_TOKEN"
```

## Submit Test Event

```bash
GATEWAY_URL=http://10.70.55.96:18080
GERRIT_PIPELINE_TELEMETRY_URL="$GATEWAY_URL" \
GERRIT_PIPELINE_TELEMETRY_KEY_ID=gerrit-pipeline-v2.0.0 \
GERRIT_PIPELINE_TELEMETRY_HMAC_SECRET=<hmac-secret> \
GERRIT_PIPELINE_TELEMETRY_INSTALL_ID=manual-test \
python3 ../gerrit-pipeline/scripts/telemetry_client.py \
  --event-type pipeline_done \
  --mode submit \
  --success true \
  --duration-ms 12345 \
  --repo-count 1 \
  --submitter-name demo \
  --strict \
  --verbose
```

Metrics require the admin token:

```bash
curl -s "$GATEWAY_URL/metrics" \
  -H "Authorization: Bearer $TELEMETRY_ADMIN_TOKEN"
```

Manual flush uses the admin token:

```bash
curl -s -X POST "$GATEWAY_URL/telemetry/flush" \
  -H "Authorization: Bearer $TELEMETRY_ADMIN_TOKEN"
```
