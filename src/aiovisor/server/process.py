import datetime
import enum
import time
import asyncio
import resource
import subprocess


try:
    import psutil
except ModuleNotFoundError:
    psutil = None

from ..util import is_posix, signal, log, AIOVisorError


PSUTIL_ATTRS = (
    "cmdline",
    "cpu_times",
    "create_time",
    "cwd",
    "exe",
    "memory_full_info",
    "name",
    "num_ctx_switches",
    "num_fds",
    "num_threads",
    "open_files",
)


class ProcessState(enum.IntEnum):
    Stopped = 0
    Starting = 1
    Running = 2
    Backoff = 3
    Stopping = 4
    Exited = 5
    Fatal = 6
    Unknown = 1000

    @property
    def is_stopped(self):
        return self in STOPPED_STATES

    @property
    def is_running(self):
        return self in RUNNING_STATES

    @property
    def is_startable(self):
        return self in STARTABLE_STATES

    @property
    def is_stoppable(self):
        return self in STOPPABLE_STATES


STOPPED_STATES = {
    ProcessState.Stopped,
    ProcessState.Exited,
    ProcessState.Fatal,
    ProcessState.Unknown,
}
RUNNING_STATES = {ProcessState.Starting, ProcessState.Running, ProcessState.Backoff}
STARTABLE_STATES = {
    ProcessState.Stopped,
    ProcessState.Exited,
    ProcessState.Fatal,
    ProcessState.Backoff,
}
STOPPABLE_STATES = {
    ProcessState.Starting,
    ProcessState.Running,
    ProcessState.Backoff,
    ProcessState.Unknown,
}


def get_ps(pid):
    if psutil is None or pid is None:
        return {}
    try:
        proc = psutil.Process(pid)
        return {
            k: v._asdict() if isinstance(v, tuple) else v
            for k, v in proc.as_dict(PSUTIL_ATTRS).items()
        }
    except psutil.NoSuchProcess:
        return {}


async def wait_for(aw, timeout):
    """Returns false if the awaitable is still running after the timeout"""
    try:
        await asyncio.wait_for(aw, timeout=timeout)
    except asyncio.TimeoutError:
        return False
    return True


