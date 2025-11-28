import json
import aiohttp


class AIOVisor:
    def __init__(self, base_url):
        self.base_url = base_url
        self.client = aiohttp.ClientSession()

    async def __aenter__(self):
        return self

    async def __aexit__(self, ext_type, exc_value, tb):
        await self.aclose()

    async def aclose(self):
        await self.client.aclose()

    async def stream(self):
        async with self.client.stream("GET", "/api/stream", timeout=None) as stream:
            async for chunk in stream.aiter_bytes():
                if chunk.startswith(b"data:"):
                    yield json.loads(chunk[5:])

    async def state(self):
        response = await self.client.get(f"{self.base_url}/api/state")
        return await response.json()

    async def processes(self):
        response = await self.client.get(f"{self.base_url}/api/processes")
        return await response.json()

    async def process_info(self, name):
        response = await self.client.get(f"{self.base_url}/api/process/info/{name}")
        return await response.json()

    async def process_start(self, name):
        response = await self.client.post(f"{self.base_url}/api/process/start/{name}")
        return await response.json()

    async def process_stop(self, name):
        response = await self.client.post(f"{self.base_url}/api/process/stop/{name}")
        return await response.json()
