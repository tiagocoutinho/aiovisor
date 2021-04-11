import enum
import time
import asyncio
import logging
import subprocess


from ..util import is_posix


log = logging.getLogger(__package__)


class ProcessState(enum.IntEnum):

    Stopped = 0
    Starting = 1
    Running = 2
    Backoff = 3
    Stopping = 4
    Exited = 5
    Fatal = 6
    Unknown = 1000

    def is_stopped(self):
        return self in STOPPED_STATES

    def is_running(self):
        return self in RUNNING_STATES

    def is_startable(self):
        return self in STARTABLE_STATES


STOPPED_STATES = {
    ProcessState.Stopped, ProcessState.Exited, ProcessState.Fatal, ProcessState.Unknown
}
RUNNING_STATES = {
    ProcessState.Starting, ProcessState.Running, ProcessState.Backoff
}
STARTABLE_STATES = {
    ProcessState.Stopped, ProcessState.Exited, ProcessState.Fatal, ProcessState.Backoff
}


class AIOVisorError(Exception):
    pass


class Process:

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.state = ProcessState.Stopped
        self.last_start_time = 0
        self.log = log.getChild(f"{type(self).__name__}.{name}")
        self.proc = None
        self.task = None

    def _create_process_args(self):
        args = self.config["command"]
        kwargs = dict(
            env=self.config["environment"],
            cwd=self.config["directory"],
            close_fds=True,
            shell=False,
        )
        if is_posix:
            kwargs["start_new_session"] = True
            kwargs["user"] = self.config["user"]
        else:
            kwargs["creationflags"] = [subprocess.CREATE_NEW_PROCESS_GROUP]
        return args, kwargs

    def change_state(self, state):
        if state == self.state:
            return
        self.log.info("State changed from %s to %s", self.state.name, state.name)
        self.state = state

    def pid(self):
        if self.proc is not None:
            return self.proc.pid

    def returncode(self):
        if self.proc is not None:
            return self.proc.returncode

    async def start(self):
        self.log.info("Attempting to start %r", self.config["command"])
        if self.pid() is not None:
            raise AIOVisorError("f{self.name!r} already running!")
        if not self.state.is_startable():
            raise AIOVisorError(
                f"{self.name!r} not in startable state (is {self.state.name})")
        self.last_start_time = time.time()
        self.change_state(ProcessState.Starting)
        args, kwargs = self._create_process_args()
        self.proc = await asyncio.create_subprocess_exec(*args, **kwargs)
        self.task = asyncio.create_task(self._run(self.proc))

    async def _run(self, proc):
        startsecs = self.config["startsecs"]
        wait = asyncio.create_task(proc.wait())
        done, pending = await asyncio.wait(
            (wait,), timeout=startsecs, return_when=asyncio.FIRST_COMPLETED)
        if done:
            # process was stopped before reached running, either by error or
            # by user command
            return_code = await wait
            self.change_state(ProcessState.Exited)
            return return_code
        self.change_state(ProcessState.Running)
        return await wait

    async def terminate(self):
        if self.proc is not None:
            self.task.cancel()
            self.proc.terminate()
            await self.proc.wait()
            self.task = None
