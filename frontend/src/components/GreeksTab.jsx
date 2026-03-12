import { useState, useEffect } from "react";

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

function Badge({ label, color, bg }) {
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 4, fontSize: 11,
      fontWeight: 600, color, background: bg
    }}>
      {label}
    </span>
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

export default function GreeksTab({ theme, symbol = "NIFTY" }) {
  const [input, setInput] = useState(symbol);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async (sym) => {
    setLoading(true);
    try { setData(await apiFetch(`/api/greeks/${sym}`)); }
    catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => {
    setInput(symbol);
    load(symbol);
  }, [symbol]);

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <SymbolInput value={input} onChange={setInput}
          onSubmit={() => load(input)} theme={theme} />
      </div>

      {loading && <Loader theme={theme} />}
      {data && (
        <>
          <div style={{ marginBottom: 8, color: theme.muted, fontSize: 12 }}>
            {data.symbol} · Spot ₹{fmt(data.spot)} · DTE {data.dte}d
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: theme.muted, borderBottom: `1px solid ${theme.border}` }}>
                  {["Strike", "CE Δ", "CE Γ", "CE θ/day", "CE Vega", "Moneyness", "PE Δ", "PE Γ", "PE θ/day", "PE Vega"].map(h => (
                    <th key={h} style={{ padding: "6px 10px", textAlign: "center", fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.strikes?.map(row => {
                  const cg = row.CE.greeks || {}; const pg = row.PE.greeks || {};
                  const isATM = cg.moneyness === "ATM" || pg.moneyness === "ATM";
                  return (
                    <tr key={row.strike}
                      style={{
                        background: isATM ? "rgba(99,102,241,.08)" : "none",
                        borderBottom: `1px solid ${theme.border}`
                      }}>
                      <td style={{
                        padding: "5px 10px", textAlign: "center", fontWeight: isATM ? 700 : 400,
                        color: isATM ? theme.accent : theme.text
                      }}>{row.strike}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.green }}>{fmt(cg.delta, 3)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.muted }}>{fmt(cg.gamma, 5)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.red }}>{fmt(cg.theta, 2)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center" }}>{fmt(cg.vega, 3)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center" }}>
                        <Badge label={cg.moneyness || "—"} color={theme.muted} bg={theme.bg} />
                      </td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.red }}>{fmt(pg.delta, 3)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.muted }}>{fmt(pg.gamma, 5)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.red }}>{fmt(pg.theta, 2)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center" }}>{fmt(pg.vega, 3)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
