import datetime
import pathlib

from aiohttp import web

from aiovisor.util import log, setup_event_loop
from aiovisor.server.web.api import create_app as create_api

log = log.getChild("web.app")
this_dir = pathlib.Path(__file__).parent
static = this_dir / "static"

routes = web.RouteTableDef()


def HTML(text):
    return web.Response(text=text, content_type="text/html")


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
    <div id="processes" data-init="@get('/processes')"></div>
  </div>
</body>

</html>
"""


PROC_ROW = """\
<tr id="{name}">
  <td>{name}</td>
  <td>{state}</td>
  <td>{pid}</td>
  <td>{returncode}</td>
  <td>{started}</td>
  <td>{stopped}</td>
  <td>{rss}</td>
  <td>{command}</td>
  <td>{executable}</td>
  <td>
    <button data-on:click="@post('/process/start/{name}')">Start</button>
    <button data-on:click="@post('/process/stop/{name}')">Stop</button>
  </td>
</tr>
"""

PROCS_TABLE = """\
<table id="processes">
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
    <th scope="col">Executable</th>
    <th scope="col">Control</th>
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
    info = proc.psutil
    if (rss := info.get("memory_full_info", {}).get("rss")) is not None:
        rss = human_readable_bytes(rss)
    return PROC_ROW.format(
        name=proc.name,
        state=proc.state.name,
        pid=to_text(proc.pid),
        returncode=to_text(proc.returncode),
        started=to_text(proc.start_datetime),
        stopped=to_text(proc.stop_datetime),
        rss=to_text(rss),
        command=to_text(info.get("cmdline")),
        executable=to_text(info.get("exe")),
    )


@routes.get("/")
async def index(request):
    aiovisor = request.app["aiovisor"]
    return HTML(PAGE.format(title=aiovisor.config["main"]["name"]))


@routes.get("/processes")
async def processes(request):
    aiovisor = request.app["aiovisor"]
    procs = map(proc_row, aiovisor.procs.values())
    rows = "\n".join(procs)
    table = PROCS_TABLE.format(rows=rows)
    return web.Response(text=table, content_type="text/html")


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
    app.add_routes([web.static("/static", static)])
    app.add_routes(routes)
    api = await create_api(aiovisor)
    app.add_subapp("/api/", api)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


def run_app(aiovisor, config):
    web.run_app(web_app(aiovisor), **config)
