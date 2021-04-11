import os
import enum
import shlex
import asyncio
import pathlib
import argparse
import subprocess

import toml

is_posix = os.name == "posix"


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
        return self in {self.Stopped, self.Exited, self.Fatal, self.Unknown}

    def is_running(self):
        return self in {self.Starting, self.Running, self.Backoff}

    def is_signallable(self):
        return self in {self.starting, self.Running, self.Stopping}


class Process:

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.proc = None

    def is_running(self):
        return self.proc is not None and self.proc.returncode is None

    def pid(self):
        if self.proc is not None:
            return self.proc.pid

    async def start(self):
        if self.is_running():
            raise RuntimeError("Already running!")
        args = self.config["command"]
        kwargs = dict(
            env=self.config["env"],
            close_fds=True,
            shell=False,
        )
        if is_posix:
            kwargs["start_new_session"] = True
            kwargs["user"] = self.config["user"]
        else:
            kwargs["creationflags"] = [subprocess.CREATE_NEW_PROCESS_GROUP]
        self.proc = await asyncio.create_subprocess_exec(*args, **kwargs)

    async def terminate(self):
        if self.proc is not None:
            self.proc.terminate()
            return await self.proc.wait()


def load_config(config_file):
    def prep_prog(name, cfg):
        cfg.setdefault("env", None)
        if is_posix:
            cfg.setdefault("user", None)
            cfg.setdefault("umask", -1)
        else:
            cfg.pop("user", None)
            cfg.pop("umask", None)
        cmd = cfg["command"]
        if isinstance(cmd, str):
            cfg["command"] = shlex.split(cmd)

    with open(config_file) as fobj:
        config = toml.load(fobj)
    glob = config.setdefault("global", {})
    glob.setdefault("name", os.uname())
    progs = config.setdefault("program", {})
    for name, opts in progs.items():
        prep_prog(name, opts)
    return config


async def run(config_file):
    config = load_config(config_file)
    progs = [Process(name, cfg) for name, cfg in config["program"].items()]

    starts = (prog.start() for prog in progs)
    await asyncio.gather(*starts)
    print("All started!")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Ctrl-C pressed. Terminating childs...")
        stops = (prog.terminate() for prog in progs)
        await asyncio.gather(*stops)
        print("Done!")


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", type=pathlib.Path)
    opts = parser.parse_args(args=args)
    asyncio.run(run(opts.config_file))


if __name__ == "__main__":
    main()
