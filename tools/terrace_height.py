"""段丘の比高（今の川底からの高さ）を標高データから出す。

使い方:
    python tools/terrace_height.py

対象: data/sites.geojson の GS-006（神威金鉱の最上位段丘＝尾田面の西部）
川底: 歴舟川本流の縦断面（tools/find_candidates.py と同じ作り方。半径60 m の最小値をならしたもの）
標高: 地理院 dem_png z14（約10 m）。段丘の中は 30 m 間隔でその画素の値を読む
出力: data/terrace_heights.json（本流の河口からの距離 0.5 km ごとの段丘面と川底の標高、比高の統計）
"""

import json
import math
from pathlib import Path

import numpy as np

import find_candidates as fc

ROOT = Path(__file__).resolve().parent.parent


def elev_at(lon, lat):
    px, py = fc.world_px(lon, lat)
    X, Y = int(px), int(py)
    return fc.tile(X // 256, Y // 256)[Y % 256, X % 256]


def inside(pt, ring):
    x, y = pt
    c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def main(site_id="GS-006"):
    rivers = json.loads((ROOT / "data/rivers.geojson").read_text(encoding="utf-8"))
    segs = [f["geometry"]["coordinates"] for f in rivers["features"] if f["properties"]["name"] == "歴舟川"]
    pts = fc.resample(fc.chain(segs), fc.STEP_KM)
    z = np.array([fc.elev_min(p[0], p[1]) for p in pts])
    for i in range(1, len(z)):
        if np.isnan(z[i]):
            z[i] = z[i - 1]
        z[i] = max(z[i], z[i - 1])

    site = [f for f in json.loads((ROOT / "data/sites.geojson").read_text(encoding="utf-8"))["features"]
            if f["properties"]["id"] == site_id][0]
    ring = site["geometry"]["coordinates"][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    dlat = 0.03 / 110.57
    dlon = 0.03 / (111.32 * math.cos(math.radians(sum(ys) / len(ys))))
    samples = []
    lat = min(ys)
    while lat <= max(ys):
        lon = min(xs)
        while lon <= max(xs):
            if inside((lon, lat), ring):
                e = elev_at(lon, lat)
                if not np.isnan(e):
                    j = min(range(len(pts)), key=lambda k: fc.km(pts[k], (lon, lat)))
                    samples.append({"lon": lon, "lat": lat, "elev": float(e), "river_km": pts[j][2],
                                    "bed": float(z[j]), "rel": float(e - z[j]), "dist_to_river_km": fc.km(pts[j], (lon, lat))})
            lon += dlon
        lat += dlat

    rel = np.array([s["rel"] for s in samples])
    bins = {}
    for s in samples:
        b = round(math.floor(s["river_km"] / 0.5) * 0.5, 1)
        bins.setdefault(b, []).append(s)
    by_km = []
    for b in sorted(bins):
        ss = bins[b]
        by_km.append({
            "river_km_from": b, "river_km_to": round(b + 0.5, 1), "n": len(ss),
            "terrace_elev_m": {"p10": round(float(np.percentile([s["elev"] for s in ss], 10)), 1),
                               "median": round(float(np.median([s["elev"] for s in ss])), 1),
                               "p90": round(float(np.percentile([s["elev"] for s in ss], 90)), 1)},
            "bed_elev_m": round(float(np.median([s["bed"] for s in ss])), 1),
            "relative_height_m_median": round(float(np.median([s["rel"] for s in ss])), 1),
        })
    out = {
        "_note": "tools/terrace_height.py が作る。比高＝段丘の中の点の標高 − 一番近い本流の谷底の標高。標高は地理院 dem_png z14（約10 m）。",
        "site": site_id,
        "n_samples": len(samples),
        "relative_height_m": {"p10": round(float(np.percentile(rel, 10)), 1), "median": round(float(np.median(rel)), 1),
                              "p90": round(float(np.percentile(rel, 90)), 1)},
        "distance_to_river_m_median": round(float(np.median([s["dist_to_river_km"] for s in samples])) * 1000),
        "by_river_km": by_km,
    }
    (ROOT / "data/terrace_heights.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "by_river_km"}, ensure_ascii=False))
    for b in by_km:
        print(b["river_km_from"], b["n"], b["terrace_elev_m"]["median"], b["bed_elev_m"], b["relative_height_m_median"])


if __name__ == "__main__":
    main()
