"""候補地点に、条件の重なり、林道までの距離、土地の区分を書き足して順位を付ける。

使い方:
    python tools/rank_candidates.py [taiki-core のパス]

順番: tools/find_candidates.py → tools/cross_strike.py → tools/build_claims.py → このスクリプト

入力:
- data/candidates.geojson、data/sites.geojson、data/reaches.geojson、data/claims.geojson
- taiki-core の国土数値情報 A45（国有林野、林道）と、北海道の道有林、民有林の森林簿の図形
出力:
- data/candidates.geojson に score、score_reasons、road_m、road_name、land、near_claim（1 km 以内の昔の鉱区）を書く
- data/forest_roads.geojson（ビューワ用、歴舟川の周りの林道）

条件（1つ1点）:
1. 勾配が急に緩む点と合流点の下流が 300 m 以内で重なる
2. 川が地層を横切る所（交わる角度 60度以上、伊木の条件3）
3. 砂金があると書かれた場所の近く：1950年の神威金鉱の区間、明治の許可の川筋のポロナイの沢の合流点、砂金の沢（1.5 km 以内）
4. 手が付けられなかった記録：ヌビナイ川（明治44年「未着手」、伊木 1912「流礫厚く堆積し稼行に便ならず」）
点数は目安で、砂金があることを示すものではない。
"""

import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
BBOX = (142.84, 42.38, 143.48, 42.62)


def km(a, b):
    return math.hypot((b[0] - a[0]) * math.cos(math.radians(a[1])) * 111.32, (b[1] - a[1]) * 110.57)


def to_m(lon, lat, lat0=42.5):
    return (lon * 111320 * math.cos(math.radians(lat0)), lat * 110570)


def main():
    core = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent / "taiki-core")
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))
    cands = load(ROOT / "data/candidates.geojson")
    sites = {f["properties"]["id"]: f for f in load(ROOT / "data/sites.geojson")["features"]}
    reaches = {f["properties"]["id"]: f for f in load(ROOT / "data/reaches.geojson")["features"]}
    claims = load(ROOT / "data/claims.geojson")["features"]

    # 林道（ビューワ用に切り出して保存）
    a45 = load(core / "geometry/external/A45-2024_taiki.geojson")["features"]
    w, s, e, n = BBOX
    roads = []
    for f in a45:
        if "ForestRoad" not in f["properties"]["source_layer"]:
            continue
        c = f["geometry"]["coordinates"]
        if all(not (w <= x <= e and s <= y <= n) for x, y in c):
            continue
        roads.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[round(x, 6), round(y, 6)] for x, y in c]},
                      "properties": {"name": f["properties"].get("A45_055") or "名称不明", "kind": "国有林の林道"}})
    (ROOT / "data/forest_roads.geojson").write_text(json.dumps({
        "type": "FeatureCollection", "_note": "tools/rank_candidates.py が作る。国土数値情報 国有林野（A45、2024年）の林道。", "features": roads},
        ensure_ascii=False), encoding="utf-8")
    road_lines = [LineString([to_m(x, y) for x, y in r["geometry"]["coordinates"]]) for r in roads]
    road_tree = STRtree(road_lines)

    # 土地の区分
    def polys(features):
        out = []
        for f in features:
            try:
                out.append((shape(f["geometry"]), f["properties"]))
            except Exception:
                pass
        return out
    national = polys([f for f in a45 if "SectionofUnit" in f["properties"]["source_layer"]])
    doyu = polys(load(core / "geometry/external/forest_doyu_taiki.geojson")["features"])
    minyu = polys(load(core / "geometry/external/forest_minyu_taiki.geojson")["features"])
    trees = [(label, STRtree([g for g, _ in ps]), ps) for label, ps in (("国有林", national), ("道有林", doyu), ("民有林", minyu))]
    claim_polys = [(shape(c["geometry"]), c["properties"]) for c in claims]

    def land_of(pt):
        for label, tree, ps in trees:
            for i in tree.query(pt):
                g, p = ps[i]
                if g.contains(pt):
                    if label == "国有林":
                        return f"国有林（{p.get('A45_009') or ''}森林計画区、{p.get('A45_015') or ''}）".replace("（森林計画区、）", "")
                    return label
        return "森林簿の範囲外（農地、河川敷など）"

    kamui = reaches["RC-005"]["geometry"]["coordinates"]
    pankepo_mouth = reaches["RC-007"]["geometry"]["coordinates"]
    sawa = sites["GS-010"]["geometry"]["coordinates"]
    sawa_pts = [q for poly in sawa for ring in poly for q in ring]

    feats = cands["features"]
    for f in feats:
        p = f["properties"]
        c = f["geometry"]["coordinates"]
        reasons = []
        other = [g for g in feats if g["properties"]["kind"] != p["kind"] and g["properties"]["river"] == p["river"]]
        if any(km(c, g["geometry"]["coordinates"]) <= 0.3 for g in other):
            reasons.append("勾配の変わり目と合流点の下流が重なる")
        if p.get("cross_angle", 0) >= 60:
            reasons.append(f"川が地層を横切る（約{p['cross_angle']}度）")
        near = []
        if min(km(c, q) for q in kamui) < 0.4:
            near.append("1950年の神威金鉱の区間")
        if any(km(c, q) < 0.5 for line in pankepo_mouth for q in line[-3:]):
            near.append("明治39年の許可のパンケホロナイ川の合流点")
        if min(km(c, q) for q in sawa_pts) < 1.5:
            near.append("砂金の沢")
        if near:
            reasons.append("砂金の記録の近く（" + "、".join(near) + "）")
        if p["river"] == "ヌビナイ川":
            reasons.append("手が付けられなかった記録（ヌビナイ川、明治44年「未着手」）")
        p["score"] = len(reasons)
        p["score_reasons"] = reasons
        pm = Point(to_m(*c))
        i = road_tree.nearest(pm)
        p["road_m"] = round(road_lines[i].distance(pm) / 10) * 10
        p["road_name"] = roads[i]["properties"]["name"]
        pt = Point(c)
        p["land"] = land_of(pt)
        near_claims = []
        for g, cp in claim_polys:
            d = Point(to_m(*c)).distance(shape({"type": "Polygon", "coordinates": [[to_m(x, y) for x, y in g.exterior.coords]]}))
            if d <= 1000:
                near_claims.append(f"{cp['name']}（{cp['set_year']}年設定）から {round(d / 10) * 10} m")
        p.pop("in_claim", None)
        p["near_claim"] = "、".join(near_claims) if near_claims else None

    feats.sort(key=lambda f: (-f["properties"]["score"], f["properties"]["road_m"]))
    for rank, f in enumerate(feats, 1):
        f["properties"]["rank"] = rank
    (ROOT / "data/candidates.geojson").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in feats[:20]:
        p = f["properties"]
        print(p["rank"], p["id"], p["score"], p["name"], "|", "；".join(p["score_reasons"]), "| 林道", p["road_m"], "m", p["road_name"], "|", p["land"], "|", p["near_claim"] or "")


if __name__ == "__main__":
    main()
