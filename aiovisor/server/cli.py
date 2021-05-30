import pathlib
import argparse
import logging.config

from ..util import log
from .web import run_app
from .core import AIOVisor
from .config import load_config


def prepare_logging(config):
    main = config["main"]
    logging.config.dictConfig(main["logging"])
    log.info("Starting...")


def run(config_file):
    config = load_config(config_file)
    prepare_logging(config)
    aiovisor = AIOVisor(config)
    run_app(aiovisor, config["web"]["aiohttp"])


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", required=True, type=pathlib.Path)
    opts = parser.parse_args(args=args)
    run(opts.config_file)


if __name__ == "__main__":
    main()
