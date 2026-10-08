"""
網頁模板與表單 / JSON 輸入解析。

TEMPLATES 交給 Flask 的 DictLoader 使用：base.html 是共用版面，其他頁面以 {% extends %} 套用。
"""
from config import PIVOT_YEARS_AFTER, PIVOT_YEARS_BEFORE
import calendar
import datetime as dt


BASE = """
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}Vantage Roster Situation{% endblock %}</title>
<script>
  // 主題：預設亮色；使用者選過深色時記在瀏覽器（localStorage），在畫面繪出前套用，避免閃爍
  try { if (localStorage.getItem('roster-theme') === 'dark') document.documentElement.dataset.theme = 'dark'; } catch (e) {}
</script>
<style>
  /* 主題：預設亮色「霧藍極光」，<html data-theme="dark"> 時為深色「極光深夜」。顏色只在這兩段定義 */
  :root { color-scheme:light;
          --bg:#f3f6fb; --glow-1:rgba(6,182,212,.10); --glow-2:rgba(139,92,246,.09); --nav-bg:rgba(255,255,255,.88);
          --card:#ffffff; --card-2:#ffffff; --raised:#f1f5f9; --input-bg:#ffffff; --line:#e2e8f0; --line-2:#cbd5e1;
          --ink:#0f172a; --muted:#556275; --faint:#cbd5e1;
          --cyan:#0891b2; --accent:#0369a1; --grad:linear-gradient(135deg, #0e7490, #7c3aed); --on-grad:#ffffff;
          --brand:linear-gradient(135deg, #06b6d4, #8b5cf6);
          --ok:#047857; --warn:#b45309; --err:#be123c;
          --ok-bg:#ecfdf5; --warn-bg:#fef3c7; --err-bg:#fff1f2; --info-bg:#e0f2fe; --muted-bg:#f1f5f9;
          --hover:rgba(3,105,161,.05); --wkend:rgba(100,116,139,.07); --focus:rgba(8,145,178,.18);
          --shadow:0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.06); --btn-shadow:0 4px 14px rgba(124,58,237,.18);
          --dialog-shadow:0 30px 60px rgba(15,23,42,.25); --backdrop:rgba(15,23,42,.45);
          --shift-bg:#e0f2fe; --shift-fg:#0369a1; --leave-bg:#fef3c7; --leave-fg:#92400e;
          --ot-bg:#fce7f3; --ot-fg:#be185d; --off-bg:#f1f5f9; --off-fg:#556275;
          --act-bg:#d1fae5; --act-fg:#047857; --pend-fg:#b45309;
          --h1:#fef9c3; --h2:#fde68a; --h3:#fdba74; --h4:#f9a8d4; }
  :root[data-theme="dark"] { color-scheme:dark;
          --bg:#0b1020; --glow-1:rgba(34,211,238,.10); --glow-2:rgba(167,139,250,.12); --nav-bg:rgba(11,16,32,.85);
          --card:#131c31; --card-2:#18233b; --raised:#1e293b; --input-bg:#0b1020; --line:#26324a; --line-2:#334155;
          --ink:#e2e8f0; --muted:#94a3b8; --faint:#475569;
          --cyan:#22d3ee; --accent:#38bdf8; --grad:linear-gradient(135deg, #22d3ee, #a78bfa); --on-grad:#0b1020;
          --brand:linear-gradient(135deg, #22d3ee, #a78bfa);
          --ok:#34d399; --warn:#fbbf24; --err:#fb7185;
          --ok-bg:rgba(52,211,153,.13); --warn-bg:rgba(251,191,36,.15); --err-bg:rgba(251,113,133,.13);
          --info-bg:rgba(56,189,248,.11); --muted-bg:rgba(148,163,184,.14);
          --hover:rgba(56,189,248,.05); --wkend:rgba(148,163,184,.06); --focus:rgba(34,211,238,.18);
          --shadow:0 0 0 1px rgba(56,189,248,.08), 0 10px 30px rgba(2,6,23,.55); --btn-shadow:0 4px 18px rgba(34,211,238,.18);
          --dialog-shadow:0 30px 60px rgba(0,0,0,.6); --backdrop:rgba(2,6,23,.7);
          --shift-bg:rgba(56,189,248,.14); --shift-fg:#7dd3fc; --leave-bg:rgba(251,191,36,.16); --leave-fg:#fcd34d;
          --ot-bg:rgba(244,114,182,.18); --ot-fg:#f9a8d4; --off-bg:rgba(100,116,139,.18); --off-fg:#94a3b8;
          --act-bg:rgba(52,211,153,.14); --act-fg:#6ee7b7; --pend-fg:#fcd34d;
          --h1:rgba(251,191,36,.10); --h2:rgba(251,191,36,.20); --h3:rgba(251,146,60,.28); --h4:rgba(244,114,182,.34); }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system, "Segoe UI", "Noto Sans TC", sans-serif; color:var(--ink);
         background:radial-gradient(1200px 500px at 10% -10%, var(--glow-1), transparent 60%),
                    radial-gradient(900px 500px at 100% 0%, var(--glow-2), transparent 60%), var(--bg);
         background-attachment:fixed; min-height:100vh; }
  main { max-width:1100px; margin:0 auto; padding:28px 16px 64px; }
  nav { background:var(--nav-bg); backdrop-filter:blur(10px); position:sticky; top:0; z-index:20;
        border-bottom:1px solid transparent; border-image:var(--brand) 1; }
  nav div { max-width:1100px; margin:0 auto; padding:0 16px; display:flex; gap:4px; flex-wrap:wrap; align-items:center; }
  nav a { color:var(--muted); text-decoration:none; padding:14px 14px; font-weight:600; border-bottom:2px solid transparent; }
  nav a:hover { color:var(--ink); }
  nav a.on { color:var(--ink); border-bottom-color:var(--cyan); }
  nav .brand { font-weight:800; padding:14px 18px 14px 0; letter-spacing:.3px;
               background:var(--brand); -webkit-background-clip:text; background-clip:text; color:transparent; }
  nav .count { display:inline-block; min-width:18px; margin-left:5px; padding:0 5px; border-radius:9px;
               background:var(--warn); color:var(--on-grad); font-size:11px; line-height:18px; text-align:center; }
  nav .theme { margin:0 0 0 auto; padding:5px 10px; background:var(--raised); color:var(--ink); border:1px solid var(--line-2);
               font-size:14px; line-height:1; box-shadow:none; }
  nav .theme:hover { border-color:var(--cyan); transform:none; }
  nav form.who { margin-left:10px; display:flex; align-items:center; gap:10px; color:var(--muted); font-size:13px; }
  nav form.who .exp { opacity:.75; }
  nav form.who button { margin:0; padding:5px 12px; background:var(--raised); color:var(--ink); border:1px solid var(--line-2);
                        font-size:13px; box-shadow:none; }
  h1 { font-size:24px; margin:0 0 4px; letter-spacing:.2px; }
  h2 { font-size:16px; margin:0 0 12px; }
  a { color:var(--accent); }
  .sub { color:var(--muted); margin:0 0 20px; }
  .card { background:linear-gradient(180deg, var(--card-2), var(--card)); border:1px solid var(--line); border-radius:14px;
          padding:20px; margin-bottom:20px; box-shadow:var(--shadow); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px 18px; }
  label { display:block; font-size:13px; font-weight:600; margin-bottom:4px; color:var(--ink); }
  select, input[type=date], input[type=text], input[type=number], input[type=time], input[type=password] {
    width:100%; padding:8px 10px; border:1px solid var(--line-2); border-radius:8px; font:inherit;
    background:var(--input-bg); color:var(--ink); }
  select:focus, input:focus { outline:none; border-color:var(--cyan); box-shadow:0 0 0 3px var(--focus); }
  input:disabled { background:var(--raised); color:var(--muted); }
  input[type=checkbox] { accent-color:var(--cyan); }
  .check { display:flex; align-items:center; gap:8px; font-weight:400; margin-top:6px; }
  .hint { font-size:12px; color:var(--muted); margin-top:4px; }
  button, a.btn { display:inline-block; margin-top:18px; background:var(--grad); color:var(--on-grad); border:0; border-radius:8px;
           padding:10px 22px; font:inherit; font-weight:700; cursor:pointer; text-decoration:none;
           box-shadow:var(--btn-shadow); transition:filter .15s, transform .15s; }
  button:hover, a.btn:hover { filter:brightness(1.08); transform:translateY(-1px); }
  button.secondary, a.btn.secondary { background:transparent; color:var(--ink); border:1px solid var(--line-2); box-shadow:none; }
  button.secondary:hover, a.btn.secondary:hover { border-color:var(--cyan); color:var(--cyan); }
  button.danger { background:transparent; color:var(--err); border:1px solid color-mix(in srgb, var(--err) 50%, transparent); box-shadow:none; }
  button.link { margin:0; padding:0; background:none; color:var(--accent); font-weight:600; font-size:13px; box-shadow:none; }
  button.link:hover { text-decoration:underline; transform:none; }
  a.back { margin-left:14px; color:var(--muted); }
  td a { color:var(--accent); font-weight:600; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th { color:var(--muted); font-weight:600; }
  td.msg { white-space:normal; }
  table tr:hover td { background-color:var(--hover); }
  .scroll { overflow-x:auto; }
  .tag { display:inline-block; padding:1px 8px; border-radius:10px; font-size:12px; font-weight:600; }
  .created, .updated, .tag.st-Approved { background:var(--ok-bg); color:var(--ok); }
  .skipped, .tag.st-Cancelled { background:var(--muted-bg); color:var(--muted); }
  .error, .tag.st-Rejected { background:var(--err-bg); color:var(--err); }
  .tag.st-Pending { background:var(--warn-bg); color:var(--warn); }
  .flag { color:var(--warn); }
  .banner { padding:10px 14px; border-radius:10px; background:var(--err-bg); color:var(--err); margin-bottom:16px;
            border:1px solid color-mix(in srgb, currentColor 25%, transparent); }
  .banner.ok { background:var(--ok-bg); color:var(--ok); }
  .banner.info { background:var(--info-bg); color:var(--accent); }
  .filter { display:flex; gap:10px; align-items:end; margin-bottom:12px; flex-wrap:wrap; }
  .filter select { width:auto; min-width:240px; }
  .filter button { margin-top:0; padding:8px 16px; }
  .head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
  .head h2 { margin:0; }
  .head a.btn, .head button { margin-top:0; padding:8px 16px; }
  .head select { width:auto; padding:6px 10px; }
  .head .tools { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  form.inline { display:flex; gap:6px; align-items:center; }
  form.inline input { width:auto; min-width:150px; padding:5px 8px; }
  form.inline button { margin:0; padding:5px 12px; font-size:13px; }
  /* 年度總覽 */
  .pivot { max-height:420px; overflow:auto; border:1px solid var(--line); border-radius:10px; }
  .pivot table { width:auto; }
  .pivot th, .pivot td { padding:5px 8px; border-right:1px solid var(--line); text-align:center; }
  .pivot thead th { position:sticky; top:0; background:var(--raised); z-index:2; line-height:1.3; }
  .pivot thead th small { display:block; font-weight:400; }
  .pivot .k { position:sticky; background:var(--card); z-index:1; text-align:left; font-weight:600; }
  .pivot thead .k { background:var(--raised); z-index:3; }
  .pivot .k1 { left:0; width:72px; min-width:72px; }
  .pivot .k2 { left:72px; width:72px; min-width:72px; }
  .pivot .k3 { left:144px; width:180px; min-width:180px; }
  .pivot .t1, .pivot .t2, .pivot .t3 { width:56px; min-width:56px; text-align:right; font-variant-numeric:tabular-nums; }
  .pivot .t1 { left:324px; }
  .pivot .t2 { left:380px; }
  .pivot .t3 { left:436px; border-right:2px solid var(--line-2); }
  .pivot .wkend { background:var(--wkend); }
  .pivot td.empty { color:var(--faint); }
  .pivot .drill { cursor:pointer; color:var(--accent); text-decoration:underline dotted; text-underline-offset:3px; }
  .pivot .drill:hover { background:var(--info-bg); }
  .pivot thead .drill { color:var(--cyan); }
  .s-SHIFT { background:var(--shift-bg); color:var(--shift-fg); }
  .s-LEAVE { background:var(--leave-bg); color:var(--leave-fg); }
  .s-OT { background:var(--ot-bg); color:var(--ot-fg); font-weight:600; }
  .s-OFF { background:var(--off-bg); color:var(--off-fg); }
  .s-ACTIVITY { background:var(--act-bg); color:var(--act-fg); }
  .s-PENDING { background:transparent; color:var(--pend-fg); outline:1px dashed var(--warn); outline-offset:-3px; }
  .legend { display:flex; gap:8px; flex-wrap:wrap; margin:0 0 12px; font-size:12px; }
  .legend span { padding:2px 10px; border-radius:10px; }
  /* 彈窗 */
  dialog { border:1px solid var(--line-2); border-radius:14px; padding:0; width:min(640px, calc(100vw - 32px));
           max-height:calc(100vh - 32px); background:var(--card); color:var(--ink); box-shadow:var(--dialog-shadow); }
  dialog.wide { width:min(980px, calc(100vw - 32px)); }
  dialog::backdrop { background:var(--backdrop); backdrop-filter:blur(3px); }
  dialog form, dialog .body { padding:20px 22px 22px; }
  dialog .close { margin:0; padding:2px 10px; background:none; color:var(--muted); font-size:22px; line-height:1; box-shadow:none; }
  dialog .actions { display:flex; justify-content:flex-end; gap:10px; }
  dialog .scroll { max-height:60vh; overflow:auto; }
  dl.meta { display:grid; grid-template-columns:max-content 1fr; gap:4px 14px; margin:0 0 16px;
            padding:12px 14px; background:var(--raised); border:1px solid var(--line); border-radius:10px; font-size:13px; }
  dl.meta dt { color:var(--muted); }
  dl.meta dd { margin:0; font-weight:600; }
  /* 請假月曆：人數越多顏色越深 */
  .cal { display:grid; grid-template-columns:repeat(7, minmax(0, 1fr)); gap:6px; }
  .cal .dow { text-align:center; font-size:12px; color:var(--muted); font-weight:600; padding:2px 0; }
  .cal .day { min-height:84px; padding:6px 7px; border-radius:10px; border:1px solid var(--line); background:var(--input-bg);
              display:flex; flex-direction:column; gap:3px; font-size:12px; overflow:hidden; text-align:left;
              margin:0; color:var(--ink); box-shadow:none; font-weight:400; cursor:default; }
  .cal button.day { cursor:pointer; }
  .cal button.day:hover { border-color:var(--cyan); transform:none; filter:none; }
  .cal .day.out { visibility:hidden; }
  .cal .day.today { border-color:var(--cyan); box-shadow:inset 0 0 0 1px var(--cyan); }
  .cal .day .n { font-weight:700; color:var(--muted); }
  .cal .day .cnt { font-weight:700; font-size:13px; }
  .cal .day .who { color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .pend { color:var(--pend-fg); }
  .cal .h1, .cal-legend .h1 { background:var(--h1); } .cal .h2, .cal-legend .h2 { background:var(--h2); }
  .cal .h3, .cal-legend .h3 { background:var(--h3); } .cal .h4, .cal-legend .h4 { background:var(--h4); }
  .cal .day.has-pend { border:1px dashed var(--warn); }
  .cal .h3 .who, .cal .h4 .who { color:var(--ink); }
  .cal-legend { display:flex; gap:6px; align-items:center; flex-wrap:wrap; font-size:12px; color:var(--muted); margin-top:10px; }
  .cal-legend i { display:inline-block; width:18px; height:12px; border-radius:3px; border:1px solid var(--line); }
  .perms .check { margin-top:2px; }
  .perms button.link { margin-top:6px; }
  .login { max-width:380px; margin:48px auto; }
  .login input { margin-bottom:12px; }
  .login button { width:100%; }
  @media (max-width:640px) { .cal .day { min-height:56px; } .cal .day .who { display:none; } }
</style>
</head>
<body>
<nav><div>
  <span class="brand">Vantage Roster Situation</span>
  {% if current_user %}
  <a href="{{ url_for('index') }}" {% if request.endpoint == 'index' %}class="on"{% endif %}>排班總覽</a>
  {% endif %}
  {% if can_leave %}
  <a href="{{ url_for('leave') }}" {% if request.endpoint == 'leave' %}class="on"{% endif %}>請假{% if nav_pending_leave %}<span class="count">{{ nav_pending_leave }}</span>{% endif %}</a>
  {% endif %}
  {% for k, label in nav_dims %}
  <a href="{{ url_for('dim_list', kind=k) }}"
     {% if request.view_args and request.view_args.get('kind') == k %}class="on"{% endif %}>{{ label }}</a>
  {% endfor %}
  <button type="button" class="theme" id="theme_toggle"></button>
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
  // 亮色 / 深色切換
  (() => {
    const btn = document.getElementById('theme_toggle');
    const root = document.documentElement;
    const render = () => {
      const dark = root.dataset.theme === 'dark';
      btn.textContent = dark ? '☀' : '☾';
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
  {% if nav_pending_leave %}<div class="banner info">有 {{ nav_pending_leave }} 張請假申請等你審核，<a href="{{ url_for('leave') }}">前往審核</a></div>{% endif %}
  <p class="sub">每人每天的排班、請假與加班狀況。上班 / 請假 / 加班天數為所選年度（或月份）小計（半天以 0.5 計）。</p>

  <div class="card">
    <form class="head" method="get">
      <h2>{{ pivot.year }} 年{% if pivot.month %} {{ pivot.month }} 月{% else %}度{% endif %}總覽</h2>
      <div class="tools">
        <select name="year" onchange="this.form.submit()">
          {% for y in pivot.years %}<option {% if y == pivot.year %}selected{% endif %}>{{ y }}</option>{% endfor %}
        </select>
        <select name="month" onchange="this.form.submit()">
          <option value="">全年</option>
          {% for m in range(1, 13) %}<option value="{{ m }}" {% if m == pivot.month %}selected{% endif %}>{{ m }} 月</option>{% endfor %}
        </select>
        <a class="btn secondary" href="{{ url_for('export_roster', year=pivot.year, month=pivot.month) }}">匯出檔案</a>
      </div>
    </form>
    <div class="legend">
      {% for code, label in situation_labels %}<span class="s-{{ code }}">{{ label }}</span>{% endfor %}
    </div>
    {% if pivot.rows %}
    <div class="pivot"><table>
      <thead><tr>
        <th class="k k1">team</th><th class="k k2">office_code</th><th class="k k3">full_name</th>
        <th class="k t1 drill" data-kind="work" title="點擊看所有人的逐日明細">上班</th>
        <th class="k t2 drill" data-kind="leave" title="點擊看所有人的逐日明細">請假</th>
        <th class="k t3 drill" data-kind="ot" title="點擊看所有人的逐日明細">加班</th>
        {% for c in pivot.columns %}<th {% if c.weekend %}class="wkend"{% endif %}>{{ c.label }}<small>{{ c.weekday }}</small></th>{% endfor %}
      </tr></thead>
      <tbody>
      {% for r in pivot.rows %}
      <tr>
        <td class="k k1">{{ r.team }}</td><td class="k k2">{{ r.office_code }}</td><td class="k k3">{{ r.full_name }}</td>
        <td class="k t1 drill" data-kind="work" data-emp="{{ r.employee_id }}">{{ r.work }}</td>
        <td class="k t2 drill" data-kind="leave" data-emp="{{ r.employee_id }}">{{ r.leave }}</td>
        <td class="k t3 drill" data-kind="ot" data-emp="{{ r.employee_id }}">{{ r.ot }}</td>
        {% for v, s in r.cells %}<td class="{% if s %}s-{{ s }}{% elif pivot.columns[loop.index0].weekend %}wkend empty{% else %}empty{% endif %}">{{ v or '·' }}</td>{% endfor %}
      </tr>
      {% endfor %}
      </tbody>
    </table></div>
    {% else %}
    <p class="sub">{{ pivot.year }} 年{% if pivot.month %} {{ pivot.month }} 月{% endif %}還沒有排班資料。</p>
    {% endif %}
    {% if pivot.rows %}<div class="hint">點「上班 / 請假 / 加班」的數字看該員工的逐日明細；點欄位標題看所有人的明細。</div>
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
      <input type="hidden" name="month" value="{{ pivot.month or '' }}">
      <div>
        <label for="view_emp">成員</label>
        <select id="view_emp" name="view_emp">
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

  <dialog id="detail_dialog" class="wide">
    <div class="body">
      <div class="head">
        <h2 data-f="title"></h2>
        <button type="button" class="close" data-close aria-label="關閉">×</button>
      </div>
      <div class="scroll"><table><thead><tr data-f="cols"></tr></thead><tbody data-f="rows"></tbody></table></div>
      <p class="sub" data-f="empty" hidden>這段期間沒有資料。</p>
    </div>
  </dialog>
{% endblock %}
{% block script %}
<script>
  // 年度總覽：點「上班 / 請假 / 加班」看逐日明細（內容一律用 textContent 寫入）
  (() => {
    const dlg = document.getElementById('detail_dialog');
    const q = sel => dlg.querySelector(`[data-f="${sel}"]`);
    async function openDetail(kind, emp) {
      const params = new URLSearchParams({kind, year: {{ pivot.year }}{% if pivot.month %}, month: {{ pivot.month }}{% endif %}});
      if (emp) params.set('employee_id', emp);
      const res = await fetch(`{{ url_for('api_roster_detail') }}?${params}`);
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
    dlg.querySelector('[data-close]').addEventListener('click', () => dlg.close());
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
  })();

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
      <div class="tools">
        {% if can('USER_CREATE') %}<a class="btn" href="{{ url_for('dim_edit', kind=kind) }}">新增{{ meta.label }}</a>{% endif %}
        <a class="btn secondary" href="{{ url_for('dim_export', kind=kind) }}">匯出檔案</a>
      </div>
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
      {% elif f.type == 'derived' %}
        <div>
          <label>{{ f.name }}</label>
          <input type="text" value="{{ v or '' }}" disabled>
          <div class="hint">由 parent_id 自動帶出</div>
        </div>
      {% elif f.type == 'perms' %}
        {% set chosen = (v or '').split(',') %}
        <div class="perms">
          <label>{{ f.name }}</label>
          {% for p in f.options %}
          <label class="check"><input type="checkbox" name="{{ f.name }}" value="{{ p }}" {% if p in chosen %}checked{% endif %}> {{ p }}</label>
          {% endfor %}
          <button type="button" class="link" id="perm_default">依角色套用預設</button>
          <div class="hint">Agent：{{ agent_perms|join('、') }}；其他角色：全部。全不勾選時依角色套用預設。</div>
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
          {% if f.name == 'parent_id' %}<div class="hint">必填；只列在職的非 Agent。最高主管請選自己。</div>{% endif %}
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

LEAVE = """
{% extends "base.html" %}
{% block title %}請假 · Vantage Roster Situation{% endblock %}
{% macro status_tag(st) %}<span class="tag st-{{ st }}">{{ leave_status_labels[st] }}</span>{% endmacro %}
{% macro period(q) %}{{ q.start_date }}{% if q.end_date != q.start_date %} → {{ q.end_date }}{% endif %}{% endmacro %}
{% block content %}
  <h1>請假</h1>
  <p class="sub">送出申請後由主管審核，核准後才寫入班表；待審核的假會在排班總覽以虛線框顯示，不計入請假天數。</p>
  {% if msg %}<div class="banner {% if not msg_error %}ok{% endif %}">{{ msg }}</div>{% endif %}

  {% if can('LEAVE_APPROVE') %}
  <div class="card">
    <h2>待審核（{{ pending|length }}）</h2>
    <p class="hint">列出主管欄位（parent_id）是你的員工送出的申請；最高主管的申請由其他有審核權限的人審。你自己的申請由你的主管審核，不會出現在這裡。</p>
    {% if pending %}
    <div class="scroll"><table>
      <tr><th>申請單</th><th>申請人</th><th>假別</th><th>日期</th><th>天數</th><th>原因</th><th>同 team 同期請假</th><th>審核</th></tr>
      {% for q in pending %}
      <tr>
        <td>{{ q.request_id }}<div class="hint">{{ q.created_at|utc_text }} UTC</div></td>
        <td>{{ q.full_name }}<div class="hint">{{ q.employee_id }} · {{ q.office_code }} / {{ q.team or '—' }}</div></td>
        <td>{{ q.shift_code }} · {{ q.roster_display }}</td>
        <td>{{ period(q) }}</td>
        <td>{{ q.days|days }}</td>
        <td class="msg">{{ q.reason or '' }}</td>
        <td>已核准 {{ q.team_off }} 人 · 待審 {{ q.team_pending }} 人</td>
        <td>
          <form class="inline" method="post" action="{{ url_for('leave_decide', request_id=q.request_id) }}">
            <input type="text" name="decision_note" placeholder="審核意見（選填）">
            <button name="decision" value="approve">核准</button>
            <button name="decision" value="reject" class="danger">駁回</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </table></div>
    {% else %}
    <p class="sub">目前沒有待審核的申請。</p>
    {% endif %}
  </div>
  {% endif %}

  <div class="card">
    <div class="head">
      <h2>請假月曆：{{ cal.year }} 年 {{ cal.month }} 月</h2>
      <div class="tools">
        <a class="btn secondary" href="{{ url_for('leave', cal=cal.prev) }}">‹ 上個月</a>
        <a class="btn secondary" href="{{ url_for('leave') }}">本月</a>
        <a class="btn secondary" href="{{ url_for('leave', cal=cal.next) }}">下個月 ›</a>
      </div>
    </div>
    <div class="cal">
      {% for d in ['一', '二', '三', '四', '五', '六', '日'] %}<div class="dow">{{ d }}</div>{% endfor %}
      {% for cell in cal.cells %}
        {% if not cell %}<div class="day out"></div>
        {% elif cell.people %}
        <button type="button" class="day h{{ cell.heat }}{% if cell.today %} today{% endif %}{% if cell.pending %} has-pend{% endif %}" data-day='{{ cell|tojson }}'>
          <span class="n">{{ cell.day }}</span>
          <span class="cnt">{{ cell.approved }} 人{% if cell.pending %} <span class="pend">+{{ cell.pending }} 待審</span>{% endif %}</span>
          {% for p in cell.people[:2] %}<span class="who">{{ p.name }}</span>{% endfor %}
          {% if cell.people|length > 2 %}<span class="who">+{{ cell.people|length - 2 }} 人</span>{% endif %}
        </button>
        {% else %}<div class="day{% if cell.today %} today{% endif %}"><span class="n">{{ cell.day }}</span></div>
        {% endif %}
      {% endfor %}
    </div>
    <div class="cal-legend">請假人數：<i class="h1"></i>1 <i class="h2"></i>2 <i class="h3"></i>3 <i class="h4"></i>4+
      ・<span class="pend">虛線 / 「待審」為尚未核准</span>・點日期看名單</div>
  </div>

  <dialog id="cal_dialog">
    <div class="body">
      <div class="head">
        <h2 data-f="title"></h2>
        <button type="button" class="close" data-close aria-label="關閉">×</button>
      </div>
      <table><thead><tr><th>姓名</th><th>team</th><th>假別</th><th>狀態</th></tr></thead><tbody data-f="rows"></tbody></table>
    </div>
  </dialog>

  {% if can('LEAVE_APPLY') %}
  <form class="card" method="post" id="leave_form">
    <h2>我的請假</h2>
    {% if error %}<div class="banner">{{ error }}</div>{% endif %}
    <div class="grid">
      <div>
        <label for="leave_shift">假別</label>
        <select id="leave_shift" name="shift_code" required>
          <option value="">請選擇</option>
          {% for leave_type, items in leave_groups %}
          <optgroup label="{{ leave_type }}">
            {% for s in items %}
            <option value="{{ s.shift_code }}" data-portion="{{ s.day_portion }}" {% if form.shift_code == s.shift_code %}selected{% endif %}>
              {{ s.shift_code }} · {{ s.shift_name }}{% if not s.deducts_leave_balance %}（不扣假）{% endif %}</option>
            {% endfor %}
          </optgroup>
          {% endfor %}
        </select>
      </div>
      <div>
        <label for="leave_start">開始日期</label>
        <input type="date" id="leave_start" name="start_date" value="{{ form.start_date }}" required>
      </div>
      <div>
        <label for="leave_end">結束日期</label>
        <input type="date" id="leave_end" name="end_date" value="{{ form.end_date }}">
        <div class="hint">只請一天可留空；半天 / 部分請假只能請單日</div>
      </div>
      <div>
        <label for="leave_reason">原因</label>
        <input type="text" id="leave_reason" name="reason" value="{{ form.reason or '' }}" placeholder="例如：家庭旅遊">
      </div>
    </div>
    <div class="hint" id="leave_preview" aria-live="polite"></div>
    <button type="submit">送出申請</button>
  </form>

  <div class="card">
    <h2>我的申請紀錄</h2>
    {% if mine %}
    <div class="scroll"><table>
      <tr><th>申請單</th><th>假別</th><th>日期</th><th>天數</th><th>原因</th><th>狀態</th><th>審核人</th><th>審核意見</th><th></th></tr>
      {% for q in mine %}
      <tr>
        <td>{{ q.request_id }}<div class="hint">{{ q.created_at|utc_text }} UTC</div></td>
        <td>{{ q.shift_code }} · {{ q.roster_display }}</td>
        <td>{{ period(q) }}</td>
        <td>{{ q.days|days }}</td>
        <td class="msg">{{ q.reason or '' }}</td>
        <td>{{ status_tag(q.status) }}</td>
        <td>{% if q.status == 'Pending' %}{% if q.waiting_for %}待 {{ q.waiting_for }} 審核{% else %}<span class="flag">目前沒有人能審核</span>{% endif %}{% else %}{{ q.approver_name or '' }}{% endif %}</td>
        <td class="msg">{{ q.decision_note or '' }}</td>
        <td>{% if q.status == 'Pending' %}
          <form method="post" action="{{ url_for('leave_cancel', request_id=q.request_id) }}" onsubmit="return confirm('確定撤回 {{ q.request_id }}？')">
            <button type="submit" class="link">撤回</button>
          </form>{% endif %}</td>
      </tr>
      {% endfor %}
    </table></div>
    <div class="hint">已核准的假如需取消，請聯絡主管。最多顯示 {{ leave_limit }} 筆。</div>
    {% else %}
    <p class="sub">還沒有申請紀錄。</p>
    {% endif %}
  </div>
  {% endif %}

  {% if can('LEAVE_APPROVE') %}
  <div class="card">
    <div class="head">
      <h2>審核紀錄</h2>
      <a class="btn secondary" href="{{ url_for('export_leave_history') }}">匯出檔案</a>
    </div>
    {% if history %}
    <div class="scroll"><table>
      <tr><th>申請單</th><th>申請人</th><th>假別</th><th>日期</th><th>天數</th><th>狀態</th><th>審核人</th><th>審核意見</th><th></th></tr>
      {% for q in history %}
      <tr>
        <td>{{ q.request_id }}</td>
        <td>{{ q.full_name }}<div class="hint">{{ q.employee_id }}</div></td>
        <td>{{ q.shift_code }} · {{ q.roster_display }}</td>
        <td>{{ period(q) }}</td>
        <td>{{ q.days|days }}</td>
        <td>{{ status_tag(q.status) }}</td>
        <td>{{ q.approver_name or '' }}<div class="hint">{{ q.decided_at|utc_text }}</div></td>
        <td class="msg">{{ q.decision_note or '' }}</td>
        <td>{% if q.status == 'Approved' %}
          <form class="inline" method="post" action="{{ url_for('leave_cancel', request_id=q.request_id) }}"
                onsubmit="return confirm('取消後會把班表還原為預設班別，確定取消 {{ q.request_id }}？')">
            <input type="text" name="note" placeholder="取消原因（選填）">
            <button type="submit" class="danger">取消</button>
          </form>{% endif %}</td>
      </tr>
      {% endfor %}
    </table></div>
    {% else %}
    <p class="sub">還沒有審核紀錄。</p>
    {% endif %}
  </div>
  {% endif %}
{% endblock %}
{% block script %}
<script>
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
    dlg.querySelector('[data-close]').addEventListener('click', () => dlg.close());
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
  })();
