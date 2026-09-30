// 歴舟川 砂金地図: 地理院の標高タイルを地形にして、採取記録を重ねる。

const GSI = 'https://cyberjapandata.gsi.go.jp/xyz';
const CONF_COLOR = { '高': 'var(--hi)', '中': 'var(--mid)', '低': 'var(--lo)' };

// 地理院の標高 PNG（dem_png）を MapLibre が読める Terrarium 形式に変換する。
// dem_png: x = R*2^16 + G*2^8 + B、x < 2^23 なら h = x*0.01、x > 2^23 なら h = (x-2^24)*0.01、x = 2^23 は欠測。
// Terrarium: h = R*256 + G + B/256 - 32768
let flatTile = null;
async function makeFlatTile() {
  const c = new OffscreenCanvas(256, 256);
  const ctx = c.getContext('2d');
  ctx.fillStyle = 'rgb(128,0,0)';
  ctx.fillRect(0, 0, 256, 256);
  return (await c.convertToBlob({ type: 'image/png' })).arrayBuffer();
}

maplibregl.addProtocol('gsidem', async (params, abort) => {
  const url = params.url.replace('gsidem://', 'https://');
  const res = await fetch(url, { signal: abort.signal });
  if (!res.ok) {
    flatTile ??= await makeFlatTile();
    return { data: flatTile.slice(0) };
  }
  const bmp = await createImageBitmap(await res.blob());
  const c = new OffscreenCanvas(bmp.width, bmp.height);
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(bmp, 0, 0);
  const img = ctx.getImageData(0, 0, bmp.width, bmp.height);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const x = d[i] * 65536 + d[i + 1] * 256 + d[i + 2];
    let h = 0;
    if (x < 8388608) h = x * 0.01;
    else if (x > 8388608) h = (x - 16777216) * 0.01;
    const v = h + 32768;
    const r = Math.floor(v / 256);
    const g = Math.floor(v) - r * 256;
    d[i] = r;
    d[i + 1] = g;
    d[i + 2] = Math.floor((v - Math.floor(v)) * 256);
    d[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return { data: await (await c.convertToBlob({ type: 'image/png' })).arrayBuffer() };
});

const raster = (path, maxzoom, ext = 'png') => ({
  type: 'raster',
  tiles: [`${GSI}/${path}/{z}/{x}/{y}.${ext}`],
  tileSize: 256,
  maxzoom,
  attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a>',
});

const demSource = () => ({
  type: 'raster-dem',
  tiles: ['gsidem://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png'],
  tileSize: 256,
  maxzoom: 14,
  encoding: 'terrarium',
});

const map = new maplibregl.Map({
  container: 'map',
  center: [143.25, 42.50],
  zoom: 10.6,
  pitch: 60,
  bearing: -15,
  maxPitch: 85,
  style: {
    version: 8,
    sources: {
      photo: raster('seamlessphoto', 18, 'jpg'),
      std: raster('std', 18),
      pale: raster('pale', 18),
      // 昔の空中写真（大樹町で使えるのは 1961〜69年と 1974〜78年。1945〜50年の米軍写真のタイルは無い）
      old60: raster('ort_old10', 17),
      old70: raster('gazo1', 17, 'jpg'),
      relief: raster('hillshademap', 16),
      // 地形用と陰影用で source を分ける（同じ source を共有すると陰影が粗くなる）
      dem: demSource(),
      demShade: demSource(),
    },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': '#dfe8ee' } },
      { id: 'photo', type: 'raster', source: 'photo' },
      { id: 'std', type: 'raster', source: 'std', layout: { visibility: 'none' } },
      { id: 'pale', type: 'raster', source: 'pale', layout: { visibility: 'none' } },
      { id: 'old60', type: 'raster', source: 'old60', layout: { visibility: 'none' } },
      { id: 'old70', type: 'raster', source: 'old70', layout: { visibility: 'none' } },
      { id: 'relief', type: 'raster', source: 'relief', layout: { visibility: 'none' } },
      {
        id: 'hillshade', type: 'hillshade', source: 'demShade', layout: { visibility: 'none' },
        paint: { 'hillshade-exaggeration': 0.4, 'hillshade-shadow-color': '#473b24' },
      },
    ],
    terrain: { source: 'dem', exaggeration: 1.5 },
    sky: {},
  },
});
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
map.addControl(new maplibregl.TerrainControl({ source: 'dem', exaggeration: 1.5 }), 'bottom-right');

