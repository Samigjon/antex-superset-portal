const state = {
  csrfToken: "",
  currentUser: null,
  users: [],
  datasets: [],
  databases: [],
  deleteTarget: null,
  datasetDetails: new Map(),
  datasetDeleteTarget: null,
  datasetFolder: "all",
  datasetMoveTarget: null,
  metabaseQueries: [],
  metabaseCollections: [],
  metabaseDetails: new Map(),
  metabaseDeleteTarget: null,
  metabaseCollectionAction: null,
};

const elements = {
  loginView: document.querySelector("#loginView"),
  loginForm: document.querySelector("#loginForm"),
  loginError: document.querySelector("#loginError"),
  appView: document.querySelector("#appView"),
  usersTable: document.querySelector("#usersTable"),
  userCount: document.querySelector("#userCount"),
  userSearch: document.querySelector("#userSearch"),
  datasetsTable: document.querySelector("#datasetsTable"),
  datasetsTableWrap: document.querySelector("#datasetsTableWrap"),
  datasetsEmpty: document.querySelector("#datasetsEmpty"),
  datasetCount: document.querySelector("#datasetCount"),
  datasetSearch: document.querySelector("#datasetSearch"),
  datasetFolderTabs: document.querySelector("#datasetFolderTabs"),
  datasetMoveDialog: document.querySelector("#datasetMoveDialog"),
  datasetMoveForm: document.querySelector("#datasetMoveForm"),
  datasetMoveError: document.querySelector("#datasetMoveError"),
  metabasePage: document.querySelector("#metabasePage"),
  metabaseTable: document.querySelector("#metabaseTable"),
  metabaseTableWrap: document.querySelector("#metabaseTableWrap"),
  metabaseEmpty: document.querySelector("#metabaseEmpty"),
  metabaseCount: document.querySelector("#metabaseCount"),
  metabaseSearch: document.querySelector("#metabaseSearch"),
  metabaseCollectionFilter: document.querySelector("#metabaseCollectionFilter"),
  metabaseViewDialog: document.querySelector("#metabaseViewDialog"),
  metabaseEditDialog: document.querySelector("#metabaseEditDialog"),
  metabaseEditForm: document.querySelector("#metabaseEditForm"),
  metabaseEditError: document.querySelector("#metabaseEditError"),
  metabaseCollectionDialog: document.querySelector("#metabaseCollectionDialog"),
  metabaseCollectionForm: document.querySelector("#metabaseCollectionForm"),
  metabaseCollectionError: document.querySelector("#metabaseCollectionError"),
  metabaseDeleteDialog: document.querySelector("#metabaseDeleteDialog"),
  metabaseDeleteForm: document.querySelector("#metabaseDeleteForm"),
  metabaseDeleteError: document.querySelector("#metabaseDeleteError"),
  addUserButton: document.querySelector("#addUserButton"),
  addDatasetButton: document.querySelector("#addDatasetButton"),
  syncDatasetsButton: document.querySelector("#syncDatasetsButton"),
  userDialog: document.querySelector("#userDialog"),
  userForm: document.querySelector("#userForm"),
  userFormError: document.querySelector("#userFormError"),
  deleteDialog: document.querySelector("#deleteDialog"),
  deleteForm: document.querySelector("#deleteForm"),
  deleteError: document.querySelector("#deleteError"),
  datasetViewDialog: document.querySelector("#datasetViewDialog"),
  datasetCreateDialog: document.querySelector("#datasetCreateDialog"),
  datasetCreateForm: document.querySelector("#datasetCreateForm"),
  datasetCreateError: document.querySelector("#datasetCreateError"),
  datasetEditDialog: document.querySelector("#datasetEditDialog"),
  datasetEditForm: document.querySelector("#datasetEditForm"),
  datasetEditError: document.querySelector("#datasetEditError"),
  datasetDeleteDialog: document.querySelector("#datasetDeleteDialog"),
  datasetDeleteForm: document.querySelector("#datasetDeleteForm"),
  datasetDeleteError: document.querySelector("#datasetDeleteError"),
  toast: document.querySelector("#toast"),
  sidebar: document.querySelector(".sidebar"),
};

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  if (state.csrfToken && options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = state.csrfToken;
  }
  const response = await fetch(path, { credentials: "same-origin", ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") showLogin();
    throw new Error(payload.error || "So'rov bajarilmadi");
  }
  return payload;
}

function showLogin() {
  state.csrfToken = "";
  state.currentUser = null;
  elements.appView.hidden = true;
  elements.loginView.hidden = false;
}

