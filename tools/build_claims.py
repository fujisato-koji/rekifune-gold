"""国土数値情報 C22（鉱区、調査時点 1991年3月）から、歴舟川の周りの鉱区を切り出す。

使い方:
    python tools/build_claims.py

入力: sources/raw/ksj/C22-59L-48-01.0a_GML.zip（世界測地系のシェープファイル）
出力: data/claims.geojson
"""

import json
import zipfile
from io import BytesIO
from pathlib import Path

import shapefile

ROOT = Path(__file__).resolve().parent.parent
BBOX = (142.84, 42.38, 143.48, 42.62)
KIND = {"1": "試掘権", "2": "採掘権", "3": "鉱区禁止区域", "9": "不明"}


def main():
    z = zipfile.ZipFile(ROOT / "sources/raw/ksj/C22-59L-48-01.0a_GML.zip")
    r = shapefile.Reader(shp=BytesIO(z.read("C22-59L-2K_MineLot.shp")), dbf=BytesIO(z.read("C22-59L-2K_MineLot.dbf")),
                         shx=BytesIO(z.read("C22-59L-2K_MineLot.shx")), encoding="cp932")
    w, s, e, n = BBOX
    feats = []
    for sr in r.iterShapeRecords():
        x0, y0, x1, y1 = sr.shape.bbox
        if x1 < w or x0 > e or y1 < s or y0 > n:
            continue
        rec = list(sr.record)
        pts = [[round(x, 6), round(y, 6)] for x, y in sr.shape.points]
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        kind = KIND.get(str(rec[3]), str(rec[3]))
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [pts]},
            "properties": {
                "id": f"KC-{rec[2]}",
                "name": f"{kind}（{rec[5]}）北海道 登録第{rec[2]}号",
                "kind": kind, "mineral": rec[5], "reg_no": rec[2], "set_year": rec[6],
                "area_ha": rec[7], "surveyed": rec[8], "area_code": rec[1],
                "sources": ["SRC-054"],
            },
        })
    (ROOT / "data/claims.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "_note": "tools/build_claims.py が作る。国土数値情報 鉱区（C22、昭和59年版、調査時点 1991年3月）。今の鉱区ではない。",
        "features": feats}, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in feats:
        print(f["properties"])


if __name__ == "__main__":
    main()
