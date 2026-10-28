// BRAND pipeline MVP — vanilla JS, no build step.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.body && !(o.body instanceof FormData)) { o.body = JSON.stringify(o.body); o.headers = { 'Content-Type': 'application/json' }; }
  const r = await fetch(path, o);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
function toast(msg, err = false) {
  const t = $('#toast'); t.textContent = msg; t.className = err ? 'err' : ''; t.style.display = 'block';
  clearTimeout(toast._t); toast._t = setTimeout(() => t.style.display = 'none', err ? 7000 : 3000);
}
function modal(html) { $('#modalBox').innerHTML = `<button class="btn sm close" onclick="closeModal()">✕</button>` + html; $('#modal').classList.add('open'); }
function closeModal() { $('#modal').classList.remove('open'); }
function zoom(url) { modal(`<img class="full" src="${url}">`); }
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

let CFG = null, DESIGNS = [], PERSONAS = [], SHEETS = [], GUIDES = {};
const label = (kind, id) => kind === 'personas'
  ? ((p => p ? `${p.label} · ${p.name}` : `${id} (удалена)`)(PERSONAS.find(x => x.id === id)))
  : kind === 'poses' ? (id === 'kit' ? 'Комплектация' : ([...CFG.poses, ...CFG.product_poses].find(x => x.id === id) || {}).label || id)
  : (CFG[kind].find(x => x.id === id) || {}).label || id;
const who = s => s.kind === 'product' ? 'Без модели' : s.kind === 'kit' ? 'Без модели' : label('personas', s.persona);

