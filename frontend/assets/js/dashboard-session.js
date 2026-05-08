(function () {
  function firstName(fullName) {
    return String(fullName || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean)[0] || "there";
  }

  function greetingForHour(date) {
    var hour = date.getHours();
    if (hour < 12) return "Good morning";
    if (hour < 18) return "Good afternoon";
    return "Good evening";
  }

  function setupUserMenuToggle() {
    var userChipToggle = document.getElementById("userChipToggle");
    var userMenuDropdown = document.getElementById("userMenuDropdown");
    
    if (!userChipToggle || !userMenuDropdown) return;

    // Toggle dropdown when clicking user chip
    userChipToggle.addEventListener("click", function (e) {
      e.stopPropagation();
      userMenuDropdown.classList.toggle("active");
    });

    // Close dropdown when clicking outside
    document.addEventListener("click", function (e) {
      if (!userChipToggle.contains(e.target) && !userMenuDropdown.contains(e.target)) {
        userMenuDropdown.classList.remove("active");
      }
    });

    // Close dropdown when clicking a menu item
    var menuItems = userMenuDropdown.querySelectorAll(".user-menu-item");
    menuItems.forEach(function (item) {
      item.addEventListener("click", function () {
        userMenuDropdown.classList.remove("active");
      });
    });
  }

  async function hydrateDashboard(options) {
    options = options || {};
    var helpers = window.KazixProfile;
    if (!helpers) {
      console.error("KazixProfile helpers are required before dashboard-session.js");
      return;
    }

    var getAccessToken = helpers.getAccessToken;
    var requestJson = helpers.requestJson;
    var getMyProfile = helpers.getMyProfile;
    var initials = helpers.initials;
    var setText = helpers.setText;
    var formatLocation = helpers.formatLocation;
    var formatTrade = helpers.formatTrade;

    if (!getAccessToken()) {
      window.location.href = options.loginHref || "login.html";
      return;
    }

    try {
      var data = getMyProfile
        ? await getMyProfile()
        : await requestJson("/v1/profiles/me", { auth: true });
      var profile = data && data.profile ? data.profile : {};
      var fundiProfile = data && data.fundi_profile ? data.fundi_profile : {};
      var role = profile.role || "";

      if (!profile.id || !role) {
        throw new Error("Missing profile details.");
      }

      localStorage.setItem("kazix_role", role);

      if (options.expectedRole && role !== options.expectedRole) {
        var defaultRedirects = {
          client: "client-dashboard.html",
          fundi: "worker-dashboard.html",
          admin: "admin-dashboard.html",
        };
        var target = (options.roleRedirects && options.roleRedirects[role]) || defaultRedirects[role] || "index.html";
        window.location.replace(target);
        return;
      }

      var name = profile.full_name || "My account";
      var avatar = initials(name);
      var location = formatLocation(profile);
      var tradeLabel = fundiProfile.trade ? formatTrade(fundiProfile.trade) : null;
      var roleLabel = role === "fundi"
        ? (tradeLabel ? "Pro account · " + tradeLabel : "Pro account")
        : role === "admin"
          ? "Admin account"
          : "Client account";

      setText("#navUserAvatar", avatar);
      setText("#navUserName", name);
      setText("#sidebarAvatar", avatar);
      setText("#sidebarName", name);
      setText("#sidebarRole", roleLabel);

      // Update user menu header with user name
      var userMenuName = document.getElementById("userMenuName");
      if (userMenuName) {
        userMenuName.textContent = name;
      }

      // Setup user menu dropdown toggle
      setupUserMenuToggle();

      var greetingName = firstName(name);
      var greeting = greetingForHour(new Date()) + ", " + greetingName + " 👋";
      setText("#dashboardGreeting", greeting);
      setText("#availabilityLocation", location);
      if (typeof helpers.hydrateDashboardState === "function") {
        helpers.hydrateDashboardState({ silent: true });
      }
      if (typeof helpers.hydrateNotificationSummary === "function") {
        helpers.hydrateNotificationSummary({ silent: true });
      }

      if (options.updateDocumentTitle !== false) {
        document.title = role === "fundi"
          ? "Dashboard — " + name + " · KaziX Pro"
          : "Dashboard — " + name + " · KaziX";
      }
    } catch (error) {
      console.error("Failed to hydrate dashboard shell", error);
      if ((error && error.message || "").toLowerCase().indexOf("sign in") !== -1) {
        window.location.href = options.loginHref || "login.html";
      }
    }
  }

  window.KazixDashboard = {
    hydrateDashboard: hydrateDashboard,
  };
})();
