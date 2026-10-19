// Source for the region controls added to the published static application.
// The existing bundle supplies the map, city validation and linear-light scaling.
export const DEFAULT_PALETTE = Object.freeze({
  enabled: true,
  background: '#ffd54f',
  map: '#ff8a3d',
  selected: '#8b4513',
});

export function validatePalette(value) {
  if (!value || typeof value.enabled !== 'boolean'
      || Object.keys(value).length !== 4
      || ['background', 'map', 'selected'].some(key =>
        typeof value[key] !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(value[key]))) {
    throw new Error('三區配色格式無效；請使用有效的六位色碼。');
  }
  return {
    enabled: value.enabled,
    background: value.background.toLowerCase(),
    map: value.map.toLowerCase(),
    selected: value.selected.toLowerCase(),
  };
}

export function readCityDocument(value, validateCities) {
  if (!value || ![1, 2].includes(value.schemaVersion)
      || !Number.isInteger(value.base) || value.base < 0 || value.base > 255) {
    throw new Error('城市設定格式無效。');
  }
  validateCities(value.cities);
  const palette = value.schemaVersion === 1
    ? {...DEFAULT_PALETTE, enabled: false}
    : validatePalette(value.palette);
  return {schemaVersion: 2, base: value.base, cities: structuredClone(value.cities), palette};
}

export function buildCityScene(cities, base, palette, rows, scaleColor) {
  const land = rows.join('');
  const regions = Boolean(palette?.enabled);
  // City points can lie just outside the original land artwork. An unselected
  // city must keep the map color instead of changing into background.
  const cityPixels = new Set(cities.flatMap(city => city.pixels));
  const mask = Array(4096).fill(0);
  const colors = Array(4096).fill(null);
  const paint = (index, color) => {
    const lit = color.toLowerCase() !== '#000000';
    mask[index] = Number(lit);
    colors[index] = lit ? color : null;
  };
  const mapColor = scaleColor(regions ? palette.map : '#62bde8', base);
  for (let index = 0; index < 4096; index++) {
    if (regions) {
      paint(index, land[index] === '1' || cityPixels.has(index) ? mapColor : palette.background);
    } else if (base > 0 && land[index] === '1') {
      paint(index, mapColor);
    }
  }
  for (const city of cities) {
    if (!city.on || (!regions && city.brightness === 0)) continue;
    const color = scaleColor(regions ? palette.selected : city.color, city.brightness);
    for (const index of city.pixels) paint(index, color);
  }
  return {mask, colors};
}

export function paletteControls(ui, {value, onChange}) {
  const fields = [
    ['background', '背景顏色', '地圖以外的燈點'],
    ['map', '未選取地圖顏色', '底圖及未勾選城市'],
    ['selected', '已選取地圖顏色', '已勾選的城市'],
  ];
  return ui.jsxs('fieldset', {className: 'city-palette', children: [
    ui.jsx('legend', {children: '地圖配色'}),
    ui.jsxs('label', {className: 'toggle-field city-palette-toggle', children: [
      ui.jsx('input', {type: 'checkbox', 'aria-label': '使用三區配色', checked: value.enabled,
        onChange: event => onChange({...value, enabled: event.target.checked})}),
      '使用三區配色',
    ]}),
    ui.jsx('div', {className: 'city-palette-fields', children: fields.map(([key, label, detail]) =>
      ui.jsxs('label', {className: 'city-palette-field', children: [
        ui.jsxs('span', {children: [label, ui.jsx('small', {children: detail})]}),
        ui.jsx('input', {type: 'color', 'aria-label': label, value: value[key], disabled: !value.enabled,
          onChange: event => onChange({...value, [key]: event.target.value})}),
        ui.jsx('code', {children: value[key].toUpperCase()}),
      ]}, key))}),
    ui.jsx('p', {className: 'hint', children: value.enabled
      ? '改色即時更新預覽；開啟「即時同步」可傳到燈板。背景選黑色可熄滅。首次啟用先以 10% 整體亮度試燈，之後保留你的亮度。'
      : '目前使用逐城配色；開啟三區配色可統一設定背景、底圖及已勾選城市。'}),
  ]});
}
