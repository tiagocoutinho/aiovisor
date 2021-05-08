import json
import asyncio
from fastapi import FastAPI, Request, status, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..util import log, signal, AIOVisorError, setup_event_loop


log = log.getChild("web")


app = FastAPI()
app.mount("/static", StaticFiles(packages=["aiovisor.server"]),
          name="static")


@app.exception_handler(AIOVisorError)
async def aiovisor_error_handler(request: Request, error: AIOVisorError):
    return await http_exception_handler(request, HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error.args[0]))


def get_process(name):
    try:
        return app.aiovisor.process(name)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process {name!r} not found")


@app.get("/")
def index():
    return RedirectResponse("/static/index.html")


@app.get("/processes")
def processes():
    return {name: p.info() for name, p in app.aiovisor.procs.items()}


@app.get("/process/info/{name}")
def process_info(name: str):
    return get_process(name).info()


@app.get("/state")
def state():
    return {"state": app.aiovisor.state.name}


@app.post("/process/stop/{name}")
async def process_stop(name: str):
    process = get_process(name)
    await process.terminate()
    return {"result": "ACK"}


@app.post("/process/start/{name}")
async def process_start(name: str, background_tasks: BackgroundTasks):
    process = get_process(name)
    background_tasks.add_task(process.start)
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


@app.get("/stream")
async def stream(request: Request):
    return EventSourceResponse(event_stream(request))


@app.on_event("startup")
async def startup_event():
    setup_event_loop()
    await app.aiovisor.start()


@app.on_event("shutdown")
async def shutdown_event():
    await app.aiovisor.stop()
