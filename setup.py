# -*- coding: utf-8 -*-

"""The setup script."""

import sys
from setuptools import setup, find_packages

TESTING = any(x in sys.argv for x in ["test", "pytest"])

setup_requirements = []
if TESTING:
    setup_requirements += ['pytest-runner']
test_requirements = ['pytest', 'pytest-cov']

extras = {
    "server-toml": ["toml"],
    "server-yaml": ["pyyaml"],
    "server-web": ["fastapi", "hypercorn"],
}
extras["all"] = list(set.union(*(set(i) for i in extras.values())))


with open("README.md") as f:
    description = f.read()


setup(
    name="aiovisor",
    author="Jose Tiago Macara Coutinho",
    author_email="coutinhotiago@gmail.com",
    description="spawn and monitor processes",
    license="GPLv3+",
    long_description=description,
    long_description_content_type="text/markdown",
    keywords="supervisor, asyncio",
    packages=find_packages(),
    url="https://gitlab.com/tiagocoutinho/aiovisor",
    version="0.1.0",
    python_requires=">=3.7",
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    extras_require=extras,
    entry_points={
        "console_scripts": [
            "aiovisor=aiovisor.server.cli:main"
        ]
    },
)
