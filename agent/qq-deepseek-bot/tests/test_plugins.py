import json
from qq_deepseek.tools.plugins import load_plugins


def test_owner_plugin_is_not_imported_for_other_users(tmp_path):
    path = tmp_path / 'plugins.json'
    path.write_text(json.dumps({'plugins': [{
        'type': 'python', 'factory': 'must_not_be_imported:tools', 'enabled': True
    }]}))
    assert load_plugins(path, owner=False) == ([], [])


def test_public_python_tools_load_from_factory(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    def tool():
        return 'hello'
    monkeypatch.setitem(sys.modules, 'example_qq_plugin', SimpleNamespace(tools=lambda: [tool]))
    path = tmp_path / 'plugins.json'
    path.write_text(json.dumps({'plugins': [{
        'type': 'python', 'factory': 'example_qq_plugin:tools',
        'scope': 'public', 'enabled': True
    }]}))
    tools, toolsets = load_plugins(path, owner=False)
    assert tools[0]() == 'hello'
    assert toolsets == []
