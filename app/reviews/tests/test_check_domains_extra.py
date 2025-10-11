from types import SimpleNamespace

from reviews.check_domains import (
    clear_domain_cache,
    domains_previously_used,
)


class CapturingFakeSite:
    """Fake site that records the arguments exturlusage was called with."""

    def __init__(self, exturlusage_map=None):
        self.map = exturlusage_map or {}
        self.last_call = None

    def exturlusage(self, query, total=None, namespaces=None):
        # record the call signature
        self.last_call = {
            'query': query,
            'total': total,
            'namespaces': namespaces,
        }
        if self.map.get(query):
            yield SimpleNamespace(title='FakePage')
        else:
            if False:
                yield None


def test_exturlusage_called_with_namespace_zero():
    site = CapturingFakeSite(exturlusage_map={"example.com": True})
    clear_domain_cache()
    ok, details = domains_previously_used(site, ["https://example.com/page"])
    assert site.last_call is not None
    assert site.last_call['namespaces'] == [0]


def test_clear_domain_cache_empties_cache():
    site = CapturingFakeSite(exturlusage_map={"example.com": True})
    # ensure value cached
    clear_domain_cache()
    ok1, d1 = domains_previously_used(site, ["https://example.com/page"])  # caches result
    # change map to false and clear cache, then requery
    site.map = {"example.com": False}
    clear_domain_cache()
    ok2, d2 = domains_previously_used(site, ["https://example.com/page"])  # should requery and get False
    assert ok1 is True
    assert ok2 is False


def test_cached_flag_reports_hit():
    site = CapturingFakeSite(exturlusage_map={"example.com": True})
    clear_domain_cache()
    ok1, d1 = domains_previously_used(site, ["https://example.com/page"])
    ok2, d2 = domains_previously_used(site, ["https://example.com/page#section"])

    assert ok1 is True and ok2 is True
    assert d1["example.com"]["cached"] is False
    assert d2["example.com"]["cached"] is True
