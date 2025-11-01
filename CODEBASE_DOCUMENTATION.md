 # Understanding PendingChangesBot-ng's Codebase

## Introduction

PendingChangesBot-ng is a Django application for reviewing Wikimedia pending changes, integrating a Vue.js frontend with a Django REST API backend. It fetches, caches, and exposes pending revisions and editor metadata from Wikimedia wikis using the Flagged Revisions API, while providing automated review suggestions based on multiple quality signals.

---

## 1. Project Overview

### Purpose

PendingChangesBot-ng pulls pending revisions from configured wikis, stores them locally, and surfaces both automated assessments and a reviewer-friendly UI so volunteers can move through a backlog quickly while seeing why a revision passed or failed. It does this by:

- Automatically fetching unreviewed edits from configured wikis
- Providing automated quality assessments using multiple signals
- Offering a streamlined review interface with rich editor context

### Technology Stack

- **Backend**: Django 4.2+ (Python 3.8–3.12) — see `app/reviewer/settings.py`
- **Frontend**: Vue.js 3 served as static files from `app/static/reviews/app.js`
- **Database**: SQLite for development, PostgreSQL for production
- **External APIs**: MediaWiki Action API, Wikimedia Superset (for SQL access to FlaggedRevs data), MediaWiki parse endpoints through Pywikibot

### Key Features

- Multi-wiki support with per-wiki configuration stored in `app/reviews/models/wiki_configuration.py`
- Automated review suggestions based on configurable checks and ORES scores
- Cached editor metadata to avoid repeated API calls in `app/reviews/models/editor_profile.py`
- Article quality signals (LiftWing predictions, Wikidata integration)
- Render error and broken wikicode detection (`app/reviews/autoreview/utils/broken_wikicode.py`)
- Statistics dashboards backed by Superset-derived caches (`app/reviews/models/flaggedrevs_statistics.py`, `app/reviews/models/review_statistics_cache.py`)
- Test mode for development and testing

---
## 2. Architecture and Design

### High-Level Architecture

The system consists of a Vue.js user interface communicating over HTTP/JSON with Django REST endpoints. Business logic resides in a services layer (WikiClient, Statistics client, LiftWing client), which coordinates with Django models that persist data in the database.

### Design Principles

- **Separation of concerns** between models, services, and presentation
- **Caching** to reduce external API load
- **Error resilience** and graceful degradation when upstream services fail
- **Extensibility** for adding wikis, signals, and review checks

### Directory Structure

Top-level Django project with settings and URLs; a "reviews" app containing models, services, views, auto-review logic, migrations, and tests; and folders for static assets and templates.

---

## 3. Core Models

The application uses Django ORM models to represent wikis, pending changes, editors, and cached data.

### WikiConfiguration

- **Purpose**: Stores per-wiki settings and connection details
- **Location**: `app/reviews/models/wiki_configuration.py`
- **Key fields**: Numeric wiki identifier, site URL, database name for analytics queries, enablement flags, test mode fields (including a list of test revision IDs), and redirect aliases
- **Methods**: Determine API endpoints and whether a wiki is active

### PendingPage

- **Purpose**: Represents an article with pending changes
- **Key fields**: Wiki reference, page ID, title, namespace, categories, associated Wikidata identifier, and last-fetched timestamp
- **Methods**: Update categories and Wikidata identifiers; detect whether the page falls under biographies of living persons (BLP)

### PendingRevision

- **Purpose**: Represents an unreviewed edit to a page
- **Key fields**: Page reference, revision identifiers (current and parent), timestamp, edit summary, editor username, byte-size delta, cached statistics and predictions (Superset and LiftWing), render error count, and superseded similarity
- **Methods**: Generate diff links, fetch or return cached statistics and predictions, check for render errors

### EditorProfile

- **Purpose**: Tracks editor reputation and history for a wiki
- **Location**: `app/reviews/models/editor_profile.py`
- **Key fields**: Username, edit counts (overall and article namespace), warning counts, block status, former-bot indicator, registration date, and last-updated timestamp
- **Methods**: Update the profile from MediaWiki, assess trust levels, compute a reputation score

---

## 4. Services Layer

The services layer handles external API interactions and business logic.

### WikiClient

- **Purpose**: Primary interface to MediaWiki and related APIs
- **Key functions**:
  - Retrieves lists of pending revisions (using analytics sources or, in test mode, selected revision IDs)
  - Fetches page info (title, namespace, categories), revision metadata, editor info (including warnings and block status), categories, and Wikidata IDs
  - Implements retries with exponential backoff, logs failures, and degrades gracefully

### StatisticsClient

- **Purpose**: Fetches article and editor statistics from Wikimedia Superset where available
- **Key functions**:
  - Retrieves page-level analytics (views, edit counts, protection status)
  - Retrieves editor-level metrics
  - Uses authenticated access and caches results in the corresponding revision data

