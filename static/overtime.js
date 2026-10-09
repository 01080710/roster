// 加班頁（有 OT_APPLY 才載入）。伺服器端的值由模板放在 data-* 屬性

// 依方式切換「時間」或「加班班別」欄位，並即時預覽天數 / 時數（伺服器逐日檢查）
(() => {
  const form = document.getElementById('ot_form');
  const f = form.elements;
  const out = document.getElementById('ot_preview');
  const toggle = () => form.querySelectorAll('[data-ot]').forEach(el => {
    const on = el.dataset.ot === f.mode.value;
    el.style.display = on ? '' : 'none';
    el.querySelectorAll('input, select').forEach(i => { i.disabled = !on; i.required = on && !('optional' in i.dataset); });
  });
  // 填時間：選日期後向伺服器取得可選的時段（依當天的班，避開上班時間），再依開始時間列出結束時間
  const startSel = f.start_time, endSel = f.end_time, shiftHint = document.getElementById('ot_shift_hint');
  let slots = [], slotSeq = 0;
  const fill = (sel, items, empty) => {
    const keep = sel.value || sel.dataset.value;
    sel.replaceChildren(new Option(items.length ? '請選擇' : empty, ''),
                        ...items.map(([value, label]) => new Option(label, value)));
    sel.value = items.some(([v]) => v === keep) ? keep : '';
    sel.dataset.value = '';
  };
  const fillEnds = () => {
    const s = slots.find(x => x.value === startSel.value);
    fill(endSel, s ? s.ends.map(e => [e.value, `${e.label}（${e.hours} 小時）`]) : [], '請先選開始時間');
  };
  async function loadSlots() {
    if (f.mode.value !== 'time' || !f.start_date.value) { slots = []; fill(startSel, [], '請先選日期'); fillEnds(); return; }
    const id = ++slotSeq;
    const q = new URLSearchParams({date: f.start_date.value});
    const d = await (await fetch(`${form.dataset.slotsUrl}?${q}`)).json();
    if (id !== slotSeq) return;
    slots = d.ok ? d.starts : [];
    shiftHint.className = d.ok ? 'hint' : 'hint flag';
    shiftHint.textContent = !d.ok ? d.error : (d.shift ? `當天的班：${d.shift}` : '當天沒有排上班，可自由選擇時段');
    fill(startSel, slots.map(x => [x.value, x.value]), d.ok ? '這天沒有可加班的時段' : '無法選擇');
    fillEnds();
    preview();
  }
  startSel.addEventListener('change', () => { fillEnds(); preview(); });

  let seq = 0;
  async function preview() {
    const unit = f.mode.value === 'unit';
    const ready = f.start_date.value && (unit ? f.shift_code.value : f.start_time.value && f.end_time.value);
    if (!ready) { out.textContent = ''; return; }
    const q = new URLSearchParams({mode: f.mode.value, start_date: f.start_date.value, end_date: f.end_date.value,
                                   shift_code: unit ? f.shift_code.value : '',
                                   start_time: unit ? '' : f.start_time.value, end_time: unit ? '' : f.end_time.value});
    const id = ++seq;
    try {
      const d = await (await fetch(`${form.dataset.previewUrl}?${q}`)).json();
      if (id !== seq) return;
      out.className = d.ok ? 'hint' : 'hint flag';
      out.textContent = d.ok ? `共 ${d.days} 天${d.hours ? `（${d.hours} 小時）` : ''}：${d.dates.join('、')}` : d.error;
    } catch { if (id === seq) out.textContent = ''; }
  }
  f.mode.addEventListener('change', () => { toggle(); loadSlots(); preview(); });
  f.start_date.addEventListener('change', loadSlots);
  ['start_date', 'end_date', 'end_time', 'shift_code'].forEach(n => f[n].addEventListener('change', preview));
  toggle();
  loadSlots();
  preview();
})();
