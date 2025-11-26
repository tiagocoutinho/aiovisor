import pathlib
import platform
import contextlib

import pytest

from aiovisor.server import config


C1_RAW = {
    "programs": {
        "web-server-lab1": {
            "command": "/hello/exec something",
            "tags": ["web", "lab1"],
        }
    }
}


C1_PARSED = {
    "main": {
        "name": platform.uname().node,
        "uname": platform.uname(),
        "logging": dict(config.DEFAULT_LOG_CONFIG)
    },
    "web": {},
    "programs": {
        "web-server-lab1": {
            "name": "web-server-lab1",
            "environment": None,
            "directory": None,
            "exitcodes": [0],
            "startsecs": 1,
            "startretries": 3,
            "autostart": True,
            "stopwaitsecs": 10,
            "stopsignal": 15,
            "user": None,
            "umask": -1,
            "resources": {},
            "command":["/hello/exec", "something"],
            "tags": ["web", "lab1"],
        }
    },
}

ctx_result = contextlib.nullcontext


def local_file(fname):
    return pathlib.Path(__file__).parent / fname


@pytest.mark.parametrize(
    "config_raw, config_parsed",
    [(C1_RAW, C1_PARSED)],
    ids=["basic"]
)
def test_parse_config(config_raw, config_parsed):
    assert config.parse_raw_config(config_raw) == config_parsed


@pytest.mark.parametrize(
    "filename, ctx_result",
    [(local_file("c1.toml"), ctx_result(C1_RAW)),
     (local_file("c1.yaml"), ctx_result(C1_RAW)),
     (local_file("c1.json"), ctx_result(C1_RAW)),
     (local_file("c1.py"), ctx_result(C1_RAW)),
     ('/tmp/inexisting.toml', pytest.raises(OSError)),
     (local_file("c1.bin"), pytest.raises(ValueError))],
    ids=['basic-toml', 'basic-yaml', 'basic-json', 'basic-py',
         'inexisting-file', 'unsupported-file-type']
)
def test_load_config_raw(filename, ctx_result):
    with ctx_result as config_raw:
        assert config.load_config_raw(filename) == config_raw


@pytest.mark.parametrize(
    "filename, ctx_result",
    [(local_file("c1.toml"), ctx_result(C1_PARSED)),
     (local_file("c1.yaml"), ctx_result(C1_PARSED)),
     (local_file("c1.json"), ctx_result(C1_PARSED)),
     (local_file("c1.py"), ctx_result(C1_PARSED)),
     ('/tmp/inexisting.toml', pytest.raises(OSError)),
     (local_file("c1.bin"), pytest.raises(ValueError))],
    ids=['basic-toml', 'basic-yaml', 'basic-json', 'basic-py',
         'inexisting-file', 'unsupported-file-type']
)
def test_load_config(filename, ctx_result):
    with ctx_result as config_parsed:
        assert config.load_config(filename) == config_parsed
