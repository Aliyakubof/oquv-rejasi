/**
 * Real-time UI synchronization for O'quv Reja Platformasi.
 * Watches /jonli-holat/ and updates [data-jonli] DOM regions in-place
 * whenever database state changes, without disrupting active popovers,
 * search inputs, open panels, or Alpine state.
 */
(() => {
  const INTERVAL_MS = 8000;
  let joriyVersiya = null;
  let sorovKetmoqda = false;

  function blokBandmi(el) {
    const globalModal = document.getElementById("app-global-modal");
    if (globalModal && !globalModal.classList.contains("is-hidden")) {
      return true;
    }
    if (document.querySelector(".table-modal-backdrop")) {
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
      if (p.offsetParent !== null) return true;
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
    if (!javob.ok) return true;

    const matn = await javob.text();
    const doc = new DOMParser().parseFromString(matn, "text/html");
    let hammasiYangilandi = true;
    let ozgarishBor = false;

    for (const el of bloklar) {
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
      el.innerHTML = yangiEl.innerHTML;
      if (window.htmx) window.htmx.process(el);
      if (window.applyDynamicStyles) window.applyDynamicStyles(el);
      ozgarishBor = true;
    }

    if (ozgarishBor) indikatorniYiltirat();
    return hammasiYangilandi;
  }

  async function tekshir() {
    if (sorovKetmoqda || document.visibilityState !== "visible") return;
    if (!document.querySelector("[data-jonli]")) return;
    sorovKetmoqda = true;
    try {
      const javob = await fetch("/jonli-holat/", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!javob.ok) return;
      const data = await javob.json();
      if (!joriyVersiya) {
        joriyVersiya = data.versiya;
      } else if (data.versiya !== joriyVersiya) {
        const tugadi = await sahifaniYangila();
        if (tugadi) joriyVersiya = data.versiya;
      }
    } catch (_) {
      // Tarmoq uzilishi bo'lsa keyingi siklda davom etadi.
    } finally {
      sorovKetmoqda = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    tekshir();
    setInterval(tekshir, INTERVAL_MS);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") tekshir();
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

