const releaseLabels = {
  proposed: ['待审批', 'orange'], approved: ['开放发放', 'green'],
  rejected: ['已驳回', 'gray'], closed: ['已收回', 'gray'],
};

export function capacityViews({ state, shell, esc, fmtDate, operationForm, focusId }) {
  const slotFor = id => state.slots.find(slot => slot.id === id);
  const localTime = time => esc(time.slice(0, 5));
  const action = (label, id, kind, style = 'secondary') =>
    `<button type="button" class="btn btn-${style}" data-release-action="${kind}" data-id="${id}">${label}</button>`;

  function renderRelease(row) {
    const slot = slotFor(row.slot_id);
    const role = state.user.role;
    const [label, color] = releaseLabels[row.status];
    const decision = row.decision_note ? `<p class="operations-note"><b>审批意见</b> ${esc(row.decision_note)}</p>` : '';
    const close = row.close_note ? `<p class="operations-note"><b>收回原因</b> ${esc(row.close_note)}</p>` : '';
    const bookings = row.bookings.map(booking => `<li><a href="#samples/${booking.sample_id}">${esc(booking.sample_code)}</a><span>${fmtDate(booking.appointment_time)}</span></li>`).join('');
    let actions = '';
    if (row.status === 'proposed' && role === 'department_reviewer') {
      actions = action('批准加号', row.id, 'approved', 'primary') + action('驳回加号', row.id, 'rejected');
    }
    if (row.status === 'approved') {
      if (row.available && ['analyst', 'operations_admin'].includes(role)) actions += action('发放加号', row.id, 'book', 'primary');
      if (role === 'operations_admin') actions += action('收回剩余名额', row.id, 'close');
    }
    return `<article class="card operations-card${focusId() === row.id ? ' operations-focus' : ''}" id="release-${row.id}">
      <header class="operations-heading"><div><div class="panel-sub">${esc(slot?.slot_date)} · ${esc(slot?.slot_label)}</div>
      <h2>${esc(slot?.department_name)} <span>${localTime(row.starts_at)}–${localTime(row.ends_at)}</span></h2></div>
      <span class="status status-${color}">${label}</span></header>
      <div class="operations-metrics"><div><small>申请名额</small><strong>${row.quantity}</strong></div><div><small>已发放</small><strong>${row.bookings.length}</strong></div><div><small>当前可发</small><strong>${row.available}</strong></div></div>
      <p class="operations-note"><b>排班依据</b> ${esc(row.staffing_note)}</p>${decision}${close}
      ${bookings ? `<div class="operations-ledger"><b>加号登记</b><ul>${bookings}</ul></div>` : ''}
      ${actions ? `<div class="operations-actions">${actions}</div>` : ''}</article>`;
  }

  function render() {
    const releases = state.releases;
    const canPropose = state.user.role === 'operations_admin' && state.slots.some(slot => slot.status === 'open');
    return shell(`<section class="operations-workspace"><div class="operations-toolbar"><p>按诊室支援时段申请额外号源，审批后逐笔发放。</p>
      ${canPropose ? action('申请临时加号', 0, 'propose', 'primary') : ''}</div>
      ${releases === null ? '<div class="card empty" role="status">正在载入加号批次…</div>' :
        `<div class="operations-grid">${releases.map(renderRelease).join('') || '<div class="card empty">当前没有临时加号批次。</div>'}</div>`}</section>`,
    '临时容量', '加号预约会进入候诊样本，发放记录留在对应的审批批次。');
  }

  function propose() {
    const slots = state.slots.filter(slot => slot.status === 'open');
    const options = slots.map(slot => `<option value="${slot.id}">${esc(slot.department_name)} · ${esc(slot.slot_date)} · ${esc(slot.slot_label)}</option>`).join('');
    operationForm('申请临时加号', `<label class="form-field full">复诊时段<select name="slot_id" required>${options}</select></label>
      <label class="form-field">加号开始<input type="time" name="starts_at" required></label>
      <label class="form-field">加号结束<input type="time" name="ends_at" required></label>
      <label class="form-field">申请名额<input type="number" name="quantity" min="1" max="100" required></label>
      <label class="form-field full">排班依据<textarea name="staffing_note" minlength="4" maxlength="500" rows="3" required></textarea></label>`,
    { label: '提交申请', endpoint: '/capacity-releases', payload: data => ({ ...data, slot_id: Number(data.slot_id), quantity: Number(data.quantity) }),
      setup: form => {
        const select = form.elements.slot_id;
        const fillWindow = () => {
          const slot = slotFor(Number(select.value));
          form.elements.starts_at.value = slot.start_time.slice(0, 5);
          form.elements.ends_at.value = slot.end_time.slice(0, 5);
          form.elements.quantity.max = slot.capacity;
        };
        select.onchange = fillWindow;
        fillWindow();
      } });
  }

  function book(row) {
    const slot = slotFor(row.slot_id);
    const first = `${slot.slot_date}T${row.starts_at.slice(0, 5)}`;
    operationForm('发放加号', `<p class="operations-form-summary full">${esc(slot.department_name)} ${localTime(row.starts_at)}–${localTime(row.ends_at)} · 剩余 ${row.available} 个名额</p>
      <label class="form-field">样本编号<input name="sample_code" minlength="3" maxlength="40" required></label>
      <label class="form-field">患者代号<input name="patient_alias" minlength="2" maxlength="80" required></label>
      <label class="form-field full">预约时间<input type="datetime-local" name="appointment_time" value="${first}" min="${first}" required></label>`,
    { label: '确认发放', endpoint: `/capacity-releases/${row.id}/bookings` });
  }

  function attachEvents() {
    document.querySelectorAll('[data-release-action]').forEach(button => button.onclick = () => {
      const kind = button.dataset.releaseAction;
      if (kind === 'propose') return propose();
      const row = state.releases.find(item => item.id === Number(button.dataset.id));
      if (kind === 'book') return book(row);
      const title = button.textContent;
      const closing = kind === 'close';
      operationForm(title, `<label class="form-field full">${closing ? '收回原因' : '审批意见'}<textarea name="note" rows="4" minlength="4" maxlength="500" required></textarea></label>`,
      { label: title, endpoint: `/capacity-releases/${row.id}/${closing ? 'close' : 'decision'}`,
        payload: data => closing ? data : { ...data, decision: kind } });
    });
    document.getElementById(`release-${focusId()}`)?.scrollIntoView({ block: 'nearest' });
  }

  return { render, attachEvents };
}
