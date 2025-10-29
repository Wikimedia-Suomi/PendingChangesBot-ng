## Important Note
I found that beta.wmflabs.org is often down or blocks IPs, so I switched to using production Meta (meta.wikimedia.org) for OAuth consumer registration instead.

## Step 1: Register OAuth Consumer on Production Meta

1. Go to https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose
2. Login to Wikimedia if you haven't already
3. Select "Propose new OAuth 1.0a consumer" (Pywikibot doesn't support OAuth 2.0 yet)
4. Fill out the registration form:
   - Application name: PendingChangesBot-ng Development
   - Application description: Local development testing of OAuth login for PendingChangesBot-ng
   - Application version: 0.1.0
   - OAuth callback URL: `http://127.0.0.1:8000/` (just the base URL)
   - Make sure to check: "Allow consumer to specify a callback in requests and use 'callback' URL above as a required prefix"
   - Applicable grants: Select "User identity verification only"
   - Public RSA key: Leave this blank
   - Contact email: Your email address
5. Submit the proposal
6. You'll see a confirmation page saying "Your OAuth consumer has been created and is ready to use"
7. Save the credentials you receive:
   - Consumer token: Something like `ef713d806fa7c02a1b9bd15252fb0ffa`
   - Secret token: Something like `c3d97b740f96fcb1e06d368687ee23a3bebbe08f`
   - Keep these safe - you'll need them for testing!

## Step 2: Set Up Environment Variables

Open your terminal and set these environment variables (replace with your actual credentials):

```bash
export OAUTH_ENABLED=true
export SOCIAL_AUTH_MEDIAWIKI_KEY=your_consumer_token_here
export SOCIAL_AUTH_MEDIAWIKI_SECRET=your_consumer_secret_here
export SOCIAL_AUTH_MEDIAWIKI_URL=https://meta.wikimedia.org/w/index.php
```

Note: These only last for your current terminal session. For a more permanent setup, you can add them to your `~/.zshrc` file or create an `app/.env` file.

## Step 3: Start the Server

```bash
cd app
python3 manage.py runserver
```

If everything's configured correctly, the server should start up with OAuth enabled.

## Step 4: Test the OAuth Login

1. Open http://127.0.0.1:8000/ in your browser
2. You should see a "Login with Wikimedia" button in the top right corner
3. Click the button and you'll be redirected to meta.wikimedia.org
4. Authorize the application on Wikimedia's OAuth page
5. You should get redirected back to http://127.0.0.1:8000/
6. After successful login, you should see your username and a "Logout" button instead of the login button

## Step 5: Verify the OAuth Tokens Are Stored

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
