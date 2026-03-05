# Toolforge Deployment Guide

This guide covers deploying PendingChangesBot-ng to [Wikimedia Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge).

## Prerequisites

- A Toolforge account with access to the `pendingchangesbot` tool
- SSH access to Toolforge (`ssh <username>@login.toolforge.org`)
- Familiarity with Toolforge's webservice framework

## Project Structure

```
PendingChangesBot-ng/
├── app/                    # Django project root
│   ├── manage.py           # Django management commands
│   ├── reviewer/           # Django settings and URL config
│   │   ├── settings.py     # Auto-detects Toolforge via IS_TOOLFORGE env var
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── reviews/            # Core review logic (models, services, checks)
│   ├── review_statistics/  # Statistics dashboard (direct SQL to replicas)
│   ├── bot_control/        # Bot control panel (start/stop, permissions)
│   ├── templates/          # HTML templates
│   └── static/             # CSS, JS (Vue.js, Chart.js)
├── requirements.txt
└── docs/
```

## Step 1: Set Up the Tool Environment

```bash
ssh <username>@login.toolforge.org
become pendingchangesbot

# Clone the repository
git clone https://github.com/Wikimedia-Suomi/PendingChangesBot-ng.git
cd PendingChangesBot-ng

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Configure Environment Variables

Create or edit `~/.profile` to set required environment variables:

```bash
export IS_TOOLFORGE=true
export DJANGO_SECRET_KEY="<generate-a-strong-secret-key>"
```

Generate a secret key:
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Step 3: Database Setup

Toolforge uses a shared MySQL database. The tool database is configured automatically in `settings.py` when `IS_TOOLFORGE=true`:

- **Database**: `s57224__pendingchangesbot`
- **Host**: `tools.db.svc.wikimedia.cloud`
- **Credentials**: Read from `~/replica.my.cnf` (auto-provisioned by Toolforge)

Run migrations:

```bash
cd app
python3 manage.py migrate
```

## Step 4: Collect Static Files

WhiteNoise serves static files in production. Collect them:

```bash
cd app
python3 manage.py collectstatic --noinput
```

## Step 5: Configure Pywikibot

Create `app/user-config.py`:

```python
usernames['meta']['meta'] = 'PendingChangesBot'
```

Log in:
```bash
cd app
python3 -m pywikibot.scripts.login -site:meta
```

## Step 6: Start the Web Service

```bash
webservice python3.11 start
```

The application will be available at: https://pendingchangesbot.toolforge.org/

## Step 7: Load Statistics Data

To populate the statistics dashboard with historical data:

```bash
cd app

# Load FlaggedRevs statistics
python3 manage.py load_flaggedrevs_statistics_direct_sql --wiki fi

# Load individual review records
python3 manage.py load_review_statistics_direct_sql --wiki fi --limit 10000
```

## Key URLs

| URL | Description |
|-----|-------------|
| `/` | Main review interface |
| `/bot/` | Bot control panel |
| `/statistics/` | Public statistics dashboard |
| `/swagger/` | Swagger API documentation |
| `/redoc/` | ReDoc API documentation |

## Wiki Replica Access

The statistics module connects directly to wiki replica databases for data:

- **Host pattern**: `<wiki>wiki.analytics.db.svc.wikimedia.cloud`
- **Database pattern**: `<wiki>wiki_p`
- **Credentials**: `~/replica.my.cnf`

All SQL queries use **parameterized queries** to prevent SQL injection.

## Authentication

The bot control panel uses **Django session-based authentication**. Users authenticate via their Wikimedia account, and permissions are determined by MediaWiki user groups:

| MediaWiki Group | Bot Role | Permissions |
|-----------------|----------|-------------|
| sysop, bureaucrat | Admin | Start/stop bot, change settings |
| reviewer, editor, autoreview | Reviewer | Manual page reviews |
| (default) | Public | View status and statistics |

See [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) for OAuth setup details.

## Running Tests

```bash
cd app
python3 manage.py test
```

## Troubleshooting

**Database connection errors**: Verify `~/replica.my.cnf` exists and has correct credentials.

**Static files not loading**: Run `python3 manage.py collectstatic --noinput` and restart the webservice.

**Bot won't start**: Check logs in the `logs/` directory (`bot_stdout.log`, `bot_stderr.log`).

**Wiki replica connection refused**: Ensure you're connecting from within the Toolforge environment (not from login nodes).
