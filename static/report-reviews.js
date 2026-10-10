(() => {
  const $ = (id) => document.getElementById(id);
  const statuses = { review: 'На проверке', changes: 'Нужны исправления', approved: 'Одобрен', published: 'Опубликован' };
  let reviews = [], publishedReviews = [], tab = 'pending', selected = null, mounted = null, version = null, generation = 0, epoch = 0, busy = false;
  let sectionOrder = [], collapsed = new Set(), preferencesLoaded = false, preferencesDirty = false, savingOrder = false, draggedSection = null;
  let companies = [];
  let fitTimer = null, fitObserver = null;
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#${name}"></use></svg>`;

  function close() {
    generation++;
    clearTimeout(fitTimer);
    fitObserver?.disconnect();
    fitObserver = null;
    mounted?.unmount();
    mounted = null;
    version = null;
    $('reviewEmbed').replaceChildren();
  }

  function reset() {
    epoch++; close(); selected = null; reviews = []; publishedReviews = []; tab = 'pending'; busy = false;
    sectionOrder = []; collapsed = new Set(); preferencesLoaded = false; preferencesDirty = false; savingOrder = false; draggedSection = null;
    companies = []; $('reviewCompanySearch').value = ''; $('reviewCompanySearchStatus').textContent = '';
    $('saveReviewOrder').hidden = true;
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
    $('reviewActions').hidden = !selected || published;
    $('reviewDetails').hidden = !selected;
    $('reviewCandidateLabel').hidden = tab === 'published';
    $('registerReview').hidden = tab === 'published';
    $('saveReviewOrder').hidden = tab !== 'published' || !publishedReviews.length;
    $('saveReviewOrder').disabled = busy || savingOrder || !preferencesDirty;
    for (const button of $('reviewTabs').querySelectorAll('[role="tab"]')) {
      const active = button.dataset.reviewTab === tab;
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
      button.disabled = busy;
    }
    $('reviewList').setAttribute('aria-labelledby', tab === 'published' ? 'reviewPublishedTab' : 'reviewPendingTab');
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
        dashboardUiConfig: { hideTitle: true, hideChartControls: true, filters: { visible:true, expanded:false } },
        referrerPolicy: 'strict-origin-when-cross-origin',
      });
      if (run !== generation) { instance.unmount(); return; }
      mounted = instance;
      fitPreview(instance, run);
    } catch (error) { if (run === generation) $('reviewError').textContent = error.message; }
    controls();
  }

  function fitPreview(instance, run) {
    const host = $('reviewEmbed');
    const frame = host.querySelector('iframe');
    let scale = 1;
    const resize = () => {
      frame.style.width = `${100 / scale}%`;
      frame.style.height = `${100 / scale}%`;
      frame.style.transform = `scale(${scale})`;
    };
    // Size the cross-origin document through the SDK, without clipping its totals.
    const fit = async () => {
      if (run !== generation) return;
      try {
        const size = await instance.getScrollSize();
        if (run !== generation) return;
        const height = Number(size.height);
        if (host.clientHeight > 0 && height * scale > host.clientHeight + 2) {
          scale = Math.min(scale, host.clientHeight / (height + 2));
          resize();
        }
      } catch (_) { /* The iframe can be reloading or closing. */ }
      if (run === generation) fitTimer = setTimeout(fit, 1000);
    };
    fitObserver = new ResizeObserver(() => { scale = 1; resize(); });
    fitObserver.observe(host);
    fit();
  }

  function visibleReviews() {
    const publishedIds = new Set(publishedReviews.map((r) => r.dashboard_id));
    return tab === 'published' ? publishedReviews : reviews.filter((r) => r.status !== 'published' && !publishedIds.has(r.dashboard_id));
  }

  function sections() {
    const groups = new Map();
    for (const report of publishedReviews) {
      for (const tag of report.tags || []) {
        const id = Number(tag.id);
        if (!groups.has(id)) groups.set(id, { id, name: tag.name, reports: [] });
        groups.get(id).reports.push(report);
      }
    }
    const missing = [...groups.keys()].filter((id) => !sectionOrder.includes(id))
      .sort((a, b) => groups.get(a).name.localeCompare(groups.get(b).name, 'ru') || a - b);
    return [...sectionOrder.filter((id) => groups.has(id)), ...missing].map((id) => groups.get(id));
  }

  function reportButton(report) {
    return `<button type="button" class="review-item ${report.dashboard_id === selected?.dashboard_id ? 'selected' : ''}" data-id="${report.dashboard_id}"><strong>${escape(report.title)}</strong><span>${escape(statuses[report.status])}${report.tags?.length ? ' · ' + escape(report.tags.map((t) => t.name).join(', ')) : ''}</span></button>`;
  }

  function groupedReports() {
    const groups = sections();
    return groups.map((group, index) => {
      const open = !collapsed.has(group.id);
      const name = escape(group.name);
      return `<section class="review-group" data-section="${group.id}">
        <div class="review-group-header">
          <button class="review-group-toggle" type="button" data-toggle-section="${group.id}" aria-expanded="${open}" aria-controls="reviewSection${group.id}">
            ${icon('chevron-right')}<span class="review-group-name">${name}</span><span class="review-group-count">${group.reports.length}</span>
          </button>
          <div class="review-group-tools">
            <button type="button" class="icon-button review-group-up" data-move-section="${group.id}" data-direction="-1" title="Выше: ${name}" aria-label="Выше: ${name}" ${index === 0 ? 'disabled' : ''}>${icon('chevron-left')}</button>
            <button type="button" class="icon-button review-group-down" data-move-section="${group.id}" data-direction="1" title="Ниже: ${name}" aria-label="Ниже: ${name}" ${index === groups.length - 1 ? 'disabled' : ''}>${icon('chevron-right')}</button>
            <button type="button" class="icon-button review-group-drag" draggable="true" data-drag-section="${group.id}" title="Перетащить раздел: ${name}" aria-label="Перетащить раздел: ${name}">${icon('menu')}</button>
          </div>
        </div>
        <div id="reviewSection${group.id}" ${open ? '' : 'hidden'}>${group.reports.map(reportButton).join('')}</div>
      </section>`;
    }).join('');
  }

  function moveSection(id, target) {
    const order = sections().map((group) => group.id);
    const from = order.indexOf(id);
    if (from < 0 || target < 0 || target >= order.length || from === target) return;
    order.splice(from, 1);
    order.splice(target, 0, id);
    sectionOrder = order;
    preferencesDirty = true;
    render();
  }

  function render() {
    const visible = visibleReviews();
    if (selected) {
      selected = visible.find((r) => r.dashboard_id === selected.dashboard_id) || null;
      if (!selected) { close(); $('reviewEvents').replaceChildren(); }
    }
    const empty = tab === 'published' ? 'Нет опубликованных отчётов' : 'Нет отчётов на проверке';
    const scroll = $('reviewList').scrollTop;
    $('reviewList').innerHTML = visible.length ? (tab === 'published' ? groupedReports() : visible.map(reportButton).join('')) : `<p>${empty}</p>`;
    $('reviewList').scrollTop = scroll;
    $('reviewTitle').textContent = selected?.title || 'Выберите отчёт';
    $('reviewStatus').textContent = selected ? statuses[selected.status] : '';
    controls();
  }

  async function list() {
    const run = epoch;
    const result = await api('/api/report-reviews');
    const published = await api('/api/report-reviews/published');
    if (run !== epoch) return;
    reviews = result.reviews;
    publishedReviews = published.reviews;
    render();
  }

  async function load() {
    const run = epoch;
    $('reviewError').textContent = '';
    try {
      if (!preferencesLoaded) {
        const preferences = await api('/api/report-reviews/preferences');
        if (run !== epoch) return;
        sectionOrder = preferences.order;
        collapsed = new Set(preferences.collapsed);
        preferencesLoaded = true;
      }
      const options = await api('/api/report-reviews/options');
      if (run !== epoch) return;
      const company = $('reviewCompany').value;
      companies = options.companies;
      const current = companies.some((c) => String(c.id) === company) ? company : companies.some((c) => c.id === 290) ? '290' : '';
      renderCompanies(current);
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
    const toggle = event.target.closest('[data-toggle-section]');
    if (toggle) {
      const id = Number(toggle.dataset.toggleSection);
      if (collapsed.has(id)) collapsed.delete(id); else collapsed.add(id);
      preferencesDirty = true; render();
      $('reviewList').querySelector(`[data-toggle-section="${id}"]`)?.focus({preventScroll:true});
      return;
    }
    const move = event.target.closest('[data-move-section]');
    if (move) {
      const id = Number(move.dataset.moveSection);
      moveSection(id, sections().findIndex((group) => group.id === id) + Number(move.dataset.direction));
      $('reviewList').querySelector(`[data-toggle-section="${id}"]`)?.focus({preventScroll:true});
      return;
    }
    const button = event.target.closest('[data-id]');
    if (!button || busy) return;
    selected = visibleReviews().find((r) => r.dashboard_id === Number(button.dataset.id));
    $('reviewNote').value = '';
    render(); await events(); await preview();
  });
  $('reviewList').addEventListener('dragstart', (event) => {
    const handle = event.target.closest('[data-drag-section]');
    if (!handle) return;
    draggedSection = Number(handle.dataset.dragSection);
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(draggedSection));
  });
  function clearDropTargets() {
    $('reviewList').querySelectorAll('.drop-target').forEach((element) => element.classList.remove('drop-target'));
  }
  $('reviewList').addEventListener('dragover', (event) => {
    const group = event.target.closest('[data-section]');
    if (!group || draggedSection === null) return;
    event.preventDefault(); event.dataTransfer.dropEffect = 'move';
    clearDropTargets(); group.classList.add('drop-target');
  });
  $('reviewList').addEventListener('drop', (event) => {
    const group = event.target.closest('[data-section]');
    if (!group || draggedSection === null) return;
    event.preventDefault();
    moveSection(draggedSection, sections().findIndex((item) => item.id === Number(group.dataset.section)));
    draggedSection = null; clearDropTargets();
  });
  $('reviewList').addEventListener('dragend', () => { draggedSection = null; clearDropTargets(); });
  $('saveReviewOrder').addEventListener('click', async () => {
    if (savingOrder || !preferencesDirty) return;
    const run = epoch;
    const order = sections().map((group) => group.id);
    const payload = {order, collapsed:order.filter((id) => collapsed.has(id))};
    savingOrder = true; controls(); $('reviewError').textContent = '';
    try {
      await api('/api/report-reviews/preferences', {method:'PUT', body:JSON.stringify(payload)});
      if (run !== epoch) return;
      const current = sections().map((group) => group.id);
      preferencesDirty = JSON.stringify(payload) !== JSON.stringify({order:current, collapsed:current.filter((id) => collapsed.has(id))});
    } catch (error) { if (run === epoch) $('reviewError').textContent = error.message; }
    finally { if (run === epoch) { savingOrder = false; controls(); } }
  });
  function switchTab(next) {
    if (busy || next === tab) return;
    close(); selected = null; tab = next;
    $('reviewNote').value = '';
    $('reviewError').textContent = '';
    $('reviewEvents').replaceChildren();
    render();
  }
  $('reviewTabs').addEventListener('click', (event) => {
    const button = event.target.closest('[data-review-tab]');
    if (button) switchTab(button.dataset.reviewTab);
  });
  $('reviewTabs').addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || busy) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 'pending' : event.key === 'End' ? 'published' : tab === 'pending' ? 'published' : 'pending';
    switchTab(next);
    $(next === 'pending' ? 'reviewPendingTab' : 'reviewPublishedTab').focus();
  });
  function renderCompanies(current = $('reviewCompany').value) {
    const normalize = (value) => String(value).normalize('NFKC').toLocaleLowerCase().trim();
    const terms = normalize($('reviewCompanySearch').value).split(/\s+/).filter(Boolean);
    const matches = companies.filter((company) => {
      const text = normalize(`${company.name} (#${company.id})`);
      return terms.every((term) => text.includes(term));
    });
    const selectedCompany = companies.find((company) => String(company.id) === current);
    const option = (company, hidden = false) => `<option value="${company.id}" ${hidden ? 'hidden' : ''}>${escape(company.name)} (#${company.id})</option>`;
    // Keep the committed company even when it is outside the search results.
    const pinned = selectedCompany && !matches.includes(selectedCompany) ? option(selectedCompany, true) : '';
    $('reviewCompany').innerHTML = '<option value="">Выберите компанию</option>' + matches.map((company) => option(company)).join('') + pinned + (!matches.length ? '<option disabled>Компании не найдены</option>' : '');
    $('reviewCompany').value = selectedCompany ? current : '';
    $('reviewCompanySearchStatus').textContent = terms.length ? (matches.length ? `Найдено: ${matches.length}` : 'Компании не найдены') : '';
  }
  $('reviewCompanySearch').addEventListener('input', () => renderCompanies());
  $('reviewCompany').addEventListener('change', async () => {
    $('reviewCompanySearch').value = '';
    renderCompanies();
    await preview();
  });
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
      tab = 'pending';
      await load();
    } catch (error) { $('reviewError').textContent = error.message; }
    finally { busy = false; controls(); }
  });
  for (const [id, action] of [['reviewTested','tested'],['reviewApprove','approve'],['reviewChanges','changes'],['reviewPublish','publish'],['reviewComment','comment']]) $(id).addEventListener('click', () => act(action));
  window.reportReviews = { load, close, reset };
})();
