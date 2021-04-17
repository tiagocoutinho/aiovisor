import enum
import time
import asyncio
import subprocess


from ..util import is_posix, signal, log, AIOVisorError


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


class Process:

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.state = ProcessState.Stopped
        self.start_time = 0
        self.log = log.getChild(f"{type(self).__name__}.{name}")
        self.proc = None
        self.task = None

    def info(self):
        return dict(
            self.config, name=self.name, state=self.state.name,
            start_time=self.start_time,
            return_code=self.returncode(),
            pid=self.pid(),
        )

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
        old_state = self.state
        if state == old_state:
            return
        self.state = state
        self.log.info("State changed from %s to %s", old_state.name, state.name)
        sig = signal("process_state")
        sig.send(self, old_state=old_state, new_state=state)

    def pid(self):
        if self.proc is not None:
            return self.proc.pid

    def returncode(self):
        if self.proc is not None:
            return self.proc.returncode

    async def start(self):
        self.log.info("Starting %r", self.config["command"])
        if self.pid() is not None and self.returncode() is None:
            raise AIOVisorError(f"{self.name!r} already running!")
        if not self.state.is_startable():
            raise AIOVisorError(
                f"{self.name!r} not in startable state (is {self.state.name})")
        self.change_state(ProcessState.Starting)
        args, kwargs = self._create_process_args()
        self.start_time = time.time()
        self.proc = await asyncio.create_subprocess_exec(*args, **kwargs)
        self.task = asyncio.create_task(self._run(self.proc))

    async def _run(self, proc):
        startsecs = self.config["startsecs"]
        wait = asyncio.create_task(proc.wait())
        done, _ = await asyncio.wait(
            (wait,), timeout=startsecs, return_when=asyncio.FIRST_COMPLETED)
        if done:
            # process was stopped before reached running, either by error or
            # by user command
            return_code = await wait
            self.change_state(ProcessState.Backoff)
            # TODO: handle retries
            self.change_state(ProcessState.Exited)
        else:
            self.change_state(ProcessState.Running)
            return_code = await wait
            if self.state == ProcessState.Stopping:
                state = ProcessState.Stopped
            else:
                state = ProcessState.Exited
            self.change_state(state)
        return return_code

    async def terminate(self):
        proc = self.proc
        if proc is not None and proc.returncode is None:
            self.change_state(ProcessState.Stopping)
            proc.terminate()
            await self.task
