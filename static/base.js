// 每一頁共用。CSP 不允許 inline script / onxxx 屬性，頁面上的行為都寫在 static/*.js

// 亮色 / 深色切換
(() => {
  const btn = document.getElementById('theme_toggle');
  const root = document.documentElement;
  const render = () => {
    const dark = root.dataset.theme === 'dark';
    btn.textContent = dark ? '☾' : '☀';
    btn.title = btn.ariaLabel = dark ? '切換成亮色' : '切換成深色';
  };
  btn.addEventListener('click', () => {
    if (root.dataset.theme === 'dark') delete root.dataset.theme; else root.dataset.theme = 'dark';
    try { localStorage.setItem('roster-theme', root.dataset.theme || 'light'); } catch (e) {}
    render();
  });
  render();
})();

// 顯示登入有效時間（瀏覽器當地時間）；到期後重新整理，伺服器會導向登入頁
(() => {
  const el = document.getElementById('token_exp');
  if (!el) return;
  const exp = Number(el.dataset.exp) * 1000;
  el.textContent = '有效至 ' + new Date(exp).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
  setTimeout(() => location.reload(), Math.max(exp - Date.now(), 0) + 1000);
})();

// <form data-confirm="訊息">：送出前先確認
document.addEventListener('submit', e => {
  const msg = e.target.dataset.confirm;
  if (msg && !confirm(msg)) e.preventDefault();
});

// <select data-autosubmit>：選了就送出所在的表單
document.addEventListener('change', e => {
  if (e.target.matches('[data-autosubmit]')) e.target.form.submit();
});

// 彈窗：[data-close] 按鈕或點背景關閉
document.querySelectorAll('dialog').forEach(dlg => {
  dlg.querySelectorAll('[data-close]').forEach(btn => btn.addEventListener('click', () => dlg.close()));
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
});

// 主管取消已核准的申請（請假 / 加班的審核紀錄）：先看逐日影響，填原因後才能確認取消，避免誤觸
(() => {
  const dlg = document.getElementById('cancel_dialog');
  if (!dlg) return;
  const form = dlg.querySelector('form');
  const q = name => dlg.querySelector(`[data-f="${name}"]`);
  const note = form.elements.note;
  let ready = false;
  const sync = () => { q('confirm').disabled = !(ready && note.value.trim()); };
  note.addEventListener('input', sync);
  document.querySelectorAll('[data-cancel-url]').forEach(btn => btn.addEventListener('click', async () => {
    form.action = btn.dataset.cancelUrl;
    note.value = '';
    ready = false;
    let d;
    try { d = await (await fetch(btn.dataset.previewUrl)).json(); }
    catch { d = {ok: false, error: '預覽失敗，請重新整理後再試'}; }
    ready = d.ok;
    q('title').textContent = `取消 ${btn.dataset.requestId}`;
    q('error').hidden = d.ok;
    q('error').textContent = d.ok ? '' : d.error;
    q('summary').textContent = d.ok ? `${d.employee}：取消後會影響以下 ${d.days.length} 天` : '';
    q('rows').replaceChildren(...(d.days || []).map(r => {
      const tr = document.createElement('tr');
      [r.date, r.before, r.after ?? '刪除'].forEach(v =>
        tr.appendChild(Object.assign(document.createElement('td'), {textContent: v})));
      return tr;
    }));
    sync();
    dlg.showModal();
    note.focus();
  }));
  form.addEventListener('submit', e => {
    if (!(ready && note.value.trim())) { e.preventDefault(); return; }
    q('confirm').disabled = true;   // 避免連點重複送出
  });
})();
