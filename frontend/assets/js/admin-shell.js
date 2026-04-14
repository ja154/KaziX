(function () {
  var NAV_SECTIONS = [
    {
      title: "Overview",
      links: [{ key: "dashboard", label: "Dashboard", href: "admin-dashboard.html", icon: "📊" }]
    },
    {
      title: "Operations",
      links: [
        { key: "disputes", label: "Disputes", href: "admin-disputes.html", icon: "⚖️", badge: "18" },
        { key: "payments", label: "Payments", href: "admin-payments.html", icon: "💳" },
        { key: "escrow-holds", label: "Escrow Holds", href: "admin-payments.html#escrow-holds", icon: "🔒", badge: "12" }
      ]
    },
    {
      title: "Trust",
      links: [
        { key: "verifications", label: "KYC Verifications", href: "admin-verifications.html", icon: "🪪", badge: "23" },
        { key: "users", label: "Users", href: "admin-users.html", icon: "👥" }
      ]
    },
    {
      title: "System",
      links: [
        { key: "settings", label: "Settings", href: "admin-settings.html", icon: "⚙️" },
        { key: "audit-log", label: "Audit Log", href: "admin-audit-log.html", icon: "🧾" }
      ]
    }
  ];

  function buildTopnav() {
    var nav = document.createElement('nav');
    nav.className = 'topnav admin-topnav';
    nav.innerHTML = ''
      + '<a href="admin-dashboard.html" class="logo">Kazi<span>X</span></a>'
      + '<div class="topnav-right">'
      + '  <span class="admin-badge">Admin</span>'
      + '  <div class="user-menu-container">'
      + '    <div class="user-chip" id="userChipToggle"><div class="user-avatar">AD</div><span class="user-name">Admin Desk</span></div>'
      + '    <div class="user-menu-dropdown" id="userMenuDropdown">'
      + '      <div class="user-menu-header">'
      + '        <div class="user-menu-name" id="userMenuName">Admin Desk</div>'
      + '        <div class="user-menu-status">'
      + '          <span class="status-indicator"></span>'
      + '          <span>Logged in</span>'
      + '        </div>'
      + '      </div>'
      + '      <div class="user-menu-body">'
      + '        <a href="admin-settings.html" class="user-menu-item">Admin Settings</a>'
      + '        <button class="user-menu-item logout" onclick="window.KazixProfile ? window.KazixProfile.logout() : window.location.href=\'login.html\'">Logout</button>'
      + '      </div>'
      + '    </div>'
      + '  </div>'
      + '</div>';
    return nav;
  }

  function buildLink(item) {
    var badge = item.badge ? '<span class="ni-badge">' + item.badge + '</span>' : '';
    return ''
      + '<a class="nav-item" data-admin-nav="' + item.key + '" href="' + item.href + '">'
      + '<span class="ni-icon">' + item.icon + '</span>'
      + item.label
      + badge
      + '</a>';
  }

  function buildSidebar(activeKey) {
    var sidebar = document.createElement('aside');
    sidebar.className = 'admin-sidebar';
    sidebar.innerHTML = NAV_SECTIONS.map(function (section) {
      return ''
        + '<div class="sidebar-section">' + section.title + '</div>'
        + section.links.map(buildLink).join('');
    }).join('');

    var activeLink = sidebar.querySelector('[data-admin-nav="' + activeKey + '"]');
    if (activeLink) {
      activeLink.classList.add('active');
    }

    return sidebar;
  }

  function getActiveKey() {
    var activeKey = document.body.getAttribute('data-admin-active') || 'dashboard';
    if (window.location.hash === '#escrow-holds') {
      return 'escrow-holds';
    }
    return activeKey;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var main = document.querySelector('[data-admin-main]');
    if (!main) {
      return;
    }

    document.body.classList.add('app', 'admin-portal');
    var activeKey = getActiveKey();

    if (!document.querySelector('.admin-topnav')) {
      var nav = buildTopnav();
      document.body.insertBefore(nav, document.body.firstChild);
    }

    var shell = document.createElement('div');
    shell.className = 'app-shell admin-shell';

    var sidebar = buildSidebar(activeKey);
    shell.appendChild(sidebar);
    shell.appendChild(main);

    var existingShell = document.querySelector('.admin-shell') || document.querySelector('.app-shell');
    if (existingShell) {
      existingShell.replaceWith(shell);
    } else {
      var navEl = document.querySelector('.admin-topnav') || document.querySelector('.topnav');
      if (navEl) {
        document.body.insertBefore(shell, navEl.nextSibling);
      } else {
        document.body.insertBefore(shell, document.body.firstChild);
      }
    }

    // Setup user menu dropdown toggle for admin topnav
    setupUserMenuToggle();
  });

  function setupUserMenuToggle() {
    var userChipToggle = document.getElementById("userChipToggle");
    var userMenuDropdown = document.getElementById("userMenuDropdown");
    
    if (!userChipToggle || !userMenuDropdown) return;

    // Remove existing listeners to prevent duplicates
    var newUserChipToggle = userChipToggle.cloneNode(true);
    userChipToggle.parentNode.replaceChild(newUserChipToggle, userChipToggle);
    userChipToggle = newUserChipToggle;

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
})();
