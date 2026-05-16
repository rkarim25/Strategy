export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const mode = url.searchParams.get("mode") || "daily";
    const dailyUrl = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=30y";
    const quoteUrl = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1m&range=1d";

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
          ticker: "^GSPC",
          source: "Yahoo Finance chart endpoint",
          timestamp: latest.date
        }), {
          headers: {
            ...corsHeaders,
            "content-type": "application/json"
          }
        });
      }

      return new Response(JSON.stringify({ error: "Use ?mode=daily or ?mode=quote" }), {
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
