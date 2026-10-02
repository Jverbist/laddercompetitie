# Azure Ubuntu VM deployment

Use Caddy as the HTTPS reverse proxy. Caddy automatically obtains and renews Let's Encrypt certificates when the domain points to the VM and ports 80 and 443 are reachable.

1. Create a DNS `A` record from your final hostname to the Azure VM public IP.
2. In the Azure Network Security Group, allow inbound TCP `80` and `443`. Do not expose `8001`.
3. Install Git, Python 3.12+, PostgreSQL, and Caddy; create a dedicated `laddercompetitie` Linux user.
4. Clone the repository to `/opt/laddercompetitie`, create `.venv`, and install the package.
5. Create `/etc/laddercompetitie/laddercompetitie.env` with production-only secrets and `SESSION_HTTPS_ONLY=true`.
6. Copy `laddercompetitie.service` to `/etc/systemd/system/`, then run `sudo systemctl daemon-reload && sudo systemctl enable --now laddercompetitie`.
7. Replace `ladder.example.com` in `Caddyfile.example`, copy it to `/etc/caddy/Caddyfile`, and run `sudo systemctl reload caddy`.

Use PostgreSQL in production. SQLite is only suitable for local development; add Alembic migrations before the first production deployment.
