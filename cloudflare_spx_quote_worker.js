// slug -> Yahoo Finance ticker. Every site asset is mapped so ?symbol=<slug> returns
// that asset's real quote. Unknown symbols fall back to the param uppercased.
const SYMBOLS = {
  spx: "^GSPC",
  ndx: "^NDX",
  gold: "GC=F",
  ftse250: "^FTMC",
  dax: "^GDAXI",
  msci_em: "EEM",
  msci_world: "SWDA.L",
  lqq3: "LQQ3.L",
  "3bal": "3BAL.L",
  vix: "^VIX",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const mode = url.searchParams.get("mode") || "daily";
    const symbolParam = url.searchParams.get("symbol") || "spx";
    const symbolKey = symbolParam.toLowerCase();

    const tickerName = SYMBOLS[symbolKey] || symbolParam.toUpperCase();
    const encodedTicker = encodeURIComponent(tickerName);

    const dailyUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodedTicker}?interval=1d&range=30y`;
    const quoteUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodedTicker}?interval=1m&range=1d`;

    const corsHeaders = {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, OPTIONS",
      "access-control-allow-headers": "content-type"
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      if (mode === "daily") {
        const res = await fetch(dailyUrl, {
          headers: { "user-agent": "Mozilla/5.0" }
        });
        const text = await res.text();

        if (!res.ok) {
          throw new Error(`Yahoo daily failed ${res.status}: ${text.slice(0, 300)}`);
        }

        const csv = yahooChartToCsv(JSON.parse(text));

        return new Response(csv, {
          headers: {
            ...corsHeaders,
            "content-type": "text/csv"
          }
        });
      }

      if (mode === "quote") {
        const res = await fetch(quoteUrl, {
          headers: { "user-agent": "Mozilla/5.0" }
        });
        const text = await res.text();

        if (!res.ok) {
          throw new Error(`Yahoo quote failed ${res.status}: ${text.slice(0, 300)}`);
        }

        const latest = latestYahooChartPoint(JSON.parse(text));

        return new Response(JSON.stringify({
          price: latest.close,
          ticker: tickerName,
          source: "Yahoo Finance chart endpoint",
          timestamp: latest.date
        }), {
          headers: {
            ...corsHeaders,
            "content-type": "application/json"
          }
        });
      }

      if (mode === "intraday") {
        const interval = url.searchParams.get("interval") || "5m";
        const range = url.searchParams.get("range") || "60d";
        const intradayUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodedTicker}?interval=${encodeURIComponent(interval)}&range=${encodeURIComponent(range)}&includePrePost=false`;
        const res = await fetch(intradayUrl, { headers: { "user-agent": "Mozilla/5.0" } });
        const text = await res.text();
        if (!res.ok) {
          throw new Error(`Yahoo intraday failed ${res.status}: ${text.slice(0, 300)}`);
        }
        const bars = yahooChartOhlcv(JSON.parse(text));
        return new Response(JSON.stringify({ ticker: tickerName, interval, bars }), {
          headers: {
            ...corsHeaders,
            "content-type": "application/json"
          }
        });
      }

      return new Response(JSON.stringify({ error: "Use ?mode=daily|quote|intraday" }), {
        status: 400,
        headers: {
          ...corsHeaders,
          "content-type": "application/json"
        }
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: {
          ...corsHeaders,
          "content-type": "application/json"
        }
      });
    }
  }
};

function yahooChartOhlcv(data) {
  const result = data?.chart?.result?.[0];
  const ts = result?.timestamp || [];
  const q = result?.indicators?.quote?.[0] || {};
  const o = q.open || [], h = q.high || [], l = q.low || [], c = q.close || [], v = q.volume || [];
  const out = [];
  for (let i = 0; i < ts.length; i++) {
    if (o[i] == null || h[i] == null || l[i] == null || c[i] == null) continue;
    if (!(Number.isFinite(c[i]) && c[i] > 0 && h[i] >= l[i])) continue;
    out.push({
      timestamp: ts[i] * 1000,
      open: Number(o[i]), high: Number(h[i]), low: Number(l[i]), close: Number(c[i]),
      volume: v[i] ? Math.round(v[i]) : 0
    });
  }
  return out;
}

function yahooChartToCsv(data) {
  const rows = yahooChartRows(data);
  if (rows.length < 2) {
    throw new Error("Yahoo chart response did not include enough close rows.");
  }
  return [
    "Date,Close",
    ...rows.map((row) => `${row.date},${row.close}`)
  ].join("\n");
}

function latestYahooChartPoint(data) {
  const rows = yahooChartRows(data);
  const latest = rows.at(-1);
  if (!latest) {
    throw new Error("Yahoo quote response did not include a valid close.");
  }
  return latest;
}

function yahooChartRows(data) {
  const result = data?.chart?.result?.[0];
  const timestamps = result?.timestamp || [];
  const closes = result?.indicators?.quote?.[0]?.close || [];
  return timestamps
    .map((timestamp, index) => ({
      date: new Date(timestamp * 1000).toISOString().slice(0, 10),
      close: Number(closes[index])
    }))
    .filter((row) => row.date && Number.isFinite(row.close) && row.close > 0);
}
