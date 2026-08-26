
async def create_cache(client, model: str, content: list, ttl_seconds: int,
                        display_name: str) -> str:
    cache = await client.caches.create(
        model=model, contents=content, ttl=f"{ttl_seconds}s", display_name=display_name,
    )
    return cache.name
