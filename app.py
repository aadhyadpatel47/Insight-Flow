"""
Insight Flow — by Aadhya
Run:  python app.py
Open: http://localhost:5000
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import io, traceback, uvicorn, asyncio
from concurrent.futures import ThreadPoolExecutor
from engine import InsightFlowEngine

app = FastAPI(title="Insight Flow", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Thread pool for blocking analysis runs ────────────────────────────────────
_executor = ThreadPoolExecutor(max_workers=4)

HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Insight Flow — by Aadhya</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
/* ── TOKENS ─────────────────────────────────────────────────── */
:root{
  --bg:#080812;--surface:#0f0f1e;--surface2:#141428;--border:#1c1c32;--border2:#252540;
  --accent:#7c6fff;--accenth:#9585ff;--green:#3de8b0;--red:#ff5f7e;--yellow:#ffc947;
  --purple:#b06fff;--blue:#38c6f8;--orange:#ff8c42;--teal:#00d4aa;
  --text:#eeeef8;--text2:#b0b0cc;--muted:#6a6a8a;--card:#0f0f1e;
  --r:12px;--sh:0 8px 32px rgba(0,0,0,.5);
  --font-head:'Syne',sans-serif;--font-body:'Inter',sans-serif;
}
[data-theme=light]{
  --bg:#f0f0f8;--surface:#fff;--surface2:#f5f5fc;--border:#deddf0;--border2:#cccce0;
  --card:#fff;--text:#14142a;--text2:#3a3a5a;--muted:#8888a8;--sh:0 8px 32px rgba(0,0,0,.08);
}

/* ── RESET ──────────────────────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--font-body);font-size:14px;line-height:1.6;min-height:100vh;transition:background .3s,color .3s}
a{color:var(--accent);text-decoration:none}
button,input,select{font-family:inherit;cursor:pointer}

/* ── NOISE TEXTURE ──────────────────────────────────────────── */
body::before{content:'';position:fixed;inset:0;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");pointer-events:none;z-index:0;opacity:.4}

/* ── PAGE VIEWS ─────────────────────────────────────────────── */
#page-landing{display:flex;flex-direction:column;min-height:100vh;position:relative;z-index:1}
#page-app{display:none;flex-direction:column;min-height:100vh;position:relative;z-index:1}
#page-app.active{display:flex}

/* ── NAV ─────────────────────────────────────────────────────── */
.nav{position:sticky;top:0;z-index:200;background:rgba(8,8,18,.85);border-bottom:1px solid var(--border);backdrop-filter:blur(20px);display:flex;align-items:center;justify-content:space-between;padding:0 1.75rem;height:58px}
[data-theme=light] .nav{background:rgba(255,255,255,.88)}
.nav-logo{display:flex;align-items:center;gap:.5rem;font-family:var(--font-head);font-size:1.2rem;font-weight:800;color:var(--text);letter-spacing:-.3px}
.logo-orb{width:28px;height:28px;border-radius:50%;background:conic-gradient(var(--accent),var(--green),var(--purple),var(--accent));animation:spin 6s linear infinite;flex-shrink:0}
@keyframes spin{to{transform:rotate(360deg)}}
.nav-by{font-size:.68rem;color:var(--muted);font-weight:500;margin-left:.15rem}
.nav-right{display:flex;align-items:center;gap:.75rem}
.theme-btn{width:34px;height:34px;border-radius:9px;border:1px solid var(--border);background:var(--surface2);color:var(--text2);font-size:1rem;display:flex;align-items:center;justify-content:center;transition:all .2s}
.theme-btn:hover{border-color:var(--accent);color:var(--accent)}
.nav-back{font-size:.8rem;color:var(--muted);border:1px solid var(--border);background:transparent;padding:.3rem .85rem;border-radius:7px;transition:all .2s;display:none}
.nav-back:hover{border-color:var(--accent);color:var(--accent)}
.nav-back.show{display:flex;align-items:center;gap:.35rem}

/* ── LANDING ─────────────────────────────────────────────────── */
.landing-hero{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:5rem 2rem 3rem;text-align:center;position:relative}
.hero-glow{position:absolute;top:10%;left:50%;transform:translateX(-50%);width:600px;height:400px;background:radial-gradient(ellipse at center,rgba(124,111,255,.12) 0%,transparent 70%);pointer-events:none}
.hero-tag{display:inline-flex;align-items:center;gap:.5rem;background:rgba(124,111,255,.1);border:1px solid rgba(124,111,255,.25);color:var(--accent);font-size:.75rem;font-weight:600;padding:.35rem .85rem;border-radius:100px;margin-bottom:1.75rem;letter-spacing:.5px}
.hero-tag-dot{width:6px;height:6px;border-radius:50%;background:var(--green);animation:pdot 2s infinite}
@keyframes pdot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.5)}}
.hero-h1{font-family:var(--font-head);font-size:clamp(2.5rem,6vw,4.5rem);font-weight:800;line-height:1.05;letter-spacing:-2px;margin-bottom:1.25rem;color:var(--text)}
.hero-h1 .grad{background:linear-gradient(135deg,var(--accent),var(--green));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero-sub{font-size:1.1rem;color:var(--text2);max-width:560px;line-height:1.75;margin-bottom:2.5rem}

/* UPLOAD ZONE — landing */
.landing-upload{width:100%;max-width:600px;margin:0 auto}
.upload-zone{border:2px dashed var(--border2);border-radius:16px;padding:2.5rem 2rem;text-align:center;cursor:pointer;transition:all .3s;background:var(--surface);position:relative;overflow:hidden}
.upload-zone::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(124,111,255,.06),transparent 70%);pointer-events:none}
.upload-zone:hover,.upload-zone.drag{border-color:var(--accent);background:rgba(124,111,255,.04);transform:translateY(-2px);box-shadow:var(--sh)}
.upload-zone.loaded{border-color:var(--green);border-style:solid}
.uicon{font-size:2.5rem;margin-bottom:.6rem}
.utext{font-size:.9rem;color:var(--muted);line-height:1.6}
.utext strong{color:var(--text)}
.uinfo{font-size:.78rem;color:var(--green);margin-top:.6rem;font-family:monospace;display:none;background:rgba(61,232,176,.06);border:1px solid rgba(61,232,176,.2);border-radius:6px;padding:.35rem .7rem;display:inline-block}
.uinfo.vis{display:inline-block}
#file-input{display:none}

/* DEMO PILLS */
.demo-row{display:flex;flex-wrap:wrap;gap:.45rem;justify-content:center;margin-top:1.25rem}
.dp{font-size:.76rem;padding:.3rem .8rem;border-radius:100px;border:1px solid var(--border2);background:var(--surface2);color:var(--text2);cursor:pointer;transition:all .2s}
.dp:hover{border-color:var(--accent);color:var(--accent);background:rgba(124,111,255,.07)}

/* SETTINGS PANEL below upload */
.landing-settings{width:100%;max-width:600px;margin:1.5rem auto 0;background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:1.25rem 1.5rem}
.ls-grid{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}
.ls-grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:.75rem}
.field{display:flex;flex-direction:column;gap:.3rem}
.field label{font-size:.7rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.field select,.field input{background:var(--surface2);border:1px solid var(--border2);color:var(--text);padding:.5rem .75rem;border-radius:8px;font-size:.82rem;outline:none;transition:border-color .2s;width:100%;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%236a6a8a' d='M5 7L0 2h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right .75rem center;padding-right:2rem}
.field select:focus{border-color:var(--accent)}
.ahint{font-size:.72rem;color:var(--muted);padding:.4rem .6rem;background:var(--surface2);border-radius:6px;border-left:2px solid var(--accent);line-height:1.4;margin-top:.25rem;grid-column:1/-1}

/* RUN BTN */
.run-btn{width:100%;max-width:600px;margin:1rem auto 0;display:block;padding:.95rem;border-radius:10px;border:none;background:linear-gradient(135deg,var(--accent),var(--purple));color:#fff;font-family:var(--font-head);font-size:1rem;font-weight:700;display:flex;align-items:center;justify-content:center;gap:.5rem;transition:all .25s;letter-spacing:.2px}
.run-btn:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 8px 28px rgba(124,111,255,.4)}
.run-btn:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}

/* FEATURE PILLS */
.feat-section{padding:3rem 2rem;text-align:center}
.feat-title{font-family:var(--font-head);font-size:1rem;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:2px;margin-bottom:1.25rem}
.feat-grid{display:flex;flex-wrap:wrap;gap:.5rem;justify-content:center;max-width:800px;margin:0 auto}
.feat-pill{font-size:.75rem;padding:.35rem .85rem;border-radius:100px;background:var(--surface);border:1px solid var(--border);color:var(--text2);cursor:default;transition:all .2s;position:relative}
.feat-pill:hover{border-color:var(--accent);color:var(--accent)}
.feat-pill .tooltip{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:var(--surface2);border:1px solid var(--border2);color:var(--text);font-size:.72rem;padding:.5rem .75rem;border-radius:8px;white-space:nowrap;z-index:99;box-shadow:var(--sh);max-width:240px;white-space:normal;text-align:left;line-height:1.5}
.feat-pill:hover .tooltip{display:block}

/* ── APP LAYOUT ──────────────────────────────────────────────── */
.app-shell{display:grid;grid-template-columns:288px 1fr;flex:1;overflow:hidden}

/* SIDEBAR */
.sidebar{background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto;position:sticky;top:58px;height:calc(100vh - 58px)}
.sb-sec{padding:1.1rem 1.1rem 0}
.sb-sec:last-child{padding-bottom:1.1rem}
.sb-div{height:1px;background:var(--border);margin:.6rem 0 0}
.slabel{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted);margin-bottom:.6rem;display:block}

/* SIDEBAR upload zone */
.sb-upload-zone{border:2px dashed var(--border2);border-radius:10px;padding:1.25rem .85rem;text-align:center;cursor:pointer;transition:all .25s;background:var(--card);font-size:.78rem}
.sb-upload-zone:hover,.sb-upload-zone.drag{border-color:var(--accent);background:rgba(124,111,255,.04)}
.sb-upload-zone.loaded{border-color:var(--green);border-style:solid}
.sb-uicon{font-size:1.5rem;margin-bottom:.3rem}
.sb-utext{color:var(--muted)}
.sb-utext strong{color:var(--text)}
.sb-uinfo{font-size:.7rem;color:var(--green);margin-top:.35rem;font-family:monospace;display:none}
.sb-uinfo.vis{display:block}

/* SIDEBAR DEMO PILLS */
.sb-demo-pills{display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.5rem}
.sdp{font-size:.68rem;padding:.2rem .55rem;border-radius:100px;border:1px solid var(--border2);background:var(--card);color:var(--muted);cursor:pointer;transition:all .2s}
.sdp:hover{border-color:var(--accent);color:var(--accent)}

/* SIDEBAR FIELD */
.sb-field{display:flex;flex-direction:column;gap:.3rem;margin-bottom:.65rem}
.sb-field:last-child{margin-bottom:0}
.sb-field label{font-size:.68rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.sb-field select{background:var(--card);border:1px solid var(--border2);color:var(--text);padding:.45rem .65rem;border-radius:8px;font-size:.8rem;outline:none;transition:border-color .2s;width:100%;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%236a6a8a' d='M5 7L0 2h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right .65rem center;padding-right:1.75rem}
.sb-field select:focus{border-color:var(--accent)}
.sb-hint{font-size:.68rem;color:var(--muted);padding:.35rem .5rem;background:var(--surface2);border-radius:5px;border-left:2px solid var(--accent);line-height:1.4;grid-column:1/-1}
.sb-run-btn{width:100%;padding:.75rem;border-radius:9px;border:none;background:linear-gradient(135deg,var(--accent),var(--purple));color:#fff;font-size:.9rem;font-weight:700;display:flex;align-items:center;justify-content:center;gap:.5rem;transition:all .2s;margin-top:.15rem}
.sb-run-btn:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 6px 20px rgba(124,111,255,.35)}
.sb-run-btn:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}
.sb-run-hint{font-size:.66rem;color:var(--muted);text-align:center;margin-top:.35rem}

/* DOMAIN BADGE */
.domain-badge{display:inline-flex;align-items:center;gap:.35rem;font-size:.68rem;font-weight:700;padding:.25rem .65rem;border-radius:100px;background:rgba(61,232,176,.1);color:var(--green);border:1px solid rgba(61,232,176,.2);margin-top:.35rem}

/* MAIN AREA */
.main{padding:1.5rem;overflow-x:hidden;flex:1}

/* LOADING */
.loading-state{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:70vh;gap:1.5rem}
.spinner-ring{width:52px;height:52px;border:3px solid var(--border2);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite}
.ltitle{font-family:var(--font-head);font-size:1.15rem;font-weight:700}
.lsteps{display:flex;flex-direction:column;gap:.4rem;width:300px}
.lstep{font-size:.78rem;color:var(--muted);display:flex;align-items:center;gap:.5rem;padding:.4rem .6rem;border-radius:7px;transition:all .3s}
.lstep.active{color:var(--accent);background:rgba(124,111,255,.08)}
.lstep.done{color:var(--green)}
.sdot{width:6px;height:6px;border-radius:50%;background:currentColor;flex-shrink:0}

/* DASHBOARD */
.dashboard{display:none}
.dashboard.show{display:block}

/* DASH HEADER */
.dash-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:1.25rem;flex-wrap:wrap;gap:.75rem}
.dash-title{font-family:var(--font-head);font-size:1.35rem;font-weight:800;letter-spacing:-.3px}
.dash-sub{font-size:.78rem;color:var(--muted);margin-top:.25rem}
.dash-actions{display:flex;gap:.5rem;flex-wrap:wrap}
.btn{padding:.45rem 1rem;border-radius:8px;border:none;font-size:.8rem;font-weight:600;display:inline-flex;align-items:center;gap:.4rem;transition:all .2s;cursor:pointer}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:var(--accenth)}
.btn-ghost{background:transparent;color:var(--text2);border:1px solid var(--border2)}
.btn-ghost:hover{border-color:var(--accent);color:var(--accent)}

/* AI SUMMARY BANNER */
.ai-summary{background:rgba(124,111,255,.06);border:1px solid rgba(124,111,255,.18);border-radius:10px;padding:1rem 1.25rem;margin-bottom:1.25rem;font-size:.84rem;line-height:1.75;color:var(--text2)}
.ai-summary strong{color:var(--text)}
.ai-label{font-size:.67rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--accent);margin-bottom:.35rem;display:block}

/* TABS */
.tabs{display:flex;border-bottom:1px solid var(--border);margin-bottom:1.25rem;gap:0;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{padding:.55rem 1rem;font-size:.8rem;font-weight:600;color:var(--muted);border-bottom:2px solid transparent;cursor:pointer;white-space:nowrap;transition:all .2s}
.tab:hover{color:var(--text2)}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-panel{display:none}
.tab-panel.active{display:block}

/* KPI CARDS */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:.65rem;margin-bottom:1.25rem}
.kpi-card{background:var(--card);border:1px solid var(--border);border-radius:11px;padding:.9rem;position:relative;overflow:hidden;transition:transform .2s,border-color .2s}
.kpi-card:hover{transform:translateY(-2px);border-color:var(--border2)}
.kpi-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--accent)}
.kpi-card.green::before{background:var(--green)}
.kpi-card.red::before{background:var(--red)}
.kpi-card.yellow::before{background:var(--yellow)}
.kpi-card.purple::before{background:var(--purple)}
.knum{font-family:var(--font-body);font-size:1.65rem;font-weight:700;line-height:1;letter-spacing:-0.02em}
.klbl{font-size:0.72rem;font-weight:600;text-transform:uppercase;color:var(--muted);margin-top:0.4rem;letter-spacing:0.05em}
.kbadge{font-size:.63rem;font-weight:700;padding:.1rem .4rem;border-radius:4px;margin-top:.3rem;display:inline-block}
.kbadge.up{background:rgba(61,232,176,.12);color:var(--green)}
.kbadge.dn{background:rgba(255,95,126,.12);color:var(--red)}

/* CHARTS */
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:11px;overflow:hidden;margin-bottom:1rem}
.chart-head{padding:.8rem 1rem;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.chart-title{font-size:.8rem;font-weight:700}
.chart-body img{width:100%;height:auto;display:block}
.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:1rem}

/* STAT ROW */
.stat-row{display:flex;gap:.45rem;flex-wrap:wrap;margin-bottom:.85rem}
.stat-pill{background:var(--surface2);border:1px solid var(--border);border-radius:7px;padding:.35rem .7rem;font-size:.74rem}
.stat-pill span{color:var(--text);font-weight:700}

/* TABLE */
.table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:.76rem}
thead tr{background:var(--surface2)}
th{padding:.5rem .8rem;text-align:left;color:var(--muted);font-weight:700;font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap;border-bottom:1px solid var(--border)}
td{padding:.45rem .8rem;border-bottom:1px solid var(--border);color:var(--text2);white-space:nowrap}
tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--surface2)}

/* QUALITY */
.q-list{display:flex;flex-direction:column;gap:.45rem}
.q-item{display:grid;grid-template-columns:155px 1fr 55px 55px;gap:.7rem;align-items:center;font-size:.74rem}
.q-name{color:var(--text);font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fill-bar{height:5px;background:var(--border2);border-radius:3px;overflow:hidden}
.fill-inner{height:100%;border-radius:3px;background:var(--green);transition:width .6s ease}
.fill-inner.warn{background:var(--yellow)}
.fill-inner.bad{background:var(--red)}
.q-pct{text-align:right;color:var(--text2)}
.q-type{text-align:right;font-size:.63rem;color:var(--muted);font-family:monospace;padding:.1rem .3rem;background:var(--surface2);border-radius:4px}

/* ALERTS */
.alert-list{display:flex;flex-direction:column;gap:.45rem}
.alert-item{background:var(--card);border:1px solid var(--border);border-radius:9px;padding:.8rem .95rem;display:flex;gap:.8rem;align-items:flex-start}
.alert-item.critical{border-left:3px solid var(--red)}
.alert-item.warning{border-left:3px solid var(--yellow)}
.aicon{font-size:1rem;flex-shrink:0;margin-top:1px}
.abody{flex:1}
.atype{font-size:.63rem;color:var(--muted);font-family:monospace;margin-bottom:.2rem}
.adesc{font-size:.78rem;color:var(--text2);line-height:1.5}
.acol{font-size:.67rem;color:var(--accent);margin-top:.2rem;font-family:monospace}
.no-alerts{display:flex;align-items:center;gap:.75rem;padding:1.25rem;background:rgba(61,232,176,.05);border:1px solid rgba(61,232,176,.18);border-radius:9px;color:var(--green);font-size:.875rem;font-weight:600}

/* RFM */
.rfm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:.65rem}
.rfm-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:.9rem;text-align:center}
.badge{display:inline-block;padding:.15rem .45rem;border-radius:4px;font-size:.63rem;font-weight:700}
.bc{background:rgba(124,111,255,.15);color:var(--accent)}
.bl{background:rgba(61,232,176,.15);color:var(--green)}
.br{background:rgba(255,201,71,.15);color:var(--yellow)}
.blost{background:rgba(255,95,126,.15);color:var(--red)}
.bn{background:rgba(176,111,255,.15);color:var(--purple)}

/* ERROR */
.err-box{background:rgba(255,95,126,.07);border:1px solid rgba(255,95,126,.25);border-radius:9px;padding:1.25rem;display:flex;gap:.75rem;align-items:flex-start}
.err-box h3{color:var(--red);font-size:.88rem;margin-bottom:.3rem}
.err-box p{font-size:.78rem;color:var(--muted);font-family:monospace}

/* SCROLLBAR */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:10px}

/* RESPONSIVE */
@media(max-width:860px){.app-shell{grid-template-columns:1fr}.sidebar{position:static;height:auto}.chart-grid{grid-template-columns:1fr}.q-item{grid-template-columns:110px 1fr 45px}.q-type{display:none}.ls-grid,.ls-grid-3{grid-template-columns:1fr}}

/* ANIMATIONS */
@keyframes fadeup{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
.fadeup{animation:fadeup .4s ease both}
@keyframes fadein{from{opacity:0}to{opacity:1}}
.fadein{animation:fadein .5s ease both}
</style>
</head>
<body>

<!-- ═══════════════ PAGE: LANDING ═══════════════ -->
<div id="page-landing">

  <!-- Nav -->
  <nav class="nav">
    <div class="nav-logo">
      <div class="logo-orb"></div>
      Insight&nbsp;Flow
      <span class="nav-by">by Aadhya</span>
    </div>
    <div class="nav-right">
      <button class="theme-btn" id="theme-btn">🌙</button>
    </div>
  </nav>

  <!-- Hero -->
  <div class="landing-hero">
    <div class="hero-glow"></div>
    <div class="hero-tag"><span class="hero-tag-dot"></span>AI-Powered Business Intelligence</div>
    <h1 class="hero-h1">Turn raw data into<br/><span class="grad">clear decisions.</span></h1>
    <p class="hero-sub">Upload any CSV or Excel file. Insight Flow detects your domain, cleans your data, and delivers narrative-style analysis — not just charts.</p>

    <!-- Upload zone -->
    <div class="landing-upload">
      <div class="upload-zone" id="landing-upload-zone">
        <input type="file" id="landing-file-input" accept=".csv,.xlsx,.xls,.json"/>
        <div class="uicon">📂</div>
        <div class="utext"><strong>Click to upload</strong> or drag & drop</div>
        <div class="utext" style="margin-top:.25rem;font-size:.78rem">CSV · Excel · JSON · up to 1M+ rows</div>
        <div class="uinfo" id="landing-uinfo"></div>
      </div>

      <!-- Demo pills -->
      <div class="demo-row">
        <span class="dp" onclick="loadDemo('sales')">📊 Sales</span>
        <span class="dp" onclick="loadDemo('cohort')">👥 Cohort</span>
        <span class="dp" onclick="loadDemo('rfm')">🎯 RFM</span>
        <span class="dp" onclick="loadDemo('funnel')">🔽 Funnel</span>
        <span class="dp" onclick="loadDemo('ops')">⚙️ Ops</span>
      </div>
    </div>

    <!-- Settings -->
    <div class="landing-settings" id="landing-settings" style="display:none">
      <div class="ls-grid" style="margin-bottom:.65rem">
        <div class="field">
          <label>Analysis Type</label>
          <select id="l-analysis-type" onchange="onLTypeChange()">
            <option value="kpi">📈 KPI Trend Analysis</option>
            <option value="trend">📉 Trend Analysis</option>
            <option value="rfm">🎯 RFM Segmentation</option>
            <option value="cohort">👥 Cohort Analysis</option>
            <option value="funnel">🔽 Funnel Analysis</option>
            <option value="ops">⚙️ Ops Monitoring</option>
            <option value="seasonal">🌦 Seasonal Patterns</option>
            <option value="pareto">📌 Pareto (80/20)</option>
            <option value="price">💲 Price Sensitivity</option>
            <option value="growth">🌱 Growth Accounting</option>
            <option value="contribution">🥧 Contribution Margin</option>
            <option value="velocity">⚡ Velocity Tracking</option>
            <option value="period">📅 Period Comparison</option>
          </select>
        </div>
        <div class="field">
          <label>Date Column</label>
          <select id="l-date-col"><option value="">Auto-detect</option></select>
        </div>
      </div>
      <div class="ls-grid-3" style="margin-bottom:.65rem">
        <div class="field">
          <label>Metric Column</label>
          <select id="l-metric-col"><option value="">Auto-detect</option></select>
        </div>
        <div class="field" id="l-cust-field">
          <label>Customer Column</label>
          <select id="l-customer-col"><option value="">Auto-detect</option></select>
        </div>
        <div></div>
      </div>
      <div class="ahint" id="l-ahint">Track revenue over time. Outputs MoM, QoQ, YoY growth with trend charts.</div>
    </div>

    <!-- Run Button -->
    <button class="run-btn" id="landing-run-btn" onclick="landingRun()" disabled style="margin-top:1.25rem">
      ▶ Run Analysis
    </button>
  </div>

  <!-- Features -->
  <div class="feat-section">
    <div class="feat-title">What's inside</div>
    <div class="feat-grid">
      <span class="feat-pill">📈 KPI Trends<span class="tooltip">Monthly, QoQ, and YoY growth charts with MoM change analysis.</span></span>
      <span class="feat-pill">📉 Trend Analysis<span class="tooltip">Linear trend detection with R² strength, 3-month and 6-month moving averages.</span></span>
      <span class="feat-pill">🎯 RFM Segments<span class="tooltip">Score customers on Recency, Frequency, Monetary. Champions/Loyal/At-Risk/Lost auto-segmentation.</span></span>
      <span class="feat-pill">👥 Cohort Analysis<span class="tooltip">Group customers by signup month. Track Average Order Value per cohort.</span></span>
      <span class="feat-pill">🔽 Funnel Analysis<span class="tooltip">Auto-detects stage columns. Shows conversion rates and drop-off at every step.</span></span>
      <span class="feat-pill">📌 Pareto 80/20<span class="tooltip">Which 20% of products/customers/regions drive 80% of revenue? Visual Pareto curve.</span></span>
      <span class="feat-pill">💲 Price Sensitivity<span class="tooltip">Price-volume relationship with Pearson correlation and binned analysis.</span></span>
      <span class="feat-pill">🌱 Growth Accounting<span class="tooltip">Splits revenue growth into New vs Retained vs Churned by month.</span></span>
      <span class="feat-pill">🥧 Contribution Margin<span class="tooltip">Which segment contributes most to total value? Donut + bar breakdown.</span></span>
      <span class="feat-pill">⚡ Velocity Tracking<span class="tooltip">Rate of change (velocity) and rate of rate-of-change (acceleration) over time.</span></span>
      <span class="feat-pill">📅 Period Comparison<span class="tooltip">Current 4 quarters vs previous 4 quarters side-by-side grouped bar chart.</span></span>
      <span class="feat-pill">🌦 Seasonal Patterns<span class="tooltip">Month, quarter, year, and day-of-week breakdown with 4 sub-charts.</span></span>
      <span class="feat-pill">⚙️ Ops Monitoring<span class="tooltip">7-day and 30-day moving averages with Bollinger bands (±2σ).</span></span>
      <span class="feat-pill">🚨 Anomaly Alerts<span class="tooltip">Z-score anomalies, period drops >20%, and high null-rate detection.</span></span>
      <span class="feat-pill">🧹 Data Quality<span class="tooltip">10-rule cleaning engine: dupes, nulls, currency, outlier flags, date parsing.</span></span>
      <span class="feat-pill">🏷 Domain Detection<span class="tooltip">Auto-identifies Sales, Marketing, Finance, HR, Ops, or E-commerce domain.</span></span>
      <span class="feat-pill">💬 AI Narratives<span class="tooltip">Plain-English summaries explain what the numbers mean, not just what they are.</span></span>
      <span class="feat-pill">📄 HTML Report<span class="tooltip">Download a standalone offline report with all charts and AI summaries.</span></span>
    </div>
  </div>

</div>
<!-- END LANDING -->


<!-- ═══════════════ PAGE: APP ═══════════════ -->
<div id="page-app">

  <!-- Nav -->
  <nav class="nav">
    <div class="nav-logo">
      <div class="logo-orb"></div>
      Insight&nbsp;Flow
      <span class="nav-by">by Aadhya</span>
    </div>
    <div class="nav-right">
      <button class="nav-back show" id="nav-back-btn" onclick="goLanding()">← Back</button>
      <button class="theme-btn" id="theme-btn2">🌙</button>
    </div>
  </nav>

  <div class="app-shell">

    <!-- SIDEBAR -->
    <aside class="sidebar">
      <div class="sb-sec">
        <span class="slabel">Data Source</span>
        <div class="sb-upload-zone" id="sb-upload-zone">
          <input type="file" id="sb-file-input" accept=".csv,.xlsx,.xls,.json"/>
          <div class="sb-uicon">📂</div>
          <div class="sb-utext"><strong>Click</strong> or drag & drop</div>
          <div class="sb-utext" style="font-size:.68rem;color:var(--muted);margin-top:.15rem">CSV · Excel · JSON</div>
          <div class="sb-uinfo" id="sb-uinfo"></div>
        </div>
        <div style="margin-top:.65rem">
          <span class="slabel">Demo Datasets</span>
          <div class="sb-demo-pills">
            <span class="sdp" onclick="loadDemo('sales')">📊 Sales</span>
            <span class="sdp" onclick="loadDemo('cohort')">👥 Cohort</span>
            <span class="sdp" onclick="loadDemo('rfm')">🎯 RFM</span>
            <span class="sdp" onclick="loadDemo('funnel')">🔽 Funnel</span>
            <span class="sdp" onclick="loadDemo('ops')">⚙️ Ops</span>
          </div>
        </div>
      </div>
      <div class="sb-div"></div>
      <div class="sb-sec">
        <span class="slabel">Analysis Settings</span>
        <div class="sb-field">
          <label>Analysis Type</label>
          <select id="sb-analysis-type" onchange="onSBTypeChange()">
            <option value="kpi">📈 KPI Trend Analysis</option>
            <option value="trend">📉 Trend Analysis</option>
            <option value="rfm">🎯 RFM Segmentation</option>
            <option value="cohort">👥 Cohort Analysis</option>
            <option value="funnel">🔽 Funnel Analysis</option>
            <option value="ops">⚙️ Ops Monitoring</option>
            <option value="seasonal">🌦 Seasonal Patterns</option>
            <option value="pareto">📌 Pareto (80/20)</option>
            <option value="price">💲 Price Sensitivity</option>
            <option value="growth">🌱 Growth Accounting</option>
            <option value="contribution">🥧 Contribution Margin</option>
            <option value="velocity">⚡ Velocity Tracking</option>
            <option value="period">📅 Period Comparison</option>
          </select>
        </div>
        <div class="sb-hint" id="sb-ahint">Track revenue over time. Outputs MoM, QoQ, YoY growth with trend charts.</div>
        <div class="sb-field" style="margin-top:.55rem">
          <label>Date Column</label>
          <select id="sb-date-col"><option value="">Auto-detect</option></select>
        </div>
        <div class="sb-field">
          <label>Metric Column</label>
          <select id="sb-metric-col"><option value="">Auto-detect</option></select>
        </div>
        <div class="sb-field" id="sb-cust-field" style="display:none">
          <label>Customer Column</label>
          <select id="sb-customer-col"><option value="">Auto-detect</option></select>
        </div>
      </div>
      <div class="sb-div"></div>
      <div class="sb-sec">
        <button class="sb-run-btn" id="sb-run-btn" onclick="runAnalysis()" disabled>▶ Run Analysis</button>
        <div class="sb-run-hint" id="sb-run-hint">Upload a file or load a demo first</div>
      </div>
    </aside>

    <!-- MAIN -->
    <main class="main" id="main-area">

      <!-- LOADING -->
      <div id="view-loading" class="loading-state" style="display:none">
        <div class="spinner-ring"></div>
        <div class="ltitle">Analyzing your data…</div>
        <div class="lsteps">
          <div class="lstep active" id="ls1"><span class="sdot"></span>Loading &amp; validating file</div>
          <div class="lstep" id="ls2"><span class="sdot"></span>Cleaning (10 rules applied)</div>
          <div class="lstep" id="ls3"><span class="sdot"></span>Detecting domain &amp; columns</div>
          <div class="lstep" id="ls4"><span class="sdot"></span>Running business analysis</div>
          <div class="lstep" id="ls5"><span class="sdot"></span>Generating charts &amp; narratives</div>
        </div>
      </div>

      <!-- DASHBOARD -->
      <div id="view-dashboard" class="dashboard">
        <div class="dash-header fadeup">
          <div>
            <div class="dash-title" id="dash-title">Analysis Complete</div>
            <div class="dash-sub" id="dash-sub"></div>
            <div class="domain-badge" id="domain-badge" style="display:none">🏷 Domain</div>
          </div>
          <div class="dash-actions">
            <button class="btn btn-ghost" onclick="exportCSV()">⬇ Clean CSV</button>
            <button class="btn btn-primary" onclick="downloadReport()">📄 Report</button>
          </div>
        </div>

        <!-- AI Summary Banner -->
        <div class="ai-summary fadeup" id="ai-summary" style="display:none">
          <span class="ai-label">✦ Insight</span>
          <span id="ai-summary-text"></span>
        </div>

        <div class="kpi-grid fadeup" id="summary-cards"></div>

        <div class="tabs fadeup" id="main-tabs">
          <div class="tab active" onclick="switchTab('kpi',this)">📈 KPI</div>
          <div class="tab" onclick="switchTab('analysis',this)" id="tab-analysis">📊 Analysis</div>
          <div class="tab" onclick="switchTab('alerts',this)">🚨 Alerts</div>
          <div class="tab" onclick="switchTab('quality',this)">🧹 Quality</div>
          <div class="tab" onclick="switchTab('preview',this)">👁 Preview</div>
        </div>

        <div class="tab-panel active" id="panel-kpi">
          <div class="stat-row" id="kpi-stats"></div>
          <div id="kpi-charts"></div>
        </div>
        <div class="tab-panel" id="panel-analysis"><div id="analysis-content"></div></div>
        <div class="tab-panel" id="panel-alerts"><div id="alerts-content"></div></div>
        <div class="tab-panel" id="panel-quality"><div id="quality-content"></div></div>
        <div class="tab-panel" id="panel-preview"><div id="preview-content"></div></div>
      </div>

    </main>
  </div>
</div>
<!-- END APP -->

<script>
// ── State ──────────────────────────────────────────────────────
let S = { file: null, data: null, ltimer: null };
const BASE = '';

const HINTS = {
  kpi:         'Track revenue over time. Outputs MoM, QoQ, YoY growth with trend charts.',
  trend:       'Linear trend detection with R² strength. 3-month and 6-month moving averages.',
  rfm:         'Score customers: Recency, Frequency, Monetary. Auto-segments into Champions/Loyal/At-Risk/Lost.',
  cohort:      'Group customers by signup month. Tracks Average Order Value per cohort.',
  funnel:      'Auto-detects stage column. Shows conversion rates and drop-off at each step.',
  ops:         '7-day and 30-day moving averages with Bollinger bands (±2σ).',
  seasonal:    'Breaks metric into month, quarter, year, and day-of-week patterns.',
  pareto:      'Which 20% of items drive 80% of value? Visual Pareto curve with 80% threshold.',
  price:       'Price-volume relationship with Pearson correlation and binned analysis.',
  growth:      'Splits growth into New vs Retained vs Churned revenue by month.',
  contribution:'Which segments contribute most to total value? Donut + bar breakdown.',
  velocity:    'Rate of change (velocity) and rate-of-rate-of-change (acceleration) per month.',
  period:      'Compare last 4 quarters vs previous 4 quarters side-by-side.',
};

// ── Theme ──────────────────────────────────────────────────────
function initTheme() {
  const th = localStorage.getItem('if_th') || 'dark';
  document.documentElement.setAttribute('data-theme', th);
  ['theme-btn','theme-btn2'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = th === 'dark' ? '🌙' : '☀️';
  });
}
function toggleTheme() {
  const c = document.documentElement.getAttribute('data-theme');
  const n = c === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', n);
  localStorage.setItem('if_th', n);
  ['theme-btn','theme-btn2'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = n === 'dark' ? '🌙' : '☀️';
  });
}
document.getElementById('theme-btn').onclick  = toggleTheme;
document.getElementById('theme-btn2').onclick = toggleTheme;
initTheme();

// ── Page navigation ────────────────────────────────────────────
function showPage(name) {
  document.getElementById('page-landing').style.display = name === 'landing' ? 'flex' : 'none';
  const appEl = document.getElementById('page-app');
  if (name === 'app') {
    appEl.style.display = 'flex';
    appEl.classList.add('active');
  } else {
    appEl.style.display = 'none';
    appEl.classList.remove('active');
  }
}
function goLanding() { showPage('landing'); }
showPage('landing');

// ── Landing Upload Zone ────────────────────────────────────────
const lZone = document.getElementById('landing-upload-zone');
const lFI   = document.getElementById('landing-file-input');
lZone.onclick = () => lFI.click();
lFI.onchange  = e => { if (e.target.files[0]) setFile(e.target.files[0], 'landing'); };
lZone.ondragover  = e => { e.preventDefault(); lZone.classList.add('drag'); };
lZone.ondragleave = () => lZone.classList.remove('drag');
lZone.ondrop      = e => { e.preventDefault(); lZone.classList.remove('drag'); if(e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0],'landing'); };

// ── Sidebar Upload Zone ────────────────────────────────────────
const sbZone = document.getElementById('sb-upload-zone');
const sbFI   = document.getElementById('sb-file-input');
sbZone.onclick = () => sbFI.click();
sbFI.onchange  = e => { if (e.target.files[0]) setFile(e.target.files[0], 'sidebar'); };
sbZone.ondragover  = e => { e.preventDefault(); sbZone.classList.add('drag'); };
sbZone.ondragleave = () => sbZone.classList.remove('drag');
sbZone.ondrop      = e => { e.preventDefault(); sbZone.classList.remove('drag'); if(e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0],'sidebar'); };

function setFile(f, src) {
  S.file = f;
  const sz = f.size > 1048576 ? (f.size/1048576).toFixed(1)+' MB' : (f.size/1024).toFixed(0)+' KB';
  const label = `✓ ${f.name} (${sz})`;

  // Landing zone
  const lui = document.getElementById('landing-uinfo');
  lui.textContent = label; lui.classList.add('vis');
  lZone.classList.add('loaded');
  document.getElementById('landing-settings').style.display = '';

  // Sidebar zone
  const sui = document.getElementById('sb-uinfo');
  sui.textContent = label; sui.classList.add('vis');
  sbZone.classList.add('loaded');

  enableRun();
  fetchCols(f);
}

async function fetchCols(f) {
  try {
    const fd = new FormData(); fd.append('file', f);
    const r  = await fetch(`${BASE}/columns`, {method:'POST', body:fd});
    if (!r.ok) return;
    const d = await r.json();
    ['l-date-col','sb-date-col'].forEach(id => fillSel(id, d.date, d.all));
    ['l-metric-col','sb-metric-col'].forEach(id => fillSel(id, d.numeric, d.all));
    ['l-customer-col','sb-customer-col'].forEach(id => fillSel(id, d.id, d.all));
  } catch(e) {}
}

function fillSel(id, priority, all) {
  const s = document.getElementById(id);
  if (!s) return;
  s.innerHTML = '<option value="">Auto-detect</option>';
  [...new Set([...(priority||[]),...(all||[])])].forEach(c => {
    const o = document.createElement('option'); o.value = c; o.textContent = c; s.appendChild(o);
  });
}

// ── Demo ───────────────────────────────────────────────────────
async function loadDemo(type) {
  const csv  = genCSV(type, 800);
  const blob = new Blob([csv], {type:'text/csv'});
  const f    = new File([blob], `demo_${type}.csv`, {type:'text/csv'});
  setFile(f, 'both');
  const m = {sales:'kpi',cohort:'cohort',rfm:'rfm',funnel:'funnel',ops:'ops'};
  if (m[type]) {
    ['l-analysis-type','sb-analysis-type'].forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.value = m[type]; }
    });
    onLTypeChange(); onSBTypeChange();
  }
}

function genCSV(type, rows) {
  let rng = mulberry32(42);
  const r  = () => rng();
  const ri = (a,b) => Math.floor(r()*(b-a)+a);
  const rc = a => a[Math.floor(r()*a.length)];
  const f2 = n => parseFloat(n.toFixed(2));
  const sd = new Date('2022-01-01');
  const ad = (d,n) => { const x=new Date(d); x.setDate(x.getDate()+n); return x; };
  const fd = d => d.toISOString().slice(0,10);
  let h, rf;
  if (type==='sales'||type==='kpi') {
    h  = ['order_id','order_date','customer_id','product','region','channel','quantity','unit_price','discount_pct','revenue'];
    const pr=['Widget A','Widget B','Service Pro','Service Lite','Addon X'],re=['North','South','East','West','Central'],ch=['Online','Direct','Partner','Retail'];
    rf = i => { const q=ri(1,20),p=f2(r()*200+10),d=rc([0,5,10,15,20]); return [`ORD-${10000+i}`,fd(ad(sd,ri(0,730))),ri(1000,5000),rc(pr),rc(re),rc(ch),q,p,d,f2(q*p*(1-d/100))]; };
  } else if (type==='rfm') {
    h  = ['customer_id','order_date','revenue','product_cat'];
    rf = () => [ri(1,200),fd(ad(sd,ri(0,730))),f2(r()*500+10),rc(['Electronics','Apparel','Food','Home','Beauty'])];
  } else if (type==='cohort') {
    h  = ['customer_id','signup_date','purchase_date','amount'];
    rf = () => { const s=ad(sd,ri(0,365)); return [ri(1,200),fd(s),fd(ad(s,ri(0,300))),f2(r()*500+20)]; };
  } else if (type==='funnel') {
    h  = ['lead_id','stage','source','days_in_stage','deal_value','created_date'];
    const st=['Visitor','Lead','MQL','SQL','Demo','Closed Won'];
    rf = i => { const si=Math.min(ri(0,6),5); return [`LEAD-${i+1}`,st[si],rc(['Organic','Paid','Referral','Email']),ri(1,90),si>=3?f2(r()*10000+500):'',fd(ad(sd,ri(0,365)))]; };
  } else {
    h  = ['date','orders','avg_handle_time','tickets_open','utilization_pct'];
    rf = i => { const v=Math.abs(1000+Math.sin(i*2*Math.PI/365)*200+(r()-.5)*100+i*.5); return [fd(ad(sd,i)),Math.round(v),f2(r()*20+5),ri(10,200),f2(r()*40+60)]; };
  }
  const lines = [h.join(',')];
  for (let i=0;i<rows;i++) { const row=rf(i); if(r()<.05) row[Math.floor(r()*row.length)]=''; lines.push(row.join(',')); }
  for (let i=0;i<Math.floor(rows*.03);i++) lines.push(lines[ri(1,lines.length)]);
  return lines.join('\n');
}

function mulberry32(a) {
  return () => { a|=0; a=a+0x6D2B79F5|0; let t=Math.imul(a^a>>>15,1|a); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296; };
}

// ── Type hint sync ─────────────────────────────────────────────
function onLTypeChange() {
  const t = document.getElementById('l-analysis-type').value;
  document.getElementById('l-ahint').textContent = HINTS[t] || '';
  const needs_cust = ['rfm','growth'].includes(t);
  document.getElementById('l-cust-field').style.display = needs_cust ? '' : 'none';
  syncTypes('l-analysis-type','sb-analysis-type');
  onSBTypeChange();
}
function onSBTypeChange() {
  const t = document.getElementById('sb-analysis-type').value;
  document.getElementById('sb-ahint').textContent = HINTS[t] || '';
  const needs_cust = ['rfm','growth'].includes(t);
  document.getElementById('sb-cust-field').style.display = needs_cust ? 'flex' : 'none';
  const lbl = {kpi:'📈 KPI',trend:'📉 Trend',rfm:'🎯 RFM',cohort:'👥 Cohort',funnel:'🔽 Funnel',ops:'⚙️ Ops',seasonal:'🌦 Seasonal',pareto:'📌 Pareto',price:'💲 Price',growth:'🌱 Growth',contribution:'🥧 Margin',velocity:'⚡ Velocity',period:'📅 Period'};
  document.getElementById('tab-analysis').textContent = lbl[t] || '📊 Analysis';
  syncTypes('sb-analysis-type','l-analysis-type');
}
function syncTypes(srcId, dstId) {
  const src = document.getElementById(srcId);
  const dst = document.getElementById(dstId);
  if (src && dst && src.value !== dst.value) dst.value = src.value;
}
onLTypeChange();

function enableRun() {
  ['landing-run-btn','sb-run-btn'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = false;
  });
  document.getElementById('sb-run-hint').textContent = 'Ready — click Run Analysis';
}

// ── Landing Run ────────────────────────────────────────────────
function landingRun() {
  if (!S.file) return;
  // Sync landing settings to sidebar
  const lType    = document.getElementById('l-analysis-type').value;
  const lDate    = document.getElementById('l-date-col').value;
  const lMetric  = document.getElementById('l-metric-col').value;
  const lCust    = document.getElementById('l-customer-col').value;
  document.getElementById('sb-analysis-type').value = lType;
  document.getElementById('sb-date-col').value       = lDate;
  document.getElementById('sb-metric-col').value     = lMetric;
  document.getElementById('sb-customer-col').value   = lCust;
  onSBTypeChange();
  showPage('app');
  runAnalysis();
}

// ── Run Analysis ───────────────────────────────────────────────
async function runAnalysis() {
  if (!S.file) return;
  showLoading(); animateSteps();
  const fd = new FormData();
  fd.append('file',         S.file);
  fd.append('analysis_type', document.getElementById('sb-analysis-type').value);
  fd.append('date_col',      document.getElementById('sb-date-col').value);
  fd.append('metric_col',    document.getElementById('sb-metric-col').value);
  fd.append('customer_col',  document.getElementById('sb-customer-col').value);
  try {
    const res = await fetch(`${BASE}/upload`, {method:'POST', body:fd});
    if (!res.ok) { const e=await res.json(); throw new Error(e.detail||'Analysis failed'); }
    S.data = await res.json();
    clearInterval(S.ltimer);
    renderDash(S.data);
  } catch(e) {
    clearInterval(S.ltimer);
    showDash();
    document.getElementById('view-dashboard').innerHTML =
      `<div class="err-box" style="max-width:480px"><div>⚠</div><div><h3>Error</h3><p>${e.message}</p></div></div>`;
  }
}

function showLoading() {
  document.getElementById('view-loading').style.display   = '';
  document.getElementById('view-dashboard').style.display = 'none';
  document.getElementById('view-dashboard').classList.remove('show');
}
function showDash() {
  document.getElementById('view-loading').style.display = 'none';
  document.getElementById('view-dashboard').style.display = '';
  document.getElementById('view-dashboard').classList.add('show');
}

function animateSteps() {
  let step = 1;
  [1,2,3,4,5].forEach(i => {
    const el = document.getElementById(`ls${i}`);
    if (el) el.classList.remove('active','done');
  });
  const first = document.getElementById('ls1');
  if (first) first.classList.add('active');
  S.ltimer = setInterval(() => {
    if (step < 5) {
      const cur = document.getElementById(`ls${step}`);
      const nxt = document.getElementById(`ls${step+1}`);
      if (cur) cur.classList.replace('active','done');
      if (nxt) nxt.classList.add('active');
      step++;
    }
  }, 800);
}

// ── Render Dashboard ───────────────────────────────────────────
function renderDash(d) {
  const sc   = d.quality_scorecard || {};
  const kpi  = d.kpi  || {};
  const anom = d.anomalies || {};
  const det  = d.detected  || {};
  const sums = d.ai_summaries || {};

  document.getElementById('dash-title').textContent = d.filename || 'Analysis Complete';
  document.getElementById('dash-sub').textContent   =
    `${(det.total_rows||0).toLocaleString()} rows · ${det.total_cols||0} cols · ${(d.analysis_type||'').toUpperCase()} · Quality: ${sc.quality_score||0}/100`;

  // Domain badge
  if (d.domain && d.domain !== 'General') {
    const db = document.getElementById('domain-badge');
    db.style.display = 'inline-flex';
    db.textContent   = `🏷 ${d.domain}`;
  }

  // AI Summary banner
  if (sums.overview) {
    const ab = document.getElementById('ai-summary');
    const at = document.getElementById('ai-summary-text');
    ab.style.display = '';
    at.textContent   = sums.overview;
  }

  renderCards(sc, kpi, anom, det);
  renderKPI(kpi, sums);
  renderAnalysis(d, sums);
  renderAlerts(anom, sums);
  renderQuality(d.col_stats||[], sc);
  renderPreview(d.preview||{});
  showDash();
}

function renderCards(sc, kpi, anom, det) {
  const score = sc.quality_score || 0;
  const sc_   = score>=80?'green':score>=60?'yellow':'red';
  const s     = kpi.summary || {};
  const mom   = s.avg_mom_pct || 0;
  const mc    = mom>=0?'green':'red';
  const ms    = mom>=0?'+':'';
  const crit  = anom.critical || 0;
  const metLabel = (det.metric_col||'Metric').replace(/_/g,' ');
  document.getElementById('summary-cards').innerHTML = `
    <div class="kpi-card ${sc_}"><div class="knum">${score}</div><div class="klbl">Quality Score</div></div>
    <div class="kpi-card"><div class="knum">${(sc.rows_after||0).toLocaleString()}</div><div class="klbl">Clean Rows</div>${sc.dupes_removed?`<div class="kbadge up">-${sc.dupes_removed} dupes</div>`:''}</div>
    <div class="kpi-card green"><div class="knum">${fmt(s.total||0)}</div><div class="klbl">Total ${metLabel}</div></div>
    <div class="kpi-card ${mc}"><div class="knum">${ms}${(mom||0).toFixed(1)}%</div><div class="klbl">Avg MoM Growth</div></div>
    <div class="kpi-card ${crit>0?'red':'green'}"><div class="knum">${anom.total||0}</div><div class="klbl">Alerts</div><div class="kbadge ${crit>0?'dn':'up'}">${crit>0?crit+' critical':'All clear'}</div></div>
    <div class="kpi-card purple"><div class="knum">${s.months||0}</div><div class="klbl">Months of Data</div></div>
  `;
}

function renderKPI(kpi, sums) {
  const sr = document.getElementById('kpi-stats');
  const cc = document.getElementById('kpi-charts');
  if (kpi.error) { cc.innerHTML=errBox(kpi.error); sr.innerHTML=''; return; }
  const s = kpi.summary || {};
  sr.innerHTML = `
    <div class="stat-pill">Total: <span>${fmt(s.total||0)}</span></div>
    <div class="stat-pill">Avg Monthly: <span>${fmt(s.avg_monthly||0)}</span></div>
    <div class="stat-pill">Best Month: <span>${s.best_month?.period||'—'}</span></div>
    <div class="stat-pill">Worst Month: <span>${s.worst_month?.period||'—'}</span></div>
    <div class="stat-pill">Avg MoM: <span>${(s.avg_mom_pct||0).toFixed(1)}%</span></div>
  `;
  const ch = kpi.charts || {};
  const summaryHtml = sums.kpi
    ? `<div class="ai-summary" style="margin-bottom:1rem"><span class="ai-label">✦ KPI Insight</span>${sums.kpi}</div>`
    : '';
  cc.innerHTML = summaryHtml + `<div class="chart-grid">
    ${ch.trend  ? ccard('Monthly Trend',         ch.trend)  : ''}
    ${ch.growth ? ccard('MoM Growth (%)',         ch.growth) : ''}
    ${ch.qoq    ? ccard('Quarter-over-Quarter (%)',ch.qoq)   : ''}
    ${ch.box    ? ccard('Distribution (Box Plot)', ch.box)   : ''}
  </div>`;
}

function renderAnalysis(d, sums) {
  const c = document.getElementById('analysis-content');
  const t = d.analysis_type;
  const summaryHtml = (txt) => txt
    ? `<div class="ai-summary" style="margin-bottom:1rem"><span class="ai-label">✦ Insight</span>${txt}</div>`
    : '';

  if (t==='rfm' && d.rfm) {
    if (d.rfm.error) { c.innerHTML=errBox(d.rfm.error); return; }
    const BCLS = {Champions:'bc',Loyal:'bl','At Risk':'br',Lost:'blost','Needs Attention':'bn'};
    const segs = (d.rfm.segments||[]).map(s=>`
      <div class="rfm-card">
        <div style="margin-bottom:.5rem"><span class="badge ${BCLS[s.Segment]||'bc'}">${s.Segment}</span></div>
        <div style="font-size:1.4rem;font-weight:800;font-family:var(--font-head)">${(s.Count||0).toLocaleString()}</div>
        <div style="font-size:.67rem;color:var(--muted);margin-top:.35rem">Avg Recency: ${(s.Avg_Rec||0).toFixed(0)}d</div>
        <div style="font-size:.67rem;color:var(--muted)">Avg Freq: ${(s.Avg_Freq||0).toFixed(1)}</div>
        <div style="font-size:.67rem;color:var(--muted)">Avg Value: ${fmt(s.Avg_Mon||0)}</div>
      </div>`).join('');
    const ch = d.rfm.charts || {};
    c.innerHTML = summaryHtml(sums.analysis) +
      `<div class="rfm-grid" style="margin-bottom:1.25rem">${segs}</div>
      <div class="chart-grid">
        ${ch.pie?ccard('Segment Distribution (Donut)',ch.pie):''}
        ${ch.scatter?ccard('Recency vs Monetary',ch.scatter):''}
        ${ch.bar?ccard('Customers per Segment',ch.bar):''}
      </div>`;
  } else if (t==='cohort' && d.cohort) {
    if (d.cohort.error) { c.innerHTML=errBox(d.cohort.error); return; }
    c.innerHTML = summaryHtml(sums.analysis) +
      (d.cohort.chart ? ccard('AOV per Cohort Month', d.cohort.chart, true) : nodata());
  } else if (t==='funnel' && d.funnel) {
    if (d.funnel.error) { c.innerHTML=errBox(d.funnel.error); return; }
    const rows = (d.funnel.data||[]).map(r=>`<tr><td>${r.stage}</td><td>${(r.count||0).toLocaleString()}</td><td>${(r.conv_pct||0).toFixed(1)}%</td></tr>`).join('');
    c.innerHTML = summaryHtml(sums.analysis) + `<div class="chart-grid">
      ${d.funnel.chart ? ccard('Funnel Conversion',d.funnel.chart) : ''}
      <div class="chart-card"><div class="chart-head"><div class="chart-title">Stage Breakdown</div></div>
        <div style="padding:.75rem"><div class="table-wrap"><table>
          <thead><tr><th>Stage</th><th>Count</th><th>Conversion</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div></div></div>
    </div>`;
  } else if (t==='ops' && d.ops) {
    if (d.ops.error) { c.innerHTML=errBox(d.ops.error); return; }
    const s = d.ops.summary || {};
    c.innerHTML = summaryHtml(sums.analysis) +
      `<div class="stat-row"><div class="stat-pill">Mean: <span>${fmt(s.mean)}</span></div><div class="stat-pill">Std: <span>${fmt(s.std)}</span></div><div class="stat-pill">Max: <span>${fmt(s.max)}</span></div><div class="stat-pill">Min: <span>${fmt(s.min)}</span></div></div>
      ${d.ops.chart ? ccard('Moving Averages (7d / 30d) + Bollinger', d.ops.chart, true) : nodata()}`;
  } else if (t==='seasonal' && d.seasonal) {
    if (d.seasonal.error) { c.innerHTML=errBox(d.seasonal.error); return; }
    c.innerHTML = summaryHtml(sums.analysis) +
      (d.seasonal.chart ? ccard('Seasonal Patterns (4-panel)', d.seasonal.chart, true) : nodata());
  } else if (t==='trend' && d.trend) {
    if (d.trend.error) { c.innerHTML=errBox(d.trend.error); return; }
    const td = d.trend;
    c.innerHTML = summaryHtml(td.summary || sums.analysis) +
      `<div class="stat-row">
        <div class="stat-pill">Direction: <span>${td.direction||'—'}</span></div>
        <div class="stat-pill">Strength: <span>${td.strength||'—'}</span></div>
        <div class="stat-pill">R²: <span>${(td.r_squared||0).toFixed(3)}</span></div>
        <div class="stat-pill">Slope: <span>${(td.slope||0).toFixed(3)}/mo</span></div>
      </div>` +
      (td.chart ? ccard('Trend Analysis with Linear Fit', td.chart, true) : nodata());
  } else if (t==='pareto' && d.pareto) {
    if (d.pareto.error) { c.innerHTML=errBox(d.pareto.error); return; }
    c.innerHTML = summaryHtml(d.pareto.summary || sums.analysis) +
      (d.pareto.chart ? ccard('Pareto Analysis (80/20 Rule)', d.pareto.chart, true) : nodata());
  } else if (t==='price' && d.price) {
    if (d.price.error) { c.innerHTML=errBox(d.price.error); return; }
    c.innerHTML = summaryHtml(d.price.summary || sums.analysis) +
      `<div class="stat-row"><div class="stat-pill">Correlation: <span>${(d.price.correlation||0).toFixed(3)}</span></div></div>` +
      (d.price.chart ? ccard('Price Sensitivity Analysis', d.price.chart, true) : nodata());
  } else if (t==='growth' && d.growth) {
    if (d.growth.error) { c.innerHTML=errBox(d.growth.error); return; }
    c.innerHTML = summaryHtml(sums.analysis) +
      (d.growth.chart ? ccard('Growth Accounting — New vs Retained vs Churned', d.growth.chart, true) : nodata());
  } else if (t==='contribution' && d.contribution) {
    if (d.contribution.error) { c.innerHTML=errBox(d.contribution.error); return; }
    c.innerHTML = summaryHtml(sums.analysis) +
      (d.contribution.chart ? ccard('Contribution Margin Analysis', d.contribution.chart, true) : nodata());
  } else if (t==='velocity' && d.velocity) {
    if (d.velocity.error) { c.innerHTML=errBox(d.velocity.error); return; }
    c.innerHTML = summaryHtml(d.velocity.summary || sums.analysis) +
      (d.velocity.chart ? ccard('Velocity & Acceleration Tracking', d.velocity.chart, true) : nodata());
  } else if (t==='period' && d.period) {
    if (d.period.error) { c.innerHTML=errBox(d.period.error); return; }
    c.innerHTML = summaryHtml(d.period.summary || sums.analysis) +
      `<div class="stat-row">
        <div class="stat-pill">Current Total: <span>${fmt(d.period.current_total||0)}</span></div>
        <div class="stat-pill">Previous Total: <span>${fmt(d.period.previous_total||0)}</span></div>
        <div class="stat-pill">Change: <span>${(d.period.change_pct||0).toFixed(1)}%</span></div>
      </div>` +
      (d.period.chart ? ccard('Period Comparison (Q vs Q)', d.period.chart, true) : nodata());
  } else {
    c.innerHTML = `<p style="color:var(--muted);padding:1rem 0">Select an analysis type from the sidebar for detailed results here.</p>`;
  }
}

function renderAlerts(anom, sums) {
  const c = document.getElementById('alerts-content');
  const summaryHtml = sums.anomalies
    ? `<div class="ai-summary" style="margin-bottom:1rem"><span class="ai-label">✦ Anomaly Insight</span>${sums.anomalies}</div>`
    : '';
  if (!anom.total) {
    c.innerHTML = summaryHtml + `<div class="no-alerts">✓ No anomalies detected. Everything looks healthy.</div>`;
    return;
  }
  const items = (anom.alerts||[]).map(a=>`
    <div class="alert-item ${a.severity.toLowerCase()}">
      <div class="aicon">${a.severity==='CRITICAL'?'🔴':'🟡'}</div>
      <div class="abody">
        <div class="atype">${a.type}</div>
        <div class="adesc">${a.description}</div>
        <div class="acol">${a.column}${a.z_score!=null?' · z='+a.z_score:''}</div>
      </div>
    </div>`).join('');
  c.innerHTML = summaryHtml +
    (anom.chart?`<div style="margin-bottom:1rem">${ccard('Alert Summary',anom.chart)}</div>`:'') +
    `<div class="alert-list">${items}</div>`;
}

function renderQuality(cols, sc) {
  const c     = document.getElementById('quality-content');
  const score = sc.quality_score || 0;
  const sc_   = score>=80?'green':score>=60?'yellow':'red';
  const colRows = cols.filter(x=>!x.col.endsWith('_outlier')).map(x=>{
    const cls = x.fill_rate>=90?'':x.fill_rate>=70?'warn':'bad';
    return `<div class="q-item">
      <div class="q-name" title="${x.col}">${x.col}</div>
      <div class="fill-bar"><div class="fill-inner ${cls}" style="width:${x.fill_rate}%"></div></div>
      <div class="q-pct">${x.fill_rate}%</div>
      <div class="q-type">${stype(x.dtype)}</div>
    </div>`;
  }).join('');
  c.innerHTML = `
    <div class="kpi-grid" style="margin-bottom:1.25rem">
      <div class="kpi-card ${sc_}"><div class="knum">${score}</div><div class="klbl">Quality Score</div></div>
      <div class="kpi-card"><div class="knum">${(sc.nulls_before||0).toLocaleString()}</div><div class="klbl">Nulls Fixed</div></div>
      <div class="kpi-card"><div class="knum">${(sc.dupes_removed||0).toLocaleString()}</div><div class="klbl">Dupes Removed</div></div>
      <div class="kpi-card"><div class="knum">${(sc.rows_before||0).toLocaleString()} → ${(sc.rows_after||0).toLocaleString()}</div><div class="klbl">Rows</div></div>
    </div>
    <div style="font-size:.67rem;color:var(--muted);margin-bottom:.5rem;display:grid;grid-template-columns:155px 1fr 55px 55px;gap:.7rem;padding:0 .1rem">
      <span>Column</span><span>Fill Rate</span><span style="text-align:right">%</span><span style="text-align:right">Type</span>
    </div>
    <div class="q-list">${colRows}</div>`;
}

function renderPreview(preview) {
  const c = document.getElementById('preview-content');
  if (!preview.columns?.length) { c.innerHTML='<p style="color:var(--muted);padding:1rem">No preview available.</p>'; return; }
  const h = preview.columns.map(x=>`<th>${x}</th>`).join('');
  const r = (preview.rows||[]).map(row=>`<tr>${row.map(v=>`<td>${v??''}</td>`).join('')}</tr>`).join('');
  c.innerHTML = `<div class="table-wrap"><table><thead><tr>${h}</tr></thead><tbody>${r}</tbody></table></div>`;
}

// ── Export ─────────────────────────────────────────────────────
async function exportCSV() {
  if (!S.file) return;
  try {
    const fd = new FormData(); fd.append('file', S.file);
    const r  = await fetch(`${BASE}/export`, {method:'POST', body:fd});
    if (!r.ok) throw new Error('Export failed');
    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href=url; a.download=`cleaned_${S.file.name}`; a.click();
    URL.revokeObjectURL(url);
  } catch(e) { alert('Export failed: '+e.message); }
}

function downloadReport() {
  if (!S.data?.report_html) return;
  const blob = new Blob([S.data.report_html], {type:'text/html'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href=url; a.download=`insightflow_${new Date().toISOString().slice(0,10)}.html`; a.click();
  URL.revokeObjectURL(url);
}

// ── UI Helpers ─────────────────────────────────────────────────
function switchTab(name, el) {
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById(`panel-${name}`).classList.add('active');
}

function ccard(title, b64, full=false) {
  const style = full ? 'style="grid-column:1/-1"' : '';
  return `<div class="chart-card" ${style}>
    <div class="chart-head"><div class="chart-title">${title}</div></div>
    <div class="chart-body"><img src="data:image/png;base64,${b64}" alt="${title}" loading="lazy"/></div>
  </div>`;
}

function errBox(msg) {
  return `<div class="err-box"><div>⚠</div><div><h3>Error</h3><p>${msg}</p></div></div>`;
}
function nodata() {
  return `<p style="color:var(--muted);padding:1rem 0">No chart available for this analysis.</p>`;
}

function fmt(n) {
  if (n==null||isNaN(n)) return '0';
  if (Math.abs(n)>=1e9) return (n/1e9).toFixed(1)+'B';
  if (Math.abs(n)>=1e6) return (n/1e6).toFixed(1)+'M';
  if (Math.abs(n)>=1e3) return (n/1e3).toFixed(1)+'K';
  return parseFloat(n.toFixed(2)).toLocaleString();
}

function stype(dt) {
  if (!dt) return '?';
  if (dt.includes('int'))      return 'int';
  if (dt.includes('float'))    return 'float';
  if (dt.includes('datetime')) return 'date';
  if (dt.includes('object'))   return 'text';
  if (dt.includes('bool'))     return 'bool';
  return dt.slice(0,5);
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.get("/health")
async def health():
    return {"status": "ok", "name": "Insight Flow", "version": "1.0.0", "by": "Aadhya"}


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    analysis_type: str = Form("kpi"),
    date_col: str = Form(""),
    metric_col: str = Form(""),
    customer_col: str = Form(""),
):
    try:
        from engine import InsightFlowEngine
        contents = await file.read()
        ext      = Path(file.filename).suffix.lower()
        
        # ✅ FIX: Run CPU-bound engine.run() in a separate thread to avoid blocking the async event loop
        def run_engine():
            engine = InsightFlowEngine(
                contents, ext,
                analysis_type=analysis_type,
                date_col=date_col   or None,
                metric_col=metric_col or None,
                customer_col=customer_col or None,
            )
            result = engine.run()
            result["filename"] = file.filename
            return result
            
        result = await asyncio.to_thread(run_engine)
        return JSONResponse(result)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))


@app.post("/export")
async def export_csv(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        ext      = Path(file.filename).suffix.lower()
        filename = file.filename

        def _run():
            engine = InsightFlowEngine(contents, ext)
            engine._load()
            engine._clean()
            buf = io.StringIO()
            engine.df.to_csv(buf, index=False)
            buf.seek(0)
            return buf.getvalue()

        csv_data = await asyncio.get_event_loop().run_in_executor(_executor, _run)
        return StreamingResponse(
            io.BytesIO(csv_data.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=cleaned_{filename}"}
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/columns")
async def get_columns(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        ext = file.filename.split('.')[-1]

        def _run():
            engine = InsightFlowEngine(contents, ext)
            engine._load()
            cols      = list(engine.df.columns)
            num_cols  = engine.df.select_dtypes(include="number").columns.tolist()
            date_cols = [c for c in cols if any(k in c.lower() for k in ["date","time","dt","period","month","year"])]
            id_cols   = [c for c in cols if any(k in c.lower() for k in ["customer","user","client","id"])]
            return {"all": cols, "numeric": num_cols, "date": date_cols, "id": id_cols}

        result = await asyncio.get_event_loop().run_in_executor(_executor, _run)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)