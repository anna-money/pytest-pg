import re
from pathlib import Path

from setuptools import setup

install_requires = [
    "docker>=5.0.0",
    "pytest>=6.0.0",
]


def read(*parts):
    return Path(__file__).resolve().parent.joinpath(*parts).read_text().strip()


def read_version():
    regexp = re.compile(r"^__version__\W*=\W*\"([\d.abrc]+)\"")
    for line in read("pytest_pg", "__init__.py").splitlines():
        match = regexp.match(line)
        if match is not None:
            return match.group(1)
    else:
        raise RuntimeError("Cannot find version in pytest_pg/__init__.py")


long_description_parts = []
with open("README.md", "r") as fh:
    long_description_parts.append(fh.read())

with open("CHANGELOG.md", "r") as fh:
    long_description_parts.append(fh.read())

long_description = "\r\n".join(long_description_parts)

# custom PyPI classifier for pytest plugins
classifiers = ["Framework :: Pytest"],
setup(
    name="pytest_pg",
    version=read_version(),
    description="Helps to run PostgreSQL in docker as pytest fixture",
    long_description=long_description,
    long_description_content_type="text/markdown",
    platforms=["macOS", "POSIX", "Windows"],
    author="Yury Pliner",
    python_requires=">=3.8",
    project_urls={},
    url="https://github.com/anna-money/pytest-pg",
    author_email="yury.pliner@gmail.com",
    license="MIT",
    packages=["pytest_pg"],
    package_dir={"pytest_pg": "./pytest_pg"},
    package_data={"pytest_pg": ["py.typed"]},
    install_requires=install_requires,
    include_package_data=True,
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Operating System :: OS Independent",
        "Development Status :: 5 - Production/Stable",
        "Framework :: Pytest"
    ],
    entry_points={
        "pytest11": [
            "pytest_pg = pytest_pg",
        ]
    }
)
