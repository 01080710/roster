"""
網頁模板與表單 / JSON 輸入解析。

TEMPLATES 交給 Flask 的 DictLoader 使用：base.html 是共用版面，其他頁面以 {% extends %} 套用。
"""
import datetime as dt

from config import PIVOT_YEARS_AFTER, PIVOT_YEARS_BEFORE

BASE = """
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}Vantage Roster Situation{% endblock %}</title>
<style>
  :root { --ink:#1d2433; --muted:#667085; --line:#e4e7ec; --bg:#f6f7f9; --card:#fff;
          --accent:#1f3864; --ok:#067647; --warn:#b54708; --err:#b42318; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system, "Segoe UI", "Noto Sans TC", sans-serif; color:var(--ink); background:var(--bg); }
  main { max-width:1100px; margin:0 auto; padding:24px 16px 64px; }
  nav { background:var(--accent); }
  nav div { max-width:1100px; margin:0 auto; padding:0 16px; display:flex; gap:4px; flex-wrap:wrap; }
  nav a { color:#c7d2e6; text-decoration:none; padding:12px 14px; font-weight:600; }
  nav a.on, nav a:hover { color:#fff; background:rgba(255,255,255,.12); }
  h1 { font-size:22px; margin:0 0 4px; }
  h2 { font-size:16px; margin:0 0 12px; }
  .sub { color:var(--muted); margin:0 0 20px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:20px; margin-bottom:20px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px 18px; }
  label { display:block; font-size:13px; font-weight:600; margin-bottom:4px; }
  select, input[type=date], input[type=text], input[type=number], input[type=time], input[type=password] {
    width:100%; padding:8px 10px; border:1px solid #d0d5dd; border-radius:6px; font:inherit; background:#fff; }
  input:disabled { background:#f2f4f7; color:var(--muted); }
  .check { display:flex; align-items:center; gap:8px; font-weight:400; margin-top:6px; }
  .hint { font-size:12px; color:var(--muted); margin-top:4px; }
  button, a.btn { display:inline-block; margin-top:18px; background:var(--accent); color:#fff; border:0; border-radius:6px;
           padding:10px 22px; font:inherit; font-weight:600; cursor:pointer; text-decoration:none; }
  button.danger { background:#fff; color:var(--err); border:1px solid #fda29b; }
  a.back { margin-left:14px; color:var(--muted); }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th { color:var(--muted); font-weight:600; }
  td.msg { white-space:normal; }
  .scroll { overflow-x:auto; }
  .tag { display:inline-block; padding:1px 8px; border-radius:10px; font-size:12px; font-weight:600; }
  .created, .updated { background:#ecfdf3; color:var(--ok); }
  .skipped { background:#f2f4f7; color:var(--muted); }
  .error { background:#fef3f2; color:var(--err); }
  .flag { color:var(--warn); }
  .banner { padding:10px 14px; border-radius:8px; background:#fef3f2; color:var(--err); margin-bottom:16px; }
  .banner.ok { background:#ecfdf3; color:var(--ok); }
  .filter { display:flex; gap:10px; align-items:end; margin-bottom:12px; flex-wrap:wrap; }
  .filter select { width:auto; min-width:240px; }
  .filter button { margin-top:0; padding:8px 16px; }
  .head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; }
  .head h2 { margin:0; }
  .head a.btn { margin-top:0; padding:8px 16px; }
  .head select { width:auto; padding:6px 10px; }
  .pivot { max-height:420px; overflow:auto; border:1px solid var(--line); border-radius:6px; }
  .pivot table { width:auto; }
  .pivot th, .pivot td { padding:5px 8px; border-right:1px solid var(--line); text-align:center; }
  .pivot thead th { position:sticky; top:0; background:#f9fafb; z-index:2; line-height:1.3; }
  .pivot thead th small { display:block; font-weight:400; }
  .pivot .k { position:sticky; background:#fff; z-index:1; text-align:left; font-weight:600; }
  .pivot thead .k { background:#f9fafb; z-index:3; }
  .pivot .k1 { left:0; width:72px; min-width:72px; }
  .pivot .k2 { left:72px; width:72px; min-width:72px; }
  .pivot .k3 { left:144px; width:180px; min-width:180px; }
  .pivot .t1, .pivot .t2, .pivot .t3 { width:56px; min-width:56px; text-align:right; font-variant-numeric:tabular-nums; }
  .pivot .t1 { left:324px; }
  .pivot .t2 { left:380px; }
  .pivot .t3 { left:436px; border-right:2px solid #d0d5dd; }
  .pivot .wkend { background:#f2f4f7; }
  .pivot td.empty { color:#d0d5dd; }
  .s-SHIFT { background:#eaf1fb; color:#1f3864; }
  .s-LEAVE { background:#fef0c7; color:#93370d; }
  .s-OT { background:#fee4e2; color:#b42318; font-weight:600; }
  .s-OFF { background:#f2f4f7; color:#667085; }
  .s-ACTIVITY { background:#e3f6ec; color:#067647; }
  .legend { display:flex; gap:8px; flex-wrap:wrap; margin:0 0 12px; font-size:12px; }
  .legend span { padding:2px 10px; border-radius:10px; }
  .banner.info { background:#eaf1fb; color:var(--accent); }
  nav .brand { color:#fff; font-weight:700; padding:12px 18px 12px 0; letter-spacing:.2px; }
  td a { color:var(--accent); font-weight:600; }
  button.link { margin:0; padding:0; background:none; color:var(--accent); font-weight:600; font-size:13px; }
  button.link:hover { text-decoration:underline; }
  button.secondary { background:#fff; color:var(--ink); border:1px solid #d0d5dd; }
  dialog { border:0; border-radius:12px; padding:0; width:min(640px, calc(100vw - 32px));
           max-height:calc(100vh - 32px); color:var(--ink); box-shadow:0 20px 40px rgba(16,24,40,.25); }
  dialog::backdrop { background:rgba(16,24,40,.45); }
  dialog form { padding:20px 22px 22px; }
  dialog .close { margin:0; padding:2px 10px; background:none; color:var(--muted); font-size:22px; line-height:1; }
  dialog .actions { display:flex; justify-content:flex-end; gap:10px; }
  dl.meta { display:grid; grid-template-columns:max-content 1fr; gap:4px 14px; margin:0 0 16px;
            padding:12px 14px; background:var(--bg); border-radius:8px; font-size:13px; }
  dl.meta dt { color:var(--muted); }
  dl.meta dd { margin:0; font-weight:600; }
  nav form.who { margin-left:auto; display:flex; align-items:center; gap:10px; color:#c7d2e6; font-size:13px; }
  nav form.who .exp { opacity:.75; }
  nav form.who button { margin:0; padding:5px 12px; background:rgba(255,255,255,.12); font-size:13px; }
  .perms .check { margin-top:2px; }
  .perms button.link { margin-top:6px; }
  .login { max-width:380px; margin:48px auto; }
  .login input { margin-bottom:12px; }
  .login button { width:100%; }
</style>
</head>
<body>
<nav><div>
  <span class="brand">Vantage Roster Situation</span>
  {% if current_user %}
  <a href="{{ url_for('index') }}" {% if request.endpoint == 'index' %}class="on"{% endif %}>排班總覽</a>
  {% endif %}
  {% for k, label in nav_dims %}
  <a href="{{ url_for('dim_list', kind=k) }}"
     {% if request.view_args and request.view_args.get('kind') == k %}class="on"{% endif %}>{{ label }}</a>
  {% endfor %}
  {% if current_user %}
  <form class="who" method="post" action="{{ url_for('logout') }}">
    <span>{{ current_user.full_name }} · {{ current_user.role or '—' }}</span>
    {% if token_exp %}<span class="exp" id="token_exp" data-exp="{{ token_exp }}"></span>{% endif %}
    <button type="submit">登出</button>
  </form>
  {% endif %}
</div></nav>
<main>
{% block content %}{% endblock %}
</main>
<script>
  // 顯示登入有效時間（瀏覽器當地時間）；到期後重新整理，伺服器會導向登入頁
  (() => {
    const el = document.getElementById('token_exp');
    if (!el) return;
    const exp = Number(el.dataset.exp) * 1000;
    el.textContent = '有效至 ' + new Date(exp).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    setTimeout(() => location.reload(), Math.max(exp - Date.now(), 0) + 1000);
  })();
</script>
{% block script %}{% endblock %}
</body>
</html>
"""

