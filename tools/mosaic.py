"""地理院タイルを範囲で切り出して 1 枚の画像につなぐ。

使い方:
    python tools/mosaic.py <レイヤ> <拡張子> <ズーム> <西> <南> <東> <北> <出力>

例（歴舟川とアイボシマ川の間の段丘、1961〜69年の写真）:
    python tools/mosaic.py ort_old10 png 16 143.398 42.444 143.440 42.482 sources/raw/gsi/terrace_1960s_z16.jpg

主なレイヤ: seamlessphoto(jpg) / ort_old10(png, 1961〜69年) / gazo1(jpg, 1974〜78年) / hillshademap(png, 陰影起伏図)
出典: 国土地理院 地理院タイル（SRC-013）
"""

import io
import math
import sys
import urllib.request
from pathlib import Path

from PIL import Image


def tile_xy(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def main():
    layer, ext, z = sys.argv[1], sys.argv[2], int(sys.argv[3])
    w, s, e, n = map(float, sys.argv[4:8])
    out = Path(sys.argv[8])
    x0, y0 = tile_xy(w, n, z)
    x1, y1 = tile_xy(e, s, z)
    xs = range(int(x0), int(x1) + 1)
    ys = range(int(y0), int(y1) + 1)
    im = Image.new("RGB", (256 * len(xs), 256 * len(ys)), (200, 200, 200))
    missing = 0
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            url = f"https://cyberjapandata.gsi.go.jp/xyz/{layer}/{z}/{x}/{y}.{ext}"
            try:
                data = urllib.request.urlopen(url, timeout=30).read()
                im.paste(Image.open(io.BytesIO(data)).convert("RGB"), (256 * i, 256 * j))
            except Exception:
                missing += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=88)
    # 画像の左上と右下のタイル境界の経緯度（画像を地図に重ねるときに使う）
    def lonlat(x, y):
        lon = x / 2 ** z * 360 - 180
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))
        return round(lon, 6), round(lat, 6)
    print(out, im.size, f"tiles={len(xs) * len(ys)} missing={missing}",
          "NW", lonlat(xs[0], ys[0]), "SE", lonlat(xs[-1] + 1, ys[-1] + 1))


if __name__ == "__main__":
    main()
