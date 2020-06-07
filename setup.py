# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

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
    python_requires=">=3.7"
)
