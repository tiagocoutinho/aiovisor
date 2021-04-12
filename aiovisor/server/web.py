from fastapi import FastAPI

from hypercorn.config import Config
from hypercorn.asyncio import serve

from ..util import log

log = log.getChild("web")


app = FastAPI()


@app.get("/processes")
def processes():
    return {p.name:p.config for p in app.procs}


def web_server(config, processes, shutdown_trigger):
    log.info("Preparing web api...")
    cfg = Config()
    cfg.bind = config["bind"]
    app.procs = processes
    return serve(app, cfg, shutdown_trigger=shutdown_trigger)
