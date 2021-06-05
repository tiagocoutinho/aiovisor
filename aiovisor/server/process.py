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


def get_psutil(pid):
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


class Process:
    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.state = ProcessState.Stopped
        self.start_time = None
        self.stop_time = None
        self.log = log.getChild(f"{type(self).__name__}.{name}")
        self.proc = None
        self.task = None

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
    def returncode(self):
        if self.proc is not None:
            return self.proc.returncode

    def info(self):
        pid = self.pid
        state = self.state
        return dict(
            config=self.config,
            state=dict(
                state=state.name,
                start_time=self.start_time,
                stop_time=self.stop_time,
                return_code=self.returncode,
                pid=pid,
            ),
            psutil=get_psutil(pid),
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
            resources = self.config["resources"]
            if resources:

                def preexec_fn():
                    for key, value in resources.items():
                        if value is None:
                            continue
                        res = getattr(resource, "RLIMIT_" + key.upper())
                        soft, hard = resource.getrlimit(res)
                        resource.setrlimit(res, (value, hard))

                kwargs["preexec_fn"] = preexec_fn
        else:
            kwargs["creationflags"] = [subprocess.CREATE_NEW_PROCESS_GROUP]
        return args, kwargs

    def change_state(self, state):
        old_state = self.state
        if state == old_state:
            return
        self.state = state
        self.log.debug("State changed from %s to %s", old_state.name, state.name)
        sig = signal("process_state")
        sig.send(self, old_state=old_state, new_state=state)

    async def start(self):
        if self.is_running:
            raise AIOVisorError(f"{self.name!r} already running!")
        if not self.state.is_startable:
            raise AIOVisorError(
                f"{self.name!r} not in startable state (is {self.state.name})"
            )
        self.task = asyncio.create_task(self._run())

    async def _run(self):
        args, kwargs = self._create_process_args()
        name = self.config["name"]
        attempts = self.config["startretries"] + 1
        startsecs = self.config["startsecs"]
        attempt = 0
        while attempt < attempts:
            attempt += 1
            self.log.info("Starting %r (attempt %d of %d)", name, attempt, attempts)
            self.start_time = time.time()
            self.change_state(ProcessState.Starting)
            self.proc = await asyncio.create_subprocess_exec(*args, **kwargs)
            wait_ended = asyncio.create_task(self.proc.wait())
            done, _ = await asyncio.wait(
                (wait_ended,), timeout=startsecs, return_when=asyncio.FIRST_COMPLETED
            )
            if done:
                # process was stopped before reached running
                return_code = await wait_ended
                if self.state == ProcessState.Stopping:
                    # by user command
                    state = ProcessState.Stopped
                elif attempt < attempts:
                    self.log.info(
                        "Failed to start %r (attempt %d of %d)", name, attempt, attempts
                    )
                    state = ProcessState.Backoff
                else:
                    self.log.warning(
                        "Give up start %r (attempt %d of %d)", name, attempt, attempts
                    )
                    state = ProcessState.Fatal
            else:
                self.log.info("Sucessfull start of %r", name)
                state = ProcessState.Running
            self.change_state(state)
            if state == ProcessState.Backoff:
                await asyncio.sleep(attempt)
            else:
                break

        if state != ProcessState.Running:
            return

        return_code = await wait_ended
        if state not in {ProcessState.Stopping, ProcessState.Stopped}:
            # Process finished by itself
            self.change_state(ProcessState.Exited)
        return return_code

    async def stop(self):
        if self.state == ProcessState.Backoff:
            self.change_state(ProcessState.Stopped)
            return
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
                "Refused to stop %g seconds. Going in for the kill", stopwaitsecs
            )
            proc.kill()
        return_code = await wait_ended
        end_stop_time = time.monotonic()
        self.stop_time = time.time()
        self.change_state(ProcessState.Stopped)
        self.log.info("Stopped after %g seconds", end_stop_time - start_stop_time)
        return return_code
