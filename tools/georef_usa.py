"""国土地理院の地図・空中写真閲覧サービスの米軍写真（1947〜48年）を、地図に重ねられるように位置合わせする。

使い方:
    python tools/georef_usa.py

写真:
- 地図・空中写真閲覧サービス（https://service.gsi.go.jp/map-photos/app/）の標準画像（standard）を使う。
  ダウンロードできる空中写真は、出典を明記すれば申請なしで使える（サービスの注意事項）。ログインが要る最高画質は使わない。
- 検索 API（/map-photos/app/api/photo）の結果に、写真の四隅のおおよその経緯度（geom_image_*_pos）がある。

位置合わせ:
1. 写真の黒い縁を除いた写真の範囲を、検索結果の四隅の中心と大きさに合わせ、向き（飛行の向きで写真ごとに違う）は1960年代の写真とのエッジの相関が最大になる角度を探して決める。
2. 1961〜69年の地理院の写真（ort_old10）を基準に、画像の相関（OpenCV の ECC、射影変換）でずれを直す。
3. Web メルカトルの北が上の格子に写真を描き直し、縁の外を透明にした WebP を書く。
限界: 1枚の写真を射影変換で合わせるだけなので、山の起伏による写真のゆがみは直せない。平らな段丘や谷の底では数十 m、山地では100 m 以上ずれることがある。

出力:
- data/usa/<写真番号>.webp と data/usa/photos.json（範囲、撮影日、縮尺、合わせ込みの相関）
- 原本は sources/raw/gsi/usa/（git 管理外）
"""

import io
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "sources/raw/gsi/usa"
OUT = ROOT / "data/usa"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept": "application/json"}
API = "https://service.gsi.go.jp/map-photos/app/api"
IMG = "https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/"

# 使う写真：specification_id、出力のズーム、見たい場所
# 向き（度）は写真の上が向く方位。写真を見て確かめた値（USA-M392-70 はアイホシマ川と歴舟川の河口の並びから約39度）
# refine=True は画像の相関（ECC）で合わせ込む。False は四隅の中心と大きさ、確かめた向きだけで置く
# （山地や季節の違いで相関がとれない写真。置いた位置は川の河口や川の線で確かめる）
PHOTOS = [
    (180514, 15, "神威金鉱の段丘と尾田", 0, True),
    (1184547, 16, "歴舟川の河口とアイボシマの間の段丘", 39, False),
    (159999, 15, "ヌビナイ川の中流", 0, False),
    (180522, 15, "生花とオイカマナイトー", 0, True),
]
REFS = [("ort_old10", "png", "1961〜69年の写真"), ("seamlessphoto", "jpg", "今の写真"), ("hillshademap", "png", "陰影起伏図")]


def get_json(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))


def spec(sid, w, s, e, n):
    q = dict(search="photo", search_date_from="1945", search_date_to="1950", lon_min=w, lon_max=e, lat_min=s, lat_max=n,
             color_type_ids="1,2", scale_from=0, scale_to=99999999)
    for r in get_json(API + "/photo?" + urllib.parse.urlencode(q))["results"]:
        if r["specification_id"] == sid:
            return r
    raise SystemExit(f"not found {sid}")


def world(lon, lat, z):
    n = 2 ** z * 256
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def lonlat(x, y, z):
    n = 2 ** z * 256
    return x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def tile(layer, ext, z, x, y):
    try:
        data = urllib.request.urlopen(f"https://cyberjapandata.gsi.go.jp/xyz/{layer}/{z}/{x}/{y}.{ext}", timeout=30).read()
        return np.asarray(Image.open(io.BytesIO(data)).convert("L"))
    except Exception:
        return None


