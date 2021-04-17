import os
import logging

from blinker import signal

__all__ = ["signal", "log", "is_posix"]


log = logging.getLogger(__package__)


is_posix = os.name == "posix"


class AIOVisorError(Exception):
    pass
