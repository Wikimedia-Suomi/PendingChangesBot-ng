"""Custom Django Social Auth pipeline functions for OAuth."""


def save_wikimedia_username(strategy, details, user=None, *args, **kwargs):
    """
    Save the original Wikimedia username in the first_name field.

    Django normalizes usernames (removes high-bit characters), so we store
    the original MediaWiki username in first_name to display it correctly.

    Args:
        strategy: Social auth strategy
        details: User details from OAuth provider
        user: Django User object (None if creating new user)
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Returns:
        None (pipeline continues)
    """
    if user:
        # Get the original username from the response
        # MediaWiki returns 'username' in the user details
        wikimedia_username = details.get("username", "")

        if wikimedia_username and user.first_name != wikimedia_username:
            user.first_name = wikimedia_username
            user.save(update_fields=["first_name"])
