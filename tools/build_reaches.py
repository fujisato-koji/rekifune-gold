"""data/reach_records.json の定義から、区間の線 data/reaches.geojson を作る。

使い方:
    python tools/build_reaches.py

各記録の geometry_rule で線の作り方を決める。
- river: rivers.geojson の同名の川の線をすべて使う（lon_max があればそれより西の線だけ）
- along: 川を河口側から上流へたどった経路のうち、起点から from_km〜to_km の部分を切り出す
  （起点は start の座標に最も近い頂点。direction が downstream なら下流へ向かって切り出す）
- coast: 中心点から bearing の向きに、前後 half_km ずつの直線
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def km(a, b):
    return math.hypot((b[0] - a[0]) * math.cos(math.radians(a[1])) * 111.32, (b[1] - a[1]) * 110.57)


def chain(segs):
    """同じ川の線分をつないで、下流端から上流端への 1 本の経路にする（本流だけを想定）。"""
    starts = {tuple(s[0]): s for s in segs}
    ends = {tuple(s[-1]) for s in segs}
    # 下流端 = どの線分の始点にもなっていない終点
    mouth = next(e for e in ends if e not in starts)
    by_end = {tuple(s[-1]): s for s in segs}
    path = [list(mouth)]
    cur = mouth
    while cur in by_end:
        s = by_end.pop(cur)
        path += [list(p) for p in reversed(s[:-1])]
        cur = tuple(s[0])
    return path  # 下流 → 上流


def cut(path, i0, dist_from, dist_to, step):
    out, acc, i = [], 0.0, i0
    out_started = dist_from == 0
    if out_started:
        out.append(path[i])
    while 0 <= i + step < len(path):
        a, b = path[i], path[i + step]
        l = km(a, b)
        if not out_started and acc + l >= dist_from:
            t = (dist_from - acc) / l
            out.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
            out_started = True
        if out_started and acc + l >= dist_to:
            t = (dist_to - acc) / l
            out.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
            return out
        acc += l
        i += step
        if out_started:
            out.append(path[i])
    return out


def main():
    rivers = json.loads((ROOT / "data/rivers.geojson").read_text(encoding="utf-8"))
    recs = json.loads((ROOT / "data/reach_records.json").read_text(encoding="utf-8"))["records"]
    feats = []
    for r in recs:
        g = r["geometry_rule"]
        if g["type"] == "river":
            lines = [f["geometry"]["coordinates"] for f in rivers["features"]
                     if f["properties"]["name"] == g["name"]
                     and all(p[0] <= g.get("lon_max", 999) for p in f["geometry"]["coordinates"])]
            geom = {"type": "MultiLineString", "coordinates": lines}
        elif g["type"] == "along":
            segs = [f["geometry"]["coordinates"] for f in rivers["features"] if f["properties"]["name"] == g["name"]]
            path = chain(segs)
            i0 = min(range(len(path)), key=lambda i: km(path[i], g["start"]))
            step = 1 if g.get("direction") == "upstream" else -1
            geom = {"type": "LineString", "coordinates": cut(path, i0, g["from_km"], g["to_km"], step)}
        elif g["type"] == "coast":
            c, b, h = g["center"], math.radians(g["bearing"]), g["half_km"]
            dx = math.sin(b) * h / (111.32 * math.cos(math.radians(c[1])))
            dy = math.cos(b) * h / 110.57
            geom = {"type": "LineString", "coordinates": [[c[0] - dx, c[1] - dy], [c[0] + dx, c[1] + dy]]}
        else:
            raise ValueError(g["type"])
        if geom["type"] == "LineString":
            geom["coordinates"] = [[round(x, 6), round(y, 6)] for x, y in geom["coordinates"]]
        else:
            geom["coordinates"] = [[[round(x, 6), round(y, 6)] for x, y in l] for l in geom["coordinates"]]
        props = {k: v for k, v in r.items() if k != "geometry_rule"}
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    out = ROOT / "data/reaches.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    for f in feats:
        g = f["geometry"]
        n = len(g["coordinates"]) if g["type"] == "LineString" else sum(len(l) for l in g["coordinates"])
        print(f["properties"]["id"], g["type"], n)


if __name__ == "__main__":
    main()