ROSTER = """
{% extends "base.html" %}
{% macro shift_options(selected) %}
          <option value="">請選擇</option>
          {% for label, items in shift_groups %}
          <optgroup label="{{ label }}">
            {% for s in items %}
            <option value="{{ s.shift_code }}" data-status="{{ s.status_group }}"
              {% if selected == s.shift_code %}selected{% endif %}>
              {{ s.shift_code }} · {{ s.roster_display }}{% if s.shift_name != 'Shift ' ~ s.roster_display %} · {{ s.shift_name }}{% endif %}</option>
            {% endfor %}
          </optgroup>
          {% endfor %}
{% endmacro %}
{% macro approval_options(selected) %}
          <option value="">—</option>
          {% for a in approval_statuses %}
          <option {% if selected == a %}selected{% endif %}>{{ a }}</option>
          {% endfor %}
{% endmacro %}
{% block content %}
  <h1>Vantage Roster Situation</h1>
  <p class="sub">每人每天的排班、請假與加班狀況。上班 / 請假 / 加班天數為該年度小計（半天以 0.5 計）。</p>

  <div class="card">
    <form class="head" method="get">
      <h2>{{ pivot.year }} 年度總覽</h2>
      <select name="year" onchange="this.form.submit()">
        {% for y in pivot.years %}<option {% if y == pivot.year %}selected{% endif %}>{{ y }}</option>{% endfor %}
      </select>
    </form>
    <div class="legend">
      {% for code, label in situation_labels %}<span class="s-{{ code }}">{{ label }}</span>{% endfor %}
    </div>
    {% if pivot.rows %}
    <div class="pivot"><table>
      <thead><tr>
        <th class="k k1">team</th><th class="k k2">office_code</th><th class="k k3">full_name</th>
        <th class="k t1">上班</th><th class="k t2">請假</th><th class="k t3">加班</th>
        {% for c in pivot.columns %}<th {% if c.weekend %}class="wkend"{% endif %}>{{ c.label }}<small>{{ c.weekday }}</small></th>{% endfor %}
      </tr></thead>
      <tbody>
      {% for r in pivot.rows %}
      <tr>
        <td class="k k1">{{ r.team }}</td><td class="k k2">{{ r.office_code }}</td><td class="k k3">{{ r.full_name }}</td>
        <td class="k t1">{{ r.work }}</td><td class="k t2">{{ r.leave }}</td><td class="k t3">{{ r.ot }}</td>
        {% for v, s in r.cells %}<td class="{% if s %}s-{{ s }}{% elif pivot.columns[loop.index0].weekend %}wkend empty{% else %}empty{% endif %}">{{ v or '·' }}</td>{% endfor %}
      </tr>
      {% endfor %}
      </tbody>
    </table></div>
    {% else %}
    <p class="sub">{{ pivot.year }} 年還沒有排班資料。</p>
    {% endif %}
  </div>

  {% if error %}<div class="banner">{{ error }}</div>{% endif %}

  {% if can('USER_CREATE') %}
  <form class="card" method="post">
    <h2>提交班表</h2>
    <div class="grid">
      <div>
        <label for="employee_id">成員</label>
        <select id="employee_id" name="employee_id" required>
          {% if submit_employees|length != 1 %}<option value="">請選擇</option>{% endif %}
          {% for e in submit_employees %}
          <option value="{{ e.employee_id }}" data-default="{{ e.default_shift_code or '' }}"
            {% if form.employee_id == e.employee_id %}selected{% endif %}>
            {{ e.employee_id }} · {{ e.full_name }} ({{ e.office_code }} / {{ e.team }})</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label for="shift_code">班別 / 狀況</label>
        <select id="shift_code" name="shift_code" required>{{ shift_options(form.shift_code) }}</select>
      </div>
      <div>
        <label for="start_date">開始日期</label>
        <input type="date" id="start_date" name="start_date" value="{{ form.start_date }}" required>
      </div>
      <div>
        <label for="end_date">結束日期</label>
        <input type="date" id="end_date" name="end_date" value="{{ form.end_date }}">
        <div class="hint">只排一天可留空</div>
      </div>
      <div id="approval_box">
        <label for="leave_approval_status">請假核准狀態</label>
        <select id="leave_approval_status" name="leave_approval_status">{{ approval_options(form.leave_approval_status) }}</select>
      </div>
      <div>
        <label for="remarks">備註</label>
        <input type="text" id="remarks" name="remarks" value="{{ form.remarks or '' }}" placeholder="例如：與 EMP0005 換班">
      </div>
    </div>
    <label class="check"><input type="checkbox" name="is_ot" {% if form.is_ot %}checked{% endif %}> 這是加班</label>
    <label class="check"><input type="checkbox" name="skip_non_working" {% if form.skip_non_working %}checked{% endif %}>
      日期區間內遇到休息日或國定假日時略過（上班與請假班別適用）</label>
    <button type="submit">送出</button>
  </form>
  {% endif %}

  {% if results %}
  <div class="card">
    <h2>提交結果：新增 {{ summary.created }} 筆、更新 {{ summary.updated }} 筆、略過 {{ summary.skipped }} 筆、失敗 {{ summary.error }} 筆</h2>
    <div class="scroll"><table>
      <tr><th>日期</th><th>星期</th><th>結果</th><th>日別</th><th>班別</th><th>上班時間</th><th>工時</th><th>提醒</th></tr>
      {% for r in results %}
      <tr>
        <td>{{ r.date }}</td>
        <td>{{ r.row.weekday if r.row else '' }}</td>
        <td><span class="tag {{ r.action }}">{{ {'created':'新增','updated':'更新','skipped':'略過','error':'失敗'}[r.action] }}</span></td>
        <td>{{ r.row.day_type if r.row else '' }}{% if r.row and r.row.holiday_name %} · {{ r.row.holiday_name }}{% endif %}</td>
        <td>{{ r.row.shift_code if r.row else '' }}{% if r.row and r.row.is_ot %} (OT){% endif %}</td>
        <td>{% if r.row and r.row.planned_start_local %}{{ r.row.planned_start_local[11:] }} → {{ r.row.planned_end_local[11:] }}{% endif %}</td>
        <td>{{ r.row.planned_hours if r.row else '' }}</td>
        <td class="msg {% if r.action != 'skipped' %}flag{% endif %}">{{ r.message }}</td>
      </tr>
      {% endfor %}
    </table></div>
  </div>
  {% endif %}

  <div class="card">
    <h2>查詢與修改</h2>
    <form class="filter" method="get">
      <input type="hidden" name="year" value="{{ pivot.year }}">
      <div>
        <label for="view_emp">成員</label>
        <select id="view_emp" name="view_emp">
          <option value="">全部</option>
          {% for e in employees %}
          <option value="{{ e.employee_id }}" {% if view.emp == e.employee_id %}selected{% endif %}>{{ e.employee_id }} · {{ e.full_name }}</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label for="view_from">日期起</label>
        <input type="date" id="view_from" name="view_from" value="{{ view.date_from or '' }}">
      </div>
      <div>
        <label for="view_to">日期迄</label>
        <input type="date" id="view_to" name="view_to" value="{{ view.date_to or '' }}">
      </div>
      <button type="submit">查詢</button>
    </form>
    {% if recent %}
    <div class="scroll"><table>
      <tr>{% if can('USER_EDIT') %}<th></th>{% endif %}<th>roster_key</th><th>姓名</th><th>星期</th><th>班別</th><th>狀態</th><th>日別</th><th>工時</th>
          <th>工作天</th><th>請假</th><th>加班</th><th>版本</th><th>updatetime (UTC)</th><th>檢查</th></tr>
      {% for r in recent %}
      <tr>
        {% if can('USER_EDIT') %}<td><button type="button" class="link" data-edit='{{ r|edit_payload|tojson }}'>修改</button></td>{% endif %}
        <td>{{ r.roster_key }}</td><td>{{ r.full_name }}</td><td>{{ r.weekday }}</td>
        <td>{{ r.shift_code }}{% if r.is_ot %} (OT){% endif %}</td><td>{{ r.status_group }}</td>
        <td>{{ r.day_type }}</td><td>{{ r.planned_hours }}</td><td>{{ r.work_fraction }}</td>
        <td>{{ r.leave_fraction }}</td><td>{{ r.ot_fraction }}</td><td>{{ r.roster_version }}</td>
        <td>{{ r.updated_at|utc_text }}</td>
        <td class="msg flag">{{ r.check_flag or '' }}</td>
      </tr>
      {% endfor %}
    </table></div>
    <div class="hint">最多顯示 {{ recent_limit }} 筆，依日期由新到舊。</div>
    {% else %}
    <p class="sub">查無資料。</p>
    {% endif %}
  </div>

  {% if can('USER_EDIT') %}
  <dialog id="edit_dialog">
    <form method="post">
      <div class="head">
        <h2>修改排班</h2>
        <button type="button" class="close" data-close aria-label="關閉">×</button>
      </div>
      <div class="banner" data-f="error" {% if not edit_error %}hidden{% endif %}>{{ edit_error or '' }}</div>
      <dl class="meta">
        <dt>roster_key</dt><dd data-f="edit_key"></dd>
        <dt>成員</dt><dd data-f="who"></dd>
        <dt>日期</dt><dd data-f="start_date"></dd>
        <dt>版本 / updatetime (UTC)</dt><dd data-f="version"></dd>
      </dl>
      <input type="hidden" name="edit_key">
      <input type="hidden" name="employee_id">
      <input type="hidden" name="start_date">
      <div class="grid">
        <div>
          <label for="dlg_shift_code">班別 / 狀況</label>
          <select id="dlg_shift_code" name="shift_code" required>{{ shift_options(none) }}</select>
        </div>
        <div id="dlg_approval_box">
          <label for="dlg_approval">請假核准狀態</label>
          <select id="dlg_approval" name="leave_approval_status">{{ approval_options(none) }}</select>
        </div>
        <div>
          <label for="dlg_remarks">備註</label>
          <input type="text" id="dlg_remarks" name="remarks">
        </div>
      </div>
      <label class="check"><input type="checkbox" name="is_ot"> 這是加班</label>
      <div class="actions">
        <button type="button" class="secondary" data-close>取消</button>
        <button type="submit">儲存修改</button>
      </div>
    </form>
  </dialog>
  {% endif %}
{% endblock %}
{% block script %}
<script>
  function bindApproval(shift, box) {
    const toggle = () => {
      const opt = shift.selectedOptions[0];
      box.style.display = opt && opt.dataset.status === 'Leave' ? '' : 'none';
    };
    shift.addEventListener('change', toggle);
    toggle();
    return toggle;
  }

  {% if can('USER_CREATE') %}
  const emp = document.getElementById('employee_id');
  const shift = document.getElementById('shift_code');
  const toggleMain = bindApproval(shift, document.getElementById('approval_box'));
  const applyDefaultShift = () => {
    const def = emp.selectedOptions[0]?.dataset.default;
    if (def && !shift.value) { shift.value = def; toggleMain(); }
  };
  emp.addEventListener('change', applyDefaultShift);
  applyDefaultShift();   // 員工已預選（例如 Agent 只能選自己）時，直接帶入預設班別
  {% endif %}

  {% if can('USER_EDIT') %}
  // 修改彈窗
  const dlg = document.getElementById('edit_dialog');
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
    f.is_ot.checked = !!d.is_ot;
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
  dlg.querySelectorAll('[data-close]').forEach(btn => btn.addEventListener('click', () => dlg.close()));
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });   // 點背景關閉

  {% if edit %}openEdit({{ edit|tojson }}, {{ (edit_error or '')|tojson }});{% endif %}
  {% endif %}
</script>
{% endblock %}
"""

