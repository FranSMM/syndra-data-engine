# Infrastructure

Production configuration for the VPS. The root `docker-compose.yml` is the local development stack; the files here are what runs in production.

| File | Purpose |
|---|---|
| `docker-compose.prod.yml` | Production stack, with every third-party image pinned to a version and digest. |
| `Caddyfile` | Sole ingress, with automatic TLS for `api.` and `demo.syndradata.com`. Returns 403 on `/metrics`. |
| `prometheus.yml` | Scrapes the API, cAdvisor, node exporter and Prometheus itself over the internal network. |
| `postgres-init.sh` | Creates `prefect_db`, the Prefect server database, the first time the Postgres volume is created. |
| `backup_syndra.sh`, `backup.cron` | Daily `pg_dump` at 03:00, keeping seven days. Installed on the VPS by hand. |

## Production stack

Eleven services on one Docker network:

- **Data:** PostgreSQL 15 (Bronze, Silver and the Prefect database), Qdrant and Redis.
- **Application:** the API and the scheduler, both from the `syndra-etl` image, the Prefect server and the Streamlit demo.
- **Observability:** Prometheus, cAdvisor and node exporter.
- **Ingress:** Caddy, the only service exposed to the internet. The origin only accepts traffic from Cloudflare.

Postgres, Qdrant, Redis, Prefect and Prometheus listen only on `127.0.0.1`. Their panels are reached through an SSH tunnel with `make web`.

## Deployment

`deploy.sh`, in the repository root, builds the images that changed, tags them with the short git SHA and points production at that tag. A rollback points it back at an earlier tag without rebuilding (ADR-022). The VPS connection is read from `VPS_USER`, `VPS_IP` and `DEPLOY_DIR` in the root `.env`.
