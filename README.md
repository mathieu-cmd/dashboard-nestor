# dashboard-nestor

Margelijst-dashboard voor Nestor — leest live uit de Prato Postgres en
levert CSV-exports met filters.

Endpoints:

- `GET /health` — Railway healthcheck.
- `GET /` — info over beschikbare endpoints.
- `GET /prato/test-connection` — sanity check op Prato Postgres.
- `GET /prato/export/diag` — introspectie van klant-bronnen.
- `GET /prato/export.csv?<filters>` — margelijst-export als CSV.

## Filters op `/prato/export.csv`

Geen filter = volledige historiek.

| Filter | Type | Multi-value |
|---|---|---|
| `jaar` | integer | ✓ |
| `kwartaal` | integer | ✓ |
| `maand` | integer | ✓ |
| `week` | integer | ✓ |
| `vestigingseenheidreferentieid` | text exact | ✓ |
| `klantreferentieid` | text exact | ✓ |
| `persoonreferentieid` | text exact | ✓ |
| `klantnaam` | LIKE %term% | ✗ |
| `familienaam` | LIKE %term% | ✗ |
| `voornaam` | LIKE %term% | ✗ |

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

Grain: één rij per (jaar, kwartaal, maand, week, vestiging, klant,
persoon). Lonen sluiten wekelijks af.

`marge = omzet_gefactureerd + omzet_te_factureren − kost`
`margeperuur = marge / verloonde_uren`

## Stack

FastAPI · psycopg3 · Railway · Nixpacks.

## Deploy

Railway-service binnen het bestaande `mathieus-agent`-project zodat de
static outbound IPs gedeeld worden met invoice-bundler. Anders moet er
nieuwe IP-whitelisting aangevraagd worden bij Prato.

### Environment variables

| Variable | Verplicht | Default | Wat het is |
|---|---|---|---|
| `PRATO_DB_HOST` | ✓ | — | `psqlfs-r-cluster1-prod-002.postgres.database.azure.com` |
| `PRATO_DB_PORT` | | `5432` | |
| `PRATO_DB_USER` | ✓ | — | `reporter_nestor_nestor` |
| `PRATO_DB_PASSWORD` | ✓ | — | komt uit Railway Variables, nooit in code |
| `PRATO_DB_NAME` | ✓ | — | de Nestor-database UUID |
| `PRATO_DB_SSLMODE` | | `require` | |
| `PRATO_DB_STATEMENT_TIMEOUT_MS` | | `300000` (5 min) | Hoger voor zware queries |
| `DATA_DIR` | | `/data` | Volume mount path |
| `SECRET_KEY` | | — | Niet gebruikt in v0.1, reservering voor latere sessies |

### Custom domain

DNS van `nestor.be`: voeg toe
```
CNAME dashboard  <waarde-uit-Railway>
```

## Geen authenticatie in v0.1

URL is publiek toegankelijk voor wie 'm kent. Hou de URL discreet of
voeg later auth toe (Google SSO met `@nestor.be`-domein in de roadmap).

## Rate-limiting

30 requests per minuut per IP (in-memory, single-worker assumption).
`/health` wordt uitgesloten zodat Railway-healthchecks niet limited zijn.