function showApp(user) {
  state.currentUser = user;
  elements.loginView.hidden = true;
  elements.appView.hidden = false;
  document.querySelector("#currentName").textContent = user.full_name;
  document.querySelector("#currentRole").textContent = roleName(user.role);
  document.querySelector("#userAvatar").textContent = initials(user.full_name);
}

function initials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join("") || "A";
}

function roleName(role) {
  return { admin: "Administrator", editor: "Muharrir", viewer: "Kuzatuvchi" }[role] || role;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("uz-UZ", { year: "numeric", month: "short", day: "2-digit" }).format(new Date(value));
}

function formatDateTime(value) {
  return new Intl.DateTimeFormat("uz-UZ", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = String(value ?? "");
  return node.innerHTML;
}

function icon(name) {
  return `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#${name}"></use></svg>`;
}

function renderUsers() {
  const query = elements.userSearch.value.trim().toLocaleLowerCase("uz");
  const users = state.users.filter((user) => `${user.full_name} ${user.username} ${roleName(user.role)}`.toLocaleLowerCase("uz").includes(query));
  elements.userCount.textContent = `${users.length} ta foydalanuvchi`;
  elements.usersTable.innerHTML = users.map((user) => `
    <tr>
      <td><div class="user-cell"><span class="avatar">${escapeHtml(initials(user.full_name))}</span>${escapeHtml(user.full_name)}</div></td>
      <td>${escapeHtml(user.username)}</td>
      <td><span class="role-badge">${escapeHtml(roleName(user.role))}</span></td>
      <td><span class="status-badge ${user.is_active ? "active" : "inactive"}">${user.is_active ? "Faol" : "Nofaol"}</span></td>
      <td>${escapeHtml(formatDate(user.created_at))}</td>
      <td>
        <div class="row-actions">
          <button class="icon-button edit-button" type="button" data-edit="${user.id}" title="Tahrirlash" aria-label="${escapeHtml(user.full_name)}ni tahrirlash">${icon("pencil")}</button>
          <button class="icon-button delete-button" type="button" data-delete="${user.id}" title="O'chirish" aria-label="${escapeHtml(user.full_name)}ni o'chirish">${icon("trash")}</button>
        </div>
      </td>
    </tr>
  `).join("");
}

async function loadUsers() {
  const payload = await api("/api/users");
  state.users = payload.users;
  renderUsers();
}

function renderDatasets() {
  const query = elements.datasetSearch.value.trim().toLocaleLowerCase("uz");
  const datasets = state.datasets.filter((dataset) => {
    const matchesFolder = state.datasetFolder === "all"
      || (state.datasetFolder === "unassigned" && !dataset.folder_name)
      || dataset.folder_name === state.datasetFolder;
    const matchesQuery = `${dataset.table_name} ${dataset.schema_name || ""} ${dataset.database_name || ""} ${dataset.folder_name || ""} ${(dataset.tags || []).join(" ")}`
      .toLocaleLowerCase("uz")
      .includes(query);
    return matchesFolder && matchesQuery;
  });
  elements.datasetCount.textContent = `${datasets.length} ta dataset`;
  elements.datasetsEmpty.hidden = datasets.length > 0;
  elements.datasetsTableWrap.hidden = datasets.length === 0;
  elements.datasetsTable.innerHTML = datasets.map((dataset) => `
    <tr>
      <td><div class="dataset-name"><strong>${escapeHtml(dataset.table_name)}</strong></div></td>
      <td>${escapeHtml(dataset.schema_name || "-")}</td>
      <td>${escapeHtml(dataset.database_name || "-")}</td>
      <td>${dataset.folder_name ? `<span class="folder-badge">${icon("folder")}${escapeHtml(dataset.folder_name)}</span>` : '<span class="muted-value">Joylanmagan</span>'}</td>
      <td>${renderTags(dataset.tags)}</td>
      <td><span class="dataset-id">#${dataset.superset_id}</span></td>
      <td>${escapeHtml(formatDateTime(dataset.synced_at))}</td>
      <td>
        <div class="row-actions dataset-actions">
          <button class="icon-button view-button" type="button" data-dataset-view="${dataset.superset_id}" title="Ko'rish" aria-label="${escapeHtml(dataset.table_name)} datasetini ko'rish">${icon("eye")}</button>
          <button class="icon-button edit-button" type="button" data-dataset-edit="${dataset.superset_id}" title="Tahrirlash" aria-label="${escapeHtml(dataset.table_name)} datasetini tahrirlash">${icon("pencil")}</button>
          <button class="icon-button move-button" type="button" data-dataset-move="${dataset.superset_id}" title="Papkaga ko'chirish" aria-label="${escapeHtml(dataset.table_name)} datasetini papkaga ko'chirish">${icon("folder-input")}</button>
          <button class="icon-button delete-button" type="button" data-dataset-delete="${dataset.superset_id}" title="O'chirish" aria-label="${escapeHtml(dataset.table_name)} datasetini o'chirish">${icon("trash")}</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderTags(tags = []) {
  if (!tags.length) return '<span class="muted-value">-</span>';
  return `<div class="tag-list">${tags.map((tag) => `<span class="tag-badge">${escapeHtml(tag)}</span>`).join("")}</div>`;
}

async function loadDatasets() {
  const payload = await api("/api/datasets");
  state.datasets = payload.datasets;
  state.datasetDetails.clear();
  renderDatasets();
}

function openDatasetMove(id) {
  const dataset = state.datasets.find((item) => item.superset_id === id);
  if (!dataset) return;
  state.datasetMoveTarget = dataset;
  elements.datasetMoveError.textContent = "";
  document.querySelector("#datasetMoveName").textContent = dataset.table_name;
  document.querySelector("#datasetMoveFolder").value = dataset.folder_name || "";
  elements.datasetMoveDialog.showModal();
}

function collectionOptions(selectedId = null) {
  return state.metabaseCollections.filter((collection) => collection.can_write).map((collection) => {
    const value = collection.id === null ? "" : String(collection.id);
    const selected = String(selectedId ?? "") === value ? " selected" : "";
    return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(collection.path)}</option>`;
  }).join("");
}

