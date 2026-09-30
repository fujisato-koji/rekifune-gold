"""川が地層の走向を横切る角度を出す（伊木 1913 の条件3「横谷」）。

使い方:
    python tools/cross_strike.py

入力:
- data/strike_domains.json：地質図から区域ごとに読み取った走向
- data/rivers.geojson、地理院 dem_png（tools/find_candidates.py と同じ川の経路）
出力:
- data/strike.json：川ごと、河口からの距離 0.1 km ごとの流向、走向、交わる角度
- data/cross_reaches.geojson：交わる角度が 60 度以上の所が 1 km 以上続く区間
- data/candidates.geojson の各候補に cross_angle と strike_domain を書き足す

流向は、前後 0.5 km の経路の向き（下流向き）。国土数値情報の川の線は実際の流れから数百 m ずれるが、向きへの影響は小さい。

最初は地質図の画像から走向を自動で出そうとした（色の境の向きを構造テンソルで求める）。
しかし断層、段丘の縁、沖積層の帯、図幅の境の向きを拾ってしまい、ヌビナイ川の中流では地図と逆の結果になったので採らなかった（notes/placer-model.md）。
"""

import json
import math
from pathlib import Path

import find_candidates as fc

ROOT = Path(__file__).resolve().parent.parent
HALF_KM = 0.5
CROSS_MIN = 60
RUN_MIN_KM = 1.0


def flow_az(pts, i):
    k = int(round(HALF_KM / fc.STEP_KM))
    a = pts[max(0, i - k)]           # 下流側
    b = pts[min(len(pts) - 1, i + k)]  # 上流側
    east = (a[0] - b[0]) * 111.32 * math.cos(math.radians(a[1]))
    north = (a[1] - b[1]) * 110.57
    return math.degrees(math.atan2(east, north)) % 360


def cross(flow, strike):
    return abs(((flow % 180) - strike + 90) % 180 - 90)


def main():
    doms = json.loads((ROOT / "data/strike_domains.json").read_text(encoding="utf-8"))["domains"]

    def domain(lon, lat):
        for d in doms:
            w, s, e, n = d["bbox"]
            if w <= lon < e and s <= lat < n:
                return d
        return None

    rivers = json.loads((ROOT / "data/rivers.geojson").read_text(encoding="utf-8"))
    out, runs = {}, []
    for name in fc.TARGETS:
        segs = [f["geometry"]["coordinates"] for f in rivers["features"] if f["properties"]["name"] == name]
        pts = fc.resample(fc.chain(segs), fc.STEP_KM)
        rows = []
        for i, (lon, lat, dist) in enumerate(pts):
            d = domain(lon, lat)
            fa = flow_az(pts, i)
            if d is None:
                rows.append({"d": round(dist, 1), "flow": round(fa)})
                continue
            rows.append({"d": round(dist, 1), "flow": round(fa), "domain": d["id"], "strike": d["strike"],
                         "cross": round(cross(fa, d["strike"])), "conf": d["confidence"]})
        out[name] = rows
        # 60 度以上が続く区間
        cur = []
        for (lon, lat, dist), r in zip(pts, rows):
            if r.get("cross") is not None and r["cross"] >= CROSS_MIN:
                cur.append((lon, lat, dist, r))
                continue
            if cur and cur[-1][2] - cur[0][2] >= RUN_MIN_KM:
                runs.append((name, cur))
            cur = []
        if cur and cur[-1][2] - cur[0][2] >= RUN_MIN_KM:
            runs.append((name, cur))

    (ROOT / "data/strike.json").write_text(json.dumps({
        "_note": "tools/cross_strike.py が作る。d は河口からの距離 km、flow は流向（下流向き、北から東回り、度）、strike は区域の走向、cross は交わる角度（0〜90度）。",
        "rivers": out}, ensure_ascii=False), encoding="utf-8")

    feats = []
    for i, (name, cur) in enumerate(runs, 1):
        doms_here = sorted({c[3]["domain"] for c in cur})
        confs = {c[3]["conf"] for c in cur}
        crosses = [c[3]["cross"] for c in cur]
        a, b = cur[0][2], cur[-1][2]
        feats.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[round(c[0], 6), round(c[1], 6)] for c in cur]},
            "properties": {
                "id": f"XS-{i:03d}",
                "name": f"{name} 河口から {a:.1f}〜{b:.1f} km：地層を横切る区間",
                "river": name,
                "from_km": round(a, 1), "to_km": round(b, 1),
                "cross_median": round(sorted(crosses)[len(crosses) // 2]),
                "domains": "、".join(doms_here),
                "confidence": "低" if "低" in confs else ("中" if "中" in confs else "高"),
            },
        })
    (ROOT / "data/cross_reaches.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "_note": "tools/cross_strike.py が作る。川が地層の走向と 60 度以上で交わる所が 1 km 以上続く区間（伊木 1913 の条件3「横谷」）。",
        "features": feats}, ensure_ascii=False), encoding="utf-8")

    cp = ROOT / "data/candidates.geojson"
    cands = json.loads(cp.read_text(encoding="utf-8"))
    for f in cands["features"]:
        p = f["properties"]
        rows = [r for r in out[p["river"]] if abs(r["d"] - p["dist_km"]) < 0.05 and r.get("cross") is not None]
        for k in ("cross_angle", "strike_deg", "strike_domain", "strike_conf"):
            p.pop(k, None)
        if rows:
            r = rows[0]
            p["cross_angle"] = r["cross"]
            p["strike_deg"] = r["strike"]
            p["strike_domain"] = r["domain"]
            p["strike_conf"] = r["conf"]
    cp.write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")

    for f in feats:
        p = f["properties"]
        print(p["id"], p["name"], "交わる角度の中央値", p["cross_median"], "区域", p["domains"], "確かさ", p["confidence"])
    n60 = [f["properties"]["id"] for f in cands["features"] if f["properties"].get("cross_angle", 0) >= CROSS_MIN]
    print("60度以上の候補:", ", ".join(n60))


if __name__ == "__main__":
    main()
