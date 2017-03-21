#!/usr/bin/env python

from setuptools import find_packages
from setuptools import setup


def find_subpackages(package):
    packages = [package]
    for subpackage in find_packages(package):
        packages.append("{0}.{1}".format(package, subpackage))
    return packages


setup(name="netmet",
      version="0.1",
      description="Simple Continious Mesh Network Monitoring Tool",
      url="",
      author="Boris Pavlovic",
      author_email="bpavlovic@godaddy.com",
      packages=find_subpackages("netmet"),
      platforms='Linux',
      license='Apache 2.0',
      entry_points={
          "console_scripts": [
              "netmet-server = netmet.server.main:main",
              "netmet-client = netmet.client.main:main"
          ]
      })
