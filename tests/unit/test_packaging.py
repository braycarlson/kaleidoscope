from __future__ import annotations

import shutil
import subprocess
import zipfile

import pytest

from pathlib import Path


pytestmark = pytest.mark.packaging
REPOSITORY = Path(__file__).resolve().parents[2]
PROJECT_FILES = ('LICENSE', 'README.md', 'pyproject.toml')
FRONTEND_MARKERS = ('/ui/', 'node_modules')

SHIPPED_ASSETS = frozenset({
    'kaleidoscope/static/kaleidoscope/kaleidoscope-sql-formatter.js',
    'kaleidoscope/static/kaleidoscope/kaleidoscope.css',
    'kaleidoscope/static/kaleidoscope/kaleidoscope.js',
    'kaleidoscope/templates/shell.html',
})

SHIPPED_DIRECTORIES = frozenset({'kaleidoscope', 'kaleidoscope/panels'})


def _project_copied(target: Path) -> None:
    ignored = shutil.ignore_patterns('__pycache__', 'node_modules')

    shutil.copytree(REPOSITORY / 'kaleidoscope', target / 'kaleidoscope', ignore=ignored)

    for name in PROJECT_FILES:
        shutil.copy2(REPOSITORY / name, target / name)

    modules = REPOSITORY / 'kaleidoscope' / 'ui' / 'node_modules'

    if modules.is_dir():
        (target / 'kaleidoscope' / 'ui' / 'node_modules').symlink_to(modules)


@pytest.fixture(scope='module')
def wheel_names(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    uv = shutil.which('uv')

    if uv is None:
        pytest.skip('uv is not installed')

    project = tmp_path_factory.mktemp('project')
    output = tmp_path_factory.mktemp('wheel')

    _project_copied(project)

    subprocess.run(
        [uv, 'build', '--wheel', '--out-dir', str(output), str(project)],
        capture_output=True,
        check=True,
    )

    wheel = next(output.glob('*.whl'))

    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


def test_the_wheel_ships_only_the_package_and_its_assets(wheel_names: list[str]) -> None:
    shipped = [Path(name) for name in wheel_names if name.startswith('kaleidoscope/')]
    python_directories = {path.parent.as_posix() for path in shipped if path.suffix == '.py'}
    assets = {path.as_posix() for path in shipped if path.suffix != '.py'}

    assert python_directories == SHIPPED_DIRECTORIES
    assert assets == SHIPPED_ASSETS


def test_the_wheel_ships_no_frontend_source_or_dependencies(wheel_names: list[str]) -> None:
    leaked = [name for name in wheel_names if any(marker in name for marker in FRONTEND_MARKERS)]

    assert leaked == []