function queryTypeName(query) {
  if (query.query_type === "native") return "SQL";
  if (query.type === "model") return "Model";
  return "Konstruktor";
}

function renderMetabaseQueries() {
  const search = elements.metabaseSearch.value.trim().toLocaleLowerCase("uz");
  const collection = elements.metabaseCollectionFilter.value;
  const queries = state.metabaseQueries.filter((query) => {
    const matchesCollection = collection === "all" || String(query.collection_id ?? "") === collection;
    const haystack = `${query.name} ${query.collection_name} ${query.database_name} ${query.creator_name}`.toLocaleLowerCase("uz");
    return matchesCollection && haystack.includes(search);
  });
  elements.metabaseCount.textContent = `${queries.length} ta query`;
  elements.metabaseEmpty.hidden = queries.length > 0;
  elements.metabaseTableWrap.hidden = queries.length === 0;
  elements.metabaseTable.innerHTML = queries.map((query) => `
    <tr>
      <td><div class="query-name"><strong>${escapeHtml(query.name)}</strong><span>#${query.id}</span></div></td>
      <td><span class="folder-badge">${icon("folder")}${escapeHtml(query.collection_name)}</span></td>
      <td><span class="query-type-badge">${escapeHtml(queryTypeName(query))}</span></td>
      <td>${escapeHtml(query.database_name || "-")}</td>
      <td>${query.updated_at ? escapeHtml(formatDateTime(query.updated_at)) : "-"}</td>
      <td>
        <div class="row-actions metabase-actions">
          <button class="icon-button view-button" type="button" data-metabase-view="${query.id}" title="Ko'rish" aria-label="${escapeHtml(query.name)} querysini ko'rish">${icon("eye")}</button>
          <button class="icon-button edit-button" type="button" data-metabase-edit="${query.id}" title="Tahrirlash" aria-label="${escapeHtml(query.name)} querysini tahrirlash">${icon("pencil")}</button>
          <button class="icon-button copy-button" type="button" data-metabase-copy="${query.id}" title="Nusxalash" aria-label="${escapeHtml(query.name)} querysidan nusxa olish">${icon("copy")}</button>
          <button class="icon-button move-button" type="button" data-metabase-move="${query.id}" title="Boshqa collectionga ko'chirish" aria-label="${escapeHtml(query.name)} querysini ko'chirish">${icon("folder-input")}</button>
          <button class="icon-button delete-button" type="button" data-metabase-delete="${query.id}" title="O'chirish" aria-label="${escapeHtml(query.name)} querysini o'chirish">${icon("trash")}</button>
        </div>
      </td>
    </tr>
  `).join("");
}

