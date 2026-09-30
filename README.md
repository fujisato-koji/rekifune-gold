# 歴舟川 砂金地図

歴舟川とその周りの川で、昔の人が砂金を採った場所の記録を集め、3D の地形の上に置く。
目的は、昔の人が掘っていない場所で、砂金がたまりやすい場所を探すこと。
まずは昔の採取地を地図にするところから始める。

## 公開サイト

https://fujisato-koji.github.io/rekifune-gold/ （GitHub Pages、main の最上位を公開）。

## 開き方

データを fetch で読むので、index.html をファイルとして直接開いても表示されない。
ローカルサーバーから開く。

```bash
python -m http.server 8791 --bind 127.0.0.1
# ブラウザで http://127.0.0.1:8791/ を開く
```

右ドラッグ（または Ctrl を押しながらドラッグ）で視点を傾け、回す。
背景は、今の写真、1974〜78年と 1961〜69年の写真、1947〜48年の米軍写真（4枚の範囲だけ）、陰影起伏図、標準地図、淡色地図から選べる。
URL に `?base=old60` のように付けると、最初からその背景で開く（photo、old70、old60、usa、relief、std、pale）。
`?at=143.110,42.562,13.5,0` のように付けると、経度、緯度、ズーム、傾きを指定して開く。
`?sel=RC-003` のように付けると、その記録を選んだ状態で開く。
一覧や地図で選んだものは、水色の線や面で光り、名前の札が付く。
採取地の点、金色の川、左の一覧を押すと、右に内容と出典が出る。

## 構成

| パス | 中身 |
|---|---|
| `index.html`, `viewer/` | ビューワ（MapLibre GL JS 4.7.1、地理院の標高タイルを Terrarium に変換して地形にする） |
| `data/sites.geojson` | 地図に置いた採取地（点） |
| `data/river_records.json` | 川単位の採取記録（区間が分からないので川全体に色を付ける） |
| `data/reach_records.json` | 区間（川筋）の記録。`tools/build_reaches.py` が `data/reaches.geojson` を作る |
| `data/district_records.json` | 郡単位の記録（明治の許可区域の合計など） |
| `data/unplaced.json` | 記録はあるが位置が分からないもの |
| `notes/` | 現地確認の計画は `notes/field-plan.md`、図書館と役所への依頼は `notes/requests.md`。一次資料の読み取り（原文の抜き書き、コマ番号つき）。文献の一覧と要点は `notes/literature.md`、考察は `notes/placer-model.md` |
| `data/rivers.geojson` | 川の線（生成物。`tools/build_rivers.py` で作る） |
| `sources/catalog.json` | 出典の目録。記録の `sources` 欄はここの id を指す |
| `sources/raw/` | 取得した原本（PDF など）。git 管理外で、このPCにだけある。目録の `local` 欄に場所と sha256 を書く |
| `tools/find_candidates.py` | 川の縦断面から、勾配が急に緩む点と合流点の下流を候補として拾う（`data/candidates.geojson`、`notes/placer-model.md`） |
| `tools/cross_strike.py` | 地質図から読んだ走向（`data/strike_domains.json`）と川の向きから、地層を横切る区間を出す（`data/cross_reaches.geojson`）。`tools/find_candidates.py` の後に回す |
| `tools/build_claims.py` | 国土数値情報の鉱区（1991年時点）を切り出す（`data/claims.geojson`） |
| `tools/rank_candidates.py` | 候補に、条件の重なり、林道までの距離、土地の区分、近くの昔の鉱区を書いて順位を付ける（`data/forest_roads.geojson` も作る） |
| `tools/terrace_height.py` | 段丘の比高（今の川底からの高さ）を出す（`data/terrace_heights.json`） |
| `profile.html` | 川の縦断面と候補地点の図（`data/profiles.json`） |
| `tools/extract_terrace.py` | 上札内図幅の地質図の画像から尾田面の範囲を切り出す |
| `tools/georef_usa.py` | 地理院の地図・空中写真閲覧サービスの1947〜48年の米軍写真を取り、位置を合わせて `data/usa/` に置く |
| `tools/mosaic.py` | 地理院タイルを範囲で切り出して 1 枚の画像にする（段丘の観察用） |
| `tools/build_rivers.py` | taiki-core の国土数値情報 W05 から、歴舟川、当縁川、紋別川、アイホシマ川の水系を切り出す |

