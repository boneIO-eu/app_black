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
    description="Python App for BoneIO",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/boneIO-eu/app_bbb",
    download_url="https://github.com/boneIO-eu/app_bbb/archive/{}.zip".format(
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
        "Adafruit-Blinka==6.20.4",
        "adafruit-circuitpython-mcp230xx==2.5.3",
        "adafruit-circuitpython-mcp9808==3.3.10",
        "adafruit-circuitpython-pct2075==1.1.12",
        "adafruit-circuitpython-register==1.9.8",
        "adafruit-circuitpython-busdevice==5.1.4",
        "Adafruit-PlatformDetect==3.19.5",
        "Adafruit-PureIO==1.1.9",
        "asyncio-mqtt==0.12.1",
        "Cerberus==1.3.4",
        "colorlog==6.6.0",
        "gpio==0.3.0",
        "luma.core==2.3.1",
        "luma.oled==3.8.1",
        "numpy==1.21.5",
        "Pillow==9.0.1",
        "paho-mqtt==1.6.1",
        "psutil==5.9.0",
        "pyaml==21.10.1",
        "pymodbus==2.5.3",
        "pyserial-asyncio==0.6",
        "typing_extensions==4.1.0",
    ],
    entry_points={"console_scripts": ["boneio=boneio.bonecli:main"]},
)