async function loadMetabaseQueries() {
  const payload = await api("/api/metabase/queries");
  state.metabaseQueries = payload.queries;
  state.metabaseCollections = payload.collections;
  state.metabaseDetails.clear();
  const selected = elements.metabaseCollectionFilter.value;
  elements.metabaseCollectionFilter.innerHTML = '<option value="all">Barcha collectionlar</option>'
    + state.metabaseCollections.map((collection) => {
      const value = collection.id === null ? "" : String(collection.id);
      return `<option value="${escapeHtml(value)}">${escapeHtml(collection.path)}</option>`;
    }).join("");
  if ([...elements.metabaseCollectionFilter.options].some((option) => option.value === selected)) {
    elements.metabaseCollectionFilter.value = selected;
  }
  renderMetabaseQueries();
}

async function getMetabaseDetails(id, force = false) {
  if (!force && state.metabaseDetails.has(id)) return state.metabaseDetails.get(id);
  const payload = await api(`/api/metabase/queries/${id}`);
  state.metabaseCollections = payload.collections;
  state.metabaseDetails.set(id, payload.query);
  return payload.query;
}

async function openMetabaseView(id) {
  const query = await getMetabaseDetails(id);
  document.querySelector("#metabaseViewTitle").textContent = query.name;
  document.querySelector("#metabaseViewCollection").textContent = query.collection_name;
  document.querySelector("#metabaseViewType").textContent = queryTypeName(query);
  document.querySelector("#metabaseViewDisplay").textContent = query.display || "-";
  document.querySelector("#metabaseViewCreator").textContent = query.creator_name || "-";
  document.querySelector("#metabaseViewDescription").textContent = query.description || "-";
  document.querySelector("#metabaseViewSqlRow").hidden = !query.sql;
  document.querySelector("#metabaseViewSql").textContent = query.sql || "";
  document.querySelector("#openInMetabase").href = query.metabase_url;
  elements.metabaseViewDialog.showModal();
}

async function openMetabaseEdit(id) {
  const query = await getMetabaseDetails(id, true);
  elements.metabaseEditForm.reset();
  elements.metabaseEditError.textContent = "";
  document.querySelector("#metabaseEditId").value = query.id;
  document.querySelector("#metabaseEditName").value = query.name;
  document.querySelector("#metabaseEditCollection").innerHTML = collectionOptions(query.collection_id);
  document.querySelector("#metabaseEditDescription").value = query.description || "";
  document.querySelector("#metabaseEditSqlField").hidden = !query.can_edit_sql;
  document.querySelector("#metabaseEditSql").value = query.sql || "";
  document.querySelector("#metabaseEditNote").textContent = query.can_edit_sql
    ? "Saqlanganda o'zgarishlar asosiy Metabase querysiga yoziladi."
    : "Bu query Metabase konstruktori bilan yaratilgan. Nomi, tavsifi va collectionini shu yerda o'zgartirish mumkin.";
  elements.metabaseEditDialog.showModal();
  document.querySelector("#metabaseEditName").focus();
}

function openMetabaseCollectionAction(query, mode) {
  state.metabaseCollectionAction = { query, mode };
  elements.metabaseCollectionForm.reset();
  elements.metabaseCollectionError.textContent = "";
  const copying = mode === "copy";
  document.querySelector("#metabaseCollectionTitle").textContent = copying ? "Querydan nusxa olish" : "Queryni ko'chirish";
  document.querySelector("#metabaseCollectionQueryName").textContent = query.name;
  document.querySelector("#metabaseCopyNameField").hidden = !copying;
  document.querySelector("#metabaseCopyName").value = copying ? `${query.name} - nusxa` : "";
  document.querySelector("#metabaseTargetCollection").innerHTML = collectionOptions(query.collection_id);
  document.querySelector("#metabaseCollectionSubmit").innerHTML = copying
    ? `${icon("copy")}Nusxalash`
    : `${icon("folder-input")}Ko'chirish`;
  elements.metabaseCollectionDialog.showModal();
}

function openMetabaseDelete(query) {
  state.metabaseDeleteTarget = query;
  elements.metabaseDeleteError.textContent = "";
  document.querySelector("#deleteMetabaseName").textContent = query.name;
  elements.metabaseDeleteDialog.showModal();
}

async function loadDatabases() {
  const payload = await api("/api/superset/databases");
  state.databases = payload.databases;
  const select = document.querySelector("#datasetCreateDatabase");
  select.innerHTML = state.databases.map((database) => (
    `<option value="${database.id}">${escapeHtml(database.name)}${database.backend ? ` (${escapeHtml(database.backend)})` : ""}</option>`
  )).join("");
  if (!state.databases.length) {
    select.innerHTML = '<option value="">Database topilmadi</option>';
  }
}

