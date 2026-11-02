// Service worker: funciona sin conexión con la última versión vista y busca datos nuevos cuando hay red.
const CACHE='tablero-cedear-v2';
const CORE=['./','./index.html','./data/ced.js','./data/ar.js','./vendor/chart.umd.min.js','./manifest.webmanifest','./icons/icon-192.png','./icons/icon-512.png'];
self.addEventListener('install',e=>{ e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).catch(()=>{})); self.skipWaiting(); });
self.addEventListener('activate',e=>{ e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch',e=>{
  const r=e.request; if (r.method!=='GET') return; const u=new URL(r.url);
  if (u.origin===location.origin){
    e.respondWith(fetch(r).then(res=>{ if (res.ok){ const cp=res.clone(); caches.open(CACHE).then(c=>c.put(r,cp)); } return res; })
      .catch(()=>caches.match(r,{ignoreSearch:true}).then(m=>m||caches.match('./index.html'))));
  } else if (/cdnjs\.cloudflare\.com|fonts\.(googleapis|gstatic)\.com/.test(u.hostname)){
    e.respondWith(caches.match(r).then(m=>m||fetch(r).then(res=>{ const cp=res.clone(); caches.open(CACHE).then(c=>c.put(r,cp)); return res; })));
  }
});