// ---- 画面の部品 ----

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let catalog = {};

function sourceList(ids) {
  return '<ol>' + (ids || []).map((id) => {
    const s = catalog[id];
    if (!s) return `<li>${esc(id)}</li>`;
    return `<li>${esc(id)} <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>（${esc(s.publisher)}、取得 ${esc(s.retrieved)}）</li>`;
  }).join('') + '</ol>';
}

function showDetail(title, rows, sources) {
  const el = document.getElementById('detail');
  el.innerHTML = `<button class="close" aria-label="閉じる">×</button><h3>${esc(title)}</h3><dl>` +
    rows.filter(([, v]) => v).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('') +
    `<dt>出典</dt><dd>${sourceList(sources)}</dd></dl>`;
  el.hidden = false;
  el.querySelector('.close').onclick = () => {
    el.hidden = true;
    clearHighlight();
    document.querySelectorAll('#panel li.sel').forEach((x) => x.classList.remove('sel'));
  };
}

function confKey(s) {
  return (s || '').trim().charAt(0);
}

function siteDetail(p) {
  showDetail(p.name, [
    ['地図', '水色で光っている所がこの場所'],
    ['種別', p.kind], ['時期', p.period], ['内容', p.summary], ['試掘の結果', p.result], ['1950年より後', p.after_1950], ['比高', p.relative_height], ['文献', p.literature],
    ['座標の決め方', p.position], ['位置の確かさ', p.position_confidence], ['記録の確かさ', p.record_confidence],
  ], p.sources);
}

// ---- データの読み込み ----

async function load(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// データは起動と同時に読み始め、スタイルの準備ができたら重ねる（'load' はタイルが揃うまで待つので遅い）
const dataReady = Promise.all([
  load('sources/catalog.json'), load('data/sites.geojson'), load('data/rivers.geojson'),
  load('data/river_records.json'), load('data/unplaced.json'), load('data/district_records.json'),
  load('data/reaches.geojson'), load('data/candidates.geojson'), load('data/cross_reaches.geojson'),
  load('data/claims.geojson'), load('data/forest_roads.geojson'),
]);
const styleReady = new Promise((ok) => map.once('style.load', ok));

// ---- 候補地点の★の画像 ----

// 白い縁取りの★を描いて、map.addImage に渡せる形で返す（size は CSS ピクセル、2倍で描く）
function starImage(fill, size) {
  const k = 2;
  const s = size * k;
  const c = document.createElement('canvas');
  c.width = s;
  c.height = s;
  const ctx = c.getContext('2d');
  const R = s / 2 - 2.5 * k;
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    const r = i % 2 ? R * 0.45 : R;
    ctx.lineTo(s / 2 + r * Math.cos(a), s / 2 + 1 * k + r * Math.sin(a));
  }
  ctx.closePath();
  ctx.lineJoin = 'round';
  ctx.lineWidth = 3 * k;
  ctx.strokeStyle = '#ffffff';
  ctx.stroke();
  ctx.fillStyle = fill;
  ctx.fill();
  return { width: s, height: s, data: new Uint8Array(ctx.getImageData(0, 0, s, s).data.buffer) };
}

// ---- 選んだものを地図で光らせる ----

const HL_EMPTY = { type: 'FeatureCollection', features: [] };
const PAD = () => (window.innerWidth < 700
  ? { top: 40, bottom: 40, left: 20, right: 20 }
  : { top: 60, bottom: 60, left: 340, right: 380 });
let hlLabel = null;

