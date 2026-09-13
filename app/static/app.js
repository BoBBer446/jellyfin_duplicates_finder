"use strict";
const $ = id => document.getElementById(id);
let scan = null, busy = false, selected = new Set(), shown = 30;
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function bytes(n) {
  if (!n) return "0 B";
  const i = Math.min(4,Math.floor(Math.log(n)/Math.log(1024)));
  return new Intl.NumberFormat("de-DE",{maximumFractionDigits:1}).format(n/1024**i)+" "+["B","KiB","MiB","GiB","TiB"][i];
}
function status(message,tone="") { $("status").textContent=message; $("status").className=tone; }
function groups() {
  const q=$("filterInput").value.trim().toLocaleLowerCase("de");
  return (scan?.groups || []).filter(g=>!q || [g.identifier,...g.items.map(i=>i.name+" "+i.path)].join(" ").toLocaleLowerCase("de").includes(q))
    .sort((a,b)=>$("sortInput").value==="title" ? a.identifier.localeCompare(b.identifier,"de") :
      $("sortInput").value==="confidence" ? a.confidence.localeCompare(b.confidence)||b.reclaimable_bytes-a.reclaimable_bytes : b.reclaimable_bytes-a.reclaimable_bytes);
}
function controls() {
  document.querySelectorAll("button,input,select").forEach(el=>{el.disabled=busy;});
  const canDelete=!busy && scan?.source==="jellyfin" && selected.size>0;
  $("deleteBtn").disabled=$("dryRunBtn").disabled=!canDelete;
  $("exportBtn").disabled=busy||!scan;
  $("selectAllBtn").disabled=busy||!groups().length;
  $("selectNoneBtn").disabled=busy||!selected.size;
  const size=(scan?.groups||[]).flatMap(g=>g.items).filter(i=>selected.has(i.id)).reduce((n,i)=>n+i.size,0);
  $("selectedCount").textContent=selected.size ? selected.size+" ausgewählt · "+bytes(size) : "Keine Auswahl";
  $("sourceHint").textContent=scan?.source==="file" ? "Dateianalyse: Löschen ist nur nach einem Jellyfin-Scan möglich." : "Es werden nur ausgewählte Dateien gelöscht.";
  document.querySelector(".workspace").setAttribute("aria-busy",String(busy));
}
function render() {
  const s=scan?.summary;
  $("summary").innerHTML=[["Einträge",s?.total_items??"—"],["Duplikatgruppen",s?.duplicate_groups??"—"],["Geschätzter Gewinn",s?bytes(s.reclaimable_bytes):"—"],["Ausgeschlossen",s?.skipped_items??"—"]]
    .map(([label,value])=>'<div class="metric"><span>'+label+"</span><strong>"+esc(value)+"</strong></div>").join("");
  const filtered=groups(), visible=filtered.slice(0,shown);
  if (scan) $("results").innerHTML=visible.length ? visible.map(g=>{
    const candidates=new Set(g.delete_candidates);
    return '<article class="group"><div class="group-head"><h3>'+esc(g.identifier)+'</h3><strong>'+bytes(g.reclaimable_bytes)+' möglich</strong></div><p class="reason">'+esc(g.match_reason)+" · "+(g.confidence==="high"?"starker Metadaten-Treffer":"bitte besonders sorgfältig prüfen")+"</p>"+
    g.items.map(i=>{
      const keep=i.id===g.keep_item_id, resolution=i.width&&i.height ? i.width+" × "+i.height : "Auflösung unbekannt";
      return '<div class="media-row '+(keep?"keep":"")+'"><div>'+
        (candidates.has(i.id)?'<input type="checkbox" aria-label="'+esc(i.name)+' zum Löschen auswählen" data-id="'+esc(i.id)+'" '+(selected.has(i.id)?"checked":"")+'>':'<span aria-label="Behalten">✓</span>')+
        '</div><div><div class="media-title">'+esc(i.name)+(keep?'<span class="badge">BEHALTEN</span>':"")+'</div><div class="path">'+esc(i.path)+'</div></div><div class="media-meta">'+bytes(i.size)+'<br><span class="muted small">'+resolution+
        (i.codec?" · "+esc(i.codec.toUpperCase()):"")+(i.runtime_seconds?"<br>"+Math.round(i.runtime_seconds/60)+" min":"")+"</span></div></div>";
    }).join("")+"</article>";
  }).join("") : '<div class="empty"><span aria-hidden="true">✓</span><h3>'+(scan.groups.length?"Keine Treffer im Filter":"Keine Duplikate erkannt")+"</h3><p>"+(scan.groups.length?"Passe den Suchbegriff an.":"Einträge mit unklaren Metadaten werden nicht als Löschkandidaten vorgeschlagen.")+"</p></div>";
  $("moreBtn").hidden=filtered.length<=shown;
  $("moreBtn").textContent="Weitere Treffer anzeigen ("+Math.max(0,filtered.length-shown)+")";
  controls();
}
async function api(url,options={}) {
  const response=await fetch(url,options), text=await response.text();
  let body;try {body=JSON.parse(text);}catch {throw new Error("Unerwartete Serverantwort (HTTP "+response.status+").");}
  if (!response.ok) throw new Error((Array.isArray(body.detail)?body.detail.map(e=>e.msg).join("; "):body.detail)||"HTTP "+response.status);
  return body;
}
async function task(message,fn) {
  if(busy)return;busy=true;status(message,"busy");controls();
  try{await fn();}catch(e){status(e.message||"Verbindung fehlgeschlagen.","error");}
  finally{busy=false;render();}
}
const sequences=()=>$("customSequences").value.split(",").map(s=>s.trim()).filter(Boolean);
$("scanForm").addEventListener("submit",e=>{
  e.preventDefault();
  const types=[$("typeMovie").checked&&"Movie",$("typeEpisode").checked&&"Episode"].filter(Boolean);
  if(!types.length)return status("Wähle mindestens einen Medientyp.","error");
  task("Bibliothek wird eingelesen und verglichen …",async()=>{
    selected.clear();
    scan=await api("/api/v1/scans/jellyfin",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      base_url:$("baseUrl").value.trim(),api_key:$("apiKey").value.trim(),include_item_types:types,
      verify_ssl:$("verifySsl").checked,custom_sequences:sequences()})});
    shown=30;status("Scan abgeschlossen. Prüfe die Treffer und wähle Dateien aus.");
  });
});
$("scanFileBtn").addEventListener("click",()=>{
  const file=$("jsonFile").files[0];
  if(!file)return status("Wähle zuerst eine JSON-Datei.","error");
  if(file.size>50*1024*1024)return status("Die Datei überschreitet 50 MiB.","error");
  task("Datei wird analysiert …",async()=>{
    const form=new FormData();form.append("file",file);form.append("custom_sequences",sequences().join(","));
    selected.clear();scan=await api("/api/v1/scans/file",{method:"POST",body:form});
    shown=30;status("Dateianalyse abgeschlossen. Der Export wird nicht verändert.");
  });
});
$("results").addEventListener("change",e=>{const id=e.target.dataset.id;if(!id||busy)return;e.target.checked?selected.add(id):selected.delete(id);controls();});
$("selectAllBtn").addEventListener("click",()=>{groups().slice(0,shown).forEach(g=>g.delete_candidates.forEach(id=>selected.add(id)));render();});
$("selectNoneBtn").addEventListener("click",()=>{selected.clear();render();});
["filterInput","sortInput"].forEach(id=>$(id).addEventListener("input",()=>{shown=30;render();}));
$("moreBtn").addEventListener("click",()=>{shown+=30;render();});
async function remove(dryRun) {
  if(!scan||busy||!selected.size||scan.source!=="jellyfin")return;
  const ids=[...selected],scanId=scan.scan_id;
  if(!dryRun&&!window.confirm(ids.length+" ausgewählte Dateien endgültig über Jellyfin löschen? Die als BEHALTEN markierten Dateien bleiben erhalten."))return;
  task(dryRun?"Auswahl wird geprüft …":"Dateien werden gelöscht und das Ergebnis geprüft …",async()=>{
    const result=await api("/api/v1/scans/"+encodeURIComponent(scanId)+"/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dry_run:dryRun,item_ids:ids})});
    if(dryRun)return status("Prüfung abgeschlossen: "+result.requested_ids.length+" gültige Kandidaten. Keine Datei wurde gelöscht.");
    result.deleted_ids.forEach(id=>selected.delete(id));
    const failures=Object.entries(result.failed_ids);
    status(result.deleted_ids.length+" gelöscht, "+failures.length+" fehlgeschlagen."+(failures.length?" "+failures[0][1]:""),failures.length?"error":"");
    try {
      scan=await api("/api/v1/scans/"+encodeURIComponent(scanId));
      const remaining=new Set(scan.groups.flatMap(g=>g.delete_candidates));
      selected=new Set([...selected].filter(id=>remaining.has(id)));
    } catch {status("Löschantwort erhalten; Ergebnisse konnten nicht aktualisiert werden. Starte einen neuen Scan.","error");}
  });
}
$("dryRunBtn").addEventListener("click",()=>remove(true));
$("deleteBtn").addEventListener("click",()=>remove(false));
$("exportBtn").addEventListener("click",()=>{
  if(!scan)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(scan,null,2)],{type:"application/json"}));
  const a=document.createElement("a");a.href=url;a.download="jellyfin-duplicates-"+scan.scan_id+".json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
api("/health").then(body=>{$("version").textContent="v"+body.version;}).catch(()=>{});
render();