</script>
{% if can('LEAVE_APPLY') %}
<script>
  // 選假別 / 日期時即時預覽會請幾天（伺服器依行事曆略過休息日與國定假日）
  (() => {
    const f = document.getElementById('leave_form').elements;
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
        const d = await (await fetch(`{{ url_for('api_leave_preview') }}?${q}`)).json();
        if (id !== seq) return;
        out.className = d.ok ? 'hint' : 'hint flag';
        out.textContent = d.ok ? `共 ${d.days} 天（略過休息日與國定假日）：${d.dates.join('、')}` : d.error;
      } catch { if (id === seq) out.textContent = ''; }
    }
    ['shift_code', 'start_date', 'end_date'].forEach(n => f[n].addEventListener('change', preview));
    preview();
  })();
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
    "leave.html": LEAVE,
    "dim_list.html": DIM_LIST,
    "dim_edit.html": DIM_EDIT,
}



def utc_text(iso):
    """'2026-10-08T03:12:00+00:00' → '2026-10-08 03:12:00'"""
    return iso[:19].replace("T", " ") if iso else ""


def _str_or_none(v):
    return v if isinstance(v, str) else None


def days_text(v):
    return f"{v:g}" if v else "0"


def pivot_to_view(pivot, totals, year, month=None):
    """把 RosterDB.roster_pivot 的結果轉成模板好用的 columns / rows。
    每格是 (roster_display, situation)；每列另帶上班 / 請假 / 加班天數小計。"""
    years = list(range(year - PIVOT_YEARS_BEFORE, year + PIVOT_YEARS_AFTER + 1))
    view = {"year": year, "month": month, "years": years, "columns": [], "rows": []}
    if pivot.empty:
        return view
    display, situation = pivot["roster_display"], pivot["situation"]
    for c in display.columns:
        d = dt.date.fromisoformat(c)
        view["columns"].append({"date": c, "label": d.strftime("%m-%d"), "weekday": d.strftime("%a"),
                                "weekend": d.isoweekday() >= 6})
    for key, cells in display.iterrows():
        team, office, name, employee_id = key
        t = totals.loc[key]
        view["rows"].append({
            "team": team, "office_code": office, "full_name": name, "employee_id": employee_id,
            "work": days_text(t["work_fraction"]), "leave": days_text(t["leave_fraction"]), "ot": days_text(t["ot_fraction"]),
            "cells": [(_str_or_none(v), _str_or_none(s)) for v, s in zip(cells, situation.loc[key])],
        })
    return view


