from os import getpid
from time import sleep

from .daemonize import daemonize


if __name__ == "__main__":
    APP = "test_app"

    pid = f"/tmp/{APP}.pid"

    with daemonize(APP, pid):
        with open('/tmp/bla', 'w') as f:
            for i in range(100):
                f.write(f'loop {i}\n')
                sleep(1)
                f.flush()