// ---------- tabs ----------
$$('nav button').forEach(b => b.onclick = () => showTab(b.dataset.tab));
function showTab(t) {
  $$('nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  ['designs', 'personas', 'cards', 'constructor', 'export'].forEach(x => $('#tab-' + x).classList.toggle('hide', x !== t));
  if (t === 'export') renderExport();
  if (t === 'cards') renderBuilder();
  if (t === 'constructor') initConstructor();
}

// ---------- jobs ----------
const watchers = {};
function watchJob(id, onDone, el) { watchers[id] = { onDone, el }; pollJobs(); }
async function pollJobs() {
  let jobs = [];
  try { jobs = await api('/api/jobs'); } catch { return; }
  const running = jobs.filter(j => j.status === 'running').length;
  $('#jobsCount').innerHTML = running ? `<span class="spin"></span> ${running}` : '';
  $('#jobList').innerHTML = jobs.map(j => `<div class="job"><div class="row"><b class="grow small">${esc(j.title)}</b>${statusBadge(j.status)}</div>
    <div class="log" style="max-height:120px;margin-top:6px">${esc(j.log.slice(-8).join('\n'))}</div></div>`).join('') || '<p class="muted small">Пока нет задач</p>';
  for (const j of jobs) {
    const w = watchers[j.id]; if (!w) continue;
    const el = typeof w.el === 'string' ? $(w.el) : w.el;
    if (el) el.innerHTML = `<div class="row small">${statusBadge(j.status)} <span class="muted">${esc(j.log[j.log.length - 1] || '')}</span></div>`;
    if (j.status !== 'running') { delete watchers[j.id]; w.onDone && w.onDone(j); }
  }
}
setInterval(pollJobs, 2500);
$('#jobsBtn').onclick = () => $('#drawer').classList.toggle('open');
$('#drawerClose').onclick = () => $('#drawer').classList.remove('open');
function statusBadge(s) {
  const m = { running: ['run', '<span class="spin"></span> идёт'], done: ['ok', 'готово'], error: ['err', 'ошибка'], queued: ['', 'в очереди'] }[s] || ['', s];
  return `<span class="badge ${m[0]}">${m[1]}</span>`;
}

// ---------- pipeline 1: designs ----------
const sidesText = d => !d.sides.includes('B') ? 'односторонняя' : d.side_b === 'mirror' ? 'двусторонняя, симметричная' : 'двусторонняя';
async function loadDesigns() {
  DESIGNS = await api('/api/designs');
  $('#designGrid').innerHTML = DESIGNS.map(d => `<div class="tile">
      <div class="img" style="background-image:url('${d.hero || d.mockup}')" onclick="openDesign('${d.slug}')"></div>
      <div class="body">
        <div class="name">${esc(d.name)}</div>
        <div class="row small"><span class="badge">${esc(d.segment)}</span><span class="badge">${sidesText(d)}</span>${d.shape && d.shape.startsWith('kid_') ? `<span class="badge">${esc(shapeLabel(d.shape))}</span>` : ''}</div>
        <div class="dots">${[d.base, ...d.inks].map(c => `<span class="dot" title="${esc(c.name)} ${c.hex}" style="background:${c.hex}"></span>`).join('')}</div>
        <div class="row" style="margin-top:auto"><button class="btn sm" onclick="openDesign('${d.slug}')">Подробнее</button>
          <button class="btn sm primary" onclick="toCards('${d.slug}')">→ Фото на моделях</button>
          <button class="btn sm ghost" style="margin-left:auto;color:var(--err)" title="Удалить дизайн" onclick="deleteDesign('${d.slug}')">🗑</button></div>
      </div></div>`).join('');
}
function openDesign(slug) {
  const d = DESIGNS.find(x => x.slug === slug);
  const imgs = [d.mockup, d.layout, d.on_model].filter(Boolean);
  modal(`<h2>${esc(d.name)} <span class="muted small">${esc(d.slug)} · ${sidesText(d)}</span></h2>
    <p>${esc(d.concept)}</p>
    <table class="t"><tr><th></th><th>RAL</th><th>Название RAL</th><th>ΔE</th><th>Цвет в дизайне</th></tr>
    ${[['Шапочка', d.base], ...d.inks.map((k, i) => [`Краска ${i + 1}${k.role ? ' · ' + k.role : ''}`, k]), ...(d.variants || []).map((v, i) => [`Вариант шапочки ${i + 1}`, v])].map(([t, c]) => `<tr>
      <th>${esc(t)}</th><td><span class="dot" style="display:inline-block;vertical-align:-3px;background:${c.ral_hex}"></span> <b>${esc(c.ral)}</b></td>
      <td>${esc(c.ral_name)}</td><td>${c.de}${c.de > 3 ? ' ⚠' : ''}</td>
      <td><span class="dot" style="display:inline-block;vertical-align:-3px;background:${c.hex}"></span> ${esc(c.name || '')} ${c.hex}</td></tr>`).join('')}
    </table>
    <p class="muted small">RAL — ближайший цвет RAL Classic по ΔE2000: до 1 — совпадение, до 3 — близко, больше 3 (⚠) — утверждать по выкрасу.</p>
    <div class="row" style="margin:14px 0;align-items:flex-start">${imgs.map(u => `<img src="${u}" style="max-width:32%;border-radius:10px;cursor:zoom-in" onclick="zoom('${u}')">`).join('')}</div>
    <details><summary>Файлы для производства (${d.files.length})</summary><ul class="small">${d.files.map(f => `<li><a href="${f.url}" target="_blank">${esc(f.name)}</a></li>`).join('')}</ul></details>
    ${d.refs && d.refs.length ? `<div class="small muted" style="margin-top:10px">Референсы:</div><div class="row">${d.refs.map(u => `<img src="${u}" style="width:90px;height:90px;object-fit:cover;border-radius:8px;cursor:zoom-in" onclick="zoom('${u}')">`).join('')}</div>` : ''}
    <details><summary>Промпт картинки</summary><p class="small muted">${esc(d.image_prompt)}</p></details>
    <div class="row" style="margin-top:12px"><button class="btn primary" onclick="closeModal();toCards('${d.slug}')">Фото на моделях →</button>
      ${d.spec_xlsx ? `<a class="btn" href="${d.spec_xlsx}" download>Скачать ТЗ (Excel, EN/中文)</a>` : ''}
      <button class="btn" style="margin-left:auto;color:var(--err)" onclick="deleteDesign('${d.slug}')">Удалить дизайн</button>
      ${d.sides.includes('B') ? '' : `<button class="btn" onclick="mirrorDesign('${d.slug}')">Сделать двусторонней симметричной (копия ${esc(d.slug)}_ab)</button>`}</div>`);
}
async function deleteDesign(slug) {
  const d = DESIGNS.find(x => x.slug === slug) || { name: slug };
  let u = { packs: 0 };
  try { u = await api(`/api/designs/${slug}/usage`); } catch { }
  const warn = u.packs ? `\n\nПо нему есть фотосессий: ${u.packs}. Фото в них останутся, но перегенерировать кадры будет нельзя.` : '';
  if (!confirm(`Удалить дизайн «${d.name}» (${slug})?\nУдалятся трафареты, мокап, ТЗ и исходники. Это необратимо.${warn}`)) return;
  try {
    await api('/api/designs/' + slug, { method: 'DELETE' });
    closeModal(); ESEL.delete(slug);
    if (C.src === slug) C.src = null;
    if (B.design === slug) B.design = null;
    toast('Дизайн удалён'); await loadDesigns(); loadStorage();
    if (!$('#tab-export').classList.contains('hide')) renderExport();
  } catch (e) { toast(e.message, true); }
}
async function mirrorDesign(slug) {
  try {
    const j = await api(`/api/designs/${slug}/mirror`, { method: 'POST' });
    closeModal(); toast('Строю сторону B…');
    watchJob(j.id, jj => { jj.status === 'done' ? toast('Готово: ' + jj.result.slug) : toast('Не удалось, см. «Задачи»', true); loadDesigns(); });
  } catch (e) { toast(e.message, true); }
}
$('#dReload').onclick = loadDesigns;
// references for a new design: uploaded once, sent as ids
const DREFS = [];
async function addRefs(files) {
  for (const f of files) {
    if (DREFS.length >= 4) { toast('Не больше 4 референсов', true); break; }
    if (!f.type.startsWith('image/')) continue;
    const fd = new FormData(); fd.append('file', f);
    try { const r = await api('/api/refs', { method: 'POST', body: fd }); DREFS.push({ id: r.id, url: URL.createObjectURL(f) }); }
    catch (e) { toast(e.message, true); }
  }
  renderRefs();
}
function renderRefs() {
  $('#dRefs').innerHTML = DREFS.map((r, i) => `<div style="position:relative"><img src="${r.url}" style="width:84px;height:84px;object-fit:cover;border-radius:8px;border:1px solid var(--line)">
    <button class="btn sm" style="position:absolute;top:2px;right:2px;padding:0 6px" onclick="DREFS.splice(${i},1);renderRefs()">✕</button></div>`).join('');
}
$('#dRefFile').onchange = e => { addRefs([...e.target.files]); e.target.value = ''; };
document.addEventListener('paste', e => {
  if ($('#tab-designs').classList.contains('hide')) return;
  const files = [...(e.clipboardData || {}).files || []].filter(f => f.type.startsWith('image/'));
  if (files.length) { e.preventDefault(); addRefs(files); }
});
$('#tab-designs').addEventListener('dragover', e => e.preventDefault());
$('#tab-designs').addEventListener('drop', e => { e.preventDefault(); addRefs([...e.dataTransfer.files]); });

$('#dGo').onclick = async () => {
  const body = { refs: DREFS.map(r => r.id), theme: $('#dTheme').value, preset: $('#dPreset').value, slug: $('#dSlug').value, sides: $('#dSides').value, shape: $('#dShape').value, logo: $('#dShape').value.startsWith('kid_') ? $('#dLogo').value : '', pu_layout: $('#dPu').value };
  try {
    const j = await api('/api/designs/generate', { method: 'POST', body });
    $('#dGo').disabled = true;
    watchJob(j.id, jj => {
      $('#dGo').disabled = false;
      if (jj.status === 'done') { toast('Дизайн готов: ' + jj.result.slug); loadDesigns(); }
      else toast('Генерация не удалась, см. «Задачи»', true);
    }, '#dJob');
  } catch (e) { toast(e.message, true); }
};

// ---------- personas and pose sheets ----------
async function loadPersonas() {
  [PERSONAS, SHEETS] = await Promise.all([api('/api/personas'), api('/api/poses')]);
  $('#personaGroups').innerHTML = CFG.groups.map(g => `<div><h3 style="margin-bottom:10px">${esc(g.label)}</h3><div class="grid">
    ${PERSONAS.filter(p => p.group === g.id).map(p => `<div class="tile persona">
      <div class="img" style="${p.ref ? `background-image:url('${p.ref}')` : ''}" ${p.ref ? `onclick="zoom('${p.ref}')"` : ''}>${p.ref ? '' : '<div style="display:grid;place-items:center;height:100%" class="muted small">эталона нет</div>'}</div>
      <div class="body">
        <div class="name">${esc(p.label)} · ${esc(p.name)}</div>
        <div class="muted small">${esc(p.look)}; ${esc(p.wear)}</div>
        <div id="pj-${p.id}"></div>
        <div class="row" style="margin-top:auto">
          <button class="btn sm primary" onclick="genPersona('${p.id}')">${p.ref ? 'Перегенерировать' : 'Сгенерировать эталон'}</button>
          <label class="btn sm">Загрузить фото<input type="file" accept="image/*" hidden onchange="uploadPersona('${p.id}', this)"></label>
          <button class="btn sm ghost" onclick="personaForm('${g.id}','${p.id}')">Изменить</button>
          <button class="btn sm ghost" style="color:var(--err)" onclick="deletePersona('${p.id}')">Удалить</button>
        </div>
      </div></div>`).join('')}
      <div class="tile add" onclick="personaForm('${g.id}')"><div class="plus">+</div><div>Новая модель</div></div></div></div>`).join('');
  B.personas = B.personas.filter(id => PERSONAS.some(p => p.id === id));
  $('#poseSheets').innerHTML = SHEETS.map(s => `<div class="panel stack">
    <div class="row"><h3 class="grow">${esc(s.label)}</h3><span id="sj-${s.id}"></span>
      <button class="btn sm ${s.sheet ? '' : 'primary'}" onclick="genSheet('${s.id}')">${s.sheet ? 'Перегенерировать лист' : 'Сгенерировать лист'}</button></div>
    ${s.sheet ? `<div class="cells">${CFG.poses.map(p => s.cells[p.id] ? `<div class="cell"><img src="${s.cells[p.id]}" onclick="zoom('${s.cells[p.id]}')"><div>${esc(p.label)} <button class="btn sm ghost" title="отзеркалить" onclick="flipPose('${s.id}','${p.id}')">⇋</button></div></div>` : '').join('')}</div>
      <a class="small" href="${s.sheet}" target="_blank">исходный лист</a>` : '<p class="muted small">Листа нет</p>'}</div>`).join('');
}
const LOOK_HINT = {
  woman: 'a woman about 30 years old, wavy auburn hair, green eyes, fair skin, athletic build',
  man: 'a man about 35 years old, short black hair, brown eyes, tanned skin, muscular swimmer build',
  girl: 'a cheerful girl about 9 years old, dark hair in a ponytail, brown eyes, friendly smile',
  boy: 'a cheerful boy about 6 years old, short blond hair, blue eyes, freckles, friendly smile',
};
function personaForm(group, id) {
  const p = id ? PERSONAS.find(x => x.id === id) : null;
  modal(`<h2>${p ? 'Изменить модель' : 'Новая модель'} · ${esc(label('groups', group))}</h2>
    <div class="stack" style="margin-top:14px">
      <label class="f">Имя (для себя)<input type="text" id="pfName" value="${esc(p ? p.name : '')}" placeholder="Полина"></label>
      <label class="f">Внешность — точнее по-английски: возраст, волосы, глаза, кожа, телосложение
        <textarea id="pfLook" rows="3" placeholder="${esc(LOOK_HINT[group] || '')}">${esc(p ? p.look : '')}</textarea></label>
      <label class="f">Купальник / одежда<input type="text" id="pfWear" value="${esc(p ? p.wear : '')}" placeholder="по умолчанию для группы"></label>
      ${p ? `<p class="muted small">После изменения внешности перегенерируйте эталон, иначе лицо останется прежним.</p>`
          : `<label class="row small"><input type="checkbox" id="pfGen" checked> сразу сгенерировать эталон (иначе загрузите фото на карточке модели)</label>`}
      <div class="row"><div class="grow"></div><button class="btn" onclick="closeModal()">Отмена</button>
        <button class="btn primary" onclick="savePersona('${group}', ${p ? `'${p.id}'` : 'null'})">${p ? 'Сохранить' : 'Создать'}</button></div>
    </div>`);
}
async function savePersona(group, id) {
  const body = { group, name: $('#pfName').value, look: $('#pfLook').value, wear: $('#pfWear').value };
  try {
    const p = await api(id ? `/api/personas/${id}` : '/api/personas', { method: id ? 'PUT' : 'POST', body });
    const gen = !id && $('#pfGen').checked;
    closeModal(); await loadPersonas();
    toast(id ? 'Сохранено' : `Модель «${p.name}» создана`);
    if (gen) genPersona(p.id, true);
  } catch (e) { toast(e.message, true); }
}
async function deletePersona(id) {
  const p = PERSONAS.find(x => x.id === id);
  if (!confirm(`Удалить модель «${p.label} · ${p.name}»? Эталон переместится в personas/_trash. Готовые фото останутся.`)) return;
  try { await api('/api/personas/' + id, { method: 'DELETE' }); toast('Модель удалена'); loadPersonas(); }
  catch (e) { toast(e.message, true); }
}
async function genPersona(id, force) {
  if (!force && PERSONAS.find(p => p.id === id).ref && !confirm('Новый эталон изменит лицо модели во всех следующих фото. Продолжить?')) return;
  const j = await api(`/api/personas/${id}/generate`, { method: 'POST' });
  watchJob(j.id, jj => { jj.status === 'done' ? toast('Эталон готов') : toast('Не удалось: см. «Задачи»', true); loadPersonas(); }, '#pj-' + id);
}
async function uploadPersona(id, input) {
  const fd = new FormData(); fd.append('file', input.files[0]);
  try { await api(`/api/personas/${id}/upload`, { method: 'POST', body: fd }); toast('Фото загружено'); loadPersonas(); }
  catch (e) { toast(e.message, true); }
}
async function flipPose(g, id) {
  try { await api(`/api/poses/${g}/${id}/flip`, { method: 'POST' }); loadPersonas(); } catch (e) { toast(e.message, true); }
}
async function genSheet(g) {
  const j = await api(`/api/poses/${g}/generate`, { method: 'POST' });
  watchJob(j.id, jj => { jj.status === 'done' ? toast('Лист ракурсов готов') : toast('Не удалось: см. «Задачи»', true); loadPersonas(); }, '#sj-' + g);
}

// ---------- pipeline 2: builder ----------
const B = { design: null, personas: [], poses: ['close_front', 'close_left', 'q_left'], scenes: ['studio'], product: [], kit: false, shots: [] };
const curDesign = () => DESIGNS.find(x => x.slug === B.design);

function toCards(slug) { B.design = slug; autoPersonas(); showTab('cards'); closePack(); }
function autoPersonas() {
  const d = curDesign(); if (!d) return;
  B.personas = d.segment === 'Детская' ? ['boy1', 'girl1'] : d.segment === 'Женская' ? ['woman1'] : ['man1', 'woman1'];
}
async function loadGuides() {
  if (!B.design || GUIDES[B.design]) return;
  GUIDES[B.design] = await api(`/api/designs/${B.design}/guides`);
}

async function renderBuilder() {
  if (!CFG) return;
  if (!B.design && DESIGNS.length) { B.design = DESIGNS[0].slug; autoPersonas(); }
  const d = curDesign();
  $('#bDesigns').innerHTML = DESIGNS.map(x => `<div class="it ${x.slug === B.design ? 'on' : ''}" onclick="pickDesign('${x.slug}')">
    <img src="${x.hero || x.mockup}" loading="lazy"><div>${esc(x.name)}</div></div>`).join('');
  $('#bSides').innerHTML = d ? (d.sides.includes('B')
    ? (d.side_b === 'mirror' ? '<b>Двусторонняя симметричная:</b> слева принт с логотипом, справа тот же принт зеркально, без логотипа.'
      : '<b>Двусторонняя:</b> сторона A с логотипом — левая сторона головы, сторона B без логотипа — правая.')
    : '<b>Односторонняя:</b> принт с логотипом — на левой стороне головы, правая сторона — чистый силикон.') : '';
  $('#bPersonas').innerHTML = CFG.groups.map(g => `<div><div class="muted small" style="margin-bottom:6px">${esc(g.label)}</div><div class="pick persons">
    ${PERSONAS.filter(p => p.group === g.id).map(p => `<div class="it ${B.personas.includes(p.id) ? 'on' : ''}" data-p="${p.id}" onclick="toggleArr(B.personas,'${p.id}');refresh()">
      ${p.ref ? `<img src="${p.ref}">` : '<div class="ph">нет эталона</div>'}<div>${esc(p.label)} · ${esc(p.name)}</div></div>`).join('')}</div></div>`).join('');
  $('#bScenes').innerHTML = CFG.scenes.map(p => `<span class="chip" data-s="${p.id}" onclick="toggleArr(B.scenes,'${p.id}');refresh()">${esc(p.label)}</span>`).join('');
  await loadGuides();
  refresh();
  loadPacks();
}
function pickDesign(slug) { B.design = slug; autoPersonas(); renderBuilder(); }
function toggleArr(a, v) { const i = a.indexOf(v); i < 0 ? a.push(v) : a.splice(i, 1); }

function poseThumb(poseId) {
  // mannequin of the first selected persona's group, else any group that has a sheet
  const groups = [...new Set(B.personas.map(p => (PERSONAS.find(x => x.id === p) || {}).group))];
  for (const g of [...groups, ...CFG.groups.map(x => x.id)]) {
    const s = SHEETS.find(x => x.id === g);
    if (s && s.cells[poseId]) return s.cells[poseId];
  }
  return null;
}
function renderPoses() {
  const d = curDesign(), guides = GUIDES[B.design] || {}, two = d && d.sides.includes('B');
  $('#bPoses').innerHTML = CFG.poses.filter(p => !p.hands).map(p => {
    const th = poseThumb(p.id), plain = !two && p.yaw > 60, hands = p.hands;
    return `<div class="pose ${B.poses.includes(p.id) ? 'on' : ''}" onclick="toggleArr(B.poses,'${p.id}');refresh()">
      <div class="pair">${th ? `<img src="${th}">` : `<div class="ph">${hands ? 'в руках' : 'нет листа'}</div>`}${guides[p.id] ? `<img src="${guides[p.id]}" class="g">` : '<div class="ph"></div>'}</div>
      <div class="lbl">${esc(p.label)}${plain ? '<div class="muted">правая сторона — без принта</div>' : ''}</div></div>`;
  }).join('');
  // example photos (app/assets/examples/<id>.jpg) show what each non-head shot looks like
  const tile = (on, id, lbl, click) => `<div class="tile1 ${on ? 'on' : ''}" onclick="${click}">
      <img src="/assets/examples/${id}.jpg" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'ph',textContent:'пример появится'}))">
      <div class="lbl">${esc(lbl)}</div></div>`;
  $('#bHands').innerHTML = CFG.poses.filter(p => p.hands).map(p => tile(B.poses.includes(p.id), p.id, p.label, `toggleArr(B.poses,'${p.id}');refresh()`)).join('');
  $('#bProduct').innerHTML = CFG.product_poses.map(p => tile(B.product.includes(p.id), p.id, p.label, `toggleArr(B.product,'${p.id}');refresh()`)).join('')
    + tile(B.kit, 'kit', 'Комплектация: шапочка + сумка + беруши', 'B.kit=!B.kit;refresh()');
}
function refresh() {
  $$('#bPersonas .it').forEach(el => el.classList.toggle('on', B.personas.includes(el.dataset.p)));
  $$('#bScenes .chip').forEach(el => el.classList.toggle('on', B.scenes.includes(el.dataset.s)));
  renderPoses();
  // shots = personas x poses, scenes round-robin; keep user edits of rows that still exist
  const old = {}; B.shots.forEach(s => old[s.kind + '|' + s.persona + '|' + s.pose] = s);
  const out = []; let k = 0;
  const add = (kind, persona, pose) => {
    const prev = old[kind + '|' + persona + '|' + pose];
    out.push(prev && B.scenes.includes(prev.scene) ? prev : { kind, persona, pose, scene: B.scenes[k % Math.max(B.scenes.length, 1)] || 'studio', note: '' });
    k++;
  };
  for (const p of B.personas) for (const pose of CFG.poses.map(x => x.id).filter(x => B.poses.includes(x))) add('model', p, pose);
  for (const pose of CFG.product_poses.map(x => x.id).filter(x => B.product.includes(x))) add('product', null, pose);
  if (B.kit) add('kit', null, 'kit');
  B.shots = out;
  renderShots(); renderSummary();
}
function renderShots() {
  $('#bShotCount').textContent = `— ${B.shots.length} шт.` + (B.shots.length > 16 ? ' (много: каждый ~40 с и деньги)' : '');
  $('#bShots').innerHTML = B.shots.length ? `<tr><th>#</th><th>Модель</th><th>Ракурс</th><th>Сцена</th><th>Уточнение</th><th></th></tr>` +
    B.shots.map((s, i) => `<tr><td>${i + 1}</td><td>${esc(who(s))}</td><td>${esc(label('poses', s.pose))}</td>
      <td><select onchange="B.shots[${i}].scene=this.value">${CFG.scenes.map(c => `<option value="${c.id}" ${c.id === s.scene ? 'selected' : ''}>${esc(c.label)}</option>`).join('')}</select></td>
      <td><input type="text" value="${esc(s.note)}" placeholder="например: улыбается, брызги" oninput="B.shots[${i}].note=this.value"></td>
      <td><button class="btn sm ghost" onclick="B.shots.splice(${i},1);renderShots();renderSummary()">✕</button></td></tr>`).join('')
    : '<tr><td class="muted">Выберите модели и ракурсы</td></tr>';
}
function renderSummary() {
  const d = curDesign();
  const missing = (B.shots.some(s => s.kind === 'model') ? B.personas : []).filter(p => !(PERSONAS.find(x => x.id === p) || {}).ref);
  const groups = [...new Set(B.personas.map(p => (PERSONAS.find(x => x.id === p) || {}).group))];
  const noSheet = groups.filter(g => !(SHEETS.find(s => s.id === g) || {}).sheet);
  $('#bSummary').innerHTML = `<div><b>${esc(d ? d.name : '—')}</b> · ${d ? sidesText(d) : ''}</div>
    <div>Кадров: <b>${B.shots.length}</b> (~${Math.ceil(B.shots.length / 4) * 40} с), 3:4, 2K</div>
    ${missing.length ? `<div class="banner" style="margin-top:8px">Нет эталона: ${missing.map(m => esc(label('personas', m))).join(', ')}</div>` : ''}
    ${noSheet.length ? `<div class="banner" style="margin-top:8px">Нет листа ракурсов: ${noSheet.map(g => esc(label('groups', g))).join(', ')}</div>` : ''}`;
}
$('#bGo').onclick = async () => {
  if (!B.design) return toast('Выберите дизайн', true);
  try {
    const r = await api('/api/packs', { method: 'POST', body: { design: B.design, shots: B.shots } });
    toast('Фотосессия запущена'); openPack(r.id);
  } catch (e) { toast(e.message, true); }
};

// ---------- packs ----------
async function loadPacks() {
  const ps = await api('/api/packs');
  $('#packList').innerHTML = ps.map(p => `<div class="row" style="cursor:pointer" onclick="openPack('${p.id}')">
    ${p.cover ? `<img src="${p.cover}" style="width:48px;height:64px;object-fit:cover;border-radius:6px">` : '<div style="width:48px;height:64px;background:#EAE7E1;border-radius:6px"></div>'}
    <div class="grow"><div><b>${esc(p.design_name)}</b></div><div class="muted">${new Date(p.created * 1000).toLocaleString('ru')} · ${p.n_ok}/${p.n_shots} фото · ${fmtSize(p.size)}</div></div>${statusBadge(p.status)}
    <button class="btn sm ghost pack-del" title="Удалить фотосессию" onclick="deletePack('${p.id}', event)">✕</button></div>`).join('') || '<span class="muted">Пока нет</span>';
}

let PACK = null, packTimer = null;
function closePack() { PACK = null; clearInterval(packTimer); $('#packView').classList.add('hide'); $('#builder').classList.remove('hide'); }
async function openPack(id) {
  showTab('cards');
  $('#builder').classList.add('hide'); $('#packView').classList.remove('hide');
  clearInterval(packTimer);
  await refreshPack(id, true);
  packTimer = setInterval(() => refreshPack(id), 3000);
}
async function refreshPack(id, force) {
  const p = await api('/api/packs/' + id);
  const busy = p.status === 'running' || p.status === 'queued' || p.shots.some(s => s.status === 'running');
  const sig = JSON.stringify([p.status, p.zip, p.shots.map(s => s.status + s.url)]);
  if (!force && PACK && sig === PACK._sig) return;
  PACK = p; PACK._sig = sig;
  renderPack();
  if (!busy) { clearInterval(packTimer); loadPacks(); loadStorage(); }
}
function renderPack() {
  const p = PACK;
  $('#packView').innerHTML = `
    <div class="row"><button class="btn sm" onclick="closePack()">← Назад</button><h2 class="grow">${esc(p.design_name)} <span class="muted small">${esc(p.id)}</span></h2>
      ${statusBadge(p.status)} ${p.zip ? `<a class="btn primary" href="${p.zip}" download>Скачать ZIP</a>` : ''}
      <button class="btn pack-del" onclick="deletePack('${p.id}')">Удалить фотосессию</button></div>
    <div class="panel stack"><div class="row"><h3 class="grow">Фото (${p.shots.filter(s => s.url).length}/${p.shots.length})</h3>
      <span class="muted small">клик — крупно; в углу — гайд размещения принта; «↻» — перегенерировать с уточнением</span></div>
      <div class="shots">${p.shots.map((s, i) => `<div class="shot">
        <div class="img" style="${s.url ? `background-image:url('${s.url}')` : ''}" ${s.url ? `onclick="zoom('${s.url}')"` : ''}>${s.url ? '' : s.status === 'error' ? 'ошибка' : '<span class="spin"></span>'}
          <img class="gmini" src="${s.guide}" onclick="event.stopPropagation();zoom('${s.guide}')"></div>
        <div class="meta"><div><b>${i + 1}.</b> ${esc(who(s))} · ${esc(label('poses', s.pose))}</div><div class="muted">${esc(label('scenes', s.scene))}${s.note ? ' · ' + esc(s.note) : ''}</div>
          ${s.error ? `<div class="small" style="color:var(--err)">${esc(s.error)}</div>` : ''}
          ${s.qa ? `<div class="small" style="color:${s.qa.ok ? 'var(--ok)' : 'var(--warn)'}">${s.qa.ok ? '✓ проверка пройдена' : '⚠ ' + esc(s.qa.problems || 'есть замечания')}${s.qa.score ? ` · ${s.qa.score}/10` : ''}</div>` : ''}
          <div class="row">${statusBadge(s.status)}<button class="btn sm" ${s.status === 'running' ? 'disabled' : ''} onclick="regenShot(${i})">↻</button>
            <button class="btn sm ghost del" title="Удалить кадр" ${s.status === 'running' ? 'disabled' : ''} onclick="deleteShot(${i})">🗑</button></div></div></div>`).join('')}</div></div>`;
}
async function regenShot(i) {
  const note = prompt('Уточнение для кадра (необязательно):', PACK.shots[i].note || '');
  if (note === null) return;
  try {
    await api(`/api/packs/${PACK.id}/shots/${i}/regen`, { method: 'POST', body: { note } });
    PACK.shots[i].status = 'running'; renderPack();
    clearInterval(packTimer); packTimer = setInterval(() => refreshPack(PACK.id), 3000);
  } catch (e) { toast(e.message, true); }
}

// ---------- storage and cleanup ----------
const fmtSize = b => b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(2).replace('.', ',') + ' ГБ' : Math.max(1, Math.round(b / 1024 ** 2)) + ' МБ';
async function loadStorage() {
  let s;
  try { s = await api('/api/storage'); } catch { return; }
  const pct = s.used / s.limit;
  const col = pct > 1 ? 'var(--err)' : pct > 0.8 ? 'var(--warn)' : 'var(--ok)';
  $('#storageBtn').innerHTML = `${fmtSize(s.used)} из ${Math.round(s.limit / 1024 ** 3)} ГБ<span class="bar"><i style="width:${Math.min(100, pct * 100)}%;background:${col}"></i></span>`;
  return s;
}
async function openStorage() {
  const [s, ps] = await Promise.all([loadStorage(), api('/api/packs')]);
  ps.sort((a, b) => b.size - a.size);
  modal(`<h2>Хранилище: ${fmtSize(s.used)} из ${Math.round(s.limit / 1024 ** 3)} ГБ</h2>
    <table class="t" style="margin:12px 0">${Object.entries(s.parts).map(([k, v]) => `<tr><td>${esc(k)}</td><td style="text-align:right">${fmtSize(v)}</td></tr>`).join('')}</table>
    <h3>Фотосессии, самые большие сверху</h3>
    <div class="stack small" style="margin-top:10px">${ps.map(p => `<div class="row">
      ${p.cover ? `<img src="${p.cover}" style="width:36px;height:48px;object-fit:cover;border-radius:6px">` : ''}
      <div class="grow"><b>${esc(p.design_name)}</b> <span class="muted">${new Date(p.created * 1000).toLocaleString('ru')} · ${p.n_ok} фото</span></div>
      <b>${fmtSize(p.size)}</b>
      <button class="btn sm" onclick="closeModal();openPack('${p.id}')">Открыть</button>
      <button class="btn sm pack-del" onclick="deletePack('${p.id}', event, true)">Удалить</button></div>`).join('') || '<span class="muted">Нет фотосессий</span>'}</div>
    <p class="muted small">Удалить отдельный кадр можно в самой фотосессии (кнопка 🗑 на кадре).</p>`);
}
$('#storageBtn').onclick = openStorage;
async function deletePack(id, ev, fromStorage) {
  if (ev) ev.stopPropagation();
  if (!confirm('Удалить фотосессию целиком? Все её фото и архив будут удалены безвозвратно.')) return;
  try {
    await api('/api/packs/' + id, { method: 'DELETE' });
    toast('Фотосессия удалена');
    if (PACK && PACK.id === id) closePack();
    loadPacks();
    if (fromStorage) openStorage(); else loadStorage();
  } catch (e) { toast(e.message, true); }
}
async function deleteShot(i) {
  if (!confirm(`Удалить кадр ${i + 1}? Файл будет удалён безвозвратно.`)) return;
  try {
    PACK = await api(`/api/packs/${PACK.id}/shots/${i}`, { method: 'DELETE' });
    renderPack(); loadStorage(); toast('Кадр удалён');
  } catch (e) { toast(e.message, true); }
}
setInterval(loadStorage, 30000);

// ---------- cap shapes ----------
const shapeLabel = id => ((CFG.shapes || []).find(s => s.id === id) || {}).label || id;
function initShapes() {
  $('#dShape').innerHTML += CFG.shapes.filter(s => s.id.startsWith('kid_') || s.pu).map(s => `<option value="${s.id}">${esc(s.label)}</option>`).join('');
  $('#dShape').onchange = () => {   // kids character caps: kids preset, the same character on both sides
    const sh = CFG.shapes.find(s => s.id === $('#dShape').value);
    $('#dLogoBox').classList.toggle('hide', !(sh && sh.id.startsWith('kid_')));
    $('#dPuBox').classList.toggle('hide', !(sh && sh.pu));
    if (sh && sh.pu) { $('#dPreset').value = sh.id === 'pu_kids' ? 'kids' : 'free'; $('#dSides').value = 'A'; }
    if (sh && sh.id.startsWith('kid_')) {
      $('#dPreset').value = 'kids';
      // ears / horns: face on the front half, back plain; fish / dragon: the same character on both sides
      $('#dSides').value = sh.panel === 'front' ? 'A' : 'ABm';
    }
  };
}

// ---------- constructor: new models from existing stencils, own colours and shape ----------
const C = { src: null, ways: [], sources: [], ral: [] };
async function initConstructor() {
  if (!C.ral.length) C.ral = await api('/api/ral');
  C.sources = [...(C.uploads || []), ...await api('/api/constructor/sources')];
  $('#cSources').innerHTML = C.sources.map(s => {
    const d = DESIGNS.find(x => x.slug === s.slug) || {};
    const img = s.thumb || d.hero;
    return `<div class="it ${s.slug === C.src ? 'on' : ''}" data-s="${s.slug}" onclick="pickSource('${s.slug}')">
      ${img ? `<img src="${img}" loading="lazy">` : ''}<div>${esc(s.name)}</div></div>`;
  }).join('');
  if (!C.src && C.sources.length) pickSource(C.sources[0].slug);
}
function pickSource(slug) {
  const s = C.sources.find(x => x.slug === slug);
  C.src = slug;
  C.pu = !!s.pu;
  $$('#cSources .it').forEach(el => el.classList.toggle('on', el.dataset.s === slug));
  // PU prints: only the cap colour (and the PU size) change; screen prints: any silicone shape, inks per colourway
  $('#cShape').innerHTML = CFG.shapes.filter(x => C.pu ? x.pu : !x.pu).map(x => `<option value="${x.id}">${esc(x.label)}</option>`).join('');
  $('#cSidesBox').classList.toggle('hide', C.pu);
  $('#cPlaceBox').classList.toggle('hide', !C.pu);
  setPlace(0, 0, 1, true);
  // own prints get the BRAND logo by default; generated PU prints already carry BRAND lettering
  setLogo({ kind: s.upload ? 'adult' : 'none', id: null, hex: logoContrast(s.base), x: 0.24, y: 0.82, s: 0.2 }, true);
  $('#cShape').value = s.shape;
  $('#cSides').value = s.side_b === 'own' ? 'AB' : s.side_b === 'mirror' ? 'mirror' : 'A';
  C.prev = [];
  C.ways = [{ cap: s.base, inks: [...s.inks] }, ...s.variants.filter(v => v.inks.length === s.inks.length).map(v => ({ cap: v.hex, inks: [...v.inks] }))];
  renderWays(); preview();
}
const ralOf = hex => C.ral.find(r => r.hex.toUpperCase() === (hex || '').toUpperCase());
function swatch(hex, w, k) {
  const r = ralOf(hex);
  return `<button class="btn sm" style="display:inline-flex;gap:6px;align-items:center" onclick="openRal(${w},${k})">
    <span class="dot" style="background:${hex}"></span>${r ? esc(r.code) : hex}</button>`;
}
function renderWays() {
  const src = C.sources.find(x => x.slug === C.src);
  C.prev = C.prev || [];
  $('#cWays').innerHTML = C.ways.map((w, i) => `<div class="cway">
    <div class="ctl">
      <div class="row"><b class="grow">${i === 0 ? 'Основная' : 'Вариант ' + i}</b>
        ${i ? `${C.pu ? '' : `<button class="btn sm" onclick="fixWay(${i})" title="заменить плохо видимые краски">подобрать краски</button>`}
               <button class="btn sm ghost" onclick="C.ways.splice(${i},1);C.prev.splice(${i},1);renderWays();preview()">✕</button>` : ''}</div>
      <div class="row"><span class="small muted" style="width:62px">шапочка</span> ${swatch(w.cap, i, -1)}</div>
      ${C.pu ? '<div class="small muted">полноцветный принт без изменений</div>'
             : `<div class="row"><span class="small muted" style="width:62px">краски</span> ${w.inks.map((h, k) => swatch(h, i, k) + `<span class="small" id="cde-${i}-${k}"></span>`).join(' ')}</div>`}
    </div>
    <div class="pv">
      <figure><img id="cpvA-${i}" src="${(C.prev[i] || {}).A || ''}" ${C.pu && i === 0 ? 'style="cursor:grab;touch-action:none" title="тяните — сдвиг, колесо — размер"' : 'onclick="zoom(this.src)"'} alt="" draggable="false"><figcaption>сторона A (слева${C.pu ? '' : ', логотип'})${C.pu && i === 0 ? ' · тяните мышью' : ''}</figcaption></figure>
      <figure><img id="cpvB-${i}" src="${(C.prev[i] || {}).B || ''}" onclick="zoom(this.src)" alt=""><figcaption>сторона B</figcaption></figure>
    </div></div>`).join('');
  C.ways.forEach((w, i) => contrastMarks(i));
  $('#cAddWay').disabled = C.ways.length >= 3;
}
function deltaE(a, b) {   // CIE76 in the browser, enough for a warning (the server uses CIEDE2000)
  const lab = h => { const c = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255).map(v => v > 0.04045 ? ((v + 0.055) / 1.055) ** 2.4 : v / 12.92);
    let x = (c[0] * 0.4124 + c[1] * 0.3576 + c[2] * 0.1805) / 0.95047, y = c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722, z = (c[0] * 0.0193 + c[1] * 0.1192 + c[2] * 0.9505) / 1.08883;
    const f = t => t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116; [x, y, z] = [f(x), f(y), f(z)];
    return [116 * y - 16, 500 * (x - y), 200 * (y - z)]; };
  const p = lab(a), q = lab(b); return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
}
function contrastMarks(i) {
  const w = C.ways[i];
  w.inks.forEach((h, k) => { const el = $(`#cde-${i}-${k}`); if (el) el.textContent = deltaE(h, w.cap) < 30 ? '⚠' : ''; });
}
function openRal(w, k) {
  openRalCb(k < 0 ? C.ways[w].cap : C.ways[w].inks[k], k < 0 ? 'Цвет шапочки' : 'Краска ' + (k + 1), hex => setColour(w, k, hex));
}
function pickRal(hex) { const cb = C.ralCb; closeModal(); cb && cb(hex); }
function openRalCb(cur, title, cb) {
  C.ralCb = cb;
  modal(`<h2>${esc(title)} — RAL Classic</h2>
    <input type="text" id="ralQ" placeholder="поиск: код, название (EN / 中文)" style="margin:10px 0" oninput="filterRal()">
    <div id="ralGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:6px">
    ${C.ral.map(r => `<div class="ralc" data-q="${esc((r.code + ' ' + r.en + ' ' + r.zh).toLowerCase())}" onclick="pickRal('${r.hex}')"
      style="cursor:pointer;border:2px solid ${r.hex === cur ? 'var(--accent)' : 'transparent'};border-radius:8px;padding:3px;font-size:11px">
      <div style="height:42px;border-radius:6px;background:${r.hex};border:1px solid #0002"></div>${esc(r.code)}<br><span class="muted">${esc(r.en)}</span></div>`).join('')}</div>`);
}
function filterRal() { const q = $('#ralQ').value.toLowerCase(); $$('#ralGrid .ralc').forEach(el => el.style.display = el.dataset.q.includes(q) ? '' : 'none'); }
function setColour(w, k, hex) { if (k < 0) C.ways[w].cap = hex; else C.ways[w].inks[k] = hex; closeModal(); renderWays(); preview(); }
async function fixWay(i) {
  if (!C.pu) C.ways[i].inks = await api('/api/colorways/fix', { method: 'POST', body: { cap: C.ways[i].cap, inks: C.ways[0].inks, prefer: [C.ways[0].cap] } });
  renderWays(); preview();
}
$('#cAddWay').onclick = async () => {
  const w0 = C.ways[0];
  const cap = (C.ral.find(r => r.code === 'RAL 9003') || {}).hex || '#F4F8F4';
  C.ways.push({ cap, inks: [...w0.inks] }); await fixWay(C.ways.length - 1);
};
$('#cShape').onchange = $('#cSides').onchange = () => preview();
// PU: the user's own print (no AI) and the BRAND logo layer
$('#cUpload').onchange = async e => {
  const f = e.target.files[0]; e.target.value = '';
  if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await api('/api/refs', { method: 'POST', body: fd });
    const s = { slug: 'upload:' + r.id, name: f.name.replace(/\.[^.]+$/, '').slice(0, 40) || 'Свой принт', shape: 'pu_kids', pu: true, upload: true,
                base: (C.ral.find(x => x.code === 'RAL 9003') || {}).hex || '#F4F8F4', inks: [], variants: [], thumb: URL.createObjectURL(f) };
    C.uploads = [s, ...(C.uploads || [])];
    await initConstructor(); pickSource(s.slug);
    if (!$('#cName').value) $('#cName').value = s.name;
  } catch (err) { toast(err.message, true); }
};
function logoContrast(cap) { return deltaE(cap, '#FFFFFF') > 45 ? ((C.ral.find(x => x.code === 'RAL 9003') || {}).hex || '#F4F8F4') : ((C.ral.find(x => x.code === 'RAL 9005') || {}).hex || '#0A0A0D'); }
let logoT = 0;
function setLogo(l, silent) {
  C.logo = { ...C.logo, ...l };
  C.logo.s = Math.max(0.05, Math.min(0.6, C.logo.s)); C.logo.x = Math.max(0, Math.min(1, C.logo.x)); C.logo.y = Math.max(0, Math.min(1, C.logo.y));
  $('#cLogo').value = C.logo.kind;
  $('#cLs').value = Math.round(C.logo.s * 100); $('#cLsv').textContent = $('#cLs').value + '%';
  const r = ralOf(C.logo.hex);
  $('#cLogoColour').innerHTML = `<span class="dot" style="display:inline-block;vertical-align:-3px;background:${C.logo.hex}"></span> ${r ? esc(r.code) : C.logo.hex}`;
  $('#cLogoS').classList.toggle('hide', C.logo.kind === 'none');
  $('#cLogoColour').classList.toggle('hide', !['adult', 'kids'].includes(C.logo.kind));
  $('#cLogoGen').classList.toggle('hide', C.logo.kind !== 'styled');
  $('#cLogoGen').textContent = C.logo.id ? 'Ещё вариант' : 'Сгенерировать';
  $('#cLogoImg').classList.toggle('hide', !(C.logo.kind === 'styled' && C.logo.id));
  if (C.logo.id) $('#cLogoImg').src = '/api/logos/' + C.logo.id;
  if (C.logo.kind === 'styled' && !C.logo.id) return;   // nothing to draw until generated
  if (!silent) { clearTimeout(logoT); logoT = setTimeout(preview, 120); }
}
C.logo = { kind: 'none', hex: '#F4F8F4', x: 0.24, y: 0.82, s: 0.2 };
$('#cLogo').onchange = () => { setLogo({ kind: $('#cLogo').value }); if ($('#cLogo').value === 'styled' && !C.logo.id) $('#cLogoGen').click(); };
$('#cLogoGen').onclick = async () => {
  const b = $('#cLogoGen'); b.disabled = true; b.innerHTML = '<span class="spin"></span> Рисую…';
  try {
    const r = await api('/api/constructor/styled_logo', { method: 'POST', body: { src: C.src } });
    setLogo({ kind: 'styled', id: r.id });
  } catch (e) { toast(e.message, true); setLogo({}, true); }
  b.disabled = false;
};
$('#cLs').oninput = () => setLogo({ s: $('#cLs').value / 100 });
$('#cLogoColour').onclick = () => openRalCb(C.logo.hex, 'Цвет логотипа', hex => setLogo({ hex }));

