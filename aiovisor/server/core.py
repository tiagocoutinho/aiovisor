import os
import enum
import time
import socket
import asyncio

from ..util import log, signal
from .process import Process


class State(enum.IntEnum):

    Stopped = 0
    Starting = 1
    Running = 2
    Stopping = 3


class AIOVisor:

    def __init__(self, config):
        self.config = config
        self.procs = {}
        self.start_time = None
        self.state = State.Stopped
        self.pid = os.getpid()
        self.hostname = socket.gethostname()

    async def __aenter__(self):
        if self.state is State.Stopped:
            await self.start()
        return self

    async def __aexit__(self, exc_type, exc_value, tb):
        if self.state in {State.Stopping, State.Stopped}:
            return
        await self.stop()

    def info(self):
        return dict(
            self.config["main"],
            state=self.state.name,
            start_time=self.start_time,
            pid=self.pid,
            hostname=self.hostname,
        )

    async def start(self):
        self.change_state(State.Starting)
        self.start_time = time.time()
        programs = self.config["programs"]
        self.procs = {name: Process(name, cfg) for name, cfg in programs.items()}
        starts = (proc.start() for proc in self.procs.values())
        await asyncio.gather(*starts)
        self.change_state(State.Running)

    async def stop(self):
        self.change_state(State.Stopping)
        stops = (proc.terminate() for proc in self.procs.values())
        await asyncio.gather(*stops)
        self.change_state(State.Stopped)

    def change_state(self, state):
        old_state = self.state
        if state == old_state:
            return
        self.state = state
        log.info("State changed from %s to %s", old_state.name, state.name)
        sig = signal("server_state")
        sig.send(self, old_state=old_state, new_state=state)

    def process(self, name):
        return self.procs[name]


