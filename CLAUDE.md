# tabechoku_DB

食べチョクの「いちご」検索結果を毎日取得し、価格・推定販売数・価格レコメンドを表示するダッシュボード。
大分県のいちご農家の運用代行で、価格設定の根拠を出すために使う。

## 構成
- `scraper/scrape.py` 検索結果一覧（上位 `max_pages` ページ）を取得し `data/snapshots/YYYY-MM-DD.csv` を保存
- `scraper/build.py` スナップショットを集計し `docs/data.js` を生成（`docs/manual.md` もHTML化して埋め込む）
- `docs/` ダッシュボード（GitHub Pages: main /docs で公開）
- `.github/workflows/daily.yml` 毎日の自動実行。データは常に `main` にコミット
- テスト: `python -m unittest discover -s tests -t .`

## 変更時のルール（必須）
運用方針・取得対象・計算ロジック・設定値・実行スケジュールを変更したときは、同じコミットで必ず次も行う。
1. `docs/manual.md` の該当箇所を更新する（数値は `config.json` などから `{{キー}}` で差し込むので、新しい設定値を追加したら `scraper/build.py` の `render_manual` にもキーを追加する）
2. `docs/manual.md` 末尾の「変更履歴」に日付と変更内容を1行追記する（新しい順）
3. `python -m scraper.build` で `docs/data.js` を再生成し、`main` と作業ブランチの両方に push する

## 注意
- 食べチョクは13ページ目以降・商品ページの連続取得で HTTP 405（アクセス制限）を返す。回避策（セッションの使い回し・偽装など）は使わない
- ユーザー向けの説明は日本語