function setupHighlight() {
  map.addSource('hl', { type: 'geojson', data: HL_EMPTY });
  const poly = ['in', ['geometry-type'], ['literal', ['Polygon', 'MultiPolygon']]];
  const pt = ['in', ['geometry-type'], ['literal', ['Point', 'MultiPoint']]];
  map.addLayer({ id: 'hl-fill', type: 'fill', source: 'hl', filter: poly, paint: { 'fill-color': '#00e5ff', 'fill-opacity': 0.35 } });
  map.addLayer({ id: 'hl-casing', type: 'line', source: 'hl', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 14, 'line-opacity': 0.95 } });
  map.addLayer({ id: 'hl-line', type: 'line', source: 'hl', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#00b4d8', 'line-width': 7 } });
  map.addLayer({ id: 'hl-point', type: 'circle', source: 'hl', filter: pt, paint: { 'circle-radius': 24, 'circle-color': 'rgba(0,229,255,0.25)', 'circle-stroke-color': '#00b4d8', 'circle-stroke-width': 4 } });
}

// 座標の配列を平らにする（Point から MultiPolygon まで）
function flatCoords(g) {
  const out = [];
  const walk = (c) => { if (typeof c[0] === 'number') out.push(c); else c.forEach(walk); };
  walk(g.coordinates);
  return out;
}

// 札を置く点：線なら一番長い線の真ん中の頂点、面なら頂点の平均、点ならその点
function labelPoint(features) {
  let best = null;
  for (const f of features) {
    const g = f.geometry;
    if (g.type === 'Point') return g.coordinates;
    const lines = g.type === 'LineString' ? [g.coordinates] : g.type === 'MultiLineString' ? g.coordinates : null;
    if (!lines) {
      const cs = flatCoords(g);
      return [cs.reduce((a, c) => a + c[0], 0) / cs.length, cs.reduce((a, c) => a + c[1], 0) / cs.length];
    }
    for (const l of lines) if (!best || l.length > best.length) best = l;
  }
  return best ? best[Math.floor(best.length / 2)] : null;
}

function highlight(features, label) {
  map.getSource('hl').setData({ type: 'FeatureCollection', features });
  if (hlLabel) hlLabel.remove();
  hlLabel = null;
  const at = labelPoint(features);
  if (at) {
    const el = document.createElement('div');
    el.className = 'hl-label';
    el.textContent = label;
    hlLabel = new maplibregl.Marker({ element: el, anchor: 'bottom', offset: [0, -14] }).setLngLat(at).addTo(map);
  }
  const cs = features.flatMap((f) => flatCoords(f.geometry));
  if (!cs.length) return;
  const b = cs.reduce((bb, c) => bb.extend(c), new maplibregl.LngLatBounds(cs[0], cs[0]));
  if (b.getNorth() - b.getSouth() < 0.002 && b.getEast() - b.getWest() < 0.002) {
    map.flyTo({ center: b.getCenter(), zoom: 14, pitch: 45, padding: PAD() });
  } else {
    map.fitBounds(b, { padding: PAD(), pitch: 30, maxZoom: 14.5 });
  }
}

function clearHighlight() {
  if (map.getSource('hl')) map.getSource('hl').setData(HL_EMPTY);
  if (hlLabel) { hlLabel.remove(); hlLabel = null; }
}

// 一覧の項目を作る。選ぶと地図で光らせて詳細を出す
const selectors = {};
function addItem(listId, key, html, onSelect) {
  const li = document.createElement('li');
  li.innerHTML = html;
  li.onclick = () => {
    document.querySelectorAll('#panel li.sel').forEach((x) => x.classList.remove('sel'));
    li.classList.add('sel');
    onSelect();
  };
  document.getElementById(listId).appendChild(li);
  if (key) selectors[key] = () => li.click();
}

Promise.all([dataReady, styleReady]).then(([[cat, sites, rivers, riverRec, unplaced, districts, reaches, candidates, crossReaches, claims, roads]]) => {
  for (const s of cat.sources) catalog[s.id] = s;

  // 川: 採取記録のある川の名前に印を付ける
  const recByName = Object.fromEntries(riverRec.records.map((r) => [r.name, r]));
  for (const f of rivers.features) f.properties.gold = recByName[f.properties.name] ? 1 : 0;
  const riverFeatures = (name) => rivers.features.filter((f) => f.properties.name === name);
  map.addSource('rivers', { type: 'geojson', data: rivers });
  map.addLayer({
    id: 'rivers', type: 'line', source: 'rivers',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: {
      'line-color': ['case', ['==', ['get', 'gold'], 1], '#d4a017', '#4a90c2'],
      'line-width': ['case', ['==', ['get', 'gold'], 1], 4, 1.5],
      'line-opacity': 0.9,
    },
  });

  // 区間: 許可や報告で川筋まで分かっているもの
  map.addSource('reaches', { type: 'geojson', data: reaches });
  map.addLayer({
    id: 'reaches', type: 'line', source: 'reaches',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#e8590c', 'line-width': 6, 'line-opacity': 0.85 },
  });

  // 面の採取地（段丘など）
  const isArea = (f) => f.geometry.type === 'Polygon' || f.geometry.type === 'MultiPolygon';
  map.addSource('areas', { type: 'geojson', data: { type: 'FeatureCollection', features: sites.features.filter(isArea) } });
  map.addLayer({ id: 'areas', type: 'fill', source: 'areas', paint: { 'fill-color': '#7b2cbf', 'fill-opacity': 0.25 } });
  map.addLayer({ id: 'areas-line', type: 'line', source: 'areas', paint: { 'line-color': '#7b2cbf', 'line-width': 2, 'line-dasharray': [2, 1] } });

  // 林道（国有林）
  map.addSource('roads', { type: 'geojson', data: roads });
  map.addLayer({
    id: 'roads', type: 'line', source: 'roads', minzoom: 11,
    paint: { 'line-color': '#7a5230', 'line-width': 1.6, 'line-dasharray': [3, 1.5], 'line-opacity': 0.9 },
  });

  // 昔の鉱区（国土数値情報、1991年時点）
  map.addSource('claims', { type: 'geojson', data: claims });
  map.addLayer({ id: 'claims', type: 'fill', source: 'claims', paint: { 'fill-color': '#c92a2a', 'fill-opacity': 0.15 } });
  map.addLayer({ id: 'claims-line', type: 'line', source: 'claims', paint: { 'line-color': '#c92a2a', 'line-width': 2, 'line-dasharray': [2, 1] } });
  for (const f of claims.features) {
    const p = f.properties;
    addItem('claims', p.id, `${esc(p.name)}<span class="meta">${esc(p.set_year)}年設定、${esc(p.area_ha)} ha</span>`, () => {
      highlight([f], p.name);
      showDetail(p.name, [
        ['地図', '水色で光っている面がこの鉱区（赤い破線）'],
        ['種類', p.kind], ['鉱物', p.mineral], ['登録番号', `北海道 ${p.kind}登録第${p.reg_no}号`], ['設定年', `${p.set_year}年`],
        ['面積', `${p.area_ha} ha`], ['データの調査時点', p.surveyed],
        ['意味', '1987〜88年に、歴舟中の川の上流で砂鉱（砂金など）の試掘権が設定されていた。この辺りは1980年代にも誰かが試掘を考えた場所で、手付かずとは限らない'],
        ['確かめ方', '北海道経済産業局に、登録番号を書いて閉鎖鉱業原簿と鉱区図の閲覧を請求できる（保存期間を過ぎて廃棄されていれば見られない）。notes/requests.md'],
      ], p.sources);
    });
  }

  // 地層を横切る区間（伊木の条件3「横谷」）
  map.addSource('cross', { type: 'geojson', data: crossReaches });
  map.addLayer({
    id: 'cross', type: 'line', source: 'cross',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#1864ab', 'line-width': 4, 'line-dasharray': [1.5, 1.2], 'line-opacity': 0.95 },
  });
  for (const f of crossReaches.features) {
    const p = f.properties;
    addItem('cross', p.id, `${esc(p.name)}<span class="meta">交わる角度 約${p.cross_median}度／確かさ ${esc(p.confidence)}</span>`, () => {
      highlight([f], p.name);
      showDetail(p.name, [
        ['地図', '水色で光っている線がこの区間（青い破線）'],
        ['意味', '川が地層の走向とほぼ直角に交わる区間。伊木（1913）は、川が粘板岩の地層を横切る所（横谷）では層の凹凸が天然のせきになり、砂金がたまりやすいとした'],
        ['交わる角度（中央値）', `約${p.cross_median}度`], ['河口からの距離', `${p.from_km}〜${p.to_km} km`],
        ['走向の区域', p.domains], ['確かさ', p.confidence],
        ['注意', '走向は5万分の1地質図から区域ごとに読み取った値で、区域の中の細かい変化は入っていない。川の線は国土数値情報で、実際の流れから数百 m ずれる。data/strike_domains.json、tools/cross_strike.py'],
      ], ['SRC-045', 'SRC-039', 'SRC-052', 'SRC-053', 'SRC-017', 'SRC-011']);
    });
  }

  // 候補地点（地形から推定）
  map.addSource('candidates', { type: 'geojson', data: candidates });
  map.addImage('star-break', starImage('#0ca678', 30), { pixelRatio: 2 });
  map.addImage('star-conf', starImage('#74c0fc', 24), { pixelRatio: 2 });
  map.addLayer({
    id: 'candidates', type: 'symbol', source: 'candidates',
    layout: {
      'icon-image': ['case', ['==', ['get', 'kind'], '勾配が急に緩む点'], 'star-break', 'star-conf'],
      'icon-size': ['interpolate', ['linear'], ['get', 'score'], 0, 0.7, 3, 1.35],
      'symbol-sort-key': ['-', 0, ['get', 'score']],
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
  });

  setupHighlight();

  const byRank = [...candidates.features].sort((a, b) => (a.properties.rank ?? 999) - (b.properties.rank ?? 999));
  for (const f of byRank) {
    const p = f.properties;
    addItem('candidates', p.id, `${p.rank}位 ${esc(p.name)}<span class="meta">重なる条件 ${p.score}：${esc((p.score_reasons || []).join('、') || 'なし')}</span>`, () => {
      highlight([f], p.name);
      showDetail(p.name, [
        ['地図', '水色の丸で囲んだ★がこの地点（緑の★は勾配の変わり目、青の★は合流点の下流）'],
        ['種類', p.kind], ['川', p.river], ['支流', p.tributary],
        ['上流1 kmの勾配', p.grad_up], ['下流1 kmの勾配', p.grad_down], ['谷底の標高', p.elev_m != null ? `${p.elev_m} m` : null],
        ['地層と交わる角度', p.cross_angle != null ? `約${p.cross_angle}度（走向 ${p.strike_deg}度、区域 ${p.strike_domain}、確かさ ${p.strike_conf}）${p.cross_angle >= 60 ? '。地層を横切る所（横谷）' : ''}` : '地層の走向の区域の外（段丘や新第三系の上など）'],
        ['順位', `${p.rank}位（重なる条件 ${p.score}）`], ['重なる条件', (p.score_reasons || []).join('。') || 'なし'],
        ['近くの記録', p.context],
        ['一番近い林道', p.road_m != null ? `${p.road_name}（約${p.road_m} m）` : null], ['土地の区分', p.land], ['近くの昔の鉱区', p.near_claim],
        ['注意', '地形の一般則から機械的に拾った候補で、砂金があることを示すものではない。川の線は国土数値情報で、実際の流れから数十〜数百 m ずれる。考え方は notes/placer-model.md'],
      ], ['SRC-011', 'SRC-013', 'SRC-055', 'SRC-056', 'SRC-054']);
    });
  }

  // 採取地: HTML マーカー（地形の高さに追従する）。面は頂点の平均に置く
  for (const f of sites.features) {
    const p = f.properties;
    const el = document.createElement('div');
    el.className = 'marker';
    el.style.background = CONF_COLOR[confKey(p.position_confidence)] || 'var(--lo)';
    el.innerHTML = `<span class="marker-label">${esc(p.name)}</span>`;
    el.addEventListener('click', (ev) => { ev.stopPropagation(); selectors[p.id](); });
    new maplibregl.Marker({ element: el }).setLngLat(labelPoint([f])).addTo(map);
    addItem('sites', p.id, `${esc(p.name)}<span class="meta">${esc(p.period)}／位置 ${esc(confKey(p.position_confidence))}</span>`, () => {
      highlight([f], p.name);
      siteDetail(p);
    });
  }

  // 区間の一覧
  for (const f of reaches.features) {
    const p = f.properties;
    addItem('reaches', p.id, `${esc(p.name)}<span class="meta">${esc(p.period)}</span>`, () => {
      highlight([f], p.name);
      reachDetail(p);
    });
  }

  // 川の一覧（地図で名前の無い川を押したときも同じ出し方にする）
  const selectRiver = (name, system) => {
    highlight(riverFeatures(name), name || '名称不明の川');
    const r = recByName[name];
    if (r) showRiver(r);
    else showDetail(name || '名称不明の川', [['地図', '水色で光っている線がこの川'], ['水系', system], ['採取記録', 'なし（未調査）']], ['SRC-011']);
  };
  for (const r of riverRec.records) {
    addItem('rivers', `river:${r.name}`, `${esc(r.name)}<span class="meta">${esc(r.period)}</span>`, () => selectRiver(r.name));
  }

  // 地図を押したとき：候補 → 横谷 → 区間 → 段丘 → 川 の順に拾う
  map.on('click', (e) => {
    const hit = map.queryRenderedFeatures(e.point, { layers: ['candidates', 'cross', 'reaches', 'claims', 'areas', 'rivers'] });
    if (!hit.length) return;
    const h = hit[0];
    if (h.layer.id !== 'rivers') selectors[h.properties.id]();
    else if (recByName[h.properties.name]) selectors[`river:${h.properties.name}`]();
    else selectRiver(h.properties.name, h.properties.system);
  });
  for (const id of ['candidates', 'cross', 'reaches', 'claims', 'areas', 'rivers']) {
    map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
  }

  // 郡ごとの記録（地図には置けない）
  for (const r of districts.records) {
    addItem('districts', r.id, `${esc(r.name)}<span class="meta">${esc(r.area)}</span>`, () => {
      clearHighlight();
      showDetail(r.name, [
        ['地図', '郡の境界はまだ入れていないので、地図には出ない'],
        ['範囲', r.area], ['時点', r.period], ['内容', r.summary], ['読み方', r.meaning],
        ['記録の確かさ', r.record_confidence], ['読み取りの記録', r.note],
      ], r.sources);
    });
  }

  // 未配置（地図には置けない）
  for (const r of unplaced.records) {
    addItem('unplaced', r.id, `${esc(r.name)}<span class="meta">${esc(r.missing)}</span>`, () => {
      clearHighlight();
      showDetail(r.name, [['地図', '位置が分からないので、地図には出ない'], ['時期', r.period], ['内容', r.summary], ['置けない理由', r.missing]], r.sources);
    });
  }

  // ?sel=RC-001 のように URL で最初に選ぶものを指定できる
  const qSel = new URLSearchParams(location.search).get('sel');
  if (qSel && selectors[qSel]) selectors[qSel]();
}).catch((err) => {
  console.error(err);
  showDetail('データを読めませんでした', [['原因', String(err)], ['確認', 'index.html をファイルとして直接開くと読めません。README の手順でローカルサーバーから開いてください。']], []);
});

function reachDetail(p) {
  showDetail(p.name, [
    ['地図', '水色で光っている線がこの区間'],
    ['昔の名前', p.historic_names], ['今の川との対応', p.mapping], ['時期', p.period], ['内容', p.summary],
    ['採取高', p.production], ['たまりやすい場所', p.hint], ['区間の分かり方', p.section_known], ['記録の確かさ', p.record_confidence],
  ], p.sources);
}

function showRiver(r) {
  showDetail(r.name, [['地図', '水色で光っている線がこの川'], ['時期', r.period], ['内容', r.summary], ['たまりやすい場所', r.hint], ['記録の確かさ', r.record_confidence], ['区間', '不明（川全体に色を付けている）']], r.sources);
}

// ---- 操作 ----

const BASEMAPS = ['photo', 'old70', 'old60', 'relief', 'std', 'pale'];

document.querySelectorAll('.seg button[data-k]').forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll('.seg button[data-k]').forEach((x) => x.classList.toggle('on', x === b));
    for (const k of BASEMAPS) map.setLayoutProperty(k, 'visibility', k === b.dataset.k ? 'visible' : 'none');
    map.setLayoutProperty('hillshade', 'visibility', ['std', 'pale'].includes(b.dataset.k) ? 'visible' : 'none');
  };
});

// ?at=経度,緯度,ズーム,傾き で最初の視点を選べる
const qAt = (new URLSearchParams(location.search).get('at') || '').split(',').map(Number);
if (qAt.length >= 2 && qAt.every((v) => !Number.isNaN(v))) {
  map.jumpTo({ center: [qAt[0], qAt[1]], zoom: qAt[2] || 13.5, pitch: Number.isNaN(qAt[3]) || qAt[3] === undefined ? map.getPitch() : qAt[3] });
}

// ?base=old60 のように URL で背景を選べる
const qBase = new URLSearchParams(location.search).get('base');
if (BASEMAPS.includes(qBase)) {
  map.once('style.load', () => document.querySelector(`.seg button[data-k="${qBase}"]`).click());
}

const exag = document.getElementById('exag');
exag.oninput = () => {
  document.getElementById('exagv').textContent = exag.value;
  if (map.getTerrain()) map.setTerrain({ source: 'dem', exaggeration: Number(exag.value) });
};
