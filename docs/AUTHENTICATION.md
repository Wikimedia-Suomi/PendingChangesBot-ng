# Authentication Setup for PendingChangesBot

## Overview

This guide covers authentication configuration for PendingChangesBot, including:
- **OAuth 1.0a** for Django web UI (production deployment)
- **Username/Password** for local development and Superset access
- **Superset third-party authentication workaround**

---

## Important: Superset Authentication

**Known Issue:** Both OAuth 1.0a and BotPassword authentication methods **do not work** with Superset (superset.toolforge.org) third-party login. See [T408286](https://phabricator.wikimedia.org/T408286) for details.

**Workaround for Local Development:**
To query Wikimedia database replicas via Superset, you must use **plain username/password authentication** for meta.wikimedia.org in your `user-config.py`:

```python
usernames['meta']['meta'] = 'YourWikimediaUsername'
password_file = "user-password.py"
```

Then create `user-password.py`:
```python
# Format: (username, password)
('YourWikimediaUsername', 'your_wikimedia_password')
```

**Note:** In production (Toolforge), Superset is not needed as you can use direct SQL connections to database replicas.

---

## Django OAuth Authentication for Production

### Purpose

This guide shows how to implement **Django OAuth login** for the PendingChangesBot web interface in production environments (Toolforge). This allows users to authenticate using their Wikimedia accounts, similar to [Wikikysely](https://wikikysely-dev.toolforge.org/en/).

---

## Why Django OAuth 1.0a?

**The Problem:**
- Production bot needs to run on behalf of authenticated users
- Each user should use their own Wikimedia credentials
- Current setup requires manual Pywikibot configuration per user

**The Solution:**
- Users log in via the web UI with their Wikimedia account (OAuth 1.0a)
- Django captures and stores OAuth credentials
- These credentials are passed to Pywikibot for API operations
- Each review/patrol action is performed as the logged-in user

**Why OAuth 1.0a (not 2.0)?**
- Pywikibot currently **only supports OAuth 1.0a** ([T323849](https://phabricator.wikimedia.org/T323849))
- OAuth 1.0a credentials can be directly passed to Pywikibot
- OAuth 2.0 support in Pywikibot is still under development

**Implementation Status:**
This is a **roadmap document** for future implementation. The OAuth 1.0a integration with Django is not yet implemented in this codebase. This guide provides the necessary steps for when you're ready to implement this feature in production.

---

## Implementation Guide

### Step 1: Register OAuth 1.0a Consumer

1. Visit: https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose
2. Click **"Propose an OAuth 1.0a consumer"**
3. Fill in the registration form:
   - **Application name**: `PendingChangesBot-Production`
   - **Consumer version**: `1.0`
   - **Application description**: Brief description of your bot's purpose
   - **Do NOT check** "This consumer is for use only by [your name]" - we need multi-user access
   - **OAuth "callback" URL**: **Leave this blank** (for OAuth 1.0a callback is optional)
   - **Applicable project**: `*` (all projects)
   - **Types of grants**: Select **"Request authorization for specific permissions"**
   - **Applicable grants** (only check what you need - avoid risky grants):
     - ✓ **Basic rights** (required)
     - ✓ **High-volume (bot) access** (recommended for production)
     - ✓ **Edit existing pages** (needed for reviewing)
     - ✓ **Patrol changes to pages** (needed for approval)
     - **Rollback changes to pages** (optional - has vandalism risk)

     **Note**: Grants with risk ratings (vandalism, security) should only be requested if absolutely necessary. See the form's "Risky grants" explanation for details.
   - **Allowed IP ranges**: Use default (`0.0.0.0/0` and `::/0`)
   - ✓ **Check the acknowledgment box** (required - acknowledges the Application Policy)
4. **Submit** the application

   After submission, you'll receive **4 tokens**:
   - Consumer Token
   - Consumer Secret
   - Access Token
   - Access Secret

   **Important**: Save all 4 tokens immediately - you won't see them again!

### Step 2: Install Dependencies

The `social-auth-app-django` library includes MediaWiki OAuth 1.0a backend support:

```bash
pip install social-auth-app-django
# OR implement custom OAuth 2.0 flow with:
pip install requests-oauthlib
```

### Step 3: Configure Django Settings

Add the following to `app/reviewer/settings.py`:

```python
INSTALLED_APPS = [
    # ... existing apps
    'social_django',
]

MIDDLEWARE = [
    # ... existing middleware
    'social_django.middleware.SocialAuthExceptionMiddleware',
]

TEMPLATES = [
    {
        'OPTIONS': {
            'context_processors': [
                # ... existing processors
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
            ],
        },
    },
]

# OAuth 1.0a Configuration
AUTHENTICATION_BACKENDS = (
    'social_core.backends.mediawiki.MediaWiki',
    'django.contrib.auth.backends.ModelBackend',
)

# Use the 4 tokens from your OAuth 1.0a consumer registration
SOCIAL_AUTH_MEDIAWIKI_KEY = 'YOUR_CONSUMER_TOKEN'  # From OAuth registration
SOCIAL_AUTH_MEDIAWIKI_SECRET = 'YOUR_CONSUMER_SECRET'  # From OAuth registration
SOCIAL_AUTH_MEDIAWIKI_URL = 'https://meta.wikimedia.org/w/index.php'

# IMPORTANT: Use environment variables in production!
# SOCIAL_AUTH_MEDIAWIKI_KEY = os.environ.get('OAUTH_CONSUMER_TOKEN')
# SOCIAL_AUTH_MEDIAWIKI_SECRET = os.environ.get('OAUTH_CONSUMER_SECRET')
```

In `app/reviewer/urls.py`:
```python
path('oauth/', include('social_django.urls', namespace='social')),
```

### Step 4: Pass Credentials to Pywikibot

```python
from social_django.models import UserSocialAuth

def get_user_pywikibot_credentials(user):
    social = user.social_auth.get(provider='mediawiki')
    return {
        'oauth_token': social.extra_data.get('access_token', {}).get('oauth_token'),
        'oauth_secret': social.extra_data.get('access_token', {}).get('oauth_token_secret'),
    }
```

See the [social-auth-app-django documentation](https://python-social-auth.readthedocs.io/en/latest/configuration/django.html) for additional configuration options.

---

## Additional Production Notes

### BotPassword for Meta-Wiki (Superset)

For Superset data access, you'll still need BotPassword for Meta-Wiki since Superset requires web session cookies. This is already documented in [CONTRIBUTING.md](../CONTRIBUTING.md#configuring-authentication) - use the same setup with a production-appropriate bot name like `PendingChangesBot-Prod`.

### OAuth 1.0a for Direct Pywikibot Access

If your production setup requires direct Pywikibot API access (without Django), see [Pywikibot OAuth documentation](https://www.mediawiki.org/wiki/Manual:Pywikibot/OAuth) for OAuth 1.0a setup.

---

## Troubleshooting

**`Invalid consumer_key` error**
- Verify `SOCIAL_AUTH_MEDIAWIKI_KEY` matches your **Consumer Token** from OAuth 1.0a registration
- Make sure you're using OAuth 1.0a tokens, not OAuth 2.0 credentials

**`Invalid token` error**
- Check that Access Token and Access Secret are correctly stored
- OAuth 1.0a requires all 4 tokens (Consumer Token, Consumer Secret, Access Token, Access Secret)

**User authenticated but Pywikibot operations fail**
- Check `get_user_pywikibot_credentials()` function
- Verify social auth extra_data contains access tokens
- Check [MediaWiki OAuth documentation](https://www.mediawiki.org/wiki/OAuth/For_Developers) for implementation details

---

## Security Best Practices

- **Never commit OAuth credentials to version control**
  - Consumer tokens and secrets should never be in your code
  - Add them to `.gitignore` if stored in files
- **Use environment variables** for production:
  ```bash
  export OAUTH_CONSUMER_TOKEN="your_consumer_token"
  export OAUTH_CONSUMER_SECRET="your_consumer_secret"
  export OAUTH_ACCESS_TOKEN="your_access_token"
  export OAUTH_ACCESS_SECRET="your_access_secret"
  ```
- **Toolforge secure storage**: Use Toolforge's credential management for production
- **Regenerate immediately** if credentials are accidentally exposed
- **Minimal permissions**: Only request grants you actually need - avoid risky grants
- **Review your OAuth clients** regularly at https://meta.wikimedia.org/wiki/Special:OAuthManageConsumers/proposed

