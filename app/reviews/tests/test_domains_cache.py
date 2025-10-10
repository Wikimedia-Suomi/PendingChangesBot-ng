import time

from types import SimpleNamespace

from reviews.check_domains import (
    clear_domain_cache,
    domains_previously_used,
)


class CountingFakeSite:
    """A FakeSite that counts exturlusage calls for a given domain."""

    def __init__(self, exturlusage_map=None):
        self.map = exturlusage_map or {}
        self.calls = 0

    def exturlusage(self, query, total=None, namespaces=None):
        self.calls += 1
        if self.map.get(query):
            yield SimpleNamespace(title='FakePage')
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


def test_cache_ttl_expires_and_requeries():
    site = CountingFakeSite(exturlusage_map={"example.com": True})
    clear_domain_cache()
    # use very small TTL
    ok1, d1 = domains_previously_used(site, ["https://example.com/page"], cache_ttl_seconds=0.01)
    time.sleep(0.02)
    ok2, d2 = domains_previously_used(site, ["https://example.com/page"], cache_ttl_seconds=0.01)
    # two calls should have hit the site because TTL expired
    assert site.calls >= 2
    assert ok1 is True and ok2 is True
