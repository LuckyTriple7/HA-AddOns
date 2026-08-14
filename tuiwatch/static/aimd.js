// Mini-Markdown-Renderer für KI-Texte (Fazit, Vergleich, Reiseberater,
// Reiseführer). Ausgelagert aus app.js, damit die öffentliche Angebots-Seite
// (templates/share.html) denselben Renderer nutzt statt einer zweiten,
// driftenden Kopie — sie lädt app.js bewusst nicht.
// Stellt window.aiMdLite / window.aiInline bereit.
(function(){
  function escHtml(s){ return (s||'').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
  // [n](url) -> anklickbare Zitat-Nummer (Perplexity-Quellenangaben, siehe
  // ai_client.py::_perplexity_linkify_citations); läuft vor **bold**, damit ein
  // Fettdruck rund um eine Zitat-Klammer die Link-Erkennung nicht stört.
  function aiInline(s){
    // Reihenfolge zählt: zuerst die NACKTEN Marker (die ohne URL) abfangen, sonst
    // träfe das zweite Muster gleich wieder die Zahl innerhalb des eben gebauten
    // <a>-Elements und legte die Ausgegraut-Optik über einen funktionierenden Link.
    // Nackt bleiben sie, wenn die KI mehr Quellen durchnummeriert hat, als sie in
    // der Antwort mitliefert (Perplexity bei vielen Suchanfragen) — dann sind sie
    // eben kein Link, sollen aber auch nicht wie kaputter Text dastehen.
    s = s.replace(/\[(\d+)\](?!\()/g,
      '<span class="ai-cite-dead" title="Quellenangabe ohne Link — die KI hat dazu keine URL mitgeliefert">[$1]</span>');
    s = s.replace(/\[(\d+)\]\((https?:\/\/[^\s")]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener" class="ai-cite">[$1]</a>');
    return s.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>');
  }
  function aiTableRow(l){ return l.trim().replace(/^\||\|$/g,'').split('|').map(c=>aiInline(c.trim())); }
  function aiMdLite(text){
    const lines = escHtml(text).split('\n');
    let html = '', inList = false, i = 0;
    const closeList = () => { if(inList){ html += '</ul>'; inList = false; } };
    while(i < lines.length){
      const line = lines[i].trim();
      if(!line){ closeList(); i++; continue; }
      // Markdown-Tabelle: Kopfzeile + Trennzeile aus -/:/| erkennen
      if(line.startsWith('|') && lines[i+1] && /^\|?[\s:|-]+\|?$/.test(lines[i+1].trim())){
        closeList();
        const header = aiTableRow(line);
        let body = '', j = i + 2;
        for(; j < lines.length && lines[j].trim().startsWith('|'); j++){
          body += '<tr>' + aiTableRow(lines[j]).map(c=>'<td>'+c+'</td>').join('') + '</tr>';
        }
        html += '<table class="ai-table"><thead><tr>' + header.map(c=>'<th>'+c+'</th>').join('')
          + '</tr></thead><tbody>' + body + '</tbody></table>';
        i = j; continue;
      }
      const h = /^#{1,4}\s+(.*)/.exec(line);
      const bullet = /^[-*]\s+(.*)/.exec(line);
      if(h){ closeList(); html += '<h4 class="ai-h">'+aiInline(h[1])+'</h4>'; }
      else if(bullet){ if(!inList){ html += '<ul class="ai-list">'; inList = true; } html += '<li>'+aiInline(bullet[1])+'</li>'; }
      else { closeList(); html += '<p>'+aiInline(line)+'</p>'; }
      i++;
    }
    closeList();
    return html;
  }
  window.aiInline = aiInline;
  window.aiMdLite = aiMdLite;
  window.aiEsc = escHtml;
})();