## 候補を作り直す順番

```bash
python tools/find_candidates.py
python tools/cross_strike.py
python tools/build_claims.py
python tools/rank_candidates.py ../taiki-core
```

## 記録の書き方

記録ごとに、確かさを二つに分けて書く。
- `position_confidence`: 座標の確かさ。高は現地や一次資料の地図で確かめたもの。中は集落など代表点に置いたもの。低は「付近」としか書かれていないもの。
- `record_confidence`: 記録そのものの確かさ。一次資料、町の資料、二次資料（個人や民間のサイト）の順に下がる。

`position` 欄に、座標をどう決めたかを必ず書く。
新しい資料を使ったら、先に `sources/catalog.json` に URL、取得日、ライセンスを入れる。

## 次に当たる資料

区間が分かる細かさの記録を探す。

| 資料 | 期待すること | 状況 |
|---|---|---|
| 『北海道砂金案内』（明治33年）第二章「砂金採取区域」 | 道内の採取地の一覧 | 読了（2026-09-29）。十勝は郡ごとの合計だけで、歴舟川の区間は無い。当縁郡に河床 約126 km、土地 約70 ha の許可区域（`notes/ndl847465-hokkaido-sakin-annai.md`） |
| 官報の砂鉱採取許可の公告（明治26年以降） | 鉱区ごとの位置と面積 | 読了（2026-09-29）。明治39年から支流の川筋の単位で許可。区間の起点と終点は無い（`notes/claims-and-permits.md`） |
| 鉱区一覧（明治44年、大正2年） | 鉱区ごとの採取高 | 読了。明治43年の採取高。大正3年〜昭和16年の各版は未読 |
| 高畠彰「十勝國神威金鉱視察報告」（1950年） | 尾田の上流の段丘と品位 | 読了。最上位段丘と蕨原野は未試掘と明記。第1図の略図と上札内図幅の地質図で、段丘を尾田面とみて範囲を描いた（`notes/kamui-1950.md`） |
| 鉱業原簿と鉱区図（北海道経済産業局） | 鉱区の形 | 未着手。登録番号を明示して閲覧請求 |
| ライマンとマンローの報告（1874年、開拓使） | 歴舟川で砂金の出た地点 | 読了。海岸の3地点（アイボシマ、当縁、歴舟の河口付近）の試掘と品位。内陸は調べていない（`notes/lyman-munroe-1874.md`） |
| 松浦武四郎『十勝日誌』（1858年） | 川沿いの地名と砂金への言及 | 未着手 |
| 5万分の1 地質図幅の説明書（大樹町の範囲の5図幅と周辺4図幅） | 応用地質の節の砂金産地 | 読了。区間の記述は無い。神威岳図幅が中ノ川の砂金とたまりやすい場所に触れる（`notes/geology-map-explanations.md`） |
| ライマンのフィールドブック（マサチューセッツ大学アマースト校の図書館） | アイボシマの位置の略図 | 未着手 |
| 地質調査所『日本鉱産誌』の金の巻 | 砂金産地の一覧 | 未着手 |
| 昔の砂鉱区（官報、鉱業原簿） | 採掘権の範囲 | 未着手 |
| 旧版地形図（明治30年代以降） | 採金の小屋、「砂金」の付く沢の名前 | 未着手 |
| 昔の空中写真と陰影起伏図 | 函館商人の導水溝の跡 | 1961〜69年、1974〜78年の写真と陰影起伏図で段丘を見た。溝は見つからず、段丘の上に旧流路の跡（`notes/coastal-terrace-imagery.md`）。ビューワの背景にも入れた |
| 『大樹町史』、尾田砂金堀友の会 | 地元が伝える採取地 | 図書館、聞き取り |

## 実際に掘る前に

砂金は鉱業法上の鉱物で、歴舟川は北海道が管理する川。
体験の範囲の手掘りを超えて採る場合は、鉱業法と河川法上の扱いと、現在の鉱区の有無を先に確かめる。

## 出典

地形と背景は国土地理院の地理院タイル、川の線は国土交通省の国土数値情報（河川データ）を使っている。
個々の記録の出典は `sources/catalog.json` にある。
