"""
Permission system for PendingChangesBot control panel.

This module handles user authentication and authorization by:
1. Checking user groups from MediaWiki API
2. Mapping groups to roles (Admin, Reviewer, Public)
3. Enforcing permissions on bot control actions
"""

from enum import Enum
from functools import wraps
from typing import Callable

from django.http import HttpRequest, JsonResponse
import requests


class UserRole(Enum):
    """User roles for permission system."""

    ADMIN = "admin"
    REVIEWER = "reviewer"
    PUBLIC = "public"


# Map MediaWiki user groups to our roles
MEDIAWIKI_GROUP_MAPPING = {
    # Admin groups (can start/stop bot, change settings)
    "sysop": UserRole.ADMIN,
    "bureaucrat": UserRole.ADMIN,
    "interface-admin": UserRole.ADMIN,

    # Reviewer groups (can manually review pages)
    "reviewer": UserRole.REVIEWER,
    "editor": UserRole.REVIEWER,
    "autoreview": UserRole.REVIEWER,
    "autoreviewer": UserRole.REVIEWER,
    "autopatrolled": UserRole.REVIEWER,

    # Bot accounts have admin access
    "bot": UserRole.ADMIN,
}


def get_user_groups_from_mediawiki(username: str, wiki_code: str = "fi", wiki_family: str = "wikipedia") -> list[str]:
    """
    Query MediaWiki API to get user groups.

    Args:
        username: MediaWiki username
        wiki_code: Wiki language code (default: fi)
        wiki_family: Wiki family (default: wikipedia)

    Returns:
        List of user groups (e.g., ['sysop', 'autopatrolled'])
    """
    api_url = f"https://{wiki_code}.{wiki_family}.org/w/api.php"

    params = {
        "action": "query",
        "list": "users",
        "ususers": username,
        "usprop": "groups",
        "format": "json",
    }

    try:
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        users = data.get("query", {}).get("users", [])
        if users and len(users) > 0:
            user_data = users[0]
            # Check if user exists (missing attribute means user doesn't exist)
            if "missing" in user_data:
                return []
            return user_data.get("groups", [])
        return []
    except Exception as e:
        # Log error but don't fail - treat as no groups
        print(f"Error fetching user groups for {username}: {e}")
        return []


def get_user_role(username: str, wiki_code: str = "fi", wiki_family: str = "wikipedia") -> UserRole:
    """
    Determine user role based on MediaWiki groups.

    Args:
        username: MediaWiki username
        wiki_code: Wiki language code
        wiki_family: Wiki family

    Returns:
        UserRole enum (ADMIN, REVIEWER, or PUBLIC)
    """
    if not username:
        return UserRole.PUBLIC

    groups = get_user_groups_from_mediawiki(username, wiki_code, wiki_family)

    # Check for admin role first (highest privilege)
    for group in groups:
        if group in MEDIAWIKI_GROUP_MAPPING:
            role = MEDIAWIKI_GROUP_MAPPING[group]
            if role == UserRole.ADMIN:
                return UserRole.ADMIN

    # Check for reviewer role
    for group in groups:
        if group in MEDIAWIKI_GROUP_MAPPING:
            role = MEDIAWIKI_GROUP_MAPPING[group]
            if role == UserRole.REVIEWER:
                return UserRole.REVIEWER

    # Default to public (read-only)
    return UserRole.PUBLIC


def require_permission(required_role: UserRole) -> Callable:
    """
    Decorator to require specific permission level for a view.

    Usage:
        @require_permission(UserRole.ADMIN)
        def start_bot(request):
            ...

    Args:
        required_role: Minimum role required to access the view

    Returns:
        Decorated view function that checks permissions
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            # TODO: Get username from session/OAuth (Week 8 implementation)
            # For now, check if username is in request headers (for testing)
            username = request.META.get("HTTP_X_WIKI_USERNAME")
            wiki_code = request.META.get("HTTP_X_WIKI_CODE", "fi")

            if not username:
                return JsonResponse(
                    {
                        "error": "Authentication required",
                        "detail": "You must be logged in to perform this action",
                    },
                    status=401,
                )

            # Get user's actual role
            user_role = get_user_role(username, wiki_code)

            # Check if user has required permissions
            if not has_permission(user_role, required_role):
                return JsonResponse(
                    {
                        "error": "Insufficient permissions",
                        "detail": f"This action requires {required_role.value} role, but you have {user_role.value} role",
                        "your_role": user_role.value,
                        "required_role": required_role.value,
                    },
                    status=403,
                )

            # User has permission, proceed with the view
            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def has_permission(user_role: UserRole, required_role: UserRole) -> bool:
    """
    Check if a user role has the required permission level.

    Permission hierarchy: ADMIN > REVIEWER > PUBLIC

    Args:
        user_role: User's current role
        required_role: Required role for the action

    Returns:
        True if user has permission, False otherwise
    """
    role_hierarchy = {
        UserRole.ADMIN: 3,
        UserRole.REVIEWER: 2,
        UserRole.PUBLIC: 1,
    }

    return role_hierarchy[user_role] >= role_hierarchy[required_role]


def get_user_info(username: str, wiki_code: str = "fi", wiki_family: str = "wikipedia") -> dict:
    """
    Get comprehensive user information including role and groups.

    Args:
        username: MediaWiki username
        wiki_code: Wiki language code
        wiki_family: Wiki family

    Returns:
        Dictionary with user info: {username, role, groups, permissions}
    """
    groups = get_user_groups_from_mediawiki(username, wiki_code, wiki_family)
    role = get_user_role(username, wiki_code, wiki_family)

    return {
        "username": username,
        "wiki": f"{wiki_code}.{wiki_family}",
        "role": role.value,
        "groups": groups,
        "permissions": {
            "can_start_stop_bot": role == UserRole.ADMIN,
            "can_manual_review": role in [UserRole.ADMIN, UserRole.REVIEWER],
            "can_change_settings": role == UserRole.ADMIN,
            "can_view_status": True,  # Everyone can view status
        },
    }
