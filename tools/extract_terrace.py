"""5万分の1地質図幅「上札内」の画像から、尾田面（Od）の範囲を色で切り出して経緯度の多角形にする。

使い方:
    python tools/extract_terrace.py

入力: sources/raw/hro/kushiro58_map.jpg（道総研の公開画像、SRC-039）
出力: 標準出力に GeoJSON の Polygon の座標

地図の枠（143°00'-15'E、42°30'-40'N）の四隅の画素位置は目で測った（notes/kamui-1950.md）。
画像の 1 画素は約 12.8 m。今の川の線と重ねたずれは 300 m 以内。
"""

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
TL, TR, BL, BR = (940, 223), (2547, 220), (938, 1671), (2548, 1670)
LON0, LAT0, DLON, DLAT = 143.0, 42 + 40 / 60, 0.25, 10 / 60


def px2ll(x, y):
    v = (y - (TL[1] + TR[1]) / 2) / ((BL[1] + BR[1]) / 2 - (TL[1] + TR[1]) / 2)
    xl = TL[0] + (BL[0] - TL[0]) * v
    xr = TR[0] + (BR[0] - TR[0]) * v
    u = (x - xl) / (xr - xl)
    return LON0 + DLON * u, LAT0 - DLAT * v


def ll2px(lon, lat):
    u = (lon - LON0) / DLON
    v = (LAT0 - lat) / DLAT
    xl = TL[0] + (BL[0] - TL[0]) * v
    xr = TR[0] + (BR[0] - TR[0]) * v
    yt = TL[1] + (TR[1] - TL[1]) * u
    yb = BL[1] + (BR[1] - BL[1]) * u
    return xl + (xr - xl) * u, yt + (yb - yt) * v


def main(lon_max=143.135, seed_box=(1650, 1080, 1740, 1160)):
    im = np.asarray(Image.open(ROOT / "sources/raw/hro/kushiro58_map.jpg").convert("RGB")).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    # 尾田面（Od）の色：赤みの強い黄色。拓北面（Th）は R-B が 60 前後で区別できる
    mask = ((r - b > 85) & (r - g > 10) & (r > 170)).astype(np.uint8) * 255
    mask = cv2.medianBlur(mask, 5)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    # 1950年の報告の範囲（合流点から東へ 5 km）で東を切る
    mask[:, int(ll2px(lon_max, 42.56)[0]):] = 0
    x0, y0, x1, y1 = seed_box  # 坂下の文字の周りの尾田面
    ys, xs = np.where(mask[y0:y1, x0:x1] > 0)
    seed = (x0 + xs[0], y0 + ys[0])
    _, lab = cv2.connectedComponents(mask)
    comp = (lab == lab[seed[1], seed[0]]).astype(np.uint8) * 255
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 2, True)
    ring = [[round(v, 6) for v in px2ll(int(p[0][0]), int(p[0][1]))] for p in c]
    ring.append(ring[0])
    print(json.dumps({"type": "Polygon", "coordinates": [ring]}))


if __name__ == "__main__":
    main()