DIM_LIST = """
{% extends "base.html" %}
{% block title %}{{ meta.label }}{% endblock %}
{% block content %}
  <h1>{{ meta.label }}</h1>
  <p class="sub">{{ meta.table }}，共 {{ rows|length }} 筆。點「編輯」查看完整欄位並修改。</p>
  {% if msg %}<div class="banner {% if not msg_error %}ok{% endif %}">{{ msg }}</div>{% endif %}
  <div class="card">
    <div class="head">
      <h2>資料列表</h2>
      {% if can('USER_CREATE') %}<a class="btn" href="{{ url_for('dim_edit', kind=kind) }}">新增{{ meta.label }}</a>{% endif %}
    </div>
    {% if rows %}
    <div class="scroll"><table>
      <tr>{% for c in meta.list_cols %}<th>{{ c }}{% if c in ('created_at', 'updated_at') %} (UTC){% endif %}</th>{% endfor %}<th></th></tr>
      {% for r in rows %}
      <tr>
        {% for c in meta.list_cols %}<td>{% if c in ('created_at', 'updated_at') %}{{ r[c]|utc_text }}{% else %}{{ '' if r[c] is none else r[c] }}{% endif %}</td>{% endfor %}
        <td><a href="{{ url_for('dim_edit', kind=kind, key=r[meta.pk]) }}">編輯</a></td>
      </tr>
      {% endfor %}
    </table></div>
    {% else %}
    <p class="sub">還沒有資料。</p>
    {% endif %}
  </div>
{% endblock %}
"""

