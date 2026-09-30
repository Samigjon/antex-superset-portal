const state = {
  csrfToken: "",
  currentUser: null,
  users: [],
  datasets: [],
  deleteTarget: null,
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
  addUserButton: document.querySelector("#addUserButton"),
  syncDatasetsButton: document.querySelector("#syncDatasetsButton"),
  userDialog: document.querySelector("#userDialog"),
  userForm: document.querySelector("#userForm"),
  userFormError: document.querySelector("#userFormError"),
  deleteDialog: document.querySelector("#deleteDialog"),
  deleteForm: document.querySelector("#deleteForm"),
  deleteError: document.querySelector("#deleteError"),
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
          <button class="icon-button edit-button" type="button" data-edit="${user.id}" title="Tahrirlash" aria-label="${escapeHtml(user.full_name)}ni tahrirlash"></button>
          <button class="icon-button delete-button" type="button" data-delete="${user.id}" title="O'chirish" aria-label="${escapeHtml(user.full_name)}ni o'chirish"></button>
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
  const datasets = state.datasets.filter((dataset) => (
    `${dataset.table_name} ${dataset.schema_name || ""} ${dataset.database_name || ""}`
      .toLocaleLowerCase("uz")
      .includes(query)
  ));
  elements.datasetCount.textContent = `${datasets.length} ta dataset`;
  elements.datasetsEmpty.hidden = state.datasets.length > 0;
  elements.datasetsTableWrap.hidden = state.datasets.length === 0;
  elements.datasetsTable.innerHTML = datasets.map((dataset) => `
    <tr>
      <td><div class="dataset-name"><span class="database-icon" aria-hidden="true"></span><strong>${escapeHtml(dataset.table_name)}</strong></div></td>
      <td>${escapeHtml(dataset.schema_name || "-")}</td>
      <td>${escapeHtml(dataset.database_name || "-")}</td>
      <td><span class="dataset-id">#${dataset.superset_id}</span></td>
      <td>${escapeHtml(formatDateTime(dataset.synced_at))}</td>
    </tr>
  `).join("");
}

async function loadDatasets() {
  const payload = await api("/api/datasets");
  state.datasets = payload.datasets;
  renderDatasets();
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
});

document.querySelector("#logoutButton").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } finally { showLogin(); }
});

elements.addUserButton.addEventListener("click", () => openUserDialog());
document.querySelector("#closeDialog").addEventListener("click", () => elements.userDialog.close());
document.querySelector("#cancelDialog").addEventListener("click", () => elements.userDialog.close());
document.querySelector("#cancelDelete").addEventListener("click", () => elements.deleteDialog.close());
elements.userSearch.addEventListener("input", renderUsers);
elements.datasetSearch.addEventListener("input", renderDatasets);
elements.syncDatasetsButton.addEventListener("click", syncDatasets);

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

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", async () => {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item === button));
    const users = button.dataset.page === "users";
    document.querySelector("#usersPage").hidden = !users;
    document.querySelector("#datasetsPage").hidden = users;
    document.querySelector("#pageTitle").textContent = users ? "Foydalanuvchilar" : "SQL datasetlar";
    elements.addUserButton.hidden = !users;
    elements.syncDatasetsButton.hidden = users;
    elements.sidebar.classList.remove("open");
    if (!users) {
      try {
        await loadDatasets();
      } catch (error) {
        showToast(error.message);
      }
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