def csv_safe(v):
    """避免 Excel 把使用者輸入（備註、原因）當成公式執行。"""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def pivot_export(view):
    """總覽 → CSV 欄位與資料列；待審核的請假加註（待審）。"""
    columns = ["team", "office_code", "full_name", "上班", "請假", "加班"] + [
        f"{c['date']} ({c['weekday']})" for c in view["columns"]]
    rows = [[r["team"], r["office_code"], r["full_name"], r["work"], r["leave"], r["ot"]]
            + [(f"{v}（待審）" if s == "PENDING" else v) or "" for v, s in r["cells"]]
            for r in view["rows"]]
    return columns, rows


def leave_export(requests, status_labels):
    columns = ["request_id", "employee_id", "full_name", "team", "office_code", "shift_code", "roster_display",
               "start_date", "end_date", "days", "reason", "status", "approver_id", "approver_name",
               "decided_at (UTC)", "decision_note", "created_at (UTC)"]
    rows = [[q["request_id"], q["employee_id"], q["full_name"], q["team"], q["office_code"], q["shift_code"],
             q["roster_display"], q["start_date"], q["end_date"], days_text(q["days"]), q["reason"],
             status_labels.get(q["status"], q["status"]), q["approver_id"], q["approver_name"],
             utc_text(q["decided_at"]), q["decision_note"], utc_text(q["created_at"])] for q in requests]
    return columns, rows


