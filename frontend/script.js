// Same server for page + API when deployed (and when opened on port 8000); only a separately
// served local page (e.g. VS Code Live Server) needs the explicit address.
const LOCAL = ['localhost', '127.0.0.1', ''].includes(location.hostname);
const API = (LOCAL && location.port !== '8000') ? 'http://127.0.0.1:8000' : '';
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
const SLOTS = ['09:00', '10:00', '11:00', '12:00', '14:00', '15:00', '16:00'];
const ACTIVE = ['Pending', 'Accepted', 'Rescheduled'];

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const qs = o => '?' + new URLSearchParams(o);

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove('show'), 3200);
}

async function api(path, method = 'GET', body) {
  try {
    const res = await fetch(API + path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined
    });
    return await res.json();
  } catch (e) {
    return { success: false, message: 'Cannot reach the server. Is server.py running?' };
  }
}
const list = x => (Array.isArray(x) ? x : []);

let me = JSON.parse(sessionStorage.getItem('campus_user'));
const freshUi = () => ({
  view: 'dashboard',
  fac: '', day: 'Mon', pick: null, topic: '',
  resId: null,
  rsId: null, rsDay: 'Mon', rsPick: null, rsReason: '',
  calFac: '', lastNid: 0,
  docQ: '', docTitle: '', docSubject: '', docDesc: '', docFile: null,
  admFac: '', venueDraft: {},
  chatContact: '', chatMessage: ''
});
let ui = freshUi();
let pollTimer = null;

$('loginForm').onsubmit = async e => {
  e.preventDefault();
  const res = await api('/api/login', 'POST', { email: $('email').value.trim(), password: $('password').value });
  if (!res.success) { $('authMsg').textContent = res.message; return; }
  me = { user_id: res.user_id, name: res.name, role: res.role };
  sessionStorage.setItem('campus_user', JSON.stringify(me));
  $('loginForm').reset(); $('authMsg').textContent = '';
  start();
};
$('logoutBtn').onclick = () => {
  sessionStorage.removeItem('campus_user'); me = null;
  clearInterval(pollTimer);
  ui = freshUi();
  $('appView').hidden = true; $('authView').hidden = false; toast('You have been logged out');
};

function start() {
  $('authView').hidden = true; $('appView').hidden = false;
  $('userName').textContent = me.name; $('userRole').textContent = me.role;
  $('avatar').textContent = me.name[0].toUpperCase();
  ui = freshUi();
  const admin = me.role === 'Admin';
  document.querySelectorAll('.navbtn[data-view]').forEach(b => b.hidden = admin && b.dataset.view !== 'dashboard');
  render();
  clearInterval(pollTimer);
  if (admin) { setBadge(0); return; }   // admin has no notifications
  pollNotifs(true);
  pollTimer = setInterval(() => pollNotifs(false), 10000);
}

async function render() {
  document.querySelectorAll('.navbtn[data-view]').forEach(b =>
    b.classList.toggle('active', b.dataset.view === ui.view));
  const views = { calendar: calendarView, notifications: notificationsView, documents: documentsView, chat: chatView };
  const view = views[ui.view] || { Student: studentView, Faculty: facultyView, Admin: adminView }[me.role];
  $('content').innerHTML = await view();
}

document.querySelectorAll('.navbtn[data-view]').forEach(b => b.onclick = () => { ui.view = b.dataset.view; render(); });

const formOpen = () => ui.resId || ui.rsId || ui.pick || ui.topic || ui.rsReason || Object.keys(ui.venueDraft).length
  || (ui.view === 'documents' && (ui.docTitle || ui.docSubject || ui.docDesc || ui.docFile || ui.docQ));

function setBadge(n) {
  const b = $('navBadge'); b.textContent = n > 99 ? '99+' : n; b.hidden = !n;
}

async function pollNotifs(first) {
  if (!me || me.role === 'Admin') return;
  const r = await api('/api/notifications' + qs({ user_id: me.user_id }));
  if (!r.success) return;
  setBadge(r.unread);
  const top = (r.notifications[0] || {}).notification_id || 0;
  if (!first && top > ui.lastNid) {
    toast('🔔 ' + r.notifications[0].message);
    if (!formOpen()) render();
  }
  ui.lastNid = top;
}

const KIND = {
  booking: ['📩', 'info'], accepted: ['✅', 'good'], rejected: ['❌', 'bad'], cancelled: ['🚫', 'bad'],
  rescheduled: ['🔄', 'warn'], reschedule_request: ['🔁', 'warn'], reschedule_approved: ['✅', 'good'],
  reschedule_declined: ['❌', 'bad'], reschedule_withdrawn: ['↩️', 'info'], reminder: ['⏰', 'info'], document: ['📄', 'info'], venue: ['📍', 'info']
};

