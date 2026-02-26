from setuptools import setup, find_packages

setup(
    name="autoquant-day04",
    version="0.1.0",
    packages=find_packages(where=".", include=["src*"]),
    package_dir={"": "."},
    python_requires=">=3.11",
    install_requires=[
        "alpaca-py>=0.13.0",
        "rich>=13.0",
    ],
    extras_require={
        "dev": ["pytest>=7.4", "pytest-asyncio>=0.23"],
    },
)

