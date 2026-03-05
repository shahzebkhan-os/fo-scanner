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
  const [expiry, setExpiry] = useState("");

  // Backtester states
  const [btData, setBtData] = useState(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btForm, setBtForm] = useState({ mode: 'db', tp: 40, sl: 20, score: 75 });

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

  // Paper Trading State
  const [paperStats, setPaperStats] = useState(null);
  const [activeTrades, setActiveTrades] = useState([]);
  const [closedTrades, setClosedTrades] = useState([]);
  const [trackedPicks, setTrackedPicks] = useState([]);
  const [loadingPaper, setLoadingPaper] = useState(false);
  const [sortConfig, setSortConfig] = useState({ key: 'entry_time', direction: 'desc' });

  const sortedTrackedPicks = React.useMemo(() => {
    let items = [...trackedPicks];
    if (sortConfig !== null) {
      items.sort((a, b) => {
        let aVal = a[sortConfig.key];
        let bVal = b[sortConfig.key];
        if (sortConfig.key === 'pnlPct') {
          aVal = (((a.current_price || a.entry_price) - a.entry_price) / a.entry_price) * 100;
          bVal = (((b.current_price || b.entry_price) - b.entry_price) / b.entry_price) * 100;
        } else if (sortConfig.key === 'buy_total') {
          aVal = a.entry_price * (a.lot_size || 0);
          bVal = b.entry_price * (b.lot_size || 0);
        } else if (sortConfig.key === 'ltp_total') {
          aVal = (a.current_price || a.entry_price) * (a.lot_size || 0);
          bVal = (b.current_price || b.entry_price) * (b.lot_size || 0);
        }
        if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return items;
  }, [trackedPicks, sortConfig]);

  const requestSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
    setSortConfig({ key, direction });
  };

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

  // ── Load Paper Trades ──
  const fetchPaperTrades = async () => {
    setLoadingPaper(true);
    try {
      const [st, act, hist, trk] = await Promise.all([
        fetch(`${API}/paper-trades/stats`).then(r => r.json()),
        fetch(`${API}/paper-trades/active`).then(r => r.json()),
        fetch(`${API}/paper-trades/history`).then(r => r.json()),
        fetch(`${API}/tracked-picks`).then(r => r.json()),
      ]);
      setPaperStats(st);
      setActiveTrades(act || []);
      setClosedTrades(hist || []);
      setTrackedPicks(trk?.data || []);
    } catch (e) {
      console.error("Failed to fetch paper trades", e);
    } finally {
      setLoadingPaper(false);
    }
  };

  const trackPick = async (symbol, pick) => {
    try {
      const r = await fetch(`${API}/track-pick`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, type: pick.type, strike: pick.strike, entry_price: pick.ltp, score: pick.score })
      });
      const data = await r.json();
      if (data.status === "success") {
        fetchPaperTrades();
      }
    } catch (e) {
      console.error("Failed to track this Option.");
    }
  };

  const trackAllPicks = async () => {
    let count = 0;
    const targets = [];
    stocks.forEach(s => {
      (s.top_picks || []).forEach(p => {
        if (p.score >= 60) targets.push({ symbol: s.symbol, pick: p });
      });
    });

    if (targets.length === 0) return;

    for (const t of targets) {
      try {
        const r = await fetch(`${API}/track-pick`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol: t.symbol, type: t.pick.type, strike: t.pick.strike, entry_price: t.pick.ltp, score: t.pick.score })
        });
        const data = await r.json();
        if (data.status === "success") count++;
      } catch (e) { }
    }
    fetchPaperTrades();
  };

  const untrackPick = async (tradeId) => {
    try {
      const r = await fetch(`${API}/track-pick/${tradeId}`, { method: "DELETE" });
      const data = await r.json();
      if (data.status === "success") fetchPaperTrades();
    } catch (e) {
      console.error("Failed to communicate with server.");
    }
  };

  const untrackAllPicks = async () => {
    if (!confirm("Are you sure you want to stop tracking ALL options?")) return;
    try {
      const r = await fetch(`${API}/tracked-picks`, { method: "DELETE" });
      const data = await r.json();
      if (data.status === "success") fetchPaperTrades();
    } catch (e) {
      console.error("Failed to communicate with server.");
    }
  };

  const runBacktest = async () => {
    setBtLoading(true);
    setBtData(null);
    try {
      const resp = await fetch(`${API}/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: btForm.mode, tp: Number(btForm.tp), sl: Number(btForm.sl), score: Number(btForm.score) })
      });
      if (!resp.ok) throw new Error("Backtest failed to run");
      setBtData(await resp.json());
    } catch (e) {
      console.error(e);
      alert("Error running backtest: " + e.message);
    } finally {
      setBtLoading(false);
    }
  };

  useEffect(() => {
    if (tab === 'paper') fetchPaperTrades();
  }, [tab]);

  // ── Download All Top Picks (Scanner) ──
  const downloadAllPicks = () => {
    if (!stocks || stocks.length === 0) return;
    const headers = ['Symbol', 'Underlying_LTP', 'Signal', 'Score', 'Pick_1_Type', 'Pick_1_Strike', 'Pick_1_LTP', 'Pick_2_Type', 'Pick_2_Strike', 'Pick_2_LTP'];
    const rows = stocks.map(s => {
      const p1 = s.top_picks && s.top_picks[0] ? s.top_picks[0] : {};
      const p2 = s.top_picks && s.top_picks[1] ? s.top_picks[1] : {};
      return [
        s.symbol,
        s.ltp,
        s.signal,
        s.score,
        p1.type || '',
        p1.strike || '',
        p1.ltp || '',
        p2.type || '',
        p2.strike || '',
        p2.ltp || ''
      ];
    });
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `all_top_picks.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // ── Download Top Picks (Tab) ──
  const downloadPicks = () => {
    if (!chain || !chain.top_picks || !selected) return;
    const headers = ['Symbol', 'Expiry', 'Strike', 'Type', 'Option_LTP', 'IV_Pct', 'OI_Chg_Pct', 'Volume', 'Score', 'Underlying_LTP'];
    const rows = chain.top_picks.map(p => [
      chain.symbol,
      chain.expiry,
      p.strike,
      p.type,
      p.ltp,
      p.iv,
      (p.oi_chg_pct ?? p.oi_chg ?? 0).toFixed(2),
      p.volume,
      p.score,
      selected.ltp
    ]);
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `${chain.symbol}_top_picks_ltp_${selected.ltp}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

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
        {[
          { id: 'scanner', label: '▦ STOCK SCANNER' },
          { id: 'chain', label: '⊞ OPTION CHAIN' },
          { id: 'picks', label: '★ TOP PICKS' },
          { id: 'all_picks', label: '★★ ALL PICKS' },
          { id: 'paper', label: '📈 PAPER TRADING' },
          { id: 'backtester', label: '🧪 BACKTESTER' }
        ].map(({ id, label }) => (
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
                        {['#', 'SYMBOL', 'LTP', 'CHG%', 'SIGNAL', 'PCR', 'IV%', 'OI CHG%', 'VOL SPIKE', 'SCORE', 'TOP PICKS', ''].map(h => (
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
                          <td style={S.td}>
                            <div style={{ display: 'flex', gap: 4, flexDirection: 'column' }}>
                              {(s.top_picks || []).map((p, j) => (
                                <div key={j} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 10 }}>
                                  <Badge label={p.type} color={p.type === 'CE' ? '#00ff88' : '#ff4d6d'} />
                                  <span style={{ color: '#f0c040', fontFamily: FONT, fontWeight: 700 }}>{p.strike}</span>
                                  <span style={{ color: '#c9d4e0', fontFamily: FONT }}>₹{p.ltp}</span>
                                </div>
                              ))}
                            </div>
                          </td>
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
                <div style={{ marginBottom: 20, fontFamily: FONT, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{ color: '#4a6278', fontSize: 12 }}>TOP PICKS FOR </span>
                    <span style={{ color: '#00ff88', fontSize: 16, fontWeight: 700 }}>{chain.symbol}</span>
                    <span style={{ color: '#4a6278', fontSize: 12 }}> · {chain.expiry}</span>
                  </div>
                  <button onClick={downloadPicks} style={{ ...S.btn(true), padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
                    ↓ DOWNLOAD CSV
                  </button>
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
                        {pick.score >= 60 && (
                          <button onClick={() => trackPick(chain.symbol, pick)} style={{ ...S.btn(true), width: '100%', marginTop: 12, padding: 8 }}>
                            ★ TRACK LIVE CHG%
                          </button>
                        )}
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
                      <div key={t} style={{ padding: '8px 12px', background: '#080c10', borderLeft: '2px solid #1e3a5f' }}>
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

        {/* ── ALL TOP PICKS TAB ── */}
        {tab === 'all_picks' && (
          <div className="slide-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div style={{ fontFamily: FONT }}>
                <span style={{ color: '#4a6278', fontSize: 12 }}>ALL TOP PICKS ACROSS </span>
                <span style={{ color: '#00ff88', fontSize: 16, fontWeight: 700 }}>{stocks.length}</span>
                <span style={{ color: '#4a6278', fontSize: 12 }}> SCANNED STOCKS</span>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <button onClick={trackAllPicks} style={{ ...S.btn(true, '#00cfff'), padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}>
                  ★ TRACK ALL &gt;60 SCORE
                </button>
                <button onClick={downloadAllPicks} style={{ ...S.btn(true), padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
                  ↓ DOWNLOAD ALL PICKS CSV
                </button>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
              {stocks.filter(s => s.top_picks && s.top_picks.length > 0).map(s => (
                <div key={s.symbol} style={{ background: '#0a0f15', border: '1px solid #1e2d40', borderRadius: 8, padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ color: '#e0eaf5', fontSize: 16, fontWeight: 700, fontFamily: FONT }}>{s.symbol}</span>
                      <span style={{ color: '#8899aa', fontSize: 12, fontFamily: FONT }}>₹{s.ltp}</span>
                    </div>
                    <SignalBadge signal={s.signal} />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {s.top_picks.map((p, j) => (
                      <div key={j} style={{ background: '#080c10', border: `1px solid ${p.type === 'CE' ? '#00ff8844' : '#ff4d6d44'}`, borderRadius: 6, padding: '10px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Badge label={p.type} color={p.type === 'CE' ? '#00ff88' : '#ff4d6d'} />
                          <span style={{ color: '#f0c040', fontFamily: FONT, fontWeight: 700, fontSize: 14 }}>{p.strike}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 9, color: '#4a6278', fontFamily: FONT }}>LTP</div>
                            <div style={{ color: '#c9d4e0', fontFamily: FONT, fontWeight: 700, fontSize: 12 }}>₹{p.ltp}</div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 9, color: '#4a6278', fontFamily: FONT }}>SCORE</div>
                            <div style={{ color: p.score >= 70 ? '#00ff88' : p.score >= 45 ? '#f0c040' : '#ff4d6d', fontFamily: FONT, fontWeight: 700, fontSize: 13 }}>{p.score}</div>
                            {p.score >= 60 && (
                              <button onClick={() => trackPick(s.symbol, p)} style={{ ...S.btn(true, '#00cfff'), fontSize: 9, padding: '2px 6px', marginTop: 4 }}>
                                TRACK
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <button onClick={() => selectStock(s)} style={{ marginTop: 16, width: '100%', ...S.btn(false), padding: '8px', border: '1px solid #1e2d40' }}>
                    VIEW OPTION CHAIN →
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── PAPER TRADING TAB ── */}
        {tab === 'paper' && (
          <div className="slide-in">
            {loadingPaper && !paperStats ? (
              <div style={{ textAlign: 'center', padding: 60 }}><Spinner /></div>
            ) : (
              <>
                <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                  {[
                    { label: 'CLOSED TRADES', val: paperStats?.total_closed || 0, color: '#c9d4e0' },
                    { label: 'WIN RATE', val: `${paperStats?.win_rate_pct || 0}%`, color: (paperStats?.win_rate_pct || 0) >= 50 ? '#00ff88' : '#ff4d6d' },
                    { label: 'NET PnL', val: `${(paperStats?.total_pnl_pct || 0) > 0 ? '+' : ''}${paperStats?.total_pnl_pct || 0}%`, color: (paperStats?.total_pnl_pct || 0) >= 0 ? '#00ff88' : '#ff4d6d' },
                    { label: 'ACTIVE TRADES', val: activeTrades.length, color: '#f0c040' },
                  ].map(st => (
                    <div key={st.label} style={{ ...S.card, minWidth: 140, flex: '1 1 auto', padding: '16px' }}>
                      <div style={{ fontSize: 11, color: '#4a6278', fontFamily: FONT, letterSpacing: '0.1em', marginBottom: 8 }}>{st.label}</div>
                      <div style={{ fontSize: 28, fontWeight: 700, color: st.color, fontFamily: FONT }}>{st.val}</div>
                    </div>
                  ))}
                </div>

                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontFamily: FONT, color: '#00cfff', fontSize: 14, fontWeight: 700, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
                    ★ LIVE TRACKED PICKS ({trackedPicks.length})
                    <button onClick={fetchPaperTrades} style={{ ...S.btn(), padding: '2px 8px' }}>⟳ REFRESH</button>
                    {trackedPicks.length > 0 && (
                      <button onClick={untrackAllPicks} style={{ ...S.btn(false), padding: '2px 8px', borderColor: '#ff4d6d', color: '#ff4d6d' }}>
                        EXIT ALL TRACKED
                      </button>
                    )}
                  </div>
                  <div style={{ background: '#0a0f15', border: '1px solid #1e2d40', borderRadius: 8, overflow: 'hidden' }}>
                    <table style={S.table}>
                      <thead>
                        <tr style={{ background: '#080c10' }}>
                          <th onClick={() => requestSort('entry_time')} style={{ ...S.th, cursor: 'pointer' }}>TRACE {sortConfig.key === 'entry_time' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('symbol')} style={{ ...S.th, cursor: 'pointer' }}>SYMBOL {sortConfig.key === 'symbol' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('score')} style={{ ...S.th, cursor: 'pointer' }}>SCORE {sortConfig.key === 'score' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('stock_price')} style={{ ...S.th, cursor: 'pointer' }}>SPOT {sortConfig.key === 'stock_price' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('lot_size')} style={{ ...S.th, cursor: 'pointer' }}>LOT QTY {sortConfig.key === 'lot_size' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('type')} style={{ ...S.th, cursor: 'pointer' }}>TYPE {sortConfig.key === 'type' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('strike')} style={{ ...S.th, cursor: 'pointer' }}>STRIKE {sortConfig.key === 'strike' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('buy_total')} style={{ ...S.th, cursor: 'pointer' }}>BUY TOTAL {sortConfig.key === 'buy_total' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('ltp_total')} style={{ ...S.th, cursor: 'pointer' }}>CURRENT TOTAL {sortConfig.key === 'ltp_total' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th onClick={() => requestSort('pnlPct')} style={{ ...S.th, cursor: 'pointer' }}>MANUAL PnL% {sortConfig.key === 'pnlPct' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : ''}</th>
                          <th style={S.th}>ACTION</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedTrackedPicks.length === 0 ? (
                          <tr><td colSpan={12} style={{ ...S.td, textAlign: 'center', color: '#4a6278' }}>No active tracked picks. Search &gt;60 score Top Picks to add.</td></tr>
                        ) : sortedTrackedPicks.map(t => {
                          const ltp = t.current_price || t.entry_price;
                          const pnlPct = ((ltp - t.entry_price) / t.entry_price) * 100;
                          const spot = t.stock_price || 0;
                          const buyTotal = t.entry_price * (t.lot_size || 0);
                          const ltpTotal = ltp * (t.lot_size || 0);
                          return (
                            <tr key={t.id}>
                              <td style={{ ...S.td, color: '#8899aa' }}>{t.entry_time.split('T')[1].substring(0, 5)}</td>
                              <td style={{ ...S.td, color: '#00cfff', fontWeight: 700 }}>{t.symbol}</td>
                              <td style={{ ...S.td }}>
                                <div style={{ display: 'inline-block', padding: '2px 6px', borderRadius: 4, background: t.score >= 70 ? '#00ff8822' : t.score >= 50 ? '#f0c04022' : '#ff4d6d22', color: t.score >= 70 ? '#00ff88' : t.score >= 50 ? '#f0c040' : '#ff4d6d', fontWeight: 700 }}>
                                  {t.score || '-'}
                                </div>
                              </td>
                              <td style={{ ...S.td, color: '#c9d4e0' }}>₹{spot.toFixed(2)}</td>
                              <td style={{ ...S.td, color: '#8899aa' }}>{t.lot_size || '-'}</td>
                              <td style={S.td}><Badge label={t.type} color={t.type === 'CE' ? '#00ff88' : '#ff4d6d'} /></td>
                              <td style={{ ...S.td, color: '#f0c040' }}>{t.strike}</td>
                              <td style={{ ...S.td, color: '#c9d4e0' }}>₹{buyTotal > 0 ? buyTotal.toFixed(2) : t.entry_price.toFixed(2)}</td>
                              <td style={{ ...S.td, color: '#00cfff', fontWeight: 700 }}>₹{ltpTotal > 0 ? ltpTotal.toFixed(2) : ltp.toFixed(2)}</td>
                              <td style={{ ...S.td, color: clr(pnlPct), fontWeight: 700 }}>
                                {pct(pnlPct)} <span style={{ fontSize: '0.85em', opacity: 0.8, marginLeft: 4 }}>({pnlPct >= 0 ? '+' : ''}₹{Math.abs((ltpTotal > 0 ? ltpTotal : ltp) - (buyTotal > 0 ? buyTotal : t.entry_price)).toFixed(2)})</span>
                              </td>
                              <td style={S.td}>
                                <button onClick={() => untrackPick(t.id)} style={{ ...S.btn(false), padding: '4px 8px', fontSize: 10, borderColor: '#ff4d6d', color: '#ff4d6d' }}>
                                  EXIT TRACK
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontFamily: FONT, color: '#e0eaf5', fontSize: 14, fontWeight: 700, marginBottom: 12 }}>
                    ACTIVE DB ALGO TRADES ({activeTrades.length})
                  </div>
                  <div style={{ background: '#0a0f15', border: '1px solid #1e2d40', borderRadius: 8, overflow: 'hidden' }}>
                    <table style={S.table}>
                      <thead>
                        <tr style={{ background: '#080c10' }}>
                          {['DATE', 'SYMBOL', 'TYPE', 'STRIKE', 'ENTRY PRICE', 'LTP', 'PnL %'].map(h => <th key={h} style={S.th}>{h}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {activeTrades.length === 0 ? (
                          <tr><td colSpan={7} style={{ ...S.td, textAlign: 'center', color: '#4a6278' }}>No active trades currently open.</td></tr>
                        ) : activeTrades.map(t => {
                          const ltp = t.current_price || t.entry_price;
                          const pnlPct = ((ltp - t.entry_price) / t.entry_price) * 100;
                          return (
                            <tr key={t.id}>
                              <td style={{ ...S.td, color: '#8899aa' }}>{t.entry_time.split('T')[1].substring(0, 5)}</td>
                              <td style={{ ...S.td, color: '#e0eaf5', fontWeight: 700 }}>{t.symbol}</td>
                              <td style={S.td}><Badge label={t.type} color={t.type === 'CE' ? '#00ff88' : '#ff4d6d'} /></td>
                              <td style={{ ...S.td, color: '#f0c040' }}>{t.strike}</td>
                              <td style={{ ...S.td, color: '#c9d4e0' }}>₹{t.entry_price}</td>
                              <td style={{ ...S.td, color: '#00ff88', fontWeight: 700 }}>₹{ltp.toFixed(2)}</td>
                              <td style={{ ...S.td, color: clr(pnlPct), fontWeight: 700 }}>{pct(pnlPct)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <div style={{ fontFamily: FONT, color: '#e0eaf5', fontSize: 14, fontWeight: 700, marginBottom: 12 }}>TRADE HISTORY</div>
                  <div style={{ background: '#0a0f15', border: '1px solid #1e2d40', borderRadius: 8, overflow: 'auto', maxHeight: 400 }}>
                    <table style={S.table}>
                      <thead>
                        <tr style={{ background: '#080c10', position: 'sticky', top: 0 }}>
                          {['DATE', 'SYMBOL', 'TYPE', 'STRIKE', 'ENTRY', 'EXIT', 'NET PnL', 'PnL %', 'REASON'].map(h => <th key={h} style={S.th}>{h}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {closedTrades.length === 0 ? (
                          <tr><td colSpan={9} style={{ ...S.td, textAlign: 'center', color: '#4a6278' }}>No completed trades yet.</td></tr>
                        ) : closedTrades.map(t => (
                          <tr key={t.id}>
                            <td style={{ ...S.td, color: '#8899aa' }}>{t.trade_date}</td>
                            <td style={{ ...S.td, color: '#e0eaf5', fontWeight: 700 }}>{t.symbol}</td>
                            <td style={S.td}><Badge label={t.type} color={t.type === 'CE' ? '#00ff88' : '#ff4d6d'} /></td>
                            <td style={{ ...S.td, color: '#f0c040' }}>{t.strike}</td>
                            <td style={{ ...S.td, color: '#8899aa' }}>₹{t.entry_price}</td>
                            <td style={{ ...S.td, color: '#c9d4e0' }}>₹{t.exit_price}</td>
                            <td style={{ ...S.td, color: clr(t.pnl_abs), fontWeight: 700 }}>₹{t.pnl_abs?.toFixed(2) || 0}</td>
                            <td style={{ ...S.td, color: clr(t.pnl_pct) }}>{pct(t.pnl_pct)}</td>
                            <td style={{ ...S.td, color: '#4a6278', fontSize: 10 }}>{t.exit_reason || t.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ── BACKTESTER TAB ── */}
        {tab === 'backtester' && (
          <div className="slide-in">
            <div style={{ background: '#0a0f15', border: '1px solid #1e2d40', borderRadius: 8, padding: 24, marginBottom: 24 }}>
              <h2 style={{ fontFamily: FONT, color: '#00ff88', marginBottom: 16 }}>Strategy Simulator</h2>
              <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'center' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <label style={{ color: '#8899aa', fontSize: 12, fontFamily: FONT }}>TEST MODE</label>
                  <select
                    value={btForm.mode} onChange={e => setBtForm({ ...btForm, mode: e.target.value })}
                    style={{ background: '#0d131a', color: '#fff', border: '1px solid #1e2d40', padding: '8px 12px', borderRadius: 4, fontFamily: FONT, width: 220 }}
                  >
                    <option value="db">Replay Past Paper Trades</option>
                    <option value="live">Scan Now & Test (Top 10)</option>
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <label style={{ color: '#00ff88', fontSize: 12, fontFamily: FONT }}>TAKE PROFIT %</label>
                  <input type="number" value={btForm.tp} onChange={e => setBtForm({ ...btForm, tp: e.target.value })} style={{ background: '#0d131a', color: '#00ff88', border: '1px solid #1e2d40', padding: '8px 12px', borderRadius: 4, fontFamily: FONT, width: 100 }} />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <label style={{ color: '#ff4d6d', fontSize: 12, fontFamily: FONT }}>STOP LOSS %</label>
                  <input type="number" value={btForm.sl} onChange={e => setBtForm({ ...btForm, sl: e.target.value })} style={{ background: '#0d131a', color: '#ff4d6d', border: '1px solid #1e2d40', padding: '8px 12px', borderRadius: 4, fontFamily: FONT, width: 100 }} />
                </div>

                {btForm.mode === 'live' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <label style={{ color: '#f0c040', fontSize: 12, fontFamily: FONT }}>MIN SCORE (0-100)</label>
                    <input type="number" value={btForm.score} onChange={e => setBtForm({ ...btForm, score: e.target.value })} style={{ background: '#0d131a', color: '#f0c040', border: '1px solid #1e2d40', padding: '8px 12px', borderRadius: 4, fontFamily: FONT, width: 100 }} />
                  </div>
                )}

                <button onClick={runBacktest} disabled={btLoading} style={{ ...S.btn('#2196f3'), height: 42, padding: '0 24px', alignSelf: 'flex-end', opacity: btLoading ? 0.5 : 1 }}>
                  {btLoading ? <Spinner /> : '▶ RUN BACKTEST'}
                </button>
              </div>
            </div>

            {btData && btData.trades && btData.trades.length === 0 && (
              <div style={{ ...S.card, padding: 32, textAlign: 'center', color: '#8899aa', fontFamily: FONT, marginTop: 24 }}>
                <span style={{ fontSize: 24, display: 'block', marginBottom: 12 }}>📭</span>
                No historical trades matched these criteria for the simulation.
              </div>
            )}

            {btData && btData.trades && btData.trades.length > 0 && btData.stats && (
              <div className="slide-in">
                {/* Metrics Row */}
                <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                  {[
                    { label: 'TOTAL TRADES', val: btData.stats.total_trades, color: '#c9d4e0' },
                    { label: 'WIN RATE', val: `${btData.stats.win_rate_pct}%`, color: btData.stats.win_rate_pct >= 50 ? '#00ff88' : '#ff4d6d' },
                    { label: 'NET RETURN', val: `${pct(btData.stats.total_return_pct)}`, color: btData.stats.total_return_pct >= 0 ? '#00ff88' : '#ff4d6d' },
                    { label: 'PROFIT FACTOR', val: btData.stats.profit_factor, color: btData.stats.profit_factor > 1.2 ? '#00ff88' : '#e0eaf5' },
                  ].map(st => (
                    <div key={st.label} style={{ ...S.card, minWidth: 140, flex: '1 1 auto', padding: '16px' }}>
                      <div style={{ fontSize: 11, color: '#4a6278', fontFamily: FONT, letterSpacing: '0.1em', marginBottom: 8 }}>{st.label}</div>
                      <div style={{ fontSize: 28, fontWeight: 700, color: st.color, fontFamily: FONT }}>{st.val}</div>
                    </div>
                  ))}
                </div>

                {/* Tables Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 300px', gap: 20 }}>
                  <div style={{ background: '#0a0f15', border: '1px solid #1e2d40', borderRadius: 8, overflow: 'hidden' }}>
                    <div style={{ padding: '12px 16px', background: '#080c10', borderBottom: '1px solid #1e2d40', fontFamily: FONT, color: '#e0eaf5', fontSize: 13, fontWeight: 700 }}>
                      SIMULATED TRADES
                    </div>
                    <div style={{ maxHeight: 500, overflowY: 'auto' }}>
                      <table style={{ ...S.table, margin: 0 }}>
                        <thead style={{ position: 'sticky', top: 0, background: '#080c10', zIndex: 1 }}>
                          <tr>
                            {['SYMBOL', 'STRIKE', 'ENTRY', 'EXIT', 'PnL %', 'REASON'].map(h => <th key={h} style={S.th}>{h}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {btData.trades.map((t, i) => (
                            <tr key={i} style={{ background: i % 2 === 0 ? '#0a0f15' : '#0c1219' }}>
                              <td style={{ ...S.td, color: '#e0eaf5', fontWeight: 600 }}>{t.symbol} <span style={{ color: t.type === 'CE' ? '#00ff88' : '#ff4d6d' }}>{t.type}</span></td>
                              <td style={{ ...S.td, color: '#f0c040' }}>{t.strike}</td>
                              <td style={{ ...S.td, color: '#8899aa' }}>₹{t.entry_price}</td>
                              <td style={{ ...S.td, color: '#c9d4e0' }}>₹{t.exit_price}</td>
                              <td style={{ ...S.td, color: clr(t.pnl_pct), fontWeight: 700 }}>{pct(t.pnl_pct)}</td>
                              <td style={{ ...S.td, color: '#4a6278', fontSize: 10 }}>{t.exit_reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Exit Breakdown Sidebar */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    <div style={{ ...S.card, padding: 16 }}>
                      <h4 style={{ fontFamily: FONT, color: '#e0eaf5', fontSize: 12, marginBottom: 16 }}>EXIT BREAKDOWN</h4>
                      {btData.stats.exit_breakdown.map((ex, i) => (
                        <div key={i} style={{ marginBottom: 12 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontFamily: FONT, color: '#8899aa', marginBottom: 4 }}>
                            <span>{ex.reason}</span>
                            <span>{ex.count} ({ex.pct}%)</span>
                          </div>
                          <div style={{ width: '100%', height: 4, background: '#111820', borderRadius: 2 }}>
                            <div style={{ width: `${ex.pct}%`, height: '100%', background: '#4a6278', borderRadius: 2 }} />
                          </div>
                        </div>
                      ))}
                    </div>

                    <div style={{ ...S.card, padding: 16 }}>
                      <h4 style={{ fontFamily: FONT, color: '#e0eaf5', fontSize: 12, marginBottom: 16 }}>AVERAGES</h4>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontFamily: FONT, color: '#00ff88', marginBottom: 8 }}>
                        <span>Avg Win</span><span>+{btData.stats.avg_win_pct}%</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontFamily: FONT, color: '#ff4d6d', marginBottom: 8 }}>
                        <span>Avg Loss</span><span>{btData.stats.avg_loss_pct}%</span>
                      </div>
                      <div style={{ borderTop: '1px solid #1e2d40', margin: '8px 0' }} />
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontFamily: FONT, color: '#e0eaf5' }}>
                        <span>Best Trade</span><span style={{ color: '#00ff88' }}>+{btData.stats.best_trade_pct}%</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontFamily: FONT, color: '#e0eaf5', marginTop: 8 }}>
                        <span>Worst Trade</span><span style={{ color: '#ff4d6d' }}>{btData.stats.worst_trade_pct}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
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
