#!/usr/bin/env python
# -*- coding:utf-8 -*-
from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()


with open("boneio/version.py") as f:
    exec(f.read())

setup(
    name="boneio",
    version=__version__,  # type: ignore # noqa: F821,
    description="Python Helper for BoneIO",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/maciejk1984/boneIO",
    download_url="https://github.com/maciejk1984/boneIO/archive/{}.zip".format(
        __version__  # type: ignore # noqa: F821
    ),
    packages=find_packages(exclude=["tests*"]),
    include_package_data=True,
    license="GNU General Public License v3.0",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    install_requires=[
        "Adafruit-BBIO==1.2.0",
        "Adafruit-Blinka==6.15.0",
        "adafruit-circuitpython-mcp230xx==2.5.1",
        "adafruit-circuitpython-pct2075==1.1.11",
        "Adafruit-PlatformDetect==3.17.2",
        "Adafruit-PureIO==1.1.9",
        "asyncio-mqtt==0.10.0",
        "Cerberus==1.3.4",
        "click==8.0.3",
        "colorlog==6.5.0",
        "gpio==0.3.0",
        "luma.core==2.3.1",
        "luma.oled==3.8.1",
        "numpy==1.21.4",
        "paho-mqtt==1.6.1",
        "psutil==5.8.0",
        "pyaml==21.10.1",
        "typing-extensions==3.10.0.2",
    ],
    entry_points={"console_scripts": ["boneio=boneio.bonecli:cli"]},
)
