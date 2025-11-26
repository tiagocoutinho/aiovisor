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
  <title>{title}</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <script type="module"
    src="https://cdn.jsdelivr.net/gh/starfederation/datastar@1.0.0-RC.6/bundles/datastar.js"></script>
  <style>
    .navbar {{
      background-color: #303030;
      color: white;
      padding: 0px 20px;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 40px;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
      z-index: 1000;
      vertical-align: center;
    }}
    .panel {{
      padding: 10px;
    }}
  </style>
</head>

<body style="margin: 0px; padding-top: 40px;">
  <nav class="navbar">AIOVisor</nav>
  <div class="panel">
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
  </tr>
  </thead>
  <tbody>
  {rows}
  </tbody>
</table>
"""

def null_text(v):
    if isinstance(v, datetime.datetime):
        return str(v) # v.ctime()
    return "---" if v is None else str(v)

def proc_row(proc):
    info = proc.psutil
    if (rss := info.get("memory_full_info", {}).get("rss")) is not None:
        rss = f"{rss / 1024 / 1024:.3f} MB"
    return PROC_ROW.format(
        name=proc.name, 
        state=proc.state.name, 
        pid=null_text(proc.pid),
        returncode=null_text(proc.returncode),
        started=null_text(proc.start_datetime),
        stopped=null_text(proc.stop_datetime),
        rss=null_text(rss),
        command=null_text(info.get("cmdline")),
        executable=null_text(info.get("exe")),
    )


@routes.get("/")
async def index(request):
    return HTML(PAGE.format(title=request.app["aiovisor"].config["main"]["name"]))


@routes.get("/processes")
async def processes(request):
    aiovisor = request.app["aiovisor"]
    procs = map(proc_row, aiovisor.procs.values())
    rows = "\n".join(procs)
    table = PROCS_TABLE.format(rows=rows)
    return web.Response(text=table, content_type="text/html")


async def web_app(aiovisor):
    setup_event_loop()
    app = web.Application()
    app["aiovisor"] = aiovisor
    app.add_routes([web.static("/static", static)])
    app.add_routes(routes)
    api = await create_api(aiovisor)
    app.add_subapp("/api/", api)

    return app


def run_app(aiovisor, config):
    web.run_app(web_app(aiovisor), **config)
