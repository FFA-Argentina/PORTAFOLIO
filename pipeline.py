#!/usr/bin/env python3
"""Tablero CEDEAR: proceso de datos.

Uso:
  python3 pipeline.py full --out DIR [--prev DIR]   reconstrucción completa con cierres ajustados (≈15 min)
  python3 pipeline.py intraday --out DIR            precio del momento sobre la historia publicada (≈1 min)

Escribe DIR/data/ced.js y DIR/data/ar.js (window.__CED / window.__AR). En modo intraday lee esos
mismos archivos como punto de partida. --prev reutiliza nombres y sectores ya conocidos.
Fuentes: data912.com (paneles BYMA y CCL), Yahoo Finance (series, cotizaciones, capitalización).
"""
import json, os, re, sys, time, statistics, datetime, argparse, http.cookiejar
import urllib.request, urllib.parse, urllib.error
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

NY, BA = ZoneInfo('America/New_York'), ZoneInfo('America/Argentina/Buenos_Aires')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
CNT = [0]
CRUMB = [None]

SECT_ES = {'Technology': 'Tecnología', 'Financial Services': 'Financiero', 'Healthcare': 'Salud',
           'Consumer Cyclical': 'Consumo discrecional', 'Consumer Defensive': 'Consumo básico', 'Energy': 'Energía',
           'Basic Materials': 'Materiales', 'Industrials': 'Industria', 'Communication Services': 'Comunicaciones',
           'Utilities': 'Servicios públicos', 'Real Estate': 'Inmobiliario'}
OVERRIDES = {'AKO.B': ['AKO-B'], 'BRKB': ['BRK-B'], 'DISN': ['DIS'], 'BNG': ['BG'], 'BNY': ['BNY', 'BK'],
             'NOKA': ['NOK'], 'PKS': ['PKX'], 'TEN': ['TS'], 'TXR': ['TX'], 'XROX': ['XRX'], 'KOFM': ['KOF'],
             'ELPC': ['ELPC', 'ELP'], 'ADS': ['ADDYY'], 'BAYN': ['BAYRY'], 'BBV': ['BBVA'], 'WBO': ['WB'],
             'FISV': ['FISV', 'FI'], 'EMBJ': ['EMBJ', 'ERJ'], 'MRSH': ['MRSH', 'MMC'], 'ADGO': ['AGRO', 'ADGO'],
             'BPA11': ['BPAC11.SA'], 'SKHY': ['SKHY', 'HXSCL']}
CED_DROP = {'B.C', 'B.D', 'BA.C', 'C.D', 'CAR.C', 'CAR.D', 'AKOBD', 'GOGLC', 'GOGLD', 'PETRC', 'PETRD',
            'SBSPD', 'VAL3C', 'VAL3D', 'NAT3D'}
CAP_ALT = {'ASR': ('ASURB.MX', 'MXN=X'), 'KOF': ('KOFUBL.MX', 'MXN=X'), 'LND': ('AGRO3.SA', 'BRL=X')}
AR_DROP = {'TECOD', 'TGN4D', 'TGSUD'}
AR_SEC = {'PAMP': 'Energía', 'INAG': 'Materiales', 'REGE': 'Consumo básico', 'HSAT': 'Comunicaciones',
          'IEB': 'Industria', 'CRES': 'Agro e inmobiliario', 'CADO': 'Agro e inmobiliario', 'LEDE': 'Consumo básico',
          'SAMI': 'Consumo básico', 'COME': 'Energía'}
MERVAL = ['ALUA', 'BBAR', 'BMA', 'BYMA', 'CEPU', 'COME', 'CRES', 'CVH', 'EDN', 'GGAL', 'IRSA', 'LOMA', 'METR', 'PAMP',
          'SUPV', 'TECO2', 'TGNO4', 'TGSU2', 'TRAN', 'TXAR', 'VALO', 'YPFD']
CCL_PAIRS = [('GGAL', 'GGAL', 10), ('YPFD', 'YPF', 1), ('PAMP', 'PAM', 25), ('BMA', 'BMA', 10)]


