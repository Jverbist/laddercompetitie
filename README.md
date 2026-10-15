# Laddercompetitie

Een overzichtelijke FastAPI-basis voor de kantoor-laddercompetitie. De applicatie bevat de kernregels uit de briefing: maximaal vijf plaatsen omhoog uitdagen, blokkering tijdens een actieve wedstrijd, resultaatbevestiging, automatische forfeit na 48 uur en het wisselen van posities wanneer de uitdager wint.

## Projectstructuur

```text
app/
  api/          HTTP-routes en authenticatie-afhankelijkheden
  core/         configuratie uit .env
  services/     zuivere competitielogica en businessregels
  db.py         databaseverbinding en sessies
  models.py     SQLAlchemy-datamodellen
  schemas.py    API-invoer- en uitvoermodellen
  main.py       FastAPI-applicatie
scripts/
  seed.py       standaardspellen en eerste admins aanmaken
tests/
  test_competition.py  kernregels van de ladder
```

De routes bevatten zo weinig mogelijk logica. Elke regel die de uitkomst van de competitie beïnvloedt staat in `app/services/competition.py`, zodat deze één keer wordt geïmplementeerd en rechtstreeks getest kan worden.

## Stap voor stap starten

1. Maak een virtuele omgeving en installeer de ontwikkelafhankelijkheden:

   ```bash
   cd laddercompetitie
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -e '.[dev]'
   ```

2. Maak het configuratiebestand en vervang de voorbeeld-e-mailadressen:

   ```bash
   cp .env.example .env
   ```

3. Vul de standaardspellen en de twee administratoraccounts:

   ```bash
   .venv/bin/python scripts/seed.py
   ```

4. Stel in `.env` minstens deze twee waarden veilig in:

   ```dotenv
   ADMIN_BOOTSTRAP_PASSWORD=kies-hier-een-uniek-wachtwoord-van-minstens-12-tekens
   SESSION_SECRET=maak-hier-een-lange-willekeurige-secret-van
   ```

   De seed maakt vervolgens de beheerders uit `ADMIN_EMAILS` aan. Zij gebruiken tijdelijk `ADMIN_BOOTSTRAP_PASSWORD` en moeten dat wachtwoord bij de eerste aanmelding wijzigen.

5. Heb je de database al aangemaakt vóór de loginuitbreiding? Werk de bestaande lokale database dan bij en voer het seedscript opnieuw uit:

   ```bash
   .venv/bin/python scripts/migrate_local.py
   .venv/bin/python scripts/seed.py
   ```

6. Start de applicatie op poort 7001:

   ```bash
   .venv/bin/uvicorn app.main:app --reload --port 7001
   ```

7. Open `http://127.0.0.1:7001/login` voor de aanmeldpagina of `http://127.0.0.1:7001/docs` voor de interactieve API-documentatie.

8. Voer de kernregeltets uit:

   ```bash
   .venv/bin/python -m pytest
   ```

## Aanmelden en beheerdersaccount

De tijdelijke e-mailheader is vervangen door een sessiegebaseerde login. Het seedscript maakt de accounts uit `ADMIN_EMAILS` aan; standaard zijn dat:

| Account | Tijdelijk wachtwoord |
|---|---|
| `christophe@example.com` | de waarde van `ADMIN_BOOTSTRAP_PASSWORD` in `.env` |
| `yasmine@example.com` | de waarde van `ADMIN_BOOTSTRAP_PASSWORD` in `.env` |

Na aanmelden met een beheerdersaccount opent `/admin`. Daar staat het overzicht van deelnemers, spellen en recente uitdagingen, met links naar de beveiligde API-documentatie. Een admin kan accounts blokkeren of deactiveren en een tijdelijk wachtwoord instellen via de adminroutes. Dat wachtwoord dwingt de gebruiker bij de volgende login tot een nieuw persoonlijk wachtwoord.

Wanneer een admin het wachtwoord niet meer weet, stel je eerst een nieuwe `ADMIN_BOOTSTRAP_PASSWORD` in `.env` in en voer je expliciet uit:

```bash
.venv/bin/python scripts/seed.py --reset-admin-passwords
```

Dit reset uitsluitend de wachtwoorden van de e-mailadressen in `ADMIN_EMAILS`; spelers, uitdagingen en ranking blijven behouden.

## Belangrijkste API-stappen