// PU: move / scale the print (fractions of the cap width / height, scale 1 = default)
C.place = { x: 0, y: 0, s: 1 };
let placeT = 0;
function setPlace(x, y, s, silent) {
  C.place = { x: Math.max(-0.45, Math.min(0.45, x)), y: Math.max(-0.45, Math.min(0.45, y)), s: Math.max(0.3, Math.min(1.6, s)) };
  $('#cS').value = Math.round(C.place.s * 100); $('#cSv').textContent = $('#cS').value + '%';
  $('#cX').value = Math.round(C.place.x * 100); $('#cXv').textContent = $('#cX').value + '%';
  $('#cY').value = Math.round(C.place.y * 100); $('#cYv').textContent = $('#cY').value + '%';
  if (!silent) { clearTimeout(placeT); placeT = setTimeout(preview, 120); }
}
$('#cS').oninput = () => setPlace(C.place.x, C.place.y, $('#cS').value / 100);
$('#cX').oninput = () => setPlace($('#cX').value / 100, C.place.y, C.place.s);
$('#cY').oninput = () => setPlace(C.place.x, $('#cY').value / 100, C.place.s);
$('#cPlaceReset').onclick = () => setPlace(0, 0, 1);
// drag on the main colourway's side-A preview; wheel = scale
document.addEventListener('pointerdown', e => {
  if (!C.pu || e.target.id !== 'cpvA-0') return;
  e.preventDefault();
  const img = e.target, r = img.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY, p0 = { ...C.place };
  img.setPointerCapture(e.pointerId); img.style.cursor = 'grabbing';
  const toLogo = C.logo.kind !== 'none' && (document.querySelector('input[name=cDrag]:checked') || {}).value === 'logo';
  const l0 = { ...C.logo };
  const move = ev => toLogo ? setLogo({ x: l0.x + (ev.clientX - x0) / r.width, y: l0.y + (ev.clientY - y0) / r.height })
                            : setPlace(p0.x + (ev.clientX - x0) / r.width, p0.y + (ev.clientY - y0) / r.height, p0.s);
  const up = () => { img.removeEventListener('pointermove', move); img.style.cursor = 'grab'; };
  img.addEventListener('pointermove', move); img.addEventListener('pointerup', up, { once: true });
});
document.addEventListener('wheel', e => {
  if (!C.pu || e.target.id !== 'cpvA-0') return;
  e.preventDefault();
  if (C.logo.kind !== 'none' && (document.querySelector('input[name=cDrag]:checked') || {}).value === 'logo') setLogo({ s: C.logo.s * (e.deltaY < 0 ? 1.05 : 0.95) });
  else setPlace(C.place.x, C.place.y, C.place.s * (e.deltaY < 0 ? 1.05 : 0.95));
}, { passive: false });