### LiftWingClient

- **Purpose**: Interacts with LiftWing models for article quality predictions
- **Key functions**:
  - Returns predicted class and quality score per revision
  - Supports batch predictions
  - Caches results and allows processing to continue if the service is unavailable

---

## 5. Auto-Review System

The auto-review system automatically approves or rejects edits based on configurable rules. Checks run in sequence and stop at the first definitive outcome.

### Check Order

1. **Broken wikicode check**: Compares HTML render errors between old and new versions; reject if errors increase
2. **Superseded edit check**: Measures similarity with current content; reject if a pending edit is largely replaced
3. **Editor reputation check**: Approves if an editor meets the trust criteria (high edit counts, no blocks, low warnings, not a former bot)
4. **LiftWing quality check**: Approve if quality prediction exceeds the configured threshold
5. **BLP check**: Require manual review for biographies of living persons
6. **Large deletion check**: Require manual review for edits removing a large number of bytes

### Configuration

Each wiki sets thresholds and feature toggles:
- Auto-approve and auto-reject thresholds
- Superseded similarity threshold
- Enabling LiftWing and broken-wikicode validation

Conservative configurations may raise approval thresholds.

### Workflow Summary

Pending revisions proceed through the checks above, resulting in one of: **reject**, **approve**, or **require manual review**. Confidence can be reported alongside the recommendation.

---



## 6. API Endpoints

The application exposes RESTful endpoints through Django views.

### Key Endpoints

Declared in `app/reviews/urls.py`, implemented in `app/reviews/views.py`:

- **GET `/api/wikis/`** — List wikis and configurations
- **POST `/api/wikis/<pk>/refresh/`** — Refresh pending data from Superset
- **GET `/api/wikis/<pk>/pending/`** — Return pending pages, revisions, and editor profiles
- **GET `/api/wikis/<pk>/pages/<pageid>/revisions/`** — Detail view for one page
- **POST `/api/wikis/<pk>/clear/`** — Purge cached pending data
- **POST `/api/wikis/<pk>/pages/<pageid>/autoreview/`** — Dry-run auto-review
- **GET/PUT `/api/wikis/<pk>/configuration/`** — Read or update per-wiki config
- **GET `/api/checks/`** and **GET/PUT `/api/wikis/<pk>/checks/`** — Inspect or modify enabled check lists
- **Statistics endpoints**:
  - `/api/wikis/<pk>/statistics/`
  - `/statistics/charts/`
  - `/statistics/refresh/`
  - `/statistics/clear/`
- **FlaggedRevs aggregates**:
  - `/api/flaggedrevs-statistics/`
  - `/available-months/`
  - `/api/flaggedrevs-activity/`
- **GET `/api/wikis/fetch-diff/`** — Proxy MediaWiki diff HTML

### Authentication

Most endpoints require Django session authentication. OAuth login is available for analytics access where needed. Unauthenticated users are prompted to log in before accessing protected endpoints.

---



## 7. Frontend Interface

The Vue.js frontend provides the reviewer experience.

### Review Dashboard

- Displays pending changes with sortable columns and filters (e.g., BLP, size change, new editors)
- Includes pagination and an optional auto-refresh toggle

### Revision Detail View

- Shows a diff, editor profile, article metadata (including categories and Wikidata link), statistics, and auto-review recommendations
- Provides actions to approve, reject, or skip

### Settings Panel

- User preferences for refresh behavior, diff presentation, highlighting, and visibility of auto-review suggestions

### User Interaction Flow

1. Load dashboard and fetch pending items for a wiki
2. Select a revision to view details, diff, editor info, and auto-review result
3. Take an action (approve or reject) and proceed to the next item

---


## 8. Database Schema

Migrations for this database schema can be found in `app/reviews/migrations/`.

### Migration Highlights

- **0001**: Sets up core models
- **0002–0008**: Add Superset payloads, categories, redirect aliases, render error counts, Wikidata IDs, and superseded thresholds
- **Later migrations**: Introduce ORES thresholds, statistics caches, enabled checks, and metadata such as `max_log_id` and `last_data_loaded_at`

### Key Relationships

- **Wiki** → many PendingPage, EditorProfile, ReviewStatisticsCache, FlaggedRevsStatistics, ReviewActivity
- **Wiki** → one WikiConfiguration, one ReviewStatisticsMetadata
- **PendingPage** → many PendingRevision
- **PendingRevision** → one ModelScores

### Indexes

Ensure quick lookups on:
- `(wiki, pageid)`
- `(page, revid)`
- Reviewer names
- Timestamps

---

## 9. Configuration Management

### Django Settings