DIM_EDIT = """
{% extends "base.html" %}
{% block title %}{{ '編輯' if key else '新增' }}{{ meta.label }}{% endblock %}
{% block content %}
  <h1>{% if key %}編輯{{ meta.label }}：{{ key }}{% else %}新增{{ meta.label }}{% endif %}</h1>
  <p class="sub">{{ meta.table }}</p>
  {% if error %}<div class="banner">{{ error }}</div>{% endif %}

  <form class="card" method="post">
    <div class="grid">
    {% for f in fields %}
      {% set v = values.get(f.name) %}
      {% if f.pk and (key or meta.pk_mode == 'derived') %}
        {% if key %}
        <div>
          <label>{{ f.name }}</label>
          <input type="text" value="{{ key }}" disabled>
          <div class="hint">{% if meta.pk_mode == 'derived' %}由 calendar_code 與 holiday_date 自動產生{% else %}主鍵不可修改{% endif %}</div>
        </div>
        {% endif %}
      {% elif f.type == 'readonly' %}
        {% if key %}
        <div>
          <label>{{ f.name }} (UTC)</label>
          <input type="text" value="{{ v|utc_text }}" disabled>
          <div class="hint">系統自動記錄</div>
        </div>
        {% endif %}
      {% elif f.type == 'perms' %}
        {% set chosen = (v or '').split(',') %}
        <div class="perms">
          <label>{{ f.name }}</label>
          {% for p in f.options %}
          <label class="check"><input type="checkbox" name="{{ f.name }}" value="{{ p }}" {% if p in chosen %}checked{% endif %}> {{ p }}</label>
          {% endfor %}
          <button type="button" class="link" id="perm_default">依角色套用預設</button>
          <div class="hint">Agent：USER_VIEW、USER_CREATE；其他角色：全部。全不勾選時依角色套用預設。</div>
        </div>
      {% elif f.type == 'bool' %}
        <div><label class="check"><input type="checkbox" name="{{ f.name }}" {% if v and v != '0' %}checked{% endif %}> {{ f.name }}</label></div>
      {% elif f.type == 'select' %}
        <div>
          <label for="{{ f.name }}">{{ f.name }}</label>
          <select id="{{ f.name }}" name="{{ f.name }}" {% if f.required %}required{% endif %}>
            <option value="">—</option>
            {% for val, text in f.options %}
            <option value="{{ val }}" {% if v == val %}selected{% endif %}>{{ text }}</option>
            {% endfor %}
          </select>
        </div>
      {% else %}
        <div>
          <label for="{{ f.name }}">{{ f.name }}</label>
          <input type="{{ f.type }}" id="{{ f.name }}" name="{{ f.name }}" value="{{ '' if v is none else v }}"
            {% if f.type == 'number' %}step="any"{% endif %}
            {% if f.required and not (f.pk and meta.pk_mode == 'auto') %}required{% endif %}>
          {% if f.pk and meta.pk_mode == 'auto' %}<div class="hint">留空自動產生</div>{% endif %}
        </div>
      {% endif %}
    {% endfor %}
    {% if kind == 'employee' %}
      <div>
        <label for="new_password">{{ '重設密碼' if key else '登入密碼' }}</label>
        <input type="password" id="new_password" name="new_password" minlength="{{ password_min_length }}" autocomplete="new-password">
        <div class="hint">至少 {{ password_min_length }} 個字元；{{ '留空表示不變更' if key else '留空則此員工暫時無法登入' }}。登入帳號為 email。</div>
      </div>
    {% endif %}
    </div>
    <button type="submit">儲存</button>
    <a class="back" href="{{ url_for('dim_list', kind=kind) }}">返回列表</a>
  </form>

  {% if key and can('USER_DELETE') %}
  <form method="post" action="{{ url_for('dim_delete', kind=kind) }}" onsubmit="return confirm('確定刪除這筆資料？')">
    <input type="hidden" name="key" value="{{ key }}">
    <button type="submit" class="danger">刪除</button>
  </form>
  {% endif %}
{% endblock %}
{% block script %}
{% if kind == 'employee' %}
<script>
  document.getElementById('perm_default')?.addEventListener('click', () => {
    const role = (document.getElementById('role')?.value || '').trim();
    const allowed = role === 'Agent' ? {{ agent_perms|tojson }} : {{ all_perms|tojson }};
    document.querySelectorAll('input[name="permission"]').forEach(cb => { cb.checked = allowed.includes(cb.value); });
  });
</script>
{% endif %}
{% endblock %}
"""

