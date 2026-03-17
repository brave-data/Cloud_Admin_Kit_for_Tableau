# Tableau Cloud Manager

> **English README**: [README.md](README.md)

Tableau Cloudサイトの**一元管理・変更追跡・メンテナンス効率化**を実現するローカルWebアプリです。
Python + FastAPIで構築され、すべて手元のマシン上で動作します。

---

## なぜこのツールが必要か

Tableau Cloud の管理画面は機能ごとに分散しており、「どのデータソースがどのダッシュボードで使われているか」「昨日と今日で何が変わったか」「誰が長期間ログインしていないか」を把握するには、複数画面を行き来する必要があります。

**Tableau Cloud Manager** は、管理者が日常のメンテナンスで本当に必要な情報を1画面に集約し、Tableau Cloudの管理を楽にするためのツールです。

---

## 主な価値

### 1. サイト全体をダッシュボードで把握

![ダッシュボード概要](docs/screenshots/01_dashboard.png)

ページを開くだけで、サイト全体の状況が一目でわかります。

- **ワークブック / データソース / ビュー / ユーザー / Prepフロー** の件数をカード表示
- **180日以上未閲覧**のコンテンツ数 → 削除・整理の優先度判断に
- **90日以上未ログイン**のユーザー数 → ライセンス最適化の手がかりに
- カードをクリックするだけで対応する一覧タブへ即ジャンプ

---

### 2. データソースと紐づきをひと目で確認

![データソース一覧](docs/screenshots/02_datasources.png)

データソース一覧では、各データソースの**プロジェクト・オーナー・タイプ・認定状態・最終更新からの経過日数**を一覧表示。

- 経過日数が長いデータソース（赤表示）を即座に特定
- 認定状態（Certified）を一列で管理
- 各行を展開すると、そのデータソースを参照しているワークブック一覧を表示

---

### 3. 人気コンテンツのランキング把握

![Top ビュー](docs/screenshots/03_topviews.png)

累計ビュー数 Top 10 を棒グラフで可視化。

- どのダッシュボードが最も使われているかを即座に把握
- 利用実績に基づくコンテンツ整理・優先メンテナンスの判断材料に

---

### 4. 日次の変更を自動追跡（差分比較）

![差分比較](docs/screenshots/05_diff.png)

「昨日と比べて今日何が変わったか」を自動で検出します。

- 🟢 **新規追加**: 新しく作成されたWB・DS・フロー・ユーザー
- 🟡 **更新**: 名前・プロジェクト・オーナーの変更
- 🔴 **削除**: 前日存在していたが今日なくなったコンテンツ
- **KTWタグ**を付けたワークブックは計算フィールドの追加・削除・数式変更まで追跡

変更通知機能のないTableau Cloudで、**誰かが誤ってコンテンツを削除したり、意図しない変更が加えられた場合でも、翌日の確認で即座に気づける**ようになります。

---

### 5. 更新スケジュールの監視

![スケジュール管理](docs/screenshots/06_schedules.png)

データの鮮度を保つために欠かせないスケジュール管理。

- 全抽出更新スケジュールを一覧表示
- 次回実行時刻が過去になっているものを**「期限超過」バッジ**でハイライト → 更新が止まっているデータソースを即特定

---

### 6. 計算フィールドの依存関係を分析

![計算フィールド分析](docs/screenshots/04_fields.png)

ワークブックの計算フィールドをダウンロード・解析し、フィールド間の依存関係をSankeyチャートで可視化。

- どの計算フィールドがどのフィールドに依存しているかを視覚的に把握
- 複雑な計算ロジックのメンテナンス・引き継ぎに役立つ

---

### 7. ダークモード対応

![ダークモード](docs/screenshots/07_dark_mode.png)

ライト / ダークモードを切り替え可能。長時間の管理作業でも目に優しい表示で利用できます。日本語 / 英語の言語切替にも対応しています。

---

## クイックスタート

```bash
git clone https://github.com/brave-data/Tableau_Cloud_Manager.git
cd Tableau_Cloud_Manager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Tableau Cloudの認証情報を入力
python main.py
```

ブラウザで **http://localhost:8000** を開き、**「↻ 更新」ボタン** を押すとデータ取得が始まります。

**→ 詳細なセットアップ手順・PATの作成方法・トラブルシューティング: [SETUP_ja.md](SETUP_ja.md)**

---

## KTWタグ — 計算フィールド変更監視

Tableau Cloud のワークブックに `KTW` タグを付けると、計算フィールドの自動監視が有効になります。

- 更新のたびに最大10件のKTWタグ付きWBをダウンロード・解析
- フィールドの**追加・削除・数式変更**が差分比較タブの「計算フィールド [KTW監視]」カテゴリに表示
- 「誰かが計算フィールドをこっそり変えた」を翌日に自動検出

---

## メンテナンス自動化

隔週（毎月1日・15日 9:00）にスケジュールタスクが自動実行され、システム健全性レポートを生成します：

- Tableau REST APIバージョンの互換性チェック
- Pythonパッケージの更新確認（tableauserverclient・fastapi・uvicornなど）
- GitHubリポジトリとの同期状態

ヘッダーのレンチアイコンに**オレンジの通知ドット**が表示されたら、対応が必要な項目があります。

---

## APIエンドポイント

アプリ起動中は `http://localhost:8000/docs` でSwagger UIが利用できます。

| エンドポイント | 説明 |
|--------------|------|
| `GET /api/status` | 取得ステータスと最終更新日時 |
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

## ファイル構成

```
Tableau_Cloud_Manager/
├── main.py                  # FastAPIサーバー（エントリーポイント）
├── tableau_client.py        # Tableau Cloud REST APIクライアント
├── requirements.txt         # Python依存パッケージ
├── .env.example             # 環境変数テンプレート
├── maintenance_report.json  # 隔週メンテナンスタスクが自動生成
├── README.md                # 英語版README
├── README_ja.md             # このファイル（日本語版）
├── SETUP.md                 # 詳細セットアップガイド（英語）
├── SETUP_ja.md              # 詳細セットアップガイド（日本語）
├── docs/screenshots/        # README用UIスクリーンショット
└── static/
    └── index.html           # シングルページUI（Bootstrap 5 + DataTables）
```

---

## 技術スタック

- **バックエンド**: Python 3.10+、FastAPI、uvicorn、tableauserverclient
- **フロントエンド**: Bootstrap 5.3、Bootstrap Icons、DataTables 1.13、D3.js（Sankey）
- **データ永続化**: ブラウザの `localStorage`（差分スナップショット）
- **スケジューリング**: Claude Codeスケジュールタスク（隔週メンテナンス）
