// TUIWatch Frontend — ausgelagert aus templates/index.html (Backlog #12).
// Erwartet window.G (Ingress-Base, Intervall, KI-Flag, Heimatort) aus dem
// kleinen Inline-Script im Template — NUR dort steckt Jinja.
// Cache-Busting über ?v=<APP_VERSION> im <script src>.

// ── Hintergrund-Konsole ──
  (function(){
    var _open=false,_seen=0,_timer=null;
    var panel=document.getElementById('tw-console');
    var header=document.getElementById('tw-console-header');
    var body=document.getElementById('tw-console-body');
    var _dx=0,_dy=0,_drag=false;
    header.addEventListener('mousedown',function(e){ if(e.target.id==='tw-console-close')return; _drag=true;_dx=e.clientX-panel.offsetLeft;_dy=e.clientY-panel.offsetTop;e.preventDefault(); });
    document.addEventListener('mousemove',function(e){ if(!_drag)return; panel.style.left=Math.max(0,Math.min(e.clientX-_dx,window.innerWidth-panel.offsetWidth))+'px'; panel.style.top=Math.max(0,Math.min(e.clientY-_dy,window.innerHeight-panel.offsetHeight))+'px'; panel.style.right='auto';panel.style.bottom='auto'; });
    document.addEventListener('mouseup',function(){_drag=false;});
    function _setOpen(v){ _open=v; panel.classList.toggle('open',_open); try{localStorage.setItem('tw-console-open',_open?'1':'0');}catch(e){} if(_open){_poll();_timer=setInterval(_poll,2000);} else {clearInterval(_timer);_timer=null;} }
    function consoleToggle(){ if(window.innerWidth<768)return; _setOpen(!_open); }
    window.consoleToggle=consoleToggle;
    try{ if(localStorage.getItem('tw-console-open')==='1') setTimeout(function(){_setOpen(true);},100); }catch(e){}
    function _cls(l){ return (l==='WARNING'||l==='WARN')?'twc-warn':(l==='ERROR'||l==='CRITICAL')?'twc-error':(l==='DEBUG')?'twc-debug':'twc-info'; }
    async function _poll(){
      try{
        var base=(window.G&&G.base)||'';
        var lines=(await fetch(base+'/api/console').then(function(r){return r.json();})).lines||[];
        var sig=lines.length+':'+(lines.length?lines[lines.length-1].ts:0);
        if(sig===_seen)return;            // nichts Neues
        _seen=sig;
        var atBottom=body.scrollHeight-body.scrollTop-body.clientHeight<40;
        body.innerHTML='';
        lines.forEach(function(e){ var d=document.createElement('div'); d.className=_cls(e.level); d.textContent=e.msg; body.appendChild(d); });
        if(atBottom)body.scrollTop=body.scrollHeight;
      }catch(e){}
    }
  })();

