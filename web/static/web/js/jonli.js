/**
 * Real-time UI synchronization for O'quv Reja Platformasi.
 * Watches /jonli-holat/ and updates [data-jonli] DOM regions in-place
 * whenever database state changes, without disrupting active popovers,
 * search inputs, open panels, or Alpine state.
 */
(() => {
  const BOSH_INTERVAL_MS = 8000;
  const MAX_INTERVAL_MS = 60000;
  let joriyIntervalMs = BOSH_INTERVAL_MS;
  let joriyVersiya = null;
  let sorovKetmoqda = false;
  let timerId = null;

  function kirishManzili() {
    return (
      document.querySelector('meta[name="login-url"]')?.getAttribute("content") ||
      "/kirish/"
    );
  }

  function qaytaRejalashtir(kechikishMs = joriyIntervalMs) {
    if (timerId) clearTimeout(timerId);
    timerId = setTimeout(tekshir, kechikishMs);
  }

  function skrollniSaqlash(el) {
    const konteynerlar = el.classList.contains("table-wrap")
      ? [el]
      : Array.from(el.querySelectorAll(".table-wrap"));
    return konteynerlar.map((k) => [k.scrollTop, k.scrollLeft]);
  }

  function skrollniTiklash(el, holatlar) {
    const konteynerlar = el.classList.contains("table-wrap")
      ? [el]
      : Array.from(el.querySelectorAll(".table-wrap"));
    konteynerlar.forEach((k, idx) => {
      if (!holatlar[idx]) return;
      k.scrollTop = holatlar[idx][0];
      k.scrollLeft = holatlar[idx][1];
    });
  }

  function blokBandmi(el) {
    const globalModal = document.getElementById("app-global-modal");
    if (globalModal && !globalModal.classList.contains("is-hidden")) {
      return true;
    }
    if (document.querySelector(".table-modal-backdrop")) {
      return true;
    }
    if (el.querySelector('[data-ozgardi="1"]')) {
      return true;
    }
    const aktiv = document.activeElement;
    if (
      aktiv &&
      ["INPUT", "TEXTAREA", "SELECT"].includes(aktiv.tagName) &&
      (el.contains(aktiv) || aktiv.closest(".search, .topbar, .controls"))
    ) {
      return true;
    }
    const popoverlar = el.querySelectorAll(".popover, .action-menu");
    for (const p of popoverlar) {
      const st = window.getComputedStyle(p);
      if (st.display !== "none" && st.visibility !== "hidden") return true;
    }
    if (el.querySelector("details[open]")) return true;
    const panellar = el.querySelectorAll('[id^="panel-"], [id^="dastur-panel-"]');
    for (const panel of panellar) {
      if (panel.id.startsWith("panel-yuk-")) continue;
      if (panel.innerHTML.trim() !== "") return true;
    }
    return false;
  }

  function indikatorniYiltirat() {
    const ind = document.getElementById("jonli-indikator");
    if (!ind) return;
    ind.classList.add("puls");
    setTimeout(() => ind.classList.remove("puls"), 900);
  }

  async function sahifaniYangila() {
    const bloklar = document.querySelectorAll("[data-jonli]");
    if (!bloklar.length) return true;

    const javob = await fetch(window.location.href, {
      headers: { "X-Requested-With": "JonliSync" },
      credentials: "same-origin",
      cache: "no-store",
    });
    if (javob.status === 401) {
      if (timerId) clearTimeout(timerId);
      window.location.assign(kirishManzili());
      return true;
    }
    if (!javob.ok) {
      joriyIntervalMs = Math.min(joriyIntervalMs * 2, MAX_INTERVAL_MS);
      return false;
    }

    const matn = await javob.text();
    const doc = new DOMParser().parseFromString(matn, "text/html");
    let hammasiYangilandi = true;
    let ozgarishBor = false;

    for (const el of bloklar) {
      if (el.parentElement && el.parentElement.closest("[data-jonli]")) {
        continue;
      }
      const kalit = el.getAttribute("data-jonli");
      const yangiEl = doc.querySelector(`[data-jonli="${kalit}"]`);
      if (!yangiEl) {
        continue;
      }
      if (el.innerHTML === yangiEl.innerHTML) continue;
      if (blokBandmi(el)) {
        hammasiYangilandi = false;
        continue;
      }
      const skroll = skrollniSaqlash(el);
      el.innerHTML = yangiEl.innerHTML;
      skrollniTiklash(el, skroll);
      if (window.htmx) window.htmx.process(el);
      if (window.applyDynamicStyles) window.applyDynamicStyles(el);
      ozgarishBor = true;
    }

    if (ozgarishBor) indikatorniYiltirat();
    return hammasiYangilandi;
  }

  async function tekshir() {
    if (sorovKetmoqda || document.visibilityState !== "visible") {
      qaytaRejalashtir();
      return;
    }
    if (!document.querySelector("[data-jonli]")) {
      qaytaRejalashtir();
      return;
    }
    sorovKetmoqda = true;
    try {
      const javob = await fetch("/jonli-holat/", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (javob.status === 401) {
        if (timerId) clearTimeout(timerId);
        window.location.assign(kirishManzili());
        return;
      }
      if (!javob.ok) {
        joriyIntervalMs = Math.min(joriyIntervalMs * 2, MAX_INTERVAL_MS);
        return;
      }
      joriyIntervalMs = BOSH_INTERVAL_MS;
      const data = await javob.json();
      if (!joriyVersiya) {
        joriyVersiya = data.versiya;
      } else if (data.versiya !== joriyVersiya) {
        const tugadi = await sahifaniYangila();
        if (tugadi) joriyVersiya = data.versiya;
      }
    } catch (_) {
      joriyIntervalMs = Math.min(joriyIntervalMs * 2, MAX_INTERVAL_MS);
    } finally {
      sorovKetmoqda = false;
      qaytaRejalashtir();
    }
  }

  function ozgarishniBelgilash(event) {
    const kirit = event.target;
    if (!kirit || !kirit.matches("input, textarea, select")) return;
    if (kirit.closest('[data-jonli] form[method="post"], [data-jonli] form[hx-post]')) {
      kirit.dataset.ozgardi = "1";
    }
  }

  function belgilarniTozalash(scope) {
    (scope || document).querySelectorAll('[data-ozgardi="1"]').forEach((el) => {
      delete el.dataset.ozgardi;
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    tekshir();
    document.body.addEventListener("input", ozgarishniBelgilash);
    document.body.addEventListener("change", ozgarishniBelgilash);
    document.body.addEventListener("submit", (e) => belgilarniTozalash(e.target));
    document.body.addEventListener("htmx:afterSwap", (e) => belgilarniTozalash(e.target));
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        joriyIntervalMs = BOSH_INTERVAL_MS;
        tekshir();
      }
    });
    window.addEventListener("focus", tekshir);
    document.body.addEventListener("htmx:afterSettle", () => {
      fetch("/jonli-holat/", { credentials: "same-origin", cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (d && d.versiya) joriyVersiya = d.versiya;
        })
        .catch(() => {});
    });
  });
})();

