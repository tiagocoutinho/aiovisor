import pathlib

"""

[main]
name = "aiovisor"
pidfile = "/tmp/aiovisor.pid"
daemon = true
#umask = 0o27
# user = "homer"
# group = "simpsons"
# directory = {here}

[main.logging]
#config = "./aiovisor_logging.conf"

[program.web-server-lab01]
command = "/bin/apache"
name = "web server"
tags = ["web", "lab01"]


"""

DEFAULT = {
    "main" : {
        "name": "aiovisor",
        "pidfile": "/tmp/{name}",
        "umask": 0o27
    }
}


def load_config_raw(filename):
    filename = pathlib.Path(filename)
#    if not filename.exists():
#        raise ValueError('configuration file does not exist')
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
        # python only supports a single detector definition
        def load(fobj):
            r = {}
            exec(fobj.read(), None, r)
            return r
    else:
        raise ValueError(f'Unsupported file {filename.suffix!r}')
    with open(filename)as fobj:
       return load(fobj)


def parse_config(config, item):
    if isinstance(item, dict):
        result = {}
        for k, v in item.items():
            result[k] = parse_config(config, v)
    elif isinstance(item, (tuple, list)):
        result = [parse_config(config, elem) for elem in item]
    elif isinstance(item, str):
        result = item.format(**config)
    else:
        result = item
    return result


def load_config(filename):
    raw = load_config_raw(filename)
    return parse_config(raw, raw)
