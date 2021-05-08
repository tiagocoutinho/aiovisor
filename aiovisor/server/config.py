"""

Example:

```toml
[main]
name = "aiovisor"
pidfile = "/tmp/aiovisor.pid"
daemon = true
umask = 0o27
user = "homer"
group = "simpsons"
directory = {here}

[main.logging]
config = "./aiovisor_logging.conf"

[program.web-server-lab01]
command = "/bin/apache"
name = "web server"
tags = ["web", "lab01"]

```
"""

import os
import shlex
import pathlib

from ..util import is_posix


DEFAULT_LOG_CONFIG = {
    "version": 1,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)8s %(name)s: %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "root": {
        "handlers": ['console'],
        "level": "INFO"
    }
}


def load_config_raw(filename):
    filename = pathlib.Path(filename)
    ext = filename.suffix
    if ext == '.toml':
        from toml import load
    elif ext in {'.yml', '.yaml'}:
        import yaml
        def load(fobj):
            return yaml.load(fobj, Loader=yaml.Loader)
    elif ext == '.json':
        from json import load
    elif ext == '.py':
        def load(fobj):
            r = {}
            exec(fobj.read(), None, r)
            return r
    else:
        raise ValueError(f'Unsupported file {filename.suffix!r}')
    with open(filename)as fobj:
       return load(fobj)


def config_program(name, cfg):
    result = dict(
        name=name,
        environment=None,
        directory=None,
        exitcodes=[0],
        startsecs=1,
        user=None,
        umask=-1 if is_posix else None,
        resources={},
    )
    result.update(cfg)
    cmd = result["command"]
    if isinstance(cmd, str):
        result["command"] = shlex.split(cmd)
    return result


def config_programs(cfg):
    return {name: config_program(name, pcfg) for name, pcfg in cfg.items()}


def config_logging(cfg):
    result = dict(
        version=1,
        disable_existing_loggers=False
    )
    result.update(cfg)
    return result


def config_web(cfg):
    result = dict(cfg)
    if "uvicorn" in result:
        uvicorn = dict(log_config=None)
        uvicorn.update(result["uvicorn"])
        # need to force asyncio event loop because at the moment
        # uvloop.subprocess_exec does not support "user" keyword argument
        # (using uvloop is 0.15.2)
        uvicorn["loop"] = "asyncio"
        result["uvicorn"] = uvicorn
    return result


def config_main(cfg):
    result = dict(
        name=os.uname(),
    )
    result.update(cfg)
    result["logging"] = config_logging(result.get("logging", DEFAULT_LOG_CONFIG))
    return result


def load_config(config_file):
    config = load_config_raw(config_file)
    return dict(
        main=config_main(config.get("main", {})),
        programs=config_programs(config.get("programs", {})),
        web=config_web(config.get("web", {})),
    )
