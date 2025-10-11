# PendingChangesBot Contributing Guide

Thank you for expressing interest in contributing to PendingChangesBot! Please be sure to read this guide thoroughly before contributing as it will lessen the chances of any issues arising during the contribution process.

Of course\! Here is a table of contents for the provided guide.

# Table of Contents

1.  [Code of Conduct](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CODE_OF_CONDUCT.MD)
2.  [Communication](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#communication)
3.  [Prerequisites](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#prerequisites)
4.  [Setup Instructions](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#setup-instructions)
    1.  [Installation](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#installation)
    2.  [Configuring Pywikibot Superset OAuth](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#configuring-pywikibot-superset-oauth)
    3.  [Running the database migrations](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#running-the-database-migrations)
    4.  [Running the application](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#running-the-application)
    5.  [Running unit tests](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#running-unit-tests)
    6.  [Running Flake8](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#running-flake8)
5.  [Label Meanings](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#label-meanings)
    1.  [Status Labels](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#status-labels)
    2.  [Type Labels](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#type-labels)
6.  [How to Contribute](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#how-to-contribute)
    1.  [Check Before Doing Anything](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#check-before-doing-anything)
    2.  [Being Assigned an Issue](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#being-assigned-an-issue)
    3.  [Branching Strategy](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#branching-strategy)
    4.  [Commit messages](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#commit-messages)
    5.  [Creating a Pull Request](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#creating-a-pull-request)
    6.  [Opening an issue](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#opening-an-issue)
7.  [Further Help](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CONTRIBUTING.md#further-help)

## Code of Conduct

All contributors must follow the project’s [Code of Conduct](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/blob/main/CODE_OF_CONDUCT.MD).

## Communication

It is advised to follow below mentioned pointers when trying to contact the mentors:
* If the discussion is specific to an existing issue or PR then it's best to have this discussion publicly in the comments of said issue or PR.
* If it's something specifically related to outreachy then the slack channel on Wikimediafi is the place to go.
* It's best to have discussions publicly so other contributors can benefit from it, however, if you feel uncomfortable in doing so then you are most welcome to talk to any of the mentors privately through slack (for faster replies) or email.

Mentor's Details:
* [zache-fi](https://github.com/zache-fi): zache on slack (Bots original developer in 2016 and maintainer. Mentoring Cat-a-lot Outreachy in the round 30)
* [ad_an_26_](https://github.com/ad-an-26): Adiba on slack  (Wikimedia Outreachy intern in round 30, knowledge with LLMs and mediawiki API)
* [ademolaomosanya](https://github.com/ademolaomosanya): Ademola on slack (Wikimedia Outreachy in round 30, knowledge with python)
* [Ipr1](): (finnish wikipedist and Wikimedia Finlands fiwiki developer/helpdesk person)

## Prerequisites
Before installing or running the application, ensure you have:
* Python 3
* Pip
* Virtual environment support (venv)
* Git
* Django-compatible environment
* Pywikibot configured with your Wikimedia username
* Browser access to Meta-Wiki and Superset for OAuth approval

## Setup Instructions


### Installation

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
3. **Check your python version** (recommended)
   * On **Windows**:
   ```bash
   python --version
   ```
   * On **macOS**:
   ```bash
   python3 --version
   ```
   Install if not found *for python3 you need to install pip3 
4. **Create and activate a virtual environment** (recommended)
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: .venv\\Scripts\\activate
   ```
4. **Install Python dependencies**
   * On **Windows**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
   * On **macOS**:
   ```bash
   pip3 install --upgrade pip
   pip3 install -r requirements.txt
   ```

### Configuring Pywikibot with OAuth

Pywikibot requires OAuth authentication to interact with Wikimedia APIs and approve Superset's OAuth client. We **strongly recommend using OAuth 1.0a** for better security.

#### Step 1: Register an OAuth 1.0a Consumer

1. **Go to the OAuth registration page**
   - Visit: <https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose>
   - Make sure you're logged into your Wikimedia account

2. **Click "Propose an OAuth 1.0a consumer"** (not OAuth 2.0)

3. **Fill in the registration form:**
   - **Application name**: `PendingChangesBot-local` (or any descriptive name)
   - **Consumer version**: `1.0`
   - **Application description**: `Local development bot for reviewing pending changes`
   - **OAuth "callback" URL**: **Leave this field completely blank**
   - Check **This consumer is for use only by [your username]**:
   - **Applicable project**: Select `*` (all projects)
   - **Types of grants**: Select "Request authorization for specific permissions"
   - **Applicable grants**: Check these permissions:
     - **Basic rights**
     - **High-volume (bot) access**
     - **Edit existing pages**
     - **Patrol changes to pages**
     - **Rollback changes to pages**
   - **Allowed IP ranges**: Leave as default (`0.0.0.0/0` and `::/0`)
   - **Public RSA key**: Leave blank
   - Check the acknowledgment box

4. **Submit and copy your tokens**
   - After submission, you'll receive **4 tokens**:
     - Consumer token
     - Consumer secret
     - Access token
     - Access secret
   - **Save these immediately. You won't see them again!**

#### Step 2: Create Your Pywikibot Configuration

1. **Option A: Copy the example template**
   ```bash
   cp user-config.py.example user-config.py
   ```

2. **Option B: Create `user-config.py` in root** with this content:
   ```python
   from collections import defaultdict as _defaultdict

   family = 'wikipedia'
   mylang = 'en'

   usernames = _defaultdict(dict)
   usernames['wikipedia']['en'] = 'YourWikipediaUsername'
   usernames['meta']['meta'] = 'YourWikipediaUsername'

   authenticate = {}
   authenticate['meta.wikimedia.org'] = (
       'CONSUMER_TOKEN',       # Replace these with your credentials
       'CONSUMER_SECRET',
       'ACCESS_TOKEN',
       'ACCESS_SECRET'
   )
   ```

3. **Replace the placeholders:**
   - Replace `'YourWikipediaUsername'` with your actual Wikipedia username
   - Replace all token placeholders with your actual OAuth tokens from Step 1

#### Step 3: Test Your OAuth Setup

1. **Test the login:**
   ```bash
   python3 -m pywikibot.scripts.login -site:meta
   ```

2. **Expected output:**
   ```
   Logged in on meta:meta as YourUsername.
   ```

3. **If successful**, a login cookie will be created

#### Step 4: Approve Superset's OAuth Client

1. **While logged in to Meta-Wiki**, visit:
   - <https://superset.wmcloud.org/login/>

2. **Authorize the OAuth request** for Superset
   - You should be redirected to Superset's interface after approval

#### Troubleshooting Common Issues

**Problem: `SyntaxError: source code string cannot contain null bytes`**
- **Cause**: Your `user-config.py` file is corrupted or contains hidden binary characters
- **Solution**: Delete the file and recreate it from scratch using the template above

**Problem: `NoUsernameError: Logged in as X but expect as Y`**
- **Cause**: Username mismatch between OAuth tokens and `user-config.py`
- **Solution**: Update `usernames` to match your actual Wikipedia username

**Problem: `UserWarning: Configuration variable "defaultdict" is defined but unknown`**
- **Cause**: Importing `defaultdict` without underscore prefix
- **Solution**: Use `from collections import defaultdict as _defaultdict`

**Problem: `Invalid value provided` for OAuth callback URL**
- **Cause**: Trying to enter a value in the callback URL field
- **Solution**: Leave the "OAuth callback URL" field **completely blank**

**Problem: OAuth login fails with `401 Unauthorized`**
- **Cause**: Incorrect or expired OAuth tokens
- **Solution**: Register a new OAuth consumer and update your tokens

#### Security Best Practices

- **Never commit** `user-config.py` to git (already in `.gitignore`)
- **Never share** your OAuth tokens publicly
- **Use owner-only consumers** for local development
- **Grant minimal permissions** – only what you need
- **Regenerate tokens** if compromised

Need help? Ask in the Slack channel or open an issue!

### Running the database migrations
   ```bash
   cd app
   ```
   * On **Windows**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```
   * On **macOS**:
   ```bash
   python3 manage.py makemigrations
   python3 manage.py migrate
   ```

### Running the application

The Django project serves both the API and the Vue.js frontend from the same codebase.

   ```bash
   cd app
   ```
   * On **Windows**:
   ```bash
   python manage.py runserver
   ```
   * On **macOS**:
   ```bash
   python3 manage.py runserver
   ```

Open <http://127.0.0.1:8000/> in your browser to use the interface. JSON endpoints are
available under `/api/wikis/<wiki_id>/…`, for example `/api/wikis/1/pending/`.

### Running unit tests

Unit tests live in the Django backend project. Run them from the `app/` directory so Django can locate the correct settings module.

   ```bash
   cd app
   ```
   * On **Windows**:
   ```bash
   python manage.py test
   ```
   * On **macOS**:
   ```bash
   python3 manage.py test
   ```

### Running Flake8

Run Flake8 from the repository root to lint the code according to the configuration provided in `.flake8`.

   ```bash
   flake8
   ```

If you are working inside a virtual environment, ensure it is activated before executing the command.

After these steps Pywikibot will be able to call Superset's SQL Lab API without running
into `User not logged in` errors, and PendingChangesBot can fetch pending revisions
successfully.

## Label Meanings

The labels that get applied to issues and PRs in our repo have specific meanings and are broken into two categories: status and type. An issue/PR should only ever have one status label, but can have multiple type labels. The following is the complete list of the labels.

### Status Labels
* **Open**: This issue has not been picked up by any contributor yet
* **Abandoned**: This issue/PR has been abandoned and will not be implemented
* **Accepted**: This PR has been accepted and is able to be merged
* **Awaiting Changes**: Waiting for requested changes to be made by the contributor
* **Awaiting Response**: Waiting for a response from the contributor
* **Discussion**: This issue/PR has an ongoing discussion
* **Do Not Merge**: This PR should not be merged until further notice
* **Do Not Review**: This issue/PR should not be reviewed until further notice
* **Help Wanted**: This issue can be assigned to other contributors
* **In Progress**: This issue/PR has ongoing work being done
* **Invalid**: This issue/PR is invalid or is not relevant
* **Investigating**: Something in this issue/PR is being investigated
* **Needs Review**: This issue/PR needs an initial or additional review
* **On Hold**: There is a temporary hold on any continued work or review
* **Stale**: This issue/PR has been inactive for over 10 days.
* **Under Review**: This issue/PR is being reviewed by at least one mentor.

### Type Labels
* **Accessibility**: Involves an accessibility feature or requires accessibility review
* **Bug**: Involves something that isn't working as intended
* **Chore**: Involves changes with no user-facing value, to the build process/internal tooling, refactors, etc.
* **Documentation**: Involves an update to the documentation
* **Duplicate**: This issue/PR already exists
* **Easy Fix**: Involves a minor fix such as grammar, syntax, etc.
* **Enhancement**: Involves a new feature or enhancement request
* **Good First Issue**: Good for beginner contributors
* **Priority**: This issue/PR should be resolved ASAP

It is advised to change the state label of the issue or PR as soon as the need arises so mentors and contributors are both aware about the change.

## How to Contribute

### Check Before Doing Anything

It's important that you look through any open [issues](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/issues) or [pull requests](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/pulls) in the repo before attempting to submit a new issue or starting to work on it. This will help avoid any duplicates from being made, as well as prevent more than one person working on the same thing at the same time without each other's knowledge.

If your proposal already exists in an open issue or PR, but you feel there are details missing or you simply wish to collaborate with the other contributor, comment on the issue/PR to let those involved know about it.

### Being Assigned an Issue:

1) Find an issue that is open and you wish to work on.
    * A couple of good places to start are issues with the `Status: Help Wanted`, `Status: Discussion`, `Status: Stale` or `Type: Good First Issue` labels. You can filter the issues list to only show ones with these (or any) specific labels to make them easier to find.
    * You can also filter out any issues with the `Status: In Progress` label, so that you only see issues that haven't been assigned to anyone.

2) No need to ask to be assigned an issue.
    * Just let people know through comments that you are working on it and assign it to yourself.
    * If there is both Phabricator ticket and Github issue then comment on both that you are working with it.
    * If someone is already working on it, ask to collaborate before jumping in.

3) After being assigned, address each item listed in the acceptance criteria, if any exist.
   * If an issue doesn't have any acceptance criteria, feel free to go about resolving the issue however you wish.
   * You can also ask the mentors if there are any specific acceptance criteria.

4) Give regular updates.
    * It's expected that you would give regular progress updates about the work that you're doing as comments on the issue so that everyone is in the loop about what work is being accomplished

5) Claim new tasks responsibly.
    * If you want to switch to another task for any reason, unassign yourself from the current ticket or issue and leave a comment there so others know it’s available to work on.
    * Please claim a new task only after you’ve submitted a pull request for your previous one.

### Branching Strategy

Follow this branching structure:
* **main**– stable production code
* **Feature branches** : feature/issueNumber
* **Bugfix branches**: fix/issueNumber
* **Documentation fix/addition branches** : docs/issueNumber
* **Style/formatting Branches** (no logic changes) : style/issueNumber
* **Test Branch** (test added or updated) : test/issueNumber

Notice how each branch refers to an issue number, this is essential to keep track of which issue is being worked on and to ease collaboration. It's good practice to have one feature or fix per branch. Basically, keep commits focused and atomic, avoid putting unrelated changes in one branch.

### Commit messages:
If the app needs auth tokens, URLs or secrets then be sure to remove them or include in `.gitignore` before making commits.

Each commit message should follow this structure:
* **Title** (A short, clear summary of the change (50 characters max))
* **Description** (Optional, recommended for anything non-trivial. Add 1–3 lines explaining what and why, not how)
* **Reference issues or tasks** (e.g., Fixes #42, Related to #101)

### Creating a Pull Request:
Before creating a PR:
* Rebase or merge latest main
* Ensure no merge conflicts
* Run and pass all tests
* Remove dead code & logs
* Follow branch naming rules

To learn how to create a pull request or to learn more about pull requests in general, please follow this official [Pull request documentation](https://docs.github.com/en/pull-requests) by github.

Make sure to use the following format in your pull request:
* **Title** (should be clear and concise. Include issue number as well. (example: Add bulk editing UI for category selections (#128))):
* **Description / Summary** (Explain the PR at a glance. What does this change do and why is it needed?):
* **Linked Issues and phabricator ticket** (Fixes/closes/relates to #IssueNumber and #PhabricatorTask etc.):
* **Changes Included** (Feature updates, Bug fixes, Refactors, Files/components affected etc.):
* **Screenshots / Demos** (if UI-related):
* **Testing & Validation** (List what was tested and how. Manual or automated. Testing environment etc.):
* **Checklist / Confirmation** (Code follows project style guidelines, Tests pass, No unnecessary console logs/leftover code, Documentation updated (if needed) etc.):

After creating the PR, go over to the appropriate phabricator task and make a comment stating that you've created a PR along with it's link.

### Opening an issue:
If you encounter a feature that should be added or a bug that needs to be fixed, then please reach out to the mentors through slack to confirm that this issue is not already in the pipeline. If they give you the go ahead, then feel free to open the issue. It's not mandatory that if you open an issue then you have to work on it, though it is ideal.

After creating the issue, make sure to announce it on the [main phabricator board for PendingChangesBot](https://phabricator.wikimedia.org/T405726) along with the link to the issue, this way mentors can create an appropriate microtask for it on phabricator and other contributors are aware about it.

1) Use the following template to create an issue for a bug:
* **Summary** :
* **Steps to replicate the bug** (include links if applicable):
* **What happens?** (Actual behaviour):
* **What should have happened instead?** (Expected Behaviour):
* **Screenshots/logs if applicable** :
* **Environment details** :
* **Any additional details** :
* **Will you be working on this issue yourself?** : Yes or No

2) Use the following template to create an issue for requesting a feature:
* **Feature summary** (what you would like to be able to do and where):
* **Use case(s)** (list the steps that you performed to discover that problem and describe the actual underlying problem which you want to solve. Do not describe only a solution):
* **Benefits** (why should this be implemented?):
* **Screenshots/logs if applicable** :
* **Any additional details** :
* **Will you be working on this issue yourself?** : Yes or No

## Further Help
Feel free to contact the mentors through slack or email if you need further help.