# ---------------------------------------------------------------- HTTP
def http(url, tries=5, raw=False):
    err = None
    for i in range(tries):
        CNT[0] += 1
        if 'finance.yahoo.com' in url and 'query' in url:
            url = re.sub(r'query[12]\.', 'query%d.' % (1 + CNT[0] % 2), url)
            time.sleep(0.25)
        try:
            with OP.open(urllib.request.Request(url, headers=UA), timeout=20) as r:
                b = r.read()
                return b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            err = e
            if e.code == 404:
                break
            time.sleep(8 * (i + 1) if e.code == 429 else 1.5)
        except Exception as e:
            err = e
            time.sleep(1.5 * (i + 1))
    raise err


def d912(path):
    return http('https://data912.com' + path)


def crumb():
    if not CRUMB[0]:
        try:
            OP.open(urllib.request.Request('https://fc.yahoo.com/', headers=UA), timeout=20)
        except Exception:
            pass
        CRUMB[0] = http('https://query1.finance.yahoo.com/v1/test/getcrumb', raw=True).decode()
    return CRUMB[0]


def quotes(syms):
    out, syms = {}, sorted(set(s for s in syms if s))
    for k in range(0, len(syms), 40):
        part = syms[k:k + 40]
        u = ('https://query1.finance.yahoo.com/v7/finance/quote?symbols=' + urllib.parse.quote(','.join(part))
             + '&crumb=' + urllib.parse.quote(crumb()))
        for q in http(u)['quoteResponse']['result']:
            out[q['symbol']] = q
    return out


def chart(sym, rng='5y'):
    u = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval=1d&events=div,split'
    d = http(u)['chart']['result'][0]
    q = d['indicators']['quote'][0]
    cl = q['close']
    adj = (d['indicators'].get('adjclose') or [{}])[0].get('adjclose') or cl
    return d['meta'], [(t, a, c) for t, a, c in zip(d['timestamp'], adj, cl) if a is not None and c is not None]


def search(sym):
    try:
        for x in http(f'https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(sym)}&quotesCount=5&newsCount=0')['quotes']:
            if x.get('symbol') == sym:
                return x
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------- utilidades
def sig(v, n=6):
    return None if v is None else (0 if v == 0 else float(f'{v:.{n}g}'))


def dstr(ts, tz):
    return datetime.datetime.fromtimestamp(ts, tz).strftime('%Y%m%d')


def now_ba():
    return datetime.datetime.now(BA).strftime('%Y-%m-%dT%H:%M')


def ffill(arr):
    last, out = None, []
    for v in arr:
        if v is not None:
            last = v
        out.append(last)
    return out


def ced_base(panel):
    S = {x['symbol'] for x in panel}
    return [s for s in sorted(S) if not ((s.endswith('D') or s.endswith('C')) and s[:-1] in S) and s not in CED_DROP]


def ar_base(panel):
    S = {x['symbol'] for x in panel}
    def dup(s):
        return (s.endswith('.D') and s[:-2] in S) or (s.endswith('D') and (s[:-1] in S or s[:-2] in S)) or (s == 'REITC' and 'REIT' in S)
    return [s for s in sorted(S) if not dup(s) and s not in AR_DROP]


def ccl_board(ccl, local=None):
    """CCL implícito: mediana de los pares local/ADR (GGAL, YPF, PAMP, BMA). Respaldo: panel de CCL de data912."""
    v = []
    Q = quotes([l + '.BA' for l, _, _ in CCL_PAIRS] + [a for _, a, _ in CCL_PAIRS])
    v = []
    for l, a, r in CCL_PAIRS:
        lp = (local or {}).get(l) or (Q.get(l + '.BA') or {}).get('regularMarketPrice')
        ap = (Q.get(a) or {}).get('regularMarketPrice')
        if lp and ap:
            v.append(lp / (ap / r))
    if v:
        return statistics.median(v)
    top = sorted(ccl or [], key=lambda x: -(x.get('ars_volume') or 0))[:15]
    return statistics.median(x['CCL_mark'] for x in top if x.get('CCL_mark'))


def cap_of(q, fx):
    if not q:
        return None
    mc = q.get('marketCap') or q.get('netAssets') or q.get('totalAssets')
    if not mc:
        return None
    cur = q.get('currency') or 'USD'
    if cur == 'USD':
        return mc
    return mc / fx[cur] if fx.get(cur) else None


