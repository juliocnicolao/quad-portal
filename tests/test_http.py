"""Testes do helper utils/http — retry, backoff, fallback suave."""
from unittest.mock import patch, MagicMock
import requests
from utils.http import get_json, get_text, request


def _mock_response(status=200, json_data=None, text=""):
    r = MagicMock(spec=requests.Response)
    r.status_code = status
    r.json.return_value = json_data
    r.text = text
    r.content = text.encode()
    r.raise_for_status = MagicMock()
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return r


def test_get_json_sucesso():
    with patch("utils.http.requests.request",
               return_value=_mock_response(200, {"ok": True})):
        assert get_json("http://x") == {"ok": True}


def test_get_json_500_faz_retry_e_retorna_none():
    call_count = {"n": 0}
    def side(*a, **kw):
        call_count["n"] += 1
        return _mock_response(500)
    with patch("utils.http.requests.request", side_effect=side), \
         patch("utils.http.time.sleep"):
        assert get_json("http://x", retries=2) is None
    assert call_count["n"] == 3  # 1 tentativa + 2 retries


def test_get_json_429_retry():
    seq = [_mock_response(429), _mock_response(200, {"ok": 1})]
    with patch("utils.http.requests.request", side_effect=seq), \
         patch("utils.http.time.sleep"):
        assert get_json("http://x", retries=1) == {"ok": 1}


def test_get_text_network_error():
    with patch("utils.http.requests.request",
               side_effect=requests.ConnectionError("boom")), \
         patch("utils.http.time.sleep"):
        assert get_text("http://x", retries=1) is None


def test_user_agent_sempre_presente():
    captured = {}
    def side(method, url, **kw):
        captured["headers"] = kw.get("headers")
        return _mock_response(200, {})
    with patch("utils.http.requests.request", side_effect=side):
        request("GET", "http://x")
    assert "User-Agent" in captured["headers"]
