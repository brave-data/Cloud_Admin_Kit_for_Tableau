"""
tableau_client.py
Tableau Cloud REST API クライアント (tableauserverclient ラッパー)
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable

import defusedxml.ElementTree as DET
import tableauserverclient as TSC
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# メインデータフェッチの最大並列数（Tableau Cloud の同時接続制限に配慮）
_MAIN_WORKERS = 8
# populate_connections の最大並列数
_CONN_WORKERS = 10


# ---------------------------------------------------------------------------
# エラー分類ヘルパー
# ---------------------------------------------------------------------------

def _classify_error(exc: Exception, resource: str) -> dict[str, str]:
    """例外を分類して警告辞書を返す（fetch_warnings リスト用）"""
    msg = str(exc)
    if "403" in msg:
        error_type = "permission"
    elif "429" in msg:
        error_type = "rate_limit"
    else:
        error_type = "general"
    return {"resource": resource, "type": error_type, "message": msg[:300]}


# ---------------------------------------------------------------------------
# 接続ヘルパー
# ---------------------------------------------------------------------------

def _make_server() -> tuple[TSC.Server, TSC.PersonalAccessTokenAuth]:
    url    = os.environ["TABLEAU_SERVER_URL"].rstrip("/")
    name   = os.environ["TABLEAU_TOKEN_NAME"]
    secret = os.environ["TABLEAU_TOKEN_SECRET"]
    site   = os.environ.get("TABLEAU_SITE_NAME", "")

    auth   = TSC.PersonalAccessTokenAuth(name, secret, site_id=site)
    server = TSC.Server(url, use_server_version=True)

    # REQUESTS_CA_BUNDLE にCA証明書パスが指定されていればそれを使用（社内プロキシ対応）
    # 未指定の場合は True（デフォルトのCA束で検証）
    ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE", "").strip()
    server.add_http_options({"verify": ca_bundle if ca_bundle else True})
    return server, auth


def _ensure_utc(dt: datetime) -> datetime:
    """naive datetime を UTC aware に変換する"""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _fmt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return _ensure_utc(dt).isoformat()


def _days_ago(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - _ensure_utc(dt)).days


def _tableau_url(server_url: str, site_name: str, resource_type: str, resource_id: str) -> str:
    """Tableau Cloud の Web UI URL を構築する"""
    base = server_url.rstrip("/")
    if site_name:
        return f"{base}/#/site/{site_name}/{resource_type}/{resource_id}"
    return f"{base}/#/{resource_type}/{resource_id}"


# ---------------------------------------------------------------------------
# 並列フェッチ用ヘルパー
# ---------------------------------------------------------------------------

def _chunk_list(lst: list, n: int) -> list[list]:
    """リストを最大 n 個のチャンクに均等分割する"""
    if not lst:
        return []
    size = max(1, -(-len(lst) // n))  # ceiling division
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def _fetch_views_with_usage(s: TSC.Server) -> list:
    """usage=True でビューを全件取得する"""
    views: list = []
    req = TSC.RequestOptions(pagesize=100)
    while True:
        page, pagination = s.views.get(req_options=req, usage=True)
        views.extend(page)
        if len(views) >= pagination.total_available:
            break
        req.pagenumber += 1
    return views


def _fetch_flow_runs(s: TSC.Server) -> list:
    """フロー実行履歴（最新1ページ分）を取得する"""
    req = TSC.RequestOptions(pagesize=100)
    result = s.flow_runs.get(req)
    return result[0] if isinstance(result, tuple) else result


def _populate_wb_connections_batch(wb_list: list) -> tuple[dict[str, list], list]:
    """ワークブックのバッチに対して接続情報を取得する（新規接続を使用）"""
    s, a = _make_server()
    conn_dict: dict[str, list] = {}
    warnings: list = []
    try:
        with s.auth.sign_in(a):
            for wb in wb_list:
                try:
                    s.workbooks.populate_connections(wb)
                    conn_dict[wb.id] = [
                        getattr(c, "datasource_id", None)
                        for c in (wb.connections or [])
                        if getattr(c, "datasource_id", None)
                    ]
                except Exception:
                    conn_dict[wb.id] = []
    except Exception as exc:
        warnings.append(_classify_error(exc, "ワークブック接続情報"))
    return conn_dict, warnings


def _populate_flow_connections_batch(flow_list: list) -> tuple[dict[str, list], list]:
    """Prepフローのバッチに対して接続情報を取得する（新規接続を使用）"""
    s, a = _make_server()
    conn_dict: dict[str, list] = {}
    warnings: list = []
    try:
        with s.auth.sign_in(a):
            for fl in flow_list:
                try:
                    s.flows.populate_connections(fl)
                    conn_dict[fl.id] = [
                        getattr(c, "datasource_id", None)
                        for c in (fl.connections or [])
                        if getattr(c, "datasource_id", None)
                    ]
                except Exception:
                    conn_dict[fl.id] = []
    except Exception as exc:
        warnings.append(_classify_error(exc, "Prepフロー接続情報"))
    return conn_dict, warnings


# ---------------------------------------------------------------------------
# メインフェッチ関数
# ---------------------------------------------------------------------------

def fetch_all() -> dict[str, Any]:
    """Tableau Cloud から全管理情報を取得して辞書で返す"""
    fetch_warnings: list[dict[str, str]] = []
    _server_url = os.environ.get("TABLEAU_SERVER_URL", "").rstrip("/")
    _site_name  = os.environ.get("TABLEAU_SITE_NAME", "")

    # ── Phase 1: 独立したリソースを並列取得 ──────────────────────────
    _fetch_tasks: dict[str, Callable] = {
        "users":         lambda s: list(TSC.Pager(s.users)),
        "projects":      lambda s: list(TSC.Pager(s.projects)),
        "workbooks":     lambda s: list(TSC.Pager(s.workbooks)),
        "datasources":   lambda s: list(TSC.Pager(s.datasources)),
        "flows":         lambda s: list(TSC.Pager(s.flows)),
        "views":         _fetch_views_with_usage,
        "jobs":          lambda s: list(TSC.Pager(s.jobs, request_opts=TSC.RequestOptions(pagesize=50)))[:200],
        "tasks":         lambda s: list(TSC.Pager(s.tasks)),
        "subscriptions": lambda s: list(TSC.Pager(s.subscriptions)),
        "sched_map":     lambda s: {_s.id: _s for _s in TSC.Pager(s.schedules)},
        "flow_runs":     _fetch_flow_runs,
    }
    raw: dict[str, Any] = {k: [] for k in _fetch_tasks}
    raw["sched_map"] = {}

    def _run(fn: Callable) -> Any:
        s, a = _make_server()
        with s.auth.sign_in(a):
            return fn(s)

    with ThreadPoolExecutor(max_workers=_MAIN_WORKERS) as executor:
        future_map = {executor.submit(_run, fn): key for key, fn in _fetch_tasks.items()}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                raw[key] = future.result()
            except Exception as exc:
                logger.warning("%s の取得に失敗しました: %s", key, exc)
                fetch_warnings.append(_classify_error(exc, key))

    users_raw         = raw["users"]
    projects_raw      = raw["projects"]
    workbooks_raw     = raw["workbooks"]
    datasources_raw   = raw["datasources"]
    flows_raw         = raw["flows"]
    views_raw         = raw["views"]
    jobs_raw          = raw["jobs"]
    tasks_raw         = raw["tasks"]
    subscriptions_raw = raw["subscriptions"]
    _sched_map        = raw["sched_map"]
    _flow_runs_raw    = raw["flow_runs"]

    # ── Phase 2: マップ構築とデータ変換 ──────────────────────────────
    user_map    = {u.id: (u.fullname or u.name) for u in users_raw}
    project_map = {p.id: p.name for p in projects_raw}

    # ── ユーザー ────────────────────────────────────────
    # 権限不足（Site Administrator 未満）の場合は空リストで続行し、オーナー表示が "Unknown" になる。
    users = []
    for u in users_raw:
        users.append({
            "id":              u.id,
            "name":            u.fullname or u.name,
            "email":           u.email or "",
            "site_role":       u.site_role or "",
            "last_login":      _fmt(u.last_login),
            "days_since_login": _days_ago(u.last_login),
            "url":             _tableau_url(_server_url, _site_name, "users", u.id),
        })

    # ── プロジェクト ─────────────────────────────────────
    projects = []
    for p in projects_raw:
        projects.append({
            "id":          p.id,
            "name":        p.name,
            "description": p.description or "",
            "parent_id":   p.parent_id,
            "parent_name": project_map.get(p.parent_id, ""),
        })

    # ── ワークブック ─────────────────────────────────────
    workbooks = []
    for wb in workbooks_raw:
        size_mb = round((getattr(wb, "size", None) or 0) / 1024 / 1024, 2)
        workbooks.append({
            "id":           wb.id,
            "name":         wb.name,
            "project":      wb.project_name or "",
            "owner":        user_map.get(wb.owner_id, "Unknown"),
            "created_at":   _fmt(wb.created_at),
            "updated_at":   _fmt(wb.updated_at),
            "days_stale":   _days_ago(wb.updated_at),
            "size_mb":      size_mb,
            "tags":         sorted(wb.tags) if wb.tags else [],
            "url":          wb.webpage_url or "",
            "description":  wb.description or "",
        })

    # ── データソース ─────────────────────────────────────
    datasources = []
    for ds in datasources_raw:
        datasources.append({
            "id":           ds.id,
            "name":         ds.name,
            "project":      ds.project_name or "",
            "owner":        user_map.get(ds.owner_id, "Unknown"),
            "type":         ds.datasource_type or "",
            "certified":    bool(getattr(ds, "certified", False)),
            "cert_note":    ds.certification_note or "",
            "created_at":   _fmt(ds.created_at),
            "updated_at":   _fmt(ds.updated_at),
            "days_stale":   _days_ago(ds.updated_at),
            "description":  ds.description or "",
            "url":          _tableau_url(_server_url, _site_name, "datasources", ds.id),
        })

    # ── ビュー (使用状況付き) ───────────────────────────
    views = []
    for v in views_raw:
        # TSC は last_viewed_at を直接公開しないため、利用可能な属性を試みる
        last_viewed = (getattr(v, "recently_viewed_at", None)
                       or getattr(v, "last_viewed_at", None))
        days_since_viewed = (_days_ago(last_viewed)
                             if isinstance(last_viewed, datetime)
                             else _days_ago(v.updated_at))
        _view_content_url = getattr(v, "content_url", "") or ""
        views.append({
            "id":               v.id,
            "name":             v.name,
            "workbook_id":      v.workbook_id,
            "owner":            user_map.get(v.owner_id, "Unknown"),
            "total_views":      v.total_views or 0,
            "created_at":       _fmt(v.created_at),
            "updated_at":       _fmt(v.updated_at),
            "days_stale":       _days_ago(v.updated_at),
            "last_viewed_at":   _fmt(last_viewed) if isinstance(last_viewed, datetime) else None,
            "days_since_viewed": days_since_viewed,
            "url":              _tableau_url(_server_url, _site_name, "views", _view_content_url) if _view_content_url else "",
        })

    # ワークブック名をビューに付与
    wb_map = {wb["id"]: wb["name"] for wb in workbooks}
    for v in views:
        v["workbook_name"] = wb_map.get(v["workbook_id"], "")

    # ── ジョブ (サマリ計算用・直近 200 件) ──────────────
    jobs = []
    for j in jobs_raw:
        jobs.append({
            "id":           getattr(j, "id",           getattr(j, "_id",           None)),
            "type":         getattr(j, "type",         getattr(j, "_type",         "")) or "",
            "status":       getattr(j, "status",       getattr(j, "_status",       "")) or "",
            "created_at":   _fmt(getattr(j, "created_at",   getattr(j, "_created_at",   None))),
            "started_at":   _fmt(getattr(j, "started_at",   getattr(j, "_started_at",   None))),
            "completed_at": _fmt(getattr(j, "ended_at",     getattr(j, "_ended_at",     None))),
            "notes":        (getattr(j, "notes", "") or "")[:300],
        })

    # ── スケジュール（抽出更新 + サブスクリプション）──────────────
    def _extract_schedule_info(obj: Any) -> tuple[str, str | None]:
        """schedule 属性または schedule_id から (frequency, next_run_at) を返す"""
        sched = getattr(obj, "schedule", None)
        if sched is None:
            sched_id = getattr(obj, "schedule_id", None)
            if sched_id:
                sched = _sched_map.get(sched_id)
        if sched is None:
            return "", None
        frequency = getattr(sched, "frequency", "") or ""
        next_raw  = getattr(sched, "next_run_at", None)
        if isinstance(next_raw, datetime):
            return frequency, _fmt(next_raw)
        return frequency, (str(next_raw) if next_raw else None)

    schedules: list[dict] = []

    # ID → オブジェクト の辞書を作成してタスク解決を O(1) に
    ds_id_map = {ds.id: ds for ds in datasources_raw}
    wb_id_map = {wb.id: wb for wb in workbooks_raw}

    # 1) 抽出更新タスク
    for task in tasks_raw:
        content_name = ""
        content_type = ""
        project_name = ""
        owner_name   = ""

        ds_ref = getattr(task, "datasource", None)
        wb_ref = getattr(task, "workbook",   None)

        if ds_ref:
            ds_id = getattr(ds_ref, "id", None)
            content_name = getattr(ds_ref, "name", "") or ""
            content_type = "datasource"
            if ds_id and ds_id in ds_id_map:
                project_name = ds_id_map[ds_id].project_name or ""
                owner_name   = user_map.get(ds_id_map[ds_id].owner_id, "Unknown")
        elif wb_ref:
            wb_id = getattr(wb_ref, "id", None)
            content_name = getattr(wb_ref, "name", "") or ""
            content_type = "workbook"
            if wb_id and wb_id in wb_id_map:
                project_name = wb_id_map[wb_id].project_name or ""
                owner_name   = user_map.get(wb_id_map[wb_id].owner_id, "Unknown")

        frequency, next_run_at = _extract_schedule_info(task)
        schedules.append({
            "id":            task.id,
            "schedule_kind": "extract",
            "content_name":  content_name,
            "content_type":  content_type,
            "project":       project_name,
            "owner":         owner_name,
            "refresh_type":  getattr(task, "extract_refresh_type", "") or "",
            "frequency":     frequency,
            "next_run_at":   next_run_at,
        })

    # 2) サブスクリプション
    for sub in subscriptions_raw:
        content      = getattr(sub, "content", None)
        content_name = getattr(content, "name", "") or "" if content else ""
        content_type = (getattr(content, "type", "") or "").lower()
        user_obj     = getattr(sub, "user", None)
        owner_name   = ""
        if user_obj:
            uid = getattr(user_obj, "id", None)
            owner_name = user_map.get(uid, getattr(user_obj, "name", "") or "")
        frequency, next_run_at = _extract_schedule_info(sub)
        schedules.append({
            "id":            sub.id,
            "schedule_kind": "subscription",
            "content_name":  content_name,
            "content_type":  content_type,
            "project":       "",
            "owner":         owner_name,
            "refresh_type":  "",
            "frequency":     frequency,
            "next_run_at":   next_run_at,
            "subject":       getattr(sub, "subject", "") or "",
        })

    # ── Prep フロー ──────────────────────────────────────
    flow_run_map: dict[str, Any] = {}
    for run in _flow_runs_raw:
        fid       = getattr(run, "flow_id", None)
        completed = getattr(run, "completed_at", getattr(run, "ended_at", None))
        if fid and completed is not None:
            existing = flow_run_map.get(fid)
            if existing is None or _ensure_utc(completed) > _ensure_utc(existing):
                flow_run_map[fid] = completed

    flows = []
    for fl in flows_raw:
        last_run = flow_run_map.get(fl.id)
        flows.append({
            "id":            fl.id,
            "name":          fl.name,
            "project":       fl.project_name or "",
            "owner":         user_map.get(fl.owner_id, "Unknown"),
            "created_at":    _fmt(fl.created_at),
            "updated_at":    _fmt(fl.updated_at),
            "days_stale":    _days_ago(fl.updated_at),
            "last_run_at":   _fmt(last_run),
            "days_since_run": _days_ago(last_run),
            "description":   fl.description or "",
            "tags":          sorted(fl.tags) if fl.tags else [],
            "url":           _tableau_url(_server_url, _site_name, "flows", fl.id),
        })

    # ── Phase 3: populate_connections を並列実行 ──────────────────────
    # WB と Prepフロー の接続情報をスレッドプールで並列取得
    wb_conn_map:   dict[str, list] = {}
    flow_conn_map: dict[str, list] = {}

    with ThreadPoolExecutor(max_workers=_CONN_WORKERS) as executor:
        wb_futures = {
            executor.submit(_populate_wb_connections_batch, chunk): "wb"
            for chunk in _chunk_list(workbooks_raw, _CONN_WORKERS)
        }
        flow_futures = {
            executor.submit(_populate_flow_connections_batch, chunk): "flow"
            for chunk in _chunk_list(flows_raw, _CONN_WORKERS)
        }
        all_conn_futures = {**wb_futures, **flow_futures}
        for future in as_completed(all_conn_futures):
            kind = all_conn_futures[future]
            conn_dict, warns = future.result()
            fetch_warnings.extend(warns)
            if kind == "wb":
                wb_conn_map.update(conn_dict)
            else:
                flow_conn_map.update(conn_dict)

    # ── Phase 4: Ghost DS フラグ付与 ─────────────────────────────────
    ghost_ds_ids:   set[str]      = {ds.id for ds in datasources_raw}
    wb_ref_count:   dict[str, int] = {}
    flow_ref_count: dict[str, int] = {}

    for ds_ids in wb_conn_map.values():
        for ds_id in ds_ids:
            ghost_ds_ids.discard(ds_id)
            wb_ref_count[ds_id] = wb_ref_count.get(ds_id, 0) + 1

    for ds_ids in flow_conn_map.values():
        for ds_id in ds_ids:
            ghost_ds_ids.discard(ds_id)
            flow_ref_count[ds_id] = flow_ref_count.get(ds_id, 0) + 1

    for ds in datasources:
        ds["wb_ref_count"]    = wb_ref_count.get(ds["id"], 0)
        ds["flow_ref_count"]  = flow_ref_count.get(ds["id"], 0)
        ds["reference_count"] = ds["wb_ref_count"] + ds["flow_ref_count"]
        ds["is_ghost"]        = ds["reference_count"] == 0

    ghost_datasources = [ds for ds in datasources if ds["is_ghost"]]

    # ── サマリ ───────────────────────────────────────────
    role_counts: dict[str, int] = {}
    for u in users:
        role_counts[u["site_role"]] = role_counts.get(u["site_role"], 0) + 1

    stale_wb  = [w for w in workbooks if (w["days_stale"] or 0) > 180]
    stale_ds  = [d for d in datasources if (d["days_stale"] or 0) > 180]
    top_views = sorted(views, key=lambda v: v["total_views"], reverse=True)[:10]

    active_wb_ids = {v["workbook_id"] for v in views if v["total_views"] > 0}
    unused_wb     = [w for w in workbooks if w["id"] not in active_wb_ids]

    inactive_users = [u for u in users
                      if u["days_since_login"] is not None
                      and u["days_since_login"] > 90]

    failed_jobs = [j for j in jobs if j["status"] == "Failed"]

    summary = {
        "total_users":        len(users),
        "total_workbooks":    len(workbooks),
        "total_datasources":  len(datasources),
        "total_views":        len(views),
        "total_projects":     len(projects),
        "total_flows":        len(flows),
        "role_counts":        role_counts,
        "stale_workbooks":    len(stale_wb),
        "stale_datasources":  len(stale_ds),
        "unused_workbooks":   len(unused_wb),
        "inactive_users_90d": len(inactive_users),
        "failed_jobs_recent": len(failed_jobs),
        "ghost_datasources":        len(ghost_datasources),
        "stale_refresh_datasources": len([d for d in datasources if (d["days_stale"] or 0) > 30]),
        "top_views":          top_views,
    }

    return {
        "summary":           summary,
        "users":             users,
        "workbooks":         workbooks,
        "datasources":       datasources,
        "views":             views,
        "schedules":         schedules,
        "flows":             flows,
        "ghost_datasources": ghost_datasources,
        "fetch_warnings":    fetch_warnings,
        "fetched_at":        datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 計算フィールド解析
# ---------------------------------------------------------------------------

def fetch_flow_connections(flow_id: str) -> dict[str, Any]:
    """Prep フローの接続情報（入力・出力データソース）を取得する"""
    server, auth = _make_server()

    with server.auth.sign_in(auth):
        try:
            flow_item = server.flows.get_by_id(flow_id)
        except Exception as exc:
            raise ValueError(f"フロー取得に失敗しました: {exc}") from exc

        connections: list[dict] = []
        try:
            server.flows.populate_connections(flow_item)
            for conn in (flow_item.connections or []):
                # TSC バージョンによって属性名が異なるため候補を総当たりで取得
                def _get(*keys) -> str:
                    for k in keys:
                        v = getattr(conn, k, None)
                        if v:
                            return str(v)
                        v = getattr(conn, f"_{k}", None)
                        if v:
                            return str(v)
                    return ""

                connections.append({
                    "datasource_name": _get("datasource_name", "name"),
                    "datasource_id":   _get("datasource_id", "id"),
                    "connection_type": _get("type", "flow_type", "connection_type"),
                    "conn_type":       _get("conn_type", "db_class", "class"),
                })
                # デバッグ用に利用可能な属性を記録
                logger.debug("FlowConnectionItem attrs: %s", {
                    k: v for k, v in vars(conn).items() if not k.startswith('__')
                })
        except Exception as exc:
            logger.warning("フロー接続情報の取得に失敗しました: %s", exc)

        # TSC の FlowConnectionItem が全空の場合、直接 REST API XML を解析してフォールバック
        # NOTE: server._site_id / server._session は TSC の内部（private）属性。
        # TSC のバージョンアップで突然壊れる可能性がある。
        # 公開 API でフロー接続を取得する手段が TSC に追加された場合はそちらに移行すること。
        if connections and all(not c["datasource_name"] and not c["connection_type"] for c in connections):
            try:
                import defusedxml.ElementTree as DET
                url  = f"{server.baseurl}/api/{server.version}/sites/{server._site_id}/flows/{flow_id}/connections"
                resp = server._session.get(url)
                root = DET.fromstring(resp.content)
                ns   = {"t": "http://tableau.com/api"}
                connections = []
                for fc in root.findall(".//t:flowConnection", ns):
                    ds_el = fc.find("t:datasource", ns)
                    connections.append({
                        "datasource_name": ds_el.get("name", "") if ds_el is not None else "",
                        "datasource_id":   ds_el.get("id",   "") if ds_el is not None else "",
                        "connection_type": fc.get("type", ""),
                        "conn_type":       "",
                    })
            except Exception as exc:
                logger.warning("フロー接続情報のフォールバック取得に失敗: %s", exc)

        return {
            "connections":  connections,
            "flow_name":    flow_item.name,
            "project":      flow_item.project_name or "",
            "description":  flow_item.description or "",
        }


def fetch_workbook_fields(workbook_id: str) -> dict[str, Any]:
    """ワークブックをダウンロードして計算フィールドの依存関係を解析する"""
    server, auth = _make_server()

    with server.auth.sign_in(auth):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = server.workbooks.download(workbook_id, filepath=tmpdir)
            twb_content = _extract_twb_content(file_path)
            if not twb_content:
                raise ValueError("TWBファイルの抽出に失敗しました")
            return _parse_twb_fields(twb_content)


def _extract_twb_content(file_path: str) -> str | None:
    """TWB / TWBX ファイルから TWB XML 文字列を抽出する"""
    if file_path.lower().endswith(".twb"):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    if file_path.lower().endswith(".twbx"):
        with zipfile.ZipFile(file_path, "r") as z:
            for name in z.namelist():
                # __MACOSX 等のメタファイルを除外
                if name.lower().endswith(".twb") and not name.startswith("__"):
                    return z.read(name).decode("utf-8", errors="replace")
    return None


def _strip_formula_for_deps(formula: str) -> str:
    """
    依存関係抽出用に数式を前処理する。
    - シングルクォート文字列リテラル内の [] を除去（文字列中の [field] を誤検出しない）
    - // 行コメントを除去
    """
    # 文字列リテラル（'...'）を空文字列に置換
    formula = re.sub(r"'[^']*'", "''", formula)
    # // 行コメントを除去
    formula = re.sub(r"//[^\n]*", "", formula)
    return formula


def _parse_twb_fields(twb_content: str) -> dict[str, Any]:
    """
    TWB XML を解析して以下を返す:
      fields         : 計算フィールド一覧 [{datasource, field, formula, type}]
      edges          : 依存関係エッジ [{source, target, weight, formula, datasource}]
      datasource_info: データソース情報 [{name, connections:[{type, server, database}]}]
    """
    root = DET.fromstring(twb_content)
    datasources_el = root.find("datasources")
    if datasources_el is None:
        return {"fields": [], "edges": [], "datasource_info": []}

    # ── 第1パス: カラム名→表示名マッピング + データソース情報収集 ──
    column_mapping: dict[str, str] = {}   # "[Calc_xxxx]" -> "表示名"
    datasource_info: list[dict] = []
    _SKIP_DS = {"Parameters"}

    for ds in datasources_el.findall("datasource"):
        ds_name    = ds.get("name", "")
        ds_caption = ds.get("caption") or ds_name
        if ds_name in _SKIP_DS or not ds_caption:
            continue

        # 接続情報
        connections = []
        for conn in ds.findall(".//connection"):
            conn_type = conn.get("class", "")
            if conn_type in ("", "sqlproxy", "federated"):
                continue
            connections.append({
                "type":     conn_type,
                "server":   conn.get("server", ""),
                "database": conn.get("dbname", "") or conn.get("filename", ""),
            })

        datasource_info.append({
            "name":        ds_caption,
            "connections": connections,
        })

        # カラムマッピング構築
        for col in ds.findall("column"):
            name    = col.get("name", "")
            caption = col.get("caption", "")
            if name and caption:
                column_mapping[name] = caption

    # ── 第2パス: 計算フィールド抽出 ──
    fields: list[dict] = []

    for ds in datasources_el.findall("datasource"):
        ds_name    = ds.get("name", "")
        ds_caption = ds.get("caption") or ds_name
        if ds_name in _SKIP_DS or not ds_caption:
            continue

        for col in ds.findall("column"):
            name    = col.get("name", "")
            caption = col.get("caption", "")
            if not name or not caption:
                continue

            calc = col.find("calculation")
            if calc is None:
                continue

            formula = calc.get("formula", "")
            if not formula:
                continue

            # カラム名参照を表示名に置換（長いキーを優先して誤置換を防ぐ）
            for key in sorted(column_mapping, key=len, reverse=True):
                formula = formula.replace(key, f"[{column_mapping[key]}]")

            fields.append({
                "datasource": ds_caption,
                "field":      caption,
                "formula":    formula,
                "type":       calc.get("class", ""),
            })

    # ── 依存関係エッジ生成（Sankey 用） ──
    edges: dict[str, dict] = {}

    for row in fields:
        target = row["field"]
        stripped = _strip_formula_for_deps(row["formula"])
        for m in re.finditer(r"\[([^\]]+)\]", stripped):
            token = m.group(1)
            # Parameters 参照はスキップ
            if "Parameters" in token:
                token = token.split(".")[-1]
            if token == target:
                continue
            key = f"{token}->{target}"
            if key not in edges:
                edges[key] = {
                    "source":     token,
                    "target":     target,
                    "weight":     1,
                    "formula":    row["formula"],
                    "datasource": row["datasource"],
                }
            else:
                edges[key]["weight"] += 1

    return {
        "fields":          fields,
        "edges":           list(edges.values()),
        "datasource_info": datasource_info,
    }
