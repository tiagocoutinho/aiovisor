import os
import enum
import asyncio
import logging.config
from signal import SIGTERM, SIGINT

from ..util import is_posix, log, signal
from .config import load_config
from .process import Process
from .web import web_server


class ServerState(enum.IntEnum):

    Stopped = 0
    Starting = 1
    Running = 2
    Stopping = 3


class Server:

    def __init__(self, config_file):
        self.config_file = config_file
        self.config = None
        self.procs = {}
        self.state = ServerState.Stopped

    async def __aenter__(self):
        self.setup()
        return self

    async def __aexit__(self, exc_type, exc_value, tb):
        await self.stop()

    async def stop(self):
        self.change_state(ServerState.Stopping)
        stops = (proc.terminate() for proc in self.procs.values())
        await asyncio.gather(*stops)
        self.change_state(ServerState.Stopped)

    def change_state(self, state):
        old_state = self.state
        if state == old_state:
            return
        self.state = state
        log.info("State changed from %s to %s", old_state.name, state.name)
        sig = signal("server_state")
        sig.send(self, old_state=old_state, new_state=state)

    def setup(self):
        self.change_state(ServerState.Starting)
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
        programs = self.config["programs"]
        web = self.config.get("web")
        self.procs = {name: Process(name, cfg) for name, cfg in programs.items()}

        stop_trigger = asyncio.Event()

        def signal_handler():
            log.info("Process received shutdown signal")
            stop_trigger.set()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(SIGTERM, signal_handler)
        loop.add_signal_handler(SIGINT, signal_handler)

        server = asyncio.create_task(web_server(web, self, stop_trigger.wait))
        self.change_state(ServerState.Running)

        starts = (proc.start() for proc in self.procs.values())
        await asyncio.gather(*starts)

        await server

    def process(self, name):
        return self.procs[name]


async def run(config_file):
    async with Server(config_file) as server:
        await server.serve_forever()
