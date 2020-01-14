"""
dotdeploy Command Line - A simple dotfile deployment system written in Python
"""

from dotdeploy import DotDeploy

from setuptools import setup, find_packages

setup(
    name=DotDeploy.NAME,
    version=DotDeploy.VERSION,
    description="A simple dotfile deployment system written in Python",
    url="https://github.com/jakemalley/dotdeploy",
    author="Jake Malley",
    author_email="jja.malley@gmail.com",
    license="MIT",
    packages=find_packages(exclude=["tests"]),
    zip_safe=False,
    entry_points={"console_scripts": ["dotdeploy = dotdeploy.cli:main"]},
    extras_require={"dev": ["pylint", "black", "mock", "coverage", "nose2"]},
)
