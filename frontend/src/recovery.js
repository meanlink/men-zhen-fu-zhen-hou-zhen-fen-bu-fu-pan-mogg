const recoveryLabels = {
  pending: ['待科室分流', 'orange'], prioritized: ['待登记叫号', 'blue'],
  dismissed: ['已解除', 'gray'], recovered: ['处置已完成', 'green'],
};

export function recoveryViews({ state, api, shell, esc, fmtDate, operationForm, toast }) {
  const mayOpen = () => ['analyst', 'operations_admin'].includes(state.user.role);
  const slotFor = id => state.slots.find(slot => slot.id === id);

  function rowMarkup(row) {
    const sample = state.samples.find(item => item.id === row.sample_id);
    const slot = slotFor(sample?.department_slot_id);
    const [label, color] = recoveryLabels[row.status];
    const canDecide = state.user.role === 'department_reviewer' && row.status === 'pending';
    const decision = row.decision_note ? `<p class="operations-note">${esc(row.decision_note)}</p>` : '';
    const release = row.release_id ? `<a class="operations-inline-link" href="#capacity/${row.release_id}">加号批次 #${row.release_id}</a>` : '';
    let actions = '';
    if (canDecide) actions = `<button class="btn btn-primary" data-recovery="prioritized" data-id="${row.id}">安排优先叫号</button>
      <button class="btn btn-secondary" data-recovery="dismissed" data-id="${row.id}">解除处置</button>`;
    if (row.status === 'prioritized' && mayOpen()) actions = `<a class="btn btn-primary" href="#samples/${row.sample_id}">前往样本叫号</a>`;
    return `<tr><td><a class="operations-inline-link" href="#samples/${row.sample_id}"><b>${esc(sample?.sample_code)}</b></a>
      <div class="muted">${esc(slot?.department_name)} · ${esc(slot?.slot_label)}</div>${release}</td>
      <td><b>${row.observed_wait_minutes} 分钟</b><div class="muted">阈值 ${row.threshold_minutes} 分钟 · ${fmtDate(row.observed_at)}</div></td>
      <td><p class="operations-note">${esc(row.incident_note)}</p><span class="status status-${color}">${label}</span>${decision}</td>
      <td>${row.called_at ? `<b>${fmtDate(row.called_at)}</b><div class="muted">观察后 ${row.recovery_minutes} 分钟叫号</div>` : actions ? `<div class="operations-actions">${actions}</div>` : '<span class="muted">—</span>'}</td></tr>`;
  }

  function render() {
    const rows = state.recoveries;
    return shell(`<section class="card page-card operations-queue"><div class="toolbar"><div><div class="panel-title">时段超时记录</div>
      <div class="panel-sub">${rows === null ? '正在载入…' : `待分流 ${rows.filter(row => row.status === 'pending').length} 条 · 优先待叫号 ${rows.filter(row => row.status === 'prioritized').length} 条`}</div></div>
      ${rows !== null && mayOpen() ? '<button type="button" class="btn btn-primary" id="open-recovery">登记候诊超时</button>' : ''}</div>
      <div class="table-wrap"><table><thead><tr><th>候诊样本</th><th>现场观察</th><th>事件与处置</th><th>叫号结果 / 操作</th></tr></thead>
      <tbody>${rows === null ? '' : rows.map(rowMarkup).join('') || '<tr><td colspan="4" class="empty">暂无处置记录。候诊超过时段阈值时可登记。</td></tr>'}</tbody></table></div></section>`,
    '候诊处置台', '登记已签到但超出时段阈值的候诊，经科室分流后回到样本记录实际叫号。');
  }

  async function openTicket(button) {
    button.disabled = true;
    try {
      const candidates = await api('/queue-recoveries/candidates');
      if (!button.isConnected) return;
      if (!candidates.length) return toast('暂无已签到且尚未叫号的候诊样本');
      const options = candidates.map(sample => `<option value="${sample.id}">${esc(sample.sample_code)} · ${esc(slotFor(sample.department_slot_id)?.department_name)}</option>`).join('');
      operationForm('登记候诊超时', `<label class="form-field full">候诊样本<select name="sample_id">${options}</select></label>
        <p class="operations-form-summary full" data-candidate-details></p>
        <label class="form-field full">现场观察时间<input type="datetime-local" name="observed_at" required></label>
        <label class="form-field full">超时情况<textarea name="incident_note" rows="3" minlength="4" maxlength="500" required></textarea></label>`,
      { label: '提交分流', endpoint: '/queue-recoveries', payload: data => ({ ...data, sample_id: Number(data.sample_id) }),
        setup: form => {
          const select = form.elements.sample_id;
          const showCandidate = () => {
            const sample = candidates.find(item => item.id === Number(select.value));
            form.querySelector('[data-candidate-details]').textContent = `签到 ${fmtDate(sample.checkin_time)} · 时段阈值 ${sample.threshold_minutes} 分钟`;
            form.elements.observed_at.min = sample.checkin_time.slice(0, 16);
          };
          form.elements.observed_at.value = new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }).slice(0, 16).replace(' ', 'T');
          select.onchange = showCandidate;
          showCandidate();
        } });
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  }

  function attachEvents() {
    const open = document.getElementById('open-recovery');
    if (open) open.onclick = () => openTicket(open);
    document.querySelectorAll('[data-recovery]').forEach(button => button.onclick = () => {
      const title = button.textContent;
      const decision = button.dataset.recovery;
      operationForm(title, '<label class="form-field full">科室意见<textarea name="note" rows="4" minlength="4" maxlength="500" required></textarea></label>',
      { label: title, endpoint: `/queue-recoveries/${button.dataset.id}/decision`, payload: data => ({ ...data, decision }) });
    });
  }

  return { render, attachEvents };
}
