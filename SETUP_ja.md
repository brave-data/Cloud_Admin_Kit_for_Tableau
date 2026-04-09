# セットアップガイド — Cloud Admin Kit for Tableau

> **English version**: [SETUP.md](SETUP.md)

---

## 動作要件

- Python **3.11以上**
- Tableau CloudサイトのPersonal Access Token（PAT）

---

## ステップ1 — リポジトリをクローン

```bash
git clone https://github.com/brave-data/Cloud_Admin_Kit_for_Tableau.git
cd Cloud_Admin_Kit_for_Tableau
```

---

## ステップ2 — 仮想環境を作成

まず、Pythonのバージョンを確認してください：

```bash
python3 --version
```

`Python 3.11.x` 以上が表示された場合：

```bash
# Mac / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

3.11 未満（例: 3.9）が表示された場合は、先に Python 3.11 をインストールしてください：

- **Mac（Homebrew）：** `brew install python@3.11`
- **その他：** [python.org](https://www.python.org/downloads/) からダウンロード

インストール後、バージョンを明示して仮想環境を作成します：

```bash
# Mac / Linux
python3.11 -m venv .venv
source .venv/bin/activate

# Windows
py -3.11 -m venv .venv
.venv\Scripts\activate
```

---

## ステップ3 — 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

---

## ステップ4 — 環境変数を設定

```bash
cp .env.example .env
```

`.env` をテキストエディタで開き、Tableau Cloudの認証情報を入力します：

```ini
TABLEAU_SERVER_URL=https://10ay.online.tableau.com   # Tableau CloudのポッドURL
TABLEAU_SITE_NAME=mycompany                          # サイト名（デフォルトサイトの場合は空欄）
TABLEAU_TOKEN_NAME=my-pat-name                       # PATの名前
TABLEAU_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxx            # PATのシークレット（パスワードと同様に管理）
```

### ポッドURLの確認方法

Tableau CloudのURLが `https://10ay.online.tableau.com/#/site/mycompany/...` の場合、ポッドURLは `https://10ay.online.tableau.com` の部分です。

### Personal Access Tokenの作成手順

1. Tableau Cloudにログイン
2. 右上のアカウントアイコン → **アカウント設定**
3. **個人用アクセストークン** → **新しいトークンを作成**
4. 名前を付けて **シークレットをすぐにコピー** — 表示は1回限りです

---

## ステップ5 — サーバーを起動

```bash
python main.py
```

デフォルトでは **http://localhost:8000** で起動します。

ポートを変更する場合は、`.env` に `PORT=8080` を追加してください。

---

## ステップ6 — データを取得

ブラウザで **http://localhost:8000** を開きます。初回はデータが空の状態で表示されます。

右上の **「↻ 更新」ボタン** を押してください。Tableau Cloud REST APIからデータを取得します。サイトの規模によりますが、**10〜30秒**ほどかかります。

完了すると、すべてのタブにデータが表示されます。

---

## オプション: pre-commit フック（認証情報の誤コミット防止）

`hooks/pre-commit` スクリプトを導入すると、`.env.example` に実際の認証情報が含まれている状態でのコミットをブロックできます。PATシークレットの誤公開を防ぐための安全策です。

インストール方法：

```bash
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

フックは `TABLEAU_SERVER_URL`・`TABLEAU_TOKEN_NAME`・`TABLEAU_TOKEN_SECRET` にプレースホルダー以外の値が入っていないかを検査します。実際の値が見つかった場合はコミットがブロックされ、エラーメッセージが表示されます。

---

## アップデート手順

```bash
git pull
pip install -r requirements.txt   # 新しい依存パッケージを取得
python main.py
```

---

## トラブルシューティング

| 症状 | 原因 | 対処法 |
|------|------|--------|
| `ImportError: tableauserverclient` | Pythonバージョンが古い、またはvenvが有効化されていない | `.venv` を有効化し、Python 3.11以上であることを確認 |
| 更新時に「接続に失敗しました」 | `.env` の認証情報が誤っている | URL・トークン名・シークレットを再確認 |
| 更新後にローディングが止まらない | バックグラウンドスレッドでエラー発生 | ターミナルのPythonエラー出力を確認 |
| タブのデータが0件 | そのコンテンツタイプがサイトに存在しない | 正常な状態です |
| ポート8000が使用中 | 別プロセスが使用中 | `.env` に `PORT=8080` を追加 |
| `SSLError: certificate verify failed` | 社内プロキシによるSSL証明書の差し替え | 下記 **SSL / 社内プロキシ** セクションを参照 |

---

## SSL / 社内プロキシ

更新ボタンを押したときに `SSLError: certificate verify failed` が表示される場合、社内プロキシがSSL通信を中継し、サーバー証明書を内部CAで署名したものに差し替えていると考えられます。

**対処法: 社内CA証明書をアプリに読み込ませる**

**手順1 — ルートCA証明書を入手する**

方法A: Chromeからエクスポート（情シスへの申請不要）
1. ChromeでTableau Cloudを開く。
2. アドレスバーの鍵アイコン → **接続が保護されています** → **証明書は有効です** をクリック。
3. **詳細**タブを開き、証明書チェーンの最上位（ルートCA）を選択。
4. **エクスポート**をクリックし、**PEM形式**で保存（例: `corporate-ca.pem`）。

方法B: 情報システム部門に **ルートCA証明書をPEM形式**（`.pem` または `.crt`）で依頼する。

**手順2 — アプリに設定する**

1. プロジェクト内の以下の場所に配置します：
   ```
   certs/corporate-ca.pem
   ```
   `certs/` フォルダは `.gitignore` 済みのため、証明書ファイルがリポジトリにコミットされることはありません。
3. `.env` に以下の1行を追加します：
   ```ini
   REQUESTS_CA_BUNDLE=certs/corporate-ca.pem
   ```
4. アプリを再起動（`python main.py`）して、更新ボタンを押し直してください。

この方法はSSL検証を無効化せず、CA束を差し替えるだけです。セキュリティ上問題なく、情シスへの申請も不要です（証明書の入手のみ依頼してください）。
