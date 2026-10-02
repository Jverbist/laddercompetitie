# Azure Ubuntu VM deployment

The production deployment uses PostgreSQL, systemd, and Caddy. FastAPI listens only on `127.0.0.1:8001`; Caddy exposes the public HTTPS site and manages Let's Encrypt certificates.

## 1. Azure and DNS

1. Create an Ubuntu 24.04 LTS VM and attach a static public IP.
2. Add an `A` record for the final hostname, such as `ladder.example.com`, to that IP.
3. In the Network Security Group, allow inbound TCP `80` and `443` from the internet. Restrict SSH port `22` to your own IP. Do not allow ports `7001` or `8001`.

Wait until the DNS record resolves to the VM before configuring Caddy; certificate issuance depends on it.

## 2. Prepare Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git python3 python3-venv postgresql caddy
sudo useradd --system --create-home --shell /usr/sbin/nologin laddercompetitie
sudo install -d -o laddercompetitie -g laddercompetitie /opt/laddercompetitie
sudo install -d -o root -g laddercompetitie -m 750 /etc/laddercompetitie
```

## 3. PostgreSQL

```bash
sudo -u postgres createuser --pwprompt laddercompetitie
sudo -u postgres createdb --owner=laddercompetitie laddercompetitie
```

Use the password selected above only in the production environment file.

## 4. Application and environment

```bash
sudo -u laddercompetitie git clone https://github.com/Jverbist/laddercompetitie.git /opt/laddercompetitie
sudo -u laddercompetitie python3 -m venv /opt/laddercompetitie/.venv
sudo -u laddercompetitie /opt/laddercompetitie/.venv/bin/pip install /opt/laddercompetitie
sudo cp /opt/laddercompetitie/deploy/laddercompetitie.env.example /etc/laddercompetitie/laddercompetitie.env
sudo chown root:laddercompetitie /etc/laddercompetitie/laddercompetitie.env
sudo chmod 640 /etc/laddercompetitie/laddercompetitie.env
sudoedit /etc/laddercompetitie/laddercompetitie.env
```

Set the real hostname in `ALLOWED_HOSTS`, use unique strong secrets, and leave `AUTO_CREATE_SCHEMA=false`. The environment file is intentionally outside Git.

## 5. Service and migrations

```bash
sudo cp /opt/laddercompetitie/deploy/laddercompetitie.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now laddercompetitie
sudo systemctl status laddercompetitie
```

The `ExecStartPre` command runs `alembic upgrade head` before every application start. This creates the schema on the first deployment and applies future versioned migrations.

## 6. HTTPS with Caddy

Replace `ladder.example.com` in the Caddy configuration with the hostname from step 1:

```bash
sudoedit /opt/laddercompetitie/deploy/Caddyfile.example
sudo cp /opt/laddercompetitie/deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy obtains and renews the certificate automatically. Verify `https://ladder.example.com/api/health` after it is active.

## Updates and backups

For every release, pull the trusted branch, install locked dependencies when they change, then restart the service:

```bash
sudo -u laddercompetitie git -C /opt/laddercompetitie pull --ff-only
sudo -u laddercompetitie /opt/laddercompetitie/.venv/bin/pip install /opt/laddercompetitie
sudo systemctl restart laddercompetitie
sudo journalctl -u laddercompetitie -n 100 --no-pager
```

Back up PostgreSQL regularly. A basic manual backup is:

```bash
sudo -u postgres pg_dump -Fc laddercompetitie > /var/backups/laddercompetitie-$(date +%F).dump
```
