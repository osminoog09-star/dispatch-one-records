// LAPD Records — клиент Supabase для статичного сайта (вход + админка/тикеты).
// publishable-ключ публичный, безопасен в браузере (доступ ограничен RLS).
(function () {
  const SUPABASE_URL = "https://gwvqfiwdbviwoimvhdvg.supabase.co";
  const SUPABASE_KEY = "sb_publishable_gkXQmLngTvpGQfLFDk2YnA_nuv0krkk";
  if (!window.supabase) { console.warn("supabase-js не загрузился"); return; }
  function supportClientId() {
    const key = "lapd_support_client_id";
    let id = localStorage.getItem(key);
    if (!id) {
      id = (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : "site-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
      localStorage.setItem(key, id);
    }
    return id;
  }
  const clientId = supportClientId();
  const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
    global: { headers: { "x-client-id": clientId } },
  });
  window.lapd = { sb, clientId };

  async function session() {
    const { data } = await sb.auth.getSession();
    return data.session;
  }
  async function isAdmin() {
    try {
      const { data, error } = await sb.rpc("is_admin");
      return !error && data === true;
    } catch (e) { return false; }
  }
  async function permissions() {
    try {
      const { data, error } = await sb.rpc("my_permissions");
      if (!error && data) return data;
    } catch (e) {}
    const admin = await isAdmin();
    return {
      role: admin ? "admin" : "viewer",
      title: admin ? "Админ" : "Наблюдатель",
      is_owner: false,
      is_admin: admin,
      can_access_admin: admin,
      can_tickets: admin,
      can_staff: admin,
      can_dictionaries: admin,
      can_moderate: admin,
      can_audit: admin,
      can_admins: false,
    };
  }
  window.lapd.session = session;
  window.lapd.isAdmin = isAdmin;
  window.lapd.permissions = {};

  window.lapdLogin = async function () {
    await sb.auth.signInWithOAuth({
      provider: "discord",
      options: { redirectTo: window.location.origin + window.location.pathname },
    });
  };
  window.lapdLogout = async function () {
    await sb.auth.signOut();
    location.reload();
  };

  async function initNav() {
    const slot = document.getElementById("auth-slot");
    const s = await session();
    if (s) {
      const perms = await permissions();
      const admin = perms.is_admin === true;
      const canAccessAdmin = perms.can_access_admin === true || admin;
      const name = (s.user.user_metadata && (s.user.user_metadata.full_name || s.user.user_metadata.name))
                   || s.user.email || "вход";
      window.lapd.userName = name;
      window.lapd.permissions = perms;
      if (slot) {
        slot.innerHTML = '<span class="auth-user">' + name + (perms.title ? " · " + perms.title : "") +
          '</span> <a href="#" class="auth-link" onclick="lapdLogout();return false">выйти</a>';
      }
      if (canAccessAdmin) document.querySelectorAll(".admin-only").forEach(function (x) { x.style.display = ""; });
      window.lapd.admin = admin;
      window.lapd.canTickets = perms.can_tickets === true;
      window.lapd.canStaff = perms.can_staff === true;
      window.lapd.canDictionaries = perms.can_dictionaries === true;
      window.lapd.canAdmins = perms.can_admins === true;
    } else {
      if (slot) slot.innerHTML = '<a href="#" class="auth-link" onclick="lapdLogin();return false">Войти</a>';
      window.lapd.admin = false;
      window.lapd.canTickets = false;
      window.lapd.canStaff = false;
      window.lapd.canDictionaries = false;
      window.lapd.canAdmins = false;
      window.lapd.permissions = {};
    }
    document.dispatchEvent(new Event("lapd:auth"));
  }
  document.addEventListener("DOMContentLoaded", initNav);
})();
