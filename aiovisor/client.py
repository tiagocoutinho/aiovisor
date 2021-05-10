import json
import httpx


class AIOVisor:

    def __init__(self, base_url):
        self.client = httpx.AsyncClient(base_url=base_url)

    async def __aenter__(self):
        return self

    async def __aexit__(self, ext_type, exc_value, tb):
        await self.aclose()

    async def aclose(self):
        await self.client.aclose()

    async def stream(self):
        async with self.client.stream("GET", "/stream", timeout=None) as stream:
            async for chunk in stream.aiter_bytes():
                if chunk.startswith(b"data:"):
                    yield json.loads(chunk[5:])

    async def state(self):
        return (await self.client.get("/state")).json()

    async def processes(self):
        return (await self.client.get("/processes")).json()

    async def process_info(self, name):
        return (await self.client.get(f"/process/info/{name}")).json()

    async def process_start(self, name):
        return (await self.client.post(f"/process/start/{name}")).json()

    async def process_stop(self, name):
        return (await self.client.post(f"/process/stop/{name}")).json()

