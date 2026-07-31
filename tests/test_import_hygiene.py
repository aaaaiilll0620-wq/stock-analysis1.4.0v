"""匯入衛生:`import core.*` 不得觸發網路。

為什麼要有這個測試:`core/data_provider.py` 曾在 class body 寫 `_api = DataLoader()`,
而 `DataLoader.__init__` 內含 `login_by_token()` —— 那一行就是連網。結果是**任何** transitive
匯入 core.data_provider 的東西(core.backtest → core.score_store → build_realbody_scores、
app.py、每一支 lab、每一次 pytest)在 import 當下就打一次 FinMind 登入:
離線/CI 不可重現、多 worker 重複登入、冷啟動慢。

測法:開子行程,先把 socket 全封死,再 import。連網 = 直接炸,不會靜默通過。
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# 封死 socket 後才 import。socket.socket / create_connection 是 requests→urllib3 的唯一出口,
# 蓋掉這兩個就足以讓任何連線嘗試變成明確的 RuntimeError。
_PROBE_HEAD = (
    "import socket\n"
    "def _deny(*a, **k):\n"
    "    raise RuntimeError('NETWORK_DURING_IMPORT')\n"
    "socket.socket = _deny\n"
    "socket.create_connection = _deny\n"
)
_PROBE_TAIL = (
    "from core.data_provider import DataProvider\n"
    "assert DataProvider._api is None, 'import 後 _api 應仍是 None(尚未建 SDK 單例)'\n"
    "print('IMPORT_CLEAN')\n"
)


def _run_probe(import_line: str) -> subprocess.CompletedProcess:
    code = _PROBE_HEAD + import_line + "\n" + _PROBE_TAIL
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.mark.parametrize("module", [
    "core.data_provider",
    "core.backtest",       # → core.data_provider
    "core.score_store",    # → core.backtest → core.data_provider
])
def test_import_does_not_touch_network(module):
    r = _run_probe("import " + module)
    out = r.stdout + r.stderr
    assert "NETWORK_DURING_IMPORT" not in out, f"import {module} 觸發了網路連線:\n{r.stderr}"
    assert "Login success" not in out, f"import {module} 觸發了 FinMind 登入:\n{r.stderr}"
    assert r.returncode == 0, r.stderr
    assert "IMPORT_CLEAN" in r.stdout


def test_get_api_is_lazy_and_cached(monkeypatch):
    """_get_api() 只建一次;不吞錯(SDK 建不起來要照樣往上拋,不得降級成 None)。"""
    from core.data_provider import DataProvider

    calls = []

    class _FakeLoader:
        def __init__(self):
            calls.append(1)

    import FinMind.data as fmd
    monkeypatch.setattr(fmd, "DataLoader", _FakeLoader)
    monkeypatch.setattr(DataProvider, "_api", None)

    a = DataProvider._get_api()
    b = DataProvider._get_api()
    assert a is b
    assert len(calls) == 1, "SDK 單例被重複建立"


def test_get_api_does_not_swallow_sdk_failure(monkeypatch):
    from core.data_provider import DataProvider

    class _Boom:
        def __init__(self):
            raise RuntimeError("SDK 壞了")

    import FinMind.data as fmd
    monkeypatch.setattr(fmd, "DataLoader", _Boom)
    monkeypatch.setattr(DataProvider, "_api", None)

    with pytest.raises(RuntimeError, match="SDK 壞了"):
        DataProvider._get_api()


# ==============================================================================
# _ensure_login() 的三種錯誤語意(Codex 第一輪審查 §三-1 的決策,鎖在測試裡)
#
#   | 錯誤                    | strict=False(線上 App 容錯) | strict=True(研究建置) |
#   | _get_api() 建構失敗       | raise                      | raise                |
#   | 缺 token / 登入失敗       | 降級匿名                     | raise                |
#   | 快取代理安裝失敗           | 降級直連                     | raise                |
# ==============================================================================
class _FakeLoader:
    def __init__(self, fail_login=False):
        self.fail_login = fail_login
        self.logged = False

    def login_by_token(self, api_token=None):
        if self.fail_login:
            raise RuntimeError("token 被拒")
        self.logged = True


@pytest.fixture
def fresh_provider(monkeypatch):
    """每個測試都拿到乾淨的 class 狀態(_api / _logged_in 是 class 級單例)。"""
    from core.data_provider import DataProvider
    monkeypatch.setattr(DataProvider, "_api", None)
    monkeypatch.setattr(DataProvider, "_logged_in", False)
    return DataProvider


def test_ensure_login_construction_failure_always_raises(fresh_provider, monkeypatch):
    """建構失敗屬於環境壞掉,**兩種模式都不得**被吞成匿名模式。"""
    class _Boom:
        def __init__(self):
            raise RuntimeError("SDK 裝不起來")

    import FinMind.data as fmd
    monkeypatch.setattr(fmd, "DataLoader", _Boom)
    monkeypatch.setenv("FINMIND_TOKEN", "x")
    for strict in (False, True):
        fresh_provider._api = None
        fresh_provider._logged_in = False
        with pytest.raises(RuntimeError, match="SDK 裝不起來"):
            fresh_provider._ensure_login(strict=strict)


def test_ensure_login_token_failure_degrades_when_not_strict(fresh_provider, monkeypatch):
    """線上 App 的容錯:登入失敗 → 匿名模式,不中斷。"""
    monkeypatch.setattr(fresh_provider, "_api", _FakeLoader(fail_login=True))
    monkeypatch.setenv("FINMIND_TOKEN", "bad-token")
    fresh_provider._ensure_login(strict=False)          # 不 raise
    assert fresh_provider._logged_in is False           # 沒登入成功,但流程繼續


def test_ensure_login_token_failure_raises_when_strict(fresh_provider, monkeypatch):
    """研究建置:登入失敗不得靜默降級成匿名額度。"""
    monkeypatch.setattr(fresh_provider, "_api", _FakeLoader(fail_login=True))
    monkeypatch.setenv("FINMIND_TOKEN", "bad-token")
    with pytest.raises(RuntimeError, match="strict=True"):
        fresh_provider._ensure_login(strict=True)


def test_ensure_login_missing_token_semantics(fresh_provider, monkeypatch):
    monkeypatch.setattr(fresh_provider, "_api", _FakeLoader())
    monkeypatch.delenv("FINMIND_TOKEN", raising=False)
    monkeypatch.setattr("core.data_provider.load_dotenv", lambda *a, **k: None)  # 別讓 .env 補回 token
    with pytest.raises(RuntimeError, match="FINMIND_TOKEN"):
        fresh_provider._ensure_login(strict=True)
    fresh_provider._logged_in = False
    fresh_provider._ensure_login(strict=False)          # 非 strict:只警告


def test_ensure_login_cache_proxy_failure_semantics(fresh_provider, monkeypatch):
    """快取代理安裝失敗:App 降級直連;研究建置 raise。"""
    import core.data_cache as dc
    monkeypatch.setenv("FINMIND_TOKEN", "ok")

    def _boom(_inner):
        raise RuntimeError("代理裝不起來")

    monkeypatch.setattr(dc, "install", _boom)
    monkeypatch.setattr(dc, "CACHE_ENABLED", True)

    monkeypatch.setattr(fresh_provider, "_api", _FakeLoader())
    fresh_provider._ensure_login(strict=False)          # 不 raise
    fresh_provider._logged_in = False
    monkeypatch.setattr(fresh_provider, "_api", _FakeLoader())
    with pytest.raises(RuntimeError, match="strict=True"):
        fresh_provider._ensure_login(strict=True)


# ==============================================================================
# 產業別對照表的 fail-closed 閘門
# ==============================================================================
def test_industry_map_strict_rejects_empty_and_finless(monkeypatch):
    from core.data_provider import DataProvider
    monkeypatch.setattr(DataProvider, "_industry_map", {})
    with pytest.raises(RuntimeError, match="產業別對照表不可用"):
        DataProvider._ensure_industry_map(strict=True)
    assert DataProvider._ensure_industry_map(strict=False) == {}   # App 端照舊回空表

    # 有 3000 檔但一檔金融股都沒有 —— 筆數正常、豁免全失效,必須擋
    monkeypatch.setattr(DataProvider, "_industry_map", {str(i): "電子工業" for i in range(3000)})
    with pytest.raises(RuntimeError, match="金融股 0 檔"):
        DataProvider._ensure_industry_map(strict=True)

    monkeypatch.setattr(DataProvider, "_industry_map", {"2330": "半導體業", "2881": "金融保險業"})
    assert DataProvider._ensure_industry_map(strict=True)["2881"] == "金融保險業"


# ==============================================================================
# Streamlit 的 _saved_api 換入/還原(Codex 第一輪審查 §三-2)
# 複製 app.py:267-273 的協定;lazy 化之後 _saved_api 可能是 None,行為必須仍然正確。
# ==============================================================================
def test_app_token_swap_restore_contract(fresh_provider, monkeypatch):
    import FinMind.data as fmd
    built = []

    class _Rebuilt:
        def __init__(self):
            built.append(self)

    monkeypatch.setattr(fmd, "DataLoader", _Rebuilt)

    # --- app.py:268-273 的協定,逐行複製 ---
    loader_a = _FakeLoader()
    _saved_api, _saved_logged = fresh_provider._api, fresh_provider._logged_in   # ← 這裡是 None/False
    assert _saved_api is None, "lazy 化後,尚未使用過時 _api 就是 None(本測試要涵蓋的正是這個情境)"
    fresh_provider._api, fresh_provider._logged_in = loader_a, True
    try:
        assert fresh_provider._get_api() is loader_a          # 分析期間用的是該 token 的 loader
    finally:
        fresh_provider._api, fresh_provider._logged_in = _saved_api, _saved_logged

    # 還原成 None 之後,下一次取用必須乾淨重建,而且不能是上一位訪客的 loader
    assert fresh_provider._api is None
    rebuilt = fresh_provider._get_api()
    assert rebuilt is not loader_a, "還原後仍指向前一個 token 的 loader = token 隔離破功"
    assert isinstance(rebuilt, _Rebuilt) and len(built) == 1


def test_app_token_swap_isolates_two_users(fresh_provider):
    """兩位訪客各自的 loader 不得互相汙染(逐一進出鎖,模擬 _api_lock 內的序列化)。"""
    seen = []
    for loader in (_FakeLoader(), _FakeLoader()):
        saved_api, saved_logged = fresh_provider._api, fresh_provider._logged_in
        fresh_provider._api, fresh_provider._logged_in = loader, True
        seen.append(fresh_provider._get_api())
        fresh_provider._api, fresh_provider._logged_in = saved_api, saved_logged
    assert seen[0] is not seen[1]
    assert fresh_provider._api is None and fresh_provider._logged_in is False
