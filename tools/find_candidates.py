"""地形から、砂金がたまりやすい候補地点を拾う。

使い方:
    python tools/find_candidates.py

入力: data/rivers.geojson（国土数値情報の川の線）、地理院の標高タイル dem_png z14（約10 m、取得して sources/raw/gsi/dem14/ に置く）
出力: data/candidates.geojson

考え方（notes/placer-model.md）:
- 勾配が急に緩む点：上流 1 km の勾配が下流 1 km の勾配の 2 倍以上。峡谷の出口や扇状地の頭にあたる。
- 合流点：記録のある川に支流が入る点の 200 m 下流。
国土数値情報の川の線は実際の流れから数十〜数百 m ずれるので、各点の標高は半径 60 m 以内の最小値（谷底）をとる。
"""

import io
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
Z = 14
CACHE = ROOT / "sources/raw/gsi/dem14"
TARGETS = ["歴舟川", "歴舟中の川", "ヌビナイ川", "ポンヤオロヌップ川"]
LON_MAX = 143.19  # 尾田の合流点より上流（山地と峡谷の出口）を対象にする
STEP_KM = 0.1
WIN_KM = 1.0
RATIO = 2.0

_tiles = {}


def tile(x, y):
    if (x, y) in _tiles:
        return _tiles[(x, y)]
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{x}_{y}.png"
    if not f.exists():
        try:
            data = urllib.request.urlopen(f"https://cyberjapandata.gsi.go.jp/xyz/dem_png/{Z}/{x}/{y}.png", timeout=30).read()
        except Exception:
            data = b""
        f.write_bytes(data)
    data = f.read_bytes()
    if not data:
        arr = np.full((256, 256), np.nan)
    else:
        a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).astype(np.int64)
        v = a[..., 0] * 65536 + a[..., 1] * 256 + a[..., 2]
        arr = np.where(v < 2 ** 23, v * 0.01, np.where(v > 2 ** 23, (v - 2 ** 24) * 0.01, np.nan))
    _tiles[(x, y)] = arr
    return arr


