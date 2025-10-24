Please check out the contribution guide ([CONTRIBUTION.md](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md)) before making any contributions.

# PendingChangesBot

PendingChangesBot is a Django application that inspects pending changes on Wikimedia
projects using the Flagged Revisions API. It fetches the 50 oldest pending pages for a
selected wiki, caches their pending revisions together with editor metadata, and exposes a
Vue.js interface for reviewing the results.

## Installation

1. **Fork the repository**
   - A fork is a new repository that shares code and visibility settings with the original “upstream” repository. Forks are often used to iterate on ideas or changes before they are proposed back to the upstream repository.
   - For more details about how to fork a repository, please check out the [github docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) for it.
2. **Clone the repository**
   - Using SSH ([requires setup of ssh keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh))
   ```bash
   git clone git@github.com:Wikimedia-Suomi/PendingChangesBot-ng.git
   cd PendingChangesBot-ng
   ```
   - Using HTTPS
   ```bash
   git clone https://github.com/Wikimedia-Suomi/PendingChangesBot-ng.git
   cd PendingChangesBot-ng
   ```
3. **Check your python version** (recommended)
   - On **Windows**:
   ```bash
   python --version
   ```
   - On **macOS / Linux**:
   ```bash
   python3 --version
   ```
   Install if not found \*for python3 you need to install pip3
4. **Create and activate a virtual environment** (recommended)
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: .venv\\Scripts\\activate
   ```
5. **Install Python dependencies**

   - On **Windows**:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

   - On **macOS / Linux**:

   ```bash
   pip3 install --upgrade pip
   pip3 install -r requirements.txt
   ```

6. **Install pre-commit hooks** (recommended for contributors)
   ```bash
   pre-commit install
   ```
   This will automatically format and lint your code before each commit.

## Authentication Setup

PendingChangesBot requires authentication to interact with Wikimedia APIs. For local development, the simplest method is using **BotPassword**.

Pywikibot needs to log in to [meta.wikimedia.org](https://meta.wikimedia.org) and approve
Superset's OAuth client before the SQL queries in `SupersetQuery` will succeed. Follow
the steps below once per user account that will run PendingChangesBot:

### Quick Start (BotPassword)

1. **Move to app directory**
   All pywikibot and manage.py commands should be run in the app directory.
   ```bash
   cd app
   ```

2. **Create a Bot Password** at <https://meta.wikimedia.org/wiki/Special:BotPasswords>

3. **Copy configuration files:**
   ```bash
   cp user-config.py.example user-config.py
   cp user-password.py.example user-password.py
   ```

4. **Create a Pywikibot configuration**
   ```bash
   echo "usernames['meta']['meta'] = 'WIKIMEDIA_USERNAME'" > user-config.py
   ```

5. **Update credentials** in `user-password.py` with your BotPassword details

6. **Log in with Pywikibot**

   - Using management command:
   ```bash
   python manage.py auth_with_username_and_password
   ```

   - Or on **Windows**:
   ```bash
   python -m pywikibot.scripts.login -site:meta
   ```

   - Or on **macOS / Linux**:
   ```bash
   python3 -m pywikibot.scripts.login -site:meta
   ```

   The command should report `Logged in on metawiki` and create a persistent login
   cookie at `~/.pywikibot/pywikibot.lwp`.

7. **Approve Superset's OAuth client**
   - While still logged in to Meta-Wiki in your browser, open
     <https://superset.wmcloud.org/login/>.
   - Authorize the OAuth request for Superset. After approval you should be redirected
     to Superset's interface.

**For complete setup instructions** (including OAuth 1.0a for production deployment and Django OAuth integration), see the [**Authentication Guide**](docs/AUTHENTICATION.md).

## Running the database migrations

```bash
cd app
```

On **Windows**:

```bash
python manage.py makemigrations
python manage.py migrate
```

- On **macOS / Linux**:

```bash
python3 manage.py makemigrations
python3 manage.py migrate
```

## Running the application

The Django project serves both the API and the Vue.js frontend from the same codebase.

```bash
cd app
```

- On **Windows**:

```bash
python manage.py runserver
```

- On **macOS / Linux**:

```bash
python3 manage.py runserver
```

Open <http://127.0.0.1:8000/> in your browser to use the interface. JSON endpoints are
available under `/api/wikis/<wiki_id>/…`, for example `/api/wikis/1/pending/`.

## Running unit tests

Unit tests live in the Django backend project. Run them from the `app/` directory so Django can locate the correct settings module.

```bash
cd app
```

- On **Windows**:

```bash
python manage.py test
```

- On **macOS / Linux**:

```bash
python3 manage.py test
```

## Code Coverage

Run tests with coverage measurement:

```bash
cd app
coverage run --source='.' manage.py test
```

View coverage report in terminal:

```bash
coverage report
```

Generate and view HTML coverage report:

```bash
coverage html
open htmlcov/index.html  # On macOS
# Or navigate to htmlcov/index.html in your browser
```

## Code Formatting and Linting

This project uses [Ruff](https://docs.astral.sh/ruff/) for code formatting and linting.

**Note:** If you installed pre-commit hooks (step 5 above), formatting and linting happen automatically before each commit. You don't need to run these commands manually.

### Manual Commands

```bash
# Format code
ruff format app/

# Check and fix linting issues
ruff check app/ --fix
```

If you are working inside a virtual environment, ensure it is activated before executing the command.

After these steps Pywikibot will be able to call Superset's SQL Lab API without running
into `User not logged in` errors, and PendingChangesBot can fetch pending revisions
successfully.
