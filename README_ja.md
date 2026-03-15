# Tableau Cloud Manager

Tableau Cloudサイトの閲覧・分析・監視を行うローカルWebアプリです。Python + FastAPIで構築されており、すべて手元のマシン上で動作します。

> **English README**: [README.md](README.md)

---

## 機能一覧

| タブ | 内容 |
|------|------|
| **ワークブック** | プロジェクト・オーナー・最終更新日・サイズ・タグの一覧 |
| **データソース** | 公開済みデータソースと認定状態 |
| **ビュー** | 全ビューと累計ビュー数 |
| **ユーザー** | ライセンス種別・最終ログイン・未ログイン日数 |
| **Prepフロー** | フロー一覧と最終実行状態 |
| **スケジュール管理** | 抽出更新スケジュールと次回実行時刻 |
| **Top ビュー** | 累計ビュー数 Top 10 の棒グラフ |
| **計算フィールド分析** | ワークブックをダウンロードして計算フィールドの依存関係を可視化（Sankeyチャート） |
| **差分比較** | 前日との比較（新規追加・更新・削除）。シート変更やKTWタグ付きWBの計算フィールド変更も検出 |
| **使い方** | アプリ内操作ガイド |
| **メンテナンス** | 隔週の自動ヘルスチェック（APIバージョン・パッケージ更新・Gitステータス） |

**サマリーカード**でサイト全体の状況（WB数・DS数・ユーザー数・180日以上未閲覧コンテンツ・90日以上未ログインユーザー）をひと目で確認できます。

---

## 動作要件

- Python 3.10以上
- Tableau CloudサイトのPersonal Access Token（PAT）

---

## セットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/brave-data/Tableau_Cloud_Manager.git
cd Tableau_Cloud_Manager
```

### 2. 仮想環境を作成・有効化

```bash
# Mac / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### 3. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数を設定

```bash
cp .env.example .env
```

`.env` をテキストエディタで開き、Tableau Cloudの認証情報を入力します：

```ini
TABLEAU_SERVER_URL=https://10ay.online.tableau.com   # Tableau CloudのURL
TABLEAU_SITE_NAME=mycompany                          # サイト名（デフォルトサイトの場合は空欄）
TABLEAU_TOKEN_NAME=my-pat-name                       # PATの名前
TABLEAU_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxx            # PATのシークレット
```

**Personal Access Tokenの作成手順：**
1. Tableau Cloudにログイン
2. 右上のアカウントメニュー → **アカウント設定**
3. **個人用アクセストークン** → **トークンを作成**
4. 名前を入力 → シークレットをコピー（表示は1回のみ）

### 5. アプリを起動

```bash
python main.py
```

ブラウザで **http://localhost:8000** を開きます。

初回起動時は右上の **「更新」ボタン** を押してTableau Cloudからデータを取得してください。サイトの規模にもよりますが、10〜30秒ほどかかります。

---

## KTWタグ — 計算フィールド監視

Tableau CloudのワークブックにKTWタグを付けると、計算フィールドの自動監視が有効になります。

- **更新**のたびに最大10件のKTWタグ付きWBをダウンロードし、計算フィールドを抽出します
- フィールドの追加・削除・数式変更が**差分比較タブ**の「計算フィールド [KTW監視]」カテゴリに表示されます
- 結果はブラウザの `localStorage` に保存され、セッションをまたいで比較されます

---

## メンテナンススケジュール

隔週（毎月1日・15日の午前9時）に自動タスクが実行され、プロジェクトルートに `maintenance_report.json` が生成されます。アプリの**メンテナンス**画面には以下が表示されます：

- Tableau REST APIバージョンの互換性確認
- Pythonパッケージの更新確認（tableauserverclient・fastapi・uvicornなど）
- リモートリポジトリとのGit同期状態
- 推奨アクション

「今すぐチェック」ボタンで手動実行も可能です。

---

## ファイル構成

```
Tableau_Cloud_Manager/
├── main.py                  # FastAPIサーバー（エントリーポイント）
├── tableau_client.py        # Tableau Cloud REST APIクライアント
├── requirements.txt         # Python依存パッケージ
├── .env.example             # 環境変数テンプレート
├── .gitignore               # .envとvenvをGitから除外
├── maintenance_report.json  # 隔週メンテナンスタスクが生成
├── README.md                # 英語版README
├── README_ja.md             # このファイル（日本語版）
└── static/
    └── index.html           # シングルページUI（Bootstrap 5 + DataTables）
```

---

## APIエンドポイント

アプリ起動中は `http://localhost:8000/docs` でSwagger UIを確認できます。

| エンドポイント | 説明 |
|--------------|------|
| `GET /api/status` | ステータスと最終更新日時 |
| `GET /api/summary` | サイト全体のサマリー統計 |
| `GET /api/workbooks` | ワークブック一覧 |
| `GET /api/datasources` | データソース一覧 |
| `GET /api/views` | ビュー一覧と累計ビュー数 |
| `GET /api/users` | ユーザー一覧 |
| `GET /api/flows` | Prepフロー一覧 |
| `GET /api/schedules` | 更新スケジュール一覧 |
| `GET /api/workbooks/{id}/fields` | ワークブックの計算フィールド分析 |
| `GET /api/ktw-fields` | KTWタグ付きWBの計算フィールド（最大10件） |
| `GET /api/maintenance-report` | 最新のメンテナンスレポート |
| `POST /api/refresh` | Tableau Cloudからデータを再取得 |

---

## トラブルシューティング

| 症状 | 対処法 |
|------|--------|
| 「接続に失敗しました」エラー | `.env` のURL・トークン名・シークレットを確認 |
| タブのデータが0件 | そのタイプのコンテンツがサイトに存在しない場合は正常 |
| ポート8000が使用中 | `.env` に `PORT=8080` を追加して再起動 |
| SSLエラー（社内プロキシ環境） | `tableau_client.py` で `verify=False` を設定（本番環境では非推奨） |

---

## 技術スタック

- **バックエンド**: Python 3.10+、FastAPI、uvicorn、tableauserverclient
- **フロントエンド**: Bootstrap 5.3、Bootstrap Icons、DataTables 1.13、D3.js（Sankey）
- **データ永続化**: ブラウザの `localStorage`（差分スナップショット）
- **スケジューリング**: Claude Codeスケジュールタスク（隔週メンテナンス）
