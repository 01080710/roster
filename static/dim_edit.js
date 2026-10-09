// 員工主檔編輯：「依角色套用預設」權限。各角色的預設權限由模板放在按鈕的 data-agent / data-all
document.getElementById('perm_default')?.addEventListener('click', e => {
  const role = (document.getElementById('role')?.value || '').trim();
  const allowed = JSON.parse(role === 'Agent' ? e.currentTarget.dataset.agent : e.currentTarget.dataset.all);
  document.querySelectorAll('input[name="permission"]').forEach(cb => { cb.checked = allowed.includes(cb.value); });
});
