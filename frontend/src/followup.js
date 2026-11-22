const attendanceLabels = { pending: '待复核', confirmed: '已核销', rejected: '已驳回' };
const reasonLabels = { no_show: '未到诊', cancelled: '已取消' };
const improvementLabels = { planned: '待实施', implemented: '待验收', evaluated: '已验收' };
const tones = { pending: 'orange', confirmed: 'green', rejected: 'gray', planned: 'orange', implemented: 'blue', evaluated: 'green' };

export function followupViews({ state, api, shell, esc, fmtDate, openModal, toast, refresh, canEdit, canReview }) {
  const sampleFor = id => state.samples.find(sample => sample.id === id);
  const slotFor = id => state.slots.find(slot => slot.id === id);
  const reportFor = id => state.reports.find(report => report.id === id);
  const attendanceFor = id => state.attendance.find(row => row.sample_id === id);
  const isAdmin = () => state.user?.role === 'operations_admin';
  const badge = (value, labels) => `<span class="status status-${tones[value]}">${labels[value]}</span>`;
  const button = (action, id, label, style = 'btn-quiet') => `<button class="btn ${style}" data-followup="${action}" data-id="${id}">${label}</button>`;
  const note = (name, label) => `<label class="form-field followup-field">${label}<textarea name="${name}" rows="3" minlength="4" maxlength="500" required></textarea></label>`;
  const post = (url, payload) => api(url, { method: 'POST', body: JSON.stringify(payload) });

  function form(title, fields, submitLabel, submit, message, page) {
    openModal(title, `<form>${fields}<div class="modal-actions"><button type="button" class="btn btn-secondary close-action">取消</button><button class="btn btn-primary">${submitLabel}</button></div></form>`, (wrap, close) => {
      wrap.querySelector('.close-action').onclick = close;
      wrap.querySelector('form').onsubmit = async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const submitButton = form.querySelector('button[type="submit"], button:not([type])');
        submitButton.disabled = true;
        try {
          await submit(Object.fromEntries(new FormData(form)));
          close();
          if (page && state.page !== page) {
            state.page = page;
            location.hash = page;
          }
          toast(message);
          await refresh();
        } catch (error) {
          toast(error.message);
          submitButton.disabled = false;
        }
      };
    });
  }

  function sampleFilterStatus(sample) {
    const row = attendanceFor(sample.id);
    return row && row.status !== 'rejected' ? row.status : sample.status;
  }

  function sampleStatus(sample, original) {
    const row = attendanceFor(sample.id);
    if (!row || row.status === 'rejected') return original;
    const label = row.status === 'pending' ? { pending: '核销待复核' } : attendanceLabels;
    return badge(row.status, label);
  }

  function sampleActions(sample, original) {
    const row = attendanceFor(sample.id);
    if (row && row.status !== 'rejected') return '<a class="btn btn-quiet" href="#attendance">查看核销</a>';
    if (row || !canEdit() || !['booked', 'needs_review'].includes(sample.status) || sample.checkin_time) return original;
    const slot = slotFor(sample.department_slot_id);
    const now = new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }).replace(' ', 'T');
    if (!slot || now < `${slot.slot_date}T${slot.end_time}` || now < sample.appointment_time) return original;
    return `<div class="followup-buttons">${original}${button('submit-attendance', sample.id, '发起核销')}</div>`;
  }

  function renderAttendance() {
    const rows = [...state.attendance].sort((a, b) => Number(b.status === 'pending') - Number(a.status === 'pending'));
    const pending = rows.filter(row => row.status === 'pending').length;
    const body = rows.map(row => {
      const sample = sampleFor(row.sample_id);
      const slot = slotFor(sample?.department_slot_id);
      const review = canReview() && row.status === 'pending' && row.submitted_by !== state.user.id;
      return `<tr><td><b>${esc(sample?.sample_code)}</b><div class="muted">${esc(slot?.department_name)} · ${esc(slot?.slot_label)}</div><div class="muted">${fmtDate(sample?.appointment_time)}</div></td>
        <td>${reasonLabels[row.reason]}<div class="muted followup-note">${esc(row.evidence)}</div></td>
        <td>${badge(row.status, attendanceLabels)}${row.decision_note ? `<div class="muted followup-note">${esc(row.decision_note)}</div>` : ''}</td>
        <td><div class="followup-buttons">${review ? button('confirm', row.id, '确认核销', 'btn-warning') + button('reject', row.id, '驳回') : '<span class="muted">—</span>'}</div></td></tr>`;
    }).join('');
    return shell(`<section class="card page-card"><div class="toolbar"><div><div class="panel-title">预约核销记录</div><div class="panel-sub">待复核 ${pending} 条 · 共 ${rows.length} 条</div></div><a class="btn btn-secondary" href="#samples">返回候诊样本</a></div>
      <div class="table-wrap"><table><thead><tr><th>预约样本</th><th>原因与证据</th><th>状态与复核意见</th><th>操作</th></tr></thead><tbody>${body || '<tr><td colspan="4" class="empty">暂无记录。闭诊后可在候诊样本发起核销。</td></tr>'}</tbody></table></div></section>`,
    '未到诊核销', '处理闭诊后未签到的预约。已确认的核销只从新生成的分布报告中排除。');
  }

  function reportExclusions(report) {
    if (!report.exclusions.length) return '';
    const sampleList = report.exclusions.map(row => `${esc(row.sample_code)}（${reasonLabels[row.reason]}）`).join('、');
    return `<div class="callout followup-callout"><strong>本报告排除 ${report.exclusions.length} 条已核销预约</strong><p>${sampleList}</p><a href="#attendance">查看核销记录</a></div>`;
  }

  function reportAction(report) {
    if (state.improvements.some(row => row.baseline_report_id === report.id)) return '<a class="btn btn-quiet" href="#improvements">查看改善事项</a>';
    if (canEdit() && ['reviewed', 'archived'].includes(report.status) && !report.missing_checkin_count && report.sample_count >= 3 && report.p90_minutes > 0 && report.anomaly_codes.length) {
      return button('plan', report.id, '立项改善');
    }
    return '';
  }

  function renderImprovements() {
    const count = status => state.improvements.filter(row => row.status === status).length;
    const overview = Object.entries(improvementLabels).map(([status, label]) => `<div class="card metric"><div class="metric-label">${label}</div><div class="metric-value">${count(status)}</div></div>`).join('');
    const cards = state.improvements.map(row => {
      const report = reportFor(row.baseline_report_id);
      const comparison = reportFor(row.comparison_report_id);
      const slot = slotFor(report?.department_slot_id);
      const outcomeLabel = row.outcome === 'met' ? '目标达成' : '目标未达成';
      const outcome = row.outcome ? `<span class="status status-${row.outcome === 'met' ? 'green' : 'orange'}">${outcomeLabel}</span>` : '';
      const stats = [['基线 P90', row.baseline_p90], ['目标 P90', row.target_p90], ['复测 P90', row.comparison_p90], ['P90 变化', row.p90_change === null ? null : `${row.p90_change > 0 ? '+' : ''}${row.p90_change}`]];
      const actions = [row.status === 'planned' && isAdmin() ? button('implement', row.id, '记录措施实施', 'btn-primary') : '',
        row.status === 'implemented' && canReview() && row.implemented_by !== state.user.id ? button('evaluate', row.id, '选择报告验收', 'btn-warning') : '',
        row.status === 'evaluated' && canReview() ? button('withdraw', row.id, '撤回验收', 'btn-secondary') : ''].join('');
      return `<article class="card panel improvement-card"><div class="panel-head"><div><div class="panel-title">${esc(report?.title)}</div><div class="panel-sub">${esc(slot?.department_name)} · ${esc(slot?.slot_label)} · ${esc(slot?.slot_date)} · 异常样本 ${esc(row.anomaly_sample_code)}</div></div><div class="followup-buttons">${badge(row.status, improvementLabels)}${outcome}</div></div>
        <div class="detail-grid">${stats.map(([label, value]) => `<div class="detail-stat"><small>${label}</small><strong>${value ?? '—'}${value === null ? '' : '<small>分钟</small>'}</strong></div>`).join('')}</div>
        <dl class="followup-details"><dt>改善措施</dt><dd>${esc(row.action_plan)}</dd>${row.implemented_on ? `<dt>实施记录</dt><dd>${esc(row.implemented_on)} · ${esc(row.implementation_note)}</dd>` : ''}${comparison ? `<dt>验收报告</dt><dd>${esc(comparison.title)} · ${esc(comparison.report_code)}<br>${esc(row.evaluation_note)}</dd>` : ''}${row.withdrawn_count ? `<dt>撤回记录</dt><dd>已撤回 ${row.withdrawn_count} 次，原结论保留在下方「验收撤回记录」。</dd>` : ''}</dl>
        ${actions ? `<div class="followup-card-actions">${actions}</div>` : ''}</article>`;
    }).join('');
    return shell(`<section class="followup-overview">${overview}</section>${renderSlotBoard()}<section class="followup-cards">${cards || '<div class="card empty">暂无改善事项。请从含异常样本的已复核报告立项。</div>'}</section><a class="btn btn-secondary followup-link" href="#reports">查看复盘报告</a>`,
    '候诊改善追踪', '从长尾样本立项，用措施实施后同科室、同窗口的复测 P90 验收；同一门诊时段同时只能被一项改善占用。');
  }

  function renderSlotBoard() {
    const board = state.slotBoard;
    if (!board) return '';
    const claimRows = board.claims.map(item => `<tr>
      <td><b>${esc(item.department_name)}</b><div class="muted">${esc(item.slot_date)} · ${esc(item.slot_label)} · ${item.start_time.slice(0, 5)}–${item.end_time.slice(0, 5)}</div></td>
      <td>${esc(item.report_title)}<div class="muted">${esc(item.report_code)} · P90 ${item.report_p90 ?? '-'} 分钟</div></td>
      <td>改善 #${item.improvement_id}<div class="muted">${esc(item.improvement_action_plan)}</div></td>
      <td>${esc(item.claimed_by_name)}<div class="muted">${fmtDate(item.claimed_at)}</div></td>
    </tr>`).join('');
    const availableRows = board.available_slots.map(item => `<tr>
      <td><b>${esc(item.department_name)}</b><div class="muted">${esc(item.slot_date)} · ${esc(item.slot_label)}</div></td>
      <td>${item.reports.map(report => `<div>${esc(report.report_code)} · ${esc(report.title)}<span class="muted">（P90 ${report.p90_minutes ?? '-'} 分钟 · ${report.sample_count} 条）</span></div>`).join('')}</td>
    </tr>`).join('');
    const historyRows = (state.evaluationHistory || []).map(item => `<tr>
      <td>改善 #${item.improvement_id}<div class="muted">${esc(item.improvement_action_plan)}</div></td>
      <td><b>${esc(item.department_name)}</b><div class="muted">${esc(item.slot_date)} · ${esc(item.slot_label)}</div></td>
      <td>${esc(item.report_title)}<div class="muted">${esc(item.report_code)} · 复测 P90 ${item.comparison_p90} 分钟</div></td>
      <td><span class="status status-${item.outcome === 'met' ? 'green' : 'orange'}">${item.outcome === 'met' ? '目标达成' : '目标未达成'}</span><div class="muted followup-note">验收：${esc(item.evaluation_note)}</div></td>
      <td>${esc(item.evaluated_by_name)}<div class="muted">${fmtDate(item.evaluated_at)}</div></td>
      <td>${esc(item.withdrawn_by_name)}<div class="muted followup-note">${esc(item.withdrawal_note)}</div><div class="muted">${fmtDate(item.withdrawn_at)}</div></td>
    </tr>`).join('');
    return `<section class="card page-card followup-board"><div class="panel-title">门诊时段占用看板</div>
      <div class="panel-sub">验收认领的是报告对应的门诊时段；撤回后时段回到可选清单，原结论进入撤回记录。</div>
      <div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>被占用门诊时段</th><th>占用依据报告</th><th>占用方改善事项</th><th>验收人 / 时间</th></tr></thead>
      <tbody>${claimRows || '<tr><td colspan="4" class="empty">当前没有被占用的时段。</td></tr>'}</tbody></table></div>
      <div class="panel-title" style="margin-top:20px">可选门诊时段</div>
      <div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>门诊时段</th><th>可用于验收的报告</th></tr></thead>
      <tbody>${availableRows || '<tr><td colspan="2" class="empty">暂无可选时段；请先生成实施日后的合格报告。</td></tr>'}</tbody></table></div>
      <div class="panel-title" style="margin-top:20px">验收撤回记录</div>
      <div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>改善事项</th><th>原门诊时段</th><th>原验收报告</th><th>原结论</th><th>验收人 / 时间</th><th>撤回人 / 意见</th></tr></thead>
      <tbody>${historyRows || '<tr><td colspan="6" class="empty">暂无撤回记录。</td></tr>'}</tbody></table></div>
    </section>`;
  }

  const actions = {
    'submit-attendance': id => form('发起未到诊核销', `<p class="muted">预约 ${esc(sampleFor(id)?.sample_code)} 将交由科室复核。</p><label class="form-field followup-field">核销原因<select name="reason"><option value="no_show">未到诊</option><option value="cancelled">已取消</option></select></label>${note('evidence', '核对证据')}`,
      '提交核销', payload => post('/attendance-exceptions', { sample_id: id, ...payload }), '核销已提交科室复核', 'attendance'),
    confirm: id => attendanceDecision(id, 'confirmed', '确认核销'),
    reject: id => attendanceDecision(id, 'rejected', '驳回核销'),
    plan: id => {
      const report = reportFor(id);
      form('从长尾报告立项', `<p class="muted">${esc(report.title)} · 基线 P90 ${report.p90_minutes} 分钟</p><label class="form-field followup-field">异常样本<select name="anomaly_sample_code">${report.anomaly_codes.map(code => `<option>${esc(code)}</option>`).join('')}</select></label><label class="form-field followup-field">目标 P90（分钟）<input name="target_p90" type="number" min="0.1" step="0.1" required></label>${note('action_plan', '改善措施')}`,
        '创建改善事项', payload => post('/improvements', { baseline_report_id: id, ...payload, target_p90: Number(payload.target_p90) }), '改善事项已立项', 'improvements');
    },
    implement: id => form('记录措施实施', `<label class="form-field followup-field">实施日期<input name="implemented_on" type="date" required></label>${note('implementation_note', '实际安排与执行记录')}`,
      '确认实施', payload => post(`/improvements/${id}/implement`, payload), '已登记实施，等待复测验收'),
    evaluate: async id => {
      const reports = await api(`/improvements/${id}/comparisons`);
      if (!reports.length) return toast('暂无合格且未被占用的实施后复测报告。请生成报告并完成复核。');
      const options = reports.map(report => `<option value="${report.id}">${esc(slotFor(report.department_slot_id)?.slot_date)} · ${esc(report.title)} · P90 ${report.p90_minutes} 分钟 · ${report.sample_count} 条</option>`);
      form('验收候诊改善', `<p class="muted">提交后将占用所选报告对应的门诊时段；同一时段同时只能通过一项改善验收。</p><label class="form-field followup-field">复测报告<select name="comparison_report_id">${options.join('')}</select></label>${note('evaluation_note', '验收意见')}`,
        '提交验收', payload => post(`/improvements/${id}/evaluate`, { ...payload, comparison_report_id: Number(payload.comparison_report_id) }), '已保存复测和验收结论，并占用对应门诊时段'),
    },
    withdraw: id => form('撤回验收', `<p class="muted">撤回后本事项回到待验收，原验收结论将保留在撤回记录中，对应门诊时段重新开放给其他事项选择。</p>${note('withdrawal_note', '撤回原因')}`,
      '确认撤回', payload => post(`/improvements/${id}/withdraw`, payload), '验收已撤回，原结论已留档，时段已释放'),
  };

  function attendanceDecision(id, decision, label) {
    form(label, note('decision_note', '科室复核意见'), label,
      payload => post(`/attendance-exceptions/${id}/decision`, { decision, ...payload }), '核销复核已保存');
  }

  function attachEvents() {
    document.querySelectorAll('[data-followup]').forEach(element => {
      element.onclick = async () => {
        try { await actions[element.dataset.followup](Number(element.dataset.id)); }
        catch (error) { toast(error.message); }
      };
    });
  }

  return { renderAttendance, renderImprovements, sampleFilterStatus, sampleStatus, sampleActions, reportExclusions, reportAction, attachEvents };
}
