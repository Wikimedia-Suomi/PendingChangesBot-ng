# API Documentation

## Overview

PendingChangesBot provides a REST API for managing pending changes on Wikimedia projects. The API allows you to fetch pending pages, run autoreview checks, manage wiki configurations, and access review statistics.

**Base URL:** `http://localhost:8000` (development) or your production URL

**Authentication:** No authentication required for public endpoints (may change in production)

**Response Format:** JSON

## Table of Contents

1. [Reviews API](#reviews-api)
   - [List Wikis](#1-list-wikis)
   - [Refresh Pending Pages](#2-refresh-pending-pages)
   - [Get Pending Pages](#3-get-pending-pages)
   - [Get Page Revisions](#4-get-page-revisions)
   - [Run Autoreview Checks](#5-run-autoreview-checks)
   - [Clear Cache](#6-clear-cache)
   - [Wiki Configuration](#7-wiki-configuration)
   - [List Available Checks](#8-list-available-checks)
   - [Manage Enabled Checks](#9-manage-enabled-checks)
   - [Fetch Diff HTML](#10-fetch-diff-html)
2. [Statistics API](#statistics-api)
   - [Get Statistics](#11-get-statistics)
   - [Get Chart Data](#12-get-chart-data)
   - [Refresh Statistics](#13-refresh-statistics)
   - [Clear Statistics](#14-clear-statistics)
   - [Get Flagged Revisions Statistics](#15-get-flagged-revisions-statistics)
   - [Get Review Activity](#16-get-review-activity)
   - [Get Available Months](#17-get-available-months)
3. [Data Models](#data-models)
4. [Error Handling](#error-handling)

---

## Reviews API

### 1. List Wikis

Get all available wikis with their configuration.

**Endpoint:** `GET /api/wikis/`

**Parameters:** None

**Response:**
```json
{
  "wikis": [
    {
      "id": 1,
      "name": "English Wikipedia",
      "code": "en",
      "api_endpoint": "https://en.wikipedia.org/w/api.php",
      "configuration": {
        "blocking_categories": [],
        "auto_approved_groups": [],
        "ores_damaging_threshold": 0.0,
        "ores_goodfaith_threshold": 0.0,
        "ores_damaging_threshold_living": 0.0,
        "ores_goodfaith_threshold_living": 0.0
      }
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/api/wikis/
```

---

### 2. Refresh Pending Pages

Fetch and cache the 50 oldest pending pages for a wiki.

**Endpoint:** `POST /api/wikis/<int:pk>/refresh/`

**Parameters:**
- `pk` (path, required) - Wiki ID

**Response:**
```json
{
  "pages": [123, 456, 789]
}
```

**Error Response (502):**
```json
{
  "error": "Error message describing what went wrong"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/wikis/1/refresh/
```

---

### 3. Get Pending Pages

Get all cached pending pages and their revisions for a wiki.

**Endpoint:** `GET /api/wikis/<int:pk>/pending/`

**Parameters:**
- `pk` (path, required) - Wiki ID

**Response:**
```json
{
  "pages": [
    {
      "pageid": 123,
      "title": "Example Page",
      "pending_since": "2024-11-06T10:30:45.123456Z",
      "stable_revid": 999,
      "revisions": [
        {
          "revid": 1000,
          "parentid": 999,
          "timestamp": "2024-11-06T10:30:45.123456Z",
          "age_seconds": 3600,
          "user_name": "Editor1",
          "change_tags": ["tag1", "tag2"],
          "comment": "Edit summary",
          "categories": ["Category:Example"],
          "sha1": "abc123def456",
          "editor_profile": {
            "usergroups": ["user", "autoreviewed"],
            "is_blocked": false,
            "is_bot": false,
            "is_autopatrolled": true,
            "is_autoreviewed": true
          }
        }
      ]
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/api/wikis/1/pending/
```

---

### 4. Get Page Revisions

Get all revisions for a specific pending page.

**Endpoint:** `GET /api/wikis/<int:pk>/pages/<int:pageid>/revisions/`

**Parameters:**
- `pk` (path, required) - Wiki ID
- `pageid` (path, required) - Page ID

**Response:**
```json
{
  "pageid": 123,
  "revisions": [
    {
      "revid": 1000,
      "parentid": 999,
      "timestamp": "2024-11-06T10:30:45.123456Z",
      "age_seconds": 3600,
      "user_name": "Editor1",
      "change_tags": [],
      "comment": "Edit summary",
      "categories": ["Category:Example"],
      "sha1": "abc123def456",
      "editor_profile": {
        "usergroups": ["user"],
        "is_blocked": false,
        "is_bot": false,
        "is_autopatrolled": false,
        "is_autoreviewed": false
      }
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/api/wikis/1/pages/123/revisions/
```

---

### 5. Run Autoreview Checks

Run autoreview checks on a specific page (dry-run only).

**Endpoint:** `POST /api/wikis/<int:pk>/pages/<int:pageid>/autoreview/`

**Parameters:**
- `pk` (path, required) - Wiki ID
- `pageid` (path, required) - Page ID

**Response:**
```json
{
  "pageid": 123,
  "title": "Example Page",
  "mode": "dry-run",
  "results": [
    {
      "check_id": "blocking_categories",
      "check_name": "Blocking Categories",
      "passed": true,
      "message": "No blocking categories found"
    },
    {
      "check_id": "ores_scores",
      "check_name": "ORES Scores",
      "passed": false,
      "message": "Damaging score exceeds threshold"
    }
  ]
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/wikis/1/pages/123/autoreview/
```

---

### 6. Clear Cache

Clear all cached pending pages for a wiki.

**Endpoint:** `POST /api/wikis/<int:pk>/clear/`

**Parameters:**
- `pk` (path, required) - Wiki ID

**Response:**
```json
{
  "cleared": 42
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/wikis/1/clear/
```

---

### 7. Wiki Configuration

Get or update wiki-specific configuration.

**Endpoint:** `GET /PUT /api/wikis/<int:pk>/configuration/`

**Parameters:**
- `pk` (path, required) - Wiki ID

**Request Body (PUT only):**
```json
{
  "blocking_categories": ["Category:Spam", "Category:Vandalism"],
  "auto_approved_groups": ["autoreviewed", "editor"],
  "ores_damaging_threshold": 0.6,
  "ores_goodfaith_threshold": 0.4,
  "ores_damaging_threshold_living": 0.5,
  "ores_goodfaith_threshold_living": 0.3
}
```

**Configuration Fields:**
- `blocking_categories` (array) - Categories that block approval
- `auto_approved_groups` (array) - User groups to auto-approve
- `ores_damaging_threshold` (float, 0.0-1.0) - Threshold for ORES damaging score
- `ores_goodfaith_threshold` (float, 0.0-1.0) - Threshold for ORES goodfaith score
- `ores_damaging_threshold_living` (float, 0.0-1.0) - Stricter threshold for biographies of living persons
- `ores_goodfaith_threshold_living` (float, 0.0-1.0) - Stricter threshold for biographies of living persons

**GET Response:**
```json
{
  "blocking_categories": ["Category:Spam"],
  "auto_approved_groups": ["autoreviewed"],
  "ores_damaging_threshold": 0.5,
  "ores_goodfaith_threshold": 0.3,
  "ores_damaging_threshold_living": 0.4,
  "ores_goodfaith_threshold_living": 0.2
}
```

**Error Response (400):**
```json
{
  "error": "ores_damaging_threshold must be between 0.0 and 1.0"
}
```

**Examples:**
```bash
# Get configuration
curl http://localhost:8000/api/wikis/1/configuration/

# Update configuration
curl -X PUT http://localhost:8000/api/wikis/1/configuration/ \
  -H "Content-Type: application/json" \
  -d '{
    "blocking_categories": ["Category:Spam"],
    "ores_damaging_threshold": 0.5
  }'
```

---

### 8. List Available Checks

Get all available autoreview checks with their metadata.

**Endpoint:** `GET /api/checks/`

**Parameters:** None

**Response:**
```json
{
  "checks": [
    {
      "id": "bot_user",
      "name": "Bot User",
      "priority": 1
    },
    {
      "id": "user_block",
      "name": "User Block",
      "priority": 2
    },
    {
      "id": "blocking_categories",
      "name": "Blocking Categories",
      "priority": 3
    }
  ]
}
```

**Available Checks:**
- `bot_user` - Detects edits by bot users
- `user_block` - Detects edits by blocked users
- `auto_approved_groups` - Checks if user is in auto-approved groups
- `ores_scores` - Checks ORES (Objective Revision Evaluation Service) scores for edit quality
- `blocking_categories` - Checks for blocking categories
- `render_errors` - Detects rendering errors in wikitext
- `article_to_redirect` - Detects article-to-redirect conversions
- `broken_wikicode` - Detects broken wiki syntax
- `invalid_isbn` - Detects invalid ISBN codes
- `manual_unapproval` - Detects manual unapproval tags
- `superseded_additions` - Detects superseded text additions

**Example:**
```bash
curl http://localhost:8000/api/checks/
```

---

### 9. Manage Enabled Checks

Get or update which autoreview checks are enabled for a wiki.

**Endpoint:** `GET /PUT /api/wikis/<int:pk>/checks/`

**Parameters:**
- `pk` (path, required) - Wiki ID

**Request Body (PUT only):**
```json
{
  "enabled_checks": ["bot_user", "blocking_categories", "ores_scores"]
}
```

**GET Response:**
```json
{
  "enabled_checks": ["bot_user", "blocking_categories", "ores_scores"],
  "all_checks": [
    "bot_user",
    "user_block",
    "auto_approved_groups",
    "ores_scores",
    "blocking_categories",
    "render_errors",
    "article_to_redirect",
    "broken_wikicode",
    "invalid_isbn",
    "manual_unapproval",
    "superseded_additions"
  ]
}
```

**Error Response (400):**
```json
{
  "error": "enabled_checks must be a list of check IDs"
}
```

**Examples:**
```bash
# Get enabled checks
curl http://localhost:8000/api/wikis/1/checks/

# Update enabled checks
curl -X PUT http://localhost:8000/api/wikis/1/checks/ \
  -H "Content-Type: application/json" \
  -d '{"enabled_checks": ["bot_user", "blocking_categories"]}'
```

---

### 10. Fetch Diff HTML

Fetch and cache HTML diff from Wikipedia.

**Endpoint:** `GET /api/wikis/fetch-diff/`

**Parameters:**
- `url` (query, required) - Full URL to diff page

**Response:** HTML content (cached for 1 hour)

**Error Response (400):**
```json
{
  "error": "Missing 'url' parameter"
}
```

**Error Response (500):**
```json
{
  "error": "Connection error or timeout details"
}
```

**Example:**
```bash
curl "http://localhost:8000/api/wikis/fetch-diff/?url=https://en.wikipedia.org/w/index.php?diff=123456"
```

---

## Statistics API

### 11. Get Statistics

Get cached review statistics for a wiki with optional filters.

**Endpoint:** `GET /api/wikis/<int:pk>/statistics/`

**Parameters:**
- `pk` (path, required) - Wiki ID
- `reviewer` (query, optional) - Filter by reviewer username
- `reviewed_user` (query, optional) - Filter by reviewed user username
- `time_filter` (query, optional) - "all", "day", or "week" (default: "all")
- `exclude_auto_reviewers` (query, optional) - "true" or "false" (default: "false")
- `limit` (query, optional) - Number of records (default: 100)

**Response:**
```json
{
  "metadata": {
    "last_refreshed_at": "2024-11-06T10:30:45.123456Z",
    "last_data_loaded_at": "2024-11-05T10:30:45.123456Z",
    "total_records": 5000,
    "oldest_review_timestamp": "2024-10-01T00:00:00Z",
    "newest_review_timestamp": "2024-11-06T23:59:59Z"
  },
  "top_reviewers": [
    {
      "reviewer_name": "Reviewer1",
      "review_count": 150
    }
  ],
  "top_reviewed_users": [
    {
      "reviewed_user_name": "Editor1",
      "review_count": 200
    }
  ],
  "records": [
    {
      "reviewer_name": "Reviewer1",
      "reviewed_user_name": "Editor1",
      "page_title": "Example Page",
      "page_id": 123,
      "reviewed_revision_id": 1000,
      "pending_revision_id": 999,
      "reviewed_timestamp": "2024-11-06T10:30:45.123456Z",
      "pending_timestamp": "2024-11-06T09:30:45.123456Z",
      "review_delay_days": 1.5
    }
  ]
}
```

**Example:**
```bash
curl "http://localhost:8000/api/wikis/1/statistics/?time_filter=week&limit=50"
```

---

### 12. Get Chart Data

Get chart data for review statistics visualization.

**Endpoint:** `GET /api/wikis/<int:pk>/statistics/charts/`

**Parameters:**
- `pk` (path, required) - Wiki ID
- `time_filter` (query, optional) - "all", "day", or "week" (default: "all")
- `exclude_auto_reviewers` (query, optional) - "true" or "false" (default: "false")

**Response:**
```json
{
  "reviewers_over_time": [
    {
      "date": "2024-11-06",
      "count": 25
    }
  ],
  "pending_reviews_per_day": [
    {
      "date": "2024-11-06",
      "count": 150
    }
  ],
  "average_delay_over_time": [
    {
      "date": "2024-11-06",
      "avg_delay": 2.5
    }
  ],
  "delay_percentiles": [
    {
      "date": "2024-11-06",
      "p10": 0.5,
      "p50": 2.0,
      "p90": 5.5
    }
  ],
  "overall_stats": {
    "avg_delay": 2.3,
    "p10": 0.5,
    "p50": 2.0,
    "p90": 5.5,
    "total_reviews": 3000,
    "unique_reviewers": 50
  }
}
```

**Example:**
```bash
curl "http://localhost:8000/api/wikis/1/statistics/charts/?time_filter=week"
```

---

### 13. Refresh Statistics

Incrementally refresh statistics (fetch only new data).

**Endpoint:** `POST /api/wikis/<int:pk>/statistics/refresh/`

**Parameters:**
- `pk` (path, required) - Wiki ID

**Response:**
```json
{
  "total_records": 5000,
  "oldest_timestamp": "2024-10-01T00:00:00Z",
  "newest_timestamp": "2024-11-06T23:59:59Z",
  "is_incremental": true,
  "batches_fetched": 5,
  "batch_limit_reached": false
}
```

**Error Response (502):**
```json
{
  "error": "Error message describing what went wrong"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/wikis/1/statistics/refresh/
```

---

### 14. Clear Statistics

Clear statistics cache and reload fresh data for specified days.

**Endpoint:** `POST /api/wikis/<int:pk>/statistics/clear/`

**Parameters:**
- `pk` (path, required) - Wiki ID

**Request Body:**
```json
{
  "days": 30
}
```

**Parameters:**
- `days` (optional) - Number of days to reload (default: 30, range: 1-365)

**Response:**
```json
{
  "total_records": 5000,
  "oldest_timestamp": "2024-10-07T00:00:00Z",
  "newest_timestamp": "2024-11-06T23:59:59Z",
  "batches_fetched": 10,
  "batch_limit_reached": false,
  "days": 30
}
```

**Error Response (400):**
```json
{
  "error": "days parameter must be between 1 and 365"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/wikis/1/statistics/clear/ \
  -H "Content-Type: application/json" \
  -d '{"days": 60}'
```

---

### 15. Get Flagged Revisions Statistics

Get cached flagged revisions statistics from Superset.

**Endpoint:** `GET /api/flaggedrevs-statistics/`

**Parameters:**
- `wiki` (query, optional) - Wiki code (e.g., "en")
- `series` (query, optional) - Specific data series to return
- `start_date` (query, optional) - Start date for filtering (YYYY-MM-DD)
- `end_date` (query, optional) - End date for filtering (YYYY-MM-DD)

**Response:**
```json
{
  "data": [
    {
      "wiki": "en",
      "date": "2024-11-01",
      "totalPages_ns0": 6500000,
      "syncedPages_ns0": 6400000,
      "reviewedPages_ns0": 6450000,
      "pendingLag_average": 1.5,
      "pendingChanges": 50000
    }
  ]
}
```

**Example:**
```bash
curl "http://localhost:8000/api/flaggedrevs-statistics/?wiki=en&start_date=2024-11-01"
```

---

### 16. Get Review Activity

Get review activity data (reviewers, reviews count per day).

**Endpoint:** `GET /api/flaggedrevs-activity/`

**Parameters:**
- `wiki` (query, optional) - Wiki code (e.g., "en")
- `start_date` (query, optional) - Start date for filtering (YYYY-MM-DD)
- `end_date` (query, optional) - End date for filtering (YYYY-MM-DD)

**Response:**
```json
{
  "data": [
    {
      "wiki": "en",
      "date": "2024-11-06",
      "number_of_reviewers": 45,
      "number_of_reviews": 200,
      "number_of_pages": 180,
      "reviews_per_reviewer": 4.44
    }
  ]
}
```

**Example:**
```bash
curl "http://localhost:8000/api/flaggedrevs-activity/?wiki=en"
```

---

### 17. Get Available Months

Get list of available months for flagged revisions statistics.

**Endpoint:** `GET /api/flaggedrevs-statistics/available-months/`

**Parameters:** None

**Response:**
```json
{
  "months": [
    {
      "value": "202411",
      "label": "November 2024"
    },
    {
      "value": "202410",
      "label": "October 2024"
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/api/flaggedrevs-statistics/available-months/
```

---

## Data Models

### Core Models

**Wiki**
- `id` - Primary key
- `name` - Wiki display name
- `code` - Wiki code (unique)
- `family` - Wiki family (default: "wikipedia")
- `api_endpoint` - Full API URL
- `script_path` - Script path (default: "/w")

**PendingPage**
- `wiki` - Foreign key to Wiki
- `pageid` - Page ID
- `title` - Page title
- `stable_revid` - Last stable revision ID
- `pending_since` - Timestamp when page became pending
- `categories` - List of categories

**PendingRevision**
- `page` - Foreign key to PendingPage
- `revid` - Revision ID
- `parentid` - Parent revision ID
- `user_name` - Editor username
- `timestamp` - Edit timestamp
- `comment` - Edit summary
- `change_tags` - Tags applied to the change
- `categories` - Categories at time of revision

**EditorProfile**
- `wiki` - Foreign key to Wiki
- `username` - Editor username
- `usergroups` - List of user groups
- `is_blocked` - Whether user is blocked
- `is_bot` - Whether user is a bot
- `is_autopatrolled` - Whether user has autopatrol rights
- `is_autoreviewed` - Whether user has autoreview rights

---

## Error Handling

### HTTP Status Codes

- `200 OK` - Request succeeded
- `400 Bad Request` - Invalid parameters or request body
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error
- `502 Bad Gateway` - External service error (e.g., Wikipedia API failure)

### Error Response Format

All error responses follow this format:

```json
{
  "error": "Error message describing what went wrong"
}
```

### Common Errors

**Missing Required Parameters:**
```json
{
  "error": "Missing 'url' parameter"
}
```

**Invalid Parameter Values:**
```json
{
  "error": "ores_damaging_threshold must be between 0.0 and 1.0"
}
```

**External Service Errors:**
```json
{
  "error": "Failed to fetch data from Wikipedia API: Connection timeout"
}
```

---

## CSRF Protection

- **GET requests:** CSRF token required via Django middleware
- **POST/PUT requests:**
  - Form data: CSRF token required
  - JSON data on `@csrf_exempt` endpoints: No token needed

For POST/PUT requests with JSON, use `Content-Type: application/json` header.

---

## Rate Limiting

Currently, no rate limiting is implemented. In production, consider implementing rate limiting to prevent abuse.

---

## Caching

- **Pending pages:** Cached until manually cleared or refreshed
- **Statistics:** Cached with metadata tracking last refresh time
- **Diff HTML:** Cached for 1 hour
- **Flagged revisions statistics:** Cached from Superset queries

---

## Notes

- All timestamps are in ISO 8601 format with timezone (UTC)
- Page IDs and revision IDs are integers
- ORES scores range from 0.0 to 1.0
- Review delays are measured in days (can be fractional)

---

## See Also

- [README.md](../README.md) - Installation and setup
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
- [AUTHENTICATION.md](AUTHENTICATION.md) - Authentication setup
