# Django OAuth Authentication for Production

## Purpose

This guide shows how to implement **Django OAuth login** for the PendingChangesBot web interface in production environments (Toolforge). This allows users to authenticate using their Wikimedia accounts, similar to [Wikikysely](https://wikikysely-dev.toolforge.org/en/).

> **For local development setup**, see the [BotPassword section in CONTRIBUTING.md](../CONTRIBUTING.md#configuring-authentication).

---

## Why Django OAuth?

**The Problem:**
- Production bot needs to run on behalf of authenticated users
- Each user should use their own Wikimedia credentials
- Current setup requires manual Pywikibot configuration per user

**The Solution:**
- Users log in via the web UI with their Wikimedia account
- Django captures and stores OAuth credentials
- These credentials are passed to Pywikibot for API operations
- Each review/patrol action is performed as the logged-in user

**Implementation Status:**
This is a **roadmap document** for future implementation. The OAuth 2.0 integration with Django is not yet implemented in this codebase. This guide provides the necessary steps for when you're ready to implement this feature in production.

---

## Implementation Guide

### Step 1: Register OAuth 2.0 Client

1. Visit: https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose
2. Click **"Propose an OAuth 2.0 client"**
3. Fill in the registration form:
   - **Application name**: `PendingChangesBot-Production`
   - **Consumer version**: `1.0`
   - **Application description**: Brief description of your bot's purpose
   - **Do NOT check** "This consumer is for use only by [your name]" - we need multi-user access
   - **OAuth "callback" URL**: `https://your-toolforge-url.toolforge.org/oauth/callback/`
     - Note: OAuth 2.0 requires exact URL match (no wildcards)
   - **Contact email address**: Your email
   - **Applicable project**: `*` (all projects)
   - **Client is confidential**: ✓ Check this (for server-side apps)
   - **Allowed OAuth2 grant types**:
     - ✓ Authorization code
     - ✓ Refresh token
   - **Types of grants**: Select **"Request authorization for specific permissions"**
   - **Applicable grants** (only check what you need - avoid risky grants):
     - ✓ **Basic rights** (required)
     - ✓ **Edit existing pages** (needed for reviewing)
     - ✓ **Patrol changes to pages** (needed for approval)
     - **High-volume (bot) access** (optional - only if needed)
     - **Rollback changes to pages** (optional - has vandalism risk)

     **Note**: Grants with risk ratings (vandalism, security) should only be requested if absolutely necessary. See the form's "Risky grants" explanation for details.
   - **Allowed IP ranges**: Use default (`0.0.0.0/0` and `::/0`)
   - **Allowed pages for editing**: Leave blank (allow all pages)
   - ✓ **Check the acknowledgment box** (required - acknowledges the Application Policy)
4. **Submit** the application

   You'll immediately receive:
   ```
   Your OAuth 2.0 client request has been received. An administrator will
   review your request; you will receive a notification when it gets approved.

   You have been assigned a client application key of [long hex string]
   and a client application secret of [long hex string].
   Please record these for future reference.
   ```

   **Important Notes**:
   - **Save your Client Key and Secret immediately** - you won't see them again!
   - Your client is in **pending approval** status (usually approved in 1-2 days)
   - Test apps with "test" in the name or localhost callbacks may be ignored
   - For test apps needing multi-user access or longer duration, request approval at [Steward requests/Miscellaneous](https://meta.wikimedia.org/wiki/Steward_requests/Miscellaneous)
   - You'll receive a notification when an administrator approves your request

### Step 2: Install Dependencies

**Note**: The `social-auth-app-django` library's MediaWiki backend primarily supports OAuth 1.0a. For OAuth 2.0 integration, you may need to implement a custom backend or use direct OAuth 2.0 flow. See the [MediaWiki OAuth 2.0 documentation](https://www.mediawiki.org/wiki/OAuth/Owner-only_consumers#OAuth_2.0) for implementation details.

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

# OAuth Configuration
AUTHENTICATION_BACKENDS = (
    'social_core.backends.mediawiki.MediaWiki',
    'django.contrib.auth.backends.ModelBackend',
)

SOCIAL_AUTH_MEDIAWIKI_KEY = 'YOUR_CLIENT_APPLICATION_KEY'  # From OAuth registration
SOCIAL_AUTH_MEDIAWIKI_SECRET = 'YOUR_CLIENT_APPLICATION_SECRET'  # From OAuth registration
SOCIAL_AUTH_MEDIAWIKI_URL = 'https://meta.wikimedia.org/w/index.php'
SOCIAL_AUTH_MEDIAWIKI_CALLBACK = 'https://your-toolforge-url.toolforge.org/oauth/callback/'

# IMPORTANT: Use environment variables in production!
# SOCIAL_AUTH_MEDIAWIKI_KEY = os.environ.get('OAUTH_CLIENT_KEY')
# SOCIAL_AUTH_MEDIAWIKI_SECRET = os.environ.get('OAUTH_CLIENT_SECRET')
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

**`redirect_uri_mismatch` error**
- Callback URL must match exactly (include trailing slash)
- Check `SOCIAL_AUTH_MEDIAWIKI_CALLBACK` in settings matches OAuth registration

**`Invalid client_id` error**
- Verify `SOCIAL_AUTH_MEDIAWIKI_KEY` matches your **Client application key** from OAuth registration
- The key is a long hexadecimal string (e.g., `c1edfd44cddb9a9271898d8875a0a7b5`)

**User authenticated but Pywikibot operations fail**
- Check `get_user_pywikibot_credentials()` function
- Verify social auth extra_data contains access tokens
- Check [MediaWiki OAuth documentation](https://www.mediawiki.org/wiki/OAuth/For_Developers) for implementation details

---

## Security Best Practices

- **Never commit OAuth credentials to version control**
  - Client application key and secret should never be in your code
  - Add them to `.gitignore` if stored in files
- **Use environment variables** for production:
  ```bash
  export OAUTH_CLIENT_KEY="your_client_application_key"
  export OAUTH_CLIENT_SECRET="your_client_application_secret"
  ```
- **Toolforge secure storage**: Use Toolforge's credential management for production
- **Regenerate immediately** if credentials are accidentally exposed
- **Minimal permissions**: Only request grants you actually need - avoid risky grants
- **Review your OAuth clients** regularly at https://meta.wikimedia.org/wiki/Special:OAuthManageConsumers/proposed