LOGIN = """
{% extends "base.html" %}
{% block title %}登入 · Vantage Roster Situation{% endblock %}
{% block content %}
  <form class="card login" method="post">
    <h1>登入</h1>
    <p class="sub">請使用員工 email 與密碼登入，登入有效 {{ jwt_expire_minutes }} 分鐘。</p>
    {% if notice %}<div class="banner info">{{ notice }}</div>{% endif %}
    {% if error %}<div class="banner">{{ error }}</div>{% endif %}
    <label for="email">帳號（email）</label>
    <input type="text" id="email" name="email" value="{{ email }}" autocomplete="username" required autofocus>
    <label for="password">密碼</label>
    <input type="password" id="password" name="password" autocomplete="current-password" required>
    <button type="submit">登入</button>
  </form>
{% endblock %}
"""

FORBIDDEN = """
{% extends "base.html" %}
{% block title %}沒有權限{% endblock %}
{% block content %}
  <div class="card">
    <h1>沒有權限</h1>
    <p class="sub">你的帳號沒有這項操作的權限，如有需要請聯絡主管。</p>
    <a class="btn" href="{{ url_for('index') }}">回到排班總覽</a>
  </div>
{% endblock %}
"""

TEMPLATES = {
    "base.html": BASE,
    "login.html": LOGIN,
    "forbidden.html": FORBIDDEN,
    "roster.html": ROSTER,
    "dim_list.html": DIM_LIST,
    "dim_edit.html": DIM_EDIT,
}



