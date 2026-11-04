import pathlib
import shutil
import stat
import sys
import tempfile

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
collect_ignore = ["fixtures"]


SIZE = (240, 120)


def area(id, kind, x, y, w=40, h=16):
    return {"id": id, "kind": kind, "corners": [[x, y], [x + w, y + 2], [x + w, y + h], [x, y + h - 2]],
            "color": "#ff2bd6", "blur": 1.5, "reflection": [[x, 100], [x + w, 100], [x + w, 112], [x, 112]]}


def spots():
    return {"areas": [area("sign-tokens", "tokens", 5, 6, 72, 20), area("sign-commits", "commits", 82, 6, 72, 20),
                      area("holo-1", "hologram", 10, 40), area("holo-2", "hologram", 60, 40),
                      area("holo-3", "hologram", 110, 40), area("billboard", "billboard", 160, 8, 76, 30)]}


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
