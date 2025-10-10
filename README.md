Please check out the contribution guide ([CONTRIBUTION.md](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md)) before making any contributions.

# PendingChangesBot

PendingChangesBot is a Django application that inspects pending changes on Wikimedia
projects using the Flagged Revisions API. It fetches the 50 oldest pending pages for a
selected wiki, caches their pending revisions together with editor metadata, and exposes a
Vue.js interface for reviewing the results.

## Installation

1. **Fork the repository**
   * A fork is a new repository that shares code and visibility settings with the original “upstream” repository. Forks are often used to iterate on ideas or changes before they are proposed back to the upstream repository.
   * For more details about how to fork a repository, please check out the [github docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) for it.
2. **Clone the repository**
   * Using SSH ([requires setup of ssh keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh))
   ```bash
   git clone git@github.com:Wikimedia-Suomi/PendingChangesBot-ng.git
   cd PendingChangesBot-ng
   ```
   * Using HTTPS
    ```bash
   git clone https://github.com/Wikimedia-Suomi/PendingChangesBot-ng.git
   cd PendingChangesBot-ng
   ```
3. **Create and activate a virtual environment** (recommended)
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: .venv\\Scripts\\activate
   ```
4. **Install Python dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Configuring Pywikibot with OAuth

Pywikibot requires OAuth 1.0a authentication to interact with Wikimedia APIs.

### Quick Setup

1. **Copy the example configuration:**
   ```bash
   cp user-config.py.example user-config.py
   ```

2. **Register an OAuth 1.0a consumer:**
   - Visit: <https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose>
   - Click "Propose an OAuth 1.0a consumer"
   - Leave callback URL **blank**
   - Select grants: Basic rights, High-volume (bot) access, Edit existing pages, Patrol changes
   - Check "This consumer is for use only by [your username]"

3. **Add credentials to `user-config.py`:**
   - Replace `YourWikipediaUsername` with your actual username
   - Replace OAuth token placeholders with your actual tokens

4. **Test your setup:**
   ```bash
   python3 -m pywikibot.scripts.login -site:meta
   ```
   Expected output: `Logged in on meta:meta as YourUsername`

5. **Approve Superset's OAuth client:**
   - Visit <https://superset.wmcloud.org/login/>
   - Authorize the OAuth request

📖 **For detailed step-by-step instructions, troubleshooting, and security best practices**, see [CONTRIBUTING.md](CONTRIBUTING.md#configuring-pywikibot-with-oauth).

## Running the database migrations

```bash
cd app
python manage.py makemigrations
python manage.py migrate
```

## Running the application

The Django project serves both the API and the Vue.js frontend from the same codebase.

```bash
cd app
python manage.py runserver
```

Open <http://127.0.0.1:8000/> in your browser to use the interface. JSON endpoints are
available under `/api/wikis/<wiki_id>/…`, for example `/api/wikis/1/pending/`.

## Running unit tests

Unit tests live in the Django backend project. Run them from the `app/` directory so Django can locate the correct settings module.

```bash
cd app
python manage.py test
```

## Running Flake8

Run Flake8 from the repository root to lint the code according to the configuration provided in `.flake8`.

```bash
flake8
```

If you are working inside a virtual environment, ensure it is activated before executing the command.

After these steps Pywikibot will be able to call Superset's SQL Lab API without running
into `User not logged in` errors, and PendingChangesBot can fetch pending revisions
successfully.
