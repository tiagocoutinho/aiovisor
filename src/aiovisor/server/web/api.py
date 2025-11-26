import asyncio

from aiohttp import web

from aiovisor.util import log, signal


log = log.getChild("web.api")

api = web.RouteTableDef()


@api.get("/processes")
async def processes(request):
    aiovisor = request.app["aiovisor"]
    return web.json_response({name: p.info() for name, p in aiovisor.procs.items()})


@api.get("/process/info/{name}")
async def process_info(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    return web.json_response(process.info())


@api.get("/state")
async def state(request):
    aiovisor = request.app["aiovisor"]
    return web.json_response({"state": aiovisor.state.name})


@api.post("/process/stop/{name}")
async def process_stop(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.stop()
    return web.json_response({"result": "ACK"})


@api.post("/process/start/{name}")
async def process_start(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.start()  # TODO: Convert to background task
    return web.json_response({"result": "ACK"})


@api.get("/ws")
async def ws(request):
    def on_server_state_event(sender, old_state, new_state):
        queue.put_nowait(
            dict(
                event_type="server_state",
                old_state=old_state.name,
                new_state=new_state.name,
                server=sender.info(),
            )
        )

    def on_process_state_event(sender, old_state, new_state):
        queue.put_nowait(
            dict(
                event_type="process_state",
                old_state=old_state.name,
                new_state=new_state.name,
                process=sender.info(),
            )
        )

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    log.info("Client %s connected to stream", request.remote)
    request.app["clients"].add(ws)
    try:
        sstate = signal("server_state")
        pstate = signal("process_state")
        sstate.connect(on_server_state_event)
        pstate.connect(on_process_state_event)
        queue = asyncio.Queue()
        try:
            while True:
                data = await queue.get()
                log.info("Sending %s to %s", data["event_type"], request.remote)
                await ws.send_json(data)
        finally:
            pstate.disconnect(on_process_state_event)
            sstate.disconnect(on_server_state_event)
    except ConnectionResetError:
        log.info("ws connection reset")
    finally:
        request.app["clients"].remove(ws)
    return ws


async def on_shutdown(app):
    clients = set(app["clients"])
    if clients:
        # ugly hack: wait for server_state to be sent to all WS clients
        await asyncio.sleep(0.1)
        for client in clients:
            await client.close()


async def create_app(aiovisor):
    api_app = web.Application()
    api_app.add_routes(api)
    api_app["aiovisor"] = aiovisor
    api_app["clients"] = set()
    api_app.on_shutdown.append(on_shutdown)
    return api_app
