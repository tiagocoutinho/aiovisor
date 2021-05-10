import os
import asyncio
import logging

from blinker import signal

__all__ = ["signal", "log", "is_posix"]


log = logging.getLogger(__package__)


is_posix = os.name == "posix"


class AIOVisorError(Exception):
    pass


def setup_event_loop():
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
