"""Fixtures scoped to tests/unit/api/.

_clear_page_count_cache: autouse guard against _PAGE_COUNT_CACHE hits
inherited across tests. The cache key is a stat signature (mtime_ns, size) on
an absolute path string, not the test's tmp_path — a coincidental signature
match against a stale entry from an earlier test (unlikely, but the module
dict is process-lifetime and never evicted mid-suite) would silently serve a
wrong page count. Clearing before and after each test keeps the cache
behavior exercised here isolated to the test that set it up (§C5).
"""

import pytest

from api.routes.sessions import _common


@pytest.fixture(autouse=True)
def _clear_page_count_cache():
    _common._PAGE_COUNT_CACHE.clear()
    yield
    _common._PAGE_COUNT_CACHE.clear()
