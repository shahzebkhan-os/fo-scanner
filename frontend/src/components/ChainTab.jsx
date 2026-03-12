import { useState, useEffect, useCallback } from "react";

const fmt = (n, d = 2) => Number(n || 0).toFixed(d);

async function apiFetch(path, options = {}) {
  const API = "";
  const r = await fetch(API + path, options);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function Loader({ theme }) {
  return (
    <div style={{ textAlign: "center", padding: 40, color: theme.muted }}>
      <div style={{
        fontSize: 24, animation: "spin 1s linear infinite",
        display: "inline-block"
      }}>⟳</div>
      <div style={{ marginTop: 8, fontSize: 12 }}>Loading...</div>
    </div>
  );
}

function Card({ children, theme, style = {} }) {
  return (
    <div style={{
      background: theme.card, border: `1px solid ${theme.border}`,
      borderRadius: 8, padding: 16, ...style
    }}>
      {children}
    </div>
  );
}

function SymbolInput({ value, onChange, onSubmit, theme }) {
  return (
    <form onSubmit={e => { e.preventDefault(); onSubmit(); }}
      style={{ display: "flex", gap: 8 }}>
      <input value={value} onChange={e => onChange(e.target.value.toUpperCase())}
        placeholder="NIFTY / RELIANCE..."
        style={{
          padding: "6px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
          background: theme.bg, color: theme.text, fontFamily: "inherit",
          fontSize: 13, width: 180
        }} />
      <button type="submit"
        style={{
          padding: "6px 14px", borderRadius: 6, background: theme.accent,
          color: "#fff", border: "none", cursor: "pointer", fontFamily: "inherit"
        }}>
        Load
      </button>
    </form>
  );
}

export default function ChainTab({ theme, symbol, setSymbol }) {
  const [data, setData] = useState(null);
  const [expiry, setExpiry] = useState("");
  const [loading, setLoading] = useState(false);
  const [input, setInput] = useState(symbol);

  const load = useCallback(async (sym, exp) => {
    setLoading(true);
    try {
      const url = `/api/chain/${sym}` + (exp ? `?expiry=${encodeURIComponent(exp)}` : "");
      const r = await apiFetch(url);
      setData(r);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => {
    setInput(symbol);
    load(symbol, expiry);
  }, [symbol]);

  const handleSubmit = () => { setSymbol(input); load(input, expiry); };

  if (loading) return <Loader theme={theme} />;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <SymbolInput value={input} onChange={setInput} onSubmit={handleSubmit} theme={theme} />
        {data?.expiries?.map(e => (
          <button key={e} onClick={() => { setExpiry(e); load(symbol, e); }}
            style={{
              padding: "4px 10px", borderRadius: 4, border: `1px solid ${theme.border}`,
              background: expiry === e ? theme.accent : "none",
              color: expiry === e ? "#fff" : theme.muted,
              cursor: "pointer", fontSize: 11, fontFamily: "inherit"
            }}>
            {e}
          </button>
        ))}
      </div>

      {data && (
        <>
          <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
            {[["Spot", `₹${fmt(data.spot)}`],
            ["Max Pain", data.max_pain ? `₹${data.max_pain}` : "—"],
            ["DTE", data.dte ? `${data.dte}d` : "—"]].map(([k, v]) => (
              <Card theme={theme} style={{ padding: "10px 16px" }} key={k}>
                <div style={{ color: theme.muted, fontSize: 10 }}>{k}</div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{v}</div>
              </Card>
            ))}
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: theme.muted, borderBottom: `1px solid ${theme.border}` }}>
                  {["CE OI", "CE Vol", "CE LTP", "CE IV", "Strike", "PE IV", "PE LTP", "PE Vol", "PE OI"].map(h => (
                    <th key={h} style={{ padding: "6px 10px", textAlign: "center", fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.strikes?.map(row => (
                  <tr key={row.strike}
                    style={{
                      background: row.isATM ? "rgba(99,102,241,.08)" : "none",
                      borderBottom: `1px solid ${theme.border}`
                    }}>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: theme.green }}>
                      {(row.CE.oi / 1000).toFixed(0)}K
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: theme.muted }}>
                      {(row.CE.volume / 1000).toFixed(0)}K
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right" }}>{fmt(row.CE.ltp)}</td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: theme.muted }}>{fmt(row.CE.iv)}</td>
                    <td style={{
                      padding: "5px 10px", textAlign: "center", fontWeight: row.isATM ? 700 : 400,
                      color: row.isATM ? theme.accent : theme.text
                    }}>
                      {row.strike}{row.isATM ? " ◀" : ""}
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "left", color: theme.muted }}>{fmt(row.PE.iv)}</td>
                    <td style={{ padding: "5px 10px", textAlign: "left" }}>{fmt(row.PE.ltp)}</td>
                    <td style={{ padding: "5px 10px", textAlign: "left", color: theme.muted }}>
                      {(row.PE.volume / 1000).toFixed(0)}K
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "left", color: theme.red }}>
                      {(row.PE.oi / 1000).toFixed(0)}K
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
