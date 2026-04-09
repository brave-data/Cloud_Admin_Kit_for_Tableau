"""
main.py
Cloud Admin Kit for Tableau — FastAPI ローカルサーバー

起動方法:
    python main.py
    または
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# ---------------------------------------------------------------------------
# 起動時の必須環境変数チェック
# ---------------------------------------------------------------------------
_REQUIRED_ENV = {
    "TABLEAU_SERVER_URL":  "Tableau Cloud のURL (例: https://10ay.online.tableau.com)",
    "TABLEAU_TOKEN_NAME":  "Personal Access Token の名前",
    "TABLEAU_TOKEN_SECRET":"Personal Access Token のシークレット",
}

def _check_env() -> None:
    """必須変数が未設定の場合、分かりやすいエラーメッセージを表示して終了する。"""
    missing = [
        (key, desc)
        for key, desc in _REQUIRED_ENV.items()
        if not os.getenv(key)
    ]
    if missing:
        print("\n" + "=" * 55)
        print("  ❌  .env の設定が不足しています")
        print("=" * 55)
        for key, desc in missing:
            print(f"  未設定: {key}")
            print(f"         ({desc})")
        print("\n  .env.example をコピーして .env を作成してください:")
        print("    cp .env.example .env")
        print("  詳細: SETUP.md / SETUP_ja.md")
        print("=" * 55 + "\n")
        raise SystemExit(1)

_check_env()

# ---------------------------------------------------------------------------
# インメモリキャッシュ
# ---------------------------------------------------------------------------
_cache: dict[str, Any] = {
    "data":           None,   # fetch_all() の戻り値
    "status":         "idle", # idle | loading | ok | error
    "error":          None,
    "fetched_at":     None,
    "fetch_warnings": [],     # 部分的な取得失敗の警告リスト
}
_lock = threading.Lock()

# ワークブックごとの計算フィールド解析キャッシュ（on-demand）
_field_cache: dict[str, Any] = {}
# Prep フローごとの接続情報キャッシュ（on-demand）
_flow_conn_cache: dict[str, Any] = {}


def _do_fetch():
    """バックグラウンドでデータ取得"""
    from tableau_client import fetch_all

    with _lock:
        _cache["status"] = "loading"
        _cache["error"]  = None

    try:
        result = fetch_all()
        with _lock:
            _cache["data"]           = result
            _cache["status"]         = "ok"
            _cache["fetched_at"]     = result["fetched_at"]
            _cache["fetch_warnings"] = result.get("fetch_warnings", [])
    except Exception as exc:
        with _lock:
            _cache["status"] = "error"
            _cache["error"]  = str(exc)
        raise


# ---------------------------------------------------------------------------
# アプリ起動
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時にバックグラウンドフェッチ開始
    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()
    yield


app = FastAPI(
    title="Cloud Admin Kit for Tableau",
    description="Tableau Cloud の管理情報をブラウザで確認・更新するローカルツール",
    version="1.5.2",
    lifespan=lifespan,
)

# static ディレクトリが存在する場合のみマウント
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ---------------------------------------------------------------------------
# HTML ルート
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    html_path = _static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html が見つかりません</h1>", status_code=500)


# ---------------------------------------------------------------------------
# API エンドポイント
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    """接続状態とキャッシュの状態を返す"""
    with _lock:
        return {
            "status":          _cache["status"],
            "error":           _cache["error"],
            "fetched_at":      _cache["fetched_at"],
            "version":         app.version,
            "fetch_warnings":  _cache["fetch_warnings"],
        }


@app.get("/api/summary")
async def get_summary():
    return _require_data()["summary"]


@app.get("/api/workbooks")
async def get_workbooks():
    return _require_data()["workbooks"]


@app.get("/api/datasources")
async def get_datasources():
    return _require_data()["datasources"]


@app.get("/api/views")
async def get_views():
    return _require_data()["views"]


@app.get("/api/users")
async def get_users():
    return _require_data()["users"]


@app.get("/api/schedules")
async def get_schedules():
    return _require_data()["schedules"]


@app.get("/api/flows")
async def get_flows():
    return _require_data()["flows"]


@app.get("/api/flows/{flow_id}/connections")
async def get_flow_connections(flow_id: str):
    """Prep フローの接続情報を返す（結果はキャッシュ）"""
    if flow_id in _flow_conn_cache:
        return _flow_conn_cache[flow_id]

    from tableau_client import fetch_flow_connections
    try:
        result = await asyncio.to_thread(fetch_flow_connections, flow_id)
        _flow_conn_cache[flow_id] = result
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/refresh")
async def trigger_refresh():
    """Tableau Cloud から最新情報を再取得する"""
    with _lock:
        if _cache["status"] == "loading":
            return {"message": "すでに取得中です。しばらくお待ちください。"}

    # ワークブック・フローの内容が変わる可能性があるため、各キャッシュをクリア
    _field_cache.clear()
    _flow_conn_cache.clear()

    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()
    return {"message": "データ取得を開始しました。数秒後にページを更新してください。"}


@app.get("/api/ktw-fields")
async def get_ktw_fields():
    """タグ'KTW'付きワークブック（最大10件）の計算フィールドを返す"""
    data = _require_data()
    ktw_wbs = [wb for wb in data["workbooks"] if "KTW" in (wb.get("tags") or [])][:10]

    from tableau_client import fetch_workbook_fields

    async def scan_one(wb):
        try:
            result = await asyncio.to_thread(fetch_workbook_fields, wb["id"])
            return {
                "id":   wb["id"],
                "name": wb["name"],
                "fields": [
                    {"datasource": f["datasource"], "field": f["field"], "formula": f["formula"]}
                    for f in result["fields"]
                ],
            }
        except Exception as e:
            return {"id": wb["id"], "name": wb["name"], "fields": [], "error": str(e)}

    results = await asyncio.gather(*[scan_one(wb) for wb in ktw_wbs])
    return list(results)


@app.get("/api/workbooks/{workbook_id}/fields")
async def get_workbook_fields(workbook_id: str):
    """ワークブックをダウンロードして計算フィールドの依存関係を返す（結果はキャッシュ）"""
    if workbook_id in _field_cache:
        return _field_cache[workbook_id]

    from tableau_client import fetch_workbook_fields
    try:
        result = await asyncio.to_thread(fetch_workbook_fields, workbook_id)
        _field_cache[workbook_id] = result
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _require_data() -> dict[str, Any]:
    """キャッシュの状態を確認し、データを返す。未準備の場合は HTTPException を送出する。"""
    with _lock:
        status = _cache["status"]
        error  = _cache["error"]
        data   = _cache["data"]

    if status == "loading":
        raise HTTPException(status_code=503, detail="データ取得中です。しばらくお待ちください。")
    if status == "error":
        raise HTTPException(status_code=503, detail=f"Tableau Cloud への接続に失敗しました: {error}")
    if data is None:
        raise HTTPException(status_code=503, detail="データが未取得です。/api/refresh を呼んでください。")
    return data


# ---------------------------------------------------------------------------
# 直接実行
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    # デフォルトは 127.0.0.1（ローカルのみ）。
    # LAN 公開が必要な場合のみ HOST=0.0.0.0 を .env に設定してください。
    # ※ 認証なしのため、0.0.0.0 での公開は同一ネットワーク全体に管理情報が見えます。
    host = os.getenv("HOST", "127.0.0.1")
    print(f"\n{'='*55}")
    print("  Cloud Admin Kit for Tableau")
    print(f"{'='*55}")
    print(f"  ブラウザで開く → http://localhost:{port}")
    print(f"  API ドキュメント → http://localhost:{port}/docs")
    if host != "127.0.0.1":
        print(f"  ⚠️  HOST={host} — LAN公開中。認証なしでアクセス可能です。")
    print(f"  停止: Ctrl+C")
    print(f"{'='*55}\n")
    uvicorn.run("main:app", host=host, port=port, reload=False)
