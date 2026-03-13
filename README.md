# Tableau Cloud Manager

Tableau Cloud の管理情報をブラウザで一覧・分析できるローカル Web アプリです。
Python + FastAPI で動作し、セットアップは 5 分で完了します。

---

## 画面イメージ

| タブ | 内容 |
|------|------|
| **ワークブック** | 全ワークブック・プロジェクト・オーナー・更新日・サイズ・タグ |
| **データソース** | 公開データソース・認定状態・更新日 |
| **ビュー（使用状況）** | 全ビューの累計アクセス数 |
| **ユーザー** | ライセンス別一覧・最終ログイン日・未ログイン日数 |
| **ジョブ** | 最近のエクストラクト更新ジョブとその成否 |
| **Top ビュー** | アクセス数 Top 10 の横棒グラフ |

サマリカードでは **ワークブック数 / DS 数 / ユーザー数 / 180 日以上未更新コンテンツ / 90 日以上未ログインユーザー** を一目で確認できます。

---

## セットアップ

### 前提
- Python 3.10 以上
- Git（VS Code の Source Control 機能でも可）

### 1. リポジトリをクローン

```bash
git clone https://github.com/YOUR_USERNAME/tableau-cloud-manager.git
cd tableau-cloud-manager
```

VS Code を使う場合:
1. `Ctrl+Shift+P` → "Git: Clone" を選択
2. リポジトリ URL を貼り付け
3. クローン先フォルダを選択

---

### 2. 仮想環境を作成・有効化

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Mac / Linux
python3 -m venv .venv
source .venv/bin/activate
```

---

### 3. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

---

### 4. 環境変数を設定

```bash
cp .env.example .env
```

`.env` をテキストエディタで開き、以下を入力します:

```ini
TABLEAU_SERVER_URL=https://10ay.online.tableau.com   # あなたの Tableau Cloud URL
TABLEAU_SITE_NAME=mycompany                          # サイト名（デフォルトサイトは空欄）
TABLEAU_TOKEN_NAME=my-pat-name                       # PAT の名前
TABLEAU_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxx            # PAT のシークレット
```

**Personal Access Token の作成手順:**
1. Tableau Cloud にログイン
2. 右上のアカウントメニュー → **「アカウント設定」**
3. **「Personal Access Tokens」** セクション → **「トークンの作成」**
4. 名前を入力して作成 → シークレットをコピー（一度しか表示されません）

---

### 5. アプリを起動

```bash
python main.py
```

ブラウザで → **http://localhost:8000** を開く

起動直後は Tableau Cloud からのデータ取得中の画面が表示されます。
データ量によりますが、通常 **10〜30 秒** で読み込み完了します。

---

## 定期更新

### 方法 A: 画面上の「更新」ボタン
ブラウザ右上の **「↻ 更新」** ボタンをクリックすると最新データを取得します。

### 方法 B: cron（Mac / Linux）

```bash
# 毎朝 8 時に自動起動（アプリが停止している場合は起動）
0 8 * * 1-5 cd /path/to/tableau-cloud-manager && .venv/bin/python main.py
```

### 方法 C: Windows タスクスケジューラ
1. タスクスケジューラを開く
2. 「基本タスクの作成」→ スケジュールを設定
3. 操作: `python main.py`（作業フォルダをプロジェクトルートに設定）

---

## ファイル構成

```
tableau-cloud-manager/
├── main.py              # FastAPI サーバー（エントリポイント）
├── tableau_client.py    # Tableau Cloud REST API クライアント
├── requirements.txt     # Python 依存パッケージ
├── .env.example         # 環境変数テンプレート
├── .gitignore           # .env などを Git 管理対象外に
├── README.md            # このファイル
└── static/
    └── index.html       # ブラウザ UI（Bootstrap + DataTables）
```

---

## API エンドポイント

アプリ起動中は `http://localhost:8000/docs` で Swagger UI も使えます。

| エンドポイント | 説明 |
|---|---|
| `GET /api/status` | 取得状態・最終更新日時 |
| `GET /api/summary` | サマリ統計 |
| `GET /api/workbooks` | ワークブック一覧 |
| `GET /api/datasources` | データソース一覧 |
| `GET /api/views` | ビュー一覧（使用状況付き） |
| `GET /api/users` | ユーザー一覧 |
| `GET /api/jobs` | ジョブ履歴 |
| `POST /api/refresh` | Tableau Cloud から再取得 |

---

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| 「接続に失敗しました」と表示される | `.env` の URL / トークン名 / シークレットを再確認 |
| データが 0 件になるタブがある | サイトのコンテンツが空の可能性あり（正常） |
| ポート 8000 が使えない | `.env` に `PORT=8080` を追加して再起動 |
| SSL エラーが出る | `tableau_client.py` の `"verify": True` を `False` に変更（社内 Proxy 環境） |