1. Een admin voegt spelers toe met `POST /api/admin/users`; ieder nieuw account moet bij de eerste login een eigen wachtwoord kiezen.
2. Een deelnemer bekijkt `GET /api/eligible-opponents`; die route toont alleen beschikbare spelers die één tot vijf plaatsen hoger staan.
3. De deelnemer maakt een uitdaging met `POST /api/challenges`.
4. Eén deelnemer registreert de winnaar via `POST /api/challenges/{id}/result`.
5. De tegenstander bevestigt die uitslag via `POST /api/challenges/{id}/confirm`. Pas dan wordt de ranking aangepast.
6. Een geplande taak roept `POST /api/admin/process-deadlines` aan. Elke verlopen actieve uitdaging wordt automatisch gewonnen door de uitdager en verwerkt volgens dezelfde ladderregel.
7. Admins beheren toegang met `PATCH /api/admin/users/{id}/access`, stellen een tijdelijk wachtwoord in met `POST /api/admin/users/{id}/reset-password`, annuleren open uitdagingen met `POST /api/admin/challenges/{id}/cancel` en bekijken alle uitdagingen met `GET /api/admin/challenges`.

## Draaien op een Azure VM (SQLite, systemd en Caddy)

Dit is de eenvoudige opzet met SQLite in de projectmap. Voor PostgreSQL en een eigen service-gebruiker, zie `deploy/README.md`.

### 1. Netwerk en DNS

- Maak een DNS A-record voor de hostnaam (bv. `ctf.exn.be`) naar het publieke IP van de VM.
- Laat in het Azure NSG inkomend TCP `80` en `443` toe. Poort `8000` hoeft niet open te staan.

### 2. Configuratie in `.env`

```dotenv
ADMIN_EMAILS=naam@exclusive-networks.be,collega@exclusive-networks.be
ADMIN_BOOTSTRAP_PASSWORD=een-uniek-wachtwoord-van-minstens-12-tekens
SESSION_SECRET=een-lange-willekeurige-string
ALLOWED_HOSTS=ctf.exn.be
SESSION_HTTPS_ONLY=true
REGISTRATION_START=2026-10-16T00:00:00+02:00
COMPETITION_START=2026-10-19T00:00:00+02:00
QUALIFICATION_DEADLINE=2026-11-13T23:59:59+01:00
REGISTRATION_ENABLED=true
REGISTRATION_EMAIL_DOMAINS=exclusive-networks.be
TEAMS_WEBHOOK_URL=
TEAMS_EMAIL_DOMAIN_MAP=
```

Zet `SESSION_HTTPS_ONLY=true` pas aan nadat HTTPS werkt, anders lukt het aanmelden niet. `REGISTRATION_EMAIL_DOMAINS` beperkt registratie tot die e-maildomeinen (kommagescheiden). Leeg betekent dat iedereen zich kan registreren. `REGISTRATION_ENABLED=false` schakelt registratie uit.

Registratie opent op `REGISTRATION_START`, uitdagen kan vanaf `COMPETITION_START` tot en met `QUALIFICATION_DEADLINE`.

Optioneel: zet `TEAMS_WEBHOOK_URL` op de URL van een Power Automate Teams-webhook-flow. Bij elke nieuwe uitdaging stuurt de app een Adaptive Card met de namen, ladderposities, deadline en het uitdaging-ID. Bewaar deze URL alleen in `.env` op de server; deel of commit hem niet. Herstart daarna de service met `sudo systemctl restart laddercompetitie`.

