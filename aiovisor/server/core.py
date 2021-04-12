import os
import signal
import asyncio
import logging.config

from ..util import is_posix, log
from .config import load_config
from .process import Process


def setup():
    if is_posix:
        if hasattr(os, "pidfd_open") and hasattr(asyncio, "PidfdChildWatcher"):
            child_watcher = asyncio.PidfdChildWatcher()
        else:
            child_watcher = asyncio.FastChildWatcher()
        child_watcher.attach_loop(asyncio.get_running_loop())
        asyncio.set_child_watcher(child_watcher)


async def run(config_file):
    config = load_config(config_file)
    main = config["main"]
    programs =  config["programs"]
    web = config.get("web")
    logging.config.dictConfig(main["logging"])
    log.info("Starting (PID=%d)...", os.getpid())
    setup()
    progs = [Process(name, cfg) for name, cfg in programs.items()]

    stop_trigger = asyncio.Event()

    if web is None:
        server = stop_trigger.wait
    else:
        from .web import web_server
        server = web_server(web, progs, stop_trigger.wait)

    starts = (prog.start() for prog in progs)
    await asyncio.gather(*starts)

    def signal_handler():
        log.info("Process received shutdown signal")
        stop_trigger.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    loop.add_signal_handler(signal.SIGINT, signal_handler)

    await server

    log.info("Shutting down...")
    stops = (prog.terminate() for prog in progs)
    await asyncio.gather(*stops)
    log.info("Shutdown complete")
