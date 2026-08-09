/*
 * Mobile scroll UI for the ttyd web terminal (injected into ttyd's index.html
 * at build time, see Dockerfile).
 *
 * Why this exists: xterm.js 5.3 (bundled in ttyd 1.7.7) does implement touch
 * scrolling, but bindMouse() bails out of both touch handlers as soon as the
 * TUI turns on mouse tracking:
 *
 *     el.addEventListener('touchstart', ev => {
 *       if (this.coreMouseService.areMouseEventsActive) return;   // <-- here
 *       this.viewport.handleTouchStart(ev);
 *     })
 *
 * tmux does exactly that in tmux_scroll_mode: tmux ("set -g mouse on"), and a
 * TUI may do it on its own — so on phones/tablets a swipe scrolls nothing.
 *
 * Approach: take over the gesture in the capture phase, so xterm's own touch
 * handlers never see it (no double scrolling in browser mode), then hand the
 * delta back to xterm as a synthetic wheel event. xterm then picks the right
 * behaviour per mode by itself: scroll the viewport in browser mode, emit SGR
 * wheel reports to tmux in tmux mode. Plus two on-screen buttons, because a
 * page-wise jump is hard to hit with a thumb.
 *
 * Touch devices only — desktop browsers are left completely untouched.
 */
(function () {
  'use strict';

  var isTouch =
    (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) ||
    'ontouchstart' in window ||
    navigator.maxTouchPoints > 0;
  if (!isTouch) return;

  var TAP_SLOP = 6;        // px of movement before a touch counts as a scroll
  var MAX_DELTA = 2000;    // px cap per wheel event, keeps tmux mode from
                           // being flooded with wheel reports

  function screenEl() {
    return document.querySelector('.xterm-screen') || document.querySelector('.xterm');
  }

  // Query lazily on every use: ttyd disposes and recreates the terminal on
  // reconnect, so a cached reference would go stale.
  function scrollBy(px) {
    var el = screenEl();
    if (!el || !px) return;
    if (px > MAX_DELTA) px = MAX_DELTA;
    if (px < -MAX_DELTA) px = -MAX_DELTA;
    el.dispatchEvent(
      new WheelEvent('wheel', {
        deltaX: 0,
        deltaY: px,
        deltaMode: 0, // DOM_DELTA_PIXEL — xterm maps this 1:1 to viewport pixels
        bubbles: true,
        cancelable: true
      })
    );
  }

  function pageHeight() {
    var vp = document.querySelector('.xterm-viewport');
    var h = (vp && vp.clientHeight) || window.innerHeight || 400;
    return Math.round(h * 0.8);
  }

  /* --- swipe ------------------------------------------------------------ */

  var lastY = null;
  var moved = 0;

  function inTerminal(target) {
    return !!(target && target.closest && target.closest('.xterm'));
  }

  document.addEventListener(
    'touchstart',
    function (ev) {
      // Multi-touch stays untouched so pinch-zoom keeps working
      if (ev.touches.length !== 1 || !inTerminal(ev.target)) {
        lastY = null;
        return;
      }
      lastY = ev.touches[0].clientY;
      moved = 0;
      // No preventDefault: the synthesized mousedown/click still has to reach
      // xterm so tapping focuses the terminal and opens the soft keyboard.
      ev.stopPropagation();
    },
    { capture: true, passive: false }
  );

  document.addEventListener(
    'touchmove',
    function (ev) {
      if (lastY === null || ev.touches.length !== 1) return;
      var y = ev.touches[0].clientY;
      var delta = lastY - y; // finger up => positive => scroll down
      lastY = y;
      moved += Math.abs(delta);
      if (moved < TAP_SLOP) return;
      ev.stopPropagation();
      ev.preventDefault(); // suppress native viewport panning and WebView pull-to-refresh
      scrollBy(delta);
    },
    { capture: true, passive: false }
  );

  document.addEventListener(
    'touchend',
    function () {
      lastY = null;
    },
    { capture: true, passive: true }
  );

  /* --- on-screen buttons ------------------------------------------------ */

  function mountButtons() {
    if (document.getElementById('cc-mscroll')) return;

    var css = document.createElement('style');
    css.textContent =
      '#cc-mscroll{position:fixed;right:10px;bottom:14px;z-index:2147482000;' +
      'display:flex;flex-direction:column;gap:6px;touch-action:manipulation}' +
      '#cc-mscroll button{width:44px;height:44px;border:0;border-radius:22px;' +
      'font-size:20px;line-height:44px;padding:0;cursor:pointer;opacity:.38;' +
      'background:rgba(127,127,127,.55);color:#fff;-webkit-tap-highlight-color:transparent}' +
      '#cc-mscroll button:active{opacity:.9}';
    document.head.appendChild(css);

    var box = document.createElement('div');
    box.id = 'cc-mscroll';

    [['▲', -1], ['▼', 1]].forEach(function (spec) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = spec[0];
      b.setAttribute('aria-label', spec[1] < 0 ? 'Scroll up' : 'Scroll down');
      // Keep focus (and the soft keyboard) on the terminal
      b.addEventListener('pointerdown', function (ev) { ev.preventDefault(); });
      b.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
      b.addEventListener('click', function (ev) {
        ev.preventDefault();
        scrollBy(spec[1] * pageHeight());
      });
      box.appendChild(b);
    });

    document.body.appendChild(box);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountButtons);
  } else {
    mountButtons();
  }
})();
