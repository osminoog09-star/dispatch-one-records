// LAPD Records — клиент Supabase для статичного сайта (вход + админка/тикеты).
// publishable-ключ публичный, безопасен в браузере (доступ ограничен RLS).
(function () {
  const SUPABASE_URL = "https://gwvqfiwdbviwoimvhdvg.supabase.co";
  const SUPABASE_KEY = "sb_publishable_gkXQmLngTvpGQfLFDk2YnA_nuv0krkk";
  if (!window.supabase) { console.warn("supabase-js не загрузился"); return; }
  const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
  window.lapd = { sb };

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
  window.lapd.session = session;
  window.lapd.isAdmin = isAdmin;

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
      const admin = await isAdmin();
      const name = (s.user.user_metadata && (s.user.user_metadata.full_name || s.user.user_metadata.name))
                   || s.user.email || "вход";
      window.lapd.userName = name;
      if (slot) {
        slot.innerHTML = '<span class="auth-user">' + name + (admin ? " · админ" : "") +
          '</span> <a href="#" class="auth-link" onclick="lapdLogout();return false">выйти</a>';
      }
      if (admin) document.querySelectorAll(".admin-only").forEach(function (x) { x.style.display = ""; });
      window.lapd.admin = admin;
    } else {
      if (slot) slot.innerHTML = '<a href="#" class="auth-link" onclick="lapdLogin();return false">Войти</a>';
      window.lapd.admin = false;
    }
    document.dispatchEvent(new Event("lapd:auth"));
  }
  document.addEventListener("DOMContentLoaded", initNav);
})();
