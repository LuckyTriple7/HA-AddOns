// Öffentliche Angebots-Seite: rendert nur die KI-Texte aus data-Attributen —
// die Seite selbst kommt fertig vom Server. Kein Fetch, keine API, kein State.
// Content-Security-Policy erlaubt keine Inline-Scripts, deshalb liegen die
// Rohtexte in data-md/data-t und werden hier durch aimd.js geschickt.
(function(){
  document.querySelectorAll('[data-md]').forEach(function(el){
    el.innerHTML = window.aiMdLite(el.dataset.md || '');
  });
  // Kurztexte (Klima-Hinweis, Reiseführer-Punkte): nur Zitat-Links + Fettdruck,
  // kein Block-Markdown — sonst stünde in jeder Tabellenzelle ein <p>.
  document.querySelectorAll('[data-t]').forEach(function(el){
    el.innerHTML = window.aiInline(window.aiEsc(el.dataset.t || ''));
  });
})();
