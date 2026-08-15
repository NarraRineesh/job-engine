# Hetzner CX33: Mongo + Typesense + Node API + Nginx

Public URL: `https://api.glowminds.in`  
Host: `157.180.95.193`

Scraping stays in GitHub Actions. This box holds Mongo (source of truth) and Typesense (search). Node API and Nginx run on the host. Mongo `27017` and Typesense `8108` bind to loopback only.

## Layout

- Docker Mongo on `127.0.0.1:27017`
- Docker Typesense on `127.0.0.1:8108`
- Node API on `127.0.0.1:8787` (systemd `job-engine-api`)
- Nginx TLS reverse proxy for `api.glowminds.in`

## DNS and firewall

- A record `api.glowminds.in` → `157.180.95.193` (DNS-only / grey cloud)
- Ingress **22, 80, 443** only (`ufw`)

## SSH

```bash
ssh -i ~/.ssh/hetzner_cx33 root@157.180.95.193
```

GitHub Actions scrape on `ubuntu-latest`, then SSH-tunnels to this box and writes Mongo (`MONGODB_URI` must use `127.0.0.1`). After a successful stream, `index-typesense.yml` SSHs and runs `npm run index`.

Repo secrets: `HETZNER_HOST=157.180.95.193`, `HETZNER_USER=root`, `HETZNER_SSH_KEY` (private OpenSSH key whose pubkey is in `/root/.ssh/authorized_keys`), `MONGODB_URI` (same localhost URI as `/opt/job-engine/.env`).

## Index (manual, after migrate-postgres finishes)

```bash
cd /opt/job-engine/api
INDEX_RECREATE=0 INDEX_PAGE=200 NODE_OPTIONS=--max-old-space-size=2048 npm run index
```

One-shot copy from Postgres: `uv run job-engine migrate-postgres` (`DATABASE_URL` in `.env`).

## Install (once)

Ubuntu on CX33 (8 GB). Docker CE, Node 22, compose, systemd unit from [`deploy/systemd/job-engine-api.service`](systemd/job-engine-api.service), Nginx from [`deploy/nginx/job-engine-api.conf`](nginx/job-engine-api.conf).

```bash
cd /opt/job-engine
docker compose up -d
cd api && npm install && npm start   # or systemd
```

Host `.env`: `MONGODB_URI`, `TYPESENSE_*`, `API_HOST=127.0.0.1`, optional `DATABASE_URL`.

```bash
sudo certbot --nginx -d api.glowminds.in --non-interactive --agree-tos -m admin@glowminds.in
```

## Check

```bash
curl -sS https://api.glowminds.in/health
curl -sS https://api.glowminds.in/v1/stats
```