async function openDatasetCreate() {
  elements.datasetCreateForm.reset();
  elements.datasetCreateError.textContent = "";
  await loadDatabases();
  const schemaCounts = state.datasets.reduce((counts, dataset) => {
    if (dataset.schema_name) counts[dataset.schema_name] = (counts[dataset.schema_name] || 0) + 1;
    return counts;
  }, {});
  const commonSchema = Object.entries(schemaCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || "";
  document.querySelector("#datasetCreateSchema").value = commonSchema;
  elements.datasetCreateDialog.showModal();
  document.querySelector("#datasetCreateName").focus();
}

async function getDatasetDetails(id, force = false) {
  if (!force && state.datasetDetails.has(id)) return state.datasetDetails.get(id);
  const payload = await api(`/api/datasets/${id}`);
  state.datasetDetails.set(id, payload.dataset);
  return payload.dataset;
}

async function openDatasetView(id) {
  const dataset = await getDatasetDetails(id);
  document.querySelector("#datasetViewTitle").textContent = dataset.table_name;
  document.querySelector("#datasetViewSchema").textContent = dataset.schema_name || "-";
  document.querySelector("#datasetViewDatabase").textContent = dataset.database_name || "-";
  document.querySelector("#datasetViewId").textContent = `#${dataset.superset_id}`;
  document.querySelector("#datasetViewType").textContent = dataset.is_sqllab_view ? "Virtual dataset" : "Jadval";
  document.querySelector("#datasetViewCharts").textContent = dataset.charts_count;
  document.querySelector("#datasetViewDashboards").textContent = dataset.dashboards_count;
  document.querySelector("#datasetViewTags").innerHTML = renderTags(dataset.tags);
  document.querySelector("#datasetViewDescription").textContent = dataset.description || "-";
  document.querySelector("#datasetViewSqlRow").hidden = dataset.sql === null;
  document.querySelector("#datasetViewSql").textContent = dataset.sql || "";
  document.querySelector("#openInSuperset").href = dataset.superset_url;
  elements.datasetViewDialog.showModal();
}

async function openDatasetEdit(id) {
  const dataset = await getDatasetDetails(id, true);
  elements.datasetEditForm.reset();
  elements.datasetEditError.textContent = "";
  document.querySelector("#datasetEditId").value = dataset.superset_id;
  document.querySelector("#datasetEditName").value = dataset.table_name;
  document.querySelector("#datasetEditSchema").value = dataset.schema_name || "";
  document.querySelector("#datasetEditTags").value = dataset.tags.join(", ");
  document.querySelector("#datasetEditDescription").value = dataset.description || "";
  document.querySelector("#datasetEditSqlField").hidden = dataset.sql === null;
  document.querySelector("#datasetEditSql").value = dataset.sql || "";
  elements.datasetEditDialog.showModal();
  document.querySelector("#datasetEditName").focus();
}

async function openDatasetDelete(id) {
  const dataset = await getDatasetDetails(id, true);
  state.datasetDeleteTarget = dataset;
  elements.datasetDeleteError.textContent = "";
  document.querySelector("#deleteDatasetName").textContent = dataset.table_name;
  document.querySelector("#deleteDatasetRelations").textContent = `${dataset.charts_count} ta chart va ${dataset.dashboards_count} ta dashboard bog'langan.`;
  elements.datasetDeleteDialog.showModal();
}

async function syncDatasets() {
  elements.syncDatasetsButton.disabled = true;
  elements.syncDatasetsButton.classList.add("loading");
  try {
    const result = await api("/api/datasets/sync", { method: "POST" });
    await loadDatasets();
    showToast(`${result.count} ta dataset yangilandi`);
  } catch (error) {
    showToast(error.message);
  } finally {
    elements.syncDatasetsButton.disabled = false;
    elements.syncDatasetsButton.classList.remove("loading");
  }
}

function openUserDialog(user = null) {
  elements.userForm.reset();
  elements.userFormError.textContent = "";
  document.querySelector("#userId").value = user?.id || "";
  document.querySelector("#dialogTitle").textContent = user ? "Foydalanuvchini tahrirlash" : "Yangi foydalanuvchi";
  document.querySelector("#fullName").value = user?.full_name || "";
  document.querySelector("#username").value = user?.username || "";
  document.querySelector("#role").value = user?.role || "viewer";
  document.querySelector("#password").required = !user;
  document.querySelector("#passwordHint").textContent = user ? "(o'zgartirish uchun kiriting)" : "";
  document.querySelector("#activeField").hidden = !user;
  document.querySelector("#isActive").checked = user ? Boolean(user.is_active) : true;
  elements.userDialog.showModal();
  document.querySelector("#fullName").focus();
}

function openDeleteDialog(user) {
  state.deleteTarget = user;
  elements.deleteError.textContent = "";
  document.querySelector("#deleteUserName").textContent = user.full_name;
  elements.deleteDialog.showModal();
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("visible"), 2800);
}

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.loginError.textContent = "";
  const submit = event.submitter;
  submit.disabled = true;
  try {
    const payload = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.querySelector("#loginUsername").value,
        password: document.querySelector("#loginPassword").value,
      }),
    });
    state.csrfToken = payload.csrf_token;
    const me = await api("/api/auth/me");
    state.csrfToken = me.csrf_token;
    showApp(me.user);
    await loadUsers();
    elements.loginForm.reset();
  } catch (error) {
    elements.loginError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

document.querySelector(".password-toggle").addEventListener("click", () => {
  const input = document.querySelector("#loginPassword");
  input.type = input.type === "password" ? "text" : "password";
  document.querySelector(".password-toggle use").setAttribute("href", `/static/icons.svg#${input.type === "password" ? "eye" : "eye-off"}`);
});

document.querySelector("#logoutButton").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } finally { showLogin(); }
});

