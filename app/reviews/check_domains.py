"""
check_domains.py

Utilities to check whether domains from newly added links have been
previously used in Wikipedia articles (namespace=0) using Pywikibot.

Main entry point:
    domains_previously_used(site, urls, cache=None, ttl_seconds=3600)

Public helpers:
- extract_domain(url) -> Optional[str]
- clear_domain_cache()
- domains_previously_used(...)

Notes:
- Safe defaults: any API error or malformed URL causes the check to fail
  (i.e., require manual review), as requested.
- Caches domain results in-memory for `ttl_seconds` (default 1 hour).
"""

from typing import Iterable, List, Optional, Dict, Tuple, Any, TYPE_CHECKING
from urllib.parse import urlparse
import time
import re

# Make pywikibot import optional so unit tests and static tools can run without it.
if TYPE_CHECKING:
    import pywikibot  # type: ignore
else:
    try:
        import pywikibot  # type: ignore
    except Exception:
        pywikibot = None  # type: ignore

# In-memory cache: domain -> (bool_was_used, timestamp)
_DOMAIN_CACHE: Dict[str, Tuple[bool, float]] = {}

# Default TTL for cached entries (seconds)
_DEFAULT_TTL = 3600.0


def clear_domain_cache() -> None:
    """Clear the in-memory domain cache."""
    global _DOMAIN_CACHE
    _DOMAIN_CACHE = {}


def _cache_get(domain: str, ttl_seconds: float) -> Optional[bool]:
    rec = _DOMAIN_CACHE.get(domain)
    if not rec:
        return None
    was_used, ts = rec
    if (time.time() - ts) > ttl_seconds:
        # expired
        del _DOMAIN_CACHE[domain]
        return None
    return was_used


def _cache_set(domain: str, value: bool) -> None:
    _DOMAIN_CACHE[domain] = (value, time.time())


# MediaWiki URL protocols (as guidance for parsing); not all protocols include a hostname.
# We will accept typical network protocols and special-case mailto: to extract domain part.
_WG_URL_PROTOCOLS = [
    'bitcoin:', 'ftp://', 'ftps://', 'geo:', 'git://', 'gopher://', 'http://',
    'https://', 'irc://', 'ircs://', 'magnet:', 'mailto:', 'matrix:', 'mms://',
    'news:', 'nntp://', 'redis://', 'sftp://', 'sip:', 'sips:', 'sms:',
    'ssh://', 'svn://', 'tel:', 'telnet://', 'urn:', 'worldwind://', 'xmpp:',
    '//',
]


def extract_domain(raw_url: str) -> Optional[str]:
    """
    Extract domain (second-level + subdomain normalized) from a URL-like string.

    Returns domain normalized to lower-case without leading 'www.' or port,
    e.g. 'example.com' or 'sub.example.co.uk'.

    If no domain can reasonably be extracted (protocols without host, malformed),
    returns None.

    Behavior:
    - If scheme is missing but the string starts with '//' or 'www.' or looks like host/path,
      we will try to prepend 'http://' for parsing.
    - mailto:user@example.com -> returns example.com
    - If host contains port, strip it (example.com:8080 -> example.com)
    """
    if not raw_url or not raw_url.strip():
        return None
    url = raw_url.strip()

    # remove surrounding angle brackets occasionally used in wikitext <https://...>
    if url.startswith('<') and url.endswith('>'):
        url = url[1:-1].strip()

    # If it starts with '//' which is protocol-relative, prepend http:
    if url.startswith('//'):
        url = 'http:' + url

    # If there's no scheme but it has typical host-like form (www. or contains a dot before a slash),
    # prepend http:// to make urlparse give us a netloc.
    if '://' not in url:
        # heuristics: starts with 'www.' or contains '.' before first '/'
        first_slash = url.find('/')
        head = url if first_slash == -1 else url[:first_slash]
        if head.startswith('www.') or ('.' in head and not head.startswith('mailto:') and not head.startswith('urn:')):
            url = 'http://' + url

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    host = parsed.netloc or ''
    scheme = (parsed.scheme or '').lower()

    # Special-case mailto: scheme -> parse path for 'user@domain'
    if scheme == 'mailto':
        path = parsed.path or ''
        if '@' in path:
            domain_part = path.split('@', 1)[1]
            # strip possible query or fragment
            domain_part = domain_part.split('?')[0].split('#')[0]
            domain = domain_part.lower()
            # strip port if present (unlikely)
            domain = domain.split(':')[0]
            domain = domain.strip()
            if domain:
                # Normalize www and return
                if domain.startswith('www.'):
                    domain = domain[4:]
                return domain
        return None

    # If parsed.netloc is empty, there's likely no host (e.g. bitcoin:..., tel:..., etc.)
    if not host:
        return None

    # Remove credentials user:pass@host
    if '@' in host:
        host = host.split('@', 1)[1]

    # Remove port
    if ':' in host:
        host = host.split(':', 1)[0]

    host = host.lower().strip()

    # Normalize leading www.
    if host.startswith('www.'):
        host = host[4:]

    # Convert internationalized domain names (IDN) to ASCII using IDNA (punycode).
    # If conversion fails, treat as malformed.
    try:
        # idna encoding expects a str and returns bytes; decode back to str
        # but Python's codec can directly produce the 'xn--' form via encode/decode.
        host = host.encode('idna').decode('ascii')
    except Exception:
        return None

    # Basic validation: host should contain at least one dot, or be localhost
    if host == 'localhost' or '.' in host:
        # remove trailing dots
        host = host.rstrip('.')
        # remove any characters not valid in hostnames (be conservative)
        host = re.sub(r'[^a-z0-9\.\-]', '', host)
        return host or None

    return None


