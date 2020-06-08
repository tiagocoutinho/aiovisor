import pathlib
import contextlib

import pytest

from aiovisor import config


C1_RAW = {
    "main": {
        "base": "/hello",
        "directory": "{main[base]}/world"
    },
    "program": {
        "web-server-lab1": {
            "command": "{main[base]}/exec something",
            "groups": ["web", "lab1"],
            "priority": 9
        }
    }
}


C1_PARSED = {
    "main": {
        "base": "/hello",
        "directory": "/hello/world"
    },
    "program": {
        "web-server-lab1": {
            "command": "/hello/exec something",
            "groups": ["web", "lab1"],
            "priority": 9
        }
    }
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
    assert config.parse_config(config_raw, config_raw) == config_parsed


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
