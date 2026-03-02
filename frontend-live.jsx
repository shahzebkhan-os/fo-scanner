import React, { useState, useEffect, useCallback } from "react";

const API = "http://localhost:8000/api";
const FONT = `'IBM Plex Mono', monospace`;

const css = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #080c10; }
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: #0d1117; }
  ::-webkit-scrollbar-thumb { background: #1e3a5f; border-radius: 2px; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
  @keyframes slideIn { from{transform:translateY(8px);opacity:0} to{transform:translateY(0);opacity:1} }
  @keyframes glow { 0%,100%{box-shadow:0 0 8px rgba(0,255,136,0.2)} 50%{box-shadow:0 0 22px rgba(0,255,136,0.5)} }
  @keyframes spin { to { transform: rotate(360deg); } }
  .live-dot { animation: pulse 1.5s infinite; }
  .slide-in { animation: slideIn 0.3s ease forwards; }
  .best-card { animation: glow 2s ease-in-out infinite; }
  .spin { animation: spin 1s linear infinite; display:inline-block; }
`;

// ── Helpers ────────────────────────────────────────────────────────────────
const fmt = (n) => n >= 1e7 ? (n / 1e7).toFixed(1) + 'Cr' : n >= 1e5 ? (n / 1e5).toFixed(1) + 'L' : n >= 1e3 ? (n / 1e3).toFixed(0) + 'K' : String(n ?? 0);
const pct = (n) => ((n ?? 0) > 0 ? '+' : '') + (n ?? 0).toFixed(1) + '%';
const clr = (v) => (v ?? 0) > 0 ? '#00ff88' : (v ?? 0) < 0 ? '#ff4d6d' : '#8899aa';

const Badge = ({ label, color }) => (
  <span style={{ padding: '2px 8px', borderRadius: 3, fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', fontFamily: FONT, background: color + '22', color, border: `1px solid ${color}44` }}>{label}</span>
);
const SignalBadge = ({ signal }) => {
  const map = { BULLISH: '#00ff88', BEARISH: '#ff4d6d', NEUTRAL: '#f0c040' };
  return <Badge label={signal} color={map[signal] || '#8899aa'} />;
};
const ScoreBar = ({ score }) => {
  const s = Math.min(score ?? 0, 100);
  const color = s >= 70 ? '#00ff88' : s >= 45 ? '#f0c040' : '#ff4d6d';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 60, height: 4, background: '#1a2535', borderRadius: 2 }}>
        <div style={{ width: `${s}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.4s' }} />
      </div>
      <span style={{ color, fontSize: 11, fontWeight: 700 }}>{s}</span>
    </div>
  );
};
const Spinner = () => <span className="spin" style={{ color: '#00ff88', fontSize: 16 }}>⟳</span>;

const ErrorBox = ({ msg, onRetry }) => (
  <div style={{ background: '#1a0a0a', border: '1px solid #ff4d6d44', borderRadius: 8, padding: 20, textAlign: 'center' }}>
    <div style={{ color: '#ff4d6d', fontFamily: FONT, fontSize: 13, marginBottom: 12 }}>⚠ {msg}</div>
    {onRetry && <button onClick={onRetry} style={{ background: '#ff4d6d22', border: '1px solid #ff4d6d', color: '#ff4d6d', padding: '6px 16px', borderRadius: 4, cursor: 'pointer', fontFamily: FONT, fontSize: 12 }}>RETRY</button>}
  </div>
);