// ── App ──
    const api = (p) => (G.base || '') + p;
    const $ = (s) => document.querySelector(s);

    (function(){ const t=localStorage.getItem('tw-theme')||'dark'; document.documentElement.setAttribute('data-theme',t); })();
    function toggleTheme(){ const c=document.documentElement.getAttribute('data-theme')||'dark'; const n=c==='dark'?'light':'dark'; document.documentElement.setAttribute('data-theme',n); localStorage.setItem('tw-theme',n); setTimeout(()=>{ if(curOffers) renderAll(curOffers); },50); }
    function logout(){ window.location.href = api('/logout'); }

    function eur(v){ if(v==null) return '–'; return v.toLocaleString('de-DE',{maximumFractionDigits:0}) + ' €'; }
    function ago(ts){ if(!ts) return 'noch nie geprüft'; const s=Math.floor(Date.now()/1000)-ts; if(s<60) return 'gerade eben'; if(s<3600) return 'vor '+Math.floor(s/60)+' Min'; if(s<86400) return 'vor '+Math.floor(s/3600)+' Std'; return 'vor '+Math.floor(s/86400)+' Tg'; }
    function cssvar(n){ return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

    let toastTimer;
    function toast(msg){ const el=$('#toast'); el.textContent=msg; el.classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.classList.remove('show'),2500); }
    function fmtUsd(v){ v = v||0; return '$' + v.toFixed(v > 0 && v < 0.01 ? 4 : 2); }

    let curOffers = null, lastSig = null, searchTerm = '', activeTags = new Set();
    let showArchived = localStorage.getItem('tw-show-archived')==='1';
    let showHistOnly = localStorage.getItem('tw-show-histonly')==='1';
    let sortMode = localStorage.getItem('tw-sort') || 'added';

    function startDateOf(o){ const s=urlParam(o.url,'startDate'); return /^\d{4}-\d{2}-\d{2}/.test(s)?s:''; }
    function sortOffers(list){
      const arr = list.slice();
      const num = (v, d) => (v==null ? d : v);
      if(sortMode==='price') arr.sort((a,b)=>num(a.price,Infinity)-num(b.price,Infinity));
      else if(sortMode==='delta') arr.sort((a,b)=>Math.abs(num(b.delta,0))-Math.abs(num(a.delta,0)));
      else if(sortMode==='rating') arr.sort((a,b)=>num(b.rating,-1)-num(a.rating,-1));
      else if(sortMode==='name') arr.sort((a,b)=>((a.label||a.hotel||'').localeCompare(b.label||b.hotel||'','de')));
      else if(sortMode==='location') arr.sort((a,b)=>{ const x=(a.location||'').trim(), y=(b.location||'').trim(); if(!x&&!y) return a.id-b.id; if(!x) return 1; if(!y) return -1; return x.localeCompare(y,'de')||a.id-b.id; });  // Ort A–Z, ohne Ort ans Ende
      else if(sortMode==='start') arr.sort((a,b)=>{ const x=startDateOf(a)||'9999', y=startDateOf(b)||'9999'; return x<y?-1:x>y?1:a.id-b.id; });  // Reisebeginn, ohne Datum ans Ende
      else arr.sort((a,b)=>a.id-b.id);  // 'added'
      return arr;
    }

    async function loadOffers(){
      try {
        const r = await fetch(api('/api/offers'));
        // Session abgelaufen (nur bei direktem Zugriff, nie unter Ingress):
        // Reload führt serverseitig zur Login-Seite statt stiller Fehler bei jedem Klick.
        if(r.status===401){ location.reload(); return; }
        if(!r.ok) return;
        const d = await r.json();
        _offlineFails = 0; hideOfflineBanner();
        curOffers = d.offers;
        // Nur neu rendern, wenn sich wirklich etwas geändert hat — verhindert das
        // periodische Neuzeichnen (Flackern) der Preisdiagramme alle 5 s.
        const sig = JSON.stringify(d.offers);
        const ae = document.activeElement;
        const editing = ae && ae.id && ae.id.indexOf('tgt-')===0;
        if(editing || sig === lastSig) return;
        lastSig = sig;
        renderAll(d.offers);
      } catch(e){ _offlineFails++; if(_offlineFails>=3) showOfflineBanner(); }
    }

    // ── Verbindungsabbruch-Erkennung ───────────────────────────────────────────
    let _offlineFails = 0;
    function showOfflineBanner(){ $('#offline-banner').style.display = 'flex'; }
    function hideOfflineBanner(){ $('#offline-banner').style.display = 'none'; }
    window.addEventListener('online',  () => { _offlineFails = 0; loadOffers(); });
    window.addEventListener('offline', () => showOfflineBanner());
    document.addEventListener('visibilitychange', () => { if(!document.hidden) loadOffers(); });
    if(!navigator.onLine) showOfflineBanner();

    function deltaBadge(o){
      if(o.ok===false) return '<span class="delta none">⚠ Abruf fehlgeschlagen</span>';
      if(o.delta==null) return '<span class="delta flat">Basiswert</span>';
      if(o.delta>0) return '<span class="delta up">▲ +'+eur(o.delta)+'</span>';
      if(o.delta<0) return '<span class="delta down">▼ '+eur(o.delta)+'</span>';
      return '<span class="delta flat">unverändert</span>';
    }
    // Tendenz aus dem bisherigen Verlauf (kein Orakel, nur ein Hinweis)
    function trendBadge(o){
      const t=o.trend; if(!t || !t.dir) return '';
      const pct = (t.pct!=null && Math.abs(t.pct)>=0.5) ? (' '+(t.pct>0?'+':'−')+Math.abs(t.pct).toLocaleString('de-DE',{maximumFractionDigits:1})+' %') : '';
      if(t.dir==='down') return '<span class="trend down" title="Tendenz aus dem bisherigen Verlauf">↘ fällt'+pct+'</span>';
      if(t.dir==='up')   return '<span class="trend up" title="Tendenz aus dem bisherigen Verlauf">↗ steigt'+pct+'</span>';
      return '<span class="trend flat" title="Tendenz aus dem bisherigen Verlauf">→ stabil</span>';
    }

    function renderTagPills(offers){
      const el = $('#tag-pills');
      // Nur Tags der aktuell sichtbaren Ansicht: Preisverlauf ist exklusiv, die
      // normale Ansicht zeigt aktive Angebote (+ Archiv nur wenn eingeblendet).
      // Sonst stehen hier Pills für Angebote, die gar nicht in der Liste sind —
      // und Tags der sichtbaren Liste fehlen.
      const vis = (offers||[]).filter(o => showHistOnly
        ? (o.history_only && !o.archived)
        : (o.archived ? showArchived : !o.history_only));
      const all = new Set();
      vis.forEach(o => (o.tags||[]).forEach(t => all.add(t)));
      // Aktive Filter-Tags, die es in dieser Ansicht nicht gibt, abwählen — ein
      // unsichtbarer Tag-Filter würde die Liste sonst kommentarlos leeren.
      activeTags.forEach(t => { if(!all.has(t)) activeTags.delete(t); });
      if(!all.size){ el.style.display = 'none'; el.innerHTML = ''; return; }
      el.style.display = 'flex';
      el.innerHTML = Array.from(all).sort((a,b)=>a.localeCompare(b,'de')).map(t =>
        `<span class="tag-pill${activeTags.has(t)?' active':''}" onclick="toggleTagFilter('${esc(t)}')">${esc(t)}</span>`
      ).join('');
    }
    function toggleTagFilter(tag){
      if(activeTags.has(tag)) activeTags.delete(tag); else activeTags.add(tag);
      renderAll(curOffers||[]);
    }

    function renderAll(offers){
      renderOverview(offers);
      renderTagPills(offers);
      // Nicht neu rendern, während der Nutzer einen Wunschpreis eingibt
      const ae = document.activeElement;
      if(ae && ae.id && ae.id.indexOf('tgt-')===0) return;
      $('#iv').textContent = Math.round(G.iv/3600*10)/10 + ' Std';
      const box = $('#offers');
      if(!offers.length){ box.innerHTML = '<div class="empty">Noch keine Angebote. Füge oben eine TUI-URL hinzu.</div>'; return; }
      // Schnellsuche über die geladenen Angebote (Hotel, Label, Ziel, Details)
      const q = (searchTerm||'').trim().toLowerCase();
      const list = q ? offers.filter(o =>
        ((o.label||'')+' '+(o.hotel||'')+' '+(o.location||'')+' '+(o.details||'')+' '+(o.dep_airport||'')+' '+(o.room||'')).toLowerCase().includes(q)
      ) : offers;
      const list2 = activeTags.size ? list.filter(o => (o.tags||[]).some(t=>activeTags.has(t))) : list;
      if(!list2.length){
        const parts = [];
        if(q) parts.push('„'+esc(searchTerm.trim())+'"');
        if(activeTags.size) parts.push('Tag „'+Array.from(activeTags).map(esc).join('/')+'"');
        box.innerHTML = '<div class="empty">Keine Treffer für '+parts.join(' + ')+'.</div>'; return;
      }
      const hist = sortOffers(list2.filter(o=>!o.archived && o.history_only));
      let html;
      if(showHistOnly){
        // Preisverlauf-Filter ist exklusiv: nur diese Angebote, sonst nichts.
        html = hist.length ? hist.map(offerCard).join('')
          : '<div class="empty">Keine Angebote im Preisverlauf-Tracking.</div>';
      } else {
        const active = sortOffers(list2.filter(o=>!o.archived && !o.history_only));
        const arch = sortOffers(list2.filter(o=>o.archived));
        html = active.map(offerCard).join('');
        if(!active.length && arch.length && !showArchived){
          html = `<div class="empty">Keine aktiven Angebote — ${arch.length} im Archiv. „Archiv" oben einblenden.</div>`;
        }
        if(showArchived && arch.length){
          html += `<div class="arch-head">📦 Archiv (${arch.length}) — abgelaufene oder manuell archivierte Reisen (keine Live-Abfragen)</div>` + arch.map(offerCard).join('');
        }
      }
      box.innerHTML = html;
      pruneSelection();
    }

    // ── Sammelaktionen ────────────────────────────────────────────────────────
    let selected = new Set();
    function bulkToggle(id, on){ if(on) selected.add(id); else selected.delete(id); renderBulkBar(); }
    function pruneSelection(){
      const ids = new Set((curOffers||[]).map(o=>o.id));
      selected.forEach(id=>{ if(!ids.has(id)) selected.delete(id); });
      renderBulkBar();
    }
    function renderBulkBar(){
      const bar=$('#bulk-bar'); if(!bar) return;
      if(!selected.size){ bar.style.display='none'; return; }
      bar.style.display='flex';
      $('#bulk-count').textContent = selected.size+' ausgewählt';
    }
    function bulkClear(){ selected.clear(); document.querySelectorAll('.bulk-check').forEach(c=>c.checked=false); renderBulkBar(); }
    async function bulkRun(fn, msg){
      const ids=[...selected]; if(!ids.length) return;
      toast(msg);
      for(const id of ids){ try{ await fn(id); }catch(e){} }
      selected.clear(); lastSig=null; loadOffers();
    }
    function bulkCheck(){ bulkRun(id=>fetch(api('/api/check/'+id),{method:'POST'}), ids_msg('werden geprüft…')); }
    function bulkArchive(){
      if(!confirm(selected.size+' Angebot(e) ins Archiv legen?')) return;
      bulkRun(id=>fetch(api('/api/offers/'+id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({archived:true})}), ids_msg('werden archiviert…'));
    }
    function bulkDelete(){
      if(!confirm(selected.size+' Angebot(e) inklusive Verlauf unwiderruflich löschen?')) return;
      bulkRun(id=>fetch(api('/api/offers/'+id),{method:'DELETE'}), ids_msg('werden gelöscht…'));
    }
    function ids_msg(t){ return selected.size+' Angebot(e) '+t; }
    async function bulkEmail(){
      const ids=[...selected]; if(!ids.length) return;
      await openEmailModal(ids);
    }

    // Schlanke Karte für history_only-Angebote (nur Preisverlauf/Preiskalender, keine
    // Benachrichtigungen/Buchungs-UI) — separat von offerCard(), damit die normale
    // Karte unverändert bleibt. Archivierte history_only-Angebote laufen weiterhin
    // über den bestehenden Archiv-Zweig in offerCard().
    function historyOfferCard(o){
        const hotel = o.hotel || '';
        const title = o.label || hotel || 'TUI-Angebot #'+o.id;
        const hasPrice = o.price!=null;
        const priceNow = hasPrice ? eur(o.price) : (o.checking?'…'
          : (o.last_ok_price!=null ? `<span class="old" title="Letzter bekannter Preis — aktueller Abruf fehlgeschlagen">${eur(o.last_ok_price)}</span>` : '–'));
        const stars = o.stars ? `<span class="stars">${'★'.repeat(Math.round(o.stars))}</span>` : '';
        let statsLine = '';
        if(o.min_price!=null && o.samples>1){
          statsLine = `<div class="stats">Tief ${eur(o.min_price)} · Hoch ${eur(o.max_price)} · Ø ${eur(o.avg_price)}</div>`;
        }
        return `<div class="offer" data-id="${o.id}">
          <div class="offer-top">
            <div class="offer-main">
              <div class="offer-label">${esc(title)} <button class="rename-btn" onclick="renameOffer(${o.id})" title="Umbenennen">✎</button><span class="tag-row card-tags inline">${(o.tags||[]).map(t =>
                `<span class="tag-pill" onclick="removeTag(${o.id}, '${esc(t)}')" title="Entfernen">${esc(t)} ×</span>`
              ).join('')}<span class="tag-pill add" onclick="addTag(${o.id})" title="Tag hinzufügen">＋</span></span></div>
              ${o.location?`<a class="offer-loc" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(((o.hotel||o.label||'')+' '+o.location).trim())}" target="_blank" rel="noopener" title="In Google Maps öffnen">📍 ${esc(o.location)} ↗</a>`:''}
              ${stars?`<div class="meta">${stars}</div>`:''}
              <a class="offer-url" href="${esc(o.url)}" target="_blank" rel="noopener">Angebot auf tui.com öffnen ↗</a>
              ${o.ok===false?`<div class="err-note">⚠ ${esc(o.note||'Preis konnte nicht gelesen werden')}</div>`:''}
            </div>
            <div class="price-box">
              <div class="price-now"${o.checking&&hasPrice?' style="opacity:.5"':''}>${priceNow}</div>
              <div class="price-pp">pro Person</div>
              <div>${deltaBadge(o)} ${trendBadge(o)}</div>
              ${o.image_url?`<img class="offer-img" src="${esc(o.image_url)}" loading="lazy" alt="" onerror="this.remove()">`:''}
            </div>
          </div>
          ${statsLine}
          <div class="offer-foot">
            <div class="when"><span class="paused-badge" title="Nur Preisverlauf-Tracking, keine Benachrichtigungen">📊 Preisverlauf</span>${o.checking?' · wird geprüft…':(' · Zuletzt: '+ago(o.last_ts))}</div>
            <div class="offer-actions">
              <button class="btn sec" onclick="openHistory(${o.id})">Verlauf</button>
              <button class="btn sec${o.calendar_alert?' cal-alert':''}" onclick="openCalendar(${o.id})" title="Preis je Abreisetag (Preiskalender)">Kalender</button>
              <button class="icon-btn" style="color:var(--red)" onclick="delOffer(${o.id})" title="Löschen">
                <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
              </button>
            </div>
          </div>
        </div>`;
    }

    function offerCard(o){
        if(o.history_only && !o.archived) return historyOfferCard(o);
        const hotel = o.hotel || '';
        const title = o.label || hotel || 'TUI-Angebot #'+o.id;
        // Untertitel: Hotel (falls eigenes Label gesetzt) + Reise-Eckdaten
        const subParts = [];
        if(o.label && hotel) subParts.push(hotel);
        if(o.details) subParts.push(o.details);
        const sub = subParts.join(' — ');
        let priceSub = '';
        if(o.old_price && o.old_price>o.price){ priceSub = '<span class="old">'+eur(o.old_price)+'</span>' + (o.discount?'<span class="disc">-'+o.discount+'%</span>':''); }
        const hasPrice = o.price!=null;
        const perNight = (o.nights && hasPrice) ? (o.price/o.nights) : null;
        const priceNow = hasPrice ? eur(o.price) : (o.checking?'…'
          : (o.last_ok_price!=null ? `<span class="old" title="Letzter bekannter Preis — aktueller Abruf fehlgeschlagen">${eur(o.last_ok_price)}</span>` : '–'));
        const plane = '<svg viewBox="0 0 24 24"><path d="M21 16v-2l-8-5V3.5A1.5 1.5 0 0 0 11.5 2 1.5 1.5 0 0 0 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/></svg>';
        let flights = '';
        if(o.flight_out || o.flight_ret){
          const fl = (label, v) => v?`<div class="flight">${plane}<span><span class="fdir">${label}:</span> ${esc(v)}</span></div>`:'';
          flights = `<div class="flights">${fl('Hin',o.flight_out)}${fl('Rück',o.flight_ret)}</div>`;
        }
        let availBadge = '';
        if(o.available===true) availBadge = '<div><span class="avail yes">✓ verfügbar</span></div>';
        else if(o.available===false) availBadge = '<div><span class="avail no">✗ nicht verfügbar</span></div>';
        // Sterne + HolidayCheck-Bewertung + kostenlose Stornierung
        const metaParts = [];
        if(o.stars) metaParts.push(`<span class="stars">${'★'.repeat(Math.round(o.stars))}</span>`);
        if(o.rating!=null){
          let rt = 'HolidayCheck '+o.rating.toLocaleString('de-DE',{minimumFractionDigits:1,maximumFractionDigits:1})+'/6';
          if(o.rating_count) rt += ' · '+o.rating_count.toLocaleString('de-DE')+' Bew.';
          if(o.recommendation!=null) rt += ' · '+o.recommendation+'% 👍';
          const hcq = ('site:holidaycheck.de '+(o.hotel||o.label||'')+' '+(o.region||o.country||'')).trim();
          const hc = 'https://www.google.com/search?q='+encodeURIComponent(hcq);
          metaParts.push('<a class="rating" href="'+esc(hc)+'" target="_blank" rel="noopener" title="HolidayCheck-Bewertungen suchen (über Google)">'+esc(rt)+' ↗</a>');
        }
        if(o.cancellation) metaParts.push('<span class="canc">✓ '+esc(o.cancellation)+'</span>');
        const metaLine = metaParts.length?`<div class="meta">${metaParts.join('')}</div>`:'';
        // Buchungscodes (zum Buchen/Anrufen bei TUI)
        const codeParts = [];
        if(o.booking_code) codeParts.push('Buchungscode <b>'+esc(o.booking_code)+'</b>');
        if(o.room_booking_code) codeParts.push('Zimmer '+esc(o.room_booking_code));
        if(o.giata){
          const giataUrl = 'https://hg15.giatamedia.com/index2.php?uid=782&com=sc&gid='+encodeURIComponent(o.giata)+'&frame=0&from=ks&catlang[]=de';
          codeParts.push('<a href="'+esc(giataUrl)+'" target="_blank" rel="noopener" title="GIATA-Hoteldetails öffnen">GIATA '+esc(o.giata)+' ↗</a>'
            +' <a href="#" onclick="event.preventDefault();openGiataGallery(\''+esc(o.giata)+'\')" title="Hotelfotos (GIATA) anzeigen">🖼 Fotos</a>');
        }
        const codesLine = codeParts.length?`<div class="codes">🧾 ${codeParts.join(' · ')}</div>`:'';
        let statsLine = '';
        if(o.min_price!=null && o.samples>1){
          const best = (o.price!=null && o.price<=o.min_price);
          // Einordnung zum 30-Tage-Schnitt (erst ab ±1 % — sonst nur Rauschen)
          let vs30 = '';
          if(o.vs_avg30!=null && Math.abs(o.vs_avg30)>=1){
            const under = o.vs_avg30<0;
            vs30 = ` · <span class="vs30 ${under?'down':'up'}" title="Aktueller Preis im Vergleich zum Durchschnitt der letzten 30 Tage (${eur(o.avg30_price)})">${Math.abs(o.vs_avg30).toLocaleString('de-DE')} % ${under?'unter':'über'} Ø 30 T</span>`;
          }
          statsLine = `<div class="stats">Tief ${eur(o.min_price)} · Hoch ${eur(o.max_price)} · Ø ${eur(o.avg_price)}${vs30}${best?' · <span class="best">✓ Bestpreis</span>':''}</div>`;
        }
        const tgt = o.target_price!=null ? Math.round(o.target_price) : '';
        const tgtLabel = o.target_price!=null ? `<span class="target-set">🎯 Wunschpreis ${eur(o.target_price)}</span>` : '🎯 Wunschpreis:';
        const targetRow = `<div class="target-row">${tgtLabel}
            <input type="number" id="tgt-${o.id}" placeholder="z. B. 1800" value="${tgt}" onkeydown="if(event.key==='Enter')setTarget(${o.id})">
            <button class="btn sec" onclick="setTarget(${o.id})">setzen</button></div>`;
        const bk = o.booked_price!=null ? Math.round(o.booked_price) : '';
        const bkLabel = o.booked_price!=null ? `<span class="booked-set">📌 Gebucht für ${eur(o.booked_price)}</span>` : '📌 Gebuchter Preis:';
        const bookedRow = `<div class="target-row booked-row">${bkLabel}
            <input type="number" id="book-${o.id}" placeholder="z. B. 1750" value="${bk}" onkeydown="if(event.key==='Enter')setBooked(${o.id})">
            <button class="btn sec" onclick="setBooked(${o.id})">setzen</button></div>`;
        let bookedSince = '';
        if(o.booked_price!=null && o.price!=null){
          const d = Math.round(o.price - o.booked_price);
          if(d<0) bookedSince = `<span class="booked-since down" title="seit deiner Buchung">📌 ${eur(d)} seit Buchung</span>`;
          else if(d>0) bookedSince = `<span class="booked-since up" title="seit deiner Buchung">📌 +${eur(d)} seit Buchung</span>`;
          else bookedSince = `<span class="booked-since flat" title="seit deiner Buchung">📌 wie gebucht</span>`;
        }
        return `<div class="offer${o.paused?' paused':''}${o.archived?' archived':''}" data-id="${o.id}">
          <div class="offer-top">
            <div class="offer-main">
              <div class="offer-label"><input type="checkbox" class="bulk-check" ${selected.has(o.id)?'checked':''} onclick="bulkToggle(${o.id}, this.checked)" title="Für Sammelaktion auswählen"> ${esc(title)} <button class="rename-btn" onclick="renameOffer(${o.id})" title="Umbenennen">✎</button><span class="tag-row card-tags inline">${(o.tags||[]).map(t =>
                `<span class="tag-pill" onclick="removeTag(${o.id}, '${esc(t)}')" title="Entfernen">${esc(t)} ×</span>`
              ).join('')}<span class="tag-pill add" onclick="addTag(${o.id})" title="Tag hinzufügen">＋</span></span></div>
              ${o.location?`<a class="offer-loc" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(((o.hotel||o.label||'')+' '+o.location).trim())}" target="_blank" rel="noopener" title="In Google Maps öffnen">📍 ${esc(o.location)} ↗</a>`:''}
              ${sub?`<div class="offer-details">${esc(sub)}</div>`:''}
              ${metaLine}
              ${flights}
              ${codesLine}
              <a class="offer-url" href="${esc(o.url)}" target="_blank" rel="noopener">Angebot auf tui.com öffnen ↗</a>
              ${o.pdf_url?`<a class="offer-url pdf" href="${esc(o.pdf_url)}" target="_blank" rel="noopener">📄 Hotelbeschreibung (PDF)</a>`:''}
              ${o.ok===false?`<div class="err-note">⚠ ${esc(o.note||'Preis konnte nicht gelesen werden')}</div>`:''}
            </div>
            <div class="price-box">
              <div class="price-now${(!o.archived&&G.check24)?' check24-feature check24-trigger':''}"${o.checking&&hasPrice?' style="opacity:.5"':''}${(!o.archived&&G.check24)?` onclick="${o.check24_linked?`openCheck24(${o.id})`:`linkCheck24(${o.id})`}" title="Preisvergleich über Check24 (andere Reiseveranstalter)"`:''}>${priceNow}</div>
              <div class="price-pp">pro Person</div>
              ${priceSub?`<div class="price-sub">${priceSub}</div>`:''}
              ${perNight!=null?`<div class="price-sub">${eur(perNight)}/Nacht</div>`:''}
              ${(o.travellers_count>1 && o.total_price!=null)?`<div class="price-total">Gesamt ${eur(o.total_price)} · ${o.travellers_count} Reisende</div>`:''}
              <div>${deltaBadge(o)} ${o.archived?'':trendBadge(o)}</div>
              ${bookedSince?`<div>${bookedSince}</div>`:''}
              ${availBadge}
              ${o.image_url?`<img class="offer-img" src="${esc(o.image_url)}" loading="lazy" alt="" onerror="this.remove()">`:''}
            </div>
          </div>
          ${statsLine}
          ${o.archived?'':`<div class="price-rows">${targetRow}${bookedRow}</div>`}
          <div class="offer-foot">
            <div class="when">${o.archived
              ? `<span class="archived-badge">📦 archiviert</span>${o.return_date?(' · Reise bis '+fmtD(o.return_date)):''}${o.price!=null?(' · letzter Preis '+eur(o.price)):''}`
              : (o.paused?'<span class="paused-badge">⏸ pausiert</span>':(o.checking?'<span class="badge-checking">wird geprüft…</span>':('Zuletzt: '+ago(o.last_ts))))}</div>
            <div class="offer-actions">
            ${o.archived
              ? `<button class="btn sec" onclick="openHistory(${o.id})">Verlauf</button>
                 <button class="btn sec" onclick="unarchiveOffer(${o.id})" title="Wieder aktiv verfolgen">Reaktivieren</button>
                 <button class="icon-btn" onclick="resetOffer(${o.id})" title="Zurücksetzen: Verlauf löschen und neu bei null beginnen">
                   <svg viewBox="0 0 24 24"><path d="M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
                 </button>
                 <button class="icon-btn" style="color:var(--red)" onclick="delOffer(${o.id})" title="Löschen">
                   <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                 </button>`
              : `<button class="btn sec" onclick="checkOne(${o.id})">Prüfen</button>
                 <button class="btn sec" onclick="openHistory(${o.id})">Verlauf</button>
                 <button class="btn sec${o.calendar_alert?' cal-alert':''}" onclick="openCalendar(${o.id})" title="${o.calendar_alert?'Preisänderung im Kalender seit letztem Öffnen! · ':''}Preis je Abreisetag (Preiskalender)">Kalender</button>
                 <button class="btn sec" onclick="pendingStartId=null;openRooms(${o.id})" title="Zimmerkategorie wählen (Standard = günstigstes)">Zimmer</button>
                 ${o.comparable?`<button class="btn sec" onclick="openCompare(${o.id})" title="Preis pro Person für andere Reisendenzahl vergleichen">Vergleich</button>`:''}
                 <button class="btn sec ai-feature" onclick="openBookingScore(${o.id})" title="KI-Buchungsscore: jetzt buchen, beobachten oder warten?">Buchungsscore</button>
                 <button class="btn sec" onclick="openNights(${o.id})" title="Preise für kürzere/längere Reisedauern vergleichen">Nächte</button>
                 <button class="btn sec" onclick="openSearchFromOffer(${o.id})" title="Weitere Hotels dieser Region suchen (Filter aus dem Angebot)">Region</button>
                 <button class="btn sec" onclick="togglePause(${o.id}, ${o.paused})" title="Automatische Prüfung aussetzen/fortsetzen">${o.paused?'Fortsetzen':'Pausieren'}</button>
                 <button class="btn sec" onclick="archiveOffer(${o.id})" title="Ins Archiv legen — keine Live-Abfragen mehr">Archivieren</button>
                 <button class="icon-btn" onclick="resetOffer(${o.id})" title="Zurücksetzen: Verlauf löschen und neu bei null beginnen">
                   <svg viewBox="0 0 24 24"><path d="M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
                 </button>
                 <button class="icon-btn" style="color:var(--red)" onclick="delOffer(${o.id})" title="Löschen">
                   <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                 </button>`}
            </div>
          </div>
        </div>`;
    }

    function esc(s){ return (s||'').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

    function drawChart(cv, pts, full, opts){
      opts = opts || {};
      const dpr = window.devicePixelRatio||1;
      const w = cv.clientWidth, h = cv.clientHeight;
      cv.width = w*dpr; cv.height = h*dpr;
      const ctx = cv.getContext('2d'); ctx.scale(dpr,dpr);
      ctx.clearRect(0,0,w,h);
      const muted = cssvar('--muted'), accent = cssvar('--accent'), border = cssvar('--border');
      const green = cssvar('--green'), amber = cssvar('--amber');
      if(pts.length===0){ ctx.fillStyle=muted; ctx.font='12px sans-serif'; ctx.fillText('Noch keine Messpunkte',8,h/2); return; }
      const padL = full?52:6, padR=6, padT=full?14:8, padB=full?22:8;
      const xs = pts.map(p=>p.ts), ys = pts.map(p=>p.price);
      // Wertebereich auf den echten Preisverlauf zoomen (+ Wunsch-/Buchungspreis als
      // Referenz). Der Vergleichspreis fließt NICHT ein, damit kleine Änderungen sichtbar
      // bleiben — er steht weiterhin in der Verlaufstabelle.
      const extra = [];
      if(opts.target) extra.push(opts.target);
      if(opts.booked) extra.push(opts.booked);
      let minY=Math.min(...ys, ...extra), maxY=Math.max(...ys, ...extra);
      if(minY===maxY){ minY-=50; maxY+=50; }
      else { const pad=(maxY-minY)*0.12; minY-=pad; maxY+=pad; }
      const minX=Math.min(...xs), maxX=Math.max(...xs);
      const X = t => padL + (maxX===minX?0.5:(t-minX)/(maxX-minX))*(w-padL-padR);
      const Y = v => padT + (1-(v-minY)/(maxY-minY))*(h-padT-padB);
      if(full){
        ctx.strokeStyle=border; ctx.fillStyle=muted; ctx.font='11px sans-serif'; ctx.lineWidth=1;
        for(let i=0;i<=3;i++){ const v=minY+(maxY-minY)*i/3; const y=Y(v); ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(w-padR,y); ctx.stroke(); ctx.fillText(Math.round(v).toLocaleString('de-DE')+' €',4,y-2); }
      }
      // Preis-Linie
      ctx.strokeStyle=accent; ctx.lineWidth=2; ctx.beginPath();
      pts.forEach((p,i)=>{ const x=X(p.ts),y=Y(p.price); i?ctx.lineTo(x,y):ctx.moveTo(x,y); });
      ctx.stroke();
      // Fläche
      ctx.lineTo(X(maxX),h-padB); ctx.lineTo(X(minX),h-padB); ctx.closePath();
      ctx.fillStyle = accent+'22'; ctx.fill();
      // Wunschpreis-Linie
      if(opts.target){
        const ty=Y(opts.target);
        ctx.save(); ctx.strokeStyle=amber; ctx.setLineDash([5,4]); ctx.lineWidth=1.2;
        ctx.beginPath(); ctx.moveTo(padL,ty); ctx.lineTo(w-padR,ty); ctx.stroke(); ctx.restore();
        if(full){ ctx.fillStyle=amber; ctx.font='10px sans-serif'; ctx.fillText('🎯 '+Math.round(opts.target).toLocaleString('de-DE')+' €', padL+3, ty-3); }
      }
      // Gebuchter-Preis-Linie (gezahlter Preis seit Buchung)
      if(opts.booked){
        const by=Y(opts.booked); const violet='#a371f7';
        ctx.save(); ctx.strokeStyle=violet; ctx.setLineDash([2,3]); ctx.lineWidth=1.4;
        ctx.beginPath(); ctx.moveTo(padL,by); ctx.lineTo(w-padR,by); ctx.stroke(); ctx.restore();
        if(full){ ctx.fillStyle=violet; ctx.font='10px sans-serif'; ctx.fillText('📌 '+Math.round(opts.booked).toLocaleString('de-DE')+' €', padL+3, by+11); }
      }
      // Änderungs-Marker (Events): senkrechte Linie + Fähnchen; Trefferflächen für Tooltip
      cv._events = [];
      if(full && opts.events && opts.events.length){
        const evcol = '#f778ba';
        opts.events.forEach(ev=>{
          let x = X(ev.ts); x = Math.max(padL, Math.min(w-padR, x));
          ctx.save(); ctx.strokeStyle=evcol; ctx.globalAlpha=.75; ctx.setLineDash([3,3]); ctx.lineWidth=1;
          ctx.beginPath(); ctx.moveTo(x,padT); ctx.lineTo(x,h-padB); ctx.stroke(); ctx.restore();
          ctx.fillStyle=evcol; ctx.beginPath(); ctx.moveTo(x,padT); ctx.lineTo(x+7,padT); ctx.lineTo(x,padT+7); ctx.closePath(); ctx.fill();
          const date = new Date(ev.ts*1000).toLocaleString('de-DE');
          cv._events.push({x, html:'<div class="tt-date">'+esc(date)+'</div>'+esc(ev.text||'')});
        });
      }
      // Punkte; Preisrückgänge grün markiert
      pts.forEach((p,i)=>{
        const drop = i>0 && p.price < pts[i-1].price;
        ctx.fillStyle = drop ? green : accent;
        ctx.beginPath(); ctx.arc(X(p.ts),Y(p.price), drop?(full?4:3):(full?3:2), 0, 7); ctx.fill();
      });
    }

    let histId = null;
    async function openHistory(id){
      histId = id;
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      $('#modal-title').textContent = o.label || o.hotel || ('TUI-Angebot #'+id);
      $('#modal-sub').textContent = [o.label&&o.hotel?o.hotel:'', o.details||''].filter(Boolean).join(' — ');
      $('#modal-bg').classList.add('show');
      const r = await fetch(api('/api/history/'+id));
      const hd = await r.json();
      const hist = hd.history;
      const pts = hist.filter(h=>h.ok && h.price!=null);
      drawChart($('#hist-canvas'), pts, true, {target: o.target_price, booked: o.booked_price, events: hd.events||[]});
      const rows = hist.map((h,i)=>{
        const d = new Date(h.ts*1000).toLocaleString('de-DE');
        if(!h.ok) return {keep:true, html:`<tr><td>${d}</td><td colspan="2" style="color:var(--amber)">⚠ ${esc(h.note||'fehlgeschlagen')}</td></tr>`};
        const prev = hist[i-1];
        let diff = '', unchanged = false;
        if(prev && prev.ok && prev.price!=null){
          const delta = h.price - prev.price;
          if(delta>0) diff = ` <span class="hist-diff up">▲ +${eur(delta)}</span>`;
          else if(delta<0) diff = ` <span class="hist-diff down">▼ ${eur(delta)}</span>`;
          else unchanged = true;
        }
        // unveränderte Preise ausblenden (Rauschen) — außer dem jüngsten Eintrag,
        // der zeigt, wann zuletzt geprüft wurde
        const keep = !unchanged || i === hist.length - 1;
        const html = `<tr><td>${d}</td><td><b>${eur(h.price)}</b>${diff}</td><td>${h.old_price?('<span class="old">'+eur(h.old_price)+'</span>'+(h.discount?' -'+h.discount+'%':'')):''}</td></tr>`;
        return {keep, html};
      }).filter(r=>r.keep).map(r=>r.html).reverse().join('');
      $('#hist-table').innerHTML = hist.length?`<table class="hist"><tr><th>Zeitpunkt</th><th>Preis</th><th>Vergleich</th></tr>${rows}</table>`:'';
    }
    function closeModal(){ $('#modal-bg').classList.remove('show'); }
    $('#modal-bg').addEventListener('click', e=>{ if(e.target.id==='modal-bg') closeModal(); });
    // Tooltip für Änderungs-Marker im Verlauf-Diagramm
    (function(){
      const cv=$('#hist-canvas'), tip=$('#hist-tip'); if(!cv||!tip) return;
      cv.addEventListener('mousemove', e=>{
        const rect=cv.getBoundingClientRect(); const mx=e.clientX-rect.left;
        const evs=cv._events||[]; let hit=null, best=18;   // nächsten Marker in Reichweite
        for(const m of evs){ const dx=Math.abs(mx-m.x); if(dx<best){ best=dx; hit=m; } }
        if(hit){ tip.innerHTML=hit.html; tip.style.left=hit.x+'px'; tip.style.display='block'; }
        else tip.style.display='none';
      });
      cv.addEventListener('mouseleave', ()=>{ tip.style.display='none'; });
    })();

    // ── Pro-Person-Vergleich (gespeichert) ────────────────────────────────────
    let cmpTimer = null, cmpId = null;
    function progBar(label, done, total){
      if(total){ const pct=Math.max(4,Math.round(done/total*100));
        return `<div class="cmp-load">${esc(label)} (${done}/${total})<div class="twprog"><i style="width:${pct}%"></i></div></div>`; }
      return `<div class="cmp-load">${esc(label)}<div class="twprog indet"><i></i></div></div>`;
    }
    function cmpSpinner(){ $('#cmp-body').innerHTML = progBar('Live-Abruf läuft… einen Moment.'); }
    function startCmpPolling(){ clearInterval(cmpTimer); cmpPoll(); cmpTimer = setInterval(cmpPoll, 2000); }

    async function openCompare(id){
      cmpId = id;
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      $('#cmp-sub').textContent = o.label || o.hotel || ('TUI-Angebot #'+id);
      $('#cmp-body').innerHTML = '<div class="cmp-load">Lade…</div>';
      $('#cmp-bg').classList.add('show');
      clearInterval(cmpTimer); cmpTimer=null;
      let job;
      try { job = await fetch(api('/api/compare/'+id)).then(r=>r.json()); } catch(e){ job={status:'idle',rows:[]}; }
      if(job.status==='running'){ cmpSpinner(); startCmpPolling(); }
      else if(job.status==='done' && job.rows && job.rows.length){ renderCompare(job); }  // gespeichert → anzeigen, nicht neu abfragen
      else { refreshCompare(); }                                                          // noch nie abgefragt → einmalig starten
    }
    async function refreshCompare(){
      if(cmpId==null) return;
      cmpSpinner();
      try { await fetch(api('/api/compare/'+cmpId), {method:'POST'}); } catch(e){}
      startCmpPolling();
    }
    function closeCompare(){ clearInterval(cmpTimer); cmpTimer=null; cmpId=null; $('#cmp-bg').classList.remove('show'); }
    $('#cmp-bg').addEventListener('click', e=>{ if(e.target.id==='cmp-bg') closeCompare(); });

    async function cmpPoll(){
      if(cmpId==null) return;
      let job;
      try { job = await fetch(api('/api/compare/'+cmpId)).then(r=>r.json()); } catch(e){ return; }
      if(job.status==='running') return;   // weiter warten
      clearInterval(cmpTimer); cmpTimer=null;
      renderCompare(job);
    }

    function cmpFooter(job){
      const when = job.ts ? ('Abgefragt: '+new Date(job.ts*1000).toLocaleString('de-DE')+' — gespeichert.')
                          : 'Live abgefragt.';
      const err = job.error ? '<div class="hint" style="color:var(--amber);margin-top:6px">⚠ Letzte Aktualisierung fehlgeschlagen — angezeigt wird das vorherige Ergebnis.</div>' : '';
      return `<div class="cmp-foot">
          <span class="hint" style="flex:1;min-width:180px">${esc(when)} „Gesamt" = Preis p. P. × Reisende.</span>
          <button class="btn sec" onclick="refreshCompare()">Neu abfragen</button>
        </div>${err}`;
    }

    function renderCompare(job){
      if(!(job.rows && job.rows.length)){
        const msg = job.error || job.note || 'Vergleich fehlgeschlagen';
        $('#cmp-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ '+esc(msg)+'</div>' + cmpFooter(job);
        return;
      }
      const ok = job.rows.filter(r=>r.ok && r.price!=null);
      const cheapest = ok.length ? Math.min(...ok.map(r=>r.price)) : null;
      const baseRow = job.rows.find(r=>r.is_base && r.price!=null);
      const basePrice = baseRow ? baseRow.price : null;
      const rows = job.rows.map(r=>{
        if(!r.ok || r.price==null) return `<tr><td>${r.travellers} ${r.travellers===1?'Person':'Personen'}${r.is_base?' <span class="cmp-base">(aktuell)</span>':''}</td><td colspan="3" style="color:var(--amber)">nicht abrufbar</td></tr>`;
        const best = (cheapest!=null && r.price<=cheapest);
        let diff = '';
        if(basePrice!=null && !r.is_base){
          const d = r.price - basePrice;
          diff = d===0 ? '±0' : (d<0 ? '<span class="cmp-down">▼ '+eur(Math.abs(d))+'</span>' : '<span class="cmp-up">▲ +'+eur(d)+'</span>');
        } else if(r.is_base){ diff = '<span style="color:var(--muted)">Basis</span>'; }
        return `<tr${best?' class="cmp-best"':''}>
          <td>${r.travellers} ${r.travellers===1?'Person':'Personen'}${r.is_base?' <span class="cmp-base">(aktuell)</span>':''}</td>
          <td><b>${eur(r.price)}</b>${best?' <span class="best">✓</span>':''}</td>
          <td>${eur(r.total)}</td>
          <td>${diff}</td></tr>`;
      }).join('');
      $('#cmp-body').innerHTML =
        `<table class="hist"><tr><th>Reisende</th><th>Preis p.&nbsp;P.</th><th>Gesamt</th><th>Diff. p.&nbsp;P.</th></tr>${rows}</table>`
        + cmpFooter(job);
    }

    // ── Nächte-Vergleich (Reisedauer ±N, gespeichert) ─────────────────────────
    let nigTimer = null, nigId = null;
    let nightsSpan = Math.max(1, Math.min(7, parseInt(localStorage.getItem('tw-nights-span')||'3',10)||3));
    function nigSpinner(){ $('#nig-body').innerHTML = progBar('Live-Abruf läuft… mehrere Dauern werden geprüft.'); }
    function nigSetSpan(v){ nightsSpan = Math.max(1, Math.min(7, v)); $('#nig-span').textContent = nightsSpan; localStorage.setItem('tw-nights-span', String(nightsSpan)); }
    function nightsStep(d){ nigSetSpan(nightsSpan + d); }
    function startNigPolling(){ clearInterval(nigTimer); nigPoll(); nigTimer = setInterval(nigPoll, 2000); }

    async function openNights(id){
      nigId = id;
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      $('#nig-sub').textContent = o.label || o.hotel || ('TUI-Angebot #'+id);
      $('#nig-span').textContent = nightsSpan;
      $('#nig-body').innerHTML = '<div class="cmp-load">Lade…</div>';
      $('#nig-bg').classList.add('show');
      clearInterval(nigTimer); nigTimer=null;
      let job;
      try { job = await fetch(api('/api/nights/'+id)).then(r=>r.json()); } catch(e){ job={status:'idle',rows:[]}; }
      if(job.status==='running'){ nigSpinner(); startNigPolling(); }
      else if(job.status==='done' && job.rows && job.rows.length){ if(job.span) nigSetSpan(job.span); renderNights(job); }
      else { $('#nig-body').innerHTML = '<div class="cmp-load">Spanne einstellen und auf <b>Vergleichen</b> klicken.</div>'; }
    }
    async function runNights(){
      if(nigId==null) return;
      nigSpinner();
      try { await fetch(api('/api/nights/'+nigId), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({span: nightsSpan})}); } catch(e){}
      startNigPolling();
    }
    function closeNights(){ clearInterval(nigTimer); nigTimer=null; nigId=null; $('#nig-bg').classList.remove('show'); }
    $('#nig-bg').addEventListener('click', e=>{ if(e.target.id==='nig-bg') closeNights(); });

    async function nigPoll(){
      if(nigId==null) return;
      let job;
      try { job = await fetch(api('/api/nights/'+nigId)).then(r=>r.json()); } catch(e){ return; }
      if(job.status==='running'){ $('#nig-body').innerHTML = progBar('Dauern werden geprüft…', job.done||0, job.total||0); return; }
      clearInterval(nigTimer); nigTimer=null;
      renderNights(job);
    }
    function nigFooter(job){
      const when = job.ts ? ('Abgefragt: '+new Date(job.ts*1000).toLocaleString('de-DE')+' — gespeichert.') : 'Live abgefragt.';
      const err = job.error ? '<div class="hint" style="color:var(--amber);margin-top:6px">⚠ Letzte Aktualisierung fehlgeschlagen — angezeigt wird das vorherige Ergebnis.</div>' : '';
      return `<div class="cmp-foot">
          <span class="hint" style="flex:1;min-width:180px">${esc(when)} „Gesamt" = Preis p. P. × Reisende. Nicht jede Dauer hat Flüge.</span>
          <button class="btn sec" onclick="runNights()">Neu abfragen</button>
        </div>${err}`;
    }
    function renderNights(job){
      if(!(job.rows && job.rows.length)){
        const msg = job.error || job.note || 'Nächte-Vergleich fehlgeschlagen';
        $('#nig-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ '+esc(msg)+'</div>' + nigFooter(job);
        return;
      }
      const ok = job.rows.filter(r=>r.ok && r.price!=null);
      const cheapest = ok.length ? Math.min(...ok.map(r=>r.price)) : null;
      const baseRow = job.rows.find(r=>r.is_base && r.price!=null);
      const basePrice = baseRow ? baseRow.price : null;
      const rows = job.rows.map(r=>{
        const lbl = `${r.nights} Nächte${r.is_base?' <span class="cmp-base">(aktuell)</span>':''}`;
        if(!r.ok || r.price==null) return `<tr><td>${lbl}</td><td colspan="4" style="color:var(--amber)">nicht abrufbar</td></tr>`;
        const best = (cheapest!=null && r.price<=cheapest);
        let diff = '';
        if(r.is_base){ diff = '<span style="color:var(--muted)">Basis</span>'; }
        else if(basePrice!=null){
          const d = r.price - basePrice;
          diff = d===0 ? '±0' : (d<0 ? '<span class="cmp-down">▼ '+eur(Math.abs(d))+'</span>' : '<span class="cmp-up">▲ +'+eur(d)+'</span>');
        }
        return `<tr${best?' class="cmp-best"':''}>
          <td>${lbl}</td>
          <td><b>${eur(r.price)}</b>${best?' <span class="best">✓</span>':''}</td>
          <td>${eur(r.per_night)}</td>
          <td>${eur(r.total)}</td>
          <td>${diff}</td></tr>`;
      }).join('');
      $('#nig-body').innerHTML =
        `<table class="hist"><tr><th>Dauer</th><th>Preis p.&nbsp;P.</th><th>€/Nacht</th><th>Gesamt</th><th>Diff. p.&nbsp;P.</th></tr>${rows}</table>`
        + nigFooter(job);
    }

    // ── Check24-Vergleich (andere Reiseveranstalter, gespeichert) ─────────────
    let c24Timer = null, c24Id = null;
    const C24_NOTES = {
      not_available_exact_dates: 'Für diese genauen Reisedaten aktuell kein Check24-Angebot (Hotel evtl. ausgebucht).',
      no_offer_link_found: 'Kein Angebotslink auf Check24 gefunden (Layout geändert oder Hotel nicht gelistet).',
      no_offers_parsed: 'Angebote gefunden, aber keine auslesbaren Preise (Layout geändert).',
      no_offers_for_board: 'Kein Check24-Angebot mit passender Verpflegung an diesen Terminen.',
      Check24_nicht_erreichbar: 'Check24 nicht erreichbar.',
    };
    function c24Spinner(){ $('#c24-body').innerHTML = progBar('Check24 wird abgefragt… kann bis zu einer Minute dauern.'); }
    function startC24Polling(){ clearInterval(c24Timer); c24Poll(); c24Timer = setInterval(c24Poll, 2000); }

    // Sucht automatisch mit dem TUI-Hotelnamen (kein Eintippen nötig) und zeigt
    // Treffer zum Anklicken; bei genau einem eindeutigen Treffer wird direkt
    // verknüpft und sofort der Preisvergleich gestartet.
    async function linkCheck24(id){
      c24Id = id;
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      const name = o.hotel || o.label || '';
      $('#c24-sub').textContent = name || ('TUI-Angebot #'+id);
      $('#c24-body').innerHTML = progBar('Check24 wird nach „'+name+'" durchsucht…');
      $('#c24-bg').classList.add('show');
      let data;
      try { data = await fetch(api('/api/check24/search?q='+encodeURIComponent(name))).then(r=>r.json()); }
      catch(e){ data = {error:'search_failed'}; }
      if(data.error){
        $('#c24-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Check24-Suche fehlgeschlagen. Bitte später erneut versuchen.</div>';
        return;
      }
      const cands = data.candidates || [];
      if(cands.length === 1){ pickCheck24Hotel(id, cands[0].hotel_id, cands[0].name); return; }
      if(cands.length === 0){
        $('#c24-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Kein passendes Hotel bei Check24 gefunden.</div>';
        return;
      }
      const rows = cands.map(c=>
        `<tr style="cursor:pointer" onclick="pickCheck24Hotel(${id}, '${jsArg(c.hotel_id)}', '${jsArg(c.name)}')">
          <td><b>${esc(c.name)}</b></td><td>${esc(c.location)}</td></tr>`).join('');
      $('#c24-body').innerHTML = `<div class="hint" style="margin-bottom:6px">Mehrere Treffer — richtiges Hotel anklicken:</div>
        <table class="hist"><tr><th>Hotel</th><th>Ort</th></tr>${rows}</table>`;
    }
    function pickCheck24Hotel(id, hotelId, name){
      $('#c24-body').innerHTML = progBar('Verknüpfe „'+name+'"…');
      fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({check24_hotel_id: hotelId, check24_hotel_name: name})})
        .then(()=>{ loadOffers(); openCheck24(id); });
    }
    function unlinkCheck24(id){
      fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({check24_hotel_id: ''})})
        .then(()=>{ toast('Check24-Verknüpfung entfernt'); loadOffers(); });
    }

    async function openCheck24(id){
      c24Id = id;
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      $('#c24-sub').textContent = o.label || o.hotel || ('TUI-Angebot #'+id);
      $('#c24-body').innerHTML = '<div class="cmp-load">Lade…</div>';
      $('#c24-bg').classList.add('show');
      clearInterval(c24Timer); c24Timer=null;
      let job;
      try { job = await fetch(api('/api/check24/'+id)).then(r=>r.json()); } catch(e){ job={status:'idle',rows:[]}; }
      if(job.status==='running'){ c24Spinner(); startC24Polling(); }
      else if(job.status==='done'){ renderCheck24(job); }
      else { refreshCheck24(); }
    }
    async function refreshCheck24(){
      if(c24Id==null) return;
      c24Spinner();
      let r;
      try { r = await fetch(api('/api/check24/'+c24Id), {method:'POST'}); } catch(e){ r=null; }
      if(r && r.status===409){ $('#c24-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Dieses Angebot ist noch nicht mit Check24 verknüpft.</div>'; return; }
      if(r && r.status===404){ $('#c24-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Check24-Vergleich ist deaktiviert.</div>'; return; }
      if(r && r.status===429){ $('#c24-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Bitte kurz warten, bevor erneut abgefragt wird.</div>'; return; }
      startC24Polling();
    }
    function closeCheck24(){ clearInterval(c24Timer); c24Timer=null; c24Id=null; $('#c24-bg').classList.remove('show'); }
    $('#c24-bg').addEventListener('click', e=>{ if(e.target.id==='c24-bg') closeCheck24(); });

    async function c24Poll(){
      if(c24Id==null) return;
      let job;
      try { job = await fetch(api('/api/check24/'+c24Id)).then(r=>r.json()); } catch(e){ return; }
      if(job.status==='running') return;   // weiter warten
      clearInterval(c24Timer); c24Timer=null;
      renderCheck24(job);
    }

    function c24Footer(job){
      const when = job.ts ? ('Abgefragt: '+new Date(job.ts*1000).toLocaleString('de-DE')+' — gespeichert.') : 'Live abgefragt.';
      const err = job.error ? '<div class="hint" style="color:var(--amber);margin-top:6px">⚠ Letzte Aktualisierung fehlgeschlagen — angezeigt wird das vorherige Ergebnis.</div>' : '';
      const link = job.offer_url ? `<a class="btn sec" href="${esc(job.offer_url)}" target="_blank" rel="noopener">Auf Check24 ansehen ↗</a>` : '';
      return `<div class="cmp-foot">
          <span class="hint" style="flex:1;min-width:180px">${esc(when)} Vergleich mit ähnlicher Zimmerkategorie/Verpflegung — nicht immer exakt identisch.</span>
          ${link}
          <button class="btn sec" onclick="refreshCheck24()">Neu abfragen</button>
        </div>${err}`;
    }

    function renderCheck24(job){
      if(!(job.rows && job.rows.length)){
        const msg = job.error || C24_NOTES[job.note] || job.note || 'Kein Check24-Angebot gefunden.';
        $('#c24-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ '+esc(msg)+'</div>' + c24Footer(job);
        return;
      }
      const cheapest = Math.min(...job.rows.map(r=>r.price));
      const tuiPrice = job.tui_price;
      const rows = job.rows.map(r=>{
        const best = r.price<=cheapest;
        let diff = '';
        if(tuiPrice!=null){
          const d = r.price - tuiPrice;
          diff = d===0 ? '±0' : (d<0 ? '<span class="cmp-down">▼ '+eur(Math.abs(d))+' günstiger</span>' : '<span class="cmp-up">▲ +'+eur(d)+' teurer</span>');
        }
        return `<tr${best?' class="cmp-best"':''}>
          <td>${esc(r.operator||'—')}</td>
          <td>${esc(r.room||'—')}${r.board?' · '+esc(r.board):''}</td>
          <td><b>${eur(r.price)}</b>${best?' <span class="best">✓</span>':''}</td>
          <td>${diff}</td></tr>`;
      }).join('');
      const tuiRow = tuiPrice!=null ? `<div class="hint" style="margin-bottom:6px">TUI-Preis zum Vergleich: <b>${eur(tuiPrice)}</b></div>` : '';
      $('#c24-body').innerHTML = tuiRow +
        `<table class="hist"><tr><th>Anbieter</th><th>Zimmer / Verpflegung</th><th>Preis p.&nbsp;P.</th><th>Diff. zu TUI</th></tr>${rows}</table>`
        + c24Footer(job);
    }

    // ── Hotelsuche (Maske / URL / aus Angebot) ────────────────────────────────
    let srchResults = [], srchOfferId = null, srchDest = null, srchTotal = 0, srchFilter = '';
    let srchLastBody = null;
    let srchSort = localStorage.getItem('tw-srch-sort') || 'price';
    let srCmpSelected = new Set();  // Schlüssel (giata/Name) der für den KI-Vergleich ausgewählten Hotels
    let airportsLoaded = false, airlinesLoaded = false, destNode = null, destData = null, destStack = [];
    function urlParam(u, key){ try{ return new URL(u).searchParams.get(key)||''; }catch(e){ return ''; } }
    function isoPlus(days){ const d=new Date(); d.setUTCDate(d.getUTCDate()+days); return d.toISOString().slice(0,10); }
    // Springt das Startdatum auf heute — z.B. wenn ein altes Datum stehengeblieben
    // ist (TUIs Such-API antwortet auf Zeiträume in der Vergangenheit mit HTTP 500).
    function srchDateToday(){ $('#srch-vom').value = isoPlus(0); syncBisMin(); }
    // Nächte = Tage zwischen von und bis (null, wenn ungültig)
    function nightsBetween(vom, bis){
      if(!vom || !bis || bis < vom) return null;
      return Math.round((Date.parse(bis) - Date.parse(vom)) / 86400000);
    }
    // Bei „Exakt": TUI liefert genau die Reisedauer (duration=exact). Das Nächte-Feld
    // wird dann von TUI bestimmt → gesperrt und zur Info auf die Tagesdifferenz gesetzt.
    function applyExact(){
      const on = $('#srch-exact').checked, dur = $('#srch-dur');
      dur.disabled = on;
      if(on){
        const n = nightsBetween($('#srch-vom').value, $('#srch-bis').value);
        if(n!=null) dur.value = Math.max(1, n);
      }
      updateNightsHint();
    }
    // Live-Hinweis, wenn die Nächte nicht in den Zeitraum passen (evtl. keine Treffer).
    // Bei „Exakt" nicht nötig – die Dauer entspricht dann immer dem Zeitraum.
    function updateNightsHint(){
      const el = $('#srch-nights-warn');
      if($('#srch-exact').checked){ el.style.display='none'; return; }
      const win = nightsBetween($('#srch-vom').value, $('#srch-bis').value);
      const dur = parseInt($('#srch-dur').value)||0;
      if(win!=null && dur>win){
        el.textContent = `⚠ ${dur} Nächte passen nicht in den Zeitraum (${win} Tage) – evtl. keine Treffer.`;
        el.style.display='';
      } else { el.style.display='none'; }
    }
    function jsArg(s){ return esc(String(s==null?'':s).replace(/\\/g,'\\\\').replace(/'/g,"\\'")); }

    async function ensureAirports(){
      if(airportsLoaded) return;
      try {
        const d = await fetch(api('/api/airports')).then(r=>r.json());
        const sel = $('#srch-airport'); const saved = localStorage.getItem('tw-airport');
        const pre = (d.airports||[]).find(a=>a.preselected);
        const def = saved || (pre&&pre.code) || 'STR';
        sel.innerHTML = (d.airports||[]).map(a=>`<option value="${esc(a.code)}"${a.code===def?' selected':''}>${esc(a.name)} (${esc(a.code)})</option>`).join('');
        airportsLoaded = true;
      } catch(e){}
    }
    async function ensureAirlines(){
      if(airlinesLoaded) return;
      try {
        const d = await fetch(api('/api/airlines')).then(r=>r.json());
        $('#srch-airline-list').innerHTML = (d.airlines||[]).map(a=>
          `<label><input type="checkbox" class="srch-airline" value="${esc(a.code)}" onchange="updateAirlineSummary()"> ${esc(a.name)}</label>`).join('');
        airlinesLoaded = true;
      } catch(e){}
    }
    function selectedAirlines(){ return [...document.querySelectorAll('.srch-airline:checked')].map(c=>c.value); }
    function setAirlines(codes){
      const set = new Set(codes||[]);
      document.querySelectorAll('.srch-airline').forEach(c=>{ c.checked = set.has(c.value); });
      updateAirlineSummary();
    }
    function updateAirlineSummary(){
      const sel = selectedAirlines(); const sum = $('#srch-airline-sum');
      sum.textContent = sel.length ? (sel.length+' gewählt') : 'alle';
      sum.classList.toggle('set', sel.length>0);
    }
    function setSearchMode(mode){     // 'mask' | 'offer'
      const off = (mode==='offer');
      $('#srch-favbar').style.display = off?'none':'';
      $('#srch-mask').style.display   = off?'none':'';
      $('#srch-adv').style.display    = off?'none':'';
      $('#srch-from').style.display   = off?'block':'none';
      $('#dest-panel').style.display  = 'none';
    }
    // "bis" muss nach "von" liegen: min setzen und bei Bedarf nachziehen.
    function syncBisMin(){
      const v=$('#srch-vom').value, b=$('#srch-bis');
      if(!v){ b.removeAttribute('min'); applyExact(); return; }
      b.min = v;
      if(b.value && b.value < v) b.value = v;
      applyExact();
    }
    function openSearch(){            // Maske (Toolbar)
      srchOfferId = null;
      setSearchMode('mask'); ensureAirports(); ensureAirlines(); renderFavs();
      $('#srch-vom').min = isoPlus(0);
      if(!$('#srch-vom').value) $('#srch-vom').value = isoPlus(21);
      if(!$('#srch-bis').value) $('#srch-bis').value = isoPlus(51);
      syncBisMin();
      updateNightsHint();
      $('#srch-bg').classList.add('show');
    }
    function openSearchFromOffer(id){ // Region-Modus (aus Angebot)
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      srchOfferId = id;
      setSearchMode('offer');
      $('#srch-from').innerHTML = 'Region aus Angebot: <b>'+esc(o.hotel||o.label||('#'+id))+'</b>'
        + (o.location?(' · '+esc(o.location)):'') + ' — Reisedaten &amp; Abflughafen werden übernommen.';
      $('#srch-url').value='';
      const ops = urlParam(o.url,'operators');
      $('#srch-tui').checked = (!ops || /TUID/i.test(ops));
      // Board-Codes des Angebots auf die Basis-Variante normalisieren (Plus → Basis),
      // damit die passende Checkbox vorbelegt wird (AP=AI Plus, FP=VP Plus, HP=HB Plus).
      const baseBoard = {AP:'AI', FP:'FB', HP:'HB'};
      const bt = (urlParam(o.url,'boardTypes')||'').split(/[;,]/)
        .map(s=>{ const c=s.trim().toUpperCase(); return baseBoard[c]||c; });
      document.querySelectorAll('.srch-board').forEach(c=>{ c.checked = bt.includes(c.value.toUpperCase()); });
      const la = (urlParam(o.url,'locationAttributes')||'').split(/[;,]/).map(s=>s.trim()).filter(Boolean);
      document.querySelectorAll('.srch-loc').forEach(c=>{ c.checked = la.includes(c.value); });
      $('#srch-direct').checked = (urlParam(o.url,'maxStopOvers')==='0');
      $('#srch-adults').checked = (urlParam(o.url,'facilityAttributes')||'').split(/[;,]/).includes('13');
      $('#srch-stars').value='3'; $('#srch-rec').value='80';
      $('#srch-qual-off').checked=false; toggleQualFilter();
      const al = (urlParam(o.url,'airlines')||'').split(/[;,]/).map(s=>s.trim()).filter(Boolean);
      ensureAirlines().then(()=>setAirlines(al));
      $('#srch-body').innerHTML='';
      $('#srch-bg').classList.add('show');
      runSearch();
    }
    // "Egal": Sterne/Weiterempfehlung komplett aus der Suche weglassen statt sie
    // auf 0 zu setzen (0 filtert zwar auch nicht, aber die Felder blieben dabei
    // trotzdem bedienbar/verwirrend) — Felder werden zur Klarheit gesperrt.
    function toggleQualFilter(){
      const off = $('#srch-qual-off').checked;
      $('#srch-stars').disabled = off;
      $('#srch-rec').disabled = off;
    }
    function closeSearch(){ $('#srch-bg').classList.remove('show'); }
    $('#srch-bg').addEventListener('click', e=>{ if(e.target.id==='srch-bg') closeSearch(); });
    // Suchmaske auf die Standardwerte zurücksetzen (inkl. Reiseziel).
    function resetSearch(){
      srchDest = null;
      const b=$('#srch-dest'); b.textContent='Reiseziel wählen…'; b.classList.remove('set');
      const air=$('#srch-airport'); if(air.options.length) air.selectedIndex=0;
      $('#srch-vom').value=isoPlus(21); $('#srch-bis').value=isoPlus(51); syncBisMin();
      $('#srch-dur').value=7; $('#srch-trav').value=2; $('#srch-exact').checked=false; applyExact();
      $('#srch-tui').checked=true; $('#srch-direct').checked=false; $('#srch-adults').checked=false;
      document.querySelectorAll('.srch-board').forEach(c=>{ c.checked=false; });
      document.querySelectorAll('.srch-loc').forEach(c=>{ c.checked=false; });
      $('#srch-stars').value=3; $('#srch-rec').value=80; $('#srch-url').value='';
      $('#srch-qual-off').checked=false; toggleQualFilter();
      setAirlines([]);
      $('#srch-favsel').value=''; favBtnState();
    }

    // ── Reisen-Datenbank (PDF-Import gebuchter Reisen) ──────────────────────────
    let tripsData = [];
    function eur(v){ return (v==null||v==='')?'–':Number(v).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2})+' €'; }
    function deDate(iso){ if(!iso) return ''; const p=iso.split('-'); return p.length===3?(p[2]+'.'+p[1]+'.'+p[0]):iso; }
    function openTrips(){ $('#trip-detail').style.display='none'; $('#trips-bg').classList.add('show'); loadTrips(); }
    function closeTrips(){ $('#trips-bg').classList.remove('show'); }
    $('#trips-bg').addEventListener('click', e=>{ if(e.target.id==='trips-bg') closeTrips(); });

    // ── TUI-Aktionscodes (öffentlich) ─────────────────────────────────────────
    let aktionTimer = null;
    function openAktion(){
      clearInterval(aktionTimer); aktionTimer=null;
      $('#aktion-bg').classList.add('show');
      $('#aktion-body').innerHTML = '<div class="cmp-load">Lade…</div>';
      aktionPoll(true);
    }
    function closeAktion(){ clearInterval(aktionTimer); aktionTimer=null; $('#aktion-bg').classList.remove('show'); }
    $('#aktion-bg').addEventListener('click', e=>{ if(e.target.id==='aktion-bg') closeAktion(); });
    async function refreshAktion(){
      $('#aktion-body').innerHTML = progBar('Aktionscodes werden geprüft…');
      try { await fetch(api('/api/aktionscodes'), {method:'POST'}); } catch(e){}
      clearInterval(aktionTimer); aktionTimer = setInterval(()=>aktionPoll(false), 2000);
    }
    async function aktionPoll(first){
      let d; try { d = await fetch(api('/api/aktionscodes')).then(r=>r.json()); } catch(e){ return; }
      if(d.running){ if(first) $('#aktion-body').innerHTML = progBar('Aktionscodes werden geprüft…'); return; }
      clearInterval(aktionTimer); aktionTimer=null;
      renderAktion(d);
    }
    function renderAktion(d){
      const when = $('#aktion-when');
      when.textContent = d.ts ? ('Abgefragt: '+new Date(d.ts*1000).toLocaleString('de-DE')) : '';
      if(d.error){ $('#aktion-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ '+esc(d.error)+'</div>'; return; }
      const cs = d.codes||[];
      setAktionGlow(cs.length>0);
      if(!cs.length){ $('#aktion-body').innerHTML = '<div class="cmp-load">Aktuell keine Aktionscodes gefunden.</div>'; return; }
      const ctx = [];
      if(d.booking_until) ctx.push('buchbar bis <b>'+esc(d.booking_until)+'</b>');
      if(d.travel_period) ctx.push('Reisezeitraum '+esc(d.travel_period));
      $('#aktion-body').innerHTML =
        (ctx.length?('<div class="aktion-ctx">'+ctx.join(' · ')+'</div>'):'') +
        '<div class="aktion-list">' + cs.map(c=>`<div class="aktion-card">
          <div class="aktion-val">${esc(String(c.value))} €</div>
          <div class="aktion-code">${esc(c.code||'')}</div>
          ${c.kind?`<div class="aktion-kind">${esc(c.kind)}</div>`:''}
        </div>`).join('') + '</div>';
    }
    function setAktionGlow(on){ const b=document.getElementById('aktion-btn'); if(b) b.classList.toggle('aktion-active', !!on); }
    // Button leuchten lassen, wenn aktuell Aktionscodes verfügbar sind (ohne Modal zu öffnen)
    async function updateAktionBtn(){
      try { const d = await fetch(api('/api/aktionscodes')).then(r=>r.json()); setAktionGlow((d.codes||[]).length>0); }
      catch(e){}
    }

    // ── Markttrend (destinationsübergreifend, überlebt Angebots-Löschung) ─────
    function openMarketTrend(){
      $('#trend-bg').classList.add('show');
      $('#trend-body').innerHTML = '<div class="cmp-load">Lade…</div>';
      loadMarketTrend();
    }
    function closeMarketTrend(){ $('#trend-bg').classList.remove('show'); }
    $('#trend-bg').addEventListener('click', e=>{ if(e.target.id==='trend-bg') closeMarketTrend(); });
    async function loadMarketTrend(){
      let d; try { d = await fetch(api('/api/market-trend')).then(r=>r.json()); }
      catch(e){ $('#trend-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Laden fehlgeschlagen</div>'; return; }
      renderMarketTrend(d);
    }
    function marketTrendBadge(t){
      if(!t) return '<span class="trend flat" title="Zu wenig Datenpunkte in den letzten 14 Tagen">→ keine Daten</span>';
      const pct = Math.abs(t.pct)>=0.5 ? (' '+(t.pct>0?'+':'−')+Math.abs(t.pct).toLocaleString('de-DE',{maximumFractionDigits:1})+' %') : '';
      const days = t.days>=2 ? ` seit ${t.days} Tagen` : '';
      const title = `Marktweiter Trend über die letzten 14 Tage (${t.n} Datenpunkte)`;
      if(t.dir==='down') return `<span class="trend down" title="${title}">↘ fällt${pct}${days}</span>`;
      if(t.dir==='up')   return `<span class="trend up" title="${title}">↗ steigt${pct}${days}</span>`;
      return `<span class="trend flat" title="${title}">→ stabil${days}</span>`;
    }
    function marketIndexLine(i){
      if(!i) return '';
      const since = new Date(i.since*1000).toLocaleDateString('de-DE');
      const sign = i.pct>0 ? '+' : '';
      const cls = i.pct>0 ? 'up' : (i.pct<0 ? 'down' : 'flat');
      return ` <span class="trend ${cls}" title="Index seit Aufzeichnungsbeginn (${i.n} Datenpunkte), unabhängig vom 14-Tage-Fenster">`
           + `Index ${i.index.toLocaleString('de-DE',{maximumFractionDigits:1})} (${sign}${i.pct.toLocaleString('de-DE',{maximumFractionDigits:1})} % seit ${since})</span>`;
    }
    let _marketTrendData = null;
    function renderMarketTrend(d){
      _marketTrendData = d;
      setTrendGlow(d.global.trend);
      const rows = (d.by_region||[]).map((r,i)=>
        `<tr><td>${esc(r.region)}</td><td>${marketTrendBadge(r.trend)}${marketIndexLine(r.index)}</td>`
        + `<td>${(r.trend||r.index||{}).n||''}</td>`
        + `<td class="ai-feature"><button class="btn sec" onclick="openRegionOutlook(${i})" title="KI-Einschätzung für diese Destination">🔮</button></td>`
        + `<td><button class="btn sec" onclick="resetRegionTrend(${i})" title="Markttrend-Daten dieser Destination löschen und neu beginnen">🗑</button></td></tr>`).join('');
      $('#trend-body').innerHTML =
        `<div class="trend-global"><b>Gesamt:</b> ${marketTrendBadge(d.global.trend)}${marketIndexLine(d.global.index)}</div>` +
        (rows ? `<table class="hist"><tr><th>Destination</th><th>Trend (14 Tage) / Index (gesamt)</th><th>Datenpunkte</th><th class="ai-feature">KI</th><th></th></tr>${rows}</table>`
              : '<div class="cmp-load">Noch keine Destination mit genug Daten für eine eigene Aufschlüsselung.</div>');
    }
    function setTrendGlow(t){
      const b = document.getElementById('trend-btn'); if(!b) return;
      b.classList.remove('trend-active-up', 'trend-active-down');
      if(t && t.dir==='up') b.classList.add('trend-active-up');
      else if(t && t.dir==='down') b.classList.add('trend-active-down');
    }
    async function updateTrendBtn(){
      try { const d = await fetch(api('/api/market-trend')).then(r=>r.json()); setTrendGlow(d.global.trend); }
      catch(e){}
    }
    async function resetRegionTrend(i){
      const r = _marketTrendData && _marketTrendData.by_region[i]; if(!r) return;
      if(!confirm(`Markttrend-Daten für „${r.region}" löschen und neu beginnen?\n`
        + `Hinweis: „Neu berechnen" baut alle Regionen aus dem Preisverlauf neu auf `
        + `und stellt die Punkte damit wieder her.`)) return;
      try {
        const d = await fetch(api('/api/market-trend/region'), {method:'DELETE',
          headers:{'Content-Type':'application/json'}, body:JSON.stringify({region:r.region})}).then(x=>x.json());
        toast(`${d.deleted} Datenpunkte für „${r.region}" gelöscht`);
      } catch(e){ toast('Löschen fehlgeschlagen'); }
      loadMarketTrend();
      updateTrendBtn();
    }
    async function recomputeMarketTrend(){
      $('#trend-body').innerHTML = '<div class="cmp-load">Wird neu berechnet…</div>';
      try {
        const d = await fetch(api('/api/market-trend/recompute'), {method:'POST'}).then(r=>r.json());
        toast(`Markttrend neu berechnet (${d.recomputed} Datenpunkte)`);
      } catch(e){ toast('Neu berechnen fehlgeschlagen'); }
      loadMarketTrend();
      updateTrendBtn();
    }
    // Preiskalender: mit Pfeiltasten ← / → durch die Monate blättern (nicht nur per Maus)
    document.addEventListener('keydown', e=>{
      if(!$('#cal-bg').classList.contains('show')) return;
      if(e.key!=='ArrowLeft' && e.key!=='ArrowRight') return;
      if(!calData || !calData.days) return;
      const months=[...new Set(calData.days.map(d=>d.date.slice(0,7)))].sort();
      const idx=months.indexOf(calMonth);
      const t = e.key==='ArrowLeft' ? (idx>0?months[idx-1]:'') : (idx<months.length-1?months[idx+1]:'');
      if(t){ calGo(t); e.preventDefault(); }
    });

    async function loadTrips(){
      let d={trips:[],stats:{},by_year:[]};
      try { d = await fetch(api('/api/trips')).then(r=>r.json()); } catch(e){}
      tripsData = d.trips||[];
      const s = d.stats||{};
      $('#trips-stats').innerHTML = [
        ['Reisen', s.count||0, true],
        ['Nächte', s.nights_sum||0, true],
        ['Gesamtausgaben', eur(s.total_sum)],
        ['Eigene Kosten', eur(s.own_sum)],
        ['Ø €/Nacht p.P.', eur(s.avg_per_night)],
      ].map(([l,v,sm])=>`<div class="tstat${sm?' sm':''}"><div class="v">${esc(String(v))}</div><div class="l">${l}</div></div>`).join('');
      const years = d.by_year||[];
      $('#trips-years').innerHTML = years.length?(
        '<table class="tdt tyears"><tr><th>Jahr</th><th>Reisen</th><th>Nächte</th><th>Ausgaben</th><th>Eigene Kosten</th><th>Ø €/Nacht p.P.</th></tr>'+
        years.map(y=>`<tr><td>${esc(y.year)}</td><td>${y.count}</td><td>${y.nights_sum}</td><td>${eur(y.total_sum)}</td><td>${eur(y.own_sum)}</td><td>${eur(y.avg_per_night)}</td></tr>`).join('')+
        '</table>'):'';
      renderTrips();
    }
    function renderTrips(){
      const el = $('#trips-list');
      if(!tripsData.length){ el.innerHTML = '<div class="trips-empty">Noch keine Reisen importiert. Lade oben eine TUI-Reisebestätigung als PDF hoch.</div>'; return; }
      el.innerHTML = tripsData.map(t=>{
        const zeit = (t.start_date||t.end_date)?`${deDate(t.start_date)} – ${deDate(t.end_date)}`:'';
        const meta = [t.hotel, t.destination, zeit,
          (t.nights?`${t.nights} Nächte`:''),
          (t.travellers?`${t.travellers} Reisende`:''),
          (t.net_per_night?`${eur(t.net_per_night)}/Nacht p.P.`:'')].filter(Boolean).join(' · ');
        const pdf = t.has_pdf?`<a class="btn sec" href="${api('/api/trips/'+t.id+'/pdf')}" target="_blank" rel="noopener">PDF</a>`:'';
        return `<div class="trip-row">
          <div class="ti"><div class="t">${esc(t.title||('Reise #'+t.id))}</div><div class="m">${esc(meta)}</div></div>
          <div class="tp">${eur(t.total_price)}</div>
          <div class="ta">
            <button class="btn sec" onclick="showTripDetail(${t.id})">Details</button>
            ${pdf}
            <button class="btn danger" onclick="delTrip(${t.id})">Löschen</button>
          </div></div>`;
      }).join('');
    }

    // — Zusammenfassung zukünftiger Reisen: Datum+Wochentag, Zeitraum, Flugdaten —
    //   zum Teilen (Web Share API) oder per E-Mail versenden. —
    let _lastTripsSummary = null;
    async function openTripsSummary(){
      let d; try { d = await fetch(api('/api/trips/summary')).then(r=>r.json()); } catch(e){ toast('Laden fehlgeschlagen'); return; }
      _lastTripsSummary = d;
      renderTripsSummary(d.trips||[]);
      $('#trips-summary-bg').classList.add('show');
    }
    function closeTripsSummary(){ $('#trips-summary-bg').classList.remove('show'); }
    $('#trips-summary-bg').addEventListener('click', e=>{ if(e.target.id==='trips-summary-bg') closeTripsSummary(); });
    function renderTripsSummary(trips){
      const el = $('#trips-summary-body');
      if(!trips.length){ el.innerHTML = '<div class="trips-empty">Keine bevorstehenden Reisen.</div>'; return; }
      el.innerHTML = trips.map(t=>{
        const von = t.start_weekday ? `${t.start_weekday}, ${t.start_date_de}` : t.start_date_de;
        const bis = t.end_weekday ? `${t.end_weekday}, ${t.end_date_de}` : t.end_date_de;
        const zeit = t.start_date ? `${von} – ${bis}${t.nights?' ('+t.nights+' Nächte)':''}` : '';
        const flights = (t.flights||[]).map(f=>
          `<div style="font-size:.84rem;color:#667">✈ <b>${esc(f.typ)}</b>: ${esc(f.datum)}${f.wochentag?' ('+esc(f.wochentag)+')':''} · ${esc(f.von)} → ${esc(f.nach)} · ${esc(f.abflug_zeit)}–${esc(f.ankunft_zeit)} Uhr${f.flugnummer?' · '+esc(f.flugnummer):''}</div>`
        ).join('');
        const hotel = (t.hotel && t.hotel !== t.title) ? `<div class="m">🏨 ${esc(t.hotel)}</div>` : '';
        return `<div class="trip-row" style="display:block;margin-bottom:10px">
          <div class="ti"><div class="t">🧳 ${esc(t.title)}</div>${hotel}<div class="m">${esc(zeit)}</div></div>
          ${flights}
        </div>`;
      }).join('');
    }
    async function shareTripsSummary(){
      const text = (_lastTripsSummary && _lastTripsSummary.text) || '';
      if(!text){ toast('Nichts zu teilen'); return; }
      if(navigator.share){
        try { await navigator.share({title:'Meine Reisen', text}); return; }
        catch(e){ if(e.name==='AbortError') return; }
      }
      try { await navigator.clipboard.writeText(text); toast('In Zwischenablage kopiert (Teilen wird hier nicht unterstützt)'); }
      catch(e){ toast('Teilen/Kopieren fehlgeschlagen'); }
    }
    async function emailTripsSummary(){
      emailMode = 'trips';
      await _openEmailModalCommon();
    }
    async function submitTripSummaryEmail(to){
      toast('Zusammenfassung wird gesendet…');
      const r = await fetch(api('/api/trips/summary/email'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({to})});
      if(r.ok){ const d=await r.json(); toast('E-Mail an '+d.to+' gesendet ('+d.count+' Reisen)'); }
      else { const d=await r.json().catch(()=>({})); toast(d.error==='no_trips'?'Keine bevorstehenden Reisen':d.error==='send_failed'?'Versand fehlgeschlagen – Einstellungen prüfen':d.error==='no_recipient'?'Kein Empfänger':'E-Mail-Fehler'); }
    }

    async function importTrip(input){
      const f = input.files && input.files[0];
      if(!f) return;
      $('#trip-imp-status').textContent = 'Importiere…';
      const fd = new FormData(); fd.append('pdf', f);
      let resp, d;
      try { resp = await fetch(api('/api/trips/import'), {method:'POST', body:fd}); d = await resp.json().catch(()=>({})); }
      catch(e){ $('#trip-imp-status').textContent=''; toast('Import fehlgeschlagen'); input.value=''; return; }
      input.value='';
      if(resp.status===413){ $('#trip-imp-status').textContent=''; toast('PDF zu groß (max. 16 MB)'); return; }
      if(resp.status===422){ $('#trip-imp-status').textContent=''; toast('PDF konnte nicht gelesen werden – Debug-Ansicht wird geöffnet'); debugUpload(f); return; }
      if(!resp.ok){ $('#trip-imp-status').textContent=''; toast('Import fehlgeschlagen'); return; }
      const warns = (d && d.warnings) || [];
      const aiFilled = (d && d.ai_filled) || [];
      if(warns.length){
        $('#trip-imp-status').textContent = '⚠ importiert – mit Hinweisen';
        toast('Hinweis: nicht erkannt – '+warns.join(', ')
          + (aiFilled.length ? ' (per KI ergänzt: '+aiFilled.join(', ')+')' : ''));
      } else if(aiFilled.length){
        $('#trip-imp-status').textContent = '✓ importiert (KI-Fallback genutzt)';
        toast('Reise importiert — per KI ergänzt: '+aiFilled.join(', '));
      } else {
        $('#trip-imp-status').textContent = '✓ importiert';
        toast('Reise importiert');
      }
      setTimeout(()=>{ $('#trip-imp-status').textContent=''; }, 4000);
      await loadTrips();
      if(d && d.id) showTripDetail(d.id);
    }

    async function showTripDetail(id){
      let t;
      try { const r = await fetch(api('/api/trips/'+id)); if(!r.ok){ toast('Reise nicht gefunden'); return; } t = await r.json(); }
      catch(e){ toast('Fehler beim Laden'); return; }
      _lastTripDetail = t;
      const d = t.data||{};
      const row = (k,v)=> v?`<div><span class="k">${k}:</span> ${esc(String(v))}</div>`:'';
      const grid = [
        row('Buchungsnr.', d.buchungsnummer),
        row('Gebucht am', d.buchungsdatum),
        row('Reiseziel', d.reiseziel),
        row('Hotel', (d.hotel||{}).name + ((d.hotel||{}).code?` (${d.hotel.code})`:'')),
        row('Zeitraum', (d.reisezeitraum||{}).von?`${d.reisezeitraum.von} – ${d.reisezeitraum.bis} (${d.naechte||'?'} Nächte)`:''),
        row('Zimmer', d.zimmertyp),
        row('Verpflegung', d.verpflegung),
        row('Gesamtpreis', d.gesamtpreis?d.gesamtpreis+' €':''),
        row('Paketpreis (brutto)', d.paketpreis?d.paketpreis+' €':''),
        row('Reisepreis (o. Extras, n. Rabatt)', d.paketpreis_netto?d.paketpreis_netto+' €':''),
        row('€/Nacht (Reisepreis)', d.preis_pro_nacht_paket?d.preis_pro_nacht_paket+' €':''),
        row('€/Person/Nacht (Reisepreis)', d.preis_pro_person_nacht_paket?d.preis_pro_person_nacht_paket+' €':''),
        row('€/Nacht (gesamt)', d.preis_pro_nacht?d.preis_pro_nacht+' €':''),
        row('Zahlungsart', d.zahlungsart),
        row('Anzahlung', (d.anzahlung||{}).betrag?`${d.anzahlung.betrag} € · fällig ${d.anzahlung.faelligkeit||'?'}`:''),
        row('Restzahlung', (d.restzahlung||{}).betrag?`${d.restzahlung.betrag} € · fällig ${d.restzahlung.faelligkeit||'?'}`:''),
      ].join('');
      const reisende = (d.reisende||[]).length?`<div class="dsec">Reisende</div><table class="tdt"><tr><th>Name</th><th>Geburtsdatum</th><th>Preis</th></tr>${
        d.reisende.map(p=>`<tr><td>${esc(p.name)}</td><td>${esc(p.geburtsdatum||'')}</td><td>${esc(p.preis||'')} €</td></tr>`).join('')}</table>`:'';
      const fluege = (d.fluege||[]).length?`<div class="dsec">Flüge</div><table class="tdt"><tr><th>Typ</th><th>Datum</th><th>Strecke</th><th>Zeit</th><th>Airline</th></tr>${
        d.fluege.map(f=>`<tr><td>${esc(f.typ||'')}</td><td>${esc(f.datum||'')}</td><td>${esc((f.von||'')+' → '+(f.nach||''))}</td><td>${esc((f.abflug_zeit||'')+(f.ankunft_zeit?('–'+f.ankunft_zeit):''))}</td><td>${esc(f.flugnummer||'')}</td></tr>`).join('')}</table>`:'';
      const extras = (d.extras||[]).length?`<div class="dsec">Extras</div><table class="tdt"><tr><th>Typ</th><th>Details</th><th>Preis</th></tr>${
        d.extras.map(e=>{ const det=[e.plaetze,e.gewicht,e.strecke,e.details,(e.anzahl?('x'+e.anzahl):'')].filter(Boolean).join(' '); const pr=(e.preis==='inkl.')?'inkl.':((e.preis!=null)?e.preis+' €':''); return `<tr><td>${esc(e.typ||'')}</td><td>${esc(det)}</td><td>${esc(pr)}</td></tr>`; }).join('')}</table>`:'';
      const rabatte = (d.rabatte||[]).length?`<div class="dsec">Rabatte${d.rabatt_inklusive?' <span class="hint">(bereits im Reisepreis enthalten)</span>':''}</div><table class="tdt"><tr><th>Code</th><th>Betrag</th></tr>${
        d.rabatte.map(r=>`<tr><td>${esc(r.code||'')}</td><td>${esc(r.betrag||'')}</td></tr>`).join('')}</table>`:'';
      const wuensche = (d.sonderwuensche||[]).length?`<div class="dsec">Sonderwünsche</div><div style="font-size:.84rem">${d.sonderwuensche.map(w=>esc(w)).join('<br>')}</div>`:'';
      const pdf = t.has_pdf?`<a class="btn" href="${api('/api/trips/'+id+'/pdf')}" target="_blank" rel="noopener">📄 PDF öffnen</a>`:'';
      const dbg = t.has_pdf?`<button class="btn sec" onclick="showTripDebug(${id}, '${jsArg(t.title||('Reise #'+id))}')" title="Bereinigten PDF-Text und je Feld erkannt/leer anzeigen — hilfreich, wenn TUI das PDF-Layout ändert">🔍 Debug</button>`:'';
      const rescan = t.has_pdf?`<button class="btn sec" onclick="rescanTrip(${id})" title="Gespeichertes PDF neu einlesen (z. B. nach Parser-Update) — ohne Löschen und Neu-Upload">🔁 Neu einlesen</button>`:'';
      const warns = t.warnings||[];
      const warnBox = warns.length?`<div class="trip-warn">⚠ Diese Felder wurden nicht (vollständig) aus dem PDF erkannt: <b>${warns.map(w=>esc(w)).join(', ')}</b>. Bitte in der PDF prüfen.</div>`:'';
      const atts = (t.attachments||[]).map(a =>
        `<span class="tag-pill">📎 <a href="${api('/api/trips/'+id+'/attachments/'+a.id)}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none">${esc(a.orig_name)}</a> <span onclick="deleteTripAttachment(${id},${a.id})" title="Anhang entfernen" style="cursor:pointer">×</span></span>`
      ).join('');
      const attRow = `<div class="tag-row" style="margin:8px 0 2px">${atts}<span class="tag-pill add" onclick="$('#trip-att-input-${id}').click()" title="Weiteres PDF hinterlegen (nur Ablage, keine Auswertung)">＋ PDF</span>
        <input type="file" id="trip-att-input-${id}" accept="application/pdf" style="display:none" onchange="uploadTripAttachment(${id}, this.files[0])"></div>`;
      const packHtml = renderPackingSection(id, t, t.packing||[]);
      const box = $('#trip-detail');
      box.innerHTML = `<h3>${esc(t.title||('Reise #'+id))}</h3>
        <div style="margin-bottom:6px">${pdf} ${dbg} ${rescan} <button class="btn sec" onclick="shareTripBanner(${id})" title="Reise als Bild teilen">📤 Teilen</button> <button class="btn sec" onclick="$('#trip-detail').style.display='none'">schließen</button></div>
        ${attRow}
        ${warnBox}<div class="dgrid">${grid}</div>${reisende}${fluege}${extras}${rabatte}${wuensche}
        ${packHtml}`;
      box.style.display='block';
      box.scrollIntoView({behavior:'smooth', block:'nearest'});
    }
    async function rescanTrip(id){
      toast('PDF wird neu eingelesen…');
      let d; try { const r = await fetch(api('/api/trips/'+id+'/rescan'), {method:'POST'}); d = await r.json().catch(()=>({})); if(!r.ok) throw d; }
      catch(e){ toast(e&&e.error==='parse_failed'?'PDF konnte nicht gelesen werden':e&&e.error==='no_pdf'?'Kein gespeichertes PDF vorhanden':'Neu einlesen fehlgeschlagen'); return; }
      toast(d.warnings&&d.warnings.length?'Neu eingelesen — nicht erkannt: '+d.warnings.join(', '):'PDF neu eingelesen ✓');
      await loadTrips();
      showTripDetail(id);
    }
    async function uploadTripAttachment(id, file){
      if(!file) return;
      const fd = new FormData(); fd.append('pdf', file);
      let d; try { const r = await fetch(api('/api/trips/'+id+'/attachments'), {method:'POST', body:fd}); d = await r.json().catch(()=>({})); }
      catch(e){ toast('Upload fehlgeschlagen'); return; }
      if(d && d.ok){ toast('PDF hinterlegt'); showTripDetail(id); } else { toast('Upload fehlgeschlagen'); }
    }
    async function deleteTripAttachment(id, aid){
      await fetch(api('/api/trips/'+id+'/attachments/'+aid), {method:'DELETE'});
      toast('Anhang entfernt'); showTripDetail(id);
    }

    // — Teilen: Reise-Banner als Bild (Countdown + Ziel/Hotel über ein Foto-Banner
    //   gelegt), per Web Share API teilen oder als Download-Fallback. —
    let _lastTripDetail = null;

    function _tripDaysInfo(t){
      if(!t.start_date) return null;
      const dep = (t.data && t.data.fluege || []).find(f=>f.typ==='Hinflug');
      const depDt = new Date(`${t.start_date}T${(dep && dep.abflug_zeit) || '00:00'}:00`);
      const diff = depDt.getTime() - Date.now();
      if(diff <= 0){
        if(t.end_date && new Date(`${t.end_date}T23:59:59`).getTime() < Date.now()) return 'Schön war\'s!';
        return 'Gute Reise!';
      }
      const mins = Math.floor(diff/60000);
      const d = Math.floor(mins/1440), h = Math.floor((mins%1440)/60), m = mins%60;
      const parts = [];
      if(d) parts.push(d+' Tag'+(d===1?'':'e'));
      if(d || h) parts.push(h+' Std');
      if(!d) parts.push(m+' Min');
      return parts.join(' ');
    }

    function _fitFont(ctx, text, weight, maxPx, maxWidth){
      const family = 'system-ui, Arial, sans-serif';
      let px = maxPx;
      ctx.font = `${weight} ${px}px ${family}`;
      while(px > 20 && ctx.measureText(text).width > maxWidth){
        px -= 4;
        ctx.font = `${weight} ${px}px ${family}`;
      }
      return px;
    }

    async function shareTripBanner(id){
      const t = _lastTripDetail;
      if(!t) return;
      const img = new Image();
      const loaded = new Promise((res,rej)=>{ img.onload=res; img.onerror=rej; });
      img.src = api('/static/share-banner.jpg');
      try { await loaded; } catch(e){ toast('Banner konnte nicht geladen werden'); return; }

      const cv = document.createElement('canvas');
      cv.width = img.naturalWidth; cv.height = img.naturalHeight;
      const ctx = cv.getContext('2d');
      ctx.drawImage(img, 0, 0);

      const counter = _tripDaysInfo(t);
      const dest = t.destination || (t.data||{}).reiseziel || '';
      const hotelName = ((t.data||{}).hotel||{}).name || t.hotel || '';
      const cx = cv.width * 0.68;
      const maxTextWidth = cv.width * 0.58;
      let y = cv.height * 0.34;

      ctx.textAlign = 'center';
      ctx.fillStyle = '#fff';
      ctx.shadowColor = 'rgba(0,0,0,.45)';
      ctx.shadowBlur = 18;
      ctx.shadowOffsetY = 4;

      if(counter){
        _fitFont(ctx, counter, 900, 128, maxTextWidth);
        ctx.fillText(counter, cx, y);
        y += 110;
      }
      if(dest){
        ctx.fillStyle = '#fff';
        _fitFont(ctx, dest, 700, 72, maxTextWidth);
        ctx.fillText(dest, cx, y);
        y += 68;
      }
      if(hotelName){
        ctx.fillStyle = 'rgba(255,255,255,.92)';
        _fitFont(ctx, hotelName, 500, 44, maxTextWidth);
        ctx.fillText(hotelName, cx, y);
      }

      const blob = await new Promise(res=>cv.toBlob(res, 'image/jpeg', 0.92));
      if(!blob){ toast('Bild konnte nicht erstellt werden'); return; }
      const file = new File([blob], 'reise-teilen.jpg', {type:'image/jpeg'});

      if(navigator.canShare && navigator.canShare({files:[file]})){
        try {
          await navigator.share({files:[file], title:'TUIWatch',
            text:[dest, hotelName].filter(Boolean).join(' · ')});
          return;
        } catch(e){ if(e.name==='AbortError') return; }
      }
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = 'reise-teilen.jpg';
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
      toast('Bild heruntergeladen (Teilen wird hier nicht unterstützt)');
    }

    // — Packliste: pro Reise, Vorlage beim ersten Öffnen automatisch geseedet,
    //   danach in der UI frei editier-/ergänz-/löschbar. Begrenzt auf
    //   MAX_PACKING_ITEMS, damit der Ausdruck auf einer A4-Seite bleibt. —
    const MAX_PACKING_ITEMS = 70;
    let _lastPack = null;
    const _packOpenState = {};

    function _groupPacking(items){
      const order = [], map = new Map();
      (items||[]).forEach(it=>{
        if(!map.has(it.category)){ map.set(it.category, []); order.push(it.category); }
        map.get(it.category).push(it);
      });
      return order.map(cat=>({cat, items:map.get(cat)}));
    }

    function _packMeta(t){
      const d = t.data||{};
      const zeitraum = (d.reisezeitraum||{}).von
        ? `${d.reisezeitraum.von} – ${d.reisezeitraum.bis} (${d.naechte||'?'} Nächte)` : '';
      return [d.reiseziel, (d.hotel||{}).name, zeitraum].filter(Boolean).join(' · ');
    }

    function _packFlights(t){
      const d = t.data||{};
      return (d.fluege||[]).map(f=>{
        const zeit = (f.abflug_zeit||'') + (f.ankunft_zeit?('–'+f.ankunft_zeit):'');
        const strecke = [f.von, f.nach].filter(Boolean).join(' → ');
        return [f.typ, f.datum, strecke, zeit, f.flugnummer].filter(Boolean).join(' · ');
      });
    }

    // Verteilt Kategorien auf 2 Spalten nach tatsächlicher Füllung (Item-Anzahl je
    // Kategorie als Näherung für die Höhe) statt CSS-columns, die per Balance-Heuristik
    // manchmal ungleich befüllen — neue Kategorie landet so immer in der leereren Spalte.
    function _splitColumns(groups){
      const cols = [[], []], weight = [0, 0];
      groups.forEach(g=>{
        const idx = weight[0] <= weight[1] ? 0 : 1;
        cols[idx].push(g);
        weight[idx] += g.items.length + 1;
      });
      return cols;
    }

    function renderPackingSection(id, t, items){
      const groups = _groupPacking(items);
      const full = items.length >= MAX_PACKING_ITEMS;
      const open = _packOpenState[id] === true;
      const doneCount = items.filter(it=>it.checked).length;
      const buildCat = g=>{
        const catId = 'pc'+id+'-'+g.cat.replace(/[^A-Za-z0-9]/g,'');
        return `<div class="pack-cat">
          <div class="dsec">${esc(g.cat)}</div>
          ${g.items.map(it=>`<div class="pack-item">
            <input type="checkbox" ${it.checked?'checked':''} onchange="togglePackItem(${id},${it.id},this.checked)">
            <span class="lbl${it.checked?' done':''}" contenteditable="true" spellcheck="false"
              onblur="renamePackItem(${id},${it.id},this.textContent)"
              onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur();}">${esc(it.label)}</span>
            <span class="del" onclick="deletePackItem(${id},${it.id})" title="Entfernen">×</span>
          </div>`).join('')}
          <div class="pack-add">
            <input type="text" id="${catId}" placeholder="+ eigenes Item" ${full?'disabled':''}
              onkeydown="if(event.key==='Enter'){addPackItem(${id}, '${jsArg(g.cat)}', this);}">
          </div>
        </div>`;
      };
      const catsHtml = _splitColumns(groups)
        .map(col=>`<div class="pack-col">${col.map(buildCat).join('')}</div>`).join('');
      const newCatRow = `<div class="pack-add" style="margin-top:6px">
          <input type="text" id="pack-newcat-${id}" placeholder="Neue Kategorie" style="flex:1" ${full?'disabled':''}>
          <input type="text" id="pack-newlabel-${id}" placeholder="Item" style="flex:2" ${full?'disabled':''}>
          <button class="btn sec" ${full?'disabled':''} onclick="addPackItemNewCat(${id})">＋</button>
        </div>`;
      _lastPack = {title: t.title||('Reise #'+id), meta: _packMeta(t), flights: _packFlights(t), items};
      return `<div class="pack-head">
          <span class="pack-toggle" id="pack-toggle-${id}" onclick="togglePackOpen(${id})" title="Ein-/ausklappen">${open?'▾':'▸'}</span>
          <div class="dsec" style="margin:0">🎒 Packliste</div>
          <span class="cnt">${items.length}/${MAX_PACKING_ITEMS} · ${doneCount} erledigt · ${items.length-doneCount} offen</span>
          <button class="btn sec" onclick="printPacking()">🖨️ Drucken</button>
          <button class="btn sec" onclick="openPackTemplate(${id})" title="Die Vorlage bearbeiten, aus der neue Packlisten (und „Zurücksetzen") erzeugt werden">📝 Vorlage</button>
          <span class="pack-reset" onclick="resetPacking(${id})">↺ Zurücksetzen</span>
        </div>
        <div class="pack-body" id="pack-body-${id}" style="${open?'':'display:none'}">
          <div class="pack-wrap">${catsHtml}</div>
          ${newCatRow}
        </div>`;
    }

    // — Packlisten-Vorlage bearbeiten: einfaches Textformat, eine Kategorie pro
    //   "# Name"-Zeile, darunter je Zeile ein Item. Gilt für neue Packlisten und
    //   "Zurücksetzen"; bestehende Reise-Packlisten bleiben unverändert. —
    async function openPackTemplate(tripId){
      let d;
      try { const r = await fetch(api('/api/packing-template')); if(!r.ok) throw 0; d = await r.json(); }
      catch(e){ toast('Vorlage konnte nicht geladen werden'); return; }
      const text = Object.entries(d.template||{}).map(([cat,items])=>'# '+cat+'\n'+items.join('\n')).join('\n\n');
      const box = $('#trip-detail');
      box.innerHTML = `<h3>📝 Packlisten-Vorlage${d.custom?' <span class="hint">(angepasst)</span>':''}</h3>
        <div class="hint" style="margin:4px 0 8px">Eine Kategorie beginnt mit <code># Name</code>, darunter je Zeile ein Item (max. 70 gesamt, damit der Ausdruck auf eine A4-Seite passt). Die Vorlage gilt für Packlisten neuer Reisen und beim „↺ Zurücksetzen" — bestehende Listen bleiben unverändert.</div>
        <textarea id="pack-tpl-text" class="reiseb-text" rows="18" spellcheck="false">${esc(text)}</textarea>
        <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn" onclick="savePackTemplate(${tripId})">💾 Vorlage speichern</button>
          <button class="btn sec" onclick="resetPackTemplate(${tripId})">↺ Standard-Vorlage wiederherstellen</button>
          <button class="btn sec" onclick="showTripDetail(${tripId})">Zurück</button>
        </div>`;
      box.style.display='block';
      box.scrollIntoView({behavior:'smooth', block:'nearest'});
    }
    function parsePackTemplate(text){
      const tpl = {}; let cat = null;
      for(const raw of (text||'').split('\n')){
        const line = raw.trim(); if(!line) continue;
        if(line.startsWith('#')){ cat = line.replace(/^#+\s*/,'').trim(); if(cat && !tpl[cat]) tpl[cat] = []; }
        else if(cat) tpl[cat].push(line);
      }
      for(const c of Object.keys(tpl)) if(!tpl[c].length) delete tpl[c];
      return tpl;
    }
    async function savePackTemplate(tripId){
      const tpl = parsePackTemplate($('#pack-tpl-text').value);
      const n = Object.values(tpl).reduce((a,b)=>a+b.length,0);
      if(!n){ toast('Vorlage ist leer — mindestens eine Kategorie („# Name") mit einem Item'); return; }
      if(n>MAX_PACKING_ITEMS){ toast('Zu viele Items ('+n+') — max. '+MAX_PACKING_ITEMS+', damit der Ausdruck auf eine Seite passt'); return; }
      let ok=false;
      try { const r = await fetch(api('/api/packing-template'), {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({template: tpl})}); ok = r.ok; } catch(e){}
      if(!ok){ toast('Speichern fehlgeschlagen'); return; }
      toast('Vorlage gespeichert ✓ — gilt für neue Packlisten und „Zurücksetzen"');
      showTripDetail(tripId);
    }
    async function resetPackTemplate(tripId){
      if(!confirm('Eigene Vorlage verwerfen und die Standard-Vorlage verwenden?')) return;
      try { await fetch(api('/api/packing-template'), {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({template: null})}); } catch(e){}
      toast('Standard-Vorlage aktiv');
      openPackTemplate(tripId);
    }

    function togglePackOpen(id){
      const open = !(_packOpenState[id] === true);
      _packOpenState[id] = open;
      const el = $('#pack-body-'+id), btn = $('#pack-toggle-'+id);
      if(el) el.style.display = open ? '' : 'none';
      if(btn) btn.textContent = open ? '▾' : '▸';
    }

    function togglePackItem(tid, iid, checked){
      fetch(api('/api/trips/'+tid+'/packing/'+iid), {method:'PATCH',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({checked})})
        .then(()=>showTripDetail(tid));
    }
    function renamePackItem(tid, iid, text){
      const label = (text||'').trim();
      if(!label){ showTripDetail(tid); return; }
      fetch(api('/api/trips/'+tid+'/packing/'+iid), {method:'PATCH',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({label})})
        .then(()=>showTripDetail(tid));
    }
    async function _postPackItem(tid, category, label){
      const r = await fetch(api('/api/trips/'+tid+'/packing'), {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({category, label})});
      if(r.status===409){ toast('Packliste voll (max. '+MAX_PACKING_ITEMS+' Einträge, damit sie auf eine Seite passt)'); return; }
      showTripDetail(tid);
    }
    function addPackItem(tid, category, inputEl){
      const label = (inputEl.value||'').trim();
      if(!label) return;
      _postPackItem(tid, category, label);
    }
    function addPackItemNewCat(tid){
      const category = ($('#pack-newcat-'+tid).value||'').trim();
      const label = ($('#pack-newlabel-'+tid).value||'').trim();
      if(!category || !label) return;
      _postPackItem(tid, category, label);
    }
    function deletePackItem(tid, iid){
      fetch(api('/api/trips/'+tid+'/packing/'+iid), {method:'DELETE'}).then(()=>showTripDetail(tid));
    }
    function resetPacking(tid){
      if(!confirm('Packliste auf Vorlage zurücksetzen? Eigene Einträge und Haken gehen verloren.')) return;
      fetch(api('/api/trips/'+tid+'/packing/reset'), {method:'POST'})
        .then(()=>{ toast('Packliste zurückgesetzt'); showTripDetail(tid); });
    }
    function printPacking(){
      if(!_lastPack) return;
      const groups = _groupPacking(_lastPack.items);
      const buildCat = g=>`<div class="pp-cat"><h4>${esc(g.cat)}</h4>${
        g.items.map(it=>`<div class="pp-item">${it.checked?'☑':'☐'} ${esc(it.label)}</div>`).join('')
      }</div>`;
      const catsHtml = _splitColumns(groups)
        .map(col=>`<div class="pp-col">${col.map(buildCat).join('')}</div>`).join('');
      const flightsHtml = (_lastPack.flights||[]).length
        ? `<div class="pp-flights">${_lastPack.flights.map(f=>`<div>✈ ${esc(f)}</div>`).join('')}</div>` : '';
      $('#pack-print-area').innerHTML = `<div class="pp-head"><h1>TUIWatch — Packliste</h1>
          <div class="pp-meta">${esc(_lastPack.title)}${_lastPack.meta?' · '+esc(_lastPack.meta):''}</div>
          ${flightsHtml}</div>
        <div class="pp-wrap">${catsHtml}</div>`;
      window.print();
    }

    // — PDF-Debug: bereinigter Text + erkannt/leer je Feld (nur für den Angemeldeten,
    //   Inhalte können persönliche Daten enthalten und werden nirgends geloggt) —
    // Manuell zuordenbare Felder (Whitelist = _MANUAL_TRIP_KEYS im Backend);
    // warn = check_fields-Label, über das die Zeile als "fehlend" hervorgehoben wird.
    const DBG_FIELDS = [
      {key:'buchungsnummer', label:'Buchungsnummer', warn:'Buchungsnummer', get:d=>d.buchungsnummer},
      {key:'buchungsdatum', label:'Buchungsdatum', warn:'Buchungsdatum', ph:'TT.MM.JJJJ', get:d=>d.buchungsdatum},
      {key:'reiseziel', label:'Reiseziel', warn:'Reiseziel', get:d=>d.reiseziel},
      {key:'hotel_name', label:'Hotel', warn:'Hotel', get:d=>(d.hotel||{}).name},
      {key:'reisezeitraum_von', label:'Anreise', warn:'Reisezeitraum', ph:'TT.MM.JJJJ', get:d=>(d.reisezeitraum||{}).von},
      {key:'reisezeitraum_bis', label:'Abreise', warn:'Reisezeitraum', ph:'TT.MM.JJJJ', get:d=>(d.reisezeitraum||{}).bis},
      {key:'naechte', label:'Nächte', warn:'Nächte', num:true,
       hint:'Bei vollständiger An-+Abreise wird die Zahl daraus berechnet', get:d=>d.naechte},
      {key:'verpflegung', label:'Verpflegung', warn:'Verpflegung', get:d=>d.verpflegung},
      {key:'gesamtpreis', label:'Gesamtpreis €', warn:'Gesamtpreis', ph:'1.234,56', get:d=>d.gesamtpreis},
      {key:'reisende_anzahl', label:'Reisende (Anzahl)', warn:'Reisende', num:true,
       hint:'Greift nur, wenn der Parser keine Reisenden erkannt hat', get:d=>(d.reisende||[]).length||''},
      {key:'anzahlung_betrag', label:'Anzahlung €', ph:'1.234,56', get:d=>(d.anzahlung||{}).betrag},
      {key:'anzahlung_faelligkeit', label:'Anzahlung fällig', ph:'TT.MM.JJJJ', get:d=>(d.anzahlung||{}).faelligkeit},
      {key:'restzahlung_betrag', label:'Restzahlung €', ph:'1.234,56', get:d=>(d.restzahlung||{}).betrag},
      {key:'restzahlung_faelligkeit', label:'Restzahlung fällig', ph:'TT.MM.JJJJ', get:d=>(d.restzahlung||{}).faelligkeit},
    ];
    let _dbgTid = null, _dbgTitle = '', _dbgManual = {};
    function dbgFieldRow(f, d){
      const cur = f.get(d.data||{});
      const ov = _dbgManual[f.key];
      return `<div class="dbg-row">
        <span class="dbg-lbl">${ov!=null?'✍️ ':''}${esc(f.label)}${f.hint?` <span class="hint" title="${esc(f.hint)}">ⓘ</span>`:''}</span>
        <span class="dbg-cur" title="Aktueller Wert">${cur!=null&&cur!==''?esc(String(cur)):'–'}</span>
        <input class="dbg-in" id="dbg-in-${f.key}" ${f.num?'type="number" min="1"':'type="text"'}
          placeholder="${esc(f.ph||'')}" value="${ov!=null?esc(String(ov)):''}">
        <button class="btn sec" onmousedown="event.preventDefault()" onclick="dbgTakeSelection('${f.key}')"
          title="Im PDF-Auszug unten markierten Text in dieses Feld übernehmen">⇦ Auswahl</button>
      </div>`;
    }
    function dbgExtraRow(e){
      e = e || {};
      return `<tr>
        <td><input class="dbg-ex-typ" value="${esc(e.typ||'')}" placeholder="z. B. Handgepäck"></td>
        <td><input class="dbg-ex-det" value="${esc(e.details||e.plaetze||e.gewicht||e.strecke||'')}" placeholder="Details"></td>
        <td style="width:60px"><input class="dbg-ex-anz" type="number" min="1" value="${e.anzahl!=null?esc(String(e.anzahl)):''}" placeholder="1"></td>
        <td style="width:90px"><input class="dbg-ex-preis" value="${esc(e.preis||'')}" placeholder="15,00"></td>
        <td style="width:26px"><span style="cursor:pointer" title="Zeile entfernen" onclick="this.closest('tr').remove()">×</span></td>
      </tr>`;
    }
    function dbgExtraAdd(){ $('#dbg-ex-rows').insertAdjacentHTML('beforeend', dbgExtraRow()); }
    function dbgRabattRow(r){
      r = r || {};
      return `<tr>
        <td><input class="dbg-rb-code" value="${esc(r.code||'')}" placeholder="z. B. SAVE150"></td>
        <td style="width:110px"><input class="dbg-rb-betrag" value="${esc(r.betrag||'')}" placeholder="-150,00"></td>
        <td style="width:26px"><span style="cursor:pointer" title="Zeile entfernen" onclick="this.closest('tr').remove()">×</span></td>
      </tr>`;
    }
    function dbgRabattAdd(){ $('#dbg-rb-rows').insertAdjacentHTML('beforeend', dbgRabattRow()); }
    function renderTripDebug(d, title, tid){
      if(!d || !d.ok){ toast(d&&d.error==='text_failed'?'Debug: Text konnte nicht aus der PDF extrahiert werden':'Debug fehlgeschlagen'); return; }
      _dbgTid = tid!=null?tid:null; _dbgTitle = title; _dbgManual = d.manual||{};
      const fields = (d.fields||[]).map(f=>`<span class="dbg-f ${f.manual?'manual':(f.ok?'ok':'miss')}">${f.manual?'✍️':(f.ok?'✓':'⚠')} ${esc(f.label)}</span>`).join('');
      const err = d.parse_error?`<div class="trip-warn">⚠ Parser abgebrochen: ${esc(d.parse_error)}</div>`:'';
      const json = d.data?`<details class="dbg-sec"><summary>Geparstes JSON anzeigen</summary><pre class="dbg-pre">${esc(JSON.stringify(d.data,null,2))}</pre></details>`:'';
      let editor = '';
      if(tid!=null){
        const warns = d.warnings||[];
        const missing = DBG_FIELDS.filter(f=>f.warn&&warns.includes(f.warn));
        const rest = DBG_FIELDS.filter(f=>!missing.includes(f));
        const extras = (_dbgManual.extras) || (d.data&&d.data.extras) || [];
        const rabatte = (_dbgManual.rabatte) || (d.data&&d.data.rabatte) || [];
        editor = `<div class="dbg-edit">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <div class="dsec" style="margin:0">✍️ Felder manuell zuordnen</div>
            <button class="btn sec ai-feature" onclick="dbgAiSuggest()" title="KI liest das gespeicherte PDF und schlägt Werte für die leeren Felder vor — nichts wird automatisch gespeichert, du prüfst und speicherst selbst">🤖 KI-Vorschläge</button>
          </div>
          <div class="hint" style="margin:2px 0 6px">Text im PDF-Auszug unten markieren und per „⇦ Auswahl" übernehmen — oder direkt eintippen. Leeres Feld speichern = Zuordnung löschen (Parser-Wert gilt wieder). Manuelle Werte überleben „Neu einlesen" und erneuten Import.</div>
          ${missing.map(f=>dbgFieldRow(f,d)).join('')}
          ${missing.length&&rest.length?`<details class="dbg-sec"><summary>Weitere Felder überschreiben (${rest.length})</summary>${rest.map(f=>dbgFieldRow(f,d)).join('')}</details>`:rest.map(f=>dbgFieldRow(f,d)).join('')}
          <details class="dbg-sec" ${_dbgManual.extras?'open':''}><summary>Extras überschreiben${_dbgManual.extras?' ✍️ (manuell gesetzt)':''}</summary>
            <label style="display:flex;gap:6px;align-items:center;font-size:.8rem;margin:6px 0"><input type="checkbox" id="dbg-ex-on" ${_dbgManual.extras?'checked':''}> Extras-Liste manuell festlegen (ersetzt die erkannten Extras komplett)</label>
            <table class="tdt dbg-ex-tbl"><tr><th>Typ</th><th>Details</th><th>Anz.</th><th>Preis €</th><th></th></tr>
              <tbody id="dbg-ex-rows">${extras.map(dbgExtraRow).join('')}</tbody></table>
            <button class="btn sec" onclick="dbgExtraAdd()" style="margin-top:4px">＋ Zeile</button>
          </details>
          <details class="dbg-sec" ${_dbgManual.rabatte||_dbgManual.rabatt_inklusive?'open':''}><summary>Rabatte überschreiben${_dbgManual.rabatte||_dbgManual.rabatt_inklusive?' ✍️ (manuell gesetzt)':''}</summary>
            <label style="display:flex;gap:6px;align-items:center;font-size:.8rem;margin:6px 0"><input type="checkbox" id="dbg-rb-ink" ${_dbgManual.rabatt_inklusive?'checked':''}> Rabatt ist bereits im Reisepreis enthalten <span class="hint" title="Manche TUI-PDFs weisen den Rabatt nur informativ aus — er steckt schon im ausgewiesenen Preis. Dann wird er NICHT zum Brutto-Paketpreis zurückgerechnet.">ⓘ</span></label>
            <label style="display:flex;gap:6px;align-items:center;font-size:.8rem;margin:6px 0"><input type="checkbox" id="dbg-rb-on" ${_dbgManual.rabatte?'checked':''}> Rabatt-Liste manuell festlegen (ersetzt die erkannten Rabatte komplett)</label>
            <table class="tdt dbg-ex-tbl"><tr><th>Code</th><th>Betrag €</th><th></th></tr>
              <tbody id="dbg-rb-rows">${rabatte.map(dbgRabattRow).join('')}</tbody></table>
            <button class="btn sec" onclick="dbgRabattAdd()" style="margin-top:4px">＋ Zeile</button>
          </details>
          <div style="margin-top:8px"><button class="btn" onclick="dbgSaveFields()">💾 Zuordnung speichern</button></div>
        </div>`;
      }
      const box = $('#trip-detail');
      box.innerHTML = `<h3>🔍 Debug — ${esc(title)}</h3>
        <div style="margin-bottom:6px"><button class="btn sec" onclick="$('#trip-detail').style.display='none'">schließen</button></div>
        ${err}
        <div class="dbg-fields">${fields}</div>
        ${editor}
        <div class="dsec">Bereinigter PDF-Text (Basis der Feld-Erkennung)</div>
        <div class="hint" style="margin:0 0 6px">Wenn TUI das Layout geändert hat: diesen Text kopieren, persönliche Daten anonymisieren und als neuer Testfall unter <code>tests/fixtures/trips/</code> ablegen — der Test zeigt dann exakt das kippende Feld.</div>
        <pre class="dbg-pre" id="dbg-text">${esc(d.cleaned_text||'')}</pre>
        ${json}`;
      box.style.display='block';
      box.scrollIntoView({behavior:'smooth', block:'nearest'});
    }
    async function dbgAiSuggest(){
      if(_dbgTid==null) return;
      toast(aiProviderName()+' liest das PDF…');
      let d;
      try {
        const r = await fetch(api('/api/trips/'+_dbgTid+'/fields/suggest'), {method:'POST'});
        d = await r.json().catch(()=>({})); if(!r.ok) throw d;
      } catch(e){
        toast(e&&e.error==='no_api_key'?'Kein KI-API-Key hinterlegt':'KI-Vorschlag fehlgeschlagen');
        return;
      }
      let n = 0;
      for(const [k,v] of Object.entries(d.suggestions||{})){
        const inp = $('#dbg-in-'+k);
        if(inp && !inp.value.trim()){ inp.value = String(v); n++; }
      }
      toast(n ? 'KI hat '+n+' Feld(er) vorgeschlagen — bitte prüfen, dann „💾 Zuordnung speichern"'
              : 'Keine neuen Vorschläge (Felder schon gefüllt oder nichts gefunden)');
    }
    function dbgTakeSelection(key){
      const s = String(window.getSelection()||'').trim();
      if(!s){ toast('Erst Text im PDF-Auszug markieren'); return; }
      const inp = $('#dbg-in-'+key); if(inp){ inp.value = s; }
    }
    async function dbgSaveFields(){
      if(_dbgTid==null) return;
      const fields = {};
      for(const f of DBG_FIELDS){
        const inp = $('#dbg-in-'+f.key); if(!inp) continue;
        const v = inp.value.trim();
        const ov = _dbgManual[f.key];
        if(v && String(ov!=null?ov:'') !== v) fields[f.key] = f.num?parseInt(v,10):v;
        else if(!v && ov!=null) fields[f.key] = null;   // Zuordnung löschen
      }
      const exOn = $('#dbg-ex-on') && $('#dbg-ex-on').checked;
      if(exOn){
        const rows = [...document.querySelectorAll('#dbg-ex-rows tr')].map(tr=>({
          typ: tr.querySelector('.dbg-ex-typ').value.trim(),
          details: tr.querySelector('.dbg-ex-det').value.trim(),
          anzahl: tr.querySelector('.dbg-ex-anz').value.trim(),
          preis: tr.querySelector('.dbg-ex-preis').value.trim(),
        })).filter(r=>r.typ);
        fields.extras = rows;
      } else if(_dbgManual.extras){
        fields.extras = null;   // Häkchen entfernt → Parser-Extras gelten wieder
      }
      const rbOn = $('#dbg-rb-on') && $('#dbg-rb-on').checked;
      if(rbOn){
        fields.rabatte = [...document.querySelectorAll('#dbg-rb-rows tr')].map(tr=>({
          code: tr.querySelector('.dbg-rb-code').value.trim(),
          betrag: tr.querySelector('.dbg-rb-betrag').value.trim(),
        })).filter(r=>r.code);
      } else if(_dbgManual.rabatte){
        fields.rabatte = null;   // Häkchen entfernt → Parser-Rabatte gelten wieder
      }
      const rbInk = $('#dbg-rb-ink') && $('#dbg-rb-ink').checked;
      if(rbInk && !_dbgManual.rabatt_inklusive) fields.rabatt_inklusive = true;
      else if(!rbInk && _dbgManual.rabatt_inklusive) fields.rabatt_inklusive = null;
      if(!Object.keys(fields).length){ toast('Keine Änderungen'); return; }
      let d; try {
        const r = await fetch(api('/api/trips/'+_dbgTid+'/fields'), {method:'PATCH',
          headers:{'Content-Type':'application/json'}, body:JSON.stringify({fields})});
        d = await r.json().catch(()=>({})); if(!r.ok) throw d;
      } catch(e){
        toast(e&&e.error==='invalid_value'?('Ungültiger Wert für „'+(e.field||'?')+'"'):'Speichern fehlgeschlagen');
        return;
      }
      toast(d.warnings&&d.warnings.length?'Gespeichert — weiterhin nicht erkannt: '+d.warnings.join(', '):'Zuordnung gespeichert ✓');
      await loadTrips();
      showTripDebug(_dbgTid, _dbgTitle);
    }
    async function showTripDebug(id, title){
      let d=null;
      try { const r = await fetch(api('/api/trips/'+id+'/debug')); if(r.ok) d = await r.json(); } catch(e){}
      renderTripDebug(d, title||('Reise #'+id), id);
    }
    async function debugUpload(f){
      const fd = new FormData(); fd.append('pdf', f);
      let d=null;
      try { const r = await fetch(api('/api/trips/debug'), {method:'POST', body:fd}); if(r.ok) d = await r.json(); } catch(e){}
      renderTripDebug(d, f.name||'Upload');
    }

    async function delTrip(id){
      if(!confirm('Diese Reise inkl. gespeicherter PDF wirklich löschen?')) return;
      let ok=false;
      try { const r = await fetch(api('/api/trips/'+id), {method:'DELETE'}); ok = r.ok; } catch(e){}
      if(ok){ $('#trip-detail').style.display='none'; toast('Reise gelöscht'); loadTrips(); }
      else toast('Löschen fehlgeschlagen');
    }

    // Drag & Drop für PDF-Import
    (function(){
      const dz = $('#trips-drop'); if(!dz) return;
      ['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev, e=>{ e.preventDefault(); dz.classList.add('drag'); }));
      ['dragleave','drop'].forEach(ev=>dz.addEventListener(ev, e=>{ e.preventDefault(); dz.classList.remove('drag'); }));
      dz.addEventListener('drop', e=>{ const f=e.dataTransfer&&e.dataTransfer.files; if(f&&f.length){ const inp=$('#trip-file'); inp.files=f; importTrip(inp); } });
    })();

    // — Reiseziel-Picker (Drilldown) —
    async function loadDest(parent){
      try { return await fetch(api('/api/destinations'+(parent?('?parent='+parent):''))).then(r=>r.json()); }
      catch(e){ return null; }
    }
    async function openDestPicker(){
      const p = $('#dest-panel'); p.style.display='block';
      p.innerHTML = '<div class="cmp-load">Lade Reiseziele…</div>';
      destStack = []; destNode = null;
      destData = await loadDest(null);
      if(!destData){ p.innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Reiseziele nicht abrufbar.</div>'; return; }
      renderDest();
    }
    function renderDestRows(){
      const q = ($('#dest-search')?$('#dest-search').value:'').trim().toLowerCase();
      const items = (destData.items||[]).filter(it => !q || (it.label||'').toLowerCase().includes(q));
      const rows = items.map(it=>
        `<div class="dest-row" onclick="destDrill(${it.giata}, '${jsArg(it.label)}')">
           <span>${esc(it.label)}</span>
           <span><button class="btn sec" onclick="event.stopPropagation();selectDest(${it.giata}, '${jsArg(it.label)}')">wählen</button> <span class="chev">›</span></span>
         </div>`).join('');
      const box = $('#dest-rows'); if(box) box.innerHTML = rows ||
        `<div class="cmp-load">${q?'Kein Treffer für „'+esc(q)+'".':'Keine Unterregionen.'}</div>`;
    }
    // Globale Suche über ALLE Ebenen (z. B. „Kanarische Inseln" ohne erst Spanien
    // zu öffnen). Nutzt den gecachten Reiseziel-Index im Backend.
    let destSearchTimer = null, destSearchToken = 0;
    function destSearch(){
      const q = ($('#dest-search')?$('#dest-search').value:'').trim();
      clearTimeout(destSearchTimer);
      if(q.length < 2){ renderDestRows(); return; }  // kurze Eingabe → aktuelle Ebene
      destSearchTimer = setTimeout(async ()=>{
        const token = ++destSearchToken;
        const box = $('#dest-rows'); if(box) box.innerHTML = '<div class="cmp-load">Suche…</div>';
        let d=null;
        try { d = await fetch(api('/api/destinations/search?q='+encodeURIComponent(q))).then(r=>r.json()); } catch(e){}
        if(token !== destSearchToken || !box) return;  // veraltete Antwort verwerfen
        if(!d){ box.innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Suche fehlgeschlagen.</div>'; return; }
        if(!d.ready && d.building){ box.innerHTML = '<div class="cmp-load">Reiseziel-Index wird aufgebaut – einen Moment…</div>'; return; }
        const items = d.items||[];
        box.innerHTML = items.map(it=>
          `<div class="dest-row" onclick="selectDest(${it.giata}, '${jsArg(it.label)}')">
             <span>${esc(it.label)}${it.path?(' <span class="chev" style="font-weight:400;font-size:.82em">— '+esc(it.path)+'</span>'):''}</span>
             <span><button class="btn sec" onclick="event.stopPropagation();selectDest(${it.giata}, '${jsArg(it.label)}')">wählen</button></span>
           </div>`).join('') || `<div class="cmp-load">Kein Treffer für „${esc(q)}".</div>`;
      }, 250);
    }
    function renderDest(){
      const p = $('#dest-panel');
      const back = destStack.length?'<button class="btn sec" onclick="destBack()">‹ zurück</button>':'';
      const title = destNode?('<b>'+esc(destNode.label)+'</b>'):'<b>Reiseziel wählen</b>';
      const whole = destNode?(`<button class="btn" onclick="selectDest(${destNode.giata}, '${jsArg(destNode.label)}')">✓ Ganze Region wählen</button>`):'';
      p.innerHTML = `<div class="dest-head">${back}${title}${whole}
          <span style="flex:1"></span><button class="btn sec" onclick="$('#dest-panel').style.display='none'">schließen</button></div>
        <input type="text" id="dest-search" class="dest-search" placeholder="Reiseziel suchen (alle Ebenen, z. B. Kanarische Inseln)…" autocomplete="off" oninput="destSearch()">
        <div id="dest-rows"></div>`;
      renderDestRows();
      const si = $('#dest-search'); if(si) si.focus();
    }
    async function destDrill(giata, label){
      const sub = await loadDest(giata);
      if(!sub || !(sub.items&&sub.items.length)){ selectDest(giata, label); return; }
      destStack.push({node:destNode, data:destData});
      destNode = {giata, label}; destData = sub; renderDest();
    }
    function destBack(){ const prev=destStack.pop(); if(!prev) return; destNode=prev.node; destData=prev.data; renderDest(); }
    function selectDest(giata, label){
      srchDest = {giata, label};
      const b = $('#srch-dest'); b.textContent = label; b.classList.add('set');
      $('#dest-panel').style.display='none';
    }

    // — Gespeicherte Suchen (in der DB, geräteübergreifend) —
    let srchFavs = [];
    async function renderFavs(){
      try { const d = await fetch(api('/api/searches')).then(r=>r.json()); srchFavs = d.searches||[]; }
      catch(e){ srchFavs = []; }
      $('#srch-favsel').innerHTML = '<option value="">– gespeicherte Suche wählen –</option>'
        + srchFavs.map(f=>`<option value="${f.id}">${f.watch?'🔔 ':''}${esc(f.name)}</option>`).join('');
      favBtnState();
    }
    // „Änderungen speichern" nur aktiv, wenn eine gespeicherte Suche gewählt ist;
    // zusätzlich die Suchabo-Zeile (Beobachten + Schwellenpreis) befüllen/verstecken.
    function favBtnState(){
      const id = $('#srch-favsel').value;
      const b = $('#srch-favupd'); if(b) b.disabled = !id;
      const row = $('#srch-watchrow'); if(!row) return;
      const fav = srchFavs.find(x=>String(x.id)===String(id));
      if(!fav){ row.style.display='none'; return; }
      row.style.display='flex';
      row.classList.toggle('active', !!fav.watch);
      $('#watch-on').checked = !!fav.watch;
      $('#watch-max').value = fav.max_price!=null?Math.round(fav.max_price):'';
      const hits = fav.hits||[];
      let info = '';
      if(fav.watch){
        info = hits.length
          ? `<a href="#" onclick="showWatchHits(${fav.id});return false">${hits.length} Hotel(s) ≤ ${eur(fav.max_price)} — anzeigen</a>`
          : 'aktuell kein Hotel unter der Schwelle';
        if(fav.last_checked) info += ' · geprüft '+ago(fav.last_checked);
      }
      $('#watch-info').innerHTML = info;
    }
    async function watchSave(){
      const id = $('#srch-favsel').value;
      if(!id){ toast('Bitte eine gespeicherte Suche wählen'); return; }
      const on = $('#watch-on').checked;
      const mx = parseFloat($('#watch-max').value)||0;
      if(on && !(mx>0)){ toast('Bitte einen Schwellenpreis angeben'); return; }
      let ok=false;
      try {
        const r = await fetch(api('/api/searches/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({watch:on, max_price:mx||null})});
        ok = r.ok;
      } catch(e){}
      if(!ok){ toast('Speichern fehlgeschlagen'); return; }
      toast(on?'Suchabo aktiv — erster Lauf startet':'Suchabo deaktiviert');
      await renderFavs(); $('#srch-favsel').value=id; favBtnState();
      if(on) watchCheckNow(true);
    }
    async function watchCheckNow(quiet){
      const id = $('#srch-favsel').value; if(!id) return;
      if(quiet!==true) toast('Suchabo wird geprüft…');
      let r, d;
      try { r = await fetch(api('/api/searches/'+id+'/check'), {method:'POST'}); d = await r.json().catch(()=>({})); }
      catch(e){ toast('Prüfen fehlgeschlagen'); return; }
      if(r.status===400){ toast('Suchabo zuerst aktivieren (Beobachten + Schwellenpreis)'); return; }
      if(r.status===429){ toast('Bitte kurz warten ('+(d.retry_after||30)+'s) — gerade erst geprüft'); return; }
      if(!r.ok){ toast('Prüfen fehlgeschlagen — Suche nicht ausführbar'); return; }
      toast((d.hits||[]).length+' Hotel(s) unter der Schwelle'+(d.new?(' ('+d.new+' neu gemeldet)'):''));
      await renderFavs(); $('#srch-favsel').value=id; favBtnState();
      if((d.hits||[]).length) showWatchHits(parseInt(id));
    }
    // Treffer eines Suchabos in der normalen Ergebnisliste anzeigen
    function showWatchHits(favId){
      const fav = srchFavs.find(x=>x.id===favId); if(!fav) return;
      srchResults = fav.hits||[]; srchTotal = srchResults.length; srchFilter='';
      sortSearchResults(); renderSearch();
    }
    function curFav(){
      return { dest: srchDest, airport: $('#srch-airport').value,
        vom: $('#srch-vom').value, bis: $('#srch-bis').value,
        dur: $('#srch-dur').value, exact: $('#srch-exact').checked, trav: $('#srch-trav').value,
        tui: $('#srch-tui').checked, direct: $('#srch-direct').checked,
        adults_only: $('#srch-adults').checked,
        boards: [...document.querySelectorAll('.srch-board:checked')].map(c=>c.value),
        location: [...document.querySelectorAll('.srch-loc:checked')].map(c=>+c.value),
        airlines: selectedAirlines(),
        stars: $('#srch-stars').value, rec: $('#srch-rec').value,
        qual_off: $('#srch-qual-off').checked };
    }
    async function saveFav(){
      if(!srchDest){ toast('Bitte zuerst ein Reiseziel wählen'); return; }
      const name = prompt('Name für die gespeicherte Suche:', srchDest.label||'Suche');
      if(name===null) return;
      let ok=false, newId=null;
      try {
        const r = await fetch(api('/api/searches'), {method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({name: name.trim()||srchDest.label, payload: curFav()})});
        ok = r.ok; if(ok){ newId = (await r.json()).id; }
      } catch(e){}
      if(ok){ await renderFavs(); if(newId!=null) $('#srch-favsel').value=newId; favBtnState(); toast('Suche gespeichert'); }
      else { toast('Speichern fehlgeschlagen'); }
    }
    // Gewählte gespeicherte Suche überschreiben — ohne Namensabfrage (Upsert per Name).
    async function updateFav(){
      const id = $('#srch-favsel').value;
      if(id===''){ toast('Keine gespeicherte Suche gewählt'); return; }
      if(!srchDest){ toast('Bitte zuerst ein Reiseziel wählen'); return; }
      const fav = srchFavs.find(x=>String(x.id)===String(id)); if(!fav) return;
      let ok=false;
      try {
        const r = await fetch(api('/api/searches'), {method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({name: fav.name, payload: curFav()})});
        ok = r.ok;
      } catch(e){}
      if(ok){ await renderFavs(); $('#srch-favsel').value=id; favBtnState(); toast('Änderungen gespeichert'); }
      else { toast('Speichern fehlgeschlagen'); }
    }
    function loadFav(){
      favBtnState();
      const id = $('#srch-favsel').value; if(id==='') return;
      const fav = srchFavs.find(x=>String(x.id)===String(id)); if(!fav) return;
      const f = fav.payload||{};
      if(f.dest){ srchDest=f.dest; const b=$('#srch-dest'); b.textContent=f.dest.label; b.classList.add('set'); }
      if(f.airport){ ensureAirports().then(()=>{ $('#srch-airport').value=f.airport; }); }
      $('#srch-vom').value=f.vom||''; $('#srch-bis').value=f.bis||''; syncBisMin();
      $('#srch-dur').value=f.dur||7; $('#srch-exact').checked=!!f.exact; applyExact();
      $('#srch-trav').value=f.trav||2;
      $('#srch-tui').checked=f.tui!==false;
      $('#srch-direct').checked=!!f.direct;
      $('#srch-adults').checked=!!f.adults_only;
      document.querySelectorAll('.srch-board').forEach(c=>{ c.checked=(f.boards||[]).includes(c.value); });
      document.querySelectorAll('.srch-loc').forEach(c=>{ c.checked=(f.location||[]).includes(+c.value); });
      ensureAirlines().then(()=>setAirlines(f.airlines||[]));
      $('#srch-stars').value=f.stars||''; $('#srch-rec').value=f.rec||'';
      $('#srch-qual-off').checked=!!f.qual_off; toggleQualFilter();
    }
    async function delFav(){
      const id = $('#srch-favsel').value; if(id===''){ toast('Bitte eine gespeicherte Suche wählen'); return; }
      let ok=false;
      try { const r = await fetch(api('/api/searches/'+id), {method:'DELETE'}); ok = r.ok; } catch(e){}
      if(ok){ await renderFavs(); toast('Gespeicherte Suche gelöscht'); } else { toast('Löschen fehlgeschlagen'); }
    }

    async function runSearch(){
      const url = $('#srch-url').value.trim();
      const boards = [...document.querySelectorAll('.srch-board:checked')].map(c=>c.value);
      const location = [...document.querySelectorAll('.srch-loc:checked')].map(c=>+c.value);
      const body = { operator_tui: $('#srch-tui').checked, direct: $('#srch-direct').checked,
        adults_only: $('#srch-adults').checked, boards,
        location, airlines: selectedAirlines(),
        min_stars: $('#srch-qual-off').checked ? 0 : (parseFloat($('#srch-stars').value)||0),
        min_recommend: $('#srch-qual-off').checked ? 0 : (parseFloat($('#srch-rec').value)||0) };
      if(srchOfferId!=null){ body.offer_id = srchOfferId; }
      else if(url){ body.url = url; }
      else {
        if(!srchDest){ toast('Bitte ein Reiseziel wählen'); return; }
        const vom=$('#srch-vom').value, bis=$('#srch-bis').value;
        if(!vom||!bis){ toast('Bitte Zeitraum (von/bis) wählen'); return; }
        if(vom<isoPlus(0)){ toast('Startdatum liegt in der Vergangenheit'); return; }
        if(bis<vom){ toast('„bis" muss nach „von" liegen'); return; }
        const exact=$('#srch-exact').checked;
        const win=nightsBetween(vom,bis), dur=parseInt($('#srch-dur').value)||7;
        if(!exact && win!=null && dur>win){ toast(`Hinweis: ${dur} Nächte passen nicht in den Zeitraum (${win} Tage) – evtl. keine Treffer.`); }
        localStorage.setItem('tw-airport', $('#srch-airport').value);
        Object.assign(body, { region: srchDest.giata, start: vom, end: bis,
          duration: exact ? 'exact' : dur, travellers: parseInt($('#srch-trav').value)||2,
          airport: $('#srch-airport').value });
      }
      srchLastBody = body;
      $('#srch-body').innerHTML = progBar('Suche läuft…');
      let r, d;
      try { r = await fetch(api('/api/search'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); d = await r.json(); }
      catch(e){ $('#srch-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Suche fehlgeschlagen.</div>'; return; }
      if(r.status===400 && d.error==='no_region'){ $('#srch-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ '+(srchOfferId!=null?'Region zu diesem Angebot nicht ermittelbar.':'Keine Region erkannt.')+'</div>'; return; }
      if(r.status===429){ $('#srch-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Bitte kurz warten ('+(d.retry_after||3)+'s) und erneut suchen.</div>'; return; }
      if(r.status===404){ $('#srch-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Angebot nicht gefunden.</div>'; return; }
      if(r.status===400 && d.note){ $('#srch-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ '+esc(d.note)+'</div>'; return; }
      if(r.status===400){ $('#srch-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Keine gültige Eingabe.</div>'; return; }
      if(!r.ok){ $('#srch-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Suche fehlgeschlagen.</div>'; return; }
      srchResults = d.results||[]; srchTotal = d.total||srchResults.length; srchFilter = '';
      srchResults.forEach(r=>{ r._key = String(r.giata||r.name); });
      srCmpSelected = new Set();
      sortSearchResults(); renderSearch();
    }

    // "Mehr laden": die Such-API liefert pro Aufruf nur resultsPerPage (50) Treffer,
    // nicht alle auf einmal — derselbe Such-Body wird mit offset=bereits geladene
    // Treffer erneut abgeschickt (resultsFrom serverseitig, siehe scraper.py).
    let srchLoadingMore = false;
    async function loadMoreSearch(){
      if(srchLoadingMore || !srchLastBody || srchResults.length>=srchTotal) return;
      srchLoadingMore = true;
      renderSearch();
      const body = Object.assign({}, srchLastBody, {offset: srchResults.length});
      let r, d;
      try { r = await fetch(api('/api/search'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); d = await r.json(); }
      catch(e){ srchLoadingMore = false; toast('Nachladen fehlgeschlagen.'); renderSearch(); return; }
      if(!r.ok){ srchLoadingMore = false; toast(d.note || 'Nachladen fehlgeschlagen.'); renderSearch(); return; }
      const fresh = d.results || [];
      fresh.forEach(x=>{ x._key = String(x.giata||x.name); });
      // Gegen bereits geladene _key dedupen — TUIs Reihenfolge kann sich zwischen
      // zwei Aufrufen bei Preis-Gleichstand minimal verschieben.
      const known = new Set(srchResults.map(x=>x._key));
      srchResults = srchResults.concat(fresh.filter(x=>!known.has(x._key)));
      srchTotal = d.total || srchTotal;
      srchLoadingMore = false;
      sortSearchResults(); renderSearch();
    }

    // Preis-Leistungs-Score: 60% Weiterempfehlung (HolidayCheck) + 40% Preis/Nacht,
    // beide auf min/max der AKTUELLEN Trefferliste normiert (0-1) — nur so
    // vergleichbar, ein absoluter Preis sagt ohne Kontext (Region/Saison/Sterne)
    // nichts über "günstig" aus. Weiterempfehlung ohne ausreichend Bewertungen
    // (<15) wird zur Basislinie (70%) gedämpft, sonst verzerrt 1 Fünf-Sterne-Review
    // den Score. Fixe Gewichtung (kein User-Regler) — bewusst einfach gehalten.
    function _valueScores(list){
      const withPn = list.filter(r=>r.nights && r.price!=null);
      if(!withPn.length) return;
      const pns = withPn.map(r=>r.price/r.nights);
      const pnMin = Math.min(...pns), pnMax = Math.max(...pns);
      list.forEach(r=>{
        if(!r.nights || r.price==null){ r._value = null; return; }
        const pn = r.price/r.nights;
        const priceNorm = pnMax>pnMin ? (pn-pnMin)/(pnMax-pnMin) : 0;
        let rec = r.recommendation!=null ? r.recommendation : 70;
        if(r.recommendation!=null && (r.reviews||0) < 15) rec = rec*0.5 + 70*0.5;
        r._value = 0.6*(rec/100) + 0.4*(1-priceNorm);
      });
    }
    function sortSearchResults(){
      const num=(v,d)=>v==null?d:v;
      const a=srchResults;
      if(srchSort==='price') a.sort((x,y)=>num(x.price,1e9)-num(y.price,1e9));
      else if(srchSort==='rec') a.sort((x,y)=>num(y.recommendation,-1)-num(x.recommendation,-1));
      else if(srchSort==='stars') a.sort((x,y)=>num(y.stars,-1)-num(x.stars,-1));
      else if(srchSort==='pernight') a.sort((x,y)=>(num(x.price,1e9)/(x.nights||1))-(num(y.price,1e9)/(y.nights||1)));
      else if(srchSort==='value'){ _valueScores(a); a.sort((x,y)=>num(y._value,-1)-num(x._value,-1)); }
    }
    function changeSrchSort(v){ srchSort=v; localStorage.setItem('tw-srch-sort',v); sortSearchResults(); renderSearchRows(); }
    function filterSearch(v){ srchFilter=v; renderSearchRows(); }

    function srItem(r,i){
      const stars = r.stars?('<span class="stars">'+'★'.repeat(r.stars)+'</span> '):'';
      const rec = r.recommendation!=null?(' · '+r.recommendation+'% 👍'+(r.reviews?(' ('+r.reviews.toLocaleString('de-DE')+')'):'')):'';
      const old = (r.old_price&&r.old_price>r.price)?('<span class="sr-old">'+eur(r.old_price)+'</span>'+(r.discount?'<span class="sr-disc">-'+r.discount+'%</span>':'')):'';
      const perNight = (r.nights && r.price!=null) ? eur(r.price/r.nights)+'/Nacht' : '';
      const img = r.image?('<img class="sr-img" src="'+esc(r.image)+'" loading="lazy" alt="">'):'<div class="sr-img"></div>';
      return `<div class="sr-item">
        <label class="sr-cmp ai-feature" title="Für KI-Vergleich auswählen">
          <input type="checkbox" class="sr-cmp-chk" data-key="${esc(r._key)}" ${srCmpSelected.has(r._key)?'checked':''}>
        </label>
        ${img}
        <div class="sr-main">
          <div class="sr-name">${stars}${esc(r.name)}${r.tracked?'<span class="tracked">✓ getrackt</span>':''}</div>
          <div class="sr-meta">📍 ${esc(r.location)}${r.country?(' · '+esc(r.country)):''}${rec}</div>
          <div class="sr-meta">${esc(r.board)} · ${r.nights} Nächte · ab ${fmtD(r.date)}</div>
          ${(r.locations&&r.locations.length)?'<div class="sr-locs">'+r.locations.map(l=>'<span class="tag-pill">'+esc(l)+'</span>').join('')+'</div>':''}
          ${r.coupon?'<div class="sr-coupon" title="TUI zeigt für dieses Hotel aktuell einen Aktionscode/Coupon an (Wert je nach Reisepreis, siehe tui.com)">% Aktionscode möglich</div>':''}
        </div>
        <div class="sr-pricecol">
          <div class="sr-price">${eur(r.price)}</div>
          <div class="sr-meta">p. P.${old?(' · '+old):''}</div>
          ${perNight?`<div class="sr-meta">${perNight}</div>`:''}
          <div class="sr-acts">
            <a class="btn sec" href="${esc(r.offer_url)}" target="_blank" rel="noopener">Öffnen</a>
            <button class="btn sec ai-feature" onclick="openAiSummary(${i})" title="Ausführliche KI-Einschätzung: Lage, Zimmer, Restaurants, Pool, Ausstattung">🤖 KI-Fazit</button>
            <button class="btn" id="srt-${i}" onclick="trackResult(${i})" title="${r.tracked?'Bereits getrackt – mit den aktuellen Suchparametern (z. B. anderer Zeitraum) erneut hinzufügen':'Hotel ins Tracking übernehmen'}">${r.tracked?'+ Tracken':'Tracken'}</button>
          </div>
        </div>
      </div>`;
    }
    function renderSearchRows(){
      const box=$('#srch-rows'); if(!box) return;
      const q=(srchFilter||'').trim().toLowerCase();
      const shown=[];
      srchResults.forEach((r,i)=>{ if(!q || ((r.name||'')+' '+(r.location||'')+' '+(r.country||'')+' '+(r.board||'')).toLowerCase().includes(q)) shown.push([r,i]); });
      const cnt=$('#srch-count'); if(cnt) cnt.textContent = q ? (shown.length+' von '+srchResults.length) : String(srchResults.length);
      box.innerHTML = shown.length ? shown.map(([r,i])=>srItem(r,i)).join('')
        : '<div class="cmp-load">Kein Treffer für „'+esc(srchFilter.trim())+'".</div>';
    }
    function renderSearch(){
      if(!srchResults.length){ $('#srch-body').innerHTML = '<div class="cmp-load">Keine Treffer für die gewählten Filter.</div>'; return; }
      const sortSel = `<select onchange="changeSrchSort(this.value)" title="Sortierung">
          <option value="price"${srchSort==='price'?' selected':''}>Preis aufsteigend</option>
          <option value="pernight"${srchSort==='pernight'?' selected':''}>Preis/Nacht</option>
          <option value="rec"${srchSort==='rec'?' selected':''}>Weiterempfehlung</option>
          <option value="stars"${srchSort==='stars'?' selected':''}>Sterne</option>
          <option value="value"${srchSort==='value'?' selected':''} title="60% Weiterempfehlung + 40% Preis/Nacht">Preis-Leistung</option>
        </select>`;
      const head = `<div class="srch-head"><span><b id="srch-count">${srchResults.length}</b> Treffer${(srchTotal>srchResults.length)?(' (von '+srchTotal+' in der Region)'):''}</span>
         <input type="text" id="srch-filter" class="srch-listfilter" placeholder="In Treffern suchen…" autocomplete="off" oninput="filterSearch(this.value)" value="${esc(srchFilter)}">
         <span style="flex:1"></span>Sortieren: ${sortSel}
         <button class="btn sec" onclick="track3()" title="Günstigstes, mittleres und teuerstes Hotel aus den Treffern automatisch für den Preisverlauf tracken (keine Benachrichtigungen)">📊 3 tracken</button>
         <button class="btn sec" onclick="trackAll()">Alle tracken</button></div>
        <div id="cmp-bar" class="cmp-foot ai-feature" style="display:none">
          <span class="hint" style="flex:1;min-width:180px"><b id="cmp-count">0</b> Hotel(s) für KI-Vergleich ausgewählt (max. 5)</span>
          <button class="btn sec" onclick="clearCmp()">Auswahl leeren</button>
          <button class="btn" onclick="openAiCompare()">🤖 Vergleichen</button>
        </div>
        <div id="srch-rows"></div>
        ${(srchResults.length<srchTotal)?`<div class="srch-more">
          <button class="btn sec" onclick="loadMoreSearch()" ${srchLoadingMore?'disabled':''}>${srchLoadingMore?'Lädt…':('Mehr laden ('+(srchTotal-srchResults.length)+' weitere)')}</button>
        </div>`:''}`;
      $('#srch-body').innerHTML = head;
      renderSearchRows();
      updateCmpBar();
    }
    $('#srch-body').addEventListener('change', e=>{
      const chk = e.target.closest('.sr-cmp-chk'); if(!chk) return;
      const key = chk.dataset.key;
      if(chk.checked){
        if(srCmpSelected.size>=5){ chk.checked=false; toast('Maximal 5 Hotels für den Vergleich'); return; }
        srCmpSelected.add(key);
      } else srCmpSelected.delete(key);
      updateCmpBar();
    });
    function updateCmpBar(){
      const bar = $('#cmp-bar'); if(!bar) return;
      const n = srCmpSelected.size;
      bar.style.display = n ? 'flex' : 'none';
      const c = $('#cmp-count'); if(c) c.textContent = String(n);
    }
    function clearCmp(){ srCmpSelected = new Set(); renderSearchRows(); updateCmpBar(); }

    async function trackResult(i){
      const r = srchResults[i]; if(!r) return;
      const btn = document.getElementById('srt-'+i);
      // Hotel kann mehrfach getrackt werden (andere Zeiträume/Parameter) → Button bleibt
      // nutzbar. Das Backend lehnt nur exakt identische Angebote ab (409).
      const restore = ()=>{ if(btn){ btn.disabled=false; btn.textContent = r.tracked?'+ Tracken':'Tracken'; } };
      if(btn){ btn.disabled=true; btn.textContent='…'; }
      let resp;
      // start:false — Angebot wird angelegt, aber erst nach der Zimmerauswahl
      // (pickRoom oder Schließen des Dialogs, siehe closeRooms) tatsächlich geprüft.
      try { resp = await fetch(api('/api/offers'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:r.offer_url, label:r.name, image:r.image, start:false, tags:r.location?[r.location]:[]})}); }
      catch(e){ toast('Fehler beim Hinzufügen'); restore(); return; }
      if(resp.status===409){ toast('Dieses Angebot wird mit genau diesen Parametern bereits verfolgt'); restore(); return; }
      if(!resp.ok){ toast('Fehler beim Hinzufügen'); restore(); return; }
      toast('Angebot angelegt – bitte Zimmer wählen');
      // Zimmerauswahl anbieten; erst danach beginnt die eigentliche Prüfung.
      try {
        const d = await resp.json();
        if(d && d.id){ pendingStartId = d.id; openRooms(d.id); }
      } catch(e){}
      r.tracked=true; restore();
      loadOffers();
    }
    async function trackAll(){
      const todo = srchResults.filter(r=>!r.tracked);
      if(!todo.length){ toast('Alle bereits getrackt'); return; }
      if(!confirm(todo.length+' Hotels ins Tracking übernehmen?')) return;
      for(const r of todo){
        try { await fetch(api('/api/offers'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:r.offer_url, label:r.name, image:r.image, tags:r.location?[r.location]:[]})}); r.tracked=true; } catch(e){}
      }
      toast(todo.length+' Hotels getrackt'); renderSearch(); loadOffers();
    }
    // Für den reinen Preisverlauf/Markttrend: günstigstes, mittleres und teuerstes
    // Hotel aus den aktuellen Treffern automatisch tracken — als history_only (kein
    // Zimmerauswahl-Dialog, keine Benachrichtigungen, siehe historyOfferCard()).
    async function track3(){
      const pool = srchResults.filter(r=>r.price!=null);
      if(pool.length<3){ toast('Mindestens 3 Treffer mit Preis nötig'); return; }
      const byPrice = [...pool].sort((a,b)=>a.price-b.price);
      const picks = [byPrice[0], byPrice[Math.floor(byPrice.length/2)], byPrice[byPrice.length-1]];
      if(!confirm('Günstigstes, mittleres und teuerstes Hotel für den Preisverlauf tracken (ohne Benachrichtigungen)?')) return;
      for(const r of picks){
        try { await fetch(api('/api/offers'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:r.offer_url, label:r.name, image:r.image, history_only:true, tags:r.location?[r.location]:[]})}); r.tracked=true; } catch(e){}
      }
      toast('3 Hotels für den Preisverlauf getrackt'); renderSearch(); loadOffers();
    }

    // ── KI-Hotel-Fazit & -Vergleich (Lage, Zimmer, Restaurants, Pool, Ausstattung) ─
    // [n](url) -> anklickbare Zitat-Nummer (Perplexity-Quellenangaben, siehe
    // ai_client.py::_perplexity_linkify_citations); läuft vor **bold**, damit ein
    // Fettdruck rund um eine Zitat-Klammer die Link-Erkennung nicht stört.
    function aiInline(s){
      s = s.replace(/\[(\d+)\]\((https?:\/\/[^\s")]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener" class="ai-cite">[$1]</a>');
      return s.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>');
    }
    function aiTableRow(l){ return l.trim().replace(/^\||\|$/g,'').split('|').map(c=>aiInline(c.trim())); }
    function aiMdLite(text){
      const lines = esc(text).split('\n');
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
    function aiErrorMsg(err){
      return err==='no_api_key' ? 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt.'
        : err==='ai_refused' ? 'Die KI konnte keine Einschätzung liefern.'
        : err==='invalid' ? 'Bitte mindestens 2 Hotels für den Vergleich auswählen.'
        : 'KI-Zusammenfassung fehlgeschlagen.';
    }
    // 'ai_failed'/'ai_empty'/'ai_refused' und Netzwerkfehler sind meist transient
    // (z. B. 503 UNAVAILABLE bei hoher Last, egal ob Claude oder Gemini) — dafür
    // einen Retry-Button anbieten. Validierungsfehler (no_data/invalid/no_api_key/…)
    // lösen sich durch bloßes Wiederholen nicht, dafür kein Button.
    function aiRetryable(err){ return err==='ai_failed' || err==='ai_refused' || err==='ai_empty' || err==null; }
    let _aiRetryFn = null;
    function aiRetry(){ if(_aiRetryFn) _aiRetryFn(); }
    function aiErrorBlock(msg, retryable){
      const btn = retryable ? ' <button class="btn sec" onclick="aiRetry()">🔄 Erneut versuchen</button>' : '';
      return '<div class="cmp-load" style="color:var(--amber)">⚠ '+esc(msg)+btn+'</div>';
    }
    // ── KI-Prompt-Vorschau (Option „KI-Prompt vor dem Senden anzeigen") ────────
    // Ist die Add-on-Option aktiv, antwortet der Server statt mit dem Ergebnis
    // mit {prompt_preview} (siehe ai_routes._prompt_preview_response). Zeigt den
    // Prompt editierbar im #ai-body-Bereich; bestätigter/editierter Text geht als
    // _prompt_override zurück, _prompt_confirmed=true überspringt die Vorschau
    // beim zweiten Aufruf. Ist die Option aus, liefert der Server sofort das
    // Ergebnis und diese Funktion greift nie ein.
    // Generischer Kern: `onPreview(promptText)` rendert die Vorschau-UI (Ort ist
    // Aufrufer-spezifisch — großes Modal vs. kleine Folgefrage-Box) und liefert
    // den editierten Text oder null bei Abbruch. `onConfirmed()` rendert den
    // Lade-Zustand für den zweiten (echten) Aufruf.
    async function aiFetchPreviewCore(url, opts, onPreview, onConfirmed){
      opts = opts || {};
      let resp = await fetch(url, opts);
      let d = await resp.json();
      if(resp.ok && d && d.prompt_preview){
        const edited = await onPreview(d.prompt_preview);
        if(edited === null) return {cancelled:true};
        let body = {};
        if(opts.body){ try { body = JSON.parse(opts.body); } catch(e){} }
        body._prompt_confirmed = true;
        body._prompt_override = edited;
        if(onConfirmed) onConfirmed();
        resp = await fetch(url, Object.assign({}, opts, {
          method: 'POST', body: JSON.stringify(body),
          headers: Object.assign({'Content-Type':'application/json'}, opts.headers||{}),
        }));
        d = await resp.json();
      }
      return {resp, d};
    }
    function promptPreviewBoxHtml(promptText){
      return `<textarea id="ai-pp-ta" style="width:100%;min-height:200px;font-family:monospace;font-size:.78rem;box-sizing:border-box;resize:vertical">${esc(promptText)}</textarea>
        <div style="display:flex;gap:8px;margin-top:8px;justify-content:flex-end">
          <button class="btn sec" id="ai-pp-cancel">Abbrechen</button>
          <button class="btn" id="ai-pp-send">🚀 Senden</button>
        </div>`;
    }
    function showPromptPreview(promptText){
      return new Promise(resolve=>{
        $('#ai-body').innerHTML = '<div class="hint" style="margin-bottom:8px">📝 Prompt vor dem Senden prüfen/bearbeiten:</div>'
          + promptPreviewBoxHtml(promptText);
        $('#ai-foot').style.display = 'none';
        $('#ai-pp-cancel').onclick = () => { closeAiSummary(); resolve(null); };
        $('#ai-pp-send').onclick = () => resolve($('#ai-pp-ta').value);
      });
    }
    async function aiFetchPreviewable(url, opts, loadingLabel){
      return aiFetchPreviewCore(url, opts, showPromptPreview,
        () => { $('#ai-body').innerHTML = progBar(loadingLabel || 'KI arbeitet…'); });
    }
    // Folgefrage-Variante: rendert die Vorschau in #ai-followup-status statt den
    // ganzen #ai-body zu ersetzen — die bisherige Konversation (#ai-thread) bleibt
    // dabei sichtbar stehen.
    function showFollowupPromptPreview(promptText){
      return new Promise(resolve=>{
        const status = $('#ai-followup-status');
        status.innerHTML = '<div class="hint" style="margin:8px 0 6px">📝 Folgefrage vor dem Senden prüfen/bearbeiten:</div>'
          + promptPreviewBoxHtml(promptText);
        $('#ai-pp-cancel').onclick = () => resolve(null);
        $('#ai-pp-send').onclick = () => resolve($('#ai-pp-ta').value);
      });
    }
    function hotelFacts(r){
      return {name:r.name, giata:r.giata, location:r.location, country:r.country,
        stars:r.stars, recommendation:r.recommendation, reviews:r.reviews, board:r.board,
        price:r.price, nights:r.nights, date:r.date};
    }
    function aiUsageLine(usage, cached, totals){
      let html = '';
      if(usage){
        const parts = [(usage.input_tokens||0)+' Input-', (usage.output_tokens||0)+' Output-Tokens'];
        if(usage.cache_read_input_tokens) parts.push(usage.cache_read_input_tokens+' aus Prompt-Cache');
        if(usage.web_search_requests) parts.push('🔍 '+usage.web_search_requests+' Websuchen');
        if(usage.estimated_usd != null) parts.push('≈ '+fmtUsd(usage.estimated_usd));
        html += '<div class="hint" style="margin-top:14px;padding-top:10px;border-top:1px solid var(--border)">🔢 '
          + parts.join(' · ') + (cached?' · Ergebnis aus Zwischenspeicher (bis zu 24 Std. alt)':'') + '</div>';
      }
      if(totals && totals.calls){
        html += '<div class="hint" style="margin-top:4px">Σ gesamt (dauerhaft gespeichert): '+totals.calls+' Aufrufe · '
          + (totals.input_tokens+totals.output_tokens).toLocaleString('de-DE')+' Tokens · geschätzt '
          + fmtUsd(totals.estimated_usd)+'</div>';
        if(totals.today || totals.month){
          html += '<div class="hint" style="margin-top:2px">Davon heute '+fmtUsd(totals.today&&totals.today.estimated_usd)
            +' · diesen Monat '+fmtUsd(totals.month&&totals.month.estimated_usd)+'</div>';
        }
      }
      return html;
    }
    let aiCurrentId = null;   // ID in ai_analyses des gerade angezeigten Ergebnisses (fürs E-Mail-Senden)
    // Folgefrage-Eingabe unter jedem Freitext-KI-Ergebnis: eigener Container (statt
    // alles bei jeder Runde neu zu rendern) — #ai-thread sammelt die Konversation
    // sichtbar an, #ai-usage-line-wrap/#ai-followup-status werden gezielt ersetzt.
    function aiFollowupBoxHtml(){
      return '<div style="margin-top:14px;padding-top:10px;border-top:1px solid var(--border);display:flex;gap:8px">'
        + '<input id="ai-followup-q" type="text" placeholder="Folgefrage stellen…" style="flex:1;min-width:0" '
        + 'onkeydown="if(event.key===\'Enter\'){ event.preventDefault(); submitAiFollowup(); }">'
        + '<button class="btn sec" onclick="submitAiFollowup()" title="Folgefrage senden">➤</button></div>';
    }
    // Baut die sichtbare Konversation aus der gespeicherten `conversation`-Liste
    // ([{role,content}, ...], siehe ai_routes.py::_ai_followup_messages) für ein
    // erneutes Öffnen aus dem KI-Verlauf. conv[0] ist der ursprüngliche, technische
    // Prompt (Hotel-Fakten + Instruktionen) — wird NICHT angezeigt, das war nie eine
    // echte Nutzerfrage. conv[1] ist die ursprüngliche Antwort, ab conv[2] wechseln
    // sich echte Folgefragen ('Du: …') und ihre Antworten ab.
    function aiThreadHtmlFromConversation(conv){
      let html = '';
      for(let i = 1; i < conv.length; i++){
        const turn = conv[i];
        html += turn.role === 'user'
          ? '<div class="hint" style="margin-top:16px"><b>Du:</b> '+esc(turn.content)+'</div>'
          : aiMdLite(turn.content);
      }
      return html;
    }
    function renderAiResult(box, result){
      let conv = null;
      if(result.conversation){
        try { conv = JSON.parse(result.conversation); } catch(e){ conv = null; }
      }
      const threadHtml = Array.isArray(conv) && conv.length > 2
        ? aiThreadHtmlFromConversation(conv) : aiMdLite(result.summary);
      $(box).innerHTML = '<div id="ai-thread">'+threadHtml+'</div>'
        + '<div id="ai-followup-status"></div>'
        + '<div id="ai-usage-line-wrap">'+aiUsageLine(result.usage, result.cached, result.totals)+'</div>'
        + aiFollowupBoxHtml();
      $('#ai-foot').style.display = 'flex';
      aiCurrentId = result.id != null ? result.id : null;
    }
    async function submitAiFollowup(){
      const input = $('#ai-followup-q');
      const q = (input && input.value || '').trim();
      if(!q){ toast('Bitte eine Frage eingeben'); return; }
      if(aiCurrentId == null){ toast('Folgefrage hier nicht möglich'); return; }
      const thread = $('#ai-thread'), status = $('#ai-followup-status');
      if(!thread || !status) return;
      input.disabled = true;
      const bubble = document.createElement('div');
      bubble.className = 'hint';
      bubble.style.marginTop = '16px';
      bubble.innerHTML = '<b>Du:</b> '+esc(q);
      thread.appendChild(bubble);
      status.innerHTML = progBar(aiProviderName()+' antwortet…');
      let resp, d;
      try {
        const r = await aiFetchPreviewCore(api('/api/ai/history/'+aiCurrentId+'/followup'), {method:'POST',
          headers:{'Content-Type':'application/json'}, body: JSON.stringify({question: q})},
          showFollowupPromptPreview, () => { status.innerHTML = progBar(aiProviderName()+' antwortet…'); });
        if(r.cancelled){ bubble.remove(); status.innerHTML = ''; input.disabled = false; input.value = q; return; }
        resp = r.resp; d = r.d;
      } catch(e){
        status.innerHTML = aiErrorBlock('Folgefrage fehlgeschlagen.', false);
        input.disabled = false;
        return;
      }
      if(!resp.ok){
        status.innerHTML = aiErrorBlock(d.error==='unsupported_kind' ? 'Für dieses Ergebnis sind keine Folgefragen möglich.'
          : d.error==='no_prompt' ? (d.note||'Keine Konversation gespeichert.') : aiErrorMsg(d.error), false);
        input.disabled = false;
        return;
      }
      thread.innerHTML += aiMdLite(d.summary);
      status.innerHTML = '';
      const usageWrap = $('#ai-usage-line-wrap');
      if(usageWrap) usageWrap.innerHTML = aiUsageLine(d.usage, false, d.totals);
      input.value = '';
      input.disabled = false;
      input.focus();
    }
    function scoreColor(score){ return score>=70 ? 'var(--green)' : score>=40 ? 'var(--amber)' : 'var(--red)'; }
    // Score-Verlauf (ai_analyses, per offer_id verknüpft): Delta zur Vor-Messung +
    // Mini-Sparkline. Ab 2 Messungen sichtbar; Tooltip listet alle Punkte.
    function scoreHistoryHtml(hist){
      if(!hist || hist.length < 2) return '';
      const prev = hist[hist.length-2], cur = hist[hist.length-1];
      const d = cur.score - prev.score;
      const dCol = d>0 ? 'var(--green)' : d<0 ? 'var(--red)' : 'var(--muted)';
      const pts = hist.map((h,i)=>`${(i/(hist.length-1))*100},${28-(h.score/100)*26}`).join(' ');
      const tip = hist.map(h=>`${new Date(h.ts*1000).toLocaleDateString('de-DE')}: ${h.score}`).join('\n');
      return `<div class="hint" style="margin-top:8px;display:flex;align-items:center;gap:8px" title="${esc(tip)}">
          <span>Verlauf: ${prev.score} → <b style="color:${scoreColor(cur.score)}">${cur.score}</b>
          <b style="color:${dCol}">(${d>0?'+':''}${d})</b> · ${hist.length} Messungen</span>
          <svg width="120" height="30" viewBox="0 0 100 30" preserveAspectRatio="none" style="flex-shrink:0">
            <polyline points="${pts}" fill="none" stroke="${scoreColor(cur.score)}" stroke-width="2"
              vector-effect="non-scaling-stroke"/></svg>
        </div>`;
    }
    function scoreErwartung(v){ return v==='steigend' ? '↗ steigend' : v==='fallend' ? '↘ fallend' : '→ gleich'; }
    // Buchungsscore/Region-Ausblick: strukturiertes Ergebnis (kein Markdown-Fazit) —
    // eigene Darstellung mit Score-Balken + Daten-/Annahme-Kennzeichnung je Begründung.
    function renderBookingScore(box, payload){
      const r = payload.result;
      const empfLabel = {jetzt_buchen:'✅ Jetzt buchen', beobachten:'👀 Beobachten', warten:'⏳ Warten'}[r.empfehlung] || r.empfehlung;
      const begr = (r.begruendung||[]).map(b=>
        `<li><span class="hint" style="text-transform:uppercase;font-size:.68rem">[${b.typ==='daten'?'Daten':'Annahme'}]</span> ${esc(b.text)}</li>`).join('');
      $(box).innerHTML = `
        <div class="score-head">
          <div class="score-num" style="color:${scoreColor(r.score)}">${r.score}</div>
          <div>
            <div class="score-empf">${empfLabel}</div>
            <div class="hint">Vertrauen: ${r.vertrauen}%</div>
          </div>
        </div>
        <div class="twprog" style="max-width:none;margin:10px 0"><i style="width:${r.score}%;background:${scoreColor(r.score)}"></i></div>
        <div class="hint">Erwartung 7 Tage: ${scoreErwartung(r.erwartung_7_tage)} · 30 Tage: ${scoreErwartung(r.erwartung_30_tage)}</div>
        ${scoreHistoryHtml(payload.history)}
        <ul class="ai-list" style="margin-top:10px">${begr}</ul>
        ${aiUsageLine(payload.usage, payload.cached, payload.totals)}`;
      $('#ai-foot').style.display = 'none';
      aiCurrentId = payload.id != null ? payload.id : null;
    }
    async function openBookingScore(id){
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      $('#ai-title').textContent = '🔮 Buchungsscore';
      $('#ai-sub').textContent = o.label || o.hotel || ('Angebot #'+id);
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      const attempt = async () => {
        $('#ai-body').innerHTML = progBar(aiProviderName()+' berechnet den Buchungsscore…');
        let resp, d;
        try {
          const r = await aiFetchPreviewable(api('/api/ai/booking-score/'+id), {method:'POST'}, 'KI berechnet den Buchungsscore…');
          if(r.cancelled) return;
          resp = r.resp; d = r.d;
        } catch(e){ _aiRetryFn = attempt; $('#ai-body').innerHTML = aiErrorBlock('Buchungsscore fehlgeschlagen.', true); return; }
        if(!resp.ok){
          const retryable = aiRetryable(d.error);
          const msg = d.error==='no_price' ? 'Noch kein Preis für dieses Angebot vorhanden.' : aiErrorMsg(d.error);
          _aiRetryFn = retryable ? attempt : null;
          $('#ai-body').innerHTML = aiErrorBlock(msg, retryable);
          return;
        }
        renderBookingScore('#ai-body', d);
      };
      attempt();
    }
    async function openRegionOutlook(idx){
      const r = _marketTrendData && _marketTrendData.by_region[idx]; if(!r) return;
      closeMarketTrend();   // beide Modals teilen sich z-index — sonst liegt Markttrend obendrauf
      $('#ai-title').textContent = '🔮 Region-Ausblick';
      $('#ai-sub').textContent = r.region;
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      const attempt = async () => {
        $('#ai-body').innerHTML = progBar(aiProviderName()+' schätzt die Destination ein…');
        let resp, d;
        try {
          const rp = await aiFetchPreviewable(api('/api/ai/region-outlook'), {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({region: r.region})}, 'KI schätzt die Destination ein…');
          if(rp.cancelled) return;
          resp = rp.resp; d = rp.d;
        } catch(e){ _aiRetryFn = attempt; $('#ai-body').innerHTML = aiErrorBlock('Region-Ausblick fehlgeschlagen.', true); return; }
        if(!resp.ok){
          const retryable = aiRetryable(d.error);
          const msg = d.error==='no_data' ? 'Noch zu wenig Markttrend-Daten für diese Destination.' : aiErrorMsg(d.error);
          _aiRetryFn = retryable ? attempt : null;
          $('#ai-body').innerHTML = aiErrorBlock(msg, retryable);
          return;
        }
        renderBookingScore('#ai-body', d);
      };
      attempt();
    }
    async function openCalendarOutlook(){
      if(calId==null) return;
      const id = calId;   // vor closeCalendar() sichern, das setzt calId=null
      const offer = (curOffers||[]).find(x=>x.id===id) || {};
      closeCalendar();   // gleicher z-index wie #ai-bg, siehe openRegionOutlook()
      $('#ai-title').textContent = '📅 Kalender-Analyse';
      $('#ai-sub').textContent = offer.label || offer.hotel || ('Angebot #'+id);
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      const attempt = async () => {
        $('#ai-body').innerHTML = progBar(aiProviderName()+' fasst die Kalenderpreise zusammen…');
        let resp, d;
        try {
          const r = await aiFetchPreviewable(api('/api/ai/calendar-outlook/'+id), {method:'POST'}, 'KI fasst die Kalenderpreise zusammen…');
          if(r.cancelled) return;
          resp = r.resp; d = r.d;
        } catch(e){ _aiRetryFn = attempt; $('#ai-body').innerHTML = aiErrorBlock('Kalender-Analyse fehlgeschlagen.', true); return; }
        if(!resp.ok){
          const retryable = aiRetryable(d.error);
          const msg = d.error==='no_data' ? 'Noch keine Kalenderdaten für dieses Angebot vorhanden.' : aiErrorMsg(d.error);
          _aiRetryFn = retryable ? attempt : null;
          $('#ai-body').innerHTML = aiErrorBlock(msg, retryable);
          return;
        }
        renderAiResult('#ai-body', d);
      };
      attempt();
    }
    function exportAiPdf(){
      const w = window.open('', '_blank');
      if(!w){ toast('Pop-up blockiert – bitte für TUIWatch erlauben'); return; }
      const title = $('#ai-title').textContent, sub = $('#ai-sub').textContent;
      // #ai-thread + Usage-Zeile statt des rohen #ai-body — sonst landet die
      // Folgefrage-Eingabezeile (<input>/Button) mit im PDF. Booking-Score-Ansicht
      // hat kein #ai-thread (renderBookingScore rendert direkt in #ai-body ohne
      // Folgefrage-UI) — dort weiterhin der komplette Inhalt.
      const thread = $('#ai-thread'), usageWrap = $('#ai-usage-line-wrap');
      const bodyHtml = thread ? thread.innerHTML + (usageWrap ? usageWrap.innerHTML : '')
                              : $('#ai-body').innerHTML;
      w.document.write('<!doctype html><html><head><meta charset="utf-8"><title>'+esc(title+' – '+sub)+'</title><style>'
        + 'body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#111;max-width:760px;margin:0 auto;padding:32px;line-height:1.5}'
        + 'h1{font-size:1.3rem;margin:0 0 4px}.sub{color:#555;font-size:.9rem;margin-bottom:20px}'
        + '.ai-h{color:#0b65d8;font-size:1rem;margin:18px 0 6px}.ai-list{margin:0 0 12px;padding-left:20px}'
        + '.ai-cite{color:#0b65d8;text-decoration:none;font-size:.78em;vertical-align:super}'
        + 'table{width:100%;border-collapse:collapse;margin:8px 0 16px;font-size:.85rem}'
        + 'th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ddd}'
        + '.hint{color:#888;font-size:.78rem;margin-top:16px;padding-top:8px;border-top:1px solid #ddd}'
        + '@media print{body{padding:0}}</style></head><body>'
        + '<h1>'+esc(title)+'</h1><div class="sub">'+esc(sub)+'</div>'
        + bodyHtml + '</body></html>');
      w.document.close();
      w.onload = () => { w.focus(); w.print(); };
    }
    async function openAiSummary(i){
      const r = srchResults[i]; if(!r) return;
      $('#ai-title').textContent = '🤖 KI-Fazit';
      $('#ai-sub').textContent = r.name || '';
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      if(r._ai){ renderAiResult('#ai-body', r._ai); return; }
      const attempt = async () => {
        $('#ai-body').innerHTML = progBar(aiProviderName()+' durchsucht das Web nach Bewertungen…');
        let resp, d;
        try {
          const rp = await aiFetchPreviewable(api('/api/ai/hotel-summary'), {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify(hotelFacts(r))}, 'KI durchsucht das Web nach Bewertungen…');
          if(rp.cancelled) return;
          resp = rp.resp; d = rp.d;
        } catch(e){ _aiRetryFn = attempt; $('#ai-body').innerHTML = aiErrorBlock('KI-Zusammenfassung fehlgeschlagen.', true); return; }
        if(!resp.ok){
          const retryable = aiRetryable(d.error);
          _aiRetryFn = retryable ? attempt : null;
          $('#ai-body').innerHTML = aiErrorBlock(aiErrorMsg(d.error), retryable);
          return;
        }
        r._ai = d;
        renderAiResult('#ai-body', d);
      };
      attempt();
    }
    async function openAiCompare(){
      const hotels = srchResults.filter(r=>srCmpSelected.has(r._key));
      if(hotels.length < 2){ toast('Bitte mindestens 2 Hotels auswählen'); return; }
      runAiCompare('srch:'+hotels.map(h=>h._key).sort().join('|'), hotels.map(hotelFacts), hotels.map(h=>h.name));
    }
    function offerFacts(o){
      return {name:o.label||o.hotel, giata:o.giata, location:o.location, country:o.country,
        stars:o.stars, recommendation:o.recommendation, reviews:o.rating_count,
        price:o.price, details:o.details};
    }
    async function openAiCompareOffers(){
      let offers = (curOffers||[]).filter(o=>selected.has(o.id));
      if(offers.length < 2){ toast('Bitte mindestens 2 Angebote auswählen'); return; }
      if(offers.length > 5){ toast('Nur die ersten 5 ausgewählten Angebote werden verglichen'); offers = offers.slice(0, 5); }
      const names = offers.map(o=>o.label||o.hotel||('Angebot #'+o.id));
      runAiCompare('off:'+offers.map(o=>o.id).sort((a,b)=>a-b).join('|'), offers.map(offerFacts), names);
    }
    async function autoTagSelected(){
      const ids = [...selected]; if(!ids.length) return;
      toast(aiProviderName()+' vergibt Tags für '+ids.length+' Angebot(e)…');
      let resp, d;
      try {
        resp = await fetch(api('/api/ai/auto-tags'), {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ids})});
        d = await resp.json();
      } catch(e){ toast('Fehler beim Auto-Tagging'); return; }
      if(!resp.ok){ toast(d.error==='no_api_key'?'Kein Anthropic API-Key hinterlegt':'Fehler beim Auto-Tagging'); return; }
      const n = Object.keys(d.results||{}).length;
      toast(n ? n+' Angebot(e) getaggt' : 'Keine Tags ermittelt');
      bulkClear(); loadOffers();
    }
    async function runAiCompare(cacheKey, facts, names){
      $('#ai-title').textContent = '🤖 KI-Vergleich';
      $('#ai-sub').textContent = names.join(' · ');
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      if(_aiCompareCache[cacheKey]){ renderAiResult('#ai-body', _aiCompareCache[cacheKey]); return; }
      const attempt = async () => {
        $('#ai-body').innerHTML = progBar(aiProviderName()+' vergleicht '+facts.length+' Hotels und durchsucht das Web…');
        let resp, d;
        try {
          const r = await aiFetchPreviewable(api('/api/ai/hotel-compare'), {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({hotels: facts})}, 'KI vergleicht '+facts.length+' Hotels und durchsucht das Web…');
          if(r.cancelled) return;
          resp = r.resp; d = r.d;
        } catch(e){ _aiRetryFn = attempt; $('#ai-body').innerHTML = aiErrorBlock('KI-Vergleich fehlgeschlagen.', true); return; }
        if(!resp.ok){
          const retryable = aiRetryable(d.error);
          _aiRetryFn = retryable ? attempt : null;
          $('#ai-body').innerHTML = aiErrorBlock(aiErrorMsg(d.error), retryable);
          return;
        }
        _aiCompareCache[cacheKey] = d;
        renderAiResult('#ai-body', d);
      };
      attempt();
    }
    const _aiCompareCache = {};  // Session-Cache: Präfix+sortierter Schlüssel-String → {summary, usage}
    function closeAiSummary(){ $('#ai-bg').classList.remove('show'); _aiRetryFn = null; }
    $('#ai-bg').addEventListener('click', e=>{ if(e.target.id==='ai-bg') closeAiSummary(); });

    // ── KI-Verlauf (dauerhaft gespeicherte Fazits/Vergleiche) ─────────────────
    let _aiHistItems = [];
    // ── Meldungen & Fehler (Footer „🔔 Meldungen") ─────────────────────────────
    // Telegram-Nachrichten enthalten die HTML-Tags des Bots (<b>/<i>/<code>) und
    // rohe URLs — fürs Panel: alles escapen, dann NUR die Whitelist-Tags wieder
    // aktivieren und URLs als gekürzte, klickbare Links rendern.
    function syslogFmt(text){
      let h = esc(text||'');
      h = h.replace(/&lt;(\/?)(b|i|u|s|code)&gt;/g, '<$1$2>');
      h = h.replace(/(https?:\/\/[^\s<]+)/g, u =>
        `<a href="${u}" target="_blank" rel="noopener" style="color:var(--accent)">${u.length>64?u.slice(0,61)+'…':u}</a>`);
      return h;
    }
    async function openSyslog(tab){
      $('#syslog-bg').classList.add('show');
      $('#syslog-tab-notify').classList.toggle('sec', tab!=='notify');
      $('#syslog-tab-errors').classList.toggle('sec', tab!=='errors');
      const body = $('#syslog-body');
      body.innerHTML = progBar('Lädt…');
      let d;
      try {
        const r = await fetch(api(tab==='errors'?'/api/errors':'/api/notifications'));
        if(!r.ok) throw 0; d = await r.json();
      } catch(e){ body.innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Konnte nicht geladen werden.</div>'; return; }
      const items = d.items||[];
      if(tab==='errors'){
        $('#syslog-sub').textContent = 'Letzte Warnungen/Fehler seit Add-on-Start (max. 100) — Diagnose ohne HA-Log.';
        body.innerHTML = items.length ? items.map(it=>{
          const t = new Date(it.ts).toLocaleString('de-DE');
          const col = it.level==='ERROR'?'var(--red)':'var(--amber)';
          return `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:.8rem">
            <span style="color:${col};font-weight:600">${esc(it.level)}</span>
            <span class="hint"> · ${esc(t)}</span>
            <div style="word-break:break-word">${esc(it.msg)}</div></div>`;
        }).join('') : '<div class="empty">Keine Warnungen/Fehler seit dem Start. 🎉</div>';
      } else {
        $('#syslog-sub').textContent = 'Gesendete Benachrichtigungen (HA & Telegram), neueste zuerst — dauerhaft, letzte 500.';
        body.innerHTML = items.length ? items.map(it=>{
          const t = new Date(it.ts*1000).toLocaleString('de-DE');
          const ch = it.channel==='telegram'?'✈️ Telegram':'🏠 HA';
          const text = it.title ? (it.title+' — '+(it.message||'')) : (it.message||'');
          return `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:.8rem">
            <b>${ch}</b>${it.ok?'':' <span style="color:var(--red);font-weight:600">✗ fehlgeschlagen</span>'}
            <span class="hint"> · ${esc(t)}</span>
            <div style="white-space:pre-wrap;word-break:break-word">${syslogFmt(text)}</div></div>`;
        }).join('') : '<div class="empty">Noch keine Benachrichtigungen gesendet.</div>';
      }
    }
    function closeSyslog(){ $('#syslog-bg').classList.remove('show'); }

    async function openGiataGallery(giata){
      $('#giata-gallery-bg').classList.add('show');
      const body = $('#giata-gallery-body');
      body.innerHTML = progBar('Lädt…');
      let d;
      try {
        const r = await fetch(api('/api/giata_images/'+encodeURIComponent(giata)));
        if(!r.ok) throw 0; d = await r.json();
      } catch(e){ body.innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Konnte nicht geladen werden.</div>'; return; }
      const images = d.images||[];
      body.innerHTML = images.length ? (
        '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-top:10px">'
        + images.map(im=>(
            '<a href="#" onclick="event.preventDefault();openGiataLightbox(\''+esc(im.full)+'\')">'
            +'<img src="'+esc(im.thumb)+'" loading="lazy" style="width:100%;height:110px;object-fit:cover;border-radius:6px;border:1px solid var(--border)">'
            +'</a>'
          )).join('')
        + '</div>'
      ) : '<div class="empty">Keine Fotos gefunden.</div>';
    }
    function closeGiataGallery(){ $('#giata-gallery-bg').classList.remove('show'); }
    function openGiataLightbox(full){
      $('#giata-lightbox-img').src = full;
      $('#giata-lightbox-bg').classList.add('show');
    }
    function closeGiataLightbox(){
      $('#giata-lightbox-bg').classList.remove('show');
      $('#giata-lightbox-img').src = '';
    }
    $('#syslog-bg').addEventListener('click', e=>{ if(e.target.id==='syslog-bg') closeSyslog(); });

    async function openAiHistory(){
      $('#aihist-bg').classList.add('show');
      $('#aihist-search').value = '';
      $('#aihist-body').innerHTML = progBar('Lädt…');
      let d;
      try { d = await fetch(api('/api/ai/history')).then(r=>r.json()); }
      catch(e){ $('#aihist-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Verlauf konnte nicht geladen werden.</div>'; return; }
      _aiHistItems = d.items||[];
      renderAiHistory(_aiHistItems);
    }
    function filterAiHistory(){
      const q = $('#aihist-search').value.trim().toLowerCase();
      if(!q){ renderAiHistory(_aiHistItems); return; }
      renderAiHistory(_aiHistItems.filter(it =>
        (it.title||'').toLowerCase().includes(q) ||
        aiKindLabel(it.kind).toLowerCase().includes(q) ||
        (it.model||'').toLowerCase().includes(q)));
    }
    function closeAiHistory(){ $('#aihist-bg').classList.remove('show'); }
    $('#aihist-bg').addEventListener('click', e=>{ if(e.target.id==='aihist-bg') closeAiHistory(); });

    // ── KI-Prompt-Einstellungen (eigene Prompt-Vorlagen für Reiseberater/Vergleich) ──
    let promptCfgData = null;
    async function openPromptCfg(){
      $('#promptcfg-bg').classList.add('show');
      try {
        const resp = await fetch(api('/api/ai/prompt-settings'));
        promptCfgData = await resp.json();
      } catch(e){ toast('Laden fehlgeschlagen'); closePromptCfg(); return; }
      for (const f of ['advisor','compare','summary','daytrip']){
        const d = promptCfgData[f];
        $(`#promptcfg-${f}-enabled`).checked = d.enabled;
        $(`#promptcfg-${f}-text`).value = (d.enabled && d.text) ? d.text : d.default;
        promptcfgCount(f);
      }
    }
    function closePromptCfg(){ $('#promptcfg-bg').classList.remove('show'); }
    $('#promptcfg-bg').addEventListener('click', e=>{ if(e.target.id==='promptcfg-bg') closePromptCfg(); });
    function promptcfgReset(f){
      $(`#promptcfg-${f}-text`).value = promptCfgData[f].default;
      promptcfgCount(f);
    }
    function promptcfgCount(f){
      $(`#promptcfg-${f}-count`).textContent = $(`#promptcfg-${f}-text`).value.length + ' / 4000 Zeichen';
    }
    async function savePromptCfg(){
      const body = {};
      for (const f of ['advisor','compare','summary','daytrip']){
        body[f] = { enabled: $(`#promptcfg-${f}-enabled`).checked, text: $(`#promptcfg-${f}-text`).value };
      }
      try {
        const resp = await fetch(api('/api/ai/prompt-settings'), {method:'POST',
          headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        if(!resp.ok) throw new Error();
        toast('Gespeichert');
        closePromptCfg();
      } catch(e){ toast('Speichern fehlgeschlagen'); }
    }
    function aiKindLabel(kind){
      return kind==='compare' ? '🤖 Vergleich' : kind==='ask' ? '❓ Frage'
        : kind==='advisor' ? '🗺️ TripPilot' : kind==='booking_score' ? '🔮 Buchungsscore'
        : kind==='region_outlook' ? '🔮 Region-Ausblick'
        : kind==='calendar_outlook' ? '📅 Kalender-Analyse' : '🤖 Fazit';
    }
    function renderAiHistory(items){
      if(!items.length){
        $('#aihist-body').innerHTML = '<div class="cmp-load">'
          + (_aiHistItems.length ? 'Keine Treffer.' : 'Noch keine KI-Analysen gespeichert.') + '</div>';
        return;
      }
      $('#aihist-body').innerHTML = items.map(it => `<div class="aihist-item">
          <div class="aihist-main" onclick="openAiHistoryItem(${it.id})">
            <div class="aihist-title">${aiKindLabel(it.kind)} · ${esc(it.title)}</div>
            <div class="hint">${esc(new Date(it.ts*1000).toLocaleString('de-DE'))} · ${esc(it.model)}</div>
          </div>
          ${it.has_prompt ? `<button class="icon-btn" onclick="repeatAiHistoryItem(${it.id}, event)" title="Mit anderer KI wiederholen">🔁</button>` : ''}
          <button class="icon-btn" onclick="deleteAiHistoryItem(${it.id}, event)" title="Eintrag löschen">🗑</button>
        </div>`).join('');
    }
    async function openAiHistoryItem(id){
      closeAiHistory();
      $('#ai-title').textContent = '🤖 KI-Verlauf';
      $('#ai-sub').textContent = 'Lädt…';
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      $('#ai-body').innerHTML = progBar('Lädt…');
      let d;
      try { d = await fetch(api('/api/ai/history/'+id)).then(r=>r.json()); }
      catch(e){ $('#ai-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Eintrag konnte nicht geladen werden.</div>'; return; }
      if(d.error){ $('#ai-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Eintrag nicht gefunden (evtl. gelöscht).</div>'; return; }
      $('#ai-title').textContent = aiKindLabel(d.kind) + ' (Verlauf)';
      $('#ai-sub').textContent = d.title + ' · ' + new Date(d.ts*1000).toLocaleString('de-DE');
      if(d.kind==='booking_score' || d.kind==='region_outlook'){
        let parsed; try { parsed = JSON.parse(d.summary); } catch(e){ parsed = null; }
        if(parsed){ renderBookingScore('#ai-body', {result: parsed, usage: d.usage, id: d.id}); return; }
      }
      renderAiResult('#ai-body', {summary: d.summary, usage: d.usage, id: d.id, conversation: d.conversation});
    }
    async function deleteAiHistoryItem(id, ev){
      ev.stopPropagation();
      if(!confirm('Diesen KI-Verlaufseintrag löschen?')) return;
      try { await fetch(api('/api/ai/history/'+id), {method:'DELETE'}); } catch(e){}
      openAiHistory();
    }
    async function repeatAiHistoryItem(id, ev){
      ev.stopPropagation();
      const it = _aiHistItems.find(x=>x.id===id); if(!it) return;
      closeAiHistory();
      $('#ai-title').textContent = '🔁 Wiederholen';
      $('#ai-sub').textContent = aiKindLabel(it.kind) + ' · ' + it.title;
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      let avail = {};
      try { avail = await fetch(api('/api/ai/provider')).then(r=>r.json()); } catch(e){}
      const mkBtn = p => {
        const ok = avail[p+'_configured'];
        return `<button class="btn${ok?'':' sec'}" ${ok?'':'disabled'} onclick="runAiHistoryRepeat(${id},'${p}')">${AI_PROVIDER_LABEL[p]}${ok?'':' (kein Key)'}</button>`;
      };
      $('#ai-body').innerHTML = `<div class="hint" style="margin-bottom:10px">Mit welcher KI wiederholen?</div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">${Object.keys(AI_PROVIDER_LABEL).map(mkBtn).join('')}</div>`;
    }
    async function runAiHistoryRepeat(id, provider){
      const attempt = async () => {
        $('#ai-body').innerHTML = progBar('Wird mit '+(AI_PROVIDER_NAME[provider]||provider)+' wiederholt…');
        let resp, d;
        try {
          const r = await aiFetchPreviewable(api('/api/ai/history/'+id+'/repeat'), {method:'POST',
            headers:{'Content-Type':'application/json'}, body: JSON.stringify({provider})}, 'Wird wiederholt…');
          if(r.cancelled) return;
          resp = r.resp; d = r.d;
        } catch(e){ _aiRetryFn = attempt; $('#ai-body').innerHTML = aiErrorBlock('Wiederholen fehlgeschlagen.', true); return; }
        if(!resp.ok){
          const retryable = aiRetryable(d.error);
          const msg = d.error==='no_prompt' ? (d.note||'Kein Prompt gespeichert.') : aiErrorMsg(d.error);
          _aiRetryFn = retryable ? attempt : null;
          $('#ai-body').innerHTML = aiErrorBlock(msg, retryable);
          return;
        }
        if(d.result){ renderBookingScore('#ai-body', d); } else { renderAiResult('#ai-body', d); }
      };
      attempt();
    }

    // ── Frag dein Portfolio ────────────────────────────────────────────────────
    function openAiAsk(){ $('#aiask-q').value=''; $('#aiask-bg').classList.add('show'); }
    function closeAiAsk(){ $('#aiask-bg').classList.remove('show'); }
    $('#aiask-bg').addEventListener('click', e=>{ if(e.target.id==='aiask-bg') closeAiAsk(); });
    async function submitAiAsk(){
      const q = $('#aiask-q').value.trim();
      if(!q){ toast('Bitte eine Frage eingeben'); return; }
      closeAiAsk();
      $('#ai-title').textContent = '❓ Frag dein Portfolio';
      $('#ai-sub').textContent = q;
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      const attempt = async () => {
        $('#ai-body').innerHTML = progBar(aiProviderName()+' durchsucht dein Portfolio…');
        let resp, d;
        try {
          const r = await aiFetchPreviewable(api('/api/ai/ask'), {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question:q})}, 'KI durchsucht dein Portfolio…');
          if(r.cancelled) return;
          resp = r.resp; d = r.d;
        } catch(e){ _aiRetryFn = attempt; $('#ai-body').innerHTML = aiErrorBlock('Frage fehlgeschlagen.', true); return; }
        if(!resp.ok){
          const retryable = aiRetryable(d.error);
          const msg = d.error==='no_offers' ? 'Keine aktiven Angebote vorhanden.' : aiErrorMsg(d.error);
          _aiRetryFn = retryable ? attempt : null;
          $('#ai-body').innerHTML = aiErrorBlock(msg, retryable);
          return;
        }
        renderAiResult('#ai-body', d);
      };
      attempt();
    }

    // ── KI-Reiseberater (geführter Fragebogen → 3 Zielvorschläge) ─────────────
    const DAYTRIP = 'Tagesausflug in der Nähe';
    const isDaytrip = state => (state.region||[]).includes(DAYTRIP);
    const ADV_STEPS = [
      {title:'Wohin soll die Reise ungefähr gehen?', key:'region', multi:true,
       exclusive:[DAYTRIP],
       options:['Deutschland','Europa','Makaronesien','Griechische Inseln','Balearen','Italien',
                'Frankreich','Adriaküste','Algarve','Zypern','Kanaren','Mittelmeer','Karibik',
                'Südostasien','Indischer Ozean','Weltweit','Egal',DAYTRIP]},
      {title:'Welche Länder kommen für dich nicht in Frage?', key:'excluded_countries', multi:true,
       showIf: state => !(state.region||[]).includes(DAYTRIP) &&
         ((state.region||[]).includes('Weltweit') || (state.region||[]).includes('Egal')),
       options:['Türkei','Ägypten','Tunesien','Marokko','Kenia','Thailand','Sri Lanka',
                'Dominikanische Republik','Mexiko','Malediven']},
      {title:'Weitere Länder ausschließen? (optional)', key:'excluded_countries_other', type:'text',
       showIf: state => !(state.region||[]).includes(DAYTRIP) &&
         ((state.region||[]).includes('Weltweit') || (state.region||[]).includes('Egal')),
       placeholder:'z. B. weitere Länder, kommagetrennt'},
      {title:'Was ist dir im Urlaub wichtig?', key:'interests', multi:true,
       showIf: state => !isDaytrip(state),
       options:['🌴 Strand','⛰️ Berge','🏛️ Kultur','🍹 Entspannung','🎉 Nachtleben','🚶 Wandern',
                '🚴 Radfahren','🍽️ Essen','🛍️ Shopping','👨‍👩‍👧 Familie','❤️ Romantik']},
      {title:'Wie soll dein Strand sein?', key:'beach_detail', multi:true,
       showIf: state => (state.interests||[]).includes('🌴 Strand'),
       options:['Feinsandig','Kies/Felsen','Naturstrand, unberührt','Weitläufig, kilometerlang',
                'Kleine, ruhige Bucht','Belebt mit Beach-Bars','Flach abfallend (familienfreundlich)',
                'Schattenplätze/Palmen','Gut zum Schnorcheln','Direkt am Hotel',
                'Fußweg/Promenade OK']},
      {title:'Wie sollen die Berge sein?', key:'berge_detail', multi:true,
       showIf: state => (state.interests||[]).includes('⛰️ Berge'),
       options:['Sanfte Wanderwege','Anspruchsvolle Gipfeltouren','Skigebiet (Winter)',
                'Aussicht/Panorama','Alm-/Hüttenromantik','Seilbahn/Gondel vorhanden',
                'Ruhig, wenig Tourismus']},
      {title:'Welche Reiseart?', key:'travel_type', multi:true,
       showIf: state => !isDaytrip(state),
       options:['Pauschalreise (TUI)','Badeurlaub','Rundreise','Städtereise','Kreuzfahrt','Wellness',
                'Aktivurlaub','Abenteuer','Luxus','Camping','All Inclusive','Ferienwohnung']},
      {title:'Mit wem reist du?', key:'companions', multi:false,
       showIf: state => !isDaytrip(state),
       options:['Alleine','Partner','Familie','Freunde','Senioren','Mit Hund']},
      {title:'Budget pro Person?', key:'budget', multi:false,
       showIf: state => !isDaytrip(state),
       options:['bis 500 €','500–1000 €','1000–2000 €','2000–3000 €','egal']},
      {title:'Reisedauer?', key:'duration', multi:false,
       showIf: state => !isDaytrip(state),
       options:['Wochenende','5 Tage','1 Woche','9–12 Tage','2 Wochen','3+ Wochen']},
      {title:'Wie viel Zeit hast du?', key:'duration_daytrip', multi:false,
       showIf: state => isDaytrip(state),
       options:['Vormittag','Nachmittag','Ganzer Tag','Ganzer Tag inkl. Abend']},
      {title:'Wann soll es losgehen?', key:'month', multi:false,
       options:['Januar','Februar','März','April','Mai','Juni','Juli','August','September',
                'Oktober','November','Dezember','Egal']},
      {title:'Wie warm soll es sein?', key:'temp', multi:false,
       showIf: state => !isDaytrip(state),
       options:['unter 20°C','20–25°C','25–30°C','20–30°C','möglichst heiß','egal']},
      {title:'Meer oder See?', key:'water_type', multi:true,
       exclusive:['Kein Gewässer nötig'],
       options:['Meer','See','Kein Gewässer nötig']},
      {title:'Wie warm soll das Wasser sein?', key:'sea', multi:false,
       showIf: state => (state.water_type||[]).length > 0 && !state.water_type.includes('Kein Gewässer nötig'),
       options:['28°C+ (tropisch warm)','24–27°C (angenehm warm)','20–24°C ist ok','egal']},
      {title:'Regen?', key:'rain', multi:false,
       options:['möglichst trocken','egal']},
      {title:'Welche Aktivitäten interessieren dich?', key:'activities', multi:true,
       options:['Tauchen','Schnorcheln','Wandern','Skifahren','Golf','Mountainbike','Surfen',
                'Safari','Fotografieren','Museen','Freizeitparks','Wein','Kulinarik',
                'Reiten','Segeln','Angeln','Klettern','Yoga','Tennis','Kajak/SUP','Bootsausflüge',
                'Zoo/Tierpark','Therme/Wellness-Tag','Sehenswürdigkeit/Schloss','Kletterpark',
                'Escape Room','Minigolf','Flohmarkt/Markt','Natur','FKK']},
      {title:'Welche Unterkunftsart?', key:'accommodation', multi:false,
       showIf: state => !isDaytrip(state),
       options:['Hotel','Apartment','Ferienwohnung','Airbnb','Villa','Camping','Hostel','egal']},
      {title:'Wie groß darf das Hotel sein?', key:'accommodation_size', multi:false,
       showIf: state => !isDaytrip(state) && state.accommodation === 'Hotel',
       options:['klein','Boutique','mittelgroß','riesige Clubanlage','egal']},
      {title:'Was ist dir beim Hotel besonders wichtig?', key:'hotel_wishes', multi:true,
       showIf: state => !isDaytrip(state),
       options:['Erwachsenenhotel','Familienhotel','Kinderpool','Rutschen','Animation','Ruhe',
                'All Inclusive','Frühstück','Halbpension','Swim-Up','Privatpool','Spa',
                'Fitnessstudio','direkte Strandlage','Sandstrand','flach abfallend','Hausriff',
                'WLAN','Homeoffice geeignet']},
      {title:'Wie möchtest du anreisen?', key:'arrival_mode', multi:false,
       showIf: state => !isDaytrip(state),
       options:['Flugzeug','Auto','Bus','Bahn','Ist mir egal']},
      {title:'Von wo geht\'s los?', key:'home_location', type:'text', required:true,
       showIf: state => ['Auto','Bus','Bahn'].includes(state.arrival_mode) || isDaytrip(state),
       placeholder:'PLZ oder Ort'},
      {title:'Wie weit darf es maximal sein?', key:'max_distance', multi:false,
       showIf: state => ['Auto','Bus','Bahn'].includes(state.arrival_mode) || isDaytrip(state),
       options:['bis 50 km','bis 100 km','bis 200 km','bis 400 km','bis 600 km','egal']},
      {title:'Flugzeit?', key:'flight_time', multi:false,
       showIf: state => !isDaytrip(state) &&
         (!state.arrival_mode || ['Flugzeug','Ist mir egal'].includes(state.arrival_mode)),
       options:['Direktflug','max. 4 Stunden','max. 6 Stunden','egal']},
      {title:'Abflughafen?', key:'airports', multi:true,
       showIf: state => !isDaytrip(state) &&
         (!state.arrival_mode || ['Flugzeug','Ist mir egal'].includes(state.arrival_mode)),
       options:['Frankfurt','Stuttgart','München','Hamburg','Düsseldorf','Berlin']},
      {title:'Was nervt dich im Urlaub?', key:'dislikes', multi:true,
       showIf: state => !isDaytrip(state),
       options:['überfüllte Strände','Kinder','Animation','Wind','Hitze','lange Transfers',
                'frühes Aufstehen','Starker Wellengang']},
      {title:'Was macht für dich einen perfekten Urlaub aus?', key:'perfect_holiday', type:'text',
       showIf: state => !isDaytrip(state),
       placeholder:'Freitext, optional'},
      {title:'Welche Hotels/Urlaube haben dir gefallen – welche nicht? Warum?',
       key:'past_trips', type:'text',
       showIf: state => !isDaytrip(state),
       placeholder:'z. B. "RIU Papayas war super, viel Auswahl beim Essen, ruhige Lage"'},
      {title:'Was macht für dich einen perfekten Ausflug aus?', key:'perfect_daytrip', type:'text',
       showIf: state => isDaytrip(state),
       placeholder:'Freitext, optional'},
    ];
    let advIdx = 0, advState = {};
    function openAdvisor(){
      advIdx = 0; advState = {};
      if(G.homeLoc) advState.home_location = G.homeLoc;
      $('#reiseb-bg').classList.add('show');
      advRender();
    }
    function closeAdvisor(){ $('#reiseb-bg').classList.remove('show'); }
    $('#reiseb-bg').addEventListener('click', e=>{ if(e.target.id==='reiseb-bg') closeAdvisor(); });
    function advVisibleSteps(){ return ADV_STEPS.filter(s => !s.showIf || s.showIf(advState)); }
    function advRender(){
      const steps = advVisibleSteps();
      const s = steps[advIdx];
      $('#reiseb-sub').textContent = 'Schritt '+(advIdx+1)+' von '+steps.length
        + (s.multi ? ' · Mehrfachauswahl möglich' : '');
      if(s.type === 'text'){
        const val = advState[s.key] || '';
        $('#reiseb-body').innerHTML = '<h3 style="margin:4px 0 12px">'+esc(s.title)+'</h3>'
          + `<textarea id="reiseb-text" class="reiseb-text" rows="4" oninput="advUpdateNextState()" `
          + `placeholder="${esc(s.placeholder||'Optional')}">${esc(val)}</textarea>`;
      } else {
        const sel = advState[s.key] != null ? advState[s.key] : (s.multi ? [] : null);
        $('#reiseb-body').innerHTML = '<h3 style="margin:4px 0 12px">'+esc(s.title)+'</h3>'
          + '<div class="tag-row">' + s.options.map((o, oi) => {
              const active = s.multi ? sel.includes(o) : sel === o;
              return `<span class="tag-pill${active?' active':''}" onclick="advPick(${oi})">${esc(o)}</span>`;
            }).join('') + '</div>';
      }
      $('#reiseb-back').style.visibility = advIdx === 0 ? 'hidden' : 'visible';
      $('#reiseb-next').textContent = advIdx === steps.length - 1 ? '🔮 Empfehlung holen' : 'Weiter';
      advUpdateNextState();
    }
    function advUpdateNextState(){
      const s = advVisibleSteps()[advIdx];
      const filled = s.type === 'text'
        ? !!($('#reiseb-text').value || '').trim()
        : !!advState[s.key];
      $('#reiseb-next').disabled = !!s.required && !filled;
    }
    function advPick(oi){
      const s = advVisibleSteps()[advIdx], o = s.options[oi];
      if(s.multi){
        const arr = advState[s.key] || (advState[s.key] = []);
        const excl = s.exclusive || [];
        if(excl.includes(o)){
          // Exklusive Option (z. B. Tagesausflug/Kein Gewässer nötig): schließt
          // alle anderen Optionen der gleichen Frage aus, toggelt sich selbst
          const active = arr.includes(o);
          arr.length = 0;
          if(!active) arr.push(o);
        } else {
          // Normale Option gewählt: vorher gesetzte exklusive Optionen entfernen
          for(const e of excl){ const ei = arr.indexOf(e); if(ei >= 0) arr.splice(ei, 1); }
          const i = arr.indexOf(o);
          if(i >= 0) arr.splice(i, 1); else arr.push(o);
        }
        advRender();
      } else {
        advState[s.key] = o;
        advRender();
        setTimeout(advNext, 150);
      }
    }
    function advCaptureText(){
      const s = advVisibleSteps()[advIdx];
      if(s.type === 'text'){
        const v = ($('#reiseb-text').value || '').trim();
        if(v) advState[s.key] = v; else delete advState[s.key];
      }
    }
    function advBack(){ advCaptureText(); if(advIdx > 0){ advIdx--; advRender(); } }
    function advNext(){
      advCaptureText();
      const steps = advVisibleSteps();
      if(advIdx < steps.length - 1){ advIdx++; advRender(); }
      else submitAdvisor();
    }
    async function submitAdvisor(){
      closeAdvisor();
      $('#ai-title').textContent = '🗺️ TripPilot';
      $('#ai-sub').textContent = [(advState.region||[]).join(', '), advState.arrival_mode,
        (advState.interests||[]).join(', ')].filter(Boolean).join(' · ');
      $('#ai-foot').style.display = 'none';
      $('#ai-bg').classList.add('show');
      const attempt = async () => {
        await ensureAiProviderLoaded();
        $('#ai-body').innerHTML = progBar(aiProviderName()+' sucht passende Ziele…');
        let resp, d;
        try {
          const r = await aiFetchPreviewable(api('/api/ai/travel-advisor'), {method:'POST',
            headers:{'Content-Type':'application/json'}, body: JSON.stringify(advState)}, 'KI sucht passende Ziele…');
          if(r.cancelled) return;
          resp = r.resp; d = r.d;
        } catch(e){ _aiRetryFn = attempt; $('#ai-body').innerHTML = aiErrorBlock('Anfrage fehlgeschlagen.', true); return; }
        if(!resp.ok){
          const retryable = aiRetryable(d.error);
          const msg = d.error==='invalid' ? 'Bitte mindestens eine Angabe auswählen.' : aiErrorMsg(d.error);
          _aiRetryFn = retryable ? attempt : null;
          $('#ai-body').innerHTML = aiErrorBlock(msg, retryable);
          return;
        }
        renderAiResult('#ai-body', d);
      };
      attempt();
    }

    // ── Preiskalender (Monats-Grid, gespeichert) ──────────────────────────────
    let calTimer = null, calId = null, calData = null, calMonth = null, calTrendView = false;
    let calMovesOpen = false;   // "Größte Bewegungen"-Liste: default eingeklappt, Zustand überlebt Monatswechsel
    function toggleCalTrend(){ calTrendView = !calTrendView; drawCalMonth(); }
    async function openCalDayChart(iso){
      const box = $('#cal-day-chart');
      box.classList.add('show');
      box.innerHTML = `<div class="cmp-load">Lade Preisverlauf für ${fmtD(iso)}…</div>`;
      let d;
      try { d = await fetch(api('/api/calendar/'+calId+'/day/'+iso)).then(r=>r.json()); }
      catch(e){ box.innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Preisverlauf konnte nicht geladen werden.</div>'; return; }
      const pts = (d.points||[]).map(p=>({ts:p.ts, price:p.price}));
      box.innerHTML = `<div class="cal-day-hd"><b>Preisverlauf: ${fmtD(iso)}</b>
          <button class="btn sec" onclick="closeCalDayChart()">✕</button></div>
        <canvas id="cal-day-canvas" style="width:100%;height:120px;display:block"></canvas>`;
      if(pts.length<2){
        $('#cal-day-canvas').outerHTML = '<div class="hint">Noch keine Preisänderung für dieses Datum aufgezeichnet.</div>';
      } else {
        drawChart($('#cal-day-canvas'), pts, false, {});
      }
    }
    function closeCalDayChart(){ $('#cal-day-chart').classList.remove('show'); $('#cal-day-chart').innerHTML=''; }
    function calSpinner(){ $('#cal-body').innerHTML = progBar('Preiskalender wird geladen…'); }
    function startCalPolling(){ clearInterval(calTimer); calPoll(); calTimer = setInterval(calPoll, 2000); }

    async function openCalendar(id){
      calId = id; calMonth = null; calData = null; calMovesOpen = false;
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      $('#cal-sub').textContent = o.label || o.hotel || ('TUI-Angebot #'+id);
      $('#cal-body').innerHTML = '<div class="cmp-load">Lade…</div>';
      $('#cal-bg').classList.add('show');
      clearInterval(calTimer); calTimer=null;
      let job;
      try { job = await fetch(api('/api/calendar/'+id)).then(r=>r.json()); } catch(e){ job={status:'idle'}; }
      if(job.status==='running'){ calSpinner(); startCalPolling(); }
      else if(job.status==='done' && job.days && job.days.length){ renderCalendar(job); }  // gespeichert → anzeigen
      else { refreshCalendar(); }                                                          // noch nie abgefragt → einmal starten
    }
    async function refreshCalendar(){
      if(calId==null) return;
      calSpinner();
      try { await fetch(api('/api/calendar/'+calId), {method:'POST'}); } catch(e){}
      startCalPolling();
    }
    function closeCalendar(){ clearInterval(calTimer); calTimer=null; calId=null; $('#cal-bg').classList.remove('show'); }
    $('#cal-bg').addEventListener('click', e=>{ if(e.target.id==='cal-bg') closeCalendar(); });
    function calGo(m){ if(!m) return; calMonth=m; drawCalMonth(); }

    // — Zimmerauswahl —
    let roomId = null;
    // Gesetzt von trackResult() für neu angelegte (start:false) Angebote — nur dann
    // startet closeRooms() beim Schließen ohne Auswahl die erste Prüfung nachträglich.
    let pendingStartId = null;
    async function openRooms(id){
      roomId = id;
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      $('#room-sub').textContent = o.label || o.hotel || ('TUI-Angebot #'+id);
      $('#room-body').innerHTML = progBar('Zimmer werden geladen…');
      $('#room-bg').classList.add('show');
      let d;
      try { d = await fetch(api('/api/rooms/'+id)).then(r=>r.json()); }
      catch(e){ $('#room-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ Zimmer konnten nicht geladen werden.</div>'; return; }
      renderRooms(d);
    }
    function renderRooms(d){
      if(!d || !d.ok || !(d.rooms&&d.rooms.length)){
        $('#room-body').innerHTML = '<div class="cmp-load">'+esc((d&&d.note)||'Keine Zimmer gefunden.')+'</div>'; return;
      }
      const cheapest = d.rooms[0].price, cur = d.current||'', auto = !cur;
      let html = `<div class="room-row auto ${auto?'active':''}">
          <div class="room-info"><div class="room-name">Günstigstes automatisch${auto?' <span class="room-badge">getrackt</span>':''}</div>
            <div class="hint">immer das jeweils günstigste Zimmer verfolgen</div></div>
          <div class="room-actions"><button class="btn ${auto?'sec':''}" ${auto?'disabled':''} onclick="pickRoom('', '')">${auto?'aktiv':'wählen'}</button></div>
        </div>`;
      html += d.rooms.map(r=>{
        const diff = r.price-cheapest, active = (r.code===cur);
        return `<div class="room-row ${active?'active':''}">
          <div class="room-info">
            <div class="room-name">${esc(r.name)} <span class="room-code">${esc(r.code)}</span>${active?' <span class="room-badge">getrackt</span>':''}</div>
            <div class="hint">${esc(r.board||'')}${diff>0?(' · +'+eur(diff)+' ggü. günstigstem'):' · günstigstes'}</div>
          </div>
          <div class="room-actions">
            <div class="room-price">${eur(r.price)} <span class="pp">p.P.</span></div>
            <a class="btn sec" href="${esc(r.url)}" target="_blank" rel="noopener" title="Details & Fotos auf tui.com">Details ↗</a>
            <button class="btn ${active?'sec':''}" ${active?'disabled':''} onclick="pickRoom('${esc(r.code)}', '${jsArg(r.name)}')">${active?'aktiv':'tracken'}</button>
          </div>
        </div>`;
      }).join('');
      html += '<div class="hint" style="margin-top:10px">Wechselst du das Zimmer, verfolgt TUIWatch ab sofort dessen Preis; der bisherige Verlauf bleibt erhalten.</div>';
      $('#room-body').innerHTML = html;
    }
    async function pickRoom(code, label){
      if(roomId==null) return;
      $('#room-body').innerHTML = progBar('Wird übernommen…');
      try {
        const r = await fetch(api('/api/rooms/'+roomId), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({code, label:label||''})});
        if(r.status===409){ toast('Dieses Zimmer wird bereits als eigenes Angebot verfolgt'); openRooms(roomId); return; }
        if(!r.ok){ toast('Fehler bei der Zimmerauswahl'); openRooms(roomId); return; }
      } catch(e){ toast('Fehler bei der Zimmerauswahl'); return; }
      toast(code?'Zimmer gewählt – wird geprüft…':'Günstigstes Zimmer – wird geprüft…');
      pendingStartId = null;   // Prüfung läuft bereits über POST /api/rooms/<id> — closeRooms soll nicht nochmal starten
      closeRooms(); lastSig=null; loadOffers();
    }
    function closeRooms(){
      // Zimmerauswahl für ein neu angelegtes (start:false) Angebot wurde OHNE
      // explizite Wahl geschlossen (X/Klick daneben) — Prüfung jetzt mit dem
      // ursprünglichen Zimmer aus der Suche nachträglich starten.
      if(pendingStartId!=null && pendingStartId===roomId){
        const id = pendingStartId;
        fetch(api('/api/offers/'+id+'/start'), {method:'POST'}).catch(()=>{});
        toast('Wird geprüft…');
        loadOffers();
      }
      pendingStartId = null; roomId=null; $('#room-bg').classList.remove('show');
    }
    $('#room-bg').addEventListener('click', e=>{ if(e.target.id==='room-bg') closeRooms(); });

    async function calPoll(){
      if(calId==null) return;
      let job;
      try { job = await fetch(api('/api/calendar/'+calId)).then(r=>r.json()); } catch(e){ return; }
      if(job.status==='running') return;
      clearInterval(calTimer); calTimer=null;
      renderCalendar(job);
    }

    function fmtD(iso){ const m=/(\d{4})-(\d{2})-(\d{2})/.exec(iso||''); return m?`${m[3]}.${m[2]}.${m[1]}`:iso; }
    function addDays(iso, n){ const m=/(\d{4})-(\d{2})-(\d{2})/.exec(iso||''); if(!m) return iso; const d=new Date(Date.UTC(+m[1],+m[2]-1,+m[3])); d.setUTCDate(d.getUTCDate()+(n||0)); return d.toISOString().slice(0,10); }
    // TUI erwartet als Reisezeitraum Hin- bis Rückreise: endDate = Anreise + Nächte.
    function dayUrl(base, iso, nights){ try{ const u=new URL(base); u.searchParams.set('startDate',iso); u.searchParams.set('endDate', nights>0?addDays(iso,nights):iso); return u.toString(); }catch(e){ return base; } }
    async function saveCalDay(ev, iso){
      ev.preventDefault();
      const offer = (curOffers||[]).find(x=>x.id===calId) || {};
      const base = offer.url || '';
      if(!base) return false;
      const nights = (calData && calData.duration) || 0;
      const name = (offer.hotel || offer.label || 'TUI-Angebot') + ' · ' + fmtD(iso);
      if(!confirm('Diesen Termin als neues Angebot tracken?\n\n'+name)) return false;
      const r = await fetch(api('/api/offers'), {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url: dayUrl(base, iso, nights), label: name})});
      if(r.status===409){ toast('Dieser Termin wird bereits verfolgt'); return false; }
      if(r.status===400){ toast('Keine gültige tui.com-URL'); return false; }
      if(!r.ok){ toast('Fehler beim Hinzufügen'); return false; }
      toast('Termin als neues Angebot gespeichert – wird geprüft…');
      loadOffers();
      return false;
    }
    function calFooter(job){
      const when = job.ts ? ('Abgefragt: '+new Date(job.ts*1000).toLocaleString('de-DE')) : '';
      const err = job.error ? '<div class="hint" style="color:var(--amber);margin-top:6px">⚠ Letzte Aktualisierung fehlgeschlagen.</div>' : '';
      const aiBtn = (job.days && job.days.length)
        ? '<button class="btn sec ai-feature" onclick="openCalendarOutlook()" title="KI fasst die Kalenderpreise zusammen und empfiehlt günstige/teure Monate">🤖 KI-Analyse</button>' : '';
      return `<div class="cmp-foot"><span class="hint" style="flex:1;min-width:180px">${esc(when)}</span>
        ${aiBtn}<button class="btn sec" onclick="refreshCalendar()">Neu abfragen</button></div>${err}`;
    }

    function renderCalendar(job){
      calData = job;
      if(!(job.days && job.days.length)){
        const msg = job.error || job.note || 'Preiskalender nicht verfügbar';
        $('#cal-body').innerHTML = '<div class="cmp-load" style="color:var(--amber)">⚠ '+esc(msg)+'</div>' + calFooter(job);
        return;
      }
      if(!calMonth){
        // Standard: der Monat des Reisebeginns (window_start) — sofern dafür Daten da sind;
        // sonst günstigster-im-Zeitraum / günstigster / erster Tag.
        const wm = (job.window_start||'').slice(0,7);
        const has = job.days.some(d=>d.date.slice(0,7)===wm);
        calMonth = (wm && has) ? wm : (job.tracked_date || job.cheapest_date || job.days[0].date).slice(0,7);
      }
      drawCalMonth();
    }

    function drawCalMonth(){
      const job = calData; if(!job) return;
      const pm = {}; job.days.forEach(d=>pm[d.date]=d.price);
      const moves = job.moves || {};
      const months = [...new Set(job.days.map(d=>d.date.slice(0,7)))].sort();
      if(!months.includes(calMonth)) calMonth = months[0];
      const [Y,M] = calMonth.split('-').map(Number);
      const first = new Date(Y, M-1, 1);
      const startWd = (first.getDay()+6)%7;          // Montag = 0
      const dim = new Date(Y, M, 0).getDate();
      const ws = job.window_start, we = job.window_end;
      const allP = job.days.map(x=>x.price);
      const pmin = Math.min(...allP), pmax = Math.max(...allP);
      const offer = (curOffers||[]).find(x=>x.id===calId) || {};
      const base = offer.url || '';
      const nights = (job.duration) || 0;
      // Sparschwein-Icon (MDI piggy-bank) für den günstigsten Termin
      const PIG = '<svg class="cal-pig" aria-hidden="true" viewBox="0 0 960 960" fill="none" xmlns="http://www.w3.org/2000/svg"> <g clip-path="url(#pigclip)"> <path d="M426.591 879.981C422.074 879.981 417.557 879.981 413.04 879.981C411.752 879.787 410.463 879.558 409.168 879.404C401.148 878.444 393.027 877.995 385.114 876.444C366.282 872.766 356.436 859.914 357.926 841.283C358.53 833.706 359.718 826.162 360.886 818.646C362.644 807.35 364.617 796.082 366.51 784.74C349.597 780.874 332.597 776.981 316.262 773.243C315.195 781.491 314.295 789.78 313.02 798.008C311.503 807.847 310.175 817.76 307.852 827.418C304.349 841.968 295.973 852.726 280.617 855.813C274.289 857.089 267.396 857.337 261.04 856.31C247.899 854.183 234.805 851.404 221.94 847.961C197.295 841.364 185.362 824.679 186.812 799.23C187.705 783.532 190.282 768.048 194.913 752.961C197.564 744.324 201.094 736.075 206.027 728.377C205.483 727.968 205.128 727.666 204.745 727.418C178.57 710.511 158.282 687.894 141.55 661.921C110.805 614.196 94.6107 561.652 90.0872 505.297C89.7383 500.914 89.3624 496.532 89 492.156C89 483.498 89 474.84 89 466.189C89.1544 465.183 89.4027 464.176 89.443 463.162C90.0604 448.015 91.8389 433.001 94.7114 418.122C102.06 380.062 116.087 344.84 139.268 313.505C139.96 312.572 140.255 310.881 139.953 309.753C136.416 296.552 133.953 283.122 133.208 269.512C132.275 252.532 131.839 235.512 131.772 218.505C131.604 177.787 135.745 137.438 143.107 97.4041C144.477 89.9478 148.805 85.1222 155.658 82.3571C157.47 81.6256 159.396 81.1826 161.268 80.6055C163.523 80.6055 165.785 80.6055 168.04 80.6055C175.228 81.8873 180.322 86.337 184.799 91.7129C185.04 92.0014 185.309 92.2699 185.564 92.5384C213.711 122.102 241.852 151.679 270.02 181.23C279.054 190.713 287.859 200.371 294.047 212.055C294.987 213.827 296.027 213.189 297.295 212.793C308.047 209.418 318.718 205.78 329.57 202.78C351.906 196.599 374.604 192.357 397.792 191.136C403.893 190.814 410.02 190.894 416.087 190.31C430.772 188.901 445.423 187.149 460.107 185.699C462.289 185.485 463.987 184.934 465.624 183.451C489.832 161.592 516.416 143.156 545.55 128.458C548.275 127.082 551.295 126.035 554.295 125.505C566.43 123.371 576.705 130.27 578.295 141.518C580.671 158.27 582.94 175.028 585.175 191.8C585.389 193.418 586.034 194.008 587.584 194.277C590.913 194.854 594.208 195.632 597.51 196.364C638.477 205.424 677.624 219.418 714.349 239.847C758.322 264.303 795.826 296.095 824.248 337.948C850.248 376.236 866.081 418.256 869.846 464.592C870.134 468.136 870.53 471.673 870.879 475.216C870.879 482.934 870.879 490.646 870.879 498.364C870.329 504.142 869.832 509.928 869.228 515.706C865.732 549.337 856.248 581.236 841.262 611.505C823.315 647.74 798.43 678.599 768.094 705.162C766.369 706.673 765.785 708.189 765.752 710.458C765.617 720.612 765.55 730.787 764.886 740.914C763.94 755.364 762.812 769.807 761.168 784.189C760.04 794.048 758.423 803.928 756.067 813.558C753.557 823.8 747.255 831.518 737.342 835.867C730.772 838.746 723.832 839.766 716.725 839.881C702.409 840.122 688.524 837.109 674.597 834.357C668.886 833.23 664.993 829.907 663.315 824.498C662.309 821.25 661.839 817.659 662.007 814.263C662.389 806.572 663.43 798.914 664 791.223C664.544 783.934 664.826 776.619 665.248 768.954C659.074 771.33 653.208 773.538 647.403 775.887C646.859 776.109 646.436 777.183 646.362 777.901C645.322 788.659 644.497 799.444 643.315 810.189C642.289 819.545 640.651 828.807 636.678 837.458C629.53 853.035 617.584 861.975 600.282 862.525C590.436 862.834 580.53 862.323 570.691 861.672C563.745 861.216 556.94 859.619 550.685 856.277C543.685 852.532 539.201 846.807 539.154 838.807C539.101 829.243 539.819 819.666 540.477 810.115C540.758 806.055 541.745 802.042 542.329 798.505C517.919 798.505 493.738 798.505 470.423 798.505C468.738 810.035 467.436 821.142 465.423 832.109C463.537 842.364 460.933 852.485 455.94 861.793C451.275 870.485 444.168 876.048 434.557 878.337C431.913 878.961 429.242 879.438 426.591 879.981ZM388.007 246.163C385.705 244.069 383.369 241.807 380.873 239.746C380.067 239.082 378.752 238.465 377.812 238.632C369.497 240.142 361.154 241.592 352.933 243.518C308.993 253.82 268.175 271.572 229.698 295.035C208.389 308.028 190.517 324.498 176.691 345.277C154.275 378.981 143.993 416.558 141.503 456.565C139.718 485.283 142.154 513.693 148.295 541.78C155.215 573.444 166.503 603.377 184.463 630.532C200.396 654.612 220.235 674.558 246.242 687.813C261.53 695.605 277.765 700.948 293.953 706.471C355.524 727.478 418.524 740.787 483.758 742.545C521.235 743.558 558.389 741.156 594.987 732.626C657.765 717.995 711.383 687.35 754.685 639.505C788.644 601.981 809.376 558.196 814.047 507.371C817.248 472.518 811.953 438.928 798.396 406.706C781.852 367.371 755.128 336.062 721.403 310.465C687.188 284.498 648.752 267.156 607.557 255.605C602.45 254.176 597.295 252.914 592.175 251.579C591.416 253.988 592.242 254.961 594.208 255.646C599.443 257.458 604.638 259.397 609.785 261.444C636.644 272.142 662.282 285.31 687.134 300.048C691.477 302.626 694.557 306.169 695.295 311.283C696.409 318.988 693.584 325.223 687.356 329.673C681.289 334.015 675.034 333.183 668.852 329.485C649.886 318.142 630.416 307.74 610.208 298.767C605.248 296.565 600.222 294.512 594.926 292.256C595.06 295.243 595.309 297.767 595.268 300.283C595.161 307.726 590.832 313.471 583.846 315.23C576.456 317.089 569.919 315.27 564.215 310.236C561.993 308.277 561.181 306.062 561.564 303.015C564.242 281.626 563.282 260.196 561.852 238.78C560.718 221.699 559.275 204.646 558.242 187.558C557.436 174.209 545.329 167.438 533.685 174.062C514.456 184.995 496.953 198.23 480.946 213.471C458.06 235.263 439.081 260.216 421.517 286.364C414.658 296.579 418.329 307.169 425.315 313.163C425.926 313.686 426.523 314.223 427.154 314.78C420.523 319.887 410.148 320.156 401.134 314.988C388.168 307.552 382.443 296.733 387.081 281.491C386.235 281.673 385.698 281.78 385.175 281.907C373.772 284.706 362.423 287.74 350.96 290.25C338.98 292.874 326.846 294.297 314.544 292.84C310.188 292.324 306.765 290.371 305.356 286.055C303.913 281.626 305.524 277.921 308.893 274.941C310.087 273.887 311.416 272.981 312.738 272.075C326.181 262.847 341.262 257.404 356.893 253.384C367.235 250.74 377.691 248.545 388.007 246.163ZM181.772 270.384C204.376 252.256 230.181 240.538 255.671 229.169C230.678 203.069 205.779 177.069 180.591 150.76C175.973 168.552 176.839 249.807 181.772 270.384ZM276.275 761.699C261.658 755.746 247.356 749.921 232.94 744.055C231.926 749.33 230.826 754.834 229.819 760.35C228.094 769.86 226.221 779.35 224.785 788.901C222.913 801.35 227.859 807.431 240.349 808.995C247.691 809.914 254.993 811.136 262.322 812.183C263.228 812.31 264.168 812.203 265.409 812.203C266.282 806.035 267.208 800.015 267.98 793.975C269.389 782.82 269.966 771.471 276.275 761.699ZM721.725 740.324C720.591 740.525 720.289 740.505 720.067 740.626C711.993 745.223 703.899 749.793 695.893 754.498C695.114 754.954 694.423 756.23 694.383 757.156C693.933 767.666 693.55 778.176 693.302 788.693C693.228 791.934 693.631 795.183 693.826 798.579C701.846 798.579 709.503 798.579 717.685 798.579C719.02 779.277 720.356 760.008 721.725 740.324ZM568.846 822.149C574.128 822.149 579.094 822.022 584.047 822.183C589.087 822.35 594.121 822.814 599.315 823.156C602.074 819.089 605.04 796.746 603.772 788.773C593.718 790.565 583.664 792.337 573.617 794.189C573.054 794.29 572.302 794.981 572.161 795.525C569.987 804.001 568.389 812.552 568.846 822.149ZM398.537 832.995C404.248 833.666 409.295 834.116 414.295 834.907C417.101 835.35 418.181 834.203 418.711 831.706C420.154 824.827 421.946 818.015 423.121 811.089C424.054 805.599 424.289 799.981 424.839 794.357C417.101 793.263 409.879 792.236 402.745 791.23C401.336 805.203 399.953 818.975 398.537 832.995Z" fill="currentColor"/> <path d="M388.009 246.162C377.686 248.545 367.237 250.733 356.901 253.397C341.277 257.417 326.196 262.86 312.747 272.088C311.431 272.994 310.096 273.894 308.901 274.954C305.532 277.941 303.921 281.645 305.364 286.068C306.774 290.384 310.19 292.337 314.552 292.853C326.854 294.31 338.988 292.887 350.968 290.263C362.431 287.753 373.78 284.719 385.183 281.92C385.713 281.793 386.243 281.686 387.089 281.504C382.451 296.739 388.183 307.558 401.143 315.001C410.156 320.169 420.532 319.9 427.163 314.793C426.532 314.236 425.935 313.699 425.324 313.175C418.337 307.182 414.666 296.585 421.525 286.377C439.089 260.222 458.069 235.276 480.955 213.484C496.962 198.243 514.465 185.008 533.693 174.075C545.337 167.457 557.445 174.229 558.25 187.571C559.284 204.659 560.727 221.712 561.861 238.793C563.284 260.209 564.25 281.639 561.572 303.028C561.19 306.075 562.009 308.29 564.223 310.249C569.928 315.283 576.465 317.102 583.854 315.243C590.841 313.484 595.17 307.739 595.277 300.296C595.317 297.779 595.069 295.256 594.935 292.269C600.237 294.518 605.264 296.571 610.217 298.78C630.425 307.759 649.894 318.155 668.861 329.498C675.042 333.196 681.29 334.028 687.364 329.686C693.592 325.229 696.418 319.001 695.304 311.296C694.566 306.182 691.485 302.639 687.143 300.061C662.297 285.316 636.66 272.155 609.794 261.457C604.646 259.41 599.451 257.471 594.217 255.659C592.243 254.974 591.425 254.001 592.183 251.592C597.304 252.927 602.458 254.189 607.566 255.618C648.753 267.169 687.19 284.511 721.411 310.477C755.129 336.068 781.861 367.384 798.405 406.719C811.955 438.941 817.257 472.531 814.055 507.384C809.384 558.209 788.653 602.001 754.693 639.518C711.391 687.363 657.774 718.001 594.995 732.639C558.398 741.169 521.25 743.571 483.767 742.558C418.532 740.8 355.532 727.491 293.962 706.484C277.774 700.961 261.539 695.618 246.25 687.826C220.243 674.571 200.405 654.625 184.472 630.545C166.505 603.39 155.223 573.457 148.304 541.793C142.17 513.712 139.727 485.296 141.512 456.578C143.995 416.571 154.277 378.994 176.7 345.29C190.525 324.511 208.398 308.041 229.707 295.048C268.183 271.578 309.002 253.833 352.941 243.531C361.163 241.605 369.505 240.155 377.821 238.645C378.753 238.477 380.076 239.095 380.881 239.759C383.371 241.806 385.706 244.068 388.009 246.162ZM610.056 393.243C610.056 386.759 610.176 380.37 610.022 373.994C609.861 367.256 605.613 362.169 599.163 360.605C589.123 358.175 580.941 364.263 580.438 374.833C580.042 383.196 580.009 391.571 579.908 399.947C579.888 401.652 579.384 402.598 577.747 403.377C552.982 415.169 535.982 434.155 526.894 459.894C518.995 482.283 520.183 504.155 533.539 524.444C544.163 540.571 559.438 550.303 577.894 555.303C579.505 555.739 580.72 555.974 580.76 558.243C581.082 576.115 581.572 593.981 581.995 611.853C582.015 612.585 581.915 613.316 581.861 614.336C580.76 614.075 579.834 613.961 578.988 613.632C570.948 610.498 562.854 607.484 554.915 604.115C550.257 602.135 545.619 600.538 540.498 600.927C528.861 601.82 519.337 610.383 516.633 622.357C514.29 632.712 518.894 642.209 529.29 648.249C545.378 657.592 562.613 663.84 580.955 666.914C583.284 667.303 583.794 668.216 583.841 670.33C584.042 679.545 584.391 688.759 584.68 697.974C584.841 703.122 587.23 706.726 591.532 708.296C598.874 710.981 605.908 706.504 606.472 698.645C606.754 694.706 606.653 690.746 606.78 686.8C606.962 681.001 607.19 675.209 607.398 669.316C613.787 668.847 619.948 668.39 626.324 667.92C626.371 668.847 626.418 669.766 626.472 670.685C627.089 681.014 627.633 691.343 628.358 701.665C628.666 706.035 631.337 708.659 634.975 708.706C638.035 708.746 639.673 706.981 640.458 702.397C642.498 690.451 644.579 678.511 646.358 666.524C646.76 663.833 647.861 662.82 650.277 662.021C696.693 646.639 731.25 604.33 736.089 556.31C738.069 536.699 732.311 519.249 718.284 505.014C704.753 491.29 687.901 487.028 669.203 488.504C665.881 488.766 662.586 489.316 659.27 489.733C658.539 481.873 662.545 428.988 664.257 425.625C668.814 427.773 673.626 429.545 677.915 432.169C686.8 437.605 695.465 443.424 704.123 449.236C709.069 452.558 713.76 452.115 717.606 447.592C721.029 443.565 721.425 438.847 718.639 434.31C709.297 419.108 696.384 407.954 680.096 400.773C675.384 398.699 670.458 397.102 665.297 395.162C665.297 391.075 665.512 386.746 665.243 382.437C664.928 377.384 664.619 372.263 663.532 367.343C662.364 362.075 656.639 358.303 651.445 358.484C646.572 358.659 643.525 361.632 642.056 367.746C641.485 370.122 640.935 372.504 640.552 374.914C639.666 380.444 638.881 385.988 638.102 391.216C628.881 391.9 619.901 392.538 610.056 393.243ZM318.639 608.954C323.337 608.504 332.753 608.068 342.022 606.632C367.418 602.685 390.391 593.028 410.196 576.363C446.552 545.779 450.767 496.182 419.982 460.082C407.539 445.491 391.7 435.8 373.982 428.947C366.17 425.927 357.874 424.585 349.894 422.29C316.753 412.739 283.693 412.612 250.968 422.927C207.391 436.665 181.19 466.249 174.76 511.847C171.948 531.793 177.552 550.075 190.579 565.746C201.082 578.383 214.854 586.363 229.74 592.592C256.66 603.847 284.941 608.243 318.639 608.954ZM376.539 349.095C367.277 349.135 359.378 352.538 353.183 359.551C343.767 370.216 342.847 384.934 350.666 397.498C357.606 408.659 371.713 413.967 385.217 410.491C401.988 406.175 412.599 388.981 408.492 372.853C407.035 367.122 403.351 362.981 399.304 358.954C393.002 352.672 385.519 349.343 376.539 349.095ZM200.458 358.907C197.19 359.659 193.794 360.068 190.68 361.229C178.941 365.598 170.673 378.035 171.579 389.726C172.693 404.075 181.243 415.263 195.096 419.196C200.109 420.618 205.19 420.41 210.21 418.088C216.935 414.981 220.76 409.135 224.693 403.477C226.545 400.82 227.599 397.39 228.223 394.155C228.753 391.37 228.196 388.37 228.049 385.464C227.25 370.531 215.559 359.437 200.458 358.907ZM512.472 229.162C505.841 229.296 500.371 233.645 496.149 240.222C489.592 250.417 482.74 260.424 476.29 270.686C473.915 274.457 471.76 278.551 470.505 282.8C468.559 289.37 471.378 296.162 476.606 299.746C482.156 303.551 489.056 303.592 494.847 299.484C497.351 297.712 499.72 295.571 501.66 293.196C509.029 284.162 516.284 275.028 523.398 265.793C525.854 262.605 528.082 259.162 529.888 255.565C536.042 243.269 527.512 229.243 512.472 229.162Z" fill="white"/> <path d="M181.77 270.382C176.837 249.805 175.965 168.55 180.589 150.758C205.777 177.067 230.676 203.067 255.67 229.167C230.186 240.536 204.374 252.254 181.77 270.382Z" fill="white"/> <path d="M276.276 761.698C269.967 771.47 269.39 782.819 267.981 793.966C267.216 800.007 266.289 806.027 265.41 812.195C264.169 812.195 263.229 812.309 262.323 812.174C254.994 811.127 247.692 809.906 240.35 808.986C227.86 807.423 222.914 801.342 224.786 788.893C226.222 779.335 228.095 769.846 229.82 760.342C230.82 754.825 231.927 749.322 232.94 744.047C247.357 749.919 261.659 755.745 276.276 761.698Z" fill="white"/> <path d="M721.725 740.32C720.356 760.005 719.02 779.273 717.685 798.575C709.497 798.575 701.846 798.575 693.825 798.575C693.631 795.179 693.228 791.931 693.302 788.689C693.544 778.173 693.933 767.663 694.382 757.152C694.423 756.226 695.121 754.951 695.893 754.495C703.906 749.79 711.993 745.22 720.067 740.622C720.289 740.502 720.591 740.522 721.725 740.32Z" fill="white"/> <path d="M568.846 822.146C568.383 812.549 569.987 803.999 572.161 795.529C572.302 794.979 573.054 794.294 573.618 794.193C583.658 792.341 593.718 790.569 603.772 788.777C605.04 796.744 602.074 819.093 599.315 823.16C594.128 822.818 589.094 822.361 584.047 822.187C579.094 822.019 574.128 822.146 568.846 822.146Z" fill="white"/> <path d="M398.535 832.992C399.945 818.972 401.334 805.2 402.737 791.227C409.871 792.24 417.092 793.26 424.83 794.354C424.28 799.985 424.045 805.596 423.112 811.086C421.938 818.005 420.146 824.824 418.703 831.703C418.179 834.2 417.092 835.348 414.287 834.905C409.3 834.113 404.247 833.663 398.535 832.992Z" fill="white"/> <path d="M610.054 393.242C619.9 392.537 628.88 391.899 638.115 391.242C638.893 386.007 639.678 380.463 640.564 374.94C640.954 372.53 641.497 370.148 642.068 367.772C643.537 361.658 646.584 358.678 651.457 358.51C656.652 358.329 662.376 362.094 663.544 367.369C664.631 372.289 664.94 377.41 665.256 382.463C665.524 386.765 665.309 391.101 665.309 395.188C670.47 397.128 675.397 398.725 680.108 400.799C696.403 407.98 709.309 419.134 718.652 434.336C721.437 438.873 721.048 443.591 717.618 447.618C713.772 452.141 709.081 452.584 704.135 449.262C695.477 443.45 686.819 437.638 677.927 432.195C673.638 429.571 668.826 427.799 664.269 425.651C662.558 429.014 658.551 481.899 659.282 489.758C662.591 489.342 665.893 488.792 669.215 488.53C687.907 487.054 704.766 491.316 718.296 505.04C732.323 519.269 738.074 536.718 736.101 556.336C731.262 604.356 696.712 646.665 650.289 662.047C647.873 662.846 646.772 663.859 646.37 666.55C644.591 678.537 642.511 690.477 640.47 702.423C639.685 707.007 638.048 708.772 634.987 708.732C631.35 708.685 628.678 706.061 628.37 701.691C627.638 691.369 627.101 681.04 626.484 670.712C626.43 669.792 626.39 668.873 626.336 667.946C619.96 668.416 613.806 668.873 607.41 669.342C607.202 675.235 606.974 681.027 606.793 686.826C606.672 690.772 606.766 694.738 606.484 698.671C605.92 706.53 598.886 711.007 591.544 708.322C587.242 706.752 584.853 703.148 584.692 698C584.403 688.785 584.054 679.571 583.853 670.356C583.806 668.242 583.296 667.329 580.967 666.94C562.625 663.866 545.39 657.618 529.303 648.275C518.907 642.235 514.303 632.738 516.645 622.383C519.35 610.403 528.873 601.839 540.511 600.953C545.631 600.564 550.269 602.161 554.927 604.141C562.866 607.517 570.96 610.53 579.001 613.658C579.846 613.987 580.772 614.101 581.873 614.363C581.933 613.336 582.027 612.604 582.007 611.879C581.584 594.007 581.095 576.141 580.772 558.269C580.732 556 579.517 555.758 577.907 555.329C559.45 550.329 544.168 540.597 533.551 524.47C520.189 504.181 519.001 482.309 526.907 459.92C535.987 434.181 552.994 415.195 577.759 403.403C579.397 402.624 579.893 401.678 579.92 399.973C580.021 391.604 580.054 383.222 580.45 374.859C580.954 364.289 589.135 358.201 599.175 360.631C605.625 362.188 609.88 367.275 610.034 374.02C610.168 380.369 610.054 386.758 610.054 393.242ZM636.712 420.926C628.793 420.96 621.289 422.275 613.927 424.705C611.84 425.396 611.061 426.302 611.074 428.644C611.175 453.282 611.128 477.926 611.121 502.564C611.121 503.47 611.121 504.376 611.121 505.967C618.457 503.49 625.303 501.222 632.088 498.805C632.678 498.597 633.222 497.389 633.262 496.624C634.45 473.43 635.584 450.235 636.699 427.04C636.793 425.094 636.712 423.141 636.712 420.926ZM652.35 604.456C664.155 597.611 676.538 582.584 681.303 569.738C683.598 563.557 684.531 557.215 684.068 550.638C683.484 542.443 679.276 538.738 671.269 540.101C666.772 540.866 662.45 542.618 658.007 543.799C656.249 544.269 655.725 545.181 655.631 546.96C654.826 561.893 653.907 576.812 653.034 591.745C652.786 595.852 652.584 599.96 652.35 604.456ZM610.262 558.423C609.793 578.181 609.316 597.946 608.826 618.369C614.692 617.564 620.061 616.906 625.39 616C626.041 615.893 626.873 614.47 626.92 613.611C627.933 596.081 628.853 578.537 629.752 561C629.866 558.805 629.766 556.604 629.766 554.503C623.289 555.805 616.967 557.074 610.262 558.423ZM579.464 448.624C572.873 454.725 568.088 461.785 565.853 470.363C563.276 480.289 565.39 489.356 571.088 497.685C573.168 500.718 575.933 503.034 579.457 504.738C579.464 485.772 579.464 467.201 579.464 448.624Z" fill="currentColor"/> <path d="M318.639 608.952C284.935 608.24 256.66 603.844 229.74 592.583C214.854 586.354 201.082 578.374 190.579 565.737C177.552 550.066 171.948 531.791 174.76 511.838C181.19 466.24 207.391 436.656 250.968 422.918C283.7 412.603 316.753 412.73 349.894 422.281C357.874 424.583 366.17 425.918 373.982 428.938C391.7 435.791 407.539 445.482 419.982 460.072C450.767 496.173 446.552 545.77 410.196 576.354C390.391 593.019 367.418 602.676 342.022 606.623C332.76 608.066 323.337 608.502 318.639 608.952ZM313.566 562.093C325.116 561.999 336.324 560.891 347.21 557.596C360.713 553.509 373.129 547.435 382.821 536.838C389.478 529.556 393.076 521.005 391.525 511.025C390.888 506.918 388.982 503.019 387.834 498.972C383.525 483.811 372.841 474.247 359.404 467.556C351.532 463.636 343.062 460.905 334.868 457.616C332.72 456.757 330.686 455.408 328.465 454.978C305.438 450.529 282.807 452.106 260.686 459.979C241.619 466.757 227.827 479.334 219.787 497.965C216.559 505.442 215.156 513.267 216.847 521.381C219.29 533.106 226.928 540.636 237.492 545.052C261.874 555.254 287.203 561.569 313.566 562.093Z" fill="currentColor"/> <path d="M376.536 349.094C385.509 349.342 392.992 352.671 399.294 358.946C403.335 362.973 407.026 367.121 408.482 372.845C412.59 388.973 401.979 406.168 385.207 410.483C371.704 413.959 357.596 408.651 350.657 397.49C342.845 384.926 343.757 370.201 353.174 359.543C359.375 352.537 367.274 349.134 376.536 349.094Z" fill="currentColor"/> <path d="M200.455 358.906C215.555 359.43 227.253 370.53 228.039 385.47C228.193 388.369 228.75 391.376 228.213 394.161C227.596 397.396 226.535 400.819 224.683 403.483C220.75 409.141 216.924 414.98 210.2 418.094C205.179 420.416 200.099 420.618 195.086 419.202C181.24 415.275 172.69 404.081 171.569 389.732C170.656 378.04 178.931 365.598 190.669 361.235C193.79 360.067 197.186 359.665 200.455 358.906Z" fill="currentColor"/> <path d="M512.47 229.16C527.517 229.241 536.04 243.268 529.879 255.563C528.081 259.16 525.846 262.603 523.389 265.791C516.275 275.026 509.02 284.16 501.651 293.194C499.712 295.57 497.343 297.704 494.839 299.482C489.047 303.583 482.148 303.543 476.598 299.744C471.369 296.16 468.551 289.368 470.497 282.798C471.752 278.556 473.913 274.462 476.282 270.684C482.732 260.422 489.584 250.422 496.141 240.221C500.369 233.643 505.832 229.301 512.47 229.16Z" fill="currentColor"/> <path d="M636.712 420.926C636.712 423.141 636.792 425.094 636.699 427.04C635.584 450.235 634.45 473.429 633.262 496.624C633.222 497.396 632.678 498.597 632.088 498.805C625.296 501.221 618.457 503.49 611.121 505.966C611.121 504.375 611.121 503.469 611.121 502.563C611.128 477.926 611.175 453.281 611.074 428.644C611.068 426.302 611.839 425.389 613.927 424.704C621.289 422.275 628.792 420.959 636.712 420.926Z" fill="white"/> <path d="M652.348 604.456C652.589 599.953 652.791 595.852 653.026 591.745C653.898 576.818 654.817 561.892 655.623 546.959C655.717 545.181 656.24 544.261 657.999 543.798C662.435 542.624 666.757 540.865 671.26 540.1C679.274 538.738 683.482 542.443 684.059 550.637C684.522 557.208 683.589 563.557 681.294 569.738C676.536 582.584 664.153 597.61 652.348 604.456Z" fill="white"/> <path d="M610.262 558.424C616.966 557.082 623.295 555.807 629.772 554.512C629.772 556.606 629.872 558.814 629.758 561.008C628.859 578.545 627.933 596.089 626.926 613.619C626.879 614.471 626.04 615.894 625.396 616.008C620.067 616.914 614.698 617.572 608.832 618.377C609.315 597.948 609.785 578.183 610.262 558.424Z" fill="white"/> <path d="M579.463 448.625C579.463 467.202 579.463 485.779 579.463 504.739C575.94 503.034 573.168 500.719 571.094 497.685C565.396 489.363 563.282 480.289 565.859 470.363C568.088 461.779 572.873 454.719 579.463 448.625Z" fill="white"/> <path d="M313.565 562.095C287.202 561.572 261.874 555.256 237.491 545.062C226.934 540.646 219.29 533.115 216.847 521.391C215.155 513.276 216.558 505.444 219.786 497.974C227.833 479.337 241.619 466.766 260.686 459.988C282.813 452.122 305.437 450.538 328.464 454.988C330.686 455.417 332.719 456.766 334.867 457.625C343.061 460.914 351.525 463.639 359.404 467.565C372.84 474.256 383.518 483.82 387.833 498.981C388.981 503.028 390.887 506.927 391.525 511.035C393.075 521.015 389.478 529.558 382.82 536.847C373.129 547.451 360.713 553.518 347.209 557.605C336.33 560.894 325.115 561.995 313.565 562.095ZM355.223 503.162C355.008 501.659 354.988 498.86 354.189 496.303C351.518 487.78 346.102 481.565 337.283 479.337C328.934 477.223 321.585 479.8 315.921 486.27C309.981 493.062 309.605 501.102 311.78 509.391C313.276 515.102 315.343 520.666 316.793 526.391C318.397 532.74 322.229 536.592 328.545 537.833C335.357 539.176 341.572 537.599 345.518 531.699C351.008 523.498 354.565 514.417 355.223 503.162ZM288.746 506.511C288.572 504.954 288.464 503.545 288.249 502.156C286.451 490.532 273.88 482.464 263.062 485.968C251.088 489.847 246.491 503.149 252.853 515.115C253.813 516.927 254.437 519.075 254.598 521.115C255.176 528.142 259.008 533.263 265.384 535.035C271.666 536.78 278.317 534.431 281.806 528.733C285.981 521.914 288.115 514.357 288.746 506.511Z" fill="white"/> <path d="M355.221 503.16C354.563 514.415 351.006 523.495 345.523 531.703C341.577 537.603 335.369 539.18 328.55 537.838C322.235 536.596 318.402 532.737 316.798 526.395C315.355 520.67 313.288 515.106 311.785 509.395C309.61 501.106 309.98 493.066 315.926 486.274C321.59 479.804 328.939 477.227 337.288 479.341C346.107 481.569 351.523 487.784 354.194 496.308C354.986 498.858 355.006 501.657 355.221 503.16Z" fill="currentColor"/> <path d="M288.744 506.511C288.12 514.35 285.979 521.914 281.805 528.739C278.315 534.437 271.657 536.786 265.382 535.041C259.006 533.27 255.167 528.149 254.597 521.122C254.429 519.082 253.811 516.927 252.852 515.122C246.489 503.155 251.093 489.847 263.06 485.974C273.885 482.471 286.456 490.538 288.248 502.162C288.456 503.551 288.563 504.954 288.744 506.511Z" fill="currentColor"/> </g> <defs> <clipPath id="pigclip"> <rect width="781.879" height="800" fill="white" transform="translate(89 80)"/> </clipPath> </defs> </svg>';
      let cells = '';
      for(let i=0;i<startWd;i++) cells += '<div class="cal-cell empty"></div>';
      for(let d=1; d<=dim; d++){
        const iso = `${Y}-${String(M).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        const price = pm[iso];
        const inWin = (!ws||iso>=ws) && (!we||iso<=we);
        const cls = ['cal-cell'];
        if(!inWin) cls.push('out');
        if(iso===job.cheapest_date) cls.push('cheapest');
        if(iso===job.tracked_date) cls.push('tracked');
        const mv = moves[iso];
        let style = '';
        if(calTrendView){
          if(mv){  // Trend: rot=gestiegen, grün=gefallen
            const hue = mv.delta>0 ? 4 : 132;
            style = ` style="background:hsla(${hue},65%,45%,.22)"`;
          }
        } else if(price!=null){  // Heatmap: günstig=grün → teuer=rot
          const ratio = pmax>pmin ? (price-pmin)/(pmax-pmin) : 0;
          style = ` style="background:hsla(${Math.round(120*(1-ratio))},65%,45%,.22)"`;
        }
        const deltaBadge = mv ? `<span class="hist-diff ${mv.delta>0?'up':'down'}" style="margin:0;font-size:.68rem;padding:1px 5px">${mv.delta>0?'▲ +':'▼ '}${eur(mv.delta)}</span>` : '';
        const infoIcon = price!=null ? `<span class="cal-info" title="Preisverlauf für diesen Tag anzeigen" onclick="event.preventDefault();event.stopPropagation();openCalDayChart('${iso}')">📈</span>` : '';
        const inner = `<span class="cal-d">${d}</span>${infoIcon}`
          + (iso===job.cheapest_date?PIG:'')   // Sparschwein als direktes Zellenkind → mittig
          + (calTrendView && mv ? deltaBadge
             : price!=null ? `<span class="cal-p">${eur(price)}</span>` : '<span class="cal-p na">–</span>');
        if(price!=null && base){
          cls.push('clk');
          cells += `<a class="${cls.join(' ')}" href="${esc(dayUrl(base,iso,nights))}" target="_blank" rel="noopener" oncontextmenu="return saveCalDay(event,'${iso}')" title="Linksklick: Termin auf tui.com öffnen · Rechtsklick: als neues Angebot tracken"${style}>${inner}</a>`;
        } else {
          cells += `<div class="${cls.join(' ')}"${style}>${inner}</div>`;
        }
      }
      const idx = months.indexOf(calMonth);
      const prev = idx>0?months[idx-1]:'', next = idx<months.length-1?months[idx+1]:'';
      const monthName = first.toLocaleDateString('de-DE',{month:'long',year:'numeric'});
      let sum = job.cheapest_date ? `Günstigster Termin: <b>${fmtD(job.cheapest_date)}</b> ${eur(job.cheapest_price)}` : '';
      if(job.tracked_date && job.tracked_date!==job.cheapest_date) sum += ` · In deinem Zeitraum: <b>${fmtD(job.tracked_date)}</b> ${eur(job.tracked_price)}`;
      const topMoves = job.top_moves || [];
      const topMovesHtml = topMoves.length ? `<details class="cal-moves" ${calMovesOpen?'open':''}
          ontoggle="calMovesOpen=this.open">
          <summary class="hint"><b>Größte Bewegungen seit letztem Abruf</b> (${topMoves.length})</summary>
          ${topMoves.map(m=>`<div class="cal-move-row" onclick="calGo('${m.date.slice(0,7)}');openCalDayChart('${m.date}')">
            <span>${fmtD(m.date)}</span>
            <span class="hist-diff ${m.delta>0?'up':'down'}">${m.delta>0?'▲ +':'▼ '}${eur(m.delta)}</span>
            <span class="hint">${eur(m.prev_price)} → ${eur(m.price)}</span>
          </div>`).join('')}
        </details>` : '';
      $('#cal-body').innerHTML = `
        <div class="cal-sum">${sum}</div>
        ${topMovesHtml}
        <div class="cal-nav">
          <button class="btn sec" onclick="calGo('${prev}')" ${prev?'':'disabled'}>‹</button>
          <span class="cal-title">${monthName}</span>
          <div style="display:flex;gap:6px;align-items:center">
            <button class="btn sec" onclick="toggleCalTrend()" title="Preis- oder Trend-Ansicht umschalten">${calTrendView?'💰 Preis':'📈 Trend'}</button>
            <button class="btn sec" onclick="calGo('${next}')" ${next?'':'disabled'}>›</button>
          </div>
        </div>
        <div class="cal-grid head">${['Mo','Di','Mi','Do','Fr','Sa','So'].map(w=>`<div class="cal-wd">${w}</div>`).join('')}</div>
        <div class="cal-grid">${cells}</div>
        <div id="cal-day-chart" class="cal-day-chart"></div>
        <div class="cal-legend">
          <span><i class="lg-cheap"></i>${PIG}günstigster Termin</span>
          <span><i class="lg-track"></i>günstigster in deinem Zeitraum</span>
          <span><i class="lg-out"></i>außerhalb deines Zeitraums</span>
          <span>🟩→🟥 günstig→teuer · Klick: auf tui.com öffnen · Rechtsklick: als neues Angebot tracken · 📈: Preisverlauf dieses Tages</span>
        </div>${calFooter(job)}`;
    }

    async function addOffer(){
      const url = $('#new-url').value.trim();
      const label = $('#new-label').value.trim();
      if(!url){ toast('Bitte eine URL eingeben'); return; }
      const r = await fetch(api('/api/offers'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url,label})});
      if(r.status===409){ toast('Dieses Angebot wird bereits verfolgt'); return; }
      if(r.status===400){ toast('Keine gültige tui.com-URL'); return; }
      if(!r.ok){ toast('Fehler beim Hinzufügen'); return; }
      $('#new-url').value=''; $('#new-label').value='';
      toast('Hinzugefügt – wird geprüft…');
      loadOffers();
    }
    async function delOffer(id){
      if(!confirm('Dieses Angebot inklusive Verlauf löschen?')) return;
      await fetch(api('/api/offers/'+id), {method:'DELETE'});
      loadOffers();
    }
    async function setTarget(id){
      const el = document.getElementById('tgt-'+id);
      const val = el && el.value.trim() ? parseFloat(el.value) : null;
      await fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({target_price: val})});
      toast(val ? ('Wunschpreis gesetzt: '+eur(val)) : 'Wunschpreis entfernt');
      loadOffers();
    }
    async function setBooked(id){
      const el = document.getElementById('book-'+id);
      const val = el && el.value.trim() ? parseFloat(el.value) : null;
      await fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({booked_price: val})});
      toast(val ? ('Gebuchter Preis gesetzt: '+eur(val)) : 'Gebuchter Preis entfernt');
      lastSig=null; loadOffers();
    }
    async function renameOffer(id){
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      const v = prompt('Eigener Name für dieses Angebot (leer = Hotelname verwenden):', o.label || '');
      if(v===null) return;
      await fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({label: v.trim()})});
      toast('Name gespeichert'); loadOffers();
    }
    async function addTag(id){
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      const v = (prompt('Tag hinzufügen (z. B. Strand, Familie):') || '').trim();
      if(!v) return;
      const tags = Array.from(new Set([...(o.tags||[]), v]));
      await fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tags})});
      toast('Tag hinzugefügt'); loadOffers();
    }
    async function removeTag(id, tag){
      const o = (curOffers||[]).find(x=>x.id===id) || {};
      const tags = (o.tags||[]).filter(t=>t!==tag);
      await fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tags})});
      toast('Tag entfernt'); loadOffers();
    }
    async function togglePause(id, paused){
      await fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({paused: !paused})});
      toast(paused ? 'Tracking fortgesetzt' : 'Tracking pausiert'); loadOffers();
    }
    async function archiveOffer(id){
      await fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({archived: true})});
      toast('Ins Archiv gelegt'); loadOffers();
    }
    async function unarchiveOffer(id){
      await fetch(api('/api/offers/'+id), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({archived: false})});
      toast('Reaktiviert – wird wieder verfolgt'); loadOffers();
    }
    async function exportCsv(){
      if(histId==null) return;
      try {
        const r = await fetch(api('/api/history/'+histId+'/csv'));
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = 'tuiwatch_'+histId+'.csv';
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
      } catch(e){ toast('Export fehlgeschlagen'); }
    }
    async function resetOffer(id){
      if(!confirm('Alle bisher getrackten Preise dieses Angebots löschen und neu bei null beginnen?')) return;
      await fetch(api('/api/reset/'+id), {method:'POST'});
      toast('Zurückgesetzt – wird neu geprüft…');
      loadOffers();
    }
    async function checkOne(id){ await fetch(api('/api/check/'+id), {method:'POST'}); toast('Prüfung gestartet…'); loadOffers(); }
    async function checkAll(){
      const r = await fetch(api('/api/check-now'), {method:'POST'});
      if(r.status===429){ const d = await r.json().catch(()=>({})); toast('Bitte kurz warten ('+(d.retry_after||60)+'s) — läuft schon eine Prüfung'); return; }
      toast('Alle Angebote werden geprüft…'); loadOffers();
    }

    async function sendEmail(){
      await openEmailModal(null);
    }
    let emailIds = null;    // null = alle aktiven Angebote, Array = Sammelaktion
    let emailMode = 'offers';  // 'offers' | 'ai' — steuert, wohin submitEmail() sendet
    async function _openEmailModalCommon(){
      let cfg; try { cfg = await fetch(api('/api/email')).then(r=>r.json()); } catch(e){ cfg = {configured:false}; }
      if(!cfg.configured){ toast('SMTP ist nicht konfiguriert (Add-on-Optionen)'); return false; }
      $('#email-to').value = localStorage.getItem('tw-mailto') || cfg.default_to || '';
      try {
        const c = await fetch(api('/api/contacts')).then(r=>r.json());
        $('#nc-contacts').innerHTML = (c.contacts||[])
          .map(k=>`<option value="${esc(k.email)}">${esc(k.name)}</option>`).join('');
      } catch(e){ $('#nc-contacts').innerHTML = ''; }
      // über anderen Modals (z.B. Reisen-Zusammenfassung) geöffnet -> gleicher
      // z-index wie alle .modal-bg, DOM-Reihenfolge würde sonst dahinter landen
      $('#email-bg').style.zIndex = 60;
      $('#email-bg').classList.add('show');
      return true;
    }
    async function openEmailModal(ids){
      emailMode = 'offers';
      emailIds = ids;
      await _openEmailModalCommon();
    }
    async function openAiEmailModal(){
      if(aiCurrentId == null){ toast('Diese Analyse kann noch nicht per E-Mail versendet werden'); return; }
      emailMode = 'ai';
      await _openEmailModalCommon();
    }
    function closeEmailModal(){ $('#email-bg').classList.remove('show'); $('#email-bg').style.zIndex = ''; }
    $('#email-bg').addEventListener('click', e=>{ if(e.target.id==='email-bg') closeEmailModal(); });
    async function submitEmail(){
      const to = $('#email-to').value;
      if(!to.trim()){ toast('Kein Empfänger angegeben'); return; }
      localStorage.setItem('tw-mailto', to.trim());
      closeEmailModal();
      if(emailMode === 'ai') return submitAiEmail(to.trim());
      if(emailMode === 'trips') return submitTripSummaryEmail(to.trim());
      toast('E-Mail wird gesendet…');
      const body = {to: to.trim()};
      if(emailIds) body.ids = emailIds;
      const r = await fetch(api('/api/email'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
      if(r.ok){ const d=await r.json(); toast('E-Mail an '+d.to+' gesendet ('+d.count+' Angebote)'); }
      else { const d=await r.json().catch(()=>({})); toast(d.error==='no_offers'?'Keine (aktiven) Angebote vorhanden':d.error==='send_failed'?'Versand fehlgeschlagen – Einstellungen prüfen':d.error==='no_recipient'?'Kein Empfänger':'E-Mail-Fehler'); }
    }
    async function submitAiEmail(to){
      toast('KI-Analyse wird gesendet…');
      let r; try {
        r = await fetch(api('/api/ai/email'), {method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({id: aiCurrentId, to})});
      } catch(e){ toast('Versand fehlgeschlagen'); return; }
      if(r.ok){ toast('KI-Analyse an '+to+' gesendet'); }
      else { const d=await r.json().catch(()=>({})); toast(d.error==='send_failed'?'Versand fehlgeschlagen – Einstellungen prüfen':d.error==='no_recipient'?'Kein Empfänger':d.error==='not_found'?'Analyse nicht gefunden':'Fehler beim Versand'); }
    }
    async function sendDigest(){
      toast('Wochenüberblick wird gesendet…');
      try{
        const r = await fetch(api('/api/digest'), {method:'POST'});
        const d = await r.json().catch(()=>({}));
        if(d.sent) toast('Wochenüberblick gesendet');
        else toast(d.note || 'Nichts zu senden');
      }catch(e){ toast('Versand fehlgeschlagen'); }
    }
    async function backupOffers(){
      try {
        const r = await fetch(api('/api/backup')); const blob = await r.blob();
        // Bewusst NICHT an document.body anhängen: das DOM-Insert+Remove um den
        // synthetischen Klick herum ist ein bekannter Ausloeser dafuer, dass Chrome
        // danach den :hover-Tracking-Zustand fuer andere Elemente auf der Seite
        // "verliert" (behebbar nur durch Reload oder echte Mausbewegung) — ein
        // losgeloestes <a> reicht für .click() mit download-Attribut völlig aus.
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = 'tuiwatch-backup.zip'; a.click(); URL.revokeObjectURL(a.href);
        toast('Backup heruntergeladen');
      } catch(e){ toast('Backup fehlgeschlagen'); }
    }
    async function restoreOffers(input){
      const f = input.files && input.files[0]; input.value=''; if(!f) return;
      const fd = new FormData(); fd.append('file', f);
      let r; try { r = await fetch(api('/api/restore'), {method:'POST', body:fd}); }
      catch(e){ toast('Wiederherstellung fehlgeschlagen'); return; }
      if(r.ok){
        const d=await r.json();
        const parts = [d.added+' Angebote'];
        if(d.trips) parts.push(d.trips+' Reisen');
        if(d.searches) parts.push(d.searches+' Suchen');
        if(d.ai_history) parts.push(d.ai_history+' KI-Verlauf');
        if(d.settings) parts.push(d.settings+' KI-Einstellungen');
        toast('Wiederhergestellt: '+parts.join(', ')+(d.skipped?(' ('+d.skipped+' übersprungen)'):''));
        loadOffers();
      } else toast('Wiederherstellung fehlgeschlagen');
    }

    function renderOverview(offers){
      const el = $('#overview'); if(!el) return;
      offers = offers || [];
      const archived = offers.filter(o=>o.archived);
      const histOnly = offers.filter(o=>!o.archived && o.history_only);
      const active = offers.filter(o=>!o.archived && !o.history_only);
      // Archiv-/Preisverlauf-Zähler an den Umschaltern
      const ac = $('#arch-count'); if(ac) ac.textContent = archived.length ? '('+archived.length+')' : '';
      const hc = $('#hist-count'); if(hc) hc.textContent = histOnly.length ? '('+histOnly.length+')' : '';
      if(!offers.length){ el.style.display='none'; el.innerHTML=''; return; }
      const ok = active.filter(o=>o.price!=null && o.ok);
      let html = '<b>'+active.length+'</b> Angebote';
      if(ok.length){
        const cheap = ok.reduce((a,b)=>b.price<a.price?b:a);
        html += ' · günstigstes: <b>'+esc(cheap.label||cheap.hotel||'')+'</b> '+eur(cheap.price);
        const below = ok.filter(o=>o.target_price && o.price<=o.target_price).length;
        if(below) html += ' · <span style="color:var(--green);font-weight:600">'+below+' unter Wunschpreis</span>';
      }
      const paused = active.filter(o=>o.paused).length;
      if(paused) html += ' · '+paused+' pausiert';
      if(histOnly.length) html += ' · '+histOnly.length+' im Preisverlauf-Tracking';
      if(archived.length) html += ' · '+archived.length+' archiviert';
      el.innerHTML = html; el.style.display='block';
    }

    // ── API-Selbsttest ──────────────────────────────────────────────────────
    let healthData = null;
    function setHealthDot(d){
      const dot = $('#hc-dot'); if(!dot) return;
      if(!d || !d.checks || !d.checks.length){
        if(d && d.running){ dot.className='wait'; dot.textContent='prüft…'; }
        else { dot.className='wait'; dot.textContent='–'; }
        return;
      }
      const bad = d.checks.filter(c=>!c.ok);
      if(!bad.length){ dot.className='ok'; dot.textContent='OK'; }
      else if(d.ok){ dot.className='warn'; dot.textContent=bad.length+' Hinweis'+(bad.length>1?'e':''); }
      else { dot.className='bad'; dot.textContent=bad.length+' Fehler'; }
    }
    function renderHealthBody(d){
      const sub=$('#hc-sub'), body=$('#hc-body');
      if(d && d.running && (!d.checks||!d.checks.length)){
        sub.textContent='Prüfung läuft…'; body.innerHTML=progBar('Endpunkte werden geprüft…',0,0); return;
      }
      if(!d || !d.checks || !d.checks.length){
        sub.textContent=''; body.innerHTML='<div class="empty">Noch kein Testergebnis. Auf „Erneut prüfen" klicken.</div>'; return;
      }
      sub.innerHTML = (d.ok?'Alle kritischen Endpunkte funktionieren.':'Es gibt Probleme bei kritischen Endpunkten.')
        + (d.ts?(' · zuletzt: '+new Date(d.ts*1000).toLocaleString('de-DE')):'');
      body.innerHTML = d.checks.map(c=>
        '<div class="hc-row '+(c.ok?'ok':'bad')+'"><span class="hc-name">'+esc(c.name)
        +(c.critical?' <span class="hc-detail">(kritisch)</span>':'')
        +'</span><span class="hc-detail">'+esc(c.ok?c.detail:('Fehler: '+c.detail))+'</span></div>').join('');
    }
    async function loadHealth(){
      try{ const r=await fetch(api('/api/healthcheck'));
        if(r.status===401){ location.reload(); return; }
        if(!r.ok) return;
        healthData=await r.json(); setHealthDot(healthData);
        if($('#hc-bg').classList.contains('show')) renderHealthBody(healthData);
      }catch(e){}
    }
    function openHealth(){
      $('#hc-bg').classList.add('show');
      renderHealthBody(healthData);
      if(!healthData || !healthData.checks || !healthData.checks.length) runHealth();
    }
    async function runHealth(){
      $('#hc-dot').className='wait'; $('#hc-dot').textContent='prüft…';
      renderHealthBody({running:true});
      try{ const r=await fetch(api('/api/healthcheck'),{method:'POST'});
        healthData=await r.json();
      }catch(e){ healthData={ok:false,checks:[],note:'Anfrage fehlgeschlagen'}; }
      setHealthDot(healthData); renderHealthBody(healthData);
    }

    $('#add-btn').addEventListener('click', addOffer);
    $('#new-url').addEventListener('keydown', e=>{ if(e.key==='Enter') addOffer(); });
    $('#new-label').addEventListener('keydown', e=>{ if(e.key==='Enter') addOffer(); });
    $('#check-all').addEventListener('click', checkAll);
    $('#search').addEventListener('input', e=>{ searchTerm = e.target.value; renderAll(curOffers||[]); });

    // ── ✕ zum Leeren in Suchfeldern ────────────────────────────────────────────
    // Generisch statt pro Feld: jedes Text-/Suchfeld mit „Such…"/🔍 im Placeholder
    // bekommt beim ersten Fokus ein ✕ (deckt auch dynamisch gerenderte Felder ab,
    // z. B. Reiseziel-Picker). Klick leert + feuert 'input', damit Filter/Listen
    // sofort mitziehen.
    function attachClearX(inp){
      if(!inp || inp.dataset.clearx) return;
      inp.dataset.clearx = '1';
      const wrap = document.createElement('span');
      wrap.className = 'clearx-wrap';
      inp.parentNode.insertBefore(wrap, inp);
      wrap.appendChild(inp);
      const x = document.createElement('span');
      x.className = 'clearx'; x.textContent = '✕'; x.title = 'Feld leeren';
      x.addEventListener('mousedown', e=>e.preventDefault());   // Fokus im Feld halten
      x.addEventListener('click', ()=>{ inp.value=''; inp.dispatchEvent(new Event('input', {bubbles:true})); inp.focus(); });
      wrap.appendChild(x);
      const upd = ()=>{ x.style.display = inp.value ? '' : 'none'; };
      inp.addEventListener('input', upd);
      upd();
    }
    document.addEventListener('focusin', e=>{
      const el = e.target;
      if(el.tagName==='INPUT' && (el.type==='text'||el.type==='search')
         && /such|🔍/i.test(el.placeholder||'')) attachClearX(el);
    });
    attachClearX($('#search'));   // Hauptsuche sofort sichtbar, nicht erst beim Fokus

    $('#sort').value = sortMode;
    $('#sort').addEventListener('change', e=>{ sortMode = e.target.value; localStorage.setItem('tw-sort', sortMode); renderAll(curOffers||[]); });
    $('#show-archived').checked = showArchived;
    $('#show-archived').addEventListener('change', e=>{ showArchived = e.target.checked; localStorage.setItem('tw-show-archived', showArchived?'1':'0'); renderAll(curOffers||[]); });
    $('#show-histonly').checked = showHistOnly;
    $('#show-histonly').addEventListener('change', e=>{ showHistOnly = e.target.checked; localStorage.setItem('tw-show-histonly', showHistOnly?'1':'0'); renderAll(curOffers||[]); });

    if('serviceWorker' in navigator){ try{ navigator.serviceWorker.register((G.base||'')+'/sw.js', {scope:(G.base||'')+'/'}); }catch(e){} }

    loadOffers();
    setInterval(loadOffers, 5000);
    loadHealth();
    updateAktionBtn();
    setInterval(updateAktionBtn, 600000);   // Button-Leuchten alle 10 min aktualisieren
    updateTrendBtn();
    setInterval(updateTrendBtn, 600000);
    setInterval(loadHealth, 60000);

    // ── Countdown zur nächsten Reise (Header) ─────────────────────────────────
    let nextTrip = null;
    async function loadNextTrip(){
      try { const d = await fetch(api('/api/trips/next')).then(r=>r.json()); nextTrip = d.trip||null; }
      catch(e){ nextTrip = null; }
      renderTripCountdown();
    }
    function renderTripCountdown(){
      const box = $('#trip-countdown');
      if(!nextTrip){ box.style.display='none'; return; }
      box.style.display='inline-flex';
      $('#tc-dest').textContent = nextTrip.destination || 'Nächste Reise';
      const diff = new Date(nextTrip.departure).getTime() - Date.now();
      if(diff <= 0){ $('#tc-time').textContent = 'Gute Reise!'; return; }
      const mins = Math.floor(diff/60000);
      const d = Math.floor(mins/1440), h = Math.floor((mins%1440)/60), m = mins%60;
      const parts = [];
      if(d) parts.push(d+' Tag'+(d===1?'':'e'));
      if(d || h) parts.push(h+' Std');
      if(!d) parts.push(m+' Min');
      $('#tc-time').textContent = 'noch '+parts.join(' ');
    }
    loadNextTrip();
    setInterval(renderTripCountdown, 30000);
    setInterval(loadNextTrip, 300000);

    function fmtBytes(n){
      if(n < 1024) return n+' B';
      if(n < 1024*1024) return (n/1024).toFixed(1)+' KB';
      return (n/1024/1024).toFixed(1)+' MB';
    }
    async function loadDbSize(){
      try { const d = await fetch(api('/api/dbsize')).then(r=>r.json()); $('#db-size').textContent = fmtBytes(d.bytes||0); }
      catch(e){}
    }
    loadDbSize();
    setInterval(loadDbSize, 300000);

    async function loadAiUsageFooter(){
      if(!G.ai) return;
      try {
        const d = await fetch(api('/api/ai/usage')).then(r=>r.json());
        $('#ai-usage-foot').textContent =
          '🔢 KI heute ' + fmtUsd(d.today && d.today.estimated_usd) +
          ' · Monat ' + fmtUsd(d.month && d.month.estimated_usd) +
          ' · gesamt ' + fmtUsd(d.estimated_usd);
      } catch(e){}
    }
    loadAiUsageFooter();
    setInterval(loadAiUsageFooter, 300000);

    const AI_PROVIDER_LABEL = { anthropic: '🤖 Claude', gemini: '✨ Gemini', perplexity: '🔎 Perplexity' };
    const AI_PROVIDER_NAME = Object.fromEntries(
      Object.entries(AI_PROVIDER_LABEL).map(([k,v]) => [k, v.replace(/^\S+\s/, '')]));
    let _aiActiveProvider = null;  // zuletzt bekannter aktiver Provider, für "<Name> durchsucht…" in Ladetexten
    let _aiProviderLoadPromise = null;
    function aiProviderName(){ return AI_PROVIDER_NAME[_aiActiveProvider] || 'KI'; }
    // Stellt sicher, dass _aiActiveProvider gesetzt ist, bevor ein Ladetext gebaut wird
    // (verhindert Race Condition beim Seitenaufruf, bei der aiProviderName() noch 'KI' liefert)
    function ensureAiProviderLoaded(){
      if(_aiActiveProvider) return Promise.resolve();
      if(!_aiProviderLoadPromise) _aiProviderLoadPromise = loadAiProviderFooter();
      return _aiProviderLoadPromise;
    }
    async function loadAiProviderFooter(){
      if(!G.ai) return;
      try {
        const d = await fetch(api('/api/ai/provider')).then(r=>r.json());
        _aiActiveProvider = d.active;
        const el = $('#ai-provider-foot');
        if(!d.both_configured){ el.style.display = 'none'; return; }
        el.style.display = '';
        el.textContent = '· ' + (AI_PROVIDER_LABEL[d.active] || d.active) + ' aktiv';
      } catch(e){}
    }
    async function toggleAiProvider(){
      try {
        const cur = await fetch(api('/api/ai/provider')).then(r=>r.json());
        const list = cur.configured_providers || [];
        if(!cur.both_configured || list.length < 2) return;
        // Zyklisch zum nächsten konfigurierten Provider (feste Reihenfolge aus der API)
        const next = list[(list.indexOf(cur.active) + 1) % list.length];
        await fetch(api('/api/ai/provider'), {method:'POST',
          headers:{'Content-Type':'application/json'}, body: JSON.stringify({provider: next})});
        _aiActiveProvider = next;
        toast((AI_PROVIDER_LABEL[next] || next) + ' aktiv');
        loadAiProviderFooter();
      } catch(e){ toast('Umschalten fehlgeschlagen'); }
    }
    loadAiProviderFooter();
