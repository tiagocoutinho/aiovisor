import pathlib
import argparse
import logging.config

from ..util import log, setup_event_loop
from .web import web_app, run_app
from .core import AIOVisor
from .config import load_config


def prepare_logging(config):
    main = config["main"]
    logging.config.dictConfig(main["logging"])
    log.info("Starting...")


def run(config_file):
    async def startup(app):
        await aiovisor.start()

    async def shutdown(app):
        await aiovisor.stop()

    async def init():
        setup_event_loop()
        app = web_app()
        app["aiovisor"] = aiovisor
        app.on_startup.append(startup)
        app.on_shutdown.append(shutdown)
        return app

    config = load_config(config_file)
    prepare_logging(config)
    aiovisor = AIOVisor(config)
    run_app(init(), **config["web"]["aiohttp"])


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", required=True, type=pathlib.Path)
    opts = parser.parse_args(args=args)
    run(opts.config_file)


if __name__ == "__main__":
    main()