def write_js(out, name, var, obj):
    os.makedirs(os.path.join(out, 'data'), exist_ok=True)
    s = json.dumps(obj, separators=(',', ':'), ensure_ascii=False).replace('</', '<\\/')
    with open(os.path.join(out, 'data', name), 'w') as f:
        f.write(f'window.{var}={s};\n')


def read_js(path):
    s = open(path).read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def ratio_of(last_usd, ccl, p_ars, p_d):
    implied = last_usd * ccl / p_ars if p_ars else (last_usd / p_d if p_d else None)
    if not implied or implied <= 0:
        return None, None, False
    ratio = max(1, round(implied)) if implied >= 0.75 else 1 / round(1 / implied)
    dev = implied / ratio - 1
    return ratio, dev, abs(dev) < 0.08


# ---------------------------------------------------------------- modo completo
def full(out, prev_dir=None):
    t0 = time.time()
    prev, PREVD = {}, {}
    for name in ('ced.js', 'ar.js'):
        p = os.path.join(prev_dir or out, 'data', name)
        if os.path.exists(p):
            try:
                PREVD[name] = read_js(p)
                for a in PREVD[name]['A']:
                    prev[a['t'] + '|' + name] = a
            except Exception:
                pass

    def carry(name, listed, have, dates, extra):
        """Activos que siguen cotizando pero cuya serie no se pudo bajar hoy: se conserva la publicada antes."""
        P0 = PREVD.get(name)
        if not P0:
            return [], [], []
        pos = {d: i for i, d in enumerate(P0['dates'])}
        A2, P2, L2 = [], [], []
        for j, a in enumerate(P0['A']):
            if a['t'] in have or a['t'] not in listed:
                continue
            src, arr, last = P0['P'][j], [], None
            for d in dates:
                i = pos.get(int(d))
                if i is not None and src[i] is not None:
                    last = src[i]
                arr.append(last)
            if sum(1 for v in arr if v is not None) < 60:
                continue
            b = dict(a); b.update(extra(a)); b['f'] = next(i for i, v in enumerate(arr) if v is not None); b['stale'] = True
            A2.append(b); P2.append(arr); L2.append(f"{a['t']}: serie no disponible hoy, se conserva la anterior")
        return A2, P2, L2
    panel = d912('/live/arg_cedears'); ccl_rows = d912('/live/ccl'); arp = d912('/live/arg_stocks')
    PANEL = {x['symbol']: x for x in panel}; ARP = {x['symbol']: x for x in arp}
    CCL = ccl_board(ccl_rows, {k: (ARP.get(k) or {}).get('c') for k in ('GGAL', 'YPFD', 'PAMP', 'BMA')})
    base = ced_base(panel)
    if len(panel) < 900 and PREVD.get('ced.js'):   # panel incompleto (apertura o rueda): universo anterior + altas claras
        known = {a['t'] for a in PREVD['ced.js']['A']}
        var = lambda x: x in known or x[:-1] in known or (x.endswith('.D') and x[:-2] in known) or x[-1] in 'CD'
        base = sorted(known | {x for x in base if not var(x)})
        for a in PREVD['ced.js']['A']:
            PANEL.setdefault(a['t'], {'c': a.get('px'), 'v': (a.get('v') or 0) / a['px'] if a.get('px') else 0})
            if a.get('pxd'): PANEL.setdefault(a['t'] + 'D', {'c': a['pxd']})
    print(f'[full] CCL {CCL:.2f} · {len(base)} CEDEARs · panel BYMA con {len(panel)} especies', flush=True)

    def work(t):
        for sym in OVERRIDES.get(t) or ([t + '.SA'] if re.fullmatch(r'[A-Z]{4}\d{1,2}', t) else [t]):
            try:
                meta, ser = chart(sym)
                if len(ser) >= 30:
                    return t, sym, meta, ser
            except Exception:
                continue
        return t, None, None, None

    with ThreadPoolExecutor(2) as ex:
        res = {t: (s, m, r) for t, s, m, r in ex.map(work, base)}
    for t in [t for t, v in res.items() if not v[0]]:   # segunda pasada, sin concurrencia
        time.sleep(2)
        _, s_, m_, r_ = work(t)
        res[t] = (s_, m_, r_)
    print(f'[full] series CEDEAR {sum(1 for v in res.values() if v[0])}/{len(base)} · {time.time()-t0:.0f}s', flush=True)
    _, brl_ser = chart('BRL=X'); _, irx_ser = chart('^IRX')

    # calendario EE.UU. (SPY)
    dates = sorted({dstr(t, NY) for t, a, c in res['SPY'][2]})
    idx = {d: i for i, d in enumerate(dates)}; N = len(dates)

    def align(ser, col, tz):
        arr = [None] * N
        for row in ser:
            d = dstr(row[0], tz)
            if d in idx and row[col] and row[col] > 0:
                arr[idx[d]] = row[col]
        return arr

    brl = ffill(align(brl_ser, 2, NY)); brl = [v or brl[next(i for i, x in enumerate(brl) if x)] for v in brl]
    irx = ffill(align(irx_ser, 2, NY)); irx = [round(v, 3) if v else 4.0 for v in irx]
    syms = [v[0] for v in res.values() if v[0]]
    Q = quotes(syms + ['BRL=X', 'MXN=X'] + [s for s, _ in CAP_ALT.values()])
    FX = {'BRL': (Q.get('BRL=X') or {}).get('regularMarketPrice') or brl[-1], 'MXN': (Q.get('MXN=X') or {}).get('regularMarketPrice')}
    need = [s for t, (s, m, r) in res.items() if s and (t + '|ced.js') not in prev]
    with ThreadPoolExecutor(2) as ex:
        INFO = dict(zip(need, ex.map(search, need)))

    assets, prices, log = [], [], []
    for t, (sym, meta, ser) in sorted(res.items()):
        if not sym:
            log.append(f'{t}: sin serie'); continue
        arr = align(ser, 1, NY)
        first = next((i for i, v in enumerate(arr) if v is not None), None)
        if first is None or N - first < 60:
            log.append(f'{t}: historia corta'); continue
        last = arr[first]
        for i in range(first, N):
            if arr[i] is None: arr[i] = last
            else: last = arr[i]
        cur = meta.get('currency') or 'USD'
        if cur == 'BRL':
            arr = [p / brl[i] if p is not None else None for i, p in enumerate(arr)]
        elif cur != 'USD':
            log.append(f'{t}: moneda {cur}'); continue
        k = ser[-1][1] / ser[-1][2]  # factor de ajuste en la última barra (≈1)
        pa = PANEL.get(t, {}); pd = PANEL.get(t + 'D', {})
        ratio, dev, ok = ratio_of(arr[-1], CCL, pa.get('c') or 0, pd.get('c') or 0)
        if dev is not None and abs(dev) > 0.30:
            log.append(f'{t}: subyacente {sym} no coincide, excluido'); continue
        old = prev.get(t + '|ced.js')
        if old:
            name, sec, ind, typ = old['n'], old['s'], old['i'], old['k']
        else:
            info = INFO.get(sym, {})
            typ = 'ETF' if (info.get('quoteType') or meta.get('instrumentType') or '').upper() == 'ETF' else 'Acción'
            sec = SECT_ES.get(info.get('sector') or '', info.get('sector') or ('ETF' if typ == 'ETF' else 'Otros'))
            name = info.get('longname') or meta.get('longName') or meta.get('shortName') or t
            ind = info.get('industry') or ''
        mc = cap_of(Q.get(sym), FX)
        if not mc and sym in CAP_ALT:
            alt, fx = CAP_ALT[sym]
            q = Q.get(alt) or {}
            if q.get('marketCap') and (Q.get(fx) or {}).get('regularMarketPrice'):
                mc = q['marketCap'] / Q[fx]['regularMarketPrice']
        assets.append({'t': t, 'u': sym, 'n': name, 's': sec, 'i': ind, 'k': typ, 'cur': cur, 'r': ratio, 'rok': ok,
                       'px': pa.get('c') or None, 'pxd': pd.get('c') or None, 'v': (pa.get('c') or 0) * (pa.get('v') or 0),
                       'f': first, 'mc': round(mc) if mc else None, 'kf': sig(k, 8)})
        prices.append([sig(p) for p in arr])
    a2, p2, l2 = carry('ced.js', set(base), {a['t'] for a in assets}, dates,
                       lambda a: {'px': (PANEL.get(a['t']) or {}).get('c') or a.get('px'),
                                  'v': ((PANEL.get(a['t']) or {}).get('c') or 0) * ((PANEL.get(a['t']) or {}).get('v') or 0)})
    assets += a2; prices += p2; log += l2
    CED = {'asof': int(dates[-1]), 'ccl': round(CCL, 2), 'dates': [int(d) for d in dates], 'rf': irx, 'A': assets, 'P': prices,
           'upd': now_ba(), 'live': False, 'close': int(dates[-1])}
    write_js(out, 'ced.js', '__CED', CED)
    print(f'[full] CEDEAR {len(assets)} activos · {dates[0]}→{dates[-1]} · {time.time()-t0:.0f}s', flush=True)
    for l in log: print('   ', l)

    # ---------------- acciones argentinas
    abase = ar_base(arp)
    if PREVD.get('ar.js'):   # las especies poco operadas no siempre figuran en el panel del día
        known = {a['t'] for a in PREVD['ar.js']['A']}
        abase = sorted(known | {x for x in abase if not (x[:-1] in known or x.endswith('D'))})
        for a in PREVD['ar.js']['A']:
            ARP.setdefault(a['t'], {'c': a.get('px'), 'q_op': a.get('ops')})
    def work_ar(t):
        try:
            meta, ser = chart(t + '.BA')
            return t, (meta, ser) if len(ser) >= 30 else None
        except Exception:
            return t, None
    with ThreadPoolExecutor(2) as ex:
        AR = {t: v for t, v in ex.map(work_ar, abase) if v}
    for t in [t for t in abase if t not in AR]:
        time.sleep(2)
        _, v_ = work_ar(t)
        if v_: AR[t] = v_
    AX = {s: chart(s)[1] for s in ['GGAL', 'YPF', 'PAM', 'BMA', '^MERV']}
    cal = sorted({dstr(t, BA) for t, a, c in AR['GGAL'][1]}); aidx = {d: i for i, d in enumerate(cal)}; M = len(cal)

    def align_ar(ser, col):
        arr = [None] * M
        for row in ser:
            d = dstr(row[0], BA)
            if d in aidx and row[col] and row[col] > 0:
                arr[aidx[d]] = row[col]
        return arr
    locs = {l: align_ar(AR[l][1], 2) for l, _, _ in CCL_PAIRS}
    adrs = {a: ffill(align_ar(AX[a], 2)) for _, a, _ in CCL_PAIRS}
    ccl = []
    for t in range(M):
        v = [locs[l][t] / (adrs[a][t] / r) for l, a, r in CCL_PAIRS if locs[l][t] and adrs[a][t]]
        ccl.append(statistics.median(v) if v else None)
    ccl = ffill(ccl); f0 = next(i for i, v in enumerate(ccl) if v); ccl = [v or ccl[f0] for v in ccl]
    irx_map = {dstr(t, NY): c for t, a, c in irx_ser}
    rf, lastr = [], 4.0
    for d in cal:
        lastr = irx_map.get(d) or lastr; rf.append(round(lastr, 3))
    merv_raw = align_ar(AX['^MERV'], 2)
    merv = ffill(merv_raw)
    B = [sig(m / c) if m and c else None for m, c in zip(merv, ccl)]
    mlast = max(i for i, v in enumerate(merv_raw) if v)
    AQ = quotes([t + '.BA' for t in AR])
    needa = [t for t in AR if (t + '|ar.js') not in prev]
    with ThreadPoolExecutor(2) as ex:
        AINFO = dict(zip(needa, ex.map(lambda t: search(t + '.BA'), needa)))
    aassets, aprices, alog = [], [], []
    for t, (meta, ser) in sorted(AR.items()):
        arr = align_ar(ser, 1)
        first = next((i for i, v in enumerate(arr) if v is not None), None)
        if first is None or M - first < 60:
            alog.append(f'{t}: historia corta'); continue
        last = arr[first]
        for i in range(first, M):
            if arr[i] is None: arr[i] = last
            else: last = arr[i]
        fixes, clean = 0, arr[:]
        for i in range(first + 1, M):
            r = arr[i] / arr[i - 1]
            if r > 1.85 or r < 0.54:
                fixes += 1; r = 1.0
            clean[i] = clean[i - 1] * r
        rawc = [r[2] for r in ser][-245:]
        flat = sum(1 for j in range(1, len(rawc)) if rawc[j] == rawc[j - 1]) / max(1, len(rawc) - 1)
        k = clean[-1] / ser[-1][2]
        q = AQ.get(t + '.BA', {}); p = ARP.get(t, {}); old = prev.get(t + '|ar.js')
        if old:
            name, sec, ind = old['n'], old['s'], old['i']
        else:
            info = AINFO.get(t, {})
            sec = AR_SEC.get(t) or SECT_ES.get(info.get('sector') or '', 'Otros')
            name = q.get('longName') or info.get('longname') or meta.get('longName') or q.get('shortName') or t
            ind = info.get('industry') or ''
        mc = q.get('marketCap')
        aassets.append({'t': t, 'u': t + '.BA', 'n': name, 's': sec, 'i': ind, 'k': 'Acción', 'cur': 'ARS', 'r': None, 'rok': True,
                        'px': p.get('c') or None, 'pxd': None, 'v': ((p.get('c') or 0) * (p.get('v') or 0)) or None,
                        'ops': p.get('q_op') or None, 'f': first, 'mc': round(mc / ccl[-1]) if mc else None,
                        'fix': fixes, 'flat': round(flat, 2), 'il': flat > 0.30, 'kf': sig(k, 8)})
        aprices.append([sig(v / ccl[i]) if v is not None else None for i, v in enumerate(clean)])
    if mlast < M - 1:   # Yahoo atrasado: se encadena un índice equivalente ponderado por capitalización
        mem = [(j, a['mc']) for j, a in enumerate(aassets) if a['t'] in MERVAL and a.get('mc')]
        tw = sum(w for _, w in mem)
        for t in range(mlast + 1, M):
            r = sum(w / tw * (aprices[j][t] / aprices[j][t - 1] - 1) for j, w in mem if aprices[j][t] and aprices[j][t - 1])
            B[t] = sig(B[t - 1] * (1 + r))
        alog.append(f'Merval de Yahoo hasta {cal[mlast]}; completado con índice equivalente de {len(mem)} acciones')
    a2, p2, l2 = carry('ar.js', set(abase), {a['t'] for a in aassets}, cal,
                       lambda a: {'px': (ARP.get(a['t']) or {}).get('c') or a.get('px'), 'ops': (ARP.get(a['t']) or {}).get('q_op') or a.get('ops')})
    aassets += a2; aprices += p2; alog += l2
    ARD = {'asof': int(cal[-1]), 'ccl': round(ccl[-1], 2), 'dates': [int(d) for d in cal], 'rf': rf, 'A': aassets, 'P': aprices,
           'B': B, 'C': [round(v, 2) for v in ccl], 'upd': now_ba(), 'live': False, 'close': int(cal[-1]), 'bproxy': int(cal[mlast]) if mlast < M - 1 else None}
    write_js(out, 'ar.js', '__AR', ARD)
    print(f'[full] AR {len(aassets)} activos · {cal[0]}→{cal[-1]} · CCL {ccl[-1]:.2f} · total {time.time()-t0:.0f}s', flush=True)
    for l in alog: print('   ', l)


