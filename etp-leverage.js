/**
 * Browser-side 2x/3x P&L using exported ETP daily returns (see export_etp_returns_json).
 */
(function (global) {
  const TRADING_DAYS = 252;
  const TER_ANNUAL = { 1: 0.003, 2: 0.006, 3: 0.009 };
  const FUNDING_SPREAD = 0.006;
  const VIX_SPREAD_BASE = 0.006;
  const VIX_STRESS_THRESHOLD = 15;
  const VIX_SPREAD_BPS_PER_10 = 0.003;
  const VIX_SPREAD_CAP = 0.026;
  const VIX_3X_SPREAD_BUMP = 0.002;

  function vixLinkedSpreadAnnual(vix, leverage) {
    const v = Number(vix);
    if (!Number.isFinite(v)) return FUNDING_SPREAD;
    let spread =
      VIX_SPREAD_BASE +
      Math.max(0, (v - VIX_STRESS_THRESHOLD) / 10) * VIX_SPREAD_BPS_PER_10;
    if (leverage >= 2.5) spread += VIX_3X_SPREAD_BUMP;
    return Math.min(spread, VIX_SPREAD_CAP);
  }

  function fundingDaily(leverage, cashRate, vix) {
    if (leverage <= 1) return 0;
    const spread =
      vix != null && Number.isFinite(Number(vix))
        ? vixLinkedSpreadAnnual(vix, leverage)
        : FUNDING_SPREAD;
    return ((leverage - 1) * (cashRate + spread)) / TRADING_DAYS;
  }

  function syntheticDailyReturn(indexRet, leverage, cashRate, vix) {
    if (leverage <= 0) return cashRate / TRADING_DAYS;
    if (leverage <= 1) return indexRet - TER_ANNUAL[1] / TRADING_DAYS;
    const borrow = fundingDaily(leverage, cashRate, vix);
    const volDrag = 0.5 * leverage * (leverage - 1) * indexRet * indexRet;
    const tier = leverage >= 2.5 ? 3 : 2;
    const ter = TER_ANNUAL[tier] / TRADING_DAYS;
    return leverage * indexRet - borrow - volDrag - ter;
  }

  function tierColumn(leverage) {
    if (leverage <= 0) return "ret_0";
    if (leverage < 1.5) return "ret_1";
    if (leverage < 2.5) return "ret_2";
    return "ret_3";
  }

  const EtpLeverage = {
    data: null,
    dateToIndex: null,

    async load(url) {
      const response = await fetch(url);   // cache via ETag/max-age (was no-store → re-downloaded every page load)
      if (!response.ok) throw new Error(`ETP returns ${url}: HTTP ${response.status}`);
      const data = await response.json();
      const map = new Map();
      (data.dates || []).forEach((d, i) => map.set(d, i));
      this.data = data;
      this.dateToIndex = map;
      return data;
    },

    dailyReturn(leverage, indexRet, cashRate, dateIso) {
      if (leverage <= 0) return cashRate / TRADING_DAYS;
      let vix = null;
      if (this.data && this.dateToIndex && dateIso) {
        const idx = this.dateToIndex.get(dateIso);
        if (idx != null) {
          const col = tierColumn(leverage);
          const v = this.data[col]?.[idx];
          if (Number.isFinite(v)) return v;
          const vixVal = this.data.vix?.[idx];
          if (Number.isFinite(vixVal)) vix = vixVal;
        }
      }
      return syntheticDailyReturn(indexRet, leverage, cashRate, vix);
    },
  };

  global.EtpLeverage = EtpLeverage;
})(typeof window !== "undefined" ? window : globalThis);