def _check_domain_used_with_site(site: Any, domain: str) -> bool:
    """
    Use pywikibot.Site.exturlusage to check whether `domain` has been used in namespace 0.

    Returns True if used, False otherwise.

    Raises exceptions thrown by the site API (we catch them at a higher level).
    """
    results = site.exturlusage(domain, total=1, namespaces=[0])
    # results may be a generator; attempt to get the first item.
    for _ in results:
        return True
    return False


def domains_previously_used(site: Any,
                            urls: Iterable[str],
                            cache_ttl_seconds: float = _DEFAULT_TTL,
                            raise_on_error: bool = False
                            ) -> Tuple[bool, Dict[str, Dict]]:
    """
    Main check function.

    Parameters
    - site: pywikibot.Site instance
    - urls: iterable of URL strings newly added in an edit
    - cache_ttl_seconds: cache TTL (seconds), default 3600
    - raise_on_error: if True, re-raise API exceptions; otherwise, swallow and return (False, details)

    Returns:
    - (all_domains_previously_used, details)
      where details is dict: domain -> {
            "url_examples": [sample urls that produced this domain],
            "domain": domain,
            "used": True/False/None (None means unknown due to error),
            "error": optional error string
        }

    Rules applied:
    - If any domain is not previously used (used == False) -> overall result is False (manual review).
    - If any domain check results in an API error -> overall result is False (manual review) and error recorded.
    - If no domains were extractable (e.g., all links are protocol types without host) -> conservative behavior: require manual review (returns False).
    """
    # Build mapping domain -> list of sample urls
    domain_to_urls: Dict[str, List[str]] = {}
    for u in urls:
        dom = extract_domain(u)
        if dom:
            domain_to_urls.setdefault(dom, []).append(u)
        else:
            # track None domains under a special key
            domain_to_urls.setdefault('__malformed__', []).append(u)

    details: Dict[str, Dict] = {}
    overall_ok = True

    # If any malformed URLs (no domain), conservative: require manual review
    if '__malformed__' in domain_to_urls:
        details['__malformed__'] = {
            'url_examples': domain_to_urls['__malformed__'],
            'domain': None,
            'used': False,
            'error': 'Malformed or protocol-only URLs detected; manual review recommended'
        }
        return False, details

    # If no domains found at all, conservative: manual review
    if not domain_to_urls:
        return False, details

    # For each domain, check cache or query
    for domain, sample_urls in domain_to_urls.items():
        cached = _cache_get(domain, cache_ttl_seconds)
        if cached is not None:
            details[domain] = {
                'url_examples': sample_urls,
                'domain': domain,
                'used': bool(cached),
                'cached': True,
                'error': None
            }
            if not cached:
                overall_ok = False
            continue

        # Not cached -> query the site
        try:
            used = _check_domain_used_with_site(site, domain)
            _cache_set(domain, bool(used))
            details[domain] = {
                'url_examples': sample_urls,
                'domain': domain,
                'used': bool(used),
                'cached': False,
                'error': None
            }
            if not used:
                overall_ok = False
        except Exception as e:
            # API error -> conservative behavior
            err_str = f'API error: {type(e).__name__}: {e}'
            details[domain] = {
                'url_examples': sample_urls,
                'domain': domain,
                'used': None,
                'cached': False,
                'error': err_str
            }
            overall_ok = False
            if raise_on_error:
                raise

    return overall_ok, details


def set_default_ttl(seconds: float) -> None:
    """Set the module default TTL (seconds) used when callers rely on the default.

    This exists to make tests and runtime tweaks easier without passing ttl everywhere.
    """
    global _DEFAULT_TTL
    _DEFAULT_TTL = float(seconds)


def get_default_ttl() -> float:
    """Return the current module default TTL in seconds."""
    return _DEFAULT_TTL