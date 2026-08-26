import pytest
from shruti.gemini.cache import create_cache


class FakeCache:
    name = "cachedContents/abc"


class FakeCachesApi:
    async def create(self, model, contents, ttl, display_name):
        return FakeCache()


class FakeClient:
    def __init__(self):
        self.caches = FakeCachesApi()


@pytest.mark.asyncio
async def test_create_cache_returns_cache_name():
    client = FakeClient()
    name = await create_cache(client, model="gemini-3.5-flash", content=["schema text"],
                               ttl_seconds=3600, display_name="extraction-schema")
    assert name == "cachedContents/abc"