Located in `app/reviewer/settings.py`.

Environment variables define keys and toggles such as:
- LiftWing API keys
- OAuth enablement
- OAuth consumer credentials and provider URL
- Debug mode
- Secret key
- Allowed hosts
- Database connection strings

**Caching**: Uses either a file-based backend (development) or Redis (production), with typical timeouts of one hour for external data.

**Database**: SQLite is recommended for development; PostgreSQL is recommended for production.

### Per-Wiki Configuration

Stored in `WikiConfiguration` model (`app/reviews/models/wiki_configuration.py`).

Each wiki defines:
- Site URL
- Analytics database name
- Enablement
- Thresholds for auto-approval and rejection
- Superseded similarity threshold
- Feature toggles (LiftWing and broken-wikicode checks)
- Test mode
- Test revision IDs
- Redirect aliases

---

## 10. OAuth Authentication

The application supports OAuth login for accessing analytics data (e.g., Superset) where required.

### Setup Outline

- Install and configure the Django social authentication app and MediaWiki OAuth backend
- Register an OAuth consumer on the Wikimedia beta environment
- Configure callback URLs and obtain consumer credentials
- Store consumer key and secret via environment variables

### Workflow Summary

Users click "Login with Wikimedia," authorize the application on the beta environment, and are redirected back. The application establishes a session and uses authenticated credentials for subsequent analytics queries where needed.

### Pywikibot Integration

For workflows that rely on Pywikibot-formatted tokens, the system can write OAuth tokens into a local configuration so that authenticated analytics queries are possible. This step is only applicable if you use such a bridge.

---

## 11. Test Mode

### Purpose

Allows development, demos, and CI to operate on a controlled set of revisions without dependency on live data.

### Configuration

Enable test mode per wiki via the admin or an API-based configuration update. Provide a small set of representative revision IDs (e.g., high-quality edit, large deletion, BLP edit, broken wikicode, superseded edit).

### Behavior

- **Normal mode**: Queries analytics-backed pending pools of unreviewed revisions
- **Test mode**: Fetches specific revisions as if they were pending

Both modes return a consistent data shape to the frontend.

---


11. Test Mode
Purpose
- Allows development, demos, and CI to operate on a controlled set of revisions without dependency on live data.
Configuration
- Enable test mode per wiki via the admin or an API-based configuration update. Provide a small set of representative revision IDs (e.g., high-quality edit, large deletion, BLP edit, broken wikicode, superseded edit).
Behavior
 - Normal mode: queries analytics-backed pending pools of unreviewed revisions
 - Test mode: fetches specific revisions as if they were pending
 Both modes return a consistent data shape to the frontend.

## 12. Testing Framework

### Structure

Located in `app/reviews/tests/`.

- Unit tests cover models, services, auto-review decisions, and views
- Integration tests validate end-to-end flows
- Fixtures seed typical wiki configurations, pending revisions, and editor profiles

### Running Tests

Developers run the project's test suite from the application root:

```bash
cd app/
python manage.py test
```

Run individual test modules or single cases as needed.

### Coverage Focus

- Model persistence and computed fields
- Service interaction, caching, and batch behavior
- Auto-review thresholds and edge cases (BLP, vandalism-like deletions)
- API response formats, authentication requirements, and error handling

### Continuous Integration

- Pre-commit hooks enforce formatting and linting
- CI pipeline runs tests, style checks, and coverage on each push or pull request

---

## 13. Deployment and Setup

### Local Development

1. Verify Python (3.8–3.12) and Git installations
2. Clone the repository: `git clone https://github.com/Wikimedia-Suomi/PendingChangesBot-ng.git`
3. Create a virtual environment: `python3 -m venv venv && source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Run database migrations: `cd app/ && python manage.py migrate`
6. Create an optional superuser: `python manage.py createsuperuser`
7. Start the development server: `python manage.py runserver`
8. Access the frontend at `http://localhost:8000/` and admin at `http://localhost:8000/admin/`

### Production Deployment

1. Configure environment variables for security and connectivity:
   - `DEBUG=False`
   - `SECRET_KEY=your_secret_key`
   - `ALLOWED_HOSTS=example.com,www.example.com`
   - `DATABASE_URL=postgresql://user:pass@localhost/dbname`
   - API keys and OAuth credentials
2. Run database migrations: `python manage.py migrate`
3. Collect static assets: `python manage.py collectstatic --noinput`
4. Serve the application with a WSGI server (e.g., Gunicorn) and a reverse proxy (e.g., Nginx)
5. Use PostgreSQL in production

### Containerization (Optional)

A containerized setup can be provided to build and run the web service alongside a database, with environment variables for configuration and dependencies defined as services.

---

## 14. Performance Considerations

### Caching Strategy

