import os
import signal
import asyncio
import logging.config

from ..util import is_posix, log
from .config import load_config
from .process import Process
from .web import web_server


class Server:

    def __init__(self, config_file):
        self.config_file = config_file
        self.config = None
        self.procs = []

    async def __aenter__(self):
        self.setup()
        return self

    async def __aexit__(self, exc_type, exc_value, tb):
        await self.stop()

    async def stop(self):
        log.info("Shutting down...")
        stops = (proc.terminate() for proc in self.procs)
        await asyncio.gather(*stops)
        log.info("Shutdown complete")

    def setup(self):
        self.config = load_config(self.config_file)
        main = self.config["main"]
        logging.config.dictConfig(main["logging"])
        log.info("Starting (PID=%d)...", os.getpid())

        if is_posix:
            # python 3.9 has pidchildwatcher but some distributions (ex: conda)
            # don't expose the necessary os.pidfd_open() since it is only available
            # since linux kernel 5.3
            if hasattr(os, "pidfd_open") and hasattr(asyncio, "PidfdChildWatcher"):
                child_watcher = asyncio.PidfdChildWatcher()
                log.info("Using PidfdChildWatcher")
            else:
                child_watcher = asyncio.FastChildWatcher()
                log.info("Using FastChildWatcher")
            child_watcher.attach_loop(asyncio.get_running_loop())
            asyncio.set_child_watcher(child_watcher)

    async def serve_forever(self):
        programs =  self.config["programs"]
        web = self.config.get("web")
        log.info("Starting (PID=%d)...", os.getpid())
        self.procs = [Process(name, cfg) for name, cfg in programs.items()]

        stop_trigger = asyncio.Event()
        server = web_server(web, self, stop_trigger.wait)

        def signal_handler():
            log.info("Process received shutdown signal")
            stop_trigger.set()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, signal_handler)
        loop.add_signal_handler(signal.SIGINT, signal_handler)

        starts = (proc.start() for proc in self.procs)
        await asyncio.gather(*starts)

        await server


async def run(config_file):
    async with Server(config_file) as server:
        await server.serve_forever()
