(function () {
  "use strict";

  var config = window.MoveDefenseMarketingConfig || {};
  var ATTR_KEY = "md_attribution_v1";
  var CONSENT_KEY = "md_consent_v1";
  var CONSENT_VERSION = 1;
  var DEFAULT_TTL_DAYS = 90;
  var analyticsLoaded = false;
  var pilotFormStarted = false;

  var TOUCH_FIELDS = [
    "source",
    "medium",
    "referrer",
    "landing_page",
    "utm_source",
    "utm_medium",
    "utm_campaign"
  ];

  var FORM_FIELDS = TOUCH_FIELDS.reduce(function (fields, field) {
    fields.push("first_" + field);
    fields.push("last_" + field);
    return fields;
  }, []);

  var SEARCH_HOSTS = [
    "google.",
    "bing.com",
    "yahoo.",
    "duckduckgo.com",
    "ecosia.org",
    "brave.com",
    "search.aol.com",
    "ask.com"
  ];

  var AI_REFERRERS = [
    ["chatgpt.com", "chatgpt"],
    ["chat.openai.com", "chatgpt"],
    ["openai.com", "openai"],
    ["perplexity.ai", "perplexity"],
    ["claude.ai", "claude"],
    ["anthropic.com", "anthropic"],
    ["gemini.google.com", "gemini"],
    ["bard.google.com", "gemini"],
    ["copilot.microsoft.com", "copilot"],
    ["phind.com", "phind"],
    ["you.com", "you"]
  ];

  var SENSITIVE_QUERY_KEYS = [
    "email",
    "e-mail",
    "phone",
    "name",
    "first_name",
    "last_name",
    "password",
    "token",
    "code",
    "session",
    "signature",
    "driver",
    "route",
    "load",
    "customer"
  ];

  function nowMs() {
    return Date.now();
  }

  function ttlDays() {
    var n = parseInt(config.attributionTtlDays, 10);
    return Number.isFinite(n) && n > 0 ? n : DEFAULT_TTL_DAYS;
  }

  function expiresAt() {
    return nowMs() + ttlDays() * 24 * 60 * 60 * 1000;
  }

  function hostWithoutWww(host) {
    return String(host || "").toLowerCase().replace(/^www\./, "");
  }

  function isSensitiveKey(key) {
    var normalized = String(key || "").toLowerCase();
    return SENSITIVE_QUERY_KEYS.some(function (sensitive) {
      return normalized === sensitive || normalized.indexOf(sensitive + "_") === 0;
    });
  }

  function publicPath(value) {
    try {
      var url = new URL(value, window.location.origin);
      var params = new URLSearchParams(url.search);
      Array.from(params.keys()).forEach(function (key) {
        if (isSensitiveKey(key)) params.delete(key);
      });
      var search = params.toString();
      return url.pathname + (search ? "?" + search : "");
    } catch (err) {
      return window.location.pathname;
    }
  }

  function publicReferrer(value) {
    if (!value) return "";
    try {
      var url = new URL(value);
      return url.origin + url.pathname;
    } catch (err) {
      return "";
    }
  }

  function params() {
    return new URLSearchParams(window.location.search || "");
  }

  function getParam(name) {
    return params().get(name) || "";
  }

  function referrerHost(referrer) {
    if (!referrer) return "";
    try {
      return hostWithoutWww(new URL(referrer).hostname);
    } catch (err) {
      return "";
    }
  }

  function isSameSite(referrer) {
    var host = referrerHost(referrer);
    return host && host === hostWithoutWww(window.location.hostname);
  }

  function aiSource(host) {
    for (var i = 0; i < AI_REFERRERS.length; i += 1) {
      if (host === AI_REFERRERS[i][0] || host.endsWith("." + AI_REFERRERS[i][0])) {
        return AI_REFERRERS[i][1];
      }
    }
    return "";
  }

  function isSearchHost(host) {
    return SEARCH_HOSTS.some(function (needle) {
      return host.indexOf(needle) !== -1;
    });
  }

  function classifyTouch(referrer, query, existing) {
    var utmSource = query.get("utm_source") || "";
    var utmMedium = query.get("utm_medium") || "";
    var utmCampaign = query.get("utm_campaign") || "";
    var host = referrerHost(referrer);

    if (utmSource || utmMedium || utmCampaign) {
      return {
        source: utmSource || "campaign",
        medium: utmMedium || "campaign",
        referrer: publicReferrer(referrer)
      };
    }

    if (isSameSite(referrer) && existing && existing.last) {
      return {
        source: existing.last.source || "direct",
        medium: existing.last.medium || "none",
        referrer: existing.last.referrer || ""
      };
    }

    if (!host) {
      return { source: "direct", medium: "none", referrer: "" };
    }

    var ai = aiSource(host);
    if (ai) {
      return { source: ai, medium: "ai_referral", referrer: publicReferrer(referrer) };
    }

    if (isSearchHost(host)) {
      return { source: host, medium: "organic_search", referrer: publicReferrer(referrer) };
    }

    return { source: host, medium: "referral", referrer: publicReferrer(referrer) };
  }

  function currentTouch(existing) {
    var query = params();
    var classified = classifyTouch(document.referrer || "", query, existing);
    return {
      source: classified.source || "",
      medium: classified.medium || "",
      referrer: classified.referrer || "",
      landing_page: publicPath(window.location.href),
      utm_source: query.get("utm_source") || "",
      utm_medium: query.get("utm_medium") || "",
      utm_campaign: query.get("utm_campaign") || ""
    };
  }

  function readJson(key) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null;
    }
  }

  function writeJson(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (err) {
      return false;
    }
  }

  function readAttribution() {
    var data = readJson(ATTR_KEY);
    if (!data || !data.expires_at || data.expires_at < nowMs()) return null;
    return data;
  }

  function writePresenceCookie() {
    var secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie = "md_attr_present=1; Max-Age=" + ttlDays() * 24 * 60 * 60 + "; Path=/; SameSite=Lax" + secure;
  }

  function updateAttribution() {
    var existing = readAttribution();
    var touch = currentTouch(existing);
    var data = existing || { first: touch };
    if (!data.first) data.first = touch;
    data.last = touch;
    data.expires_at = expiresAt();
    data.updated_at = new Date().toISOString();
    writeJson(ATTR_KEY, data);
    writePresenceCookie();
    return data;
  }

  function flattenedAttribution() {
    var data = readAttribution() || updateAttribution();
    var flattened = {};
    TOUCH_FIELDS.forEach(function (field) {
      flattened["first_" + field] = data.first && data.first[field] ? data.first[field] : "";
      flattened["last_" + field] = data.last && data.last[field] ? data.last[field] : "";
    });
    return flattened;
  }

  function ensureHiddenFields(form) {
    var holder = form.querySelector("[data-attribution-fields]") || form;
    FORM_FIELDS.forEach(function (name) {
      if (form.querySelector('input[name="' + name + '"]')) return;
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      holder.appendChild(input);
    });
  }

  function populateAttributionFields(form) {
    ensureHiddenFields(form);
    var data = flattenedAttribution();
    FORM_FIELDS.forEach(function (name) {
      var input = form.querySelector('input[name="' + name + '"]');
      if (input) input.value = data[name] || "";
    });
  }

  function readConsent() {
    var consent = readJson(CONSENT_KEY);
    if (!consent || consent.version !== CONSENT_VERSION) return null;
    return {
      necessary: true,
      analytics: consent.analytics === true,
      marketing: consent.marketing === true,
      version: CONSENT_VERSION,
      saved_at: consent.saved_at || ""
    };
  }

  function saveConsent(values) {
    var consent = {
      necessary: true,
      analytics: values.analytics === true,
      marketing: values.marketing === true,
      version: CONSENT_VERSION,
      saved_at: new Date().toISOString()
    };
    writeJson(CONSENT_KEY, consent);
    return consent;
  }

  function analyticsAllowed() {
    var consent = readConsent();
    return consent ? consent.analytics === true : config.analyticsDefault !== false;
  }

  function provider() {
    return String(config.analyticsProvider || "none").toLowerCase();
  }

  function updateGoogleConsent(analyticsGranted) {
    if (provider() !== "ga4" || typeof window.gtag !== "function") return;
    window.gtag("consent", "update", {
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
      analytics_storage: analyticsGranted ? "granted" : "denied"
    });
  }

  function injectScript(src, attrs) {
    if (!src) return null;
    var script = document.createElement("script");
    script.async = true;
    script.defer = true;
    script.src = src;
    Object.keys(attrs || {}).forEach(function (key) {
      script.setAttribute(key, attrs[key]);
    });
    document.head.appendChild(script);
    return script;
  }

  function loadAnalytics() {
    if (analyticsLoaded) return;
    var selected = provider();

    if (selected === "ga4" && config.ga4MeasurementId) {
      window.dataLayer = window.dataLayer || [];
      window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
      updateGoogleConsent(analyticsAllowed());
      injectScript("https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(config.ga4MeasurementId));
      window.gtag("js", new Date());
      window.gtag("config", config.ga4MeasurementId, { send_page_view: false });
      analyticsLoaded = true;
      return;
    }

    if (!analyticsAllowed()) return;

    if (selected === "plausible" && config.plausibleDomain) {
      window.plausible = window.plausible || function () {
        (window.plausible.q = window.plausible.q || []).push(arguments);
      };
      injectScript(config.plausibleSrc || "https://plausible.io/js/script.js", {
        "data-domain": config.plausibleDomain
      });
      analyticsLoaded = true;
      return;
    }

    if (selected === "umami" && config.umamiWebsiteId) {
      injectScript(config.umamiSrc || "https://cloud.umami.is/script.js", {
        "data-website-id": config.umamiWebsiteId
      });
      analyticsLoaded = true;
    }
  }

  function pageProps() {
    var attr = flattenedAttribution();
    return {
      page_path: publicPath(window.location.href),
      first_source: attr.first_source,
      first_medium: attr.first_medium,
      last_source: attr.last_source,
      last_medium: attr.last_medium
    };
  }

  function trackEvent(name, props) {
    if (!analyticsAllowed()) return;
    var selected = provider();
    var cleanProps = Object.assign({ page_path: publicPath(window.location.href) }, props || {});

    if (selected === "ga4" && window.gtag && config.ga4MeasurementId) {
      window.gtag("event", name, cleanProps);
      return;
    }

    if (selected === "plausible" && window.plausible) {
      window.plausible(name, { props: cleanProps });
      return;
    }

    if (selected === "umami" && window.umami && typeof window.umami.track === "function") {
      window.umami.track(name, cleanProps);
    }
  }

  function maybeTrackPricingView() {
    var path = window.location.pathname.toLowerCase();
    if (path.indexOf("pricing") !== -1 || document.querySelector("[data-pricing-page]")) {
      trackEvent("pricing_page_view", pageProps());
    }
  }

  function formPayload(form) {
    populateAttributionFields(form);
    var payload = [];
    Array.from(new FormData(form).entries()).forEach(function (entry) {
      var key = entry[0];
      var value = String(entry[1] || "").trim();
      if (!value) return;
      payload.push(key + ": " + value);
    });
    return payload.join("\n");
  }

  function submitMailtoForm(form, eventName) {
    var to = form.getAttribute("data-md-mailto") || "bibbstechnology@gmail.com";
    var subject = form.getAttribute("data-md-subject") || "MoveDefense request";
    var status = form.querySelector("[data-form-status]");
    var body = formPayload(form);
    trackEvent(eventName, pageProps());
    if (status) status.textContent = "Opening your email app with the request and attribution attached.";
    window.location.href = "mailto:" + encodeURIComponent(to) +
      "?subject=" + encodeURIComponent(subject) +
      "&body=" + encodeURIComponent(body);
  }

  function wireForms() {
    document.querySelectorAll("form[data-md-form]").forEach(function (form) {
      populateAttributionFields(form);

      if (form.getAttribute("data-md-form") === "pilot") {
        form.addEventListener("focusin", function () {
          if (pilotFormStarted) return;
          pilotFormStarted = true;
          trackEvent("pilot_form_start", pageProps());
        });
      }

      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var formType = form.getAttribute("data-md-form");
        submitMailtoForm(form, formType === "contact" ? "contact_form_submit" : "pilot_form_submit");
      });
    });
  }

  function wireCtas() {
    document.querySelectorAll("[data-track-cta]").forEach(function (el) {
      el.addEventListener("click", function () {
        trackEvent("CTA_click", {
          cta_id: el.getAttribute("data-track-cta") || "",
          cta_text: (el.textContent || "").trim().slice(0, 80)
        });
      });
    });
  }

  function wireConsentBanner() {
    var banner = document.getElementById("cookie-consent");
    if (!banner) return;
    var consent = readConsent();
    var analytics = document.getElementById("consent-analytics");
    var marketing = document.getElementById("consent-marketing");
    if (analytics) analytics.checked = consent ? consent.analytics : config.analyticsDefault !== false;
    if (marketing) marketing.checked = consent ? consent.marketing : false;

    function persist(values) {
      saveConsent(values);
      updateGoogleConsent(values.analytics === true);
      banner.classList.remove("show");
      loadAnalytics();
      trackEvent("page_view", pageProps());
      maybeTrackPricingView();
    }

    var decline = banner.querySelector("[data-consent-decline]");
    var save = banner.querySelector("[data-consent-save]");
    var prefLink = document.getElementById("open-preferences");

    if (prefLink) {
      prefLink.addEventListener("click", function (e) {
        e.preventDefault();
        banner.classList.add("show");
      });
    }

    if (decline) decline.addEventListener("click", function () {
      persist({ analytics: false, marketing: false });
    });
    if (save) save.addEventListener("click", function () {
      persist({
        analytics: analytics ? analytics.checked : false,
        marketing: marketing ? marketing.checked : false
      });
    });
  }

  function init() {
    updateAttribution();
    wireForms();
    wireCtas();
    wireConsentBanner();
    loadAnalytics();
    trackEvent("page_view", pageProps());
    maybeTrackPricingView();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
