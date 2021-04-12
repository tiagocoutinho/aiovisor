import asyncio
import pathlib
import argparse

from .core import run


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", required=True, type=pathlib.Path)
    opts = parser.parse_args(args=args)
    asyncio.run(run(opts.config_file))


if __name__ == "__main__":
    main()
