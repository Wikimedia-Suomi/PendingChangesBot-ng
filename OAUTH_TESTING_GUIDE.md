## Testing Status (Updated with Maintainer Guidance)

**Update from @zache-fi:** Use **meta.wikimedia.beta.wmcloud.org** for local testing. This doesn't work for Superset queries, but OAuth registration and approval can be done there. Note that beta cloud doesn't use Wikimedia's unified login, so you need to register a separate account there.

**What's Working:**
- Django Social Auth integrated with MediaWiki OAuth 1.0a backend 
- Login/logout UI implemented 
- `configure_pywikibot_oauth()` helper function ready 
- Environment variable toggle (`OAUTH_ENABLED`) working 

**Known Issues:**
- Testing on localhost requires beta cloud registration (see instructions below)
- Beta cloud requires separate account registration

## Step 1: Register Account on Beta Cloud

1. Go to https://meta.wikimedia.beta.wmcloud.org
2. Click "Create account" (this is separate from your main Wikimedia account)
3. Register with username, password, email
4. Verify your email if required

## Step 2: Register OAuth Consumer on Beta Cloud

1. Go to https://meta.wikimedia.beta.wmcloud.org/wiki/Special:OAuthConsumerRegistration/propose
2. Login with your beta cloud account
3. Select "Propose new OAuth 1.0a consumer" (Pywikibot doesn't support OAuth 2.0 yet)
4. Fill out the registration form:
   - **Application name:** PendingChangesBot test
   - **Consumer version:** 1.0
   - **Application description:** PendingChangesBot is FlaggedRevs automatic review bot (https://github.com/Wikimedia-Suomi/PendingChangesBot-ng)
   - **OAuth callback URL:** `http://127.0.0.1:8000/`
   - **Check this box:** "Allow consumer to specify a callback in requests and use 'callback' URL above as a required prefix"
   - **Contact email:** Your email address
   - **Applicable project:** `*` (all projects)
   - **Types of grants:** "Request authorization for specific permissions"
   - **Applicable grants:**
     - Edit existing pages
     - Create, edit, and move pages
     - Patrol changes to pages
     - Rollback changes to pages
5. Submit the proposal
6. Save the credentials you receive:
   - **Consumer token:** e.g., `ef713d806fa7c02a1b9bd15252fb0ffa`
   - **Secret token:** e.g., `c3d97b740f96fcb1e06d368687ee23a3bebbe08f`

## Step 3: Set Up Environment Variables

Based on maintainer's configuration, set these environment variables (replace with your actual credentials from Step 2):

```bash
export OAUTH_ENABLED=true
export SOCIAL_AUTH_MEDIAWIKI_KEY=your_consumer_token_here
export SOCIAL_AUTH_MEDIAWIKI_SECRET=your_consumer_secret_here
export SOCIAL_AUTH_MEDIAWIKI_URL=https://meta.wikimedia.beta.wmcloud.org/w/index.php
export SOCIAL_AUTH_MEDIAWIKI_CALLBACK=http://127.0.0.1:8000/oauth/complete/mediawiki/
```

**Example (using dummy tokens):**
```bash
export OAUTH_ENABLED=true
export SOCIAL_AUTH_MEDIAWIKI_KEY=ef713d806fa7c02a1b9bd15252fb0ffa
export SOCIAL_AUTH_MEDIAWIKI_SECRET=c3d97b740f96fcb1e06d368687ee23a3bebbe08f
export SOCIAL_AUTH_MEDIAWIKI_URL=https://meta.wikimedia.beta.wmcloud.org/w/index.php
export SOCIAL_AUTH_MEDIAWIKI_CALLBACK=http://127.0.0.1:8000/oauth/complete/mediawiki/
```

Note: These only last for your current terminal session. For a more permanent setup, you can add them to your `~/.zshrc` file or create an `app/.env` file.

## Step 4: Start the Server

```bash
cd app
python3 manage.py runserver
```

If everything's configured correctly, the server should start up with OAuth enabled.

## Step 5: Test the OAuth Login

1. Open http://127.0.0.1:8000/ in your browser
2. You should see a "Login with Wikimedia" button in the top right corner
3. Click the button and you'll be redirected to meta.wikimedia.beta.wmcloud.org
4. Login with your **beta cloud account** (not your regular Wikimedia account)
5. Authorize the application on the OAuth page
6. You should get redirected back to http://127.0.0.1:8000/
7. After successful login, you should see your username and a "Logout" button instead of the login button

**Important:** Make sure you're using your beta cloud credentials, not your main Wikimedia account!

## Step 6: Verify the OAuth Tokens Are Stored

Open the Django shell to check if everything was saved correctly:

```bash
cd app
python3 manage.py shell
```

Then run this code to check the stored OAuth data:

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
    print("\nWARNING: No access_token found in extra_data!")
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

While still in the Django shell, test if Pywikibot can use the OAuth credentials:

```python
from reviews.views import configure_pywikibot_oauth

# Try configuring Pywikibot with the OAuth credentials
try:
    site = configure_pywikibot_oauth(user, 'meta.wikimedia.org')
    print(f"\nSuccess! Pywikibot is working with OAuth")
    print(f"Site family: {site.family}")
    print(f"Site code: {site.code}")
    print(f"Logged in as: {site.username()}")
except Exception as e:
    print(f"\nError: {e}")
```

If everything works, you should see:
```
Success! Pywikibot is working with OAuth
Site family: meta
Site code: meta
Logged in as: YourWikimediaUsername
```

Type `exit()` when you're done.

## Step 7: Test Logout

1. Go back to http://127.0.0.1:8000/ in your browser
2. Click the "Logout" button
3. You should see the "Login with Wikimedia" button appear again
4. The user session should be cleared

## What Should Work When Testing Is Complete

Here's what we're expecting to see when everything's working:

- OAuth consumer registered on meta.wikimedia.org
- Environment variables configured properly
- Server starts without any errors when OAUTH_ENABLED is true
- Login button appears when you're not logged in
- Clicking login redirects you to Wikimedia's OAuth authorization page
- After authorizing, you get redirected back to the app
- Your username and logout button show up after login
- User record gets created in the database
- UserSocialAuth record is created with provider='mediawiki'
- OAuth tokens (oauth_token and oauth_token_secret) are stored in extra_data
- The `configure_pywikibot_oauth()` function successfully authenticates with Pywikibot
- Pywikibot can access the user's identity
- Logout works and clears the session
