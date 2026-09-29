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
  el.querySelector('.close').onclick = () => { el.hidden = true; };
}

function confKey(s) {
  return (s || '').trim().charAt(0);
}

function siteDetail(p) {
  showDetail(p.name, [
    ['種別', p.kind], ['時期', p.period], ['内容', p.summary], ['試掘の結果', p.result],
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
  load('data/reaches.geojson'),
]);
const styleReady = new Promise((ok) => map.once('style.load', ok));

Promise.all([dataReady, styleReady]).then(([[cat, sites, rivers, riverRec, unplaced, districts, reaches]]) => {
  for (const s of cat.sources) catalog[s.id] = s;

  // 川: 採取記録のある川の名前に印を付ける
  const recByName = Object.fromEntries(riverRec.records.map((r) => [r.name, r]));
  for (const f of rivers.features) f.properties.gold = recByName[f.properties.name] ? 1 : 0;
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
  map.on('mouseenter', 'rivers', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'rivers', () => { map.getCanvas().style.cursor = ''; });
  map.on('click', 'rivers', (e) => {
    const p = e.features[0].properties;
    const r = recByName[p.name];
    if (r) showRiver(r);
    else showDetail(p.name || '名称不明の川', [['水系', p.system], ['採取記録', 'なし（未調査）']], ['SRC-011']);
  });

  // 区間: 許可や報告で川筋まで分かっているもの
  map.addSource('reaches', { type: 'geojson', data: reaches });
  map.addLayer({
    id: 'reaches', type: 'line', source: 'reaches',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#e8590c', 'line-width': 6, 'line-opacity': 0.85 },
  });
  map.on('mouseenter', 'reaches', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'reaches', () => { map.getCanvas().style.cursor = ''; });
  const reachById = Object.fromEntries(reaches.features.map((f) => [f.properties.id, f]));
  map.on('click', 'reaches', (e) => { reachDetail(reachById[e.features[0].properties.id].properties); });
  const rcl = document.getElementById('reaches');
  for (const f of reaches.features) {
    const p = f.properties;
    const li = document.createElement('li');
    li.innerHTML = `${esc(p.name)}<span class="meta">${esc(p.period)}</span>`;
    li.onclick = () => {
      const b = new maplibregl.LngLatBounds();
      const lines = f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates;
      lines.forEach((l) => l.forEach((c) => b.extend(c)));
      map.fitBounds(b, { padding: 80, pitch: 60 });
      reachDetail(p);
    };
    rcl.appendChild(li);
  }

  // 面の採取地（段丘など）
  const areas = { type: 'FeatureCollection', features: sites.features.filter((f) => f.geometry.type === 'Polygon') };
  map.addSource('areas', { type: 'geojson', data: areas });
  map.addLayer({ id: 'areas', type: 'fill', source: 'areas', paint: { 'fill-color': '#7b2cbf', 'fill-opacity': 0.25 } });
  map.addLayer({ id: 'areas-line', type: 'line', source: 'areas', paint: { 'line-color': '#7b2cbf', 'line-width': 2, 'line-dasharray': [2, 1] } });

  // 採取地: HTML マーカー（地形の高さに追従する）。面は重心に置く
  const ul = document.getElementById('sites');
  for (const f of sites.features) {
    const p = f.properties;
    if (f.geometry.type === 'Polygon') {
      const ring = f.geometry.coordinates[0].slice(0, -1);
      f.geometry = { type: 'Point', coordinates: [ring.reduce((a, c) => a + c[0], 0) / ring.length, ring.reduce((a, c) => a + c[1], 0) / ring.length] };
    }
    const el = document.createElement('div');
    el.className = 'marker';
    el.style.background = CONF_COLOR[confKey(p.position_confidence)] || 'var(--lo)';
    el.innerHTML = `<span class="marker-label">${esc(p.name)}</span>`;
    el.addEventListener('click', (ev) => { ev.stopPropagation(); siteDetail(p); });
    new maplibregl.Marker({ element: el }).setLngLat(f.geometry.coordinates).addTo(map);

    const li = document.createElement('li');
    li.innerHTML = `${esc(p.name)}<span class="meta">${esc(p.period)}／位置 ${esc(confKey(p.position_confidence))}</span>`;
    li.onclick = () => {
      map.flyTo({ center: f.geometry.coordinates, zoom: 13.5, pitch: 65 });
      siteDetail(p);
    };
    ul.appendChild(li);
  }

  // 川ごとの記録
  const rl = document.getElementById('rivers');
  for (const r of riverRec.records) {
    const li = document.createElement('li');
    li.innerHTML = `${esc(r.name)}<span class="meta">${esc(r.period)}</span>`;
    li.onclick = () => {
      const fs = rivers.features.filter((f) => f.properties.name === r.name);
      if (fs.length) {
        const b = new maplibregl.LngLatBounds();
        fs.forEach((f) => f.geometry.coordinates.forEach((c) => b.extend(c)));
        map.fitBounds(b, { padding: 80, pitch: 60 });
      }
      showRiver(r);
    };
    rl.appendChild(li);
  }

  // 郡ごとの記録
  const dl = document.getElementById('districts');
  for (const r of districts.records) {
    const li = document.createElement('li');
    li.innerHTML = `${esc(r.name)}<span class="meta">${esc(r.area)}</span>`;
    li.onclick = () => showDetail(r.name, [
      ['範囲', r.area], ['時点', r.period], ['内容', r.summary], ['読み方', r.meaning],
      ['記録の確かさ', r.record_confidence], ['読み取りの記録', r.note],
    ], r.sources);
    dl.appendChild(li);
  }

  // 未配置
  const ul2 = document.getElementById('unplaced');
  for (const r of unplaced.records) {
    const li = document.createElement('li');
    li.innerHTML = `${esc(r.name)}<span class="meta">${esc(r.missing)}</span>`;
    li.onclick = () => showDetail(r.name, [['時期', r.period], ['内容', r.summary], ['置けない理由', r.missing]], r.sources);
    ul2.appendChild(li);
  }
}).catch((err) => {
  console.error(err);
  showDetail('データを読めませんでした', [['原因', String(err)], ['確認', 'index.html をファイルとして直接開くと読めません。README の手順でローカルサーバーから開いてください。']], []);
});

function reachDetail(p) {
  showDetail(p.name, [
    ['昔の名前', p.historic_names], ['今の川との対応', p.mapping], ['時期', p.period], ['内容', p.summary],
    ['採取高', p.production], ['区間の分かり方', p.section_known], ['記録の確かさ', p.record_confidence],
  ], p.sources);
}

function showRiver(r) {
  showDetail(r.name, [['時期', r.period], ['内容', r.summary], ['たまりやすい場所', r.hint], ['記録の確かさ', r.record_confidence], ['区間', '不明（川全体に色を付けている）']], r.sources);
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
