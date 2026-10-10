(() => {
  const $ = (id) => document.getElementById(id);
  const statuses = { review: 'На проверке', changes: 'Нужны исправления', approved: 'Одобрен', published: 'Опубликован' };
  let reviews = [], selected = null, mounted = null, version = null, generation = 0, epoch = 0, busy = false;
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function close() {
    generation++;
    mounted?.unmount();
    mounted = null;
    version = null;
    $('reviewEmbed').replaceChildren();
  }

  function reset() {
    epoch++; close(); selected = null; reviews = []; busy = false;
    for (const id of ['reviewCompany','reviewCandidate','reviewTag','reviewList','reviewEvents']) $(id).replaceChildren();
    $('reviewNote').value = '';
    $('reviewError').textContent = '';
    $('reviewsPage').hidden = true;
    if ($('reviewsNav').classList.contains('active')) {
      document.querySelectorAll('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.page === 'users'));
      $('usersPage').hidden = false;
      $('pageTitle').textContent = 'Foydalanuvchilar';
      $('addUserButton').hidden = false;
    }
  }

  function controls() {
    const published = selected?.status === 'published';
    $('reviewActions').hidden = !selected;
    for (const id of ['reviewTested', 'reviewApprove', 'reviewChanges', 'reviewComment', 'reviewTag']) {
      $(id).disabled = busy || published;
    }
    $('reviewTested').disabled ||= !version;
    $('reviewApprove').disabled ||= !version || selected?.tested_hash !== version;
    $('reviewPublish').disabled = busy || !version || selected?.status !== 'approved' || selected?.approved_hash !== version;
    $('registerReview').disabled = busy || !$('reviewCandidate').value;
  }

  async function act(action) {
    if (!selected || busy) return;
    const run = epoch;
    if (action === 'publish' && !confirm(`Опубликовать «${selected.title}» в выбранном разделе для клиентов?`)) return;
    busy = true; controls(); $('reviewError').textContent = '';
    try {
      const payload = await api(`/api/report-reviews/${selected.dashboard_id}/action`, { method: 'POST', body: JSON.stringify({
        action, note: $('reviewNote').value, company_id: $('reviewCompany').value,
        version, tag_id: $('reviewTag').value,
      }) });
      if (run !== epoch) return;
      selected = payload.review;
      $('reviewNote').value = '';
      await list(); await events();
    } catch (error) { $('reviewError').textContent = error.message; }
    finally { busy = false; controls(); }
  }

  async function events() {
    if (!selected) return;
    const run = epoch;
    const did = selected.dashboard_id;
    const result = await api(`/api/report-reviews/${did}/events`);
    if (run !== epoch || selected?.dashboard_id !== did) return;
    $('reviewEvents').innerHTML = result.events.map((e) => `<div><strong>${escape(e.actor)}</strong> · ${escape(e.action)} · ${escape(formatDate(e.created_at))}<p>${escape(e.note)}</p></div>`).join('');
  }

  async function preview() {
    close(); controls(); $('reviewError').textContent = '';
    if (!selected || !$('reviewCompany').value) return;
    const run = generation, did = selected.dashboard_id, cid = $('reviewCompany').value;
    try {
      const getToken = async () => {
        if (run !== generation) throw new Error('Preview closed');
        const result = await api(`/api/report-reviews/${did}/preview`, { method: 'POST', body: JSON.stringify({company_id:cid}) });
        if (run !== generation) throw new Error('Preview closed');
        return result;
      };
      const initial = await getToken();
      version = initial.version;
      const instance = await supersetEmbeddedSdk.embedDashboard({
        id: initial.uuid, supersetDomain: initial.superset_url, mountPoint: $('reviewEmbed'),
        fetchGuestToken: async () => {
          const fresh = await getToken();
          if (fresh.version !== version) { version = null; controls(); }
          return fresh.token;
        },
        dashboardUiConfig: { hideTitle: true, hideChartControls: true, filters: { visible:true, expanded:true } },
        referrerPolicy: 'strict-origin-when-cross-origin',
      });
      if (run !== generation) { instance.unmount(); return; }
      mounted = instance;
    } catch (error) { if (run === generation) $('reviewError').textContent = error.message; }
    controls();
  }

  async function list() {
    const run = epoch;
    const result = await api('/api/report-reviews');
    if (run !== epoch) return;
    reviews = result.reviews;
    if (selected) selected = reviews.find((r) => r.dashboard_id === selected.dashboard_id) || null;
    $('reviewList').innerHTML = reviews.length ? reviews.map((r) => `<button type="button" class="review-item ${r.dashboard_id === selected?.dashboard_id ? 'selected' : ''}" data-id="${r.dashboard_id}"><strong>${escape(r.title)}</strong><span>${escape(statuses[r.status])}</span></button>`).join('') : '<p>Нет отчётов на проверке</p>';
    $('reviewTitle').textContent = selected?.title || 'Выберите отчёт';
    $('reviewStatus').textContent = selected ? statuses[selected.status] : '';
    controls();
  }

  async function load() {
    const run = epoch;
    $('reviewError').textContent = '';
    try {
      const options = await api('/api/report-reviews/options');
      if (run !== epoch) return;
      const company = $('reviewCompany').value;
      $('reviewCompany').innerHTML = '<option value="">Выберите компанию</option>' + options.companies.map((c) => `<option value="${c.id}">${escape(c.name)} (#${c.id})</option>`).join('');
      if (options.companies.some((c) => String(c.id) === company)) $('reviewCompany').value = company;
      else if (options.companies.some((c) => c.id === 290)) $('reviewCompany').value = '290';
      await list();
      if (run !== epoch) return;
      const ids = new Set(reviews.map((r) => r.dashboard_id));
      $('reviewCandidate').innerHTML = '<option value="">Выберите dashboard</option>' + options.dashboards.filter((d) => !ids.has(d.id)).map((d) => `<option value="${d.id}">${escape(d.title)} (#${d.id})</option>`).join('');
      $('reviewTag').innerHTML = '<option value="">Выберите раздел</option>' + options.tags.map((t) => `<option value="${t.id}">${escape(t.name)}</option>`).join('');
      controls();
      if (selected) { await events(); await preview(); }
    } catch (error) { $('reviewError').textContent = error.message; }
  }

  $('reviewList').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-id]');
    if (!button || busy) return;
    selected = reviews.find((r) => r.dashboard_id === Number(button.dataset.id));
    $('reviewNote').value = '';
    await list(); await events(); await preview();
  });
  $('reviewCompany').addEventListener('change', preview);
  $('reviewCandidate').addEventListener('change', controls);
  $('refreshReviews').addEventListener('click', load);
  $('registerReview').addEventListener('click', async () => {
    if (busy || !$('reviewCandidate').value) return;
    const run = epoch;
    busy = true; controls();
    try {
      const result = await api('/api/report-reviews', { method:'POST', body:JSON.stringify({dashboard_id:$('reviewCandidate').value}) });
      if (run !== epoch) return;
      selected = result.review;
      await load();
    } catch (error) { $('reviewError').textContent = error.message; }
    finally { busy = false; controls(); }
  });
  for (const [id, action] of [['reviewTested','tested'],['reviewApprove','approve'],['reviewChanges','changes'],['reviewPublish','publish'],['reviewComment','comment']]) $(id).addEventListener('click', () => act(action));
  window.reportReviews = { load, close, reset };
})();