// ── Main App ───────────────────────────────────────────────────────────────
export default function App() {
  const [stocks, setStocks] = useState([]);
  const [selected, setSelected] = useState(null);
  const [chain, setChain] = useState(null);
  const [expiry, setExpiry] = useState(null);
  const [tab, setTab] = useState("scanner");
  const [filter, setFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState("score");
  const [searchQ, setSearchQ] = useState("");
  const [scanning, setScanning] = useState(false);
  const [loadingChain, setLoadingChain] = useState(false);
  const [scanError, setScanError] = useState(null);
  const [chainError, setChainError] = useState(null);
  const [lastScan, setLastScan] = useState(null);
  const [hoverRow, setHoverRow] = useState(null);
  const [backendOk, setBackendOk] = useState(null); // null=checking, true, false

  // ── Check backend health ──
  useEffect(() => {
    fetch(`${API.replace('/api', '/health')}`)
      .then(r => r.ok ? setBackendOk(true) : setBackendOk(false))
      .catch(() => setBackendOk(false));
  }, []);

  // ── Scan ──
  const runScan = useCallback(async () => {
    setScanning(true);
    setScanError(null);
    try {
      const r = await fetch(`${API}/scan?limit=50`);
      if (!r.ok) throw new Error(`Server error ${r.status}`);
      const json = await r.json();
      setStocks(json.data || []);
      setLastScan(new Date());
    } catch (e) {
      setScanError("Could not reach backend. Is it running on port 8000?");
    } finally {
      setScanning(false);
    }
  }, []);

  useEffect(() => { if (backendOk) runScan(); }, [backendOk]);

  // ── Load chain ──
  const selectStock = async (s) => {
    setSelected(s);
    setChain(null);
    setChainError(null);
    setLoadingChain(true);
    setTab("chain");
    try {
      const exp = expiry || (s.expiries?.[0] ?? "");
      const url = `${API}/chain/${s.symbol}${exp ? `?expiry=${encodeURIComponent(exp)}` : ""}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`Server error ${r.status}`);
      const json = await r.json();
      setChain(json);
      if (!expiry && json.expiry) setExpiry(json.expiry);
    } catch (e) {
      setChainError("Failed to load option chain. Check backend logs.");
    } finally {
      setLoadingChain(false);
    }
  };

  const changeExpiry = async (exp) => {
    if (!selected) return;
    setExpiry(exp);
    setLoadingChain(true);
    setChainError(null);
    try {
      const r = await fetch(`${API}/chain/${selected.symbol}?expiry=${encodeURIComponent(exp)}`);
      if (!r.ok) throw new Error();
      setChain(await r.json());
    } catch { setChainError("Failed to load chain for this expiry."); }
    finally { setLoadingChain(false); }
  };

  // ── Filtered/sorted scanner data ──
  const filtered = stocks
    .filter(s => filter === "ALL" || s.signal === filter)
    .filter(s => s.symbol.includes(searchQ.toUpperCase()))
    .sort((a, b) => sortBy === "score" ? b.score - a.score : sortBy === "iv" ? a.iv - b.iv : b.vol_spike - a.vol_spike);

  // ── Styles ──
  const S = {
    app: { minHeight: '100vh', background: '#080c10', color: '#c9d4e0', fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 13 },
    header: { borderBottom: '1px solid #1e2d40', padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 16, background: '#0a0f15' },
    title: { fontFamily: FONT, fontSize: 18, fontWeight: 700, color: '#00ff88', letterSpacing: '0.05em' },
    nav: { display: 'flex', gap: 0, borderBottom: '1px solid #1e2d40', background: '#0a0f15', padding: '0 20px' },
    navBtn: (a) => ({ padding: '10px 18px', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: FONT, letterSpacing: '0.05em', border: 'none', background: 'none', color: a ? '#00ff88' : '#4a6278', borderBottom: a ? '2px solid #00ff88' : '2px solid transparent', transition: 'all 0.2s' }),
    main: { padding: 20 },
    toolbar: { display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' },
    input: { background: '#0d1520', border: '1px solid #1e3a5f', color: '#c9d4e0', padding: '6px 12px', borderRadius: 4, fontSize: 12, fontFamily: FONT, outline: 'none' },
    btn: (a, color = '#00ff88') => ({ padding: '5px 12px', borderRadius: 4, border: `1px solid ${a ? color : '#1e3a5f'}`, background: a ? color + '22' : 'transparent', color: a ? color : '#4a6278', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: FONT, transition: 'all 0.2s' }),
    table: { width: '100%', borderCollapse: 'collapse' },
    th: { padding: '8px 12px', textAlign: 'left', fontSize: 10, color: '#4a6278', fontFamily: FONT, fontWeight: 600, letterSpacing: '0.1em', borderBottom: '1px solid #1e2d40', textTransform: 'uppercase' },
    td: { padding: '9px 12px', borderBottom: '1px solid #0f1a25', fontSize: 12, fontFamily: FONT },
    card: { background: '#0d1520', border: '1px solid #1e2d40', borderRadius: 8, padding: 16 },
    scanBtn: (dis) => ({ padding: '7px 18px', background: dis ? '#1e2d40' : '#00ff8822', border: `1px solid ${dis ? '#1e2d40' : '#00ff88'}`, color: dis ? '#4a6278' : '#00ff88', borderRadius: 4, cursor: dis ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: 700, fontFamily: FONT, letterSpacing: '0.05em', transition: 'all 0.2s', display: 'flex', alignItems: 'center', gap: 8 }),
  };

  // ── Backend offline banner ──
  if (backendOk === false) {
    return (
      <div style={S.app}>
        <style>{css}</style>
        <div style={S.header}>
          <div style={S.title}>◈ NSE F&O SCANNER</div>
        </div>
        <div style={{ padding: 40, maxWidth: 600, margin: '0 auto' }}>
          <div style={{ background: '#100a0a', border: '1px solid #ff4d6d44', borderRadius: 12, padding: 32 }}>
            <div style={{ fontFamily: FONT, fontSize: 16, color: '#ff4d6d', marginBottom: 16 }}>⚠ BACKEND NOT RUNNING</div>
            <div style={{ color: '#8899aa', lineHeight: 1.8, marginBottom: 20 }}>
              The Python backend is not running yet. Start it first:
            </div>
            <pre style={{ background: '#080c10', border: '1px solid #1e2d40', padding: 16, borderRadius: 8, fontFamily: FONT, fontSize: 12, color: '#00ff88', overflowX: 'auto' }}>
              {`# 1. Install dependencies
pip install fastapi uvicorn httpx

# 2. Set your token
export INDSTOCKS_TOKEN=your_new_token

# 3. Start the backend
python main.py

# Backend will run at http://localhost:8000`}
            </pre>
            <button onClick={() => { setBackendOk(null); fetch(`${API.replace('/api', '/health')}`).then(r => r.ok ? setBackendOk(true) : setBackendOk(false)).catch(() => setBackendOk(false)); }}
              style={{ marginTop: 16, ...S.scanBtn(false) }}>
              ⟳ CHECK AGAIN
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={S.app}>
      <style>{css}</style>

      {/* Header */}
      <div style={S.header}>
        <div>
          <div style={S.title}>◈ NSE F&amp;O SCANNER</div>
          <div style={{ fontSize: 11, color: '#4a6278', fontFamily: FONT }}>LIVE DATA · INDSTOCKS + NSE · {stocks.length} STOCKS SCANNED</div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          {lastScan && <span style={{ fontSize: 10, color: '#4a6278', fontFamily: FONT }}>LAST SCAN: {lastScan.toLocaleTimeString()}</span>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className="live-dot" style={{ width: 7, height: 7, borderRadius: '50%', background: '#00ff88' }} />
            <span style={{ fontSize: 10, color: '#00ff88', fontFamily: FONT, fontWeight: 700 }}>LIVE</span>
          </div>
          <button style={S.scanBtn(scanning)} onClick={runScan} disabled={scanning}>
            {scanning ? <><Spinner /> SCANNING...</> : '⟳ RESCAN ALL'}
          </button>
        </div>
      </div>

      {/* Nav */}
      <div style={S.nav}>
        {[['scanner', '▦ STOCK SCANNER'], ['chain', '⊞ OPTION CHAIN'], ['picks', '★ TOP PICKS']].map(([id, label]) => (
          <button key={id} style={S.navBtn(tab === id)} onClick={() => setTab(id)}>{label}</button>
        ))}
        {selected && (
          <span style={{ marginLeft: 'auto', alignSelf: 'center', fontSize: 11, color: '#4a6278', fontFamily: FONT }}>
            SELECTED: <span style={{ color: '#00ff88' }}>{selected.symbol}</span> @ ₹{selected.ltp}
          </span>
        )}
      </div>

      <div style={S.main}>

        {/* ── SCANNER TAB ── */}
        {tab === 'scanner' && (
          <div className="slide-in">
            {/* Stats */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
              {[
                { label: 'SCANNED', val: stocks.length, color: '#c9d4e0' },
                { label: 'BULLISH', val: stocks.filter(s => s.signal === 'BULLISH').length, color: '#00ff88' },
                { label: 'BEARISH', val: stocks.filter(s => s.signal === 'BEARISH').length, color: '#ff4d6d' },
                { label: 'NEUTRAL', val: stocks.filter(s => s.signal === 'NEUTRAL').length, color: '#f0c040' },
                { label: 'HIGH (70+)', val: stocks.filter(s => s.score >= 70).length, color: '#00cfff' },
              ].map(st => (
                <div key={st.label} style={{ ...S.card, minWidth: 110, flex: '0 0 auto', padding: '12px 16px' }}>
                  <div style={{ fontSize: 10, color: '#4a6278', fontFamily: FONT, letterSpacing: '0.1em', marginBottom: 4 }}>{st.label}</div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: st.color, fontFamily: FONT }}>{scanning ? '—' : st.val}</div>
                </div>
              ))}
            </div>

            {scanError && <ErrorBox msg={scanError} onRetry={runScan} />}

            {scanning && (
              <div style={{ textAlign: 'center', padding: 60, color: '#4a6278', fontFamily: FONT }}>
                <div style={{ fontSize: 24, marginBottom: 12 }}><Spinner /></div>
                SCANNING {stocks.length > 0 ? 'UPDATING' : 'ALL NSE F&O STOCKS'}...
              </div>
            )}

            {!scanning && !scanError && stocks.length > 0 && (
              <>
                <div style={S.toolbar}>
                  <input style={{ ...S.input, width: 160 }} placeholder="Search symbol..." value={searchQ} onChange={e => setSearchQ(e.target.value)} />
                  {['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL'].map(f => (
                    <button key={f} style={S.btn(filter === f, f === 'BULLISH' ? '#00ff88' : f === 'BEARISH' ? '#ff4d6d' : f === 'NEUTRAL' ? '#f0c040' : '#00cfff')} onClick={() => setFilter(f)}>{f}</button>
                  ))}
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 10, color: '#4a6278', fontFamily: FONT }}>SORT:</span>
                    {[['score', 'SCORE'], ['iv', 'LOW IV'], ['vol_spike', 'VOL SPIKE']].map(([k, l]) => (
                      <button key={k} style={S.btn(sortBy === k)} onClick={() => setSortBy(k)}>{l}</button>
                    ))}
                  </div>
                </div>

                <div style={{ background: '#0a0f15', border: '1px solid #1e2d40', borderRadius: 8, overflow: 'hidden' }}>
                  <table style={S.table}>
                    <thead>
                      <tr style={{ background: '#080c10' }}>
                        {['#', 'SYMBOL', 'LTP', 'CHG%', 'SIGNAL', 'PCR', 'IV%', 'OI CHG%', 'VOL SPIKE', 'SCORE', ''].map(h => (
                          <th key={h} style={S.th}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((s, i) => (
                        <tr key={s.symbol}
                          style={{ cursor: 'pointer', background: hoverRow === s.symbol ? '#0d1825' : 'transparent', transition: 'background 0.15s' }}
                          onMouseEnter={() => setHoverRow(s.symbol)}
                          onMouseLeave={() => setHoverRow(null)}
                          onClick={() => selectStock(s)}
                        >
                          <td style={{ ...S.td, color: '#4a6278', width: 32 }}>{i + 1}</td>
                          <td style={{ ...S.td, color: '#e0eaf5', fontWeight: 700, letterSpacing: '0.05em' }}>{s.symbol}</td>
                          <td style={S.td}>₹{(s.ltp || 0).toLocaleString()}</td>
                          <td style={{ ...S.td, color: clr(s.change_pct) }}>{pct(s.change_pct)}</td>
                          <td style={S.td}><SignalBadge signal={s.signal} /></td>
                          <td style={{ ...S.td, color: s.pcr > 1.3 ? '#00ff88' : s.pcr < 0.8 ? '#ff4d6d' : '#f0c040' }}>{s.pcr}</td>
                          <td style={{ ...S.td, color: s.iv < 25 ? '#00ff88' : s.iv > 50 ? '#ff4d6d' : '#c9d4e0' }}>{s.iv}%</td>
                          <td style={{ ...S.td, color: clr(s.oi_change) }}>{pct(s.oi_change)}</td>
                          <td style={{ ...S.td, color: s.vol_spike > 3 ? '#00cfff' : '#c9d4e0' }}>{s.vol_spike}x</td>
                          <td style={S.td}><ScoreBar score={s.score} /></td>
                          <td style={{ ...S.td, color: '#00ff88', fontSize: 11 }}>VIEW →</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        {/* ── CHAIN TAB ── */}
        {tab === 'chain' && (
          <div className="slide-in">
            {!selected ? (
              <div style={{ textAlign: 'center', padding: 60, color: '#4a6278', fontFamily: FONT }}>← SELECT A STOCK FROM THE SCANNER</div>
            ) : loadingChain ? (
              <div style={{ textAlign: 'center', padding: 60, color: '#4a6278', fontFamily: FONT }}><Spinner /> &nbsp;LOADING CHAIN FOR {selected.symbol}...</div>
            ) : chainError ? (
              <ErrorBox msg={chainError} onRetry={() => selectStock(selected)} />
            ) : chain && (
              <>
                {/* Stock bar */}
                <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                  <div style={{ fontFamily: FONT, fontSize: 20, fontWeight: 700, color: '#e0eaf5' }}>{chain.symbol}</div>
                  <div style={{ fontFamily: FONT, fontSize: 18, color: '#00ff88' }}>₹{chain.spot}</div>
                  <SignalBadge signal={selected.signal} />
                  <span style={{ fontSize: 11, color: '#4a6278', fontFamily: FONT }}>PCR: <span style={{ color: '#c9d4e0' }}>{selected.pcr}</span></span>
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {(chain.expiries || []).map(e => (
                      <button key={e} style={S.btn(expiry === e)} onClick={() => changeExpiry(e)}>{e}</button>
                    ))}
                  </div>
                </div>

                <div style={{ background: '#0a0f15', border: '1px solid #1e2d40', borderRadius: 8, overflow: 'auto' }}>
                  <table style={{ ...S.table, minWidth: 950 }}>
                    <thead>
                      <tr style={{ background: '#080c10' }}>
                        <th style={{ ...S.th, color: '#00ff8888' }} colSpan={5}>CALLS (CE)</th>
                        <th style={{ ...S.th, textAlign: 'center', color: '#f0c040' }}>STRIKE</th>
                        <th style={{ ...S.th, color: '#ff4d6d88' }} colSpan={5}>PUTS (PE)</th>
                      </tr>
                      <tr style={{ background: '#0a0f15' }}>
                        {['SCORE', 'OI CHG%', 'VOLUME', 'IV%', 'LTP', '', 'LTP', 'IV%', 'VOLUME', 'OI CHG%', 'SCORE'].map((h, i) => (
                          <th key={i} style={{ ...S.th, textAlign: i === 5 ? 'center' : 'left' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(chain.strikes || []).map(row => (
                        <tr key={row.strike}
                          style={{ background: row.isATM ? '#0d1e10' : 'transparent', transition: 'background 0.15s' }}
                          onMouseEnter={e => e.currentTarget.style.background = row.isATM ? '#0d1e10' : '#0d1520'}
                          onMouseLeave={e => e.currentTarget.style.background = row.isATM ? '#0d1e10' : 'transparent'}
                        >
                          <td style={S.td}><ScoreBar score={row.CE.score} /></td>
                          <td style={{ ...S.td, color: clr(row.CE.oi_chg_pct) }}>{pct(row.CE.oi_chg_pct)}</td>
                          <td style={{ ...S.td, color: '#8899aa' }}>{fmt(row.CE.volume)}</td>
                          <td style={{ ...S.td, color: row.CE.iv < 25 ? '#00ff88' : '#c9d4e0' }}>{row.CE.iv}%</td>
                          <td style={{ ...S.td, color: '#00ff88', fontWeight: 700 }}>₹{row.CE.ltp}</td>
                          <td style={{ ...S.td, textAlign: 'center', fontWeight: 700, color: row.isATM ? '#f0c040' : '#8899aa', background: row.isATM ? '#1a1500' : 'transparent', padding: '9px 20px' }}>
                            {row.strike}{row.isATM && <span style={{ marginLeft: 4, fontSize: 9, color: '#f0c040' }}>ATM</span>}
                          </td>
                          <td style={{ ...S.td, color: '#ff4d6d', fontWeight: 700 }}>₹{row.PE.ltp}</td>
                          <td style={{ ...S.td, color: row.PE.iv < 25 ? '#00ff88' : '#c9d4e0' }}>{row.PE.iv}%</td>
                          <td style={{ ...S.td, color: '#8899aa' }}>{fmt(row.PE.volume)}</td>
                          <td style={{ ...S.td, color: clr(row.PE.oi_chg_pct) }}>{pct(row.PE.oi_chg_pct)}</td>
                          <td style={S.td}><ScoreBar score={row.PE.score} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        {/* ── TOP PICKS TAB ── */}
        {tab === 'picks' && (
          <div className="slide-in">
            {!chain ? (
              <div style={{ textAlign: 'center', padding: 60, color: '#4a6278', fontFamily: FONT }}>← SELECT A STOCK FROM THE SCANNER FIRST</div>
            ) : (
              <>
                <div style={{ marginBottom: 20, fontFamily: FONT }}>
                  <span style={{ color: '#4a6278', fontSize: 12 }}>TOP PICKS FOR </span>
                  <span style={{ color: '#00ff88', fontSize: 16, fontWeight: 700 }}>{chain.symbol}</span>
                  <span style={{ color: '#4a6278', fontSize: 12 }}> · {chain.expiry}</span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px,1fr))', gap: 16, marginBottom: 28 }}>
                  {(chain.top_picks || []).map((pick, i) => (
                    <div key={i} className={i === 0 ? 'best-card' : ''} style={{ background: '#0d1520', border: `1px solid ${pick.type === 'CE' ? '#00ff8844' : '#ff4d6d44'}`, borderRadius: 10, padding: 20, position: 'relative' }}>
                      {i === 0 && <div style={{ position: 'absolute', top: 10, right: 10, background: '#f0c04022', border: '1px solid #f0c040', color: '#f0c040', fontSize: 9, fontFamily: FONT, padding: '2px 8px', borderRadius: 3, fontWeight: 700 }}>★ BEST PICK</div>}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                        <div style={{ fontSize: 20, fontWeight: 700, fontFamily: FONT, color: '#e0eaf5' }}>{chain.symbol}</div>
                        <div style={{ fontSize: 13, fontWeight: 700, fontFamily: FONT, color: '#8899aa' }}>{pick.strike}</div>
                        <Badge label={pick.type} color={pick.type === 'CE' ? '#00ff88' : '#ff4d6d'} />
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                        {[
                          ['LTP', `₹${pick.ltp}`, pick.type === 'CE' ? '#00ff88' : '#ff4d6d'],
                          ['IV', `${pick.iv}%`, pick.iv < 25 ? '#00ff88' : pick.iv > 50 ? '#ff4d6d' : '#c9d4e0'],
                          ['OI CHG', pct(pick.oi_chg_pct ?? pick.oi_chg ?? 0), clr(pick.oi_chg_pct ?? pick.oi_chg ?? 0)],
                          ['VOLUME', fmt(pick.volume), '#00cfff'],
                        ].map(([l, v, c]) => (
                          <div key={l}>
                            <div style={{ fontSize: 9, color: '#4a6278', fontFamily: FONT, letterSpacing: '0.1em', marginBottom: 2 }}>{l}</div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: c, fontFamily: FONT }}>{v}</div>
                          </div>
                        ))}
                      </div>
                      <div style={{ marginTop: 16 }}>
                        <div style={{ fontSize: 9, color: '#4a6278', fontFamily: FONT, marginBottom: 6, letterSpacing: '0.1em' }}>SIGNAL SCORE</div>
                        <ScoreBar score={pick.score} />
                      </div>
                    </div>
                  ))}
                </div>

                {/* Legend */}
                <div style={{ ...S.card, padding: 16 }}>
                  <div style={{ fontFamily: FONT, fontSize: 10, color: '#4a6278', letterSpacing: '0.1em', marginBottom: 12 }}>SCORE METHODOLOGY</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 10 }}>
                    {[
                      ['OI Change %', 'Rising OI with price = trend confirmation'],
                      ['Volume', 'Spike in volume = institutional activity'],
                      ['Low IV', 'Cheaper options = better risk/reward ratio'],
                      ['ATM Proximity', 'Near-ATM = best delta, less theta decay'],
                    ].map(([t, d]) => (
                      <div key={t} style={{ padding: '8px 12px', background: '#080c10', borderRadius: 6, borderLeft: '2px solid #1e3a5f' }}>
                        <div style={{ fontFamily: FONT, fontSize: 11, fontWeight: 600, color: '#c9d4e0', marginBottom: 2 }}>{t}</div>
                        <div style={{ fontSize: 11, color: '#4a6278' }}>{d}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

      </div>

      {/* Footer */}
      <div style={{ borderTop: '1px solid #1e2d40', padding: '10px 20px', display: 'flex', justifyContent: 'space-between', background: '#0a0f15' }}>
        <span style={{ fontFamily: FONT, fontSize: 10, color: '#2a3d50' }}>NSE F&O SCANNER · LIVE · INDSTOCKS API + NSE SCRAPER</span>
        <span style={{ fontFamily: FONT, fontSize: 10, color: '#2a3d50' }}>⚠ FOR EDUCATIONAL USE ONLY · NOT FINANCIAL ADVICE</span>
      </div>
    </div>
  );
}