def reference(x0, y0, x1, y1, z, layer="ort_old10", ext="png"):
    """基準の画像を、世界画素 x0..x1, y0..y1 の範囲で作る（タイルが無いところは valid=0）。"""
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    W, H = (tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256
    ref = np.zeros((H, W), np.uint8)
    valid = np.zeros((H, W), np.uint8)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            a = tile(layer, ext, min(z, 16) if layer == "hillshademap" else z, tx, ty)
            if a is None:
                continue
            ref[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = a
            valid[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = 255
    ox, oy = tx0 * 256, ty0 * 256
    c = (int(x0 - ox), int(y0 - oy), int(x1 - ox), int(y1 - oy))
    return ref[c[1]:c[3], c[0]:c[2]], valid[c[1]:c[3], c[0]:c[2]]


def frame(img):
    """写真の黒い縁の内側（写真の範囲）の四隅を返す。"""
    g = cv2.GaussianBlur(img, (0, 0), 5)
    cols = (g > 35).mean(0)
    rows = (g > 35).mean(1)
    xs = np.where(cols > 0.6)[0]
    ys = np.where(rows > 0.6)[0]
    l, r, t, b = xs[0], xs[-1], ys[0], ys[-1]
    return np.float32([[l, t], [r, t], [r, b], [l, b]])


def edges(a):
    a = cv2.GaussianBlur(a, (0, 0), 1.5).astype(np.float32)
    gx = cv2.Sobel(a, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(a, cv2.CV_32F, 0, 1)
    return cv2.magnitude(gx, gy)


def orient(img, src, dst, ref, valid, step=3, hint=None, fixed=False):
    """写真の向きを探す。写真の範囲の中心と大きさは四隅の経緯度に合わせ、回す角度だけを変えて、
    基準（1960年代の写真）とのエッジの相関が一番大きい向きを選ぶ。粗く（約20 m/画素）探してから細かく探す。"""
    c_src = src.mean(0)
    c_dst = dst.mean(0)
    scale = math.sqrt(cv2.contourArea(dst) / cv2.contourArea(src))
    k = 0.15  # 基準の格子を縮める
    rsmall = edges(cv2.resize(ref, None, fx=k, fy=k, interpolation=cv2.INTER_AREA))
    vsmall = cv2.resize(valid, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST) > 0
    size = (rsmall.shape[1], rsmall.shape[0])
    fr = np.zeros(img.shape, np.uint8)
    l, t = src[0]
    r, b = src[2]
    fr[int(t) + 30:int(b) - 30, int(l) + 30:int(r) - 30] = 255

    def sim(theta):
        a = math.radians(theta)
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]]) * scale
        A = np.eye(3)
        A[:2, :2] = R
        A[:2, 2] = c_dst - R @ c_src
        return A

    def score(theta):
        A = np.diag([k, k, 1]) @ sim(theta)
        w = edges(cv2.warpPerspective(img, A, size))
        m = (cv2.warpPerspective(fr, A, size) > 0) & vsmall
        if m.sum() < 1000:
            return -1
        x, y = w[m], rsmall[m]
        x = (x - x.mean()) / (x.std() + 1e-6)
        y = (y - y.mean()) / (y.std() + 1e-6)
        return float((x * y).mean())

    if hint is not None and fixed:
        return sim(hint), hint, score(hint)
    if hint is not None:
        best = max([hint + d * 0.5 for d in range(-10, 11)], key=score)
        return sim(best), best, score(best)
    coarse = max(range(0, 360, step), key=score)
    best = max([coarse + d * 0.5 for d in range(-6, 7)], key=score)
    return sim(best), best, score(best)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = []
    for sid, z, place, hint, refine in PHOTOS:
        cand = json.loads((ROOT / "sources/raw/gsi/usa/usa_candidates.json").read_text(encoding="utf-8"))
        r = cand[str(sid)]
        name = f"USA-{r['course_number']}-{r['photo_number']}"
        f = RAW / f"{name}_standard.jpg"
        if not f.exists():
            u = get_json(f"{API}/urls/{sid}/standard")["results"]["url_image"]
            data = urllib.request.urlopen(urllib.request.Request(IMG + urllib.parse.quote(u), headers=UA), timeout=120).read()
            f.write_bytes(data)
        img = np.asarray(Image.open(f).convert("L"))
        src = frame(img)
        corners = [r["geom_image_left_top_pos"], r["geom_image_right_top_pos"], r["geom_image_right_bottom_pos"], r["geom_image_left_bottom_pos"]]
        wpts = np.float32([world(lo, la, z) for lo, la in corners])
        margin = 400 / (156543.03 * math.cos(math.radians(42.5)) / 2 ** z)  # 400 m
        x0, y0 = wpts[:, 0].min() - margin, wpts[:, 1].min() - margin
        x1, y1 = wpts[:, 0].max() + margin, wpts[:, 1].max() + margin
        refs = {name_: reference(x0, y0, x1, y1, z, lay, ext) for lay, ext, name_ in REFS}
        H0, rot, score = orient(img, src, wpts - np.float32([x0, y0]), *refs["1961〜69年の写真"], hint=hint, fixed=not refine)
        size = (refs["1961〜69年の写真"][0].shape[1], refs["1961〜69年の写真"][0].shape[0])
        warped = cv2.warpPerspective(img, H0, size)
        inside = cv2.warpPerspective(np.full(img.shape, 255, np.uint8), H0, size)
        inside = cv2.erode(inside, np.ones((25, 25), np.uint8))

        def prep(a, k):
            a = cv2.resize(a, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            a = cv2.createCLAHE(2.0, (8, 8)).apply(a)
            return cv2.GaussianBlur(a, (0, 0), 2).astype(np.float32) / 255

        best = (None, np.eye(3), None)
        for refname, (ref, valid) in (refs.items() if refine else []):
            if (valid > 0).mean() < 0.3:
                continue
            Wcur = np.eye(3)
            cc = None
            ok = True
            for k in (0.125, 0.25, 0.5):  # 粗い解像度から段階的に合わせ込む
                S = np.diag([k, k, 1.0])
                Wk = (S @ Wcur @ np.linalg.inv(S)).astype(np.float32)
                mask = cv2.resize(((valid > 0) & (inside > 0)).astype(np.uint8) * 255, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)
                try:
                    cc, Wk = cv2.findTransformECC(prep(ref, k), prep(warped, k), Wk, cv2.MOTION_HOMOGRAPHY,
                                                  (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), mask, 3)
                except cv2.error:
                    ok = False
                    break
                Wcur = np.linalg.inv(S) @ Wk.astype(np.float64) @ S
            # 大きく動きすぎた解は採らない（中心で1.5 km 以上）
            p = Wcur @ np.array([size[0] / 2, size[1] / 2, 1.0])
            moved = math.hypot(p[0] / p[2] - size[0] / 2, p[1] / p[2] - size[1] / 2) * 156543.03 * math.cos(math.radians(42.5)) / 2 ** z
            print(f"  {name} 基準 {refname}：ECC {None if cc is None else round(float(cc), 3)}、動いた量 {moved:.0f} m、{'収束' if ok else '失敗'}")
            if ok and cc is not None and moved < 1500 and (best[0] is None or cc > best[0]):
                best = (float(cc), Wcur, refname)
        cc, Wfull, refused = best
        ref = refs["1961〜69年の写真"][0]
        # 基準の格子の画素 → 元の写真の画素
        M = np.linalg.inv(H0) @ Wfull
        # 合わせ込みで動いた量（写真の中心で）
        cx, cy = size[0] / 2, size[1] / 2
        p = Wfull @ np.array([cx, cy, 1.0])
        shift_px = math.hypot(p[0] / p[2] - cx, p[1] / p[2] - cy)
        mpp = 156543.03 * math.cos(math.radians(42.5)) / 2 ** z
        out = cv2.warpPerspective(img, M, size, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        alpha = cv2.warpPerspective(np.full(img.shape, 255, np.uint8), M, size, flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP)
        fr = np.zeros(img.shape, np.uint8)
        l, t = src[0]
        rr, b = src[2]
        fr[int(t) + 20:int(b) - 20, int(l) + 20:int(rr) - 20] = 255
        alpha = cv2.warpPerspective(fr, M, size, flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP)
        rgba = np.dstack([out, out, out, alpha])
        # 透明な外側を切り落とす
        ys, xs = np.where(alpha > 0)
        cx0, cy0, cx1, cy1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        rgba = rgba[cy0:cy1, cx0:cx1]
        wlo, wla = lonlat(x0 + cx0, y0 + cy0, z)
        elo, sla = lonlat(x0 + cx1, y0 + cy1, z)
        fn = OUT / f"{name}.webp"
        Image.fromarray(rgba, "RGBA").save(fn, "WEBP", quality=72, method=6)
        meta.append({
            "id": name, "specification_id": sid, "place": place, "date": r["search_date"], "scale": r["scale"],
            "file": f"data/usa/{name}.webp",
            "coordinates": [[round(wlo, 6), round(wla, 6)], [round(elo, 6), round(wla, 6)], [round(elo, 6), round(sla, 6)], [round(wlo, 6), round(sla, 6)]],
            "ecc": None if cc is None else round(float(cc), 3),
            "shift_m": round(shift_px * mpp),
            "rotation_deg": round(rot, 1),
            "matched_to": refused,
            "zoom": z,
            "source": "SRC-061",
        })
        print(name, "向き", round(rot, 1), "度、エッジの相関", round(score, 3))
        print(name, r["search_date"], "ECC", None if cc is None else round(float(cc), 3), "合わせ込みで動いた量 約", round(shift_px * mpp), "m", fn.stat().st_size // 1024, "KB", rgba.shape)
        # 確認用：基準との重ね合わせと、国土数値情報の川の線
        chk = np.dstack([ref, cv2.warpPerspective(img, M, size, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP), ref])
        rivers = json.loads((ROOT / "data/rivers.geojson").read_text(encoding="utf-8"))
        chk = np.ascontiguousarray(chk)
        for fe in rivers["features"]:
            pts = np.int32([[world(lo, la, z)[0] - x0, world(lo, la, z)[1] - y0] for lo, la in fe["geometry"]["coordinates"]])
            cv2.polylines(chk, [pts], False, (255, 255, 0), 3)
        Image.fromarray(chk).resize((size[0] // 3, size[1] // 3)).save(RAW / f"{name}_check.jpg", quality=85)
    (OUT / "photos.json").write_text(json.dumps({
        "_note": "tools/georef_usa.py が作る。1947〜48年の米軍撮影の空中写真（国土地理院 地図・空中写真閲覧サービス）を位置合わせしたもの。coordinates は MapLibre の image ソースの四隅（左上、右上、右下、左下）。",
        "photos": meta}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
