/** Conventional vs halal UCITS/ETP reference for UK / II investors on LSE. */
window.HALAL_FEES_DATA = [
  {
    group: "Conventional — 1x equity",
    badge: "conventional",
    rows: [
      {
        productType: "S&P 500",
        ticker: "SPYL / SPXL",
        ter: "0.03%",
        terClass: "ter-low",
        notes: "Lowest-cost S&P 500 UCITS on LSE; accumulating share classes",
      },
      {
        productType: "S&P 500",
        ticker: "CSPX / CSP1",
        ter: "0.07%",
        terClass: "ter-mid",
        notes: "iShares Core S&P 500; physical replication; large AUM",
      },
      {
        productType: "S&P 500",
        ticker: "VUAG",
        ter: "0.07%",
        terClass: "ter-mid",
        notes: "Vanguard S&P 500 UCITS; GBP LSE listing",
      },
      {
        productType: "Nasdaq 100",
        ticker: "EQQQ",
        ter: "0.30%",
        terClass: "ter-mid",
        notes: "Invesco EQQQ; most liquid Nasdaq 100 UCITS on LSE",
      },
      {
        productType: "Nasdaq 100",
        ticker: "CNDX",
        ter: "0.30%",
        terClass: "ter-mid",
        notes: "iShares Nasdaq 100 UCITS; synthetic swap structure",
      },
    ],
  },
  {
    group: "Conventional — levered ETPs",
    badge: "levered",
    rows: [
      {
        productType: "2× S&P 500",
        ticker: "XS2D",
        ter: "0.60%",
        terClass: "ter-high",
        notes: "Xtrackers daily 2× S&P 500 swap UCITS; compounding drag applies",
      },
      {
        productType: "3× S&P 500",
        ticker: "3USL",
        ter: "0.75%",
        terClass: "ter-high",
        notes: "WisdomTree daily 3× S&P 500; used in Guarded SPX back-tests",
      },
      {
        productType: "2× Nasdaq 100",
        ticker: "LQQ",
        ter: "0.60%",
        terClass: "ter-high",
        notes: "WisdomTree daily 2× Nasdaq 100 leveraged ETP",
      },
      {
        productType: "3× Nasdaq 100",
        ticker: "LQQ3",
        ter: "0.75%",
        terClass: "ter-high",
        notes: "WisdomTree daily 3× Nasdaq 100 leveraged ETP",
      },
    ],
  },
  {
    group: "Halal — US equity",
    badge: "halal",
    rows: [
      {
        productType: "US Shariah equity",
        ticker: "ISUS / ISDU",
        ter: "0.30%",
        terClass: "ter-mid",
        notes: "iShares MSCI USA Islamic UCITS; AAOIFI-screened US large & mid cap",
      },
      {
        productType: "US Shariah equity",
        ticker: "HIUS",
        ter: "0.30%",
        terClass: "ter-mid",
        notes: "HSBC Islamic USA Equity UCITS; similar US universe to ISUS",
      },
      {
        productType: "US Shariah equity",
        ticker: "SPUS",
        ter: "0.45%",
        terClass: "ter-mid",
        notes: "SP Funds S&P 500 Sharia Industry Exclusions; US-listed, some LSE access",
      },
      {
        productType: "US Shariah equity",
        ticker: "HLAL",
        ter: "0.50%",
        terClass: "ter-mid",
        notes: "Wahed FTSE USA Shariah ETF; broader US Shariah index",
      },
    ],
  },
  {
    group: "Halal — other",
    badge: "halal",
    rows: [
      {
        productType: "Nasdaq 100",
        ticker: "—",
        ter: "—",
        terClass: "",
        notes: "No halal Nasdaq 100 UCITS/ETP listed on LSE",
      },
      {
        productType: "Global Shariah equity",
        ticker: "ISWD",
        ter: "0.30%",
        terClass: "ter-mid",
        notes: "iShares MSCI World Islamic UCITS; global context, not pure US beta",
      },
      {
        productType: "Levered Shariah",
        ticker: "—",
        ter: "—",
        terClass: "",
        notes: "No halal 2×/3× levered equivalent on LSE; Guarded-style tiered leverage is not Shariah-compliant as packaged",
      },
    ],
  },
];

window.HALAL_SCREENING_DATA = [
  {
    category: "Conventional financials",
    conventional: "Included — banks, insurers, asset managers, and other interest-based financials are standard index constituents.",
    halal: "Excluded — companies deriving material revenue from riba (interest) are screened out under AAOIFI business-activity rules.",
  },
  {
    category: "Alcohol, tobacco, gambling, adult entertainment, weapons",
    conventional: "Included when part of the benchmark — e.g. beverage, casino, defence, and adult-content firms remain in broad indices.",
    halal: "Excluded — non-permissible (haram) business activities are removed regardless of index weight.",
  },
  {
    category: "Pork & non-halal food production",
    conventional: "Included — food producers with pork or non-halal meat lines can remain in conventional trackers.",
    halal: "Excluded — companies with material pork or non-halal meat revenue fail business-activity screens.",
  },
  {
    category: "High financial leverage (debt)",
    conventional: "No debt-ratio screen — highly leveraged firms remain if they meet index criteria.",
    halal: "Excluded above ~33% debt/market-cap threshold (AAOIFI financial-ratio screen; exact methodology varies by provider).",
  },
  {
    category: "Interest income",
    conventional: "No income-source screen — interest income from cash deposits or bonds is immaterial to index inclusion.",
    halal: "Excluded above ~5% of total revenue from interest or non-permissible income (purification may apply for residual exposure).",
  },
  {
    category: "Other AAOIFI / Shariah rules",
    conventional: "Not applicable — conventional indices follow market-cap weighting only.",
    halal: "Additional screens: impermissible contracts, excessive uncertainty (gharar), and ongoing Shariah board oversight; non-compliant names rebalanced out.",
  },
  {
    category: "Sector & factor exposure",
    conventional: "Full market-cap exposure to all eligible index constituents, including financials (~13–15% in S&P 500).",
    halal: "Material sector shifts — financials near zero; overweight tech/healthcare vs conventional US indices; tracking error vs S&P 500 is structural.",
  },
  {
    category: "Leveraged products",
    conventional: "2×/3× daily ETPs available (XS2D, 3USL, LQQ, LQQ3) for tactical Guarded-style strategies.",
    halal: "No halal levered equivalent on LSE — daily swap/leverage structures involve riba; Shariah-compliant investors are limited to 1× screened equity.",
  },
];
