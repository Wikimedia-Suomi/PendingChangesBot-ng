# OAuth Testing Guide for PR #117

## Important Note
Beta.wmflabs.org is often down or blocks IPs. Use **production Meta** for OAuth consumer registration - it works fine for local development testing!

## Step 1: Register OAuth Consumer on Production Meta

1. **Go to**: https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose
2. **Login** to Wikimedia if needed
3. **Fill out the form**:
   - **OAuth version**: OAuth 1.0a ⚠️ (NOT 2.0 - Pywikibot doesn't support it)
   - **Application name**: PendingChangesBot-ng Development
   - **Application description**: Local development testing of OAuth login for PendingChangesBot-ng
   - **Application version**: 0.1.0
   - **OAuth "callback" URL**: `http://127.0.0.1:8000/oauth/complete/mediawiki/` ⚠️ (trailing slash is CRITICAL!)
   - **Allow consumer to specify a callback**: ✓ (check this box)
   - **Applicable grants**: Select "User identity verification only" (basic auth for now)
   - **Public RSA key**: Leave blank (not needed for OAuth 1.0a)
   - **Contact email**: Your email address
4. **Submit** the proposal
5. **Copy** the **Consumer token** (key) and **Consumer secret token** - you'll need these!

## Step 2: Configure Environment Variables

Open a new terminal and export these variables (replace with your actual tokens):

```bash
export OAUTH_ENABLED=true
export SOCIAL_AUTH_MEDIAWIKI_KEY=your_consumer_token_here
export SOCIAL_AUTH_MEDIAWIKI_SECRET=your_consumer_secret_here
export SOCIAL_AUTH_MEDIAWIKI_URL=https://meta.wikimedia.org/w/index.php
```

**Note**: These will only persist in the current terminal session. For permanent setup, add them to your `~/.zshrc` or create an `app/.env` file.

## Step 3: Start the Development Server

```bash
cd app
python3 manage.py runserver
```

The server should start with OAuth enabled.

## Step 4: Test OAuth Login Flow

1. **Open browser** to: http://127.0.0.1:8000/
2. You should see a **"Login with Wikimedia"** button in the top right corner
3. **Click the button** - you'll be redirected to meta.wikimedia.org
4. **Authorize the application** on the Wikimedia OAuth page
5. You should be **redirected back** to http://127.0.0.1:8000/
6. You should now see **your username** and a **"Logout"** button instead of "Login"

## Step 5: Verify OAuth Token Storage

Open Django shell:

```bash
cd app
python3 manage.py shell
```

Check the stored OAuth data:

```python
from django.contrib.auth.models import User
from social_django.models import UserSocialAuth

# Check if user was created
users = User.objects.all()
print(f"Total users: {users.count()}")
user = users.first()
print(f"Username: {user.username}")

# Check OAuth tokens
social_auth = user.social_auth.get(provider='mediawiki')
print(f"\nProvider: {social_auth.provider}")
print(f"UID: {social_auth.uid}")
print(f"Extra data keys: {list(social_auth.extra_data.keys())}")

# Check if access token exists
if 'access_token' in social_auth.extra_data:
    access_token = social_auth.extra_data['access_token']
    print(f"\nAccess token keys: {list(access_token.keys())}")
    print(f"Has oauth_token: {'oauth_token' in access_token}")
    print(f"Has oauth_token_secret: {'oauth_token_secret' in access_token}")
else:
    print("\n⚠️ WARNING: No access_token found in extra_data!")
```

Expected output:
```
Total users: 1
Username: YourWikimediaUsername

Provider: mediawiki
UID: 12345
Extra data keys: ['access_token', 'id', 'username']

Access token keys: ['oauth_token', 'oauth_token_secret']
Has oauth_token: True
Has oauth_token_secret: True
```

## Step 6: Test Pywikibot Integration

In the same Django shell:

```python
from reviews.views import configure_pywikibot_oauth

# Try configuring Pywikibot with OAuth credentials
try:
    site = configure_pywikibot_oauth(user, 'meta.wikimedia.org')
    print(f"\n✅ SUCCESS!")
    print(f"Site family: {site.family}")
    print(f"Site code: {site.code}")
    print(f"Logged in as: {site.username()}")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
```

Expected output:
```
✅ SUCCESS!
Site family: meta
Site code: meta
Logged in as: YourWikimediaUsername
```

Type `exit()` to leave the shell.

## Step 7: Test Logout

1. Go back to http://127.0.0.1:8000/
2. Click the **"Logout"** button
3. You should see the **"Login with Wikimedia"** button again
4. User session should be cleared

## Expected Test Results Checklist

- ✅ OAuth consumer registered successfully on meta.wikimedia.org
- ✅ Environment variables set correctly
- ✅ Server starts without errors with OAUTH_ENABLED=true
- ✅ Login button appears when not authenticated
- ✅ Clicking login redirects to Wikimedia OAuth page
- ✅ Authorization succeeds and redirects back to app
- ✅ Username and logout button displayed after login
- ✅ User record created in database
- ✅ UserSocialAuth record created with provider='mediawiki'
- ✅ OAuth tokens (oauth_token, oauth_token_secret) stored in extra_data
- ✅ `configure_pywikibot_oauth()` successfully authenticates with Pywikibot
- ✅ Pywikibot can access user's identity
- ✅ Logout works and clears session

## Common Issues & Solutions

### Issue: Login button redirects but then fails silently
**Solution**: Check callback URL has trailing slash: `http://127.0.0.1:8000/oauth/complete/mediawiki/`

### Issue: Error about user groups (T353593)
**Solution**: Verify `SOCIAL_AUTH_PROTECTED_USER_FIELDS = ['groups']` is in `app/reviewer/settings.py`

### Issue: Pywikibot can't authenticate
**Solution**: 
- Check OAuth tokens exist: `social_auth.extra_data['access_token']`
- Verify consumer key/secret match what you registered
- Check wiki_domain format matches the wiki you're authenticating to

### Issue: "NoUsernameError" in Pywikibot
**Solution**: The OAuth consumer might not have been approved yet, or tokens are invalid

### Issue: Beta.wmflabs.org is blocked/down
**Solution**: Use production meta.wikimedia.org instead (works fine for local dev!)

## Cleanup After Testing

Stop the server:
```bash
# In the terminal running the server
CTRL+C
```

Clear test data (optional):
```bash
cd app
python3 manage.py shell
```

```python
from django.contrib.auth.models import User
User.objects.all().delete()
exit()
```

Unset environment variables:
```bash
unset OAUTH_ENABLED
unset SOCIAL_AUTH_MEDIAWIKI_KEY
unset SOCIAL_AUTH_MEDIAWIKI_SECRET
unset SOCIAL_AUTH_MEDIAWIKI_URL
```

## Next Steps After Successful Testing

1. Document any issues in the PR
2. Commit and push the OAuth implementation
3. Update PR description with testing notes
4. Consider adding automated tests for OAuth flow
5. Document OAuth setup in main docs/AUTHENTICATION.md
