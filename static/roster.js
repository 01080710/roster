// 排班總覽頁。伺服器端的值由模板放在 data-* 屬性

// 年度總覽：點「上班 / 請假 / 加班」看逐日明細（內容一律用 textContent 寫入）
(() => {
  const dlg = document.getElementById('detail_dialog');
  const q = sel => dlg.querySelector(`[data-f="${sel}"]`);
  async function openDetail(kind, emp) {
    const params = new URLSearchParams({kind, year: dlg.dataset.year});
    if (dlg.dataset.month) params.set('month', dlg.dataset.month);
    if (emp) params.set('employee_id', emp);
    const res = await fetch(`${dlg.dataset.url}?${params}`);
    const d = await res.json();
    q('title').textContent = d.ok ? d.title : (d.error || '讀取失敗');
    q('cols').replaceChildren(...(d.columns || []).map(c => Object.assign(document.createElement('th'), {textContent: c})));
    q('rows').replaceChildren(...(d.rows || []).map(r => {
      const tr = document.createElement('tr');
      if (r.pending) tr.className = 's-PENDING';
      r.cells.forEach(v => tr.appendChild(Object.assign(document.createElement('td'), {textContent: v ?? ''})));
      return tr;
    }));
    q('empty').hidden = !d.ok || (d.rows || []).length > 0;
    dlg.showModal();
  }
  document.querySelectorAll('.pivot .drill').forEach(el =>
    el.addEventListener('click', () => openDetail(el.dataset.kind, el.dataset.emp)));
})();

// 選了請假類班別才顯示「請假核准狀態」
function bindApproval(shift, box) {
  const toggle = () => {
    const opt = shift.selectedOptions[0];
    box.style.display = opt && opt.dataset.status === 'Leave' ? '' : 'none';
  };
  shift.addEventListener('change', toggle);
  toggle();
  return toggle;
}

// 提交班表（有 USER_CREATE 才有這張表單）
(() => {
  const emp = document.getElementById('employee_id');
  if (!emp) return;
  const shift = document.getElementById('shift_code');
  const toggleMain = bindApproval(shift, document.getElementById('approval_box'));
  const applyDefaultShift = () => {
    const def = emp.selectedOptions[0]?.dataset.default;
    if (def && !shift.value) { shift.value = def; toggleMain(); }
  };
  emp.addEventListener('change', applyDefaultShift);
  applyDefaultShift();   // 員工已預選（例如 Agent 只能選自己）時，直接帶入預設班別
})();

// 修改彈窗（有 USER_EDIT 才有）
(() => {
  const dlg = document.getElementById('edit_dialog');
  if (!dlg) return;
  const dlgForm = dlg.querySelector('form');
  const toggleDlg = bindApproval(dlgForm.elements.shift_code, document.getElementById('dlg_approval_box'));
  const show = (name, text) => { dlg.querySelector(`[data-f="${name}"]`).textContent = text; };

  function openEdit(d, error) {
    const f = dlgForm.elements;
    f.edit_key.value = d.edit_key;
    f.employee_id.value = d.employee_id;
    f.start_date.value = d.start_date;
    f.shift_code.value = d.shift_code;
    f.leave_approval_status.value = d.leave_approval_status || '';
    f.remarks.value = d.remarks || '';
    show('edit_key', d.edit_key);
    show('who', `${d.employee_id} · ${d.full_name || ''}`);
    show('start_date', `${d.start_date} (${d.weekday || ''})`);
    show('version', `v${d.roster_version} · ${d.updatetime}`);
    const err = dlg.querySelector('[data-f="error"]');
    err.hidden = !error;
    err.textContent = error || '';
    toggleDlg();
    dlg.showModal();
  }

  document.querySelectorAll('[data-edit]').forEach(btn =>
    btn.addEventListener('click', () => openEdit(JSON.parse(btn.dataset.edit))));

  // 驗證失敗或 /?edit=<roster_key>：頁面載入後自動開啟
  if (dlg.dataset.open) openEdit(JSON.parse(dlg.dataset.open), dlg.dataset.error);
})();
