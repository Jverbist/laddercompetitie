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

## Volgende bouwstappen

1. Configureer vóór productie `https_only=True` voor de sessiecookie, voeg CSRF-bescherming toe aan formulieracties en vervang lokale login desgewenst door bedrijfs-SSO/OIDC.
2. Plan `process-deadlines` elke minuut via een worker, bijvoorbeeld Celery + Redis of een platform scheduler. Voeg daarin ook de 24-uursreminder toe.
3. Voeg Alembic-migraties toe vóór de eerste gedeelde of productieomgeving; `create_all` is geschikt voor de lokale start.
4. Bouw een responsive frontend tegen deze API voor dashboard, ranking, uitdagingen en administratie.
5. Voeg de finale toe als afzonderlijk, configureerbaar bracket-formaat nadat het wedstrijdschema voor de Top 10 is bepaald.
