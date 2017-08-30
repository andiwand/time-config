from setuptools import setup

setup(
    name="time-config",
    version="0.0.1",
    url="https://github.com/andiwand/time-config",
    license="GNU Lesser General Public License",
    author="Andreas Stefl",
    install_requires=[],
    author_email="stefl.andreas@gmail.com",
    description="Startup script for ntp/ptp/gps.",
    long_description="",
    package_dir={"": "src"},
    packages=["timeconfig"],
    platforms=["linux"],
    entry_points={
        "console_scripts": ["time-config = timeconfig.start:main"]
    },
)