def utc_text(iso):
    """'2026-10-08T03:12:00+00:00' → '2026-10-08 03:12:00'"""
    return iso[:19].replace("T", " ") if iso else ""


def _str_or_none(v):
    return v if isinstance(v, str) else None


def _days(v):
    return f"{v:g}" if v else "0"


def pivot_to_view(pivot, totals, year):
    """把 RosterDB.roster_pivot 的結果轉成模板好用的 columns / rows。
    每格是 (roster_display, situation)；每列另帶上班 / 請假 / 加班天數小計。"""
    years = list(range(year - PIVOT_YEARS_BEFORE, year + PIVOT_YEARS_AFTER + 1))
    view = {"year": year, "years": years, "columns": [], "rows": []}
    if pivot.empty:
        return view
    display, situation = pivot["roster_display"], pivot["situation"]
    for c in display.columns:
        d = dt.date.fromisoformat(c)
        view["columns"].append({"label": d.strftime("%m-%d"), "weekday": d.strftime("%a"),
                                "weekend": d.isoweekday() >= 6})
    for key, cells in display.iterrows():
        team, office, name = key
        t = totals.loc[key]
        view["rows"].append({
            "team": team, "office_code": office, "full_name": name,
            "work": _days(t["work_fraction"]), "leave": _days(t["leave_fraction"]), "ot": _days(t["ot_fraction"]),
            "cells": [(_str_or_none(v), _str_or_none(s)) for v, s in zip(cells, situation.loc[key])],
        })
    return view


