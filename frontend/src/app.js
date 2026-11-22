import { followupViews } from './followup.js';
import { capacityViews } from './capacity.js';
import { recoveryViews } from './recovery.js';

const API = '/api';
const hashPage = () => location.hash.slice(1).split('/')[0] || 'dashboard';
const focusId = () => Number(location.hash.split('/')[1]) || null;
const state = { token: localStorage.getItem('clinic_token'), user: JSON.parse(localStorage.getItem('clinic_user') || 'null'), page: hashPage(), slots: [], samples: [], reports: [], attendance: [], improvements: [], releases: null, recoveries: null, summary: null };
const roleNames = { analyst: '分析专员', department_reviewer: '科室复核员', operations_admin: '运营管理员' };
const sampleNames = { booked:'已预约', checked_in:'已签到', called:'已叫号', completed:'已完成', needs_review:'待复核' };
const reportNames = { draft:'草稿', under_review:'待科室复核', reviewed:'已复核', archived:'已归档' };

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(`${API}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请检查必填项和输入格式');
  return data;
}
function esc(value) { return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function fmtDate(value) { if (!value) return '-'; return new Date(value).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }); }
function statusClass(status) { return ({under_review:'status-orange', reviewed:'status-blue', archived:'status-green', completed:'status-green', called:'status-blue', checked_in:'status-blue', booked:'status-gray', needs_review:'status-orange'}[status] || 'status-gray'); }
function toast(message) { const old = document.querySelector('.toast'); if (old) old.remove(); const node = document.createElement('div'); node.className = 'toast'; node.textContent = message; document.body.appendChild(node); setTimeout(() => node.remove(), 3600); }
function openModal(title, body, onSubmit) { const wrap = document.createElement('div'); wrap.className = 'modal-backdrop'; wrap.innerHTML = `<div class="modal"><div class="modal-head"><div class="modal-title">${title}</div><button class="close">×</button></div><div class="modal-body">${body}</div></div>`; document.body.appendChild(wrap); wrap.querySelector('.close').onclick = () => wrap.remove(); wrap.onclick = (e) => { if (e.target === wrap) wrap.remove(); }; onSubmit(wrap, () => wrap.remove()); }
function navButton(id, icon, label) { return `<button class="${state.page === id ? 'active' : ''}" data-nav="${id}"><span class="nav-icon" aria-hidden="true">${icon}</span>${label}</button>`; }
function shell(content, title, subtitle) {
  return `<div class="app-shell"><aside class="sidebar"><div class="brand"><div class="brand-mark">CW</div><div>候诊复盘<small>CLINIC WAIT REVIEW</small></div></div><div class="nav-label">工作区</div><nav class="nav">${navButton('dashboard','◈','复盘总览')}${navButton('samples','◌','候诊样本')}${navButton('slots','▦','科室时段')}${navButton('reports','◫','复盘报告')}${navButton('attendance','⊙','未到诊核销')}${navButton('improvements','↗','候诊改善追踪')}${navButton('capacity','＋','临时容量')}${navButton('recovery','↻','候诊处置台')}</nav><div class="sidebar-footer"><div class="user-chip"><div class="avatar">${esc((state.user?.display_name || '用户').slice(0,1))}</div><div><div class="user-name">${esc(state.user?.display_name || '未登录')}</div><div class="user-role">${esc(roleNames[state.user?.role] || '')}</div></div></div><button class="btn btn-secondary" style="width:100%;margin-top:16px" id="logout">退出登录</button></div></aside><main class="main"><div class="topbar"><div><div class="eyebrow">EVIDENCE-LED OPERATIONS</div><h1>${title}</h1><div class="subtitle">${subtitle}</div></div><div class="top-actions"><div class="date-pill">数据日 · 2026.11.20</div>${state.page === 'samples' && canEdit() ? '<button class="btn btn-primary" id="new-sample">+ 录入样本</button>' : ''}${state.page === 'slots' && state.user?.role === 'operations_admin' ? '<button class="btn btn-primary" id="new-slot">+ 新建时段</button>' : ''}${state.page === 'reports' && canGenerate() ? '<button class="btn btn-primary" id="new-report">+ 生成复盘</button>' : ''}</div></div>${content}</main></div>`;
}
function canEdit() { return ['analyst','operations_admin'].includes(state.user?.role); }
function canGenerate() { return ['analyst','operations_admin'].includes(state.user?.role); }
async function loadAll() { [state.summary, state.slots, state.samples, state.reports, state.attendance, state.improvements] = await Promise.all([api('/dashboard/summary'), api('/slots'), api('/samples'), api('/reports'), api('/attendance-exceptions'), api('/improvements')]); }

function renderDashboard() {
  const s = state.summary || {};
  const latest = state.reports.slice(0, 3);
  const slotRows = state.slots.slice(0, 4).map(slot => `<tr><td><b>${esc(slot.department_name)}</b><div class="muted">${esc(slot.slot_label)}</div></td><td>${slot.slot_date}</td><td>${slot.start_time.slice(0,5)} — ${slot.end_time.slice(0,5)}</td><td>${slot.threshold_minutes} 分钟</td><td><span class="status status-green">开放</span></td></tr>`).join('');
  const reportRows = latest.map(r => `<tr><td><b>${esc(r.title)}</b><div class="muted">${r.report_code}</div></td><td>${r.p50_minutes ?? '-'} 分钟</td><td>${r.anomaly_count} 条</td><td><span class="status ${statusClass(r.status)}">${reportNames[r.status]}</span></td></tr>`).join('');
  const counts = latest[0]?.distribution || [{label:'0-14 分钟',count:0},{label:'15-29 分钟',count:0},{label:'30-44 分钟',count:0},{label:'45-59 分钟',count:0},{label:'60 分钟以上',count:0}]; const max = Math.max(...counts.map(x => x.count), 1);
  const bars = counts.map(x => `<div class="bar-item"><div class="bar-value">${x.count}</div><div class="bar" style="height:${Math.max(8, x.count / max * 150)}px"></div><div class="bar-label">${x.label.replace(' 分钟','')}</div></div>`).join('');
  return shell(`<section class="grid-4"><div class="card metric"><div class="metric-label">开放科室时段</div><div class="metric-value">${s.slot_count || 0}</div><div class="metric-note">今日已配置复诊窗口</div></div><div class="card metric orange"><div class="metric-label">候诊样本</div><div class="metric-value">${s.sample_count || 0}</div><div class="metric-note">预约台 + 现场加号</div></div><div class="card metric orange"><div class="metric-label">待科室复核</div><div class="metric-value">${s.under_review_count || 0}</div><div class="metric-note">超过阈值或长尾样本</div></div><div class="card metric green"><div class="metric-label">已归档报告</div><div class="metric-value">${s.archived_count || 0}</div><div class="metric-note">可供排班复盘引用</div></div></section><section class="section-grid"><div class="card panel"><div class="panel-head"><div><div class="panel-title">最近一份候诊分布</div><div class="panel-sub">基于最近生成的复盘报告，按候诊时长分桶</div></div><span class="status status-blue">P50 ${latest[0]?.p50_minutes ?? '-'} 分钟</span></div><div class="bar-chart">${bars}</div><div class="callout" style="margin-top:16px"><strong>${latest[0]?.summary || '请先在复盘报告页生成一份时段报告。'}</strong><p>算法同时计算 P50、P90 与 MAD。超过科室阈值的候诊样本会进入科室复核，缺失签到时间会阻断发布。</p></div></div><div class="card panel"><div class="panel-head"><div><div class="panel-title">科室时段</div><div class="panel-sub">阈值用于识别长尾候诊</div></div><button class="btn btn-quiet" data-nav="slots">查看全部</button></div><div class="table-wrap"><table><thead><tr><th>科室</th><th>日期</th><th>窗口</th><th>阈值</th><th>状态</th></tr></thead><tbody>${slotRows || '<tr><td colspan="5" class="empty">暂无数据</td></tr>'}</tbody></table></div></div></section><section class="card panel" style="margin-top:18px"><div class="panel-head"><div><div class="panel-title">最近复盘报告</div><div class="panel-sub">复核状态和异常样本会被完整保留</div></div><button class="btn btn-quiet" data-nav="reports">进入报告库</button></div><div class="table-wrap"><table><thead><tr><th>报告</th><th>P50</th><th>异常</th><th>状态</th></tr></thead><tbody>${reportRows || '<tr><td colspan="4" class="empty">暂无报告</td></tr>'}</tbody></table></div></section>`, '复盘总览', '把候诊等待从一张表，整理成可复核的分布证据。'); }

function renderSamples() { const rows = state.samples.map(s => `<tr data-status="${followup.sampleFilterStatus(s)}"><td><b>${esc(s.sample_code)}</b><div class="muted">${esc(s.patient_alias)} · ${esc(s.source_channel)}</div></td><td>${fmtDate(s.appointment_time)}</td><td>${fmtDate(s.checkin_time)}</td><td>${fmtDate(s.called_time)}</td><td>${followup.sampleStatus(s, `<span class="status ${statusClass(s.status)}">${sampleNames[s.status]}</span>`)}</td><td>${followup.sampleActions(s, canEdit() && s.status === 'booked' ? `<button class="btn btn-quiet checkin" data-id="${s.id}">补签到</button>` : canEdit() && s.status === 'checked_in' ? `<button class="btn btn-quiet call" data-id="${s.id}">登记叫号</button>` : canEdit() && s.status === 'called' ? `<button class="btn btn-success complete" data-id="${s.id}">完成接诊</button>` : '<span class="muted">—</span>')}</td></tr>`).join(''); return shell(`<section class="card page-card"><div class="toolbar"><div class="filters"><input class="search" id="sample-search" placeholder="搜索样本编号、患者代号或渠道" /><select id="sample-status"><option value="">全部状态</option>${Object.entries({ ...sampleNames, pending: '核销待复核', confirmed: '已核销' }).map(([k,v]) => `<option value="${k}">${v}</option>`).join('')}</select></div><div class="muted">${state.samples.length} 条样本</div></div><div class="table-wrap"><table id="samples-table"><thead><tr><th>样本</th><th>预约时间</th><th>签到时间</th><th>叫号时间</th><th>当前状态</th><th>动作</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="empty">暂无候诊样本</td></tr>'}</tbody></table></div></section>`, '候诊样本', '预约、签到和叫号事件在同一条样本上串成可追溯的候诊记录。'); }

function renderSlots() { const rows = state.slots.map(s => `<tr><td><b>${esc(s.department_name)}</b></td><td>${s.slot_date}</td><td>${esc(s.slot_label)}</td><td>${s.start_time.slice(0,5)} — ${s.end_time.slice(0,5)}</td><td><b>${s.threshold_minutes} 分钟</b><div class="muted">容量 ${s.capacity}</div></td><td><span class="status status-green">${esc(s.status === 'open' ? '开放' : s.status)}</span></td></tr>`).join(''); return shell(`<section class="card page-card"><div class="toolbar"><div><div class="panel-title">科室复诊窗口</div><div class="panel-sub">每个时段拥有独立候诊阈值，复盘算法按时段切片。</div></div><a class="btn btn-secondary" href="#capacity">查看临时容量</a></div><div class="table-wrap"><table><thead><tr><th>科室</th><th>日期</th><th>窗口标签</th><th>时间段</th><th>阈值 / 容量</th><th>状态</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="empty">暂无时段</td></tr>'}</tbody></table></div></section>`, '科室时段', '先定义当天的复诊窗口，再让样本和报告沿着窗口汇总。'); }

function renderReports() { const cards = state.reports.map(r => `<div class="card panel"><div class="panel-head"><div><div class="panel-title">${esc(r.title)}</div><div class="panel-sub">${r.report_code} · ${fmtDate(r.created_at)}</div></div><span class="status ${statusClass(r.status)}">${reportNames[r.status]}</span></div><div class="detail-grid"><div class="detail-stat"><small>P50 候诊</small><strong>${r.p50_minutes ?? '-'}<small>分钟</small></strong></div><div class="detail-stat"><small>P90 长尾</small><strong>${r.p90_minutes ?? '-'}<small>分钟</small></strong></div><div class="detail-stat"><small>MAD</small><strong>${r.mad_minutes ?? '-'}<small>分钟</small></strong></div><div class="detail-stat"><small>异常样本</small><strong>${r.anomaly_count}<small>条</small></strong></div></div><div class="muted" style="font-size:12px;line-height:1.7">${esc(r.summary || '')}</div>${r.missing_checkin_count ? `<div class="callout" style="margin-top:14px;background:#fff8ed;border-color:#f9dfba"><strong>发布被阻断</strong><p>当前有 ${r.missing_checkin_count} 条样本缺签到或叫号。补齐记录或确认核销后，请重新生成报告。</p></div>` : ''}${followup.reportExclusions(r)}<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">${followup.reportAction(r)}${r.status === 'under_review' && canReview() ? `<button class="btn btn-warning review-report" data-id="${r.id}">完成科室复核</button>` : ''}${r.status === 'reviewed' && state.user?.role === 'operations_admin' ? `<button class="btn btn-success archive-report" data-id="${r.id}">归档报告</button>` : ''}</div></div>`).join(''); return shell(`<section style="display:grid;gap:16px">${cards || '<div class="card empty">暂无复盘报告。请先选择科室时段生成一份分布复盘。</div>'}</section>`, '复盘报告', '从分布统计到科室复核，再到可留档的运营证据。'); }
function canReview() { return ['department_reviewer','operations_admin'].includes(state.user?.role); }

const followup = followupViews({ state, api, shell, esc, fmtDate, openModal, toast, refresh, canEdit, canReview });
const capacity = capacityViews({ state, shell, esc, fmtDate, operationForm, focusId });
const recovery = recoveryViews({ state, api, shell, esc, fmtDate, operationForm, toast });

function operationForm(title, fields, { label, endpoint, payload = data => data, setup }) {
  openModal(title, `<form class="operations-form"><div class="form-grid">${fields}</div><p class="operations-error" role="alert" hidden></p>
    <div class="modal-actions"><button type="button" class="btn btn-secondary close-action">取消</button>
    <button type="submit" class="btn btn-primary">${label}</button></div></form>`, (wrap, close) => {
    const form = wrap.querySelector('form');
    const submit = form.querySelector('[type="submit"]');
    const error = form.querySelector('[role="alert"]');
    form.querySelector('.close-action').onclick = close;
    setup?.(form);
    form.onsubmit = async event => {
      event.preventDefault();
      submit.disabled = true;
      error.hidden = true;
      try {
        const body = JSON.stringify(payload(Object.fromEntries(new FormData(form))));
        await api(endpoint, { method: 'POST', body });
        close();
        await refresh();
      } catch (failure) {
        error.textContent = failure.message;
        error.hidden = false;
      } finally {
        submit.disabled = false;
      }
    };
  });
}

async function loadOperations(page) {
  const route = { capacity: ['releases', '/capacity-releases'], recovery: ['recoveries', '/queue-recoveries'] }[page];
  if (!route) return;
  const identity = state.token;
  const data = await api(route[1]);
  if (state.token === identity) state[route[0]] = data;
}


function attachPageEvents() {
  followup.attachEvents();
  capacity.attachEvents();
  recovery.attachEvents();
  document.querySelectorAll('[data-nav]').forEach(el => el.onclick = () => { location.hash = el.dataset.nav; });
  document.getElementById('logout')?.addEventListener('click', () => { localStorage.clear(); state.token = null; state.user = null; state.releases = null; state.recoveries = null; renderLogin(); });
  document.getElementById('new-slot')?.addEventListener('click', showSlotModal);
  document.getElementById('new-sample')?.addEventListener('click', showSampleModal);
  document.getElementById('new-report')?.addEventListener('click', showReportModal);
  document.querySelectorAll('.checkin').forEach(btn => btn.onclick = () => showActionModal(btn.dataset.id, 'checkin', '补登记签到'));
  document.querySelectorAll('.call').forEach(btn => btn.onclick = () => showActionModal(btn.dataset.id, 'call', '登记叫号'));
  document.querySelectorAll('.complete').forEach(btn => btn.onclick = () => showActionModal(btn.dataset.id, 'complete', '完成接诊'));
  document.querySelectorAll('.review-report').forEach(btn => btn.onclick = () => showReviewModal(btn.dataset.id));
  document.querySelectorAll('.archive-report').forEach(btn => btn.onclick = async () => { try { await api(`/reports/${btn.dataset.id}/archive`, { method:'POST' }); toast('报告已归档'); await refresh(); } catch (e) { toast(e.message); } });
  const search = document.getElementById('sample-search'); const status = document.getElementById('sample-status');
  if (search && status) { const filter = () => { const query = search.value.toLowerCase(); document.querySelectorAll('#samples-table tbody tr').forEach(row => { const text = row.textContent.toLowerCase(); row.style.display = text.includes(query) && (!status.value || row.dataset.status === status.value) ? '' : 'none'; }); }; search.oninput = filter; status.onchange = filter;
    const sample = state.samples.find(item => item.id === focusId());
    if (sample) { search.value = sample.sample_code; filter(); }
  }
}
function showSlotModal() { openModal('新建科室时段', `<div class="form-grid"><div class="form-field"><label>科室名称</label><input name="department_name" value="心内科" /></div><div class="form-field"><label>窗口标签</label><input name="slot_label" value="上午复诊" /></div><div class="form-field"><label>日期</label><input type="date" name="slot_date" value="2026-11-21" /></div><div class="form-field"><label>阈值（分钟）</label><input type="number" name="threshold_minutes" value="30" /></div><div class="form-field"><label>开始时间</label><input type="time" name="start_time" value="08:30" /></div><div class="form-field"><label>结束时间</label><input type="time" name="end_time" value="12:00" /></div><div class="form-field"><label>容量</label><input type="number" name="capacity" value="20" /></div></div><div class="modal-actions"><button class="btn btn-secondary close-action">取消</button><button class="btn btn-primary submit-action">保存时段</button></div>`, (wrap, close) => { wrap.querySelector('.close-action').onclick = close; wrap.querySelector('.submit-action').onclick = async () => { const payload = {}; wrap.querySelectorAll('input').forEach(i => payload[i.name] = i.value); payload.threshold_minutes = Number(payload.threshold_minutes); payload.capacity = Number(payload.capacity); try { await api('/slots', { method:'POST', body:JSON.stringify(payload) }); close(); toast('科室时段已保存'); await refresh(); } catch (e) { toast(e.message); } }; }); }
function showSampleModal() { const options = state.slots.map(s => `<option value="${s.id}">${esc(s.department_name)} · ${esc(s.slot_label)} · ${s.slot_date}</option>`).join(''); openModal('录入预约样本', `<div class="form-grid"><div class="form-field"><label>样本编号</label><input name="sample_code" value="OP-${Date.now().toString().slice(-6)}" /></div><div class="form-field"><label>患者代号</label><input name="patient_alias" value="新登记患者" /></div><div class="form-field full"><label>科室时段</label><select name="department_slot_id">${options}</select></div><div class="form-field"><label>预约时间</label><input type="datetime-local" name="appointment_time" value="2026-11-20T15:00" /></div><div class="form-field"><label>签到时间（可留空）</label><input type="datetime-local" name="checkin_time" /></div><div class="form-field full"><label>来源渠道</label><select name="source_channel"><option>线上预约</option><option>电话预约</option><option>现场加号</option></select></div></div><div class="modal-actions"><button class="btn btn-secondary close-action">取消</button><button class="btn btn-primary submit-action">保存样本</button></div>`, (wrap, close) => { wrap.querySelector('.close-action').onclick=close; wrap.querySelector('.submit-action').onclick=async()=>{ const payload={}; wrap.querySelectorAll('input,select').forEach(i=>payload[i.name]=i.value || null); payload.department_slot_id=Number(payload.department_slot_id); try{await api('/samples',{method:'POST',body:JSON.stringify(payload)});close();toast('候诊样本已录入');await refresh();}catch(e){toast(e.message);}}; }); }
function showReportModal() { const options = state.slots.map(s => `<option value="${s.id}">${esc(s.department_name)} · ${esc(s.slot_label)} · ${s.slot_date}</option>`).join(''); openModal('生成分布复盘', `<div class="callout"><strong>Python 统计会从当前样本重新计算</strong><p>报告会给出候诊时长分桶、P50、P90、MAD，并把超过时段阈值的样本列入复核。</p></div><div class="form-grid" style="margin-top:16px"><div class="form-field full"><label>科室时段</label><select name="department_slot_id">${options}</select></div><div class="form-field full"><label>报告标题</label><input name="title" value="${new Date().toLocaleDateString('zh-CN')} 候诊分布复盘" /></div></div><div class="modal-actions"><button class="btn btn-secondary close-action">取消</button><button class="btn btn-primary submit-action">生成报告</button></div>`, (wrap, close) => { wrap.querySelector('.close-action').onclick=close; wrap.querySelector('.submit-action').onclick=async()=>{ const payload={};wrap.querySelectorAll('input,select').forEach(i=>payload[i.name]=i.value);payload.department_slot_id=Number(payload.department_slot_id);try{await api('/reports',{method:'POST',body:JSON.stringify(payload)});close();toast('复盘报告已生成，等待科室复核');state.page='reports';location.hash='reports';await refresh();}catch(e){toast(e.message);}}; }); }
function showActionModal(id, action, title) { openModal(title, `<div class="form-field"><label>事件时间</label><input type="datetime-local" name="event_time" value="2026-11-20T17:00" /></div><div class="form-field" style="margin-top:12px"><label>备注</label><textarea name="note" rows="3" placeholder="记录现场情况"></textarea></div><div class="modal-actions"><button class="btn btn-secondary close-action">取消</button><button class="btn btn-primary submit-action">确认${title}</button></div>`, (wrap, close) => { wrap.querySelector('.close-action').onclick=close; wrap.querySelector('.submit-action').onclick=async()=>{const payload={};wrap.querySelectorAll('input,textarea').forEach(i=>payload[i.name]=i.value);try{await api(`/samples/${id}/${action}`,{method:'POST',body:JSON.stringify(payload)});close();toast('样本状态已更新');await refresh();}catch(e){toast(e.message);}};}); }
function showReviewModal(id) { openModal('科室复核', `<div class="callout"><strong>复核确认会进入报告归档链路</strong><p>请写下对超阈值样本的解释，例如医生迟到、加号插入或检查室切换。</p></div><div class="form-field" style="margin-top:16px"><label>复核意见</label><textarea name="review_note" rows="4">已核对叫号记录，长尾样本与现场加号有关。</textarea></div><div class="modal-actions"><button class="btn btn-secondary close-action">取消</button><button class="btn btn-warning submit-action">提交复核</button></div>`, (wrap, close) => { wrap.querySelector('.close-action').onclick=close;wrap.querySelector('.submit-action').onclick=async()=>{try{await api(`/reports/${id}/review`,{method:'POST',body:JSON.stringify({review_note:wrap.querySelector('textarea').value})});close();toast('科室复核已完成');await refresh();}catch(e){toast(e.message);}};}); }

async function refresh() { try { await Promise.all([loadAll(), loadOperations(state.page)]); render(); } catch(e) { toast(e.message); } }
function render() { if (!state.token) return renderLogin(); const pages = { dashboard: renderDashboard, samples: renderSamples, slots: renderSlots, reports: renderReports, attendance: followup.renderAttendance, improvements: followup.renderImprovements, capacity: capacity.render, recovery: recovery.render }; document.getElementById('app').innerHTML = (pages[state.page] || renderDashboard)(); attachPageEvents(); }
function renderLogin() { document.getElementById('app').innerHTML = `<div class="login-shell"><section class="login-visual"><div><div class="brand"><div class="brand-mark">CW</div><div>候诊复盘<small>CLINIC WAIT REVIEW</small></div></div><div class="eyebrow" style="color:#6fdbcc;margin-top:80px">DATA INTO DECISIONS</div><h1>让每一次等待<br>都能被解释。</h1><p>把预约、签到和叫号事件串成一条有证据的复诊复盘链路。看见分布、识别长尾、留下科室复核意见。</p></div><div class="mini-bars"><span style="height:56px"></span><span style="height:110px"></span><span style="height:78px"></span><span style="height:142px"></span><span style="height:92px"></span><span style="height:164px"></span></div></section><section class="login-panel"><div class="login-box"><div class="eyebrow">CLINIC OPERATIONS</div><h2>登录工作台</h2><div class="hint">使用你的角色账号进入候诊分布复盘。</div><div class="form-field"><label>账号</label><input id="login-username" value="analyst" /></div><div class="form-field" style="margin-top:14px"><label>密码</label><input id="login-password" type="password" value="demo123" /></div><button class="btn btn-primary" id="login-btn" style="width:100%;margin-top:20px">进入复盘工作台</button><div class="demo-accounts"><b>演示账号</b><br>analyst 分析专员 · reviewer 科室复核员 · admin 运营管理员<br>统一密码 demo123</div></div></section></div>`; document.getElementById('login-btn').onclick=async()=>{try{const data=await api('/auth/login',{method:'POST',body:JSON.stringify({username:document.getElementById('login-username').value,password:document.getElementById('login-password').value})});state.token=data.access_token;state.user=data.user;localStorage.setItem('clinic_token',state.token);localStorage.setItem('clinic_user',JSON.stringify(state.user));await refresh();}catch(e){toast(e.message);}}; }
window.addEventListener('hashchange', async () => {
  state.page = hashPage();
  if (state.page === 'capacity') state.releases = null;
  if (state.page === 'recovery') state.recoveries = null;
  render();
  const page = state.page;
  if (state.token && ['capacity', 'recovery'].includes(page)) {
    try {
      await loadOperations(page);
      if (state.page === page) render();
    } catch (error) { toast(error.message); }
  }
});
if (state.token) refresh(); else renderLogin();
