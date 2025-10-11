"""
check_domains.py

Utilities to check whether domains from newly added links have been
previously used in Wikipedia articles (namespace=0) using Pywikibot.

Main entry point:
    domains_previously_used(site, urls)

Public helpers:
- extract_domain(url) -> Optional[str]
- clear_domain_cache()
- domains_previously_used(...)

Notes:
- Safe defaults: any API error or malformed URL causes the check to fail
  (i.e., require manual review), as requested.
- Caches domain results in-memory using functools.lru_cache().
"""

from typing import Iterable, List, Optional, Dict, Any, Tuple, TYPE_CHECKING
from urllib.parse import urlparse
from functools import lru_cache
import weakref
import re
import time

# Make pywikibot import optional so unit tests and static tools can run without it.
if TYPE_CHECKING:
    import pywikibot  # type: ignore
else:
    try:
        import pywikibot  # type: ignore
    except Exception:
        pywikibot = None  # type: ignore

_DEFAULT_CACHE_TTL_SECONDS: float = 3600.0
_SITE_REGISTRY: "weakref.WeakValueDictionary[int, Any]" = weakref.WeakValueDictionary()


def _register_site(site: Any) -> int:
    """Store a weak reference to the site and return a cache key."""
    site_key = id(site)
    _SITE_REGISTRY[site_key] = site
    return site_key


def clear_domain_cache() -> None:
    """Clear memoized domain usage checks."""
    _cached_domain_usage.cache_clear()
    _SITE_REGISTRY.clear()


def set_default_ttl(seconds: Optional[float]) -> None:
    """Set the default cache TTL in seconds (0/None disables TTL bucketing)."""
    global _DEFAULT_CACHE_TTL_SECONDS
    _DEFAULT_CACHE_TTL_SECONDS = float(seconds or 0)
    _cached_domain_usage.cache_clear()


def get_default_ttl() -> Optional[float]:
    """Return the currently configured default TTL in seconds, or None if disabled."""
    return _DEFAULT_CACHE_TTL_SECONDS or None


def _cache_bucket(ttl_seconds: Optional[float]) -> Optional[int]:
    if not ttl_seconds or ttl_seconds <= 0:
        return None
    return int(time.time() // ttl_seconds)


@lru_cache(maxsize=4096)
def _cached_domain_usage(site_key: int, domain: str, bucket: Optional[int]) -> Tuple[bool, Optional[Exception]]:
    site = _SITE_REGISTRY.get(site_key)
    if site is None:
        raise RuntimeError("Site reference expired; cache needs refresh")

    try:
        results = site.exturlusage(domain, total=1, namespaces=[0])
        for _ in results:
            return True, None
        return False, None
    except Exception as exc:  # pragma: no cover - network failure fallback
        return False, exc


def _effective_ttl_seconds(ttl_override: Optional[float]) -> Optional[float]:
    if ttl_override is None:
        return _DEFAULT_CACHE_TTL_SECONDS or None
    return ttl_override or None


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


def _check_domain_used_with_site(
    site: Any,
    domain: str,
    *,
    cache_ttl_seconds: Optional[float] = None,
) -> Tuple[bool, Optional[Exception]]:
    """Return (used, error) for namespace=0 domain usage on the given site."""

    effective_ttl = _effective_ttl_seconds(cache_ttl_seconds)
    bucket = _cache_bucket(effective_ttl)
    site_key = _register_site(site)
    try:
        return _cached_domain_usage(site_key, domain, bucket)
    except RuntimeError:
        # Site reference expired from the registry; reset registry and retry once.
        _SITE_REGISTRY.clear()
        _cached_domain_usage.cache_clear()
        site_key = _register_site(site)
        return _cached_domain_usage(site_key, domain, bucket)


def domains_previously_used(site: Any,
                            urls: Iterable[str],
                            raise_on_error: bool = False
                            ) -> Tuple[bool, Dict[str, Dict]]:
    """
    Main check function.

    Parameters
    - site: pywikibot.Site instance
    - urls: iterable of URL strings newly added in an edit
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
        before_hits = _cached_domain_usage.cache_info().hits
        used, error = _check_domain_used_with_site(site, domain)
        after_hits = _cached_domain_usage.cache_info().hits
        was_cached = after_hits > before_hits

        if error is not None:
            err_str = f'API error: {type(error).__name__}: {error}'
            details[domain] = {
                'url_examples': sample_urls,
                'domain': domain,
                'used': None,
                'cached': False,
                'error': err_str
            }
            overall_ok = False
            if raise_on_error:
                raise error
            continue

        details[domain] = {
            'url_examples': sample_urls,
            'domain': domain,
            'used': bool(used),
            'cached': was_cached,
            'error': None
        }
        if not used:
            overall_ok = False

    return overall_ok, details