function ago(ts) {
  const d = new Date(String(ts).replace(' ', 'T') + 'Z'), s = Math.max(0, (Date.now() - d) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s / 60) + ' min ago';
  if (s < 86400) return Math.floor(s / 3600) + ' h ago';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

async function notificationsView() {
  const r = await api('/api/notifications' + qs({ user_id: me.user_id }));
  const items = list(r.notifications);
  setBadge(r.unread || 0);
  return `
  <div class="card">
    <div class="row head"><div><h2>Notifications</h2>
      <p class="muted small">${r.unread ? r.unread + ' unread' : 'You are all caught up'}</p></div>
      <button class="btn ghost small" data-act="readAll" ${r.unread ? '' : 'disabled'}>Mark all as read</button></div>
    ${items.map(n => { const [icon, tone] = KIND[n.kind] || ['🔔', 'info'];
      return `<button class="notif ${tone} ${n.is_read ? '' : 'unread'}" data-act="readOne" data-id="${n.notification_id}">
        <span class="nicon">${icon}</span>
        <span class="ntext">${esc(n.message)}<small>${ago(n.created_at)}</small></span>
        ${n.is_read ? '' : '<span class="dot" aria-label="Unread"></span>'}</button>`; }).join('')
      || '<p class="muted">No notifications yet. They appear when bookings are made, answered, moved or cancelled.</p>'}
  </div>`;
}

async function calendarView() {
  const needFac = me.role !== 'Faculty';
  const facs = needFac ? list(await api('/api/faculty')) : [];
  const cal = await api('/api/calendar' + qs({ user_id: me.user_id, ...(needFac && ui.calFac ? { faculty_id: ui.calFac } : {}) }));
  if (!cal.success) return `<div class="card"><p class="error">${esc(cal.message)}</p></div>`;

  const showFree = cal.faculty_id != null;
  const fmt = iso => new Date(iso + 'T00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  const cell = (d, t) => {
    const ev = cal.events.filter(e => e.day === d.day && e.time_slot === t);
    const inner = ev.map(e => e.kind === 'class'
        ? `<div class="ev class"><b>${esc(e.title)}</b><small>${esc(e.detail)}</small></div>`
        : e.kind === 'busy'
        ? `<div class="ev busy"><b>${esc(e.title)}</b><small>${esc(e.detail)}</small></div>`
        : `<div class="ev appt ${e.status}"><b>${esc(e.title)}</b><small>${esc(e.detail)}</small>
            ${e.moving_to ? `<small class="mv">→ asked to move to ${esc(e.moving_to)}</small>` : ''}
            <span class="tag ${e.status}">${e.status}</span></div>`).join('');
    if (inner) return `<td class="${d.is_today ? 'today' : ''}">${inner}</td>`;
    if (showFree && me.role === 'Student')
      return `<td class="${d.is_today ? 'today' : ''}"><button class="ev free link" data-act="calbook" data-d="${d.day}" data-t="${t}">Free<small>Book this</small></button></td>`;
    return `<td class="${d.is_today ? 'today' : ''}">${showFree ? '<div class="ev free">Free</div>' : ''}</td>`;
  };

  const titles = { Student: 'My calendar', Faculty: 'My calendar', Admin: 'Campus calendar' };
  return `
  <div class="card">
    <h2>${titles[me.role]}</h2>
    <p class="muted small">Week of ${fmt(cal.days[0].date)} – ${fmt(cal.days[4].date)}. Meetings repeat in the same weekly slot.</p>
    ${needFac ? `<label for="calFacSel">${me.role === 'Student' ? 'View a faculty member’s availability' : 'Show'}</label>
      <select id="calFacSel" data-change="calFac">
        <option value="">${me.role === 'Student' ? 'Only my bookings' : 'All faculty'}</option>
        ${facs.map(f => `<option value="${f.user_id}" ${String(f.user_id) === String(ui.calFac) ? 'selected' : ''}>${esc(f.name)}</option>`).join('')}
      </select>` : ''}
    <div class="legend">
      <span><i class="sw class"></i>Class</span><span><i class="sw Accepted"></i>Confirmed</span>
      <span><i class="sw Pending"></i>Pending</span>${showFree ? '<span><i class="sw free"></i>Free</span>' : ''}
      ${me.role === 'Student' && showFree ? '<span><i class="sw busy"></i>Booked by others</span>' : ''}
    </div>
    <div class="scroll"><table class="cal"><thead><tr><th>Time</th>
      ${cal.days.map(d => `<th class="${d.is_today ? 'today' : ''}">${d.day}<small>${fmt(d.date)}${d.is_today ? ' · Today' : ''}</small></th>`).join('')}
    </tr></thead><tbody>
      ${cal.slots.map(t => `<tr><th>${t}</th>${cal.days.map(d => cell(d, t)).join('')}</tr>`).join('')}
    </tbody></table></div>
  </div>`;
}

async function studentView() {
  const facs = list(await api('/api/faculty'));
  if (!ui.fac && facs.length) ui.fac = String(facs[0].user_id);
  const mineP = api('/api/appointments' + qs({ student_id: me.user_id }));
  const [av, mine] = await Promise.all([api('/api/availability' + qs({ faculty_id: ui.fac })), mineP]);
  const free = (av.slots || {})[ui.day] || [];
  const appts = list(mine);
  const curFac = facs.find(f => String(f.user_id) === ui.fac);

  let rsSlots = [];
  const rsAppt = appts.find(a => a.appointment_id === ui.rsId);
  if (rsAppt) rsSlots = ((await api('/api/availability' + qs({ faculty_id: rsAppt.faculty_id }))).slots || {})[ui.rsDay] || [];

  const rsForm = a => ui.rsId !== a.appointment_id ? '' : `
    <div class="subform">
      <p class="small"><b>Move “${a.day} ${a.time_slot}” to another time.</b> Faculty approval is needed before it changes.</p>
      <div class="grid2">
        <div><label for="rsDaySel">New day</label>
          <select id="rsDaySel" data-change="rsDay">${DAYS.map(d => `<option ${d === ui.rsDay ? 'selected' : ''}>${d}</option>`).join('')}</select></div>
        <div><label for="rsReason">Reason (optional)</label>
          <input id="rsReason" type="text" value="${esc(ui.rsReason)}" placeholder="e.g. clash with lab session"></div>
      </div>
      <div class="slots">${rsSlots.map(t => `<button class="slot" data-act="rspick" data-t="${t}" aria-pressed="${ui.rsPick === t}">${t}</button>`).join('') || '<p class="muted">No free slots on this day.</p>'}</div>
      <div class="actions" style="margin-top:12px">
        <button class="btn small" data-act="rssend" data-id="${a.appointment_id}" ${ui.rsPick ? '' : 'disabled'}>${ui.rsPick ? `Request ${ui.rsDay} ${ui.rsPick}` : 'Select a new slot'}</button>
        <button class="btn ghost small" data-act="rsclose">Close</button></div>
    </div>`;

  return `
  <div class="card">
    <h2>Book a meeting with faculty</h2>
    <p class="muted small">Only times when the faculty has no class and no other meeting are shown. The faculty will confirm the meeting venue.</p>
    <div class="grid2">
      <div><label for="fSel">Faculty</label>
        <select id="fSel" data-change="fac">${facs.map(f => `<option value="${f.user_id}" ${String(f.user_id) === ui.fac ? 'selected' : ''}>${esc(f.name)}</option>`).join('')}</select></div>
      <div><label for="dSel">Day</label>
        <select id="dSel" data-change="day">${DAYS.map(d => `<option ${d === ui.day ? 'selected' : ''}>${d}</option>`).join('')}</select></div>
    </div>
    ${curFac && curFac.office ? `<p class="small" style="margin:10px 0 0">🏢 <b>${esc(curFac.name)}’s office:</b> ${esc(curFac.office)}</p>` : ''}
    <div class="slots">${free.map(t => `<button class="slot" data-act="pick" data-t="${t}" aria-pressed="${ui.pick === t}">${t}</button>`).join('') || '<p class="muted">No free slots on this day. Try another day.</p>'}</div>
    <label for="topic">Project / topic to discuss</label>
    <textarea id="topic" placeholder="e.g. Review of my ER diagram">${esc(ui.topic)}</textarea>
    <button class="btn" data-act="book" ${ui.pick ? '' : 'disabled'}>${ui.pick ? `Request ${ui.day} ${ui.pick}` : 'Select a slot'}</button>
  </div>
  <div class="card"><h2>My bookings</h2>
    ${appts.map(a => `<div class="row"><div><strong>${esc(a.faculty)}</strong> · ${a.day} ${a.time_slot}
      ${a.venue ? `<span class="venue">📍 ${esc(a.venue)}</span>` : ''}
      ${a.faculty_office ? `<div class="muted small">🏢 Office: ${esc(a.faculty_office)}</div>` : ''}
      <div class="muted small">${esc(a.topic)}</div>
      ${a.req_id ? `<div class="req small">🔁 Reschedule requested → <b>${a.req_day} ${a.req_time}</b>${a.req_reason ? ' · ' + esc(a.req_reason) : ''} — waiting for faculty</div>` : ''}</div>
      <div class="actions"><span class="tag ${a.status}">${a.status}</span>
      ${a.req_id ? `<button class="btn ghost small" data-act="rswithdraw" data-id="${a.req_id}">Withdraw request</button>`
        : ACTIVE.includes(a.status) ? `<button class="btn ghost small" data-act="rsform" data-id="${a.appointment_id}">Reschedule</button>` : ''}
      ${ACTIVE.includes(a.status) ? `<button class="btn ghost small" data-act="cancel" data-id="${a.appointment_id}">Cancel</button>` : ''}</div>
      ${rsForm(a)}</div>`).join('')
      || '<p class="muted">You have no bookings yet.</p>'}
  </div>`;
}

async function facultyView() {
  const [appts, tt, av, facs] = await Promise.all([
    api('/api/appointments' + qs({ faculty_id: me.user_id })),
    api('/api/timetable'),
    api('/api/availability' + qs({ faculty_id: me.user_id })),
    api('/api/faculty')
  ]);
  const myOffice = (list(facs).find(f => f.user_id === me.user_id) || {}).office || '';
  const mine = list(appts), myTT = list(tt).filter(t => t.faculty_id === me.user_id);
  const pending = mine.filter(a => a.status === 'Pending');
  const others = mine.filter(a => a.status !== 'Pending');
  const moves = mine.filter(a => a.req_id);
  // Faculty types where to meet (or taps "My office"); the student sees it on their booking.
  const venueBox = a => `<div class="actions" style="width:100%">
      <input id="venue-${a.appointment_id}" type="text" maxlength="100" aria-label="Meeting place"
        value="${esc(ui.venueDraft[a.appointment_id] ?? a.venue ?? '')}"
        placeholder="${a.status === 'Pending' ? 'Where to meet? (required to accept) e.g. my office, Room 204' : 'Where to meet? e.g. my office, Room 204'}"
        style="flex:1;min-width:220px">
      ${myOffice ? `<button class="btn ghost small" data-act="myOffice" data-id="${a.appointment_id}" data-office="${esc(myOffice)}">🏢 My office</button>` : ''}
      ${a.status === 'Pending' ? '' : `<button class="btn small" data-act="setVenue" data-id="${a.appointment_id}">Save place</button>`}
    </div>`;
  const options = DAYS.flatMap(d => ((av.slots || {})[d] || []).map(t => `<option value="${d}|${t}">${d} ${t}</option>`)).join('');

  const row = a => `<div class="row"><div><strong>${esc(a.student)}</strong> · ${a.day} ${a.time_slot}
      ${a.venue ? `<span class="venue">📍 ${esc(a.venue)}</span>` : ''}
      <div class="muted small">${esc(a.topic)}</div></div>
      <div class="actions">${a.status === 'Pending' ? `
        <button class="btn ok small" data-act="accept" data-id="${a.appointment_id}">Accept</button>
        <button class="btn bad small" data-act="reject" data-id="${a.appointment_id}">Reject</button>
        <button class="btn ghost small" data-act="resform" data-id="${a.appointment_id}">Reschedule</button>`
      : `<span class="tag ${a.status}">${a.status}</span>
         ${ACTIVE.includes(a.status) ? `<button class="btn ghost small" data-act="resform" data-id="${a.appointment_id}">Reschedule</button>` : ''}`}</div>
      ${ACTIVE.includes(a.status) ? venueBox(a) : ''}
      ${ui.resId === a.appointment_id ? `<div class="actions" style="width:100%">
        <select id="resSel" aria-label="New time">${options || '<option value="">No free slots</option>'}</select>
        <button class="btn small" data-act="resok" data-id="${a.appointment_id}">Confirm new time</button></div>` : ''}</div>`;

  return `
  <div class="card"><h2>Reschedule requests (${moves.length})</h2>
    <p class="muted small">Students asking to move a booking. Approving moves it right away and notifies them.</p>
    ${moves.map(a => `<div class="row"><div><strong>${esc(a.student)}</strong>
      <div class="small">${a.day} ${a.time_slot} <span class="arrow">→</span> <b>${a.req_day} ${a.req_time}</b></div>
      <div class="muted small">${a.req_reason ? 'Reason: ' + esc(a.req_reason) : esc(a.topic)}</div></div>
      <div class="actions"><button class="btn ok small" data-act="rqok" data-id="${a.req_id}">Approve</button>
      <button class="btn bad small" data-act="rqno" data-id="${a.req_id}">Decline</button></div></div>`).join('')
      || '<p class="muted">No reschedule requests.</p>'}</div>
  <div class="card"><h2>Booking requests (${pending.length})</h2>
    ${pending.map(row).join('') || '<p class="muted">No pending requests.</p>'}</div>
  <div class="card"><h2>My availability this week</h2>
    <p class="muted small">Classes come from the timetable set by the admin. Everything else is open for student bookings.</p>
    <div class="scroll"><table><thead><tr><th>Time</th>${DAYS.map(d => `<th>${d}</th>`).join('')}</tr></thead><tbody>
    ${SLOTS.map(t => `<tr><th>${t}</th>${DAYS.map(d => {
      const c = myTT.find(x => x.day === d && x.time_slot === t);
      if (c) return `<td class="class">${esc(c.subject)}<br>${esc(c.room)}</td>`;
      const b = mine.find(x => x.day === d && x.time_slot === t && ACTIVE.includes(x.status));
      return b ? `<td class="booked">${esc(b.student)}<br>${b.status}${b.venue ? '<br>📍 ' + esc(b.venue) : ''}</td>` : '<td class="free">Free</td>';
    }).join('')}</tr>`).join('')}</tbody></table></div></div>
  <div class="card"><h2>All requests</h2>${others.map(row).join('') || '<p class="muted">Nothing here yet.</p>'}</div>`;
}

async function adminView() {
  const facs = list(await api('/api/faculty'));
  if (!facs.some(f => String(f.user_id) === String(ui.admFac))) ui.admFac = facs.length ? String(facs[0].user_id) : '';
  const fac = facs.find(f => String(f.user_id) === String(ui.admFac));
  const tt = fac ? list(await api('/api/timetable' + qs({ faculty_id: fac.user_id }))) : [];
  return `
  <div class="card"><h2>Add user</h2>
    <p class="muted small">Create a faculty or student account. For faculty, add the office where students can find them.</p>
    <div class="grid2">
      <div><label for="uName">Name</label><input id="uName" type="text"></div>
      <div><label for="uEmail">Email</label><input id="uEmail" type="email"></div>
      <div><label for="uPass">Password</label><input id="uPass" type="text"></div>
      <div><label for="uRole">Role</label><select id="uRole"><option>Faculty</option><option>Student</option></select></div>
    </div>
    <div id="uOfficeWrap"><label for="uOffice">Office (shown to students)</label>
      <input id="uOffice" type="text" placeholder="e.g. Staff block, Room 12"></div>
    <button class="btn" data-act="addUser">Add user</button>
  </div>
  <div class="card"><h2>Faculty timetable</h2>
    ${fac ? `
    <p class="muted small">Pick a faculty member to see their timetable, set their office and add or remove classes.</p>
    <label for="admFacSel">Faculty</label>
    <select id="admFacSel" data-change="admFac">${facs.map(f => `<option value="${f.user_id}" ${String(f.user_id) === String(ui.admFac) ? 'selected' : ''}>${esc(f.name)}</option>`).join('')}</select>
    <label for="fOffice">Office</label>
    <div class="actions"><input id="fOffice" type="text" value="${esc(fac.office)}" placeholder="e.g. Staff block, Room 12" style="flex:1;min-width:200px">
      <button class="btn small" data-act="saveOffice">Save office</button></div>
    <div class="scroll" style="margin-top:16px"><table><thead><tr><th>Time</th>${DAYS.map(d => `<th>${d}</th>`).join('')}</tr></thead><tbody>
    ${SLOTS.map(t => `<tr><th>${t}</th>${DAYS.map(d => {
      const c = tt.find(x => x.day === d && x.time_slot === t);
      return c ? `<td class="class">${esc(c.subject)}<br>${esc(c.room)}<br><button class="btn ghost small" style="margin-top:6px" data-act="delClass" data-id="${c.timetable_id}">Remove</button></td>` : '<td></td>';
    }).join('')}</tr>`).join('')}</tbody></table></div>
    <h3 style="margin-top:22px">Add class for ${esc(fac.name)}</h3>
    <div class="grid2">
      <div><label for="tDay">Day</label><select id="tDay">${DAYS.map(d => `<option>${d}</option>`).join('')}</select></div>
      <div><label for="tSlot">Time</label><select id="tSlot">${SLOTS.map(t => `<option>${t}</option>`).join('')}</select></div>
      <div><label for="tSub">Subject</label><input id="tSub" type="text"></div>
      <div><label for="tRoom">Room</label><input id="tRoom" type="text"></div>
    </div>
    <button class="btn" data-act="addClass">Add class</button>
    ` : '<p class="muted">No faculty yet. Add a faculty user above first.</p>'}
  </div>`;
}

const fmtSize = n => n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
const toB64 = f => new Promise((res, rej) => {
  const r = new FileReader();
  r.onload = () => res(String(r.result).split(',')[1]);
  r.onerror = () => rej(new Error('read'));
  r.readAsDataURL(f);
});

async function documentsView() {
  const canUpload = me.role === 'Faculty' || me.role === 'Admin';
  const r = await api('/api/documents' + qs({ user_id: me.user_id, ...(ui.docQ ? { q: ui.docQ } : {}) }));
  const docs = list(r.documents);
  return `
  ${canUpload ? `<div class="card"><h2>Upload a document</h2>
    <p class="muted small">Share notes, slides or assignments with students. PDF, Word, PowerPoint, Excel, text, images or zip, up to 10 MB.</p>
    <div class="grid2">
      <div><label for="docTitle">Title</label><input id="docTitle" type="text" value="${esc(ui.docTitle)}" placeholder="e.g. DBMS Unit 2 notes"></div>
      <div><label for="docSubject">Subject (optional)</label><input id="docSubject" type="text" value="${esc(ui.docSubject)}"></div>
    </div>
    <label for="docDesc">Description (optional)</label>
    <textarea id="docDesc">${esc(ui.docDesc)}</textarea>
    <label for="docFile">File</label>
    <div class="file-pick"><input id="docFile" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.zip">
      ${ui.docFile ? `<div class="small">Selected: <b>${esc(ui.docFile.name)}</b> (${fmtSize(ui.docFile.size)})</div>` : ''}</div>
    <button class="btn" data-act="upload">Upload</button></div>` : ''}
  <div class="card"><div class="row head"><div><h2>Shared documents</h2>
      <p class="muted small">${docs.length} document${docs.length === 1 ? '' : 's'}</p></div>
      <input id="docQ" class="search" type="search" placeholder="Search title, subject or faculty" value="${esc(ui.docQ)}" aria-label="Search documents"></div>
    ${docs.map(d => `<div class="row doc"><span class="doc-icon">📄</span><div><strong>${esc(d.title)}</strong>
      <div class="muted small">${esc(d.uploader)}${d.subject ? ' · ' + esc(d.subject) : ''} · ${esc(d.filename)} · ${fmtSize(d.size_bytes)} · ${ago(d.uploaded_at)}</div>
      ${d.description ? `<div class="small">${esc(d.description)}</div>` : ''}</div>
      <div class="actions"><a class="btn small" href="${API}/api/documents/download${qs({ document_id: d.document_id, user_id: me.user_id })}" download>Download</a>
      ${me.role === 'Admin' || d.uploader_id === me.user_id ? `<button class="btn ghost small" data-act="delDoc" data-id="${d.document_id}">Delete</button>` : ''}</div></div>`).join('')
      || `<p class="muted">${ui.docQ ? 'No documents match your search.' : 'No documents have been shared yet.'}</p>`}
  </div>`;
}

async function chatView() {
  if (me.role === 'Admin') return `<div class="card"><h2>Chat</h2><p class="muted">Direct chat is available to student and faculty accounts.</p></div>`;
  const cr = await api('/api/chat/contacts' + qs({ user_id: me.user_id }));
  const contacts = list(cr.contacts);
  if (!ui.chatContact && contacts.length) ui.chatContact = String(contacts[0].user_id);
  if (ui.chatContact && !contacts.some(c => String(c.user_id) === String(ui.chatContact))) ui.chatContact = contacts.length ? String(contacts[0].user_id) : '';
  const selected = contacts.find(c => String(c.user_id) === String(ui.chatContact));
  const mr = selected ? await api('/api/chat/messages' + qs({ user_id: me.user_id, other_user_id: selected.user_id })) : { success: true, messages: [] };
  const msgs = list(mr.messages);
  const fmt = ts => { const d = new Date(String(ts || '').replace(' ', 'T') + 'Z'); return Number.isNaN(d.getTime()) ? '' : d.toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}); };
  return `
    <div class="card"><h2>💬 Faculty–Student Chat</h2>
      <p class="muted small">Send messages to discuss appointments, course questions, or meeting details. Keep messages respectful and avoid sharing passwords or sensitive information.</p>
      ${contacts.length ? `
        <label for="chatContact">${me.role === 'Student' ? 'Choose faculty' : 'Choose student'}</label>
        <select id="chatContact" data-change="chatContact">${contacts.map(c => `<option value="${c.user_id}" ${String(c.user_id) === String(ui.chatContact) ? 'selected' : ''}>${esc(c.name)}${c.unread ? ` · ${c.unread} unread` : ''}</option>`).join('')}</select>
        <div class="chat-messages" aria-live="polite">${msgs.map(m => `<div class="chat-line ${Number(m.sender_id) === Number(me.user_id) ? 'mine' : 'theirs'}"><div class="chat-bubble"><p>${esc(m.message)}</p><small>${Number(m.sender_id) === Number(me.user_id) ? 'You' : esc(selected.name)} · ${esc(fmt(m.created_at))}</small></div></div>`).join('') || '<p class="muted">No messages yet. Start the conversation below.</p>'}</div>
        <div class="chat-compose"><label for="chatMessage">Message</label><textarea id="chatMessage" maxlength="2000" placeholder="Write a message…">${esc(ui.chatMessage)}</textarea><div class="actions"><span class="muted small">Up to 2000 characters</span><button class="btn" data-act="sendChat">Send message</button></div></div>
      ` : '<p class="muted">No contacts available yet. Students can message any faculty member. Faculty contacts appear after a student has an appointment or starts a conversation.</p>'}
    </div>
`;
}

