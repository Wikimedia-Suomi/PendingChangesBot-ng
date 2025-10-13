from types import SimpleNamespace

from reviews.check_domains import (
    clear_domain_cache,
    domains_previously_used,
    extract_domain,
)

# --- Helpers: Fake site objects with exturlusage behavior ---


class FakeSite:
    """
    fake site supporting exturlusage(domain, total=..., namespaces=[0]).
    exturlusage_map should be dict: domain -> bool (True means pages exist)
    If domain not in map -> return empty iterator.
    If exturlusage_raises is set to an Exception instance, calling exturlusage raises it.
    """

    def __init__(self, exturlusage_map=None, exturlusage_raises=None):
        self.map = exturlusage_map or {}
        self.raises = exturlusage_raises

    def exturlusage(self, query, total=None, namespaces=None):
        if self.raises:
            raise self.raises
        # Return generator that yields a fake Page if domain exists in map True
        count = 0
        value = self.map.get(query)
        if isinstance(value, int):
            count = value
        elif value:
            count = 2

        for _ in range(count):
            yield SimpleNamespace(title="FakePage")
        if count == 0:
            if False:
                yield None  # unreachable; just to keep generator type


# --- Tests for extract_domain ---


def test_extract_domain():
    cases = [
        ("https://example.com/page", "example.com"),
        ("http://www.Example.com:8080/foo", "example.com"),
        ("//cdn.example.org/path", "cdn.example.org"),
        ("www.example.co.uk/path", "example.co.uk"),
        ("mailto:user@example.com", "example.com"),
        ("bitcoin:1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", None),
        ("", None),
        ("not a url", None),
        ("ftp://ftp.example.net/resource", "ftp.example.net"),
    ]
    for input_url, expected in cases:
        assert extract_domain(input_url) == expected


# --- Domain check tests ---


def test_trusted_domain_approved():
    site = FakeSite(exturlusage_map={"example.com": True})
    clear_domain_cache()
    ok, details = domains_previously_used(site, ["https://example.com/article"])
    assert ok is True
    assert details["example.com"]["used"] is True


def test_never_used_domain_rejected():
    site = FakeSite(exturlusage_map={"example.com": False})
    clear_domain_cache()
    ok, details = domains_previously_used(site, ["https://new-site-123.com/article"])
    # domain 'new-site-123.com' not present in map -> treated as False
    assert ok is False
    # details should have an entry for the normalized domain
    # extract_domain of input becomes 'new-site-123.com'
    # In this fake site map domain isn't set -> used should be False
    # We expect details to show used False
    # confirm by checking details contains the domain key and used is False or None
    assert any(not v["used"] for v in details.values())


def test_multiple_all_trusted_approved():
    site = FakeSite(exturlusage_map={"example.com": True, "bbc.com": True})
    clear_domain_cache()
    ok, details = domains_previously_used(site, ["https://example.com/a", "http://bbc.com/news"])
    assert ok is True
    assert details["example.com"]["used"] is True
    assert details["bbc.com"]["used"] is True


def test_single_usage_not_enough():
    site = FakeSite(exturlusage_map={"example.com": 1})
    clear_domain_cache()
    ok, details = domains_previously_used(site, ["https://example.com/about"])  # single hit
    assert ok is False
    assert details["example.com"]["used"] is False


def test_multiple_mixed_rejected():
    site = FakeSite(exturlusage_map={"example.com": True})
    clear_domain_cache()
    ok, details = domains_previously_used(
        site, ["https://example.com/article", "https://suspicious-site.com/stuff"]
    )
    assert ok is False
    # example.com should be True; suspicious-site.com should be False
    assert details["example.com"]["used"] is True
    # suspicious site key exists and used False
    assert any(
        k == "suspicious-site.com" or (v["used"] is False and k != "example.com")
        for k, v in details.items()
    )


def test_various_url_formats_and_normalization():
    site = FakeSite(exturlusage_map={"example.com": True, "sub.example.co.uk": True})
    clear_domain_cache()
    ok, details = domains_previously_used(
        site,
        [
            "https://www.example.com/some",  # normalizes to example.com
            "http://sub.example.co.uk/path",  # retains subdomain
            "mailto:editor@sub.example.co.uk",  # mailto domain extraction
        ],
    )
    assert ok is True
    assert details["example.com"]["used"] is True
    assert details["sub.example.co.uk"]["used"] is True


def test_malformed_url_requires_manual_review():
    # no domains can be extracted
    site = FakeSite(exturlusage_map={})
    clear_domain_cache()
    ok, details = domains_previously_used(site, ["bitcoin:xyz", "not a url"])
    assert ok is False
    assert "__malformed__" in details


def test_api_error_defaults_to_manual_review():
    site = FakeSite(exturlusage_raises=RuntimeError("api down"))
    clear_domain_cache()
    ok, details = domains_previously_used(site, ["https://example.com/article"])
    assert ok is False
    # details for example.com should show error
    # find any detail with error not None
    assert any(v.get("error") for v in details.values())
