(function () {
  var AUTH_TOKEN_KEY = 'kazix_access_token';
  var LEGACY_AUTH_KEYS = new Set([
    'kazix_access_token',
    'kazix_refresh_token',
    'kazix_expires_in',
    'kazix_expires_at',
    'kazix_token_type',
    'kazix_user_id',
    'kazix_role',
    'kazix_login_email',
    'kazix_reg_pending_profile',
    'kazix_profile',
    'kazix_dashboard_state',
    'kazix_notification_summary',
  ]);

  function isSupabaseStorageKey(key) {
    return key === 'supabase.auth.token'
      || /^sb-[a-z0-9_-]+-auth-token(?:-code-verifier)?$/i.test(key);
  }

  function purgeLegacyPersistentAuth() {
    var storage = window.localStorage;
    if (!storage) return;

    for (var index = storage.length - 1; index >= 0; index -= 1) {
      var key = storage.key(index);
      if (!key) continue;

      if (LEGACY_AUTH_KEYS.has(key) || isSupabaseStorageKey(key)) {
        storage.removeItem(key);
      }
    }
  }

  function hasSession() {
    try {
      return Boolean(window.sessionStorage.getItem(AUTH_TOKEN_KEY));
    } catch (_error) {
      return false;
    }
  }

  function buildLoginHref() {
    var next = encodeURIComponent(window.location.pathname + window.location.search);
    return 'login.html?next=' + next;
  }

  function requireAuthPage() {
    purgeLegacyPersistentAuth();
    if (hasSession()) {
      return true;
    }

    window.location.replace(buildLoginHref());
    return false;
  }

  purgeLegacyPersistentAuth();

  window.KazixAuthGuard = {
    hasSession: hasSession,
    purgeLegacyPersistentAuth: purgeLegacyPersistentAuth,
    requireAuthPage: requireAuthPage,
  };
})();
