/*
 * Booking Monitor — lightweight client-side JP/EN i18n (SOT-954).
 *
 * The app is server-rendered Jinja2 with no shared layout, so this single shared
 * script provides a JP|EN toggle for every page. It works by snapshotting each
 * text node's original (Japanese) value and, when English is selected, swapping
 * the value for a dictionary translation of the UI-shell strings. Default is
 * Japanese (the server-rendered text), so there is no first-paint mismatch.
 *
 * Only static UI chrome is translated (nav, headings, buttons, table headers,
 * labels, empty states, badges). Dynamic data (store names, dates, error text
 * from the backend) is intentionally left untouched.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "bm.lang";

  // Japanese (normalized) -> English. Keys are matched after trimming and
  // collapsing internal whitespace to single spaces (see norm()).
  var DICT = {
    // --- Nav / shared chrome ---
    "ダッシュボード": "Dashboard",
    "カレンダー": "Calendar",
    "監視履歴": "Monitor history",
    "通知履歴": "Notification history",
    "設定確認": "Settings",
    "ログアウト": "Logout",
    "エラー:": "Error:",
    "設定警告:": "Config warning:",

    // --- Status (dashboard) page ---
    "監視対象数": "Targets",
    "通知有効数": "Notify enabled",
    "空きあり": "Available",
    "満席": "Full",
    "取得失敗": "Fetch failed",
    "未確認": "Unchecked",
    "最終チェック:": "Last check:",
    "最終通知:": "Last notify:",
    "未実行": "Not run",
    "履歴なし": "No history",
    "手動実行": "Run now",
    "実行中...": "Running...",
    "監視対象一覧": "Monitored targets",
    "監視対象が設定されていません。": "No monitoring targets configured.",
    "店舗名": "Store",
    "種別": "Type",
    "曜日": "Days",
    "時刻": "Time",
    "大人": "Adults",
    "子ども": "Children",
    "通知": "Notify",
    "状態": "Status",
    "最終確認": "Last checked",
    "エラー": "Error",
    "空きあり 通知済": "Available (notified)",
    "空き状況グリッド（日付 × 時刻）": "Availability grid (date × time)",
    "エラー詳細": "Error details",
    "不明/未取得": "Unknown/not fetched",

    // --- Calendar page ---
    "空き状況カレンダー": "Availability calendar",
    "日 × 時間 空き状況（全対象を集約）": "Day × time availability (all targets aggregated)",
    "空きあり（数字=空き対象数）": "Available (number = available targets)",
    "不明/対象なし": "Unknown/no target",
    "日×時間レンジ監視（date_range / time_range）が設定された対象がまだありません。 設定確認ページで対象に範囲条件を追加すると、ここにカレンダーが表示されます。":
      "No target has day×time range monitoring (date_range / time_range) configured yet. Add a range condition to a target on the Settings page and the calendar will appear here.",

    // --- Monitor history page ---
    "チェック日時": "Checked at",
    "対象店舗": "Target store",
    "結果": "Result",
    "状態変化": "State change",
    "サマリー": "Summary",
    "あり": "Yes",
    "通知済": "Notified",
    "まだ監視履歴がありません。手動実行または自動スケジュールが実行されると記録されます。":
      "No monitor history yet. Records appear after a manual run or a scheduled run.",

    // --- Notification history page ---
    "通知日時": "Notified at",
    "エラー概要": "Error summary",
    "通知スキップ": "Skipped",
    "送信成功": "Sent",
    "送信失敗": "Send failed",
    "Discord Webhook URLなどの秘密情報はこの画面に表示されません。":
      "Secrets such as the Discord Webhook URL are not shown on this screen.",
    "まだ通知履歴がありません。": "No notification history yet.",

    // --- Config (settings) page ---
    "通知設定": "Notification settings",
    "通知タイプ": "Notification type",
    "Webhook 環境変数名": "Webhook env var name",
    "（値は非表示）": "(value hidden)",
    "スヌーズ（一時停止）": "Snooze (pause)",
    "一時停止中": "Paused",
    "稼働中": "Active",
    "(無効)": "(disabled)",
    "汎用 HTTP": "Generic HTTP",
    "通知OFF": "Notify OFF",
    "チェック間隔": "Check interval",
    "対象曜日": "Target days",
    "指定なし": "Not set",
    "対象時刻": "Target time",
    "3歳以下の子ども": "Children under 3",
    "種別メモ": "Type note",
    "TableCheck サイト — Playwright でブラウザ操作を行います":
      "TableCheck site — browser automation via Playwright",
    "汎用 HTTP キーワードチェック": "Generic HTTP keyword check",
    "空きありキーワード": "Available keywords",
    "満席キーワード": "Full keywords",
    "監視対象 (": "Monitored targets (",
    "通知チャネル (": "Notification channels (",
    " 件)": " items)",

    // --- Login page ---
    "ログインして監視を続ける": "Log in to continue monitoring",
    "メールアドレス": "Email",
    "パスワード": "Password",
    "ログイン": "Login",
    "ログイン中...": "Logging in...",
    "メールアドレスまたはパスワードが正しくありません": "Incorrect email or password",
    "ログインに失敗しました": "Login failed"
  };

  // Translatable placeholder attributes.
  var PLACEHOLDER_DICT = {
    "店舗名で絞り込み...": "Filter by store..."
  };

  // document.title per page.
  var TITLE_DICT = {
    "ダッシュボード - Booking Monitor": "Dashboard - Booking Monitor",
    "カレンダー - Booking Monitor": "Calendar - Booking Monitor",
    "監視履歴 - Booking Monitor": "Monitor history - Booking Monitor",
    "通知履歴 - Booking Monitor": "Notification history - Booking Monitor",
    "設定確認 - Booking Monitor": "Settings - Booking Monitor",
    "ログイン - Booking Monitor": "Login - Booking Monitor"
  };

  function norm(s) {
    return s.trim().replace(/\s+/g, " ");
  }

  var origTitle = null;
  var applying = false;

  function translateNode(node, toEn) {
    var parent = node.parentNode;
    if (parent && (parent.nodeName === "SCRIPT" || parent.nodeName === "STYLE")) return;
    if (parent && parent.closest && parent.closest("[data-bm-i18n-toggle]")) return;
    if (node.__bmOrig === undefined) {
      if (!node.nodeValue || !node.nodeValue.trim()) return; // skip pure whitespace
      node.__bmOrig = node.nodeValue;
    }
    var orig = node.__bmOrig;
    if (!toEn) {
      node.nodeValue = orig;
      return;
    }
    var en = DICT[norm(orig)];
    if (en === undefined) return;
    var lead = orig.match(/^\s*/)[0];
    var trail = orig.match(/\s*$/)[0];
    node.nodeValue = lead + en + trail;
  }

  function walkText(root, toEn) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var n;
    var batch = [];
    while ((n = walker.nextNode())) batch.push(n);
    batch.forEach(function (node) { translateNode(node, toEn); });
  }

  function translateAttrs(toEn) {
    document.querySelectorAll("[placeholder]").forEach(function (el) {
      if (el.__bmOrigPlaceholder === undefined) {
        el.__bmOrigPlaceholder = el.getAttribute("placeholder") || "";
      }
      var orig = el.__bmOrigPlaceholder;
      if (!toEn) { el.setAttribute("placeholder", orig); return; }
      var en = PLACEHOLDER_DICT[norm(orig)];
      if (en !== undefined) el.setAttribute("placeholder", en);
    });
  }

  function applyLang(lang) {
    var toEn = lang === "en";
    applying = true;
    try {
      walkText(document.body, toEn);
      translateAttrs(toEn);
      if (origTitle === null) origTitle = document.title;
      if (toEn && TITLE_DICT[origTitle]) {
        document.title = TITLE_DICT[origTitle];
      } else {
        document.title = origTitle;
      }
      document.documentElement.lang = toEn ? "en" : "ja";
    } finally {
      applying = false;
    }
    updateToggle(lang);
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) { /* ignore */ }
  }

  var toggleEl = null;

  function updateToggle(lang) {
    if (!toggleEl) return;
    toggleEl.querySelectorAll("button").forEach(function (b) {
      var active = b.getAttribute("data-lang") === lang;
      b.style.background = active ? "rgba(255,255,255,0.95)" : "transparent";
      b.style.color = active ? "#1f2d3d" : "rgba(255,255,255,0.9)";
      b.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function buildToggle() {
    var wrap = document.createElement("div");
    wrap.setAttribute("data-bm-i18n-toggle", "");
    wrap.style.cssText =
      "display:inline-flex;border:1px solid rgba(255,255,255,0.5);border-radius:6px;" +
      "overflow:hidden;flex-shrink:0;";
    ["ja", "en"].forEach(function (lang) {
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("data-lang", lang);
      b.textContent = lang === "ja" ? "JP" : "EN";
      b.style.cssText =
        "border:none;background:transparent;color:rgba(255,255,255,0.9);" +
        "padding:0.25rem 0.6rem;font-size:0.8rem;font-weight:600;cursor:pointer;line-height:1;";
      b.addEventListener("click", function () { applyLang(lang); });
      wrap.appendChild(b);
    });
    return wrap;
  }

  function mountToggle() {
    toggleEl = buildToggle();
    var nav = document.querySelector("nav");
    if (nav) {
      var form = nav.querySelector("form");
      if (form) {
        nav.insertBefore(toggleEl, form);
      } else {
        nav.appendChild(toggleEl);
      }
    } else {
      // No nav (e.g. login page): fixed top-right, dark pill so it stays visible.
      toggleEl.style.position = "fixed";
      toggleEl.style.top = "0.8rem";
      toggleEl.style.right = "0.8rem";
      toggleEl.style.zIndex = "1000";
      toggleEl.style.background = "#1f2d3d";
      toggleEl.style.borderColor = "rgba(0,0,0,0.2)";
      document.body.appendChild(toggleEl);
    }
  }

  function currentLang() {
    var saved;
    try { saved = localStorage.getItem(STORAGE_KEY); } catch (e) { saved = null; }
    return saved === "en" ? "en" : "ja";
  }

  function init() {
    mountToggle();
    var lang = currentLang();
    applyLang(lang);

    // Re-translate dynamically inserted static labels when English is active.
    var observer = new MutationObserver(function (mutations) {
      if (applying) return;
      if (currentLang() !== "en") return;
      var touched = false;
      mutations.forEach(function (m) {
        if (m.addedNodes && m.addedNodes.length) touched = true;
      });
      if (!touched) return;
      applying = true;
      try {
        walkText(document.body, true);
        translateAttrs(true);
      } finally {
        applying = false;
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
