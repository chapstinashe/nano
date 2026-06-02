# Production edge security

Place a WAF-capable reverse proxy in front of the Flask app. The app listens on port 5000; do not expose it directly to the public internet.

## Option A: Azure Front Door (recommended on Azure)

1. Deploy the app to Azure Container Apps or App Service (HTTPS only).
2. Create an **Azure Front Door** profile with:
   - HTTPS redirect and TLS 1.2 minimum
   - **Web Application Firewall** policy (OWASP 3.2 managed rules)
   - Rate limiting rule: e.g. 300 requests/min per IP on `/api/*`
3. Point Front Door origin to your container/app hostname.
4. Set app env:
   - `ALLOWED_ORIGINS=https://your-front-door-domain.azurefd.net`
   - `COOKIE_SECURE=1`
   - `FLASK_DEBUG=0`
   - `RATE_LIMIT_STORAGE_URI=redis://<redis-host>:6379/0`
   - `AZURE_KEY_VAULT_URL=https://<vault>.vault.azure.net/`
5. Enable **Managed Identity** on the app and grant **Key Vault Secrets User** on the vault.
6. Ship `security.audit` logs to **Azure Monitor / Log Analytics** (Diagnostic settings on the app).

## Option B: Cloudflare

1. Put the app behind Cloudflare proxy (orange cloud).
2. Enable **WAF managed rules** and **Bot Fight Mode** (or Super Bot Fight Mode).
3. Add rate limiting rules for `/api/auth/*` and `/api/ingest/*`.
4. Set `ALLOWED_ORIGINS` to your Cloudflare hostname.

## Redis for global rate limits

Docker Compose already wires Redis:

```bash
docker compose up -d
```

For Azure, use **Azure Cache for Redis** and set:

```bash
RATE_LIMIT_STORAGE_URI=rediss://:<key>@<name>.redis.cache.windows.net:6380/0
```

## Penetration testing

Before handling sensitive data:

1. Run the CI security workflow (pip-audit + bandit).
2. Commission an external pen test or use OWASP ZAP against staging.
3. Review `security.audit` JSON logs for abuse patterns after launch.
