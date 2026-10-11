import pathlib
import shutil
import stat
import sys
import tempfile

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
collect_ignore = ["fixtures"]


def remove_readonly(function, path, exception):
    if not isinstance(exception, PermissionError):
        raise exception
    pathlib.Path(path).chmod(stat.S_IWRITE)
    function(path)


def pytest_configure(config):
    # All test artifacts stay inside the packet's tests/ write boundary.
    config.cache._cachedir = pathlib.Path(__file__).parent / "fixtures" / ".pytest-cache"


@pytest.fixture
def tmp_path():
    root = pathlib.Path(__file__).parent / "fixtures"
    root.mkdir(exist_ok=True)
    path = pathlib.Path(tempfile.mkdtemp(prefix="run-", dir=root))
    try:
        yield path
    finally:
        shutil.rmtree(path, onexc=remove_readonly)