- Cache analytics queries for one hour
- Cache LiftWing predictions for long-lived reuse
- Cache category data for one hour

Caching dramatically reduces external calls when multiple users inspect the same revision set.

### Django Query Optimization

Use related-object loading patterns (e.g., `select_related()`, `prefetch_related()`) to avoid N+1 queries when listing revisions and associated pages.

### Batch Processing

Leverage batch predictions for LiftWing and bulk database operations to minimize round trips and accelerate ingestion.

### Background Tasks (Planned)

Use a task queue (e.g., Celery) to offload long-running analytics and profile updates and to schedule periodic refreshes during low-traffic windows.

---

## 15. Security Features

### Authentication and Authorization

- Use Django session-based authentication and CSRF protection
- Store passwords with secure hashing (PBKDF2)
- Separate reviewer and admin roles; superusers manage the Django admin

### OAuth Security

- Rely on OAuth 1.0a with signature verification
- Store tokens securely (encrypted) and never expose them to the frontend

### Input Validation

- Validate all API inputs via serializers with type and range checks
- Ensure list and JSON fields are well-formed

### SQL Injection Prevention

- Use the ORM and parameterized queries for analytics requests

### Rate Limiting (Planned)

- Apply user/IP quotas to protect critical endpoints from abuse

### Data Privacy

- Process only publicly available usernames; no email addresses or private data
- Encrypt tokens and provide clear data-deletion and audit options

---

## 16. Error Handling

### Strategy

- Degrade gracefully on external failures by serving cached data when available
- Log errors for diagnostics; continue processing when optional services fail
- Map common failures to appropriate HTTP status codes (e.g., 404, 409, 500)

### Frontend Behavior

- Show user-friendly errors
- Retry when appropriate
- Fall back to defaults if data cannot be loaded

### Logging

- Use environment-specific log levels
- Separate loggers per component
- File-based logs with rotation to manage volume
- *Example*: Timeouts from prediction services are clearly tagged with revision identifiers

### Error Reporting (Planned)

- Integrate with an error-tracking service (e.g., Sentry) for stack traces, context, and alerting

---

## 17. How Components Are Connected

### Data Flow

```
Frontend (Vue.js)
       ↓
Django Views (API Endpoints)
       ↓
Auto-Review System
       ↓
Services Layer (WikiClient, StatisticsClient, LiftWingClient)
       ↓
External APIs (MediaWiki, Superset, LiftWing)
       ↓
Django Models (ORM)
       ↓
Database (SQLite/PostgreSQL)
```

### Key Interactions

- **Frontend → Views**: JSON requests for pending lists, details, and actions
- **Views → Auto-Review**: Decision and confidence returned before responding
- **Auto-Review → Services**: External data retrieval (editor info, predictions, categories)
- **Services → External APIs**: MediaWiki, analytics, and prediction endpoints
- **Models → Database**: ORM-managed persistence and caching

### Dependencies

- **Views** depend on models, services, and auto-review
- **Auto-review** depends on models and services
- **Services** depend on models and external APIs
- **Models** depend on the ORM

### Request Journey Example

1. User loads the dashboard (Vue.js)
2. Frontend sends `GET /api/wikis/1/pending/` to Django
3. View calls `WikiClient.get_pending_revisions(1)`
4. WikiClient queries Superset (or uses test revision IDs if in test mode)
5. View fetches page and editor data for each revision
6. Auto-review system evaluates each revision through checks
7. View returns JSON with pending revisions, editor profiles, and auto-review recommendations
8. Frontend displays dashboard with results
9. User clicks on a revision to view details
10. Frontend sends `GET /api/wikis/1/pages/<pageid>/revisions/`
11. View returns detailed revision data with diff, editor info, and auto-review result
12. User approves or rejects the revision
13. Frontend sends `POST /api/wikis/1/pages/<pageid>/review/` with decision
14. View processes the review action and updates the database
15. Frontend updates the dashboard and moves to the next revision

---


## 18. Conclusion

The PendingChangesBot-ng project combines multiple data sources, machine learning predictions, and automated checks to streamline review of Wikimedia pending changes. Its modular, layered architecture, strong testing posture, and per-wiki configurability make it suitable for diverse community needs.

### Key Takeaways

- Clear separation between frontend, API, services, and data layers
- Automated review using editor reputation, content quality, and wikicode validation
- Performance through caching, batching, and efficient queries
- Flexibility via per-wiki configuration and extensible services and checks

### For Contributors

See the project's `CONTRIBUTING.md` for guidelines on submitting bug fixes and new features.

### For Developers

Please use this document as a reference to understand and extend the codebase. For implementation details, consult inline comments and docstrings in the repository.

### Repository

Latest updates: https://github.com/Wikimedia-Suomi/PendingChangesBot-ng

