import asyncio
import datetime
import functools
import pathlib

from aiohttp import ClientConnectionResetError, web
from aiohttp_sse import sse_response

from aiovisor.util import log, setup_event_loop, signal
from aiovisor.server.web.api import create_app as create_api

log = log.getChild("web.app")

routes = web.RouteTableDef()


def HTML(text, **kwargs):
    return web.Response(text=text, content_type="text/html", **kwargs)


DATASTAR_PATCH_ELEMENTS = "datastar-patch-elements"


def datastar_patch_elements(sse, elements: str, mode=None):
    lines = []
    if mode is not None and mode != "outer":
        lines.append("mode {mode}")
    lines.extend(f"elements {line}" for line in elements.splitlines())

    return sse.send("\n".join(lines), event=DATASTAR_PATCH_ELEMENTS)


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
  <link rel="stylesheet" type="text/css" href="static/style.css">
</head>

<body style="margin: 0px; padding-top: 40px;">
  <nav style="background-color: #aabbbb; position: fixed; width:100%; top: 0; padding: 10px 20px;">
    AIOVisor {title}
  </nav>
  <div style="padding: 10px;">
    {processes}
  </div>
  <div id="message"></div>
  <div class="error"><span id="error"></span></div>
</body>

</html>
"""


class Column:
    def __init__(self, name, getter, classes=None):
        self.name = name
        self.getter = getter
        self.classes = classes
        self.class_ = name.lower().replace(" ", "-")


    def render_header(self):
        return f'<th scope="col" class="{self.class_}">{self.name}</th>'

    def render_footer(self):
        return f'<th scope="col" class="{self.class_}">{self.name}</th>'

    def render_cell(self, obj):
        value = self.getter(obj)
        text = value_to_text(value)
        classes = " ".join(self.classes(obj)) if self.classes else ""
        return f"""<td class="{self.class_} {classes}">{text}</td>"""


def render_process_buttons(proc):
    name, state = proc["name"], proc["state"]["state"]
    return "\n".join(
        (
            Button(START, f"/process/start/{name}", disabled=not state.is_startable),
            Button(STOP, f"/process/stop/{name}", disabled=not state.is_stoppable),
            Button(KILL, f"/process/kill/{name}", disabled=not state.is_stoppable),
        )
    )


class ProcessTable:
    base_path = "/processes/table"

    cols = [
        Column("Name", lambda p: p["name"]),
        Column("State", lambda p: p["state"]["state"].name, classes=lambda p: [p["state"]["state"].name.lower()]),
        Column("PID", lambda p: p["state"]["pid"]),
        Column("Started", lambda p: human_timestamp(p["state"]["start_time"])),
        Column("Stopped", lambda p: human_timestamp(p["state"]["stop_time"])),
        Column(
            "RSS",
            lambda p: human_bytes(p["ps"].get("memory_full_info", {}).get("rss")),
        ),
        Column("Command", lambda p: p["ps"].get("cmdline")),
        Column("Process name", lambda p: p["ps"].get("name")),
        Column("Controls", render_process_buttons),
        Column("Last return code", lambda p: p["state"]["last_returncode"]),
        Column("Last error", lambda p: p["state"]["last_error"]),
    ]

    def __init__(self, aiovisor, table_id="processes"):
        self.aiovisor = aiovisor
        self.table_id = table_id

    def iter_render_header(self):
        yield "<thead><tr>"
        yield from (col.render_header() for col in self.cols)
        yield "</tr></thead>"

    def iter_render_row(self, row):
        info = row.info()
        yield f"""<tr id="{self.table_id}-{row.name}" class="">"""
        yield from (col.render_cell(info) for col in self.cols)
        yield "</tr>"

    def iter_render_rows(self, rows):
        for row in rows:
            yield from self.iter_render_row(row)

    def iter_render_body(self, rows=None):
        if rows is None:
            rows = self.aiovisor.procs.values()
        yield f"""<tbody id="{self.table_id}-body">"""
        yield from self.iter_render_rows(rows)
        yield "</tbody>"

    def iter_render_footer(self):
        yield ""

    def iter_render(self, rows=None):
        yield f"""<table id="{self.table_id}" data-init="@get('{self.base_path}/events')" class="processes">"""
        yield from self.iter_render_header()
        yield from self.iter_render_body(rows)
        yield from self.iter_render_footer()
        yield "</table>"

    def render_row(self, row):
        return "\n".join(self.iter_render_row(row))

    def __str__(self):
        return "\n".join(self.iter_render())


def human_bytes(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "---"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    for unit in units:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024

    return f"{num_bytes:.1f} {units[-1]}"


def human_timestamp(value):
    if value is None:
        return "---"
    return str(datetime.datetime.fromtimestamp(value))


def value_to_text(value):
    return "---" if value is None else str(value)


@routes.get("/")
async def index(request):
    aiovisor = request.app["aiovisor"]
    processes = ProcessTable(aiovisor)
    return HTML(PAGE.format(title=aiovisor.config["main"]["name"], processes=processes))


@routes.get("/processes/table/events")
async def processes_events(request):
    table = ProcessTable(request.app["aiovisor"])
    events = asyncio.Queue()

    def on_process_state_event(sender, old_state, new_state):
        events.put_nowait(sender)

    state_event = signal("process_state")
    state_event.connect(on_process_state_event)
    try:
        async with sse_response(request) as sse:
            while sse.is_connected():
                proc = await events.get()
                text = table.render_row(proc)
                await datastar_patch_elements(sse, text)
    except ClientConnectionResetError:
        log.info("Client closed connection")
    finally:
        state_event.disconnect(on_process_state_event)
    return sse


def process_action(f):
    @functools.wraps(f)
    async def wrapper(request):
        try:
            await f(request)
        except Exception as error:
            text = f'<span id="error">{error}</span>'
            return HTML(text, reason=str(error), status=200)
        return web.Response(status=204)

    return wrapper


@routes.post("/process/start/{name}")
@process_action
async def process_start(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.start()


@routes.post("/process/stop/{name}")
@process_action
async def process_stop(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.stop()


@routes.post("/process/kill/{name}")
@process_action
async def process_kill(request):
    aiovisor = request.app["aiovisor"]
    name = request.match_info["name"]
    process = aiovisor.process(name)
    await process.kill()


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
