# dashboard-nestor

Margelijst-dashboard voor Nestor — lokale SQLite-cache van Prato-data,
dagelijkse auto-sync, UI met filters en CSV-download.

## Architectuur in één blik

```
                  ┌──────────────────────────────────────┐
   browser  ─────►│  dashboard.nestor.be                  │
                  │  ┌────────────────────────────────┐   │
                  │  │ FastAPI + APScheduler          │   │
                  │  │  /            UI (HTML form)   │   │
                  │  │  /prato/export.csv   uit cache │   │
                  │  │  /sync/run    manuele trigger  │   │
                  │  └─────┬──────────────────┬───────┘   │
                  │        │ daily 11:59 BE   │ read       │
                  │        ▼                  ▼            │
                  │  ┌──────────────┐  ┌──────────────┐    │
                  │  │ sync_from_   │  │ SQLite cache │    │
                  │  │ prato()      │──►/data/        │    │
                  │  └──────┬───────┘  │ margelijst.  │    │
                  └─────────┼──────────┼──sqlite──────┘    │
                            │ live query
                            ▼
                   ┌────────────────────┐
                   │ Prato Postgres     │
                   │ (read-only,        │
                   │  IP-whitelisted)   │
                   └────────────────────┘
```

## Endpoints

| Endpoint | Beschrijving |
|---|---|
| `GET /` | HTML-form met filters, Download- en Sync-knop |
| `GET /health` | Railway healthcheck |
| `GET /api/status` | JSON: cache row-count + laatste sync |
| `POST /sync/run` | Trigger manuele sync (background) |
| `GET /sync/status` | JSON: status van meest recente sync |
| `GET /prato/test-connection` | **Live** check op Prato Postgres |
| `GET /prato/export/diag` | **Live** introspectie van klant-bronnen |
| `GET /prato/export.csv?<filters>` | Margelijst-CSV uit de lokale cache |

## Filters op `/prato/export.csv`

Geen filter = volledige cache. Filters worden op de SQLite-cache toegepast.

| Filter | Type | Multi-value |
|---|---|---|
| `jaar` | integer | ✓ |
| `kwartaal` | integer | ✓ |
| `maand` | integer | ✓ |
| `week` | integer | ✓ |
| `vestigingseenheidreferentieid` | text exact | ✓ |
| `klantreferentieid` | text exact | ✓ |
| `persoonreferentieid` | text exact | ✓ |
| `klantnaam` | LIKE %term%, case-insensitive | ✗ |
| `familienaam` | LIKE %term%, case-insensitive | ✗ |
| `voornaam` | LIKE %term%, case-insensitive | ✗ |

Voorbeeld: `?jaar=2026&maand=4&maand=5&klantnaam=Smartmat`

## Output-format

CSV, semicolon-separated, UTF-8 zonder BOM, Belgische decimaalkomma.

22 kolommen in vaste volgorde — 10 dimensies + 12 measures:

```
jaar; kwartaal; maand; week;
vestigingseenheidreferentieid;
klantreferentieid; klantnaam;
persoonreferentieid; familienaam; voornaam;
loonkost; werkuitkering; bvvrijstellingen;
rszwerkgeversbijdragen; rszverminderingen; provisies;
omzet_gefactureerd; omzet_te_factureren;
kost; verloonde_uren;
marge; margeperuur
```

Grain: één rij per (jaar, kwartaal, maand, week, vestiging, klant, persoon).

`marge = omzet_gefactureerd + omzet_te_factureren − kost`
`margeperuur = marge / verloonde_uren`

## Sync

**Automatisch**: APScheduler draait elke dag om **11:59 Europe/Brussels**
de `sync_from_prato()`-functie. Bij elke sync wordt de hele
`margelijst`-tabel in SQLite **overschreven** (DELETE + INSERT) — geen
incremental.

**Manueel**: `POST /sync/run` (of via de UI). Sync draait in background;
status zichtbaar via `GET /sync/status` of in de UI (polling elke 10s).

**Log**: elke sync wordt opgeslagen in tabel `sync_meta` met
`started_at`, `ended_at`, `status` (running/ok/failed), `rows_loaded`,
`duration_ms`, `error`.

## Stack

FastAPI · psycopg3 · SQLite · APScheduler · Railway · Nixpacks.

## Deploy op Railway

Service binnen het bestaande `mathieus-agent`-project zodat de static
outbound IPs gedeeld worden met invoice-bundler (= Prato whitelist
hoeft niet aangepast te worden).

### Environment variables

| Variable | Verplicht | Default | Wat het is |
|---|---|---|---|
| `PRATO_DB_HOST` | ✓ | — | `psqlfs-r-cluster1-prod-002.postgres.database.azure.com` |
| `PRATO_DB_PORT` | | `5432` | |
| `PRATO_DB_USER` | ✓ | — | `reporter_nestor_nestor` |
| `PRATO_DB_PASSWORD` | ✓ | — | komt uit Railway Variables, nooit in code |
| `PRATO_DB_NAME` | ✓ | — | de Nestor-database UUID |
| `PRATO_DB_SSLMODE` | | `require` | |
| `PRATO_DB_STATEMENT_TIMEOUT_MS` | | `300000` | Hoger voor zware sync-query |
| `DATA_DIR` | | `/data` | Volume mount path (SQLite-cache) |
| `SECRET_KEY` | | — | Niet gebruikt in v0.2, reservering voor latere sessies |

### Volume

Mount path `/data`, 1 GB volstaat ruim voor onze schaal (~10 MB voor
~10k rijen).

### Custom domain

`dashboard.nestor.be` als CNAME naar Railway's target. **Cloudflare
proxy uit** (grijze wolk = DNS Only) — Railway regelt eigen Let's
Encrypt-cert.

## Geen authenticatie in v0.2

URL is publiek toegankelijk voor wie 'm kent. Hou de URL discreet of
voeg later auth toe (Google SSO met `@nestor.be`-domein in de roadmap).

## Rate-limiting

30 requests per minuut per IP (in-memory). `/health` uitgesloten zodat
Railway-healthchecks niet limited zijn.
