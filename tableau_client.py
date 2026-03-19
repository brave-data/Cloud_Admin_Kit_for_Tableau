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
from datetime import datetime, timezone
from typing import Any

import defusedxml.ElementTree as DET
import tableauserverclient as TSC
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


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
    server.add_http_options({"verify": True})
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


# ---------------------------------------------------------------------------
# メインフェッチ関数
# ---------------------------------------------------------------------------

def fetch_all() -> dict[str, Any]:
    """Tableau Cloud から全管理情報を取得して辞書で返す"""
    server, auth = _make_server()

    with server.auth.sign_in(auth):

        # ── ユーザー ────────────────────────────────────────
        # 権限不足（Site Administrator 未満）の場合に取得失敗することがある。
        # 失敗時は空リストで続行し、以降のオーナー表示が "Unknown" になる。
        try:
            users_raw = list(TSC.Pager(server.users))
        except Exception as exc:
            logger.warning("ユーザー一覧の取得に失敗しました（権限不足の可能性）: %s", exc)
            users_raw = []
        user_map  = {u.id: (u.fullname or u.name) for u in users_raw}

        users = []
        for u in users_raw:
            users.append({
                "id":         u.id,
                "name":       u.fullname or u.name,
                "email":      u.email or "",
                "site_role":  u.site_role or "",
                "last_login": _fmt(u.last_login),
                "days_since_login": _days_ago(u.last_login),
            })

        # ── プロジェクト ─────────────────────────────────────
        try:
            projects_raw = list(TSC.Pager(server.projects))
        except Exception as exc:
            logger.warning("プロジェクト一覧の取得に失敗しました: %s", exc)
            projects_raw = []
        project_map  = {p.id: p.name for p in projects_raw}

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
        try:
            workbooks_raw = list(TSC.Pager(server.workbooks))
        except Exception as exc:
            logger.warning("ワークブック一覧の取得に失敗しました: %s", exc)
            workbooks_raw = []
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
        try:
            datasources_raw = list(TSC.Pager(server.datasources))
        except Exception as exc:
            logger.warning("データソース一覧の取得に失敗しました: %s", exc)
            datasources_raw = []
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
            })

        # ── ビュー (使用状況付き) ───────────────────────────
        # TSC 0.30+ では usage=True を views.get() に直接渡す必要がある
        views_raw = []
        try:
            req = TSC.RequestOptions(pagesize=100)
            while True:
                page, pagination = server.views.get(req_options=req, usage=True)
                views_raw.extend(page)
                if len(views_raw) >= pagination.total_available:
                    break
                req.pagenumber += 1
        except Exception as exc:
            logger.warning("ビュー一覧の取得に失敗しました: %s", exc)
        views = []
        for v in views_raw:
            # TSC は last_viewed_at を直接公開しないため、利用可能な属性を試みる
            last_viewed = (getattr(v, "recently_viewed_at", None)
                           or getattr(v, "last_viewed_at", None))
            days_since_viewed = (_days_ago(last_viewed)
                                 if isinstance(last_viewed, datetime)
                                 else _days_ago(v.updated_at))
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
            })

        # ワークブック名をビューに付与
        wb_map = {wb["id"]: wb["name"] for wb in workbooks}
        for v in views:
            v["workbook_name"] = wb_map.get(v["workbook_id"], "")

        # ── ジョブ (サマリ計算用・直近 200 件、返却なし) ────────────
        job_req = TSC.RequestOptions(pagesize=50)
        try:
            jobs_raw = list(TSC.Pager(server.jobs, request_opts=job_req))[:200]
        except Exception as exc:
            logger.warning("ジョブ一覧の取得に失敗しました: %s", exc)
            jobs_raw = []

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

        # ── 抽出スケジュール ──────────────────────────────────
        schedules = []
        try:
            tasks_raw = list(TSC.Pager(server.tasks))
            for task in tasks_raw:
                content_name = ""
                content_type = ""
                project_name = ""
                owner_name   = ""

                ds_ref = getattr(task, "datasource", None)
                wb_ref = getattr(task, "workbook",   None)

                if ds_ref:
                    content_name = getattr(ds_ref, "name", "") or ""
                    content_type = "datasource"
                    for ds in datasources_raw:
                        if ds.id == getattr(ds_ref, "id", None):
                            project_name = ds.project_name or ""
                            owner_name   = user_map.get(ds.owner_id, "Unknown")
                            break
                elif wb_ref:
                    content_name = getattr(wb_ref, "name", "") or ""
                    content_type = "workbook"
                    for wb in workbooks_raw:
                        if wb.id == getattr(wb_ref, "id", None):
                            project_name = wb.project_name or ""
                            owner_name   = user_map.get(wb.owner_id, "Unknown")
                            break

                # スケジュール頻度・次回実行時刻
                frequency   = ""
                next_run_at = None
                schedule_obj = getattr(task, "schedule", None)
                if schedule_obj:
                    frequency = getattr(schedule_obj, "frequency", "") or ""
                    next_raw  = getattr(schedule_obj, "next_run_at", None)
                    if isinstance(next_raw, datetime):
                        next_run_at = _fmt(next_raw)
                    elif next_raw:
                        next_run_at = str(next_raw)

                schedules.append({
                    "id":           task.id,
                    "content_name": content_name,
                    "content_type": content_type,
                    "project":      project_name,
                    "owner":        owner_name,
                    "refresh_type": getattr(task, "extract_refresh_type", "") or "",
                    "frequency":    frequency,
                    "next_run_at":  next_run_at,
                })
        except Exception as exc:
            logger.warning("抽出スケジュールの取得に失敗しました: %s", exc)
            schedules = []

        # ── Prep フロー ──────────────────────────────────────
        flows_raw = []
        try:
            flows_raw = list(TSC.Pager(server.flows))
        except Exception as exc:
            logger.warning("Prepフロー一覧の取得に失敗しました: %s", exc)

        # フロー実行履歴（最新1ページ分）でフローIDごとの最終実行日を取得
        flow_run_map: dict[str, object] = {}
        try:
            run_req = TSC.RequestOptions(pagesize=100)
            recent_runs, _ = server.flow_runs.get(run_req)
            for run in recent_runs:
                fid = getattr(run, "flow_id", None)
                completed = getattr(run, "completed_at", getattr(run, "ended_at", None))
                if fid and completed is not None:
                    existing = flow_run_map.get(fid)
                    if existing is None or _ensure_utc(completed) > _ensure_utc(existing):
                        flow_run_map[fid] = completed
        except Exception as exc:
            logger.warning("フロー実行履歴の取得に失敗しました: %s", exc)

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
            })

        # ── サマリ ───────────────────────────────────────────
        role_counts: dict[str, int] = {}
        for u in users:
            role_counts[u["site_role"]] = role_counts.get(u["site_role"], 0) + 1

        stale_wb  = [w for w in workbooks if (w["days_stale"] or 0) > 180]
        stale_ds  = [d for d in datasources if (d["days_stale"] or 0) > 180]
        top_views = sorted(views, key=lambda v: v["total_views"], reverse=True)[:10]

        active_wb_ids = {v["workbook_id"] for v in views if v["total_views"] > 0}
        unused_wb = [w for w in workbooks if w["id"] not in active_wb_ids]

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
            "top_views":          top_views,
        }

        return {
            "summary":     summary,
            "users":       users,
            "workbooks":   workbooks,
            "datasources": datasources,
            "views":       views,
            "schedules":   schedules,
            "flows":       flows,
            "fetched_at":  datetime.now(timezone.utc).isoformat(),
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
        for m in re.finditer(r"\[([^\]]+)\]", row["formula"]):
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
