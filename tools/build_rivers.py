"""taiki-core の国土数値情報 W05（河川）から、砂金の記録がある水系の線を切り出す。

使い方:
    python tools/build_rivers.py [taiki-core のパス]

出力: data/rivers.geojson（線のみ。名前の文字化け cp932 を直す）
"""

import json
import sys
from pathlib import Path

# 水系コード（W05_001）
SYSTEMS = {
    "010051": "歴舟川水系",
    "010050": "当縁川水系",
    "010052": "紋別川水系",
    "010588": "アイホシマ川水系",
}


def fix(s):
    if not s:
        return None
    try:
        return s.encode("latin1").decode("cp932")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def main():
    core = Path(sys.argv[1] if len(sys.argv) > 1 else "../taiki-core")
    src = core / "geometry/external/W05_taiki.geojson"
    d = json.loads(src.read_text(encoding="utf-8"))
    out = []
    for f in d["features"]:
        p = f["properties"]
        if f["geometry"]["type"] != "LineString" or p["W05_001"] not in SYSTEMS:
            continue
        name = fix(p["W05_004"])
        # 小数 6 桁（約 0.1 m）に丸める。原本の精度はこれより粗い
        coords = [[round(x, 6), round(y, 6)] for x, y in f["geometry"]["coordinates"]]
        out.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "name": None if name in (None, "名称不明") else name,
                "system": SYSTEMS[p["W05_001"]],
                "river_code": p["W05_002"],
            },
        })
    fc = {
        "type": "FeatureCollection",
        "source": "SRC-011",
        "features": out,
    }
    dst = Path(__file__).resolve().parent.parent / "data/rivers.geojson"
    dst.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"{len(out)} 本 → {dst}")


if __name__ == "__main__":
    main()