DETAIL_LABELS = {"work": "上班", "leave": "請假", "ot": "加班"}


def detail_view(kind, rows, title, all_people):
    """逐日明細彈窗的欄位與資料（JSON）。all_people 時多一欄姓名。"""
    columns = (["姓名"] if all_people else []) + ["日期", "星期", "日別", "班別", "時間", "工時", "天數"]
    columns += {"leave": ["狀態", "申請單"], "ot": ["標記加班"]}.get(kind, []) + ["備註 / 檢查"]
    out, total = [], 0
    for r in rows:
        time = (f"{r['planned_start_local'][11:]} → {r['planned_end_local'][11:]}"
                if r.get("planned_start_local") else "")
        day_type = r["day_type"] + (f" · {r['holiday_name']}" if r.get("holiday_name") else "")
        cells = ([r["name"]] if all_people else []) + [
            r["roster_date"], r["weekday"], day_type, f"{r['shift_code']} · {r['roster_display'] or ''}",
            time, days_text(r["planned_hours"]) if r.get("planned_hours") else "",
            "0（待審，不計入）" if r["pending"] else days_text(r["days"])]
        if kind == "leave":
            cells += ["待審核" if r["pending"] else (r["leave_approval_status"] or "—"),
                      r.get("leave_request_id") or "手動輸入"]
        elif kind == "ot":
            cells += ["是" if r["is_ot"] else "OT 班別"]
        cells.append("；".join(x for x in (r.get("remarks"), r.get("check_flag")) if x))
        total += 0 if r["pending"] else (r["days"] or 0)
        out.append({"cells": cells, "pending": r["pending"]})
    return {"ok": True, "title": f"{title} · {DETAIL_LABELS[kind]}明細（共 {days_text(total)} 天）",
            "columns": columns, "rows": out}