async function run(promise, okMsg) {
  const res = await promise;
  toast(res.success ? (okMsg || res.message) : res.message);
  if (res.success) { ui.pick = null; ui.resId = null; ui.topic = ''; ui.rsId = null; ui.rsPick = null; ui.rsReason = ''; ui.venueDraft = {}; }
  render();
  pollNotifs(true);
}

$('content').addEventListener('input', e => {
  if (e.target.id === 'topic') ui.topic = e.target.value;
  if (e.target.id === 'rsReason') ui.rsReason = e.target.value;
  if (e.target.id === 'docTitle') ui.docTitle = e.target.value;
  if (e.target.id === 'docSubject') ui.docSubject = e.target.value;
  if (e.target.id === 'docDesc') ui.docDesc = e.target.value;
  if (e.target.id === 'chatMessage') ui.chatMessage = e.target.value;
  if (e.target.id.startsWith('venue-')) ui.venueDraft[e.target.id.slice(6)] = e.target.value;
  if (e.target.id === 'docQ') {   // search as you type, keep the caret in the box
    ui.docQ = e.target.value;
    clearTimeout(ui.docQTimer);
    ui.docQTimer = setTimeout(async () => { await render(); const q = $('docQ'); if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }, 250);
  }
});

$('content').addEventListener('change', e => {
  const c = e.target.dataset.change;
  if (c === 'fac') { ui.fac = e.target.value; ui.pick = null; render(); }
  if (c === 'day') { ui.day = e.target.value; ui.pick = null; render(); }
  if (c === 'rsDay') { ui.rsDay = e.target.value; ui.rsPick = null; render(); }
  if (c === 'calFac') { ui.calFac = e.target.value; render(); }
  if (c === 'admFac') { ui.admFac = e.target.value; render(); }
  if (e.target.id === 'uRole') $('uOfficeWrap').hidden = e.target.value !== 'Faculty';
  if (c === 'chatContact') { ui.chatContact = e.target.value; ui.chatMessage = ''; render(); }
  if (e.target.id === 'docFile') { ui.docFile = e.target.files[0] || null; render(); }
});