elements.addUserButton.addEventListener("click", () => openUserDialog());
elements.addDatasetButton.addEventListener("click", async () => {
  elements.addDatasetButton.disabled = true;
  try {
    await openDatasetCreate();
  } catch (error) {
    showToast(error.message);
  } finally {
    elements.addDatasetButton.disabled = false;
  }
});
document.querySelector("#closeDialog").addEventListener("click", () => elements.userDialog.close());
document.querySelector("#cancelDialog").addEventListener("click", () => elements.userDialog.close());
document.querySelector("#cancelDelete").addEventListener("click", () => elements.deleteDialog.close());
document.querySelector("#closeDatasetCreate").addEventListener("click", () => elements.datasetCreateDialog.close());
document.querySelector("#cancelDatasetCreate").addEventListener("click", () => elements.datasetCreateDialog.close());
elements.userSearch.addEventListener("input", renderUsers);
elements.datasetSearch.addEventListener("input", renderDatasets);
elements.metabaseSearch.addEventListener("input", renderMetabaseQueries);
elements.metabaseCollectionFilter.addEventListener("change", renderMetabaseQueries);
elements.syncDatasetsButton.addEventListener("click", syncDatasets);
document.querySelector("#closeDatasetView").addEventListener("click", () => elements.datasetViewDialog.close());
document.querySelector("#closeDatasetViewAction").addEventListener("click", () => elements.datasetViewDialog.close());
document.querySelector("#closeDatasetEdit").addEventListener("click", () => elements.datasetEditDialog.close());
document.querySelector("#cancelDatasetEdit").addEventListener("click", () => elements.datasetEditDialog.close());
document.querySelector("#cancelDatasetDelete").addEventListener("click", () => elements.datasetDeleteDialog.close());
document.querySelector("#closeDatasetMove").addEventListener("click", () => elements.datasetMoveDialog.close());
document.querySelector("#cancelDatasetMove").addEventListener("click", () => elements.datasetMoveDialog.close());
document.querySelector("#closeMetabaseView").addEventListener("click", () => elements.metabaseViewDialog.close());
document.querySelector("#closeMetabaseViewAction").addEventListener("click", () => elements.metabaseViewDialog.close());
document.querySelector("#closeMetabaseEdit").addEventListener("click", () => elements.metabaseEditDialog.close());
document.querySelector("#cancelMetabaseEdit").addEventListener("click", () => elements.metabaseEditDialog.close());
document.querySelector("#closeMetabaseCollection").addEventListener("click", () => elements.metabaseCollectionDialog.close());
document.querySelector("#cancelMetabaseCollection").addEventListener("click", () => elements.metabaseCollectionDialog.close());
document.querySelector("#cancelMetabaseDelete").addEventListener("click", () => elements.metabaseDeleteDialog.close());

elements.datasetFolderTabs.addEventListener("click", (event) => {
  const button = event.target.closest("[data-folder]");
  if (!button) return;
  state.datasetFolder = button.dataset.folder;
  elements.datasetFolderTabs.querySelectorAll("[data-folder]").forEach((item) => item.classList.toggle("active", item === button));
  renderDatasets();
});