def calendar_view(year, month, days):
    """請假月曆：週一開始的格子；heat 0–4 依當天請假人數（含待審）決定顏色深淺。"""
    first = dt.date(year, month, 1)
    prev_m = (first - dt.timedelta(days=1)).replace(day=1)
    next_m = (first + dt.timedelta(days=32)).replace(day=1)
    today = dt.date.today()
    cells = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        for d in week:
            if d.month != month:
                cells.append(None)
                continue
            people = days.get(d.isoformat(), [])
            pending = sum(1 for p in people if p["pending"])
            cells.append({"day": d.day, "date": d.isoformat(), "weekday": "一二三四五六日"[d.weekday()],
                          "today": d == today, "people": people, "approved": len(people) - pending,
                          "pending": pending, "heat": min(len(people), 4)})
    return {"year": year, "month": month, "cells": cells,
            "prev": prev_m.strftime("%Y-%m"), "next": next_m.strftime("%Y-%m")}


def parse_month(s):
    """'2026-10' → (2026, 10)；空值或格式錯誤 → 本月。"""
    try:
        y, m = (int(x) for x in (s or "").split("-"))
        if 1 <= m <= 12 and 1900 <= y <= 9999:
            return y, m
    except ValueError:
        pass
    return dt.date.today().year, dt.date.today().month


def parse_date(s):
    return dt.date.fromisoformat(s) if s else None


def default_form():
    return {"start_date": dt.date.today().isoformat(), "end_date": "", "skip_non_working": True}


def with_waiting_for(requests, approvers):
    """自己的申請：待審核的加上「等誰審」，讓申請人知道單子在誰手上。"""
    names = "、".join(a["full_name"] for a in approvers[:3]) + (" 等" if len(approvers) > 3 else "")
    return [dict(q, waiting_for=names if q["status"] == "Pending" else None) for q in requests]


def default_leave_form():
    return {"shift_code": "", "start_date": dt.date.today().isoformat(), "end_date": "", "reason": ""}


def parse_leave_form(f):
    return {
        "shift_code": f.get("shift_code"),
        "start_date": f.get("start_date"),
        "end_date": f.get("end_date"),
        "reason": (f.get("reason") or "").strip() or None,
    }


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
