// 請假頁。伺服器端的值由模板放在 data-* 屬性

// 請假月曆：點日期看當天名單
(() => {
  const dlg = document.getElementById('cal_dialog');
  document.querySelectorAll('.cal button.day').forEach(btn => btn.addEventListener('click', () => {
    const d = JSON.parse(btn.dataset.day);
    dlg.querySelector('[data-f="title"]').textContent =
      `${d.date}（${d.weekday}）請假 ${d.approved} 人` + (d.pending ? `、待審 ${d.pending} 人` : '');
    dlg.querySelector('[data-f="rows"]').replaceChildren(...d.people.map(p => {
      const tr = document.createElement('tr');
      if (p.pending) tr.className = 's-PENDING';
      [p.name, p.team || '—', p.display, p.pending ? '待審核' : '已核准'].forEach(v =>
        tr.appendChild(Object.assign(document.createElement('td'), {textContent: v})));
      return tr;
    }));
    dlg.showModal();
  }));
})();

// 選假別 / 日期時即時預覽會請幾天（伺服器依行事曆略過休息日與國定假日）；有 LEAVE_APPLY 才有表單
(() => {
  const form = document.getElementById('leave_form');
  if (!form) return;
  const f = form.elements;
  const out = document.getElementById('leave_preview');
  let seq = 0;
  async function preview() {
    const portion = f.shift_code.selectedOptions[0]?.dataset.portion;
    f.end_date.disabled = !!portion && portion !== 'FD';     // 非全天假只能單日
    if (f.end_date.disabled) f.end_date.value = '';
    if (!f.shift_code.value || !f.start_date.value) { out.textContent = ''; return; }
    const q = new URLSearchParams({shift_code: f.shift_code.value, start_date: f.start_date.value,
                                   end_date: f.end_date.value});
    const id = ++seq;
    try {
      const d = await (await fetch(`${form.dataset.previewUrl}?${q}`)).json();
      if (id !== seq) return;
      out.className = d.ok ? 'hint' : 'hint flag';
      const periods = (d.periods || []).map(p => `當天的班：${p.shift}；請假 ${p.leave}`).join('、');
      out.textContent = d.ok ? `共 ${d.days} 天（略過休息日與國定假日）：${d.dates.join('、')}` + (periods ? `。${periods}` : '')
                             : d.error;
    } catch { if (id === seq) out.textContent = ''; }
  }
  ['shift_code', 'start_date', 'end_date'].forEach(n => f[n].addEventListener('change', preview));
  preview();
})();