def world_px(lon, lat):
    n = 2 ** Z * 256
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def elev_min(lon, lat, r_m=60):
    px, py = world_px(lon, lat)
    m_per_px = 156543.03 * math.cos(math.radians(lat)) / 2 ** Z
    r = max(1, int(round(r_m / m_per_px)))
    vals = []
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            X, Y = int(px) + dx, int(py) + dy
            v = tile(X // 256, Y // 256)[Y % 256, X % 256]
            if not np.isnan(v):
                vals.append(v)
    return min(vals) if vals else float("nan")


def km(a, b):
    return math.hypot((b[0] - a[0]) * math.cos(math.radians(a[1])) * 111.32, (b[1] - a[1]) * 110.57)


def chain(segs):
    """同じ名前の線分をつなぎ、下流端から一番長くたどれる経路を返す（本流）。"""
    starts = {}
    for s in segs:
        starts.setdefault(tuple(s[0]), []).append(s)
    by_end = {}
    for s in segs:
        by_end.setdefault(tuple(s[-1]), []).append(s)
    mouths = [e for e in by_end if e not in starts]
    best = []
    for m in mouths:
        path, cur = [list(m)], m
        while cur in by_end:
            s = max(by_end[cur], key=len)
            path += [list(p) for p in reversed(s[:-1])]
            cur = tuple(s[0])
        if len(path) > len(best):
            best = path
    return best  # 下流 → 上流


def resample(path, step):
    out, acc = [path[0] + [0.0]], 0.0
    carry = 0.0
    for a, b in zip(path, path[1:]):
        l = km(a, b)
        t = step - carry
        while t <= l:
            f = t / l
            out.append([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, acc + t])
            t += step
        carry = l - (t - step)
        acc += l
    return out


def main():
    rivers = json.loads((ROOT / "data/rivers.geojson").read_text(encoding="utf-8"))
    feats = []
    target_pts = {}
    profiles = {}
    for name in TARGETS:
        segs = [f["geometry"]["coordinates"] for f in rivers["features"] if f["properties"]["name"] == name]
        path = [p for p in chain(segs)]
        pts = resample(path, STEP_KM)
        z = np.array([elev_min(p[0], p[1]) for p in pts])
        # 下流に向かって標高が上がらないようにならす（窪地の誤差を消す）
        zs = z.copy()
        for i in range(1, len(zs)):
            if np.isnan(zs[i]):
                zs[i] = zs[i - 1]
            zs[i] = max(zs[i], zs[i - 1])
        target_pts[name] = pts
        profiles[name] = {
            "step_km": STEP_KM,
            "analysis_from_km": next((round(p[2], 1) for p in pts if p[0] <= LON_MAX), None),
            "elev_m": [None if np.isnan(v) else round(float(v), 1) for v in zs],
        }
        w = int(round(WIN_KM / STEP_KM))
        for i in range(w, len(pts) - w):
            lon, lat, d = pts[i]
            if lon > LON_MAX:
                continue
            down = (zs[i] - zs[i - w]) / (WIN_KM * 1000)
            up = (zs[i + w] - zs[i]) / (WIN_KM * 1000)
            if down <= 0.0005:
                down = 0.0005
            ratio = up / down
            if ratio >= RATIO and up >= 0.005 and down <= 0.03:  # 下流側が緩い（砂礫がたまる）所だけ
                feats.append({"lon": lon, "lat": lat, "river": name, "dist_km": d, "elev": float(zs[i]),
                              "up": up, "down": down, "ratio": ratio})
    # 近い点をまとめる（同じ川で 1 km 以内は比の大きい方だけ残す）
    feats.sort(key=lambda f: -f["ratio"])
    kept = []
    for f in feats:
        if all(not (g["river"] == f["river"] and abs(g["dist_km"] - f["dist_km"]) < 1.0) for g in kept):
            kept.append(f)

    out = []
    for i, f in enumerate(sorted(kept, key=lambda f: (f["river"], f["dist_km"])), 1):
        out.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(f["lon"], 5), round(f["lat"], 5)]},
            "properties": {
                "id": f"CP-{i:03d}",
                "kind": "勾配が急に緩む点",
                "name": f"{f['river']} 河口から {f['dist_km']:.1f} km：勾配の変わり目",
                "river": f["river"],
                "dist_km": round(f["dist_km"], 1),
                "elev_m": round(f["elev"]),
                "grad_up": f"{f['up'] * 1000:.0f}‰",
                "grad_down": f"{f['down'] * 1000:.0f}‰",
                "ratio": round(f["ratio"], 1),
            },
        })

    # 合流点：対象の川の線上に、別の名前の川の下流端が来る点
    n = len(out)
    for f in rivers["features"]:
        nm = f["properties"]["name"]
        c = f["geometry"]["coordinates"]
        end = c[-1]
        for tname, pts in target_pts.items():
            if nm == tname or end[0] > LON_MAX:
                continue
            j = min(range(len(pts)), key=lambda k: km(pts[k], end))
            if km(pts[j], end) > 0.05 or pts[j][2] < 0.3:
                continue  # 対象の川の河口そのもの（尾田の三川合流など）は除く
            k = max(0, j - int(round(0.2 / STEP_KM)))  # 200 m 下流
            n += 1
            out.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(pts[k][0], 5), round(pts[k][1], 5)]},
                "properties": {
                    "id": f"CP-{n:03d}",
                    "kind": "合流点の下流",
                    "name": f"{tname} 河口から {pts[k][2]:.1f} km：{nm or '名称不明の川'}の合流点の下流",
                    "river": tname,
                    "dist_km": round(pts[k][2], 1),
                    "tributary": nm or "名称不明",
                },
            })
    # 名前のある支流だけ残す（名称不明の小沢は数が多すぎるため）。同じ地点の重複も除く
    seen, uniq = set(), []
    for f in out:
        p = f["properties"]
        if p["kind"] == "合流点の下流" and p["tributary"] == "名称不明":
            continue
        key = (p["kind"], tuple(f["geometry"]["coordinates"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    out = uniq
    # 近くの記録との関係を書く
    reaches = json.loads((ROOT / "data/reaches.geojson").read_text(encoding="utf-8"))
    kamui = [f for f in reaches["features"] if f["properties"]["id"] == "RC-005"][0]["geometry"]["coordinates"]
    sites = json.loads((ROOT / "data/sites.geojson").read_text(encoding="utf-8"))
    sawa = [f for f in sites["features"] if f["properties"]["id"] == "GS-010"][0]
    sawa_pts = [q for poly in sawa["geometry"]["coordinates"] for ring in poly for q in ring]
    river_note = {
        "歴舟川": "明治のヤオロオマップ（主な採取地、RC-001）",
        "歴舟中の川": "明治のルーツルオマップ（主な採取地、RC-003）。1950年の報告が中川流域を有望とみる",
        "ヌビナイ川": "明治44年に「未タ着手セラレサルカ如シ」（RC-004）",
        "ポンヤオロヌップ川": "明治39年に許可（RC-002）",
    }
    for f in out:
        c = f["geometry"]["coordinates"]
        notes = [river_note[f["properties"]["river"]]]
        if min(km(c, q) for q in kamui) < 0.4:
            notes.append("1950年の神威金鉱の区間（峡谷が扇状地に出る所、RC-005）の中")
        if min(km(c, q) for q in sawa_pts) < 1.5:
            notes.append("砂金の沢（GS-010）から 1.5 km 以内")
        f["properties"]["context"] = "。".join(notes)
    for i, f in enumerate(out, 1):
        f["properties"]["id"] = f"CP-{i:03d}"
    fc = {"type": "FeatureCollection", "_note": "tools/find_candidates.py が作る。地形の一般則からの候補で、砂金があることを示すものではない。", "features": out}
    (ROOT / "data/profiles.json").write_text(json.dumps({
        "_note": "tools/find_candidates.py が作る。河口からの距離 0.1 km ごとの谷底の標高（半径60 m の最小値を、下流に向かって上がらないようにならしたもの）。",
        "rivers": profiles}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data/candidates.geojson").write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {}
    for f in out:
        kinds[f["properties"]["kind"]] = kinds.get(f["properties"]["kind"], 0) + 1
    print(kinds)
    for f in out:
        p = f["properties"]
        print(p["id"], p["name"], p.get("grad_up", ""), p.get("grad_down", ""), f["geometry"]["coordinates"])


if __name__ == "__main__":
    main()
