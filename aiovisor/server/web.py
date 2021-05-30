import asyncio
import pathlib

from aiohttp import web

from ..util import log, signal, setup_event_loop


log = log.getChild("web")
this_dir = pathlib.Path(__file__).parent

routes = web.RouteTableDef()


@routes.get("/")
async def index(request):
    return web.FileResponse(this_dir / "static" / "index.html")


@routes.get("/processes")
async def processes(request):
    aiovisor = request.app["aiovisor"]
    return web.json_response(
        {name: p.info() for name, p in aiovisor.procs.items()}
    )


@routes.get("/process/info/{name}")
async def process_info(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    return web.json_response(process.info())


@routes.get("/state")
async def state(request):
    aiovisor = request.app["aiovisor"]
    return web.json_response({"state": aiovisor.state.name})


@routes.post("/process/stop/{name}")
async def process_stop(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.terminate()
    return web.json_response({"result": "ACK"})


@routes.post("/process/start/{name}")
async def process_start(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.start()  # TODO: Convert to background task
    return web.json_response({"result": "ACK"})


"""
async def event_stream(request):
    def on_server_state_event(sender, old_state, new_state):
        queue.put_nowait(dict(
            event_type="server_state",
            old_state=old_state.name,
            new_state=new_state.name,
            server=sender.info(),
        ))
    def on_process_state_event(sender, old_state, new_state):
        queue.put_nowait(dict(
            event_type="process_state",
            old_state=old_state.name,
            new_state=new_state.name,
            process=sender.info(),
        ))

    log.info("Client %s connected to stream", request.client)
    sstate = signal("server_state")
    pstate = signal("process_state")
    sstate.connect(on_server_state_event)
    pstate.connect(on_process_state_event)
    queue = asyncio.Queue()
    while True:
        if await request.is_disconnected():
            log.info("Client %s disconnected from stream", request.client)
            break
        data = await queue.get()
        log.info("Sending %s to %s", data["event_type"], request.client)
        yield dict(data=json.dumps(data))
    pstate.disconnect(on_process_state_event)
    sstate.disconnect(on_server_state_event)


@app.get("/stream")
async def stream(request: Request):
    return EventSourceResponse(event_stream(request))

@app.on_event("startup")
async def startup_event():
    setup_event_loop()
    await app["aiovisor"].start()


@app.on_event("shutdown")
async def shutdown_event():
    await app["aiovisor"].stop()
"""


@routes.get("/ws")
async def ws(request):
    def on_server_state_event(sender, old_state, new_state):
        queue.put_nowait(dict(
            event_type="server_state",
            old_state=old_state.name,
            new_state=new_state.name,
            server=sender.info(),
        ))
    def on_process_state_event(sender, old_state, new_state):
        queue.put_nowait(dict(
            event_type="process_state",
            old_state=old_state.name,
            new_state=new_state.name,
            process=sender.info(),
        ))

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
        while True:
            data = await queue.get()
            log.info("Sending %s to %s", data["event_type"], request.remote)
            await ws.send_json(data)
        pstate.disconnect(on_process_state_event)
        sstate.disconnect(on_server_state_event)
    except ConnectionResetError:
        log.info("ws connection reset")
    finally:
        request.app["clients"].remove(ws)
    return ws


async def on_startup(app):
    await app["aiovisor"].start()


async def on_shutdown(app):
    await app["aiovisor"].stop()
    clients = set(app["clients"])
    if clients:
        # ugly hack: wait for server_state to be sent to all WS clients
        await asyncio.sleep(0.1)
        for client in clients:
            await client.close()


async def web_app(aiovisor):
    setup_event_loop()
    app = web.Application()
    app.add_routes(routes)
    app["aiovisor"] = aiovisor
    app["clients"] = set()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


def run_app(aiovisor, config):
    web.run_app(web_app(aiovisor), **config)
