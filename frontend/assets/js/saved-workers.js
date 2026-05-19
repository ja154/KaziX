(function () {
  const STORAGE_PREFIX = 'kazix_saved_workers:';
  const SAVED_WORKERS_EVENT = 'kazix:saved-workers-updated';
  const TRADE_LABELS = {
    plumber: 'Plumber',
    electrician: 'Electrician',
    mason: 'Mason',
    mama_fua: 'Mama Fua',
    carpenter: 'Carpenter',
    painter: 'Painter',
    roofer: 'Roofer',
    gardener: 'Gardener',
    driver_mover: 'Driver / Mover',
    security: 'Security',
    other: 'Skilled Worker',
  };
  const TRADE_EMOJIS = {
    plumber: '🚿',
    electrician: '⚡',
    mason: '🧱',
    mama_fua: '👗',
    carpenter: '🪚',
    painter: '🎨',
    roofer: '🏠',
    gardener: '🌿',
    driver_mover: '🛻',
    security: '🔒',
    other: '🔧',
  };

  function getProfileHelpers() {
    return window.KazixProfile || null;
  }

  function safeJson(text) {
    try {
      return JSON.parse(text);
    } catch (_error) {
      return null;
    }
  }

  function trimValue(value) {
    return String(value || '').trim();
  }

  function toFiniteNumber(value) {
    const normalized = Number(value);
    return Number.isFinite(normalized) ? normalized : null;
  }

  function resolveCurrentUserId() {
    const helpers = getProfileHelpers();
    if (helpers && typeof helpers.getStoredUserId === 'function') {
      const helperUserId = trimValue(helpers.getStoredUserId());
      if (helperUserId) {
        return helperUserId;
      }
    }

    const storedUserId = trimValue(window.sessionStorage.getItem('kazix_user_id'));
    if (storedUserId) {
      return storedUserId;
    }

    const cachedProfile = safeJson(window.sessionStorage.getItem('kazix_profile') || 'null');
    return trimValue(cachedProfile && cachedProfile.id);
  }

  function resolveStorageKey(userId) {
    return `${STORAGE_PREFIX}${trimValue(userId) || resolveCurrentUserId() || 'guest'}`;
  }

  function formatTradeLabel(trade) {
    return TRADE_LABELS[trade] || TRADE_LABELS.other;
  }

  function formatTradeEmoji(trade) {
    return TRADE_EMOJIS[trade] || TRADE_EMOJIS.other;
  }

  function normalizeSkills(skills) {
    if (Array.isArray(skills)) {
      return skills
        .map((skill) => trimValue(skill))
        .filter(Boolean)
        .slice(0, 8);
    }

    if (typeof skills === 'string') {
      return skills
        .split(',')
        .map((skill) => trimValue(skill))
        .filter(Boolean)
        .slice(0, 8);
    }

    return [];
  }

  function formatRateLabel(rateMin, rateMax) {
    const min = toFiniteNumber(rateMin);
    const max = toFiniteNumber(rateMax);

    if (min !== null && min > 0) {
      return `KES ${Math.round(min).toLocaleString()}/hr`;
    }

    if (max !== null && max > 0) {
      return `KES ${Math.round(max).toLocaleString()}/hr`;
    }

    return 'Negotiable';
  }

  function normalizeSavedWorker(worker) {
    if (!worker || !worker.id) {
      return null;
    }

    const id = trimValue(worker.id);
    if (!id) {
      return null;
    }

    const trade = trimValue(worker.trade).toLowerCase() || 'other';
    const rateMin = toFiniteNumber(worker.rate_min);
    const rateMax = toFiniteNumber(worker.rate_max);
    const rating = toFiniteNumber(worker.rating);
    const jobsCompleted = toFiniteNumber(worker.jobs_completed);
    const experienceYears = toFiniteNumber(worker.experience_years);
    const serviceRadiusKm = toFiniteNumber(worker.service_radius_km);

    return {
      id,
      full_name: trimValue(worker.full_name) || 'Saved fundi',
      avatar_url: trimValue(worker.avatar_url),
      trade,
      trade_label: trimValue(worker.trade_label) || formatTradeLabel(trade),
      trade_emoji: trimValue(worker.trade_emoji) || formatTradeEmoji(trade),
      county: trimValue(worker.county),
      area: trimValue(worker.area),
      is_verified: Boolean(worker.is_verified),
      is_available: worker.is_available === null || worker.is_available === undefined
        ? null
        : Boolean(worker.is_available),
      rate_min: rateMin,
      rate_max: rateMax,
      rate_label: trimValue(worker.rate_label) || formatRateLabel(rateMin, rateMax),
      rating: rating === null ? null : Math.max(0, Math.min(5, rating)),
      jobs_completed: jobsCompleted === null ? 0 : Math.max(0, Math.round(jobsCompleted)),
      skills: normalizeSkills(worker.skills),
      experience_years: experienceYears === null ? null : Math.max(0, Math.round(experienceYears)),
      service_radius_km: serviceRadiusKm === null ? null : Math.max(0, Math.round(serviceRadiusKm)),
      saved_at: Number(worker.saved_at) || Date.now(),
    };
  }

  function sortSavedWorkers(items) {
    return items.sort((left, right) => Number(right.saved_at || 0) - Number(left.saved_at || 0));
  }

  function readSavedWorkers(options = {}) {
    const raw = window.localStorage.getItem(resolveStorageKey(options.userId)) || '[]';
    const parsed = safeJson(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return sortSavedWorkers(
      parsed
        .map((item) => normalizeSavedWorker(item))
        .filter(Boolean)
    );
  }

  function dispatchSavedWorkersEvent(items, options = {}) {
    if (typeof window.CustomEvent !== 'function') {
      return;
    }

    window.dispatchEvent(new CustomEvent(SAVED_WORKERS_EVENT, {
      detail: {
        user_id: trimValue(options.userId) || resolveCurrentUserId() || null,
        count: items.length,
        items,
      },
    }));
  }

  function syncSavedWorkersNavCount() {
    const helpers = getProfileHelpers();
    const count = getSavedWorkersCount();

    if (helpers && typeof helpers.setNavCount === 'function') {
      helpers.setNavCount('saved-workers.html', count);
    }

    return count;
  }

  function writeSavedWorkers(items, options = {}) {
    const normalized = sortSavedWorkers(
      (Array.isArray(items) ? items : [])
        .map((item) => normalizeSavedWorker(item))
        .filter(Boolean)
    );

    window.localStorage.setItem(resolveStorageKey(options.userId), JSON.stringify(normalized));
    syncSavedWorkersNavCount();
    dispatchSavedWorkersEvent(normalized, options);
    return normalized;
  }

  function saveWorker(worker, options = {}) {
    const normalized = normalizeSavedWorker(worker);
    if (!normalized) {
      return readSavedWorkers(options);
    }

    const current = readSavedWorkers(options).filter((item) => item.id !== normalized.id);
    current.push(normalized);
    return writeSavedWorkers(current, options);
  }

  function removeSavedWorker(workerId, options = {}) {
    const normalizedId = trimValue(workerId);
    if (!normalizedId) {
      return readSavedWorkers(options);
    }

    const next = readSavedWorkers(options).filter((item) => item.id !== normalizedId);
    return writeSavedWorkers(next, options);
  }

  function isWorkerSaved(workerId, options = {}) {
    const normalizedId = trimValue(workerId);
    if (!normalizedId) {
      return false;
    }

    return readSavedWorkers(options).some((item) => item.id === normalizedId);
  }

  function toggleSavedWorker(worker, options = {}) {
    const normalized = normalizeSavedWorker(worker);
    if (!normalized) {
      return {
        saved: false,
        items: readSavedWorkers(options),
      };
    }

    if (isWorkerSaved(normalized.id, options)) {
      return {
        saved: false,
        items: removeSavedWorker(normalized.id, options),
      };
    }

    return {
      saved: true,
      items: saveWorker(normalized, options),
    };
  }

  function getSavedWorkersCount(options = {}) {
    return readSavedWorkers(options).length;
  }

  function buildSavedWorkerFromSearchResult(worker) {
    return normalizeSavedWorker(worker);
  }

  function buildSavedWorkerFromProfile(profile, fundiProfile) {
    if (!profile || !profile.id) {
      return null;
    }

    const worker = {
      id: profile.id,
      full_name: profile.full_name,
      avatar_url: profile.avatar_url,
      trade: fundiProfile?.trade,
      county: profile.county,
      area: profile.area,
      is_verified: Boolean(profile.is_verified)
        || String(fundiProfile?.kyc_status || '').toLowerCase() === 'approved',
      is_available: fundiProfile?.is_available,
      rate_min: fundiProfile?.rate_min,
      rate_max: fundiProfile?.rate_max,
      rating: fundiProfile?.rating_avg,
      jobs_completed: fundiProfile?.jobs_completed,
      skills: fundiProfile?.skills,
      experience_years: fundiProfile?.experience_years,
      service_radius_km: fundiProfile?.service_radius_km,
    };

    return normalizeSavedWorker(worker);
  }

  window.KazixSavedWorkers = {
    SAVED_WORKERS_EVENT,
    buildSavedWorkerFromProfile,
    buildSavedWorkerFromSearchResult,
    formatTradeEmoji,
    formatTradeLabel,
    getSavedWorkersCount,
    isWorkerSaved,
    normalizeSavedWorker,
    readSavedWorkers,
    removeSavedWorker,
    resolveCurrentUserId,
    saveWorker,
    syncSavedWorkersNavCount,
    toggleSavedWorker,
    writeSavedWorkers,
  };

  window.addEventListener('storage', function (event) {
    if (!event.key) {
      return;
    }

    if (event.key === 'kazix_user_id' || event.key.indexOf(STORAGE_PREFIX) === 0) {
      syncSavedWorkersNavCount();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', syncSavedWorkersNavCount);
  } else {
    syncSavedWorkersNavCount();
  }
})();