$('content').addEventListener('click', async e => {
  const b = e.target.closest('button[data-act]'); if (!b) return;
  const act = b.dataset.act, id = Number(b.dataset.id), v = x => $(x).value.trim();

  if (act === 'pick') { ui.pick = ui.pick === b.dataset.t ? null : b.dataset.t; render(); }
  else if (act === 'book') {
    if (!v('topic')) return toast('Add a topic for the meeting');
    run(api('/api/appointments', 'POST', { student_id: me.user_id, faculty_id: Number(ui.fac), day: ui.day, time_slot: ui.pick, topic: v('topic') }));
  }
  else if (act === 'cancel') run(api('/api/appointments/cancel', 'POST', { appointment_id: id, user_id: me.user_id }));
  else if (act === 'accept') {
    const place = ($('venue-' + id) || {}).value || '';
    if (!place.trim()) return toast('Enter where the meeting will take place');
    run(api('/api/appointments/respond', 'POST', { faculty_id: me.user_id, appointment_id: id, action: 'Accepted', venue: place.trim() }));
  }
  else if (act === 'reject') run(api('/api/appointments/respond', 'POST', { faculty_id: me.user_id, appointment_id: id, action: 'Rejected' }));
  else if (act === 'resform') { ui.resId = ui.resId === id ? null : id; render(); }
  else if (act === 'resok') {
    const [day, time_slot] = ($('resSel').value || '|').split('|');
    if (!day) return toast('No free slots to move to');
    run(api('/api/appointments/reschedule', 'POST', { faculty_id: me.user_id, appointment_id: id, day, time_slot }));
  }

  else if (act === 'rsform') { ui.rsId = ui.rsId === id ? null : id; ui.rsPick = null; ui.rsReason = ''; render(); }
  else if (act === 'rsclose') { ui.rsId = null; ui.rsPick = null; ui.rsReason = ''; render(); }
  else if (act === 'rspick') { ui.rsPick = ui.rsPick === b.dataset.t ? null : b.dataset.t; render(); }
  else if (act === 'rssend') {
    run(api('/api/appointments/reschedule-request', 'POST', { student_id: me.user_id, appointment_id: id, day: ui.rsDay, time_slot: ui.rsPick, reason: ui.rsReason }));
  }
  else if (act === 'rswithdraw') run(api('/api/appointments/reschedule-withdraw', 'POST', { student_id: me.user_id, request_id: id }));
  else if (act === 'rqok') run(api('/api/appointments/reschedule-respond', 'POST', { faculty_id: me.user_id, request_id: id, action: 'Approved' }));
  else if (act === 'rqno') run(api('/api/appointments/reschedule-respond', 'POST', { faculty_id: me.user_id, request_id: id, action: 'Declined' }));

  else if (act === 'calbook') {
    ui.fac = String(ui.calFac); ui.day = b.dataset.d; ui.pick = b.dataset.t; ui.view = 'dashboard'; render();
  }

  else if (act === 'readOne') { await api('/api/notifications/read', 'POST', { user_id: me.user_id, notification_id: id }); render(); }
  else if (act === 'readAll') { await api('/api/notifications/read', 'POST', { user_id: me.user_id }); render(); }

  else if (act === 'sendChat') {
    if (!ui.chatContact) return toast('Choose a contact first');
    if (!ui.chatMessage.trim()) return toast('Write a message first');
    const res = await api('/api/chat/send', 'POST', { user_id: me.user_id, recipient_id: Number(ui.chatContact), message: ui.chatMessage.trim() });
    toast(res.message);
    if (res.success) ui.chatMessage = '';
    render(); pollNotifs(true);
  }
  else if (act === 'setVenue') {
    const place = ($('venue-' + id) || {}).value || '';
    if (!place.trim()) return toast('Enter where the meeting will take place');
    run(api('/api/appointments/venue', 'POST', { faculty_id: me.user_id, appointment_id: id, venue: place.trim() }));
  }
  else if (act === 'myOffice') {
    const inp = $('venue-' + id);
    if (inp) { inp.value = b.dataset.office; ui.venueDraft[id] = inp.value; inp.focus(); }
  }
  else if (act === 'saveOffice') {
    run(api('/api/admin/faculty-office', 'POST', { admin_id: me.user_id, faculty_id: Number(ui.admFac), office: v('fOffice') }));
  }
  else if (act === 'addClass') {
    run(api('/api/timetable', 'POST', { admin_id: me.user_id, faculty_id: Number(ui.admFac), day: $('tDay').value, time_slot: $('tSlot').value, subject: v('tSub'), room: v('tRoom') }));
  }
  else if (act === 'delClass') run(api('/api/timetable', 'DELETE', { admin_id: me.user_id, timetable_id: id }));
  else if (act === 'addUser') {
    run(api('/api/admin/users', 'POST', { admin_id: me.user_id, name: v('uName'), email: v('uEmail'), password: $('uPass').value, role: $('uRole').value, office: $('uOffice') ? v('uOffice') : '' }));
  }
  else if (act === 'upload') {
    if (!ui.docTitle.trim()) return toast('Give the document a title');
    if (!ui.docFile) return toast('Choose a file to upload');
    if (ui.docFile.size > 10 * 1024 * 1024) return toast('File is larger than 10 MB');
    b.disabled = true; toast('Uploading…');
    let data; try { data = await toB64(ui.docFile); } catch { b.disabled = false; return toast('Could not read that file'); }
    const res = await api('/api/documents', 'POST', { user_id: me.user_id, title: ui.docTitle, subject: ui.docSubject,
      description: ui.docDesc, filename: ui.docFile.name, data });
    toast(res.message);
    if (res.success) { ui.docTitle = ui.docSubject = ui.docDesc = ''; ui.docFile = null; }
    render(); pollNotifs(true);
  }
  else if (act === 'delDoc') {
    if (confirm('Delete this document?')) run(api('/api/documents', 'DELETE', { user_id: me.user_id, document_id: id }));
  }
});

if (me) start();