De payload bevat ook de namen en e-mailadressen van uitdager en uitgedaagde, en een mention van de uitgedaagde. Wijkt het Teams-account af van het opgeslagen adres, zet dan `TEAMS_EMAIL_DOMAIN_MAP=exclusive-networks.be=exclusive-networks.com` (meerdere paren gescheiden door komma's).

### 3. Database voorbereiden

```bash
cd ~/laddercompetitie
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py
```

`seed.py` maakt de standaardspellen en de admins uit `ADMIN_EMAILS` aan en mag meermaals uitgevoerd worden. Nieuwe admins komen onderaan de ladder. Een bestaand account wordt hierdoor niet admin, zie "Admins beheren" hieronder.

### 4. HTTPS met Caddy

```bash
sudo apt update && sudo apt install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
ctf.exn.be {
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy haalt het Let's Encrypt-certificaat zelf op en vernieuwt het. Poort 80 en 443 moeten vrij zijn.

### 5. De app permanent laten draaien (zonder SSH-sessie)

```bash
sudo tee /etc/systemd/system/laddercompetitie.service >/dev/null <<'EOF'
[Unit]
Description=Laddercompetitie FastAPI application
After=network.target

[Service]
Type=exec
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/laddercompetitie
ExecStartPre=/home/ubuntu/laddercompetitie/.venv/bin/alembic upgrade head
ExecStart=/home/ubuntu/laddercompetitie/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now laddercompetitie
sudo systemctl status laddercompetitie
curl -i https://ctf.exn.be/api/health
```

De app leest `.env` zelf uit de `WorkingDirectory`. Uvicorn luistert enkel op `127.0.0.1`, zodat alleen Caddy bereikbaar is van buitenaf.

| Doel | Commando |
|---|---|
| Logs live volgen | `sudo journalctl -u laddercompetitie -f` |
| Herstarten na een codewijziging of `.env`-wijziging | `sudo systemctl restart laddercompetitie` |
| Stoppen | `sudo systemctl stop laddercompetitie` |

Zonder `--reload` wordt nieuwe code pas actief na een herstart.

### 6. Updates uitrollen

```bash
cd ~/laddercompetitie
cp laddercompetitie.db laddercompetitie.db.bak
git pull --ff-only
.venv/bin/pip install .
sudo systemctl restart laddercompetitie
```

De migraties worden bij elke start automatisch uitgevoerd via `ExecStartPre`.

### Admins beheren

De rol wordt niet automatisch aangepast voor bestaande accounts. Gebruik de database:

```bash
sqlite3 laddercompetitie.db "UPDATE users SET role='ADMIN' WHERE email='naam@exclusive-networks.be';"
sqlite3 laddercompetitie.db "UPDATE users SET role='PARTICIPANT' WHERE email='naam@exclusive-networks.be';"
sqlite3 laddercompetitie.db "SELECT rank, email, role FROM users;"
```

Installeer `sqlite3` indien nodig met `sudo apt install -y sqlite3`. De wijziging werkt meteen, een herstart is niet nodig.

### Spellen beheren

Zet een spel inactief in plaats van het te verwijderen, zodat de geschiedenis behouden blijft:

```bash
.venv/bin/python -c "
from app.db import SessionLocal
from app.models import Game
with SessionLocal.begin() as db:
    for g in db.query(Game).filter(Game.name.in_(['Bowling', 'Mikado'])):
        g.is_active = False
"
```

Een nieuw spel toevoeg je aan `STANDARD_GAMES` in `scripts/seed.py` en je voert daarna `scripts/seed.py` uit.

### Competitie resetten

In `/admin` staat onder "Gevarenzone" de knop **Reset en schud de ladder**. Die verwijdert alle uitdagingen en plaatst alle spelers in een willekeurige volgorde. Maak vooraf een back-up met `cp laddercompetitie.db laddercompetitie.db.bak`. De reset kan niet ongedaan gemaakt worden.

## Spelregels in de applicatie

- De uitdager kiest een tegenstander tot vijf plaatsen hoger. De uitgedaagde kiest het spel.
- Na een afgeronde wedstrijd moet je twee andere wedstrijden spelen voor je dezelfde tegenstander opnieuw mag uitdagen (`REMATCH_COOLDOWN_TURNS` in `app/services/competition.py`).
- Nieuwe spelers beginnen onderaan de ladder.
- Het dashboard heeft een spelregelpagina op `/regels`, en het beheerpaneel toont alle uitdagingen met hun winnaar.

## Volgende bouwstappen

1. Configureer vóór productie `https_only=True` voor de sessiecookie, voeg CSRF-bescherming toe aan formulieracties en vervang lokale login desgewenst door bedrijfs-SSO/OIDC.
2. Plan `process-deadlines` elke minuut via een worker, bijvoorbeeld Celery + Redis of een platform scheduler. Voeg daarin ook de 24-uursreminder toe.
3. Voeg Alembic-migraties toe vóór de eerste gedeelde of productieomgeving; `create_all` is geschikt voor de lokale start.
4. Bouw een responsive frontend tegen deze API voor dashboard, ranking, uitdagingen en administratie.
5. Voeg de finale toe als afzonderlijk, configureerbaar bracket-formaat nadat het wedstrijdschema voor de Top 10 is bepaald.
