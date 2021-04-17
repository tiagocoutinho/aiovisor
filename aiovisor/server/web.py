import asyncio

from fastapi import FastAPI, Response, status

from hypercorn.config import Config
from hypercorn.asyncio import serve

from ..util import log, AIOVisorError


log = log.getChild("web")


app = FastAPI()


@app.get("/processes")
def processes():
    return {name: p.info() for name, p in app.server.procs.items()}


@app.get("/process/info/{name}")
def process_info(name: str):
    return app.server.process(name).info()


@app.get("/state")
def state():
    return {"state": app.server.state.name}


@app.post("/process/stop/{name}")
async def process_stop(name: str):
    process = app.server.process(name)
    await process.terminate()
    return process.info()


@app.post("/process/start/{name}")
async def process_start(name: str, response: Response):
    try:
        process = app.server.process(name)
        await process.start()
        return process.info()
    except AIOVisorError as error:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"error": error.args[0]}


def web_server(config, server, shutdown_trigger):
    log.info("Preparing web app...")
    cfg = Config()
    cfg.bind = config["bind"]
    app.server = server
    return serve(app, cfg, shutdown_trigger=shutdown_trigger)