let prevT = 0;
async function preview() {
  if (!C.src) return;
  const t = ++prevT; $('#cPrevState').innerHTML = '<span class="spin"></span>';
  try {
    const r = await api('/api/constructor/preview', { method: 'POST', body: { src: C.src, shape: $('#cShape').value, sides: $('#cSides').value,
      place: C.pu ? C.place : null, logo: C.pu ? C.logo : null,
      ways: C.ways.map(w => ({ cap: w.cap, inks: C.pu ? [] : w.inks })) } });
    if (t !== prevT) return;
    C.prev = r.ways;   // each colourway's preview sits next to its colour controls
    r.ways.forEach((p, i) => { const a = $(`#cpvA-${i}`), b = $(`#cpvB-${i}`); if (a) a.src = p.A; if (b) b.src = p.B; });
    $('#cPrevState').textContent = '';
  } catch (e) { $('#cPrevState').textContent = e.message; }
}
$('#cSave').onclick = async () => {
  const [w0, ...rest] = C.ways;
  const body = { src: C.src, shape: $('#cShape').value, sides: C.pu ? 'A' : $('#cSides').value, base: w0.cap, inks: C.pu ? [] : w0.inks,
                 place: C.pu ? C.place : null, logo: C.pu ? C.logo : null,
                 variants: rest.map(w => ({ hex: w.cap, inks: w.inks })), name: $('#cName').value.trim(), slug: $('#cSlug').value.trim() };
  try {
    const j = await api('/api/constructor/save', { method: 'POST', body });
    $('#cSave').disabled = true;
    watchJob(j.id, jj => { $('#cSave').disabled = false; if (jj.status === 'done') { toast('Модель сохранена: ' + jj.result.slug); loadDesigns(); } else toast('Не удалось, см. лог', true); }, $('#cJob'));
  } catch (e) { toast(e.message, true); }
};

