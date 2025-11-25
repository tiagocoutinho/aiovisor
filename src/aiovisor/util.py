import asyncio
import logging
import os
import sys

from blinker import signal

__all__ = ["signal", "log", "is_posix"]


log = logging.getLogger(__package__)


is_posix = os.name == "posix"
py_ver = sys.version_info[:2]

class AIOVisorError(Exception):
    pass


def setup_posix_event_loop():
    if py_ver >= (3, 14):
        return

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


def setup_event_loop():
    if is_posix:
        return setup_posix_event_loop()
