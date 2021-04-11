import os
import asyncio
import pathlib
import argparse
import logging.config

from ..util import is_posix
from .config import load_config
from .process import Process


def setup(config):
    logging.config.dictConfig(config["logging"])
    if is_posix:
        if hasattr(os, "pidfd_open") and hasattr(asyncio, "PidfdChildWatcher"):
            child_watcher = asyncio.PidfdChildWatcher()
        else:
            child_watcher = asyncio.FastChildWatcher()
        child_watcher.attach_loop(asyncio.get_running_loop())
        asyncio.set_child_watcher(child_watcher)


async def run(config_file):
    config = load_config(config_file)
    setup(config["main"])
    programs = config["programs"]
    progs = [Process(name, cfg) for name, cfg in programs.items()]

    starts = (prog.start() for prog in progs)
    await asyncio.gather(*starts)

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        print("Shutting down...")
        stops = (prog.terminate() for prog in progs)
        await asyncio.gather(*stops)
        print("Done!")


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", required=True, type=pathlib.Path)
    opts = parser.parse_args(args=args)
    asyncio.run(run(opts.config_file))


if __name__ == "__main__":
    main()
