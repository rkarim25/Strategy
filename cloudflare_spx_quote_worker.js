export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const mode = url.searchParams.get("mode") || "daily";
    const ticker = "spy";

    const corsHeaders = {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, OPTIONS",
      "access-control-allow-headers": "content-type"
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      if (!env.TIINGO_API_TOKEN) {
        throw new Error("Missing TIINGO_API_TOKEN Worker secret.");
      }

      if (mode === "daily") {
        const endDate = new Date().toISOString().slice(0, 10);
        const start = new Date();
        start.setFullYear(start.getFullYear() - 25);
        const startDate = start.toISOString().slice(0, 10);

        const tiingoUrl =
          `https://api.tiingo.com/tiingo/daily/${ticker}/prices?startDate=${startDate}&endDate=${endDate}&format=json&token=${env.TIINGO_API_TOKEN}`;

        const res = await fetch(tiingoUrl);
        const text = await res.text();

        if (!res.ok) {
          throw new Error(`Tiingo daily failed ${res.status}: ${text.slice(0, 300)}`);
        }

        const data = JSON.parse(text);
        const csv = [
          "Date,Close",
          ...data
            .filter((row) => row.date && Number.isFinite(Number(row.close)))
            .map((row) => `${row.date.slice(0, 10)},${row.close}`)
        ].join("\n");

        return new Response(csv, {
          headers: {
            ...corsHeaders,
            "content-type": "text/csv"
          }
        });
      }

      if (mode === "quote") {
        const tiingoUrl =
          `https://api.tiingo.com/iex/${ticker}/prices?token=${env.TIINGO_API_TOKEN}`;

        const res = await fetch(tiingoUrl);
        const text = await res.text();

        if (!res.ok) {
          throw new Error(`Tiingo quote failed ${res.status}: ${text.slice(0, 300)}`);
        }

        const data = JSON.parse(text);
        const row = Array.isArray(data) ? data[0] : data;
        const price = Number(row?.last ?? row?.close ?? row?.tngoLast ?? row?.prevClose);

        if (!Number.isFinite(price) || price <= 0) {
          throw new Error(`No valid Tiingo quote price returned: ${text.slice(0, 300)}`);
        }

        return new Response(JSON.stringify({ price, ticker: "SPY" }), {
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
