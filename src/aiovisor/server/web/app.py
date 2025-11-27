import asyncio
import datetime
import pathlib

from aiohttp import ClientConnectionResetError, web
from aiohttp_sse import sse_response

from aiovisor.util import log, setup_event_loop, signal
from aiovisor.server.web.api import create_app as create_api

log = log.getChild("web.app")

routes = web.RouteTableDef()


def HTML(text):
    return web.Response(text=text, content_type="text/html")


START = "&#x23F5;"
RESTART = "&#x21BA;"
PAUSE = "&#x23F8;"
STOP = "&#x23F9;"
DELETE = "&#x2672;"
KILL = "&#x1F571;"
LOGS = "&#x2399;"
ATTACH = "&#x2328;"


BUTTON = """<button data-on:click="@post('{post}')" {attrs}>{text}</button>"""
def Button(text, post, disabled=False):
    attrs = ["disabled"] if disabled else [] 
    return BUTTON.format(text=text, post=post, attrs=" ".join(attrs))


PAGE = """\
<!DOCTYPE html>
<html lang="en">

<head>
  <title>AIOVisor {title}</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <script type="module" src="static/datastar.js"></script>
</head>

<body style="margin: 0px; padding-top: 40px;">
  <nav style="background-color: #aabbbb; position: fixed; width:100%; top: 0; padding: 10px 20px;">
    AIOVisor {title}
  </nav>
  <div style="padding: 10px;">
    <div id="processes" data-init="@get('/processes/table')"></div>
  </div>
  <div id="message"></div>

</body>

</html>
"""

PROC_ROW = """\
<tr id="{name}-process-row">\
  <td>{name}</td>\
  <td>{state}</td>\
  <td>{pid}</td>\
  <td>{returncode}</td>\
  <td>{started}</td>\
  <td>{stopped}</td>\
  <td>{rss}</td>\
  <td>{command}</td>\
  <td>{proc_name}</td>\
  <td>{control}</td>\
  <td>{last_error}</td>\
</tr>\
"""

PROCS_TABLE = """\
<table id="processes" data-init="@get('/processes/table/events')">
  <thead>
  <tr>
    <th scope="col">Name</th>
    <th scope="col">State</th>
    <th scope="col">PID</th>
    <th scope="col">Return code</th>
    <th scope="col">Started</th>
    <th scope="col">Stopped</th>
    <th scope="col">RSS</th>
    <th scope="col">Command</th>
    <th scope="col">Process name</th>
    <th scope="col">Control</th>
    <th scope="col">Last error</th>
  </tr>
  </thead>
  <tbody>
  {rows}
  </tbody>
</table>
"""


def human_readable_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    for unit in units:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024

    return f"{num_bytes:.1f} {units[-1]}"


def to_text(value):
    if isinstance(value, datetime.datetime):
        return str(value)  # v.ctime()
    return "---" if value is None else str(value)


def proc_row(proc):
    info = proc.psutil()
    if (rss := info.get("memory_full_info", {}).get("rss")) is not None:
        rss = human_readable_bytes(rss)
    name, state = proc.name, proc.state
    start = Button(START, f"/process/start/{name}", disabled=not state.is_startable)
    stop = Button(STOP, f"/process/stop/{name}", disabled=state.is_stopped)
    kill = Button(KILL, f"/process/kill/{name}", disabled=state.is_stopped)
    return PROC_ROW.format(
        name=proc.name,
        state=proc.state.name,
        pid=to_text(proc.pid),
        returncode=to_text(proc.returncode),
        started=to_text(proc.start_datetime),
        stopped=to_text(proc.stop_datetime),
        rss=to_text(rss),
        last_error=to_text(proc.last_error or ""),
        command=to_text(info.get("cmdline")),
        proc_name=to_text(info.get("name")),
        control="".join((start, stop, kill)),
    )


@routes.get("/")
async def index(request):
    aiovisor = request.app["aiovisor"]
    return HTML(PAGE.format(title=aiovisor.config["main"]["name"]))


@routes.get("/processes/table")
async def processes(request):
    aiovisor = request.app["aiovisor"]
    procs = map(proc_row, aiovisor.procs.values())
    rows = "\n".join(procs)
    table = PROCS_TABLE.format(rows=rows)
    return web.Response(text=table, content_type="text/html")


@routes.get("/processes/table/events")
async def processes_events(request):
    def on_process_state_event(sender, old_state, new_state):
        events.put_nowait(sender)
    pstate = signal("process_state")
    pstate.connect(on_process_state_event)    
    events = asyncio.Queue()
    async with sse_response(request) as resp:
        while resp.is_connected():
            proc = await events.get()
            try:
                row = proc_row(proc)
                await resp.send(f'elements {row}', event="datastar-patch-elements")
            except ClientConnectionResetError:
                log.info("Client closed connection")
        pstate.disconnect(on_process_state_event)
    return resp

@routes.post("/process/start/{name}")
async def process_start(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.start()
    return web.Response(status=204)


@routes.post("/process/stop/{name}")
async def process_stop(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.stop()
    return web.Response(status=204)


async def on_startup(app):
    await app["aiovisor"].start()


async def on_shutdown(app):
    await app["aiovisor"].stop()


async def web_app(aiovisor):
    setup_event_loop()
    app = web.Application()
    app["aiovisor"] = aiovisor
    app.add_routes([web.static("/static", pathlib.Path(__file__).parent / "static")])
    app.add_routes(routes)
    api = await create_api(aiovisor)
    app.add_subapp("/api/", api)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app




def run_app(aiovisor, config):
    web.run_app(web_app(aiovisor), **config)
