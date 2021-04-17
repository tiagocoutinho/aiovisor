from fastapi import FastAPI

from hypercorn.config import Config
from hypercorn.asyncio import serve

from ..util import log

log = log.getChild("web")


app = FastAPI()


@app.get("/processes")
def processes():
    return {p.name:p.config for p in app.server.procs}


@app.get("/state")
def state():
    return {"state": app.server.state.name}


def web_server(config, server, shutdown_trigger):
    log.info("Preparing web app...")
    cfg = Config()
    cfg.bind = config["bind"]
    app.server = server
    return serve(app, cfg, shutdown_trigger=shutdown_trigger)