elements.datasetsTable.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-dataset-view], [data-dataset-edit], [data-dataset-move], [data-dataset-delete]");
  if (!button) return;
  button.disabled = true;
  try {
    if (button.dataset.datasetView) await openDatasetView(Number(button.dataset.datasetView));
    if (button.dataset.datasetEdit) await openDatasetEdit(Number(button.dataset.datasetEdit));
    if (button.dataset.datasetMove) openDatasetMove(Number(button.dataset.datasetMove));
    if (button.dataset.datasetDelete) await openDatasetDelete(Number(button.dataset.datasetDelete));
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

elements.metabaseTable.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-metabase-view], [data-metabase-edit], [data-metabase-copy], [data-metabase-move], [data-metabase-delete]");
  if (!button) return;
  const id = Number(button.dataset.metabaseView || button.dataset.metabaseEdit || button.dataset.metabaseCopy || button.dataset.metabaseMove || button.dataset.metabaseDelete);
  const query = state.metabaseQueries.find((item) => item.id === id);
  button.disabled = true;
  try {
    if (button.dataset.metabaseView) await openMetabaseView(id);
    if (button.dataset.metabaseEdit) await openMetabaseEdit(id);
    if (button.dataset.metabaseCopy) openMetabaseCollectionAction(query, "copy");
    if (button.dataset.metabaseMove) openMetabaseCollectionAction(query, "move");
    if (button.dataset.metabaseDelete) openMetabaseDelete(query);
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

elements.usersTable.addEventListener("click", (event) => {
  const editId = event.target.closest("[data-edit]")?.dataset.edit;
  const deleteId = event.target.closest("[data-delete]")?.dataset.delete;
  if (editId) openUserDialog(state.users.find((user) => user.id === Number(editId)));
  if (deleteId) openDeleteDialog(state.users.find((user) => user.id === Number(deleteId)));
});

elements.userForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.userFormError.textContent = "";
  const id = document.querySelector("#userId").value;
  const payload = {
    full_name: document.querySelector("#fullName").value,
    username: document.querySelector("#username").value,
    role: document.querySelector("#role").value,
    password: document.querySelector("#password").value,
    is_active: document.querySelector("#isActive").checked,
  };
  try {
    await api(id ? `/api/users/${id}` : "/api/users", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    elements.userDialog.close();
    await loadUsers();
    showToast(id ? "Foydalanuvchi yangilandi" : "Foydalanuvchi qo'shildi");
  } catch (error) {
    elements.userFormError.textContent = error.message;
  }
});

elements.deleteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.deleteError.textContent = "";
  try {
    await api(`/api/users/${state.deleteTarget.id}`, { method: "DELETE" });
    elements.deleteDialog.close();
    await loadUsers();
    showToast("Foydalanuvchi o'chirildi");
  } catch (error) {
    elements.deleteError.textContent = error.message;
  }
});

