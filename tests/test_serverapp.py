import os
import getpass
import pathlib
import pytest
import logging
from unittest.mock import patch

from traitlets import TraitError
from traitlets.tests.utils import check_help_all_output
from jupyter_core.application import NoStart
import nbformat

from jupyter_server.serverapp import (
    ServerApp,
    list_running_servers,
    JupyterPasswordApp,
    JupyterServerStopApp
)
from jupyter_server.auth.security import passwd_check


def test_help_output():
    """jupyter server --help-all works"""
    check_help_all_output('jupyter_server')


def test_server_info_file(tmp_path, jp_configurable_serverapp):
    app = jp_configurable_serverapp(log=logging.getLogger())

    app.write_server_info_file()
    servers = list(list_running_servers(app.runtime_dir))

    assert len(servers) == 1
    sinfo = servers[0]

    assert sinfo['port'] == app.port
    assert sinfo['url'] == app.connection_url
    assert sinfo['version'] == app.version

    app.remove_server_info_file()

    assert list(list_running_servers(app.runtime_dir)) == []
    app.remove_server_info_file


def test_root_dir(tmp_path, jp_configurable_serverapp):
    app = jp_configurable_serverapp(root_dir=str(tmp_path))
    assert app.root_dir == str(tmp_path)


# Build a list of invalid paths
@pytest.fixture(
    params=[
        ('notebooks',),
        ('root', 'dir', 'is', 'missing'),
        ('test.txt',)
    ]
)
def invalid_root_dir(tmp_path, request):
    path = tmp_path.joinpath(*request.param)
    # If the path is a file, create it.
    if os.path.splitext(str(path))[1] != '':
        path.write_text('')
    return str(path)


def test_invalid_root_dir(invalid_root_dir, jp_configurable_serverapp):
    app = jp_configurable_serverapp()
    with pytest.raises(TraitError):
        app.root_dir = invalid_root_dir

@pytest.fixture(
    params=[
        ('/',),
        ('first-level',),
        ('first-level', 'second-level')
    ]
)
def valid_root_dir(tmp_path, request):
    path = tmp_path.joinpath(*request.param)
    if not path.exists():
        # Create path in temporary directory
        path.mkdir(parents=True)
    return str(path)

def test_valid_root_dir(valid_root_dir, jp_configurable_serverapp):
    app = jp_configurable_serverapp(root_dir=valid_root_dir)
    root_dir = valid_root_dir
    # If nested path, the last slash should
    # be stripped by the root_dir trait.
    if root_dir != '/':
        root_dir = valid_root_dir.rstrip('/')
    assert app.root_dir == root_dir


def test_generate_config(tmp_path, jp_configurable_serverapp):
    app = jp_configurable_serverapp(config_dir=str(tmp_path))
    app.initialize(['--generate-config', '--allow-root'])
    with pytest.raises(NoStart):
        app.start()
    assert tmp_path.joinpath('jupyter_server_config.py').exists()


def test_server_password(tmp_path, jp_configurable_serverapp):
    password = 'secret'
    with patch.dict(
        'os.environ', {'JUPYTER_CONFIG_DIR': str(tmp_path)}
        ), patch.object(getpass, 'getpass', return_value=password):
        app = JupyterPasswordApp(log_level=logging.ERROR)
        app.initialize([])
        app.start()
        sv = jp_configurable_serverapp()
        sv.load_config_file()
        assert sv.password != ''
        passwd_check(sv.password, password)


def test_list_running_servers(jp_serverapp, jp_web_app):
    servers = list(list_running_servers(jp_serverapp.runtime_dir))
    assert len(servers) >= 1


def tmp_notebook(nbpath):
    nbpath = pathlib.Path(nbpath)
    # Check that the notebook has the correct file extension.
    if nbpath.suffix != '.ipynb':
        raise Exception("File extension for notebook must be .ipynb")
    # If the notebook path has a parent directory, make sure it's created.
    parent = nbpath.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Create a notebook string and write to file.
    nb = nbformat.v4.new_notebook()
    nbtext = nbformat.writes(nb, version=4)
    nbpath.write_text(nbtext)
    return nbpath


@pytest.mark.parametrize(
    "root_dir,file_to_run,file_to_create,expected_output",
    [
        (
            None,
            'notebook.ipynb',
            None,
            'notebook.ipynb'
        ),
        (
            None,
            'path/to/notebook.ipynb',
            None,
            'notebook.ipynb'
        ),
        (
            None,
            '/path/to/notebook.ipynb',
            None,
            'notebook.ipynb'
        ),
        (
            'jp_root_dir',
            '/tmp_path/path/to/notebook.ipynb',
            None,
            SystemExit
        ),
        (
            'tmp_path',
            '/tmp_path/path/to/notebook.ipynb',
            '/tmp_path/path/to/notebook.ipynb',
            'path/to/notebook.ipynb'
        ),
        (
            'jp_root_dir',
            'notebook.ipynb',
            'jp_root_dir/notebook.ipynb',
            'notebook.ipynb'
        ),
        (
            'jp_root_dir',
            '/path/to/notebook.ipynb',
            None,
            SystemExit
        ),
        (
            'jp_root_dir',
            'path/to/notebook.ipynb',
            'jp_root_dir/path/to/notebook.ipynb',
            'path/to/notebook.ipynb'
        ),
    ]
)
def test_resolve_file_to_run_with_root_dir(
    jp_root_dir,
    tmp_path,
    root_dir,
    file_to_run,
    file_to_create,
    expected_output
):
    """Check that the
    """
    # Verify that the Singleton instance is cleared before the test runs.
    ServerApp.clear_instance()
    kwargs = {}
    file_to_run = file_to_run.replace('/tmp_path', str(tmp_path))
    # Root dir can be the jp_root_dir or tmp_path fixtures or None.
    if root_dir:
        root_dir = root_dir.replace('jp_root_dir', str(jp_root_dir))
        root_dir = root_dir.replace('tmp_path', str(tmp_path))
        kwargs["root_dir"] = root_dir

    # If file_to_create is given, create a temporary notebook
    # in that location.
    if file_to_create:
        file_to_create = file_to_create.replace('jp_root_dir', str(jp_root_dir))
        file_to_create = file_to_create.replace('tmp_path', str(tmp_path))
        tmp_notebook(file_to_create)

    kwargs["file_to_run"] = file_to_run

    # Create the notebook in the given location
    serverapp = ServerApp.instance(**kwargs)

    if expected_output is SystemExit:
        with pytest.raises(SystemExit):
            serverapp._resolve_file_to_run_with_root_dir()
    else:
        relpath = serverapp._resolve_file_to_run_with_root_dir()
        assert relpath == expected_output

    # Clear the singleton instance after each run.
    ServerApp.clear_instance()
