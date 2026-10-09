import importlib.util
import json
from pathlib import Path

import httpx

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replay_script_prints_status_and_excerpt(tmp_path, capsys):
    request = tmp_path / "req.json"
    request.write_text(json.dumps({"method": "GET", "path": "/rest/basket/2",
                                   "expected_blocked_status": 401}))
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(401, text="nope")

    code = _load("replay").main(["http://127.0.0.1:3001", str(request)],
                                client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert code == 0 and seen == ["http://127.0.0.1:3001/rest/basket/2"]
    assert json.loads(capsys.readouterr().out) == {"status": 401, "excerpt": "nope"}


def test_regression_script_exits_nonzero_on_failures(capsys):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    code = _load("regression_smoke").main(["http://127.0.0.1:3001"], client=client)
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["passed"] == 0 and out["failed"] == 6