elements.datasetCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.datasetCreateError.textContent = "";
  const submit = event.submitter;
  submit.disabled = true;
  try {
    const result = await api("/api/datasets", {
      method: "POST",
      body: JSON.stringify({
        database_id: Number(document.querySelector("#datasetCreateDatabase").value),
        schema_name: document.querySelector("#datasetCreateSchema").value,
        table_name: document.querySelector("#datasetCreateName").value,
        sql: document.querySelector("#datasetCreateSql").value,
        tags: document.querySelector("#datasetCreateTags").value.split(",").map((tag) => tag.trim()).filter(Boolean),
        description: document.querySelector("#datasetCreateDescription").value,
      }),
    });
    elements.datasetCreateDialog.close();
    await loadDatasets();
    showToast(`Dataset #${result.id} Supersetda yaratildi`);
  } catch (error) {
    elements.datasetCreateError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

elements.datasetEditForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.datasetEditError.textContent = "";
  const id = Number(document.querySelector("#datasetEditId").value);
  const sqlField = document.querySelector("#datasetEditSqlField");
  const submit = event.submitter;
  submit.disabled = true;
  try {
    await api(`/api/datasets/${id}`, {
      method: "PUT",
      body: JSON.stringify({
        table_name: document.querySelector("#datasetEditName").value,
        schema_name: document.querySelector("#datasetEditSchema").value,
        tags: document.querySelector("#datasetEditTags").value.split(",").map((tag) => tag.trim()).filter(Boolean),
        description: document.querySelector("#datasetEditDescription").value,
        sql: sqlField.hidden ? null : document.querySelector("#datasetEditSql").value,
      }),
    });
    elements.datasetEditDialog.close();
    await loadDatasets();
    showToast("Dataset Supersetda yangilandi");
  } catch (error) {
    elements.datasetEditError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

elements.datasetDeleteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.datasetDeleteError.textContent = "";
  const submit = event.submitter;
  submit.disabled = true;
  try {
    await api(`/api/datasets/${state.datasetDeleteTarget.superset_id}`, { method: "DELETE" });
    elements.datasetDeleteDialog.close();
    await loadDatasets();
    showToast("Dataset Supersetdan o'chirildi");
  } catch (error) {
    elements.datasetDeleteError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

elements.datasetMoveForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.datasetMoveError.textContent = "";
  const submit = event.submitter;
  submit.disabled = true;
  try {
    await api(`/api/datasets/${state.datasetMoveTarget.superset_id}/folder`, {
      method: "PUT",
      body: JSON.stringify({ folder_name: document.querySelector("#datasetMoveFolder").value }),
    });
    elements.datasetMoveDialog.close();
    await loadDatasets();
    showToast("Dataset papkaga joylandi");
  } catch (error) {
    elements.datasetMoveError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

elements.metabaseEditForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.metabaseEditError.textContent = "";
  const id = Number(document.querySelector("#metabaseEditId").value);
  const sqlField = document.querySelector("#metabaseEditSqlField");
  const submit = event.submitter;
  submit.disabled = true;
  try {
    await api(`/api/metabase/queries/${id}`, {
      method: "PUT",
      body: JSON.stringify({
        name: document.querySelector("#metabaseEditName").value,
        collection_id: document.querySelector("#metabaseEditCollection").value,
        description: document.querySelector("#metabaseEditDescription").value,
        sql: sqlField.hidden ? null : document.querySelector("#metabaseEditSql").value,
      }),
    });
    elements.metabaseEditDialog.close();
    await loadMetabaseQueries();
    showToast("Query Metabaseda yangilandi");
  } catch (error) {
    elements.metabaseEditError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

elements.metabaseCollectionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.metabaseCollectionError.textContent = "";
  const { query, mode } = state.metabaseCollectionAction;
  const submit = event.submitter;
  submit.disabled = true;
  try {
    const payload = { collection_id: document.querySelector("#metabaseTargetCollection").value };
    if (mode === "copy") payload.name = document.querySelector("#metabaseCopyName").value;
    await api(`/api/metabase/queries/${query.id}/${mode}`, {
      method: mode === "copy" ? "POST" : "PUT",
      body: JSON.stringify(payload),
    });
    elements.metabaseCollectionDialog.close();
    await loadMetabaseQueries();
    showToast(mode === "copy" ? "Query nusxasi Metabaseda yaratildi" : "Query boshqa collectionga ko'chirildi");
  } catch (error) {
    elements.metabaseCollectionError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

elements.metabaseDeleteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.metabaseDeleteError.textContent = "";
  const submit = event.submitter;
  submit.disabled = true;
  try {
    await api(`/api/metabase/queries/${state.metabaseDeleteTarget.id}`, { method: "DELETE" });
    elements.metabaseDeleteDialog.close();
    await loadMetabaseQueries();
    showToast("Query Metabase Trash bo'limiga o'tkazildi");
  } catch (error) {
    elements.metabaseDeleteError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", async () => {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item === button));
    const page = button.dataset.page;
    document.querySelector("#usersPage").hidden = page !== "users";
    document.querySelector("#datasetsPage").hidden = page !== "datasets";
    elements.metabasePage.hidden = page !== "metabase";
    document.querySelector("#pageTitle").textContent = {
      users: "Foydalanuvchilar",
      datasets: "Superset datasetlar",
      metabase: "Metabase querylar",
    }[page];
    elements.addUserButton.hidden = page !== "users";
    elements.addDatasetButton.hidden = page !== "datasets";
    elements.syncDatasetsButton.hidden = page !== "datasets";
    elements.sidebar.classList.remove("open");
    try {
      if (page === "datasets") await loadDatasets();
      if (page === "metabase") await loadMetabaseQueries();
    } catch (error) {
      showToast(error.message);
    }
  });
});

document.querySelector("#menuButton").addEventListener("click", () => elements.sidebar.classList.toggle("open"));

(async function boot() {
  try {
    const payload = await api("/api/auth/me");
    state.csrfToken = payload.csrf_token;
    showApp(payload.user);
    await loadUsers();
  } catch (_error) {
    showLogin();
  }
})();