class Process:
    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.state = ProcessState.Stopped
        self.start_time = None
        self.stop_time = None
        self.log = log.getChild(f"{type(self).__name__}.{name}")
        self.proc = None
        self.last_error = None
        self.last_returncode = None

    @property
    def is_running(self):
        if self.proc is None:
            return False
        return self.proc.returncode is None

    @property
    def pid(self):
        if self.is_running:
            return self.proc.pid

    @property
    def start_datetime(self):
        return (
            None
            if self.start_time is None
            else datetime.datetime.fromtimestamp(self.start_time)
        )

    @property
    def stop_datetime(self):
        return (
            None
            if self.stop_time is None
            else datetime.datetime.fromtimestamp(self.stop_time)
        )

    def ps(self):
        return get_ps(self.pid)

    def info(self):
        return dict(
            name=self.name,
            config=self.config,
            state=dict(
                state=self.state,
                start_time=self.start_time,
                stop_time=self.stop_time,
                last_returncode=self.last_returncode,
                last_error=self.last_error,
                pid=self.pid,
            ),
            ps=self.ps(),
        )

    def _pre_exec(self):
        if not (resources := self.config["resources"]):
            return
        for key, value in resources.items():
            if value is None:
                continue
            res = getattr(resource, "RLIMIT_" + key.upper())
            soft, hard = resource.getrlimit(res)
            resource.setrlimit(res, (value, hard))

    def _create_process_args(self):
        if self.config["shell"]:
            args = [self.config["command_line"]]
        else:
            args = self.config["command"]
        kwargs = dict(
            env=self.config["environment"],
            cwd=self.config["directory"],
            close_fds=True,
        )
        if is_posix:
            kwargs["start_new_session"] = True
            kwargs["user"] = self.config["user"]
            kwargs["preexec_fn"] = self._pre_exec
        else:
            kwargs["creationflags"] = [subprocess.CREATE_NEW_PROCESS_GROUP]
        return args, kwargs

    async def _create_process(self):
        args, kwargs = self._create_process_args()
        if self.config["shell"]:
            create = asyncio.create_subprocess_shell
        else:
            create = asyncio.create_subprocess_exec
        try:
            return await create(*args, **kwargs)
        except Exception as error:
            self.log.error("Cannot start program: %r", error)
            self.last_error = str(error)

    def change_state(self, state):
        old_state = self.state
        if state == old_state:
            return
        self.state = state
        self.log.info("State changed from %s to %s", old_state.name, state.name)
        sig = signal("process_state")
        sig.send(self, old_state=old_state, new_state=state)

    async def start(self):
        if self.is_running:
            raise AIOVisorError(f"{self.name!r} already running!")
        if not self.state.is_startable:
            raise AIOVisorError(
                f"{self.name!r} not in startable state (is {self.state.name})"
            )
        asyncio.create_task(self._run(), name=self.name + "-loop")

    async def _try_start(self, attempt, attempts):
        self.log.info("Starting (attempt %d of %d)", attempt, attempts)
        self.change_state(ProcessState.Starting)
        if (proc := await self._create_process()) is None:
            self.change_state(ProcessState.Fatal)
            return
        self.change_state(ProcessState.Starting)
        self.proc = proc
        startsecs = self.config["startsecs"]
        self.start_time = time.time()
        done = await wait_for(self.proc.wait(), timeout=startsecs)
        if done:
            # process was stopped before reached running
            self.last_returncode = self.proc.returncode
            if self.state == ProcessState.Stopping:
                # by user command
                self.change_state(ProcessState.Stopped)
            elif attempt < attempts:
                self.log.warning(
                    "Failed to start (attempt %d of %d)", attempt, attempts
                )
                self.change_state(ProcessState.Backoff)
            else:
                self.log.error("Give up start (attempt %d of %d)", attempt, attempts)
                self.change_state(ProcessState.Fatal)
        else:
            self.log.info("Successfull start")
            self.change_state(ProcessState.Running)

    async def _run(self):
        attempt, attempts = 0, self.config["startretries"] + 1
        while attempt < attempts:
            attempt += 1
            await self._try_start(attempt, attempts)
            if self.state != ProcessState.Backoff:
                break
            await asyncio.sleep(attempt)

        if self.state != ProcessState.Running:
            return

        self.last_returncode = await self.proc.wait()
        if self.state in {ProcessState.Stopping, ProcessState.Stopped}:
            return
        # Process finished by itself
        self.stop_time = time.time()
        dt = self.stop_time - self.start_time
        self.log.info("Process exited by itself after %g seconds", dt)
        self.change_state(ProcessState.Exited)

    async def stop(self):
        if self.state == ProcessState.Stopped:
            raise AIOVisorError(f"{self.name!r} already stopped!")
        if not self.state.is_stoppable:
            raise AIOVisorError(
                f"{self.name!r} not in stoppable state (is {self.state.name})"
            )
        if self.state == ProcessState.Backoff:
            self.change_state(ProcessState.Stopped)
            return
        return await self._stop()

    async def _stop(self):
        proc = self.proc
        if proc is None or proc.returncode is not None:
            return
        start_stop_time = time.monotonic()
        self.change_state(ProcessState.Stopping)
        if is_posix:
            proc.send_signal(self.config["stopsignal"])
        else:
            proc.terminate()
        wait_ended = asyncio.create_task(proc.wait())
        stopwaitsecs = self.config["stopwaitsecs"]
        done, _ = await asyncio.wait(
            (wait_ended,), timeout=stopwaitsecs, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            self.log.warning(
                "Refused to stop in %g seconds. Going in for the kill", stopwaitsecs
            )
            proc.kill()
        return_code = await wait_ended
        end_stop_time = time.monotonic()
        self.stop_time = time.time()
        self.change_state(ProcessState.Stopped)
        self.log.info("Stopped (took %g seconds)", end_stop_time - start_stop_time)
        return return_code

    async def kill(self):
        if self.state == ProcessState.Stopped:
            raise AIOVisorError(f"{self.name!r} already stopped!")
        if not self.state.is_stoppable:
            raise AIOVisorError(
                f"{self.name!r} not in stoppable state (is {self.state.name})"
            )
        if self.state == ProcessState.Backoff:
            self.change_state(ProcessState.Stopped)
            return
        proc = self.proc
        if proc is None or proc.returncode is not None:
            return
        start_kill_time = time.monotonic()
        self.change_state(ProcessState.Stopping)
        proc.kill()
        return_code = await proc.wait()
        end_kill_time = time.monotonic()
        self.stop_time = time.time()
        self.change_state(ProcessState.Stopped)
        self.log.info("Killed (took %g seconds)", end_kill_time - start_kill_time)
        return return_code
