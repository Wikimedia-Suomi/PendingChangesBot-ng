from types import SimpleNamespace

from reviews.check_domains import (
    clear_domain_cache,
    domains_previously_used,
    get_default_ttl,
    set_default_ttl,
)


class CountingFakeSite:
    """A FakeSite that counts exturlusage calls for a given domain."""

    def __init__(self, exturlusage_map=None):
        self.map = exturlusage_map or {}
        self.calls = 0

    def exturlusage(self, query, total=None, namespaces=None):
        self.calls += 1
        if self.map.get(query):
            yield SimpleNamespace(title="FakePage")
        else:
            if False:
                yield None


def test_cache_hit_avoids_second_query():
    site = CountingFakeSite(exturlusage_map={"example.com": True})
    clear_domain_cache()
    ok1, d1 = domains_previously_used(site, ["https://example.com/page"])
    ok2, d2 = domains_previously_used(site, ["https://example.com/other"])  # should use cache
    assert site.calls == 1
    assert ok1 is True and ok2 is True


def test_clear_cache_causes_requery():
    site = CountingFakeSite(exturlusage_map={"example.com": True})
    clear_domain_cache()
    ok1, d1 = domains_previously_used(site, ["https://example.com/page"])

    site.map = {"example.com": False}
    clear_domain_cache()
    ok2, d2 = domains_previously_used(site, ["https://example.com/page"])

    assert site.calls == 2
    assert ok1 is True
    assert ok2 is False
    assert d2["example.com"]["used"] is False


def test_cache_respects_ttl(monkeypatch):
    site = CountingFakeSite(exturlusage_map={"example.com": True})
    clear_domain_cache()

    original_ttl = get_default_ttl()
    set_default_ttl(1)

    # Ensure the second lookup happens in a different TTL bucket (>= 1s later).
    times = iter([1000.0, 1002.0, 1004.0])
    monkeypatch.setattr("reviews.check_domains.time.time", lambda: next(times))

    ok1, _ = domains_previously_used(site, ["https://example.com/a"])

    site.map = {"example.com": False}
    ok2, _ = domains_previously_used(site, ["https://example.com/b"])

    assert site.calls == 2
    assert ok1 is True
    assert ok2 is False

    # Restore defaults for other tests
    set_default_ttl(original_ttl or 3600)
    clear_domain_cache()