# ---------------------------------------------------------------- modo intradiario
def place(D, qdate):
    """Devuelve 'append', 'replace' o None según la fecha de la cotización y el último punto."""
    last = D['dates'][-1]
    if qdate > last:
        D['dates'].append(qdate); D['rf'].append(D['rf'][-1])
        for p in D['P']:
            p.append(p[-1])
        if 'B' in D:
            D['B'].append(D['B'][-1])
        if 'C' in D:
            D['C'].append(D['C'][-1])
        return 'append'
    if qdate == last and D.get('live'):
        return 'replace'
    return None


def intraday(out):
    t0 = time.time()
    CED = read_js(os.path.join(out, 'data', 'ced.js')); ARD = read_js(os.path.join(out, 'data', 'ar.js'))
    panel = d912('/live/arg_cedears'); ccl_rows = d912('/live/ccl'); arp = d912('/live/arg_stocks')
    PANEL = {x['symbol']: x for x in panel}; ARP = {x['symbol']: x for x in arp}
    syms = [a['u'] for a in CED['A']] + [a['u'] for a in ARD['A']] + ['BRL=X', '^IRX', '^MERV', 'SPY', 'GGAL', 'YPF', 'PAM', 'BMA'] + [l + '.BA' for l, _, _ in CCL_PAIRS]
    Q = quotes(syms)
    FX = {'BRL': (Q.get('BRL=X') or {}).get('regularMarketPrice')}
    px = lambda s: (Q.get(s) or {}).get('regularMarketPrice')
    qd = lambda s, tz: dstr(Q[s]['regularMarketTime'], tz) if (Q.get(s) or {}).get('regularMarketTime') else None

    # ---- CEDEARs
    CED['ccl'] = round(ccl_board(ccl_rows, {k: (ARP.get(k) or {}).get('c') for k in ('GGAL', 'YPFD', 'PAMP', 'BMA')}), 2)
    qdate = int(qd('SPY', NY))
    mode = place(CED, qdate)
    upd = 0
    for a, p in zip(CED['A'], CED['P']):
        pa, pd = PANEL.get(a['t'], {}), PANEL.get(a['t'] + 'D', {})
        a['px'] = pa.get('c') or a['px']; a['pxd'] = pd.get('c') or a.get('pxd')
        a['v'] = (pa.get('c') or 0) * (pa.get('v') or 0) or a['v']
        mc = cap_of(Q.get(a['u']), FX)
        if mc: a['mc'] = round(mc)
        if mode:
            pr, d = px(a['u']), qd(a['u'], NY)
            fx = 1 if a['cur'] == 'USD' else FX.get(a['cur'])
            if pr and fx and d and int(d) == qdate:
                p[-1] = sig((a.get('kf') or 1) * pr / fx); upd += 1
    if mode and px('^IRX'):
        CED['rf'][-1] = round(px('^IRX'), 3)
    if mode:
        CED['live'] = True; CED['asof'] = qdate
    CED['upd'] = now_ba()
    write_js(out, 'ced.js', '__CED', CED)
    print(f'[intraday] CEDEAR {mode or "sin cambio de precios"} {qdate} · {upd} precios · CCL {CED["ccl"]}', flush=True)

    # ---- acciones argentinas
    ccl_now = CED['ccl']
    lead = [qd(l + '.BA', BA) for l, _, _ in CCL_PAIRS]
    lead = [int(d) for d in lead if d]
    adate = max(lead) if lead else ARD['dates'][-1]
    amode = place(ARD, adate)
    aupd = 0
    for a, p in zip(ARD['A'], ARD['P']):
        pa = ARP.get(a['t'], {})
        a['px'] = pa.get('c') or a['px']; a['ops'] = pa.get('q_op') or a.get('ops')
        a['v'] = ((pa.get('c') or 0) * (pa.get('v') or 0)) or a.get('v')
        mc = (Q.get(a['u']) or {}).get('marketCap')
        if mc: a['mc'] = round(mc / ccl_now)
        if amode and pa.get('c'):
            p[-1] = sig((a.get('kf') or 1) * pa['c'] / ccl_now); aupd += 1
    if amode:
        if px('^MERV') and qd('^MERV', BA) and int(qd('^MERV', BA)) == adate:
            ARD['B'][-1] = sig(px('^MERV') / ccl_now)
        else:
            mem = [(j, a['mc']) for j, a in enumerate(ARD['A']) if a['t'] in MERVAL and a.get('mc')]
            tw = sum(w for _, w in mem) or 1
            r = sum(w / tw * (ARD['P'][j][-1] / ARD['P'][j][-2] - 1) for j, w in mem if ARD['P'][j][-1] and ARD['P'][j][-2])
            ARD['B'][-1] = sig(ARD['B'][-2] * (1 + r))
        if px('^IRX'): ARD['rf'][-1] = round(px('^IRX'), 3)
        if 'C' in ARD: ARD['C'][-1] = round(ccl_now, 2)
        ARD['live'] = True; ARD['asof'] = adate
    ARD['ccl'] = round(ccl_now, 2); ARD['upd'] = now_ba()
    write_js(out, 'ar.js', '__AR', ARD)
    print(f'[intraday] AR {amode or "sin cambio de precios"} {adate} · {aupd} precios · CCL implícito {ccl_now:.2f} · {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['full', 'intraday'])
    ap.add_argument('--out', required=True)
    ap.add_argument('--prev')
    a = ap.parse_args()
    (full(a.out, a.prev) if a.mode == 'full' else intraday(a.out))
