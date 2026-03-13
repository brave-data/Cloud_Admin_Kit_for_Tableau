# Tableau Cloud Manager — 開発者向けドキュメント

> 対象読者: このリポジトリのメンテナー（本人）

---

## アーキテクチャ概要

```
ブラウザ (Bootstrap 5 + DataTables)
    │  fetch / XHR
    ▼
FastAPI (main.py) ─── localhost:8000
    │  Python 関数呼び出し
    ▼
tableau_client.py
    │  tableauserverclient (TSC) ライブラリ
    ▼
Tableau Cloud REST API
```

- **サーバー**: uvicorn + FastAPI, シングルプロセス
- **データ**: 起動時に一括取得してインメモリキャッシュ (`_cache["data"]`)
- **UI**: SPA ではなく単一 HTML。タブ切替はクラス操作で実現

---

## ファイル構成

```
tableau-cloud-manager/
├── main.py              # FastAPI エントリポイント・APIルート
├── tableau_client.py    # Tableau REST APIラッパー・XML解析
├── maintenance.py       # 隔週メンテナンス用スタンドアロンスクリプト
├── requirements.txt     # pip依存
├── .env                 # 認証情報（Git管理外）
├── .env.example         # テンプレート
├── .gitignore
├── README.md            # ユーザー向け
├── DEVELOPER.md         # このファイル
├── reports/             # maintenance.py が生成するレポート（Git管理外推奨）
└── static/
    └── index.html       # フロントエンド全体（HTML + CSS + JS 一体型）
```

---

## データフロー

### 起動時
1. `lifespan()` → バックグラウンドスレッドで `_do_fetch()` 実行
2. `_do_fetch()` → `fetch_all()` (tableau_client) → `_cache["data"]` に格納
3. ブラウザが `/api/status` をポーリング → `ok` になったらデータ取得開始

### 更新ボタン押下時
1. `POST /api/refresh` → `_field_cache` / `_flow_conn_cache` をクリア → 再フェッチ
2. フロントエンドが各 `/api/*` を順次 fetch し、グローバル変数 `window._allData` に格納
3. `rotateSnapshot()` → localStorage に前回/今回スナップショット保存
4. 各テーブル/グラフを再描画

---

## API エンドポイント一覧

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/` | index.html を返す |
| GET | `/api/status` | `{status, error, fetched_at}` |
| GET | `/api/summary` | サマリ統計オブジェクト |
| GET | `/api/workbooks` | WB一覧 (tags含む) |
| GET | `/api/datasources` | DS一覧 |
| GET | `/api/views` | ビュー一覧 (usage_count付き) |
| GET | `/api/users` | ユーザー一覧 |
| GET | `/api/schedules` | エクストラクト更新スケジュール |
| GET | `/api/flows` | Prep フロー一覧 |
| GET | `/api/flows/{id}/connections` | フロー接続情報（キャッシュ付き） |
| GET | `/api/workbooks/{id}/fields` | WB計算フィールド解析（キャッシュ付き） |
| GET | `/api/ktw-fields` | KTWタグWBの計算フィールド一括取得 |
| POST | `/api/refresh` | データ再取得トリガー |
| GET | `/docs` | Swagger UI |

---

## フロントエンド構成 (index.html)

### 主要グローバル変数

| 変数 | 型 | 内容 |
|---|---|---|
| `window._allData` | Object | `{wb, ds, views, users, schedules, flows, summary}` |
| `window._lang` | `'ja'` \| `'en'` | 現在の言語設定 |
| `window._ktwDiff` | Array | KTW計算フィールド差分結果 |

### 主要関数

| 関数 | 役割 |
|---|---|
| `loadAll()` | 更新ボタン押下時の全データ取得〜描画 |
| `rotateSnapshot(data)` | localStorageのスナップショットローテーション |
| `computeDiff(cur, prev, fields)` | 配列差分計算 → `{added, changed, deleted}` |
| `computeKtwDiff(curWbs, prevWbs)` | KTW計算フィールド差分 |
| `renderDiffTab(snap)` | 差分タブ全体を再描画 |
| `applyLang(lang)` | 言語切替（i18n適用） |
| `switchToSection(name)` | 隠しタブ（Schedules/TopViews/Fields/Diff）への切替 |
| `initTable(id, order)` | DataTables 初期化・再初期化 |

### i18n

`I18N = { ja: {...}, en: {...} }` にキーを追加し、
HTMLには `data-i18n="key"` 属性をつけるだけで `applyLang()` が自動適用。

---

## localStorage キー

| キー | 内容 |
|---|---|
| `tcm_snap_cur` | 今回取得データのスナップショット |
| `tcm_snap_prev` | 前回取得データのスナップショット（差分比較元） |
| `tcm_ktw_cur` | 今回のKTW計算フィールドスキャン結果 |
| `tcm_ktw_prev` | 前回のKTW計算フィールドスキャン結果 |

---

## 新機能を追加する手順

### テーブルに列を追加する
1. `tableau_client.py` の該当 `fetch_*` 関数の返却 dict にキー追加
2. `static/index.html` の `<th>` 行と `tbody.innerHTML = rows.map(...)` の `<td>` 行に追加
3. `i18n` に `th_新キー` を追加（ja/en 両方）
4. 差分比較が必要なら `rotateSnapshot` と `computeDiff` の `compareFields` にも追加

### 新しいタブを追加する
1. `NAV_SECTIONS` と `ALL_PANES` にキーを追加
2. `<li class="nav-item">` をナビに追加
3. `<div class="tab-pane fade" id="tab-新キー">` をコンテンツ領域に追加
4. `switchToSection('新キー')` が機能するか確認

### 新しい API エンドポイントを追加する
1. `main.py` に `@app.get("/api/...")` を追加
2. `tableau_client.py` に対応するフェッチ関数を追加（必要に応じて）

---

## メンテナンスチェックリスト

```
[ ] requirements.txt の依存パッケージが最新か確認
    pip list --outdated

[ ] tableauserverclient のバージョンが Tableau Cloud APIと互換か確認
    https://tableau.github.io/server-client-python/

[ ] .env.example が実際の .env の項目と一致しているか確認

[ ] KTW監視WBのリスト（Tableau Cloudのタグ設定）が10件以内か確認

[ ] reports/ ディレクトリが肥大化していないか確認・古いレポートを削除
```

---

## よくある開発上のハマりポイント

### DataTables の再初期化
タブ切替後に列幅がズレる場合は `initTable()` を再呼び出し。
`destroy()` → 新規 `DataTable()` の順が必要。

### スナップショットタイミング
`rotateSnapshot()` は `loadAll()` のデータ取得直後に呼ぶ。
KTW フィールドスキャン（`fetchKtwFields()`）は非同期で後から完了するため、
完了後に `rotateKtwSnapshot()` → `renderDiffTab()` を再呼び出しする設計。

### Tableau Cloud 認証
TSC は `with server.auth.sign_in(auth):` ブロック内でのみ認証済み。
並列処理する場合は `asyncio.to_thread()` でスレッドに渡す（イベントループをブロックしない）。

### `.twb` / `.twbx` の計算フィールド解析
`fetch_workbook_fields()` は一時ディレクトリにダウンロードして解析後に削除。
大きいWBは数秒かかるため UI でフィードバックを出すこと。

---

## 環境

```
Python:      3.10+
FastAPI:     最新安定版
uvicorn:     最新安定版
Bootstrap:   5.3
DataTables:  1.13.8
```