// ---------- export: Excel with mockups ----------
const ESEL = new Set();
function renderExport() {
  const types = [...new Set(DESIGNS.map(d => d.type))].sort();
  const cur = $('#eType').value;
  $('#eType').innerHTML = '<option value="">все</option>' + types.map(t => `<option ${t === cur ? 'selected' : ''}>${esc(t)}</option>`).join('');
  const list = DESIGNS.filter(d => !$('#eType').value || d.type === $('#eType').value);
  $('#eGrid').innerHTML = list.map(d => `<label class="tile" style="cursor:pointer;${ESEL.has(d.slug) ? 'outline:3px solid var(--accent)' : ''}">
    <div class="img" style="background-image:url('${d.hero || d.mockup}')"></div>
    <div class="body"><div class="row"><input type="checkbox" ${ESEL.has(d.slug) ? 'checked' : ''} onchange="toggleExport('${d.slug}', this.checked)">
      <span class="name grow">${esc(d.name)}</span></div>
      <div class="row small"><span class="badge">${esc(d.type)}</span><span class="muted">${esc(d.slug)}</span></div></div></label>`).join('');
  const nways = [...ESEL].reduce((n, s) => n + 1 + Math.min(2, ((DESIGNS.find(d => d.slug === s) || {}).variants || []).length), 0);
  $('#eCount').textContent = ESEL.size ? `выбрано моделей: ${ESEL.size}, цветов: ${nways}` : '';
}
function toggleExport(slug, on) { on ? ESEL.add(slug) : ESEL.delete(slug); renderExport(); }
$('#eType').onchange = renderExport;
$('#eAll').onclick = () => { DESIGNS.filter(d => !$('#eType').value || d.type === $('#eType').value).forEach(d => ESEL.add(d.slug)); renderExport(); };
$('#eNone').onclick = () => { ESEL.clear(); renderExport(); };
$('#eSave').onclick = async () => {
  if (!ESEL.size) return toast('Отметьте шапочки', true);
  const order = DESIGNS.map(d => d.slug).filter(s => ESEL.has(s));
  const btn = $('#eSave'), label = btn.textContent;
  if (!window.showDirectoryPicker) {   // Firefox / Safari: the same structure as a ZIP
    btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Собираю ZIP…';
    try {
      const r = await fetch('/api/export/zip', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slugs: order }) });
      if (!r.ok) throw new Error(r.statusText);
      const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(await r.blob()), download: `${CFG.brand}_export.zip` });
      document.body.appendChild(a); a.click(); a.remove(); toast('Браузер не умеет выбирать папку — скачан ZIP с той же структурой');
    } catch (e) { toast(e.message, true); }
    btn.disabled = false; btn.textContent = label; return;
  }
  let dir;
  try { dir = await window.showDirectoryPicker({ mode: 'readwrite' }); } catch { return; }   // cancelled
  btn.disabled = true;
  try {
    btn.innerHTML = '<span class="spin"></span> Готовлю файлы…';
    const pkg = await api('/api/export/package', { method: 'POST', body: { slugs: order } });
    let n = 0;
    for (const f of pkg.files) {
      const parts = f.path.split('/');
      let d = dir;
      for (const p of parts.slice(0, -1)) d = await d.getDirectoryHandle(p, { create: true });
      const fh = await d.getFileHandle(parts[parts.length - 1], { create: true });
      const w = await fh.createWritable();
      await w.write(await (await fetch(f.url)).blob()); await w.close();
      btn.innerHTML = `<span class="spin"></span> ${++n} / ${pkg.files.length}`;
    }
    toast(`Сохранено в «${dir.name}»: ${pkg.files.length} файлов`);
  } catch (e) { toast(e.message, true); }
  btn.disabled = false; btn.textContent = label;
};
$('#eGo').onclick = async () => {
  if (!ESEL.size) return toast('Отметьте шапочки', true);
  const btn = $('#eGo'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Формирую…';
  try {
    const order = DESIGNS.map(d => d.slug).filter(s => ESEL.has(s));   // the catalogue order
    const r = await fetch('/api/export/mockups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slugs: order }) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const blob = await r.blob();
    const name = decodeURIComponent((r.headers.get('Content-Disposition') || '').split("''")[1] || 'mockups.xlsx');
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a); a.click(); a.remove();
    toast('Файл скачан');
  } catch (e) { toast(e.message, true); }
  btn.disabled = false; btn.textContent = 'Скачать Excel';
};

// ---------- boot ----------
(async () => {
  CFG = await api('/api/config');
  if (!CFG.key_set) $('#keyBanner').classList.remove('hide');
  $('#brandName').textContent = CFG.brand || 'BRAND';
  initShapes();
  window.addEventListener('hashchange', () => { const t = location.hash.slice(1); if (document.getElementById('tab-' + t)) showTab(t); });
  await Promise.all([loadDesigns(), loadPersonas()]);
  pollJobs(); loadStorage();
  { const t = location.hash.slice(1); if (document.getElementById('tab-' + t)) showTab(t); }   // open a tab by link, e.g. #constructor
})();
