import sys


pytest_plugins = [
    "jupyter_server.pytest_plugin"
]


def pytest_configure(config):

    if all([
        sys.platform.startswith("win32"),
        sys.version_info.major == 3,
        sys.version_info.minor == 6,
        config.option.capture is None
    ]):
        config.option.capture == 'sys'
