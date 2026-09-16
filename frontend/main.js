/* Syndra landing: the only script on the page. Vanilla, no dependencies.
   Everything here is an enhancement: with JS disabled the page is fully readable
   (English copy, final metric figures, native <details> nav and FAQ). */
(function () {
  'use strict';

  var root = document.documentElement;

  /* ---------- 1. Language switch (EN default, ES opt-in) ---------- */
  var STORE = 'syndra.lang';
  function setLang(lang) {
    root.setAttribute('data-lang', lang);
    root.setAttribute('lang', lang);
    var btns = document.querySelectorAll('[data-lang-btn]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute('aria-pressed', String(btns[i].getAttribute('data-lang-btn') === lang));
    }
    try { localStorage.setItem(STORE, lang); } catch (e) {}
  }
  /* English is the default for everyone, unconditionally. Browser-locale
     auto-switching was removed on purpose: the primary audience is B2B
     engineering buyers and a TFG tribunal, the served copy is English, and
     an es-* browser silently flipping the page to Spanish meant the author
     never saw what a visitor sees. Spanish is opt-in via the EN/ES switch
     and only then remembered. */
  var stored = null;
  try { stored = localStorage.getItem(STORE); } catch (e) {}
  if (stored === 'es' || stored === 'en') setLang(stored);

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('[data-lang-btn]') : null;
    if (btn) setLang(btn.getAttribute('data-lang-btn'));
  });

  /* ---------- 2. Metric count-up ----------
     The final figure is in the HTML, so it is correct before and without JS.
     Skipped entirely for users who ask for reduced motion. */
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var figs = document.querySelectorAll('[data-count]');
  if (!reduced && figs.length && 'IntersectionObserver' in window && window.requestAnimationFrame) {
    var animate = function (el) {
      if (el.dataset.done) return;
      el.dataset.done = '1';
      var target = Number(el.getAttribute('data-count')) || 0;
      var suffix = el.getAttribute('data-suffix') || '';
      var t0 = performance.now(), dur = 1100;
      var tick = function (now) {
        var p = Math.min(1, (now - t0) / dur);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * eased).toLocaleString('en-US') + suffix;
        if (p < 1) requestAnimationFrame(tick);
        else el.textContent = target.toLocaleString('en-US') + suffix;
      };
      requestAnimationFrame(tick);
    };
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) animate(e.target); });
    }, { threshold: 0.4 });
    for (var j = 0; j < figs.length; j++) io.observe(figs[j]);
  }

  /* ---------- 3. Access form: inline validation ---------- */
  var form = document.querySelector('form.access');
  var err = document.querySelector('[data-form-error]');
  if (form && err) {
    var MSG = {
      en: { email: 'Enter a valid work email address.', name: 'Tell us your name.' },
      es: { email: 'Introduce un email de trabajo válido.', name: 'Indícanos tu nombre.' }
    };
    form.addEventListener('submit', function (ev) {
      var lang = root.getAttribute('data-lang') === 'es' ? 'es' : 'en';
      var name = form.querySelector('input[name="name"]');
      var email = form.querySelector('input[name="email"]');
      var problem = null, focusOn = null;
      if (!name.value.trim()) { problem = MSG[lang].name; focusOn = name; }
      else if (!/^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$/.test(email.value)) { problem = MSG[lang].email; focusOn = email; }
      if (problem) {
        ev.preventDefault();
        err.textContent = problem;
        err.setAttribute('data-show', '');
        focusOn.focus();
      } else {
        err.removeAttribute('data-show');
      }
    });
  }

  /* ---------- 4. Close the mobile menu after a jump ---------- */
  var mob = document.querySelector('.mobnav');
  if (mob) {
    mob.addEventListener('click', function (ev) {
      if (ev.target.tagName === 'A') mob.removeAttribute('open');
    });
  }
})();
