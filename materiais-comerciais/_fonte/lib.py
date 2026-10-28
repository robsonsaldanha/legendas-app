ICONS = {
 'lang':'<path d="M5 8l6 6M4 14l6-6 2-3M2 5h12M7 2h1M22 22l-5-10-5 10M14 18h6"/>',
 'shield':'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
 'wave':'<path d="M2 12h2M6 8v8M10 4v16M14 7v10M18 9v6M22 12h-2"/>',
 'clock':'<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
 'users':'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
 'chart':'<path d="M3 3v18h18"/><path d="M7 15l4-5 4 3 5-7"/>',
 'mic':'<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3"/>',
 'ear':'<path d="M6 8.5a6 6 0 1 1 12 0c0 3-2 4-3 6s0 5-3 5-3-2-3-3"/><path d="M9 9a3 3 0 0 1 6 0"/>',
 'refresh':'<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>',
 'check':'<circle cx="12" cy="12" r="10"/><path d="M8 12l3 3 5-6"/>',
 'layers':'<path d="M12 2l10 5-10 5L2 7z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>',
 'folder':'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
 'file':'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
 'sliders':'<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
 'cloud':'<path d="M18 10a6 6 0 0 0-11.7-1.6A4.5 4.5 0 0 0 7 17h11a4 4 0 0 0 0-8z"/>',
 'bolt':'<path d="M13 2L3 14h8l-1 8 10-12h-8z"/>',
 'lock':'<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
 'film':'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 12h4M3 16h4M17 8h4M17 12h4M17 16h4"/>',
 'target':'<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
 'pc':'<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
 'star':'<path d="M12 2l3 7 7 .6-5.3 4.7 1.6 7.2L12 17.8 5.7 21.5l1.6-7.2L2 9.6 9 9z"/>',
}
def ico(n): return f'<div class="ico"><svg viewBox="0 0 24 24">{ICONS[n]}</svg></div>'
def icon_only(n,size=20): return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" style="stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round">{ICONS[n]}</svg>'
LOGO='<img src="../img/logo.png" alt="CNT Legendas">'
SITE='legendas.cntoficial.com.br'
def shot(name, style=''): return f'<div class="shot" style="{style}"><img src="../img/{name}.jpg"></div>'
def page(inner, cls='', style=''): return f'<section class="pg {cls}" style="{style}">{inner}</section>'
def doc(title, css, body):
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{title}</title><link rel="stylesheet" href="base.css"><style>{css}</style></head><body>{body}</body></html>'
