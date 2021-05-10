import json
import asyncio

from aiohttp import web

from ..util import log, signal


log = log.getChild("web")

routes = web.RouteTableDef()

run_app = web.run_app


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
    return {"result": "ACK"}


@routes.post("/process/start/{name}")
async def process_start(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.start()  # TODO: Convert to background task
    return {"result": "ACK"}


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


"""
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

def web_app():
    app = web.Application()
    app.add_routes(routes)
    return app