def parse_date(s):
    return dt.date.fromisoformat(s) if s else None


def default_form():
    return {"start_date": dt.date.today().isoformat(), "end_date": "", "skip_non_working": True}


def parse_submit_form(f):
    """把 HTML 表單轉成 dict（保留原字串，供重新填回表單）。"""
    return {
        "employee_id": f.get("employee_id"),
        "shift_code": f.get("shift_code"),
        "start_date": f.get("start_date"),
        "end_date": f.get("end_date"),
        "leave_approval_status": f.get("leave_approval_status") or None,
        "remarks": (f.get("remarks") or "").strip() or None,
        "is_ot": "is_ot" in f,
        "skip_non_working": "skip_non_working" in f,
        "edit_key": f.get("edit_key") or None,
    }


def edit_payload(row, overrides=None):
    """把 fact_roster 的一筆資料轉成修改彈窗要填入的值；overrides 為使用者剛送出的欄位（驗證失敗時保留）。"""
    payload = {
        "edit_key": row["roster_key"],
        "employee_id": row["employee_id"],
        "full_name": row["full_name"],
        "start_date": row["roster_date"],
        "weekday": row["weekday"],
        "shift_code": row["shift_code"],
        "leave_approval_status": row["leave_approval_status"],
        "remarks": row["remarks"],
        "is_ot": bool(row["is_ot"]),
        "roster_version": row["roster_version"],
        "updatetime": utc_text(row["updated_at"]),
    }
    for k in ("shift_code", "leave_approval_status", "remarks", "is_ot"):
        if overrides and k in overrides:
            payload[k] = overrides[k]
    return payload


def parse_view_filter(args):
    return {"emp": args.get("view_emp") or "", "date_from": args.get("view_from") or None,
            "date_to": args.get("view_to") or None}


def parse_api_payload(b):
    """把 JSON 請求轉成 submit_range 的參數。缺欄位丟 KeyError，日期格式錯丟 ValueError。"""
    start = parse_date(b.get("start_date"))
    return {
        "employee_id": b["employee_id"],
        "shift_code": b["shift_code"],
        "start_date": start,
        "end_date": parse_date(b.get("end_date")) or start,
        "is_ot": bool(b.get("is_ot")),
        "leave_approval_status": b.get("leave_approval_status"),
        "remarks": b.get("remarks"),
        "skip_non_working": b.get("skip_non_working", True),
    }
