"""
ValuMonk SIF Tracker - Single-file Python Backend
Run locally:  python app.py
Deploy:       gunicorn app:app
"""

import json, math, re, time, logging, os, threading
import urllib.request
from datetime import datetime
from flask import Flask, jsonify, send_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
app = Flask(__name__)

# ================================================================
# NIFTY 50 TRI MONTHLY RETURNS
# Add one line each month after month-end close.
# Format: "Mon-YY": return_percent
# ================================================================

# NIFTY removed - not maintained manually
# Months list is derived automatically from the first fund's monthly data
NIFTY = {}

# ================================================================
# ISIN MAP - Regular Growth plan ISIN for each fund
# Auto-updated when new funds detected from AMFI
# ================================================================

ISIN_MAP = {'altiva-hls': 'INF754K30052', 'qsif-hls': 'INF966L30084', 'magnum-hls': 'INF200K30015', 'arudha-hls': 'INF194K30010', 'apex-hls': 'INF209K30040', 'titanium-hls': 'INF277K30013', 'isif-hls': 'INF109K30018', 'qsif-els': 'INF966L30027', 'dyna-els': 'INF579M30018', 'arudha-els': 'INF194K30358', 'sapphire-els': 'INF090I30014', 'diviniti-els': 'INF00XX30019', 'qsif-extop': 'INF966L30183', 'isif-extop': 'INF109K30034', 'dyna-aaa': 'INF579M30075', 'qsif-aaa': 'INF966L30217', 'qsif-sr': 'INF966L30308'}

# ================================================================
# INDEX FUND ISINs - fetched from AMFI NAVAll.txt automatically
# Used to compute benchmark monthly returns with zero manual work
# Source: AMFI NAVAll.txt (Direct Growth plans of index funds)
# ================================================================

INDEX_FUNDS = {
    "Nifty 50":           {"isin": "INF204KB16I2", "label": "Nifty 50 (Index Fund NAV)"},
    "Nifty 500":          {"isin": "INF209KB12L7", "label": "Nifty 500 (Index Fund NAV)"},
    "Nifty MidSmall 400": {"isin": "INF959L01DC0", "label": "Nifty MidSmallcap 400"},
    "Balanced Advantage": {"isin": "INF179KB1HY0", "label": "Balanced Advantage (HDFC)"},
    "Multi Asset":        {"isin": "INF247L01AA0", "label": "Multi Asset (Motilal)"},
}

# Which index to compare with each SIF category
CAT_BENCHMARK = {
    "hybrid": ["Nifty 50", "Balanced Advantage"],
    "equity": ["Nifty 50", "Nifty 500"],
    "extop":  ["Nifty MidSmall 400"],
    "asset":  ["Multi Asset"],
    "sector": ["Nifty 500"],
}

# ================================================================
# CATEGORY LABELS AND COMPARABLE MF DEFAULTS
# ================================================================

CAT_LABELS = {
    "hybrid": "Hybrid Long-Short",
    "equity": "Equity Long-Short",
    "extop":  "Equity Ex-Top 100",
    "asset":  "Active Asset Allocator",
    "sector": "Sector Rotation",
}
COMP_MF_MAP = {
    "hybrid": "Balanced Advantage Fund",
    "equity": "Flexicap Funds",
    "extop":  "Small & Midcap Funds",
    "asset":  "Multi Asset Funds",
    "sector": "Business Cycle Funds",
}
COMP_MF_OVERRIDE = {
    "altiva-hls": "Between Arbitrage & Equity Savings",
    "magnum-hls": "Between Arbitrage & Equity Savings",
}

# ================================================================
# FUND REGISTRY - qualitative data for each fund
# Fields set to None show as "-" on the website.
# To update any field: change the value here and push to GitHub.
# New auto-detected funds appear at the bottom with None fields.
# ================================================================

FUND_REGISTRY = {
    "altiva-hls": {
        "name": "Altiva Hybrid Long-Short",
        "amc": "Edelweiss MF",
        "brand": "Altiva",
        "cat": "hybrid",
        "fm": "Dhawal Dalal",
        "fmYrs": 20,
        "inception": "24 Oct 2025",
        "inceptionDate": "24 Oct 2025",
        "bench": "NIFTY 50 Hybrid Composite Debt 50:50",
        "er": 1.7,
        "aum": 2704,
        "riskLevel": 2,
        "exitLoad": "0.5% within 30 days",
        "liq": "Twice weekly (Mon & Wed)",
        "minHorizon": "1.5 years",
        "purpose": "Conservative income generation via arbitrage + FD-plus returns",
        "strategy": "Income-first hybrid built around cash-futures arbitrage (20–40%), fixed income (40–60%), and special-situation derivatives (covered calls, straddles). Net equity exposure capped at 0–15%. Lowest drawdown of all hybrid SIFs during the March 2026 crash (Nifty -11.3%): Altiva fell -1.42% vs benchmark -6.35%. Ranked #3 of 7 Hybrid SIFs in downside protection.",
        "compMF": "Between Arbitrage & Equity Savings",
        "nfo": False,
        "navBase": False,
        "monthly": {"Oct-25": 0.09, "Nov-25": 1.01, "Dec-25": 1.71, "Jan-26": 0.13, "Feb-26": 0.71, "Mar-26": -1.53, "Apr-26": 3.17, "May-26": 1.14, "Jun-26": 0.99},
        "rsi": 6.54,
        "r1m": 1.14,
        "r3m": 2.75,
        "r6m": None,
        "r1y": None,
    },
    "qsif-hls": {
        "name": "qSIF Hybrid Long-Short",
        "amc": "Quant MF",
        "brand": "qSIF",
        "cat": "hybrid",
        "fm": "Sanjeev Sharma",
        "fmYrs": 18,
        "inception": "20 Oct 2025",
        "inceptionDate": "20 Oct 2025",
        "bench": "NIFTY 50 Hybrid Composite Debt 65:35",
        "er": 1.9,
        "aum": 305,
        "riskLevel": 5,
        "exitLoad": "1% within 15 days",
        "liq": "Daily (T+3)",
        "minHorizon": "2–3 years",
        "purpose": "Systematic long-short hybrid using MARCOV + VLRT quantitative models",
        "strategy": "India's first SIF — launched before SEBI's April 2025 go-live under special approval. Uses MARCOV framework and High Frequency Analytics for systematic hybrid allocation. Daily liquidity is a structural advantage vs most hybrid SIFs. Strong 3-month recovery (+4.88%) post-March crash.",
        "compMF": "Balanced Advantage Fund",
        "nfo": False,
        "navBase": False,
        "monthly": {"Oct-25": 0.46, "Nov-25": -0.38, "Dec-25": -0.08, "Jan-26": -1.29, "Feb-26": 0.48, "Mar-26": -0.91, "Apr-26": 6.94, "May-26": -1.02, "Jun-26": 1.29},
        "rsi": 4.02,
        "r1m": -1.02,
        "r3m": 4.88,
        "r6m": None,
        "r1y": None,
    },
    "magnum-hls": {
        "name": "Magnum Hybrid Long-Short",
        "amc": "SBI MF",
        "brand": "Magnum SIF",
        "cat": "hybrid",
        "fm": "Gaurav Mehta",
        "fmYrs": 12,
        "inception": "29 Oct 2025",
        "inceptionDate": "29 Oct 2025",
        "bench": "CRISIL Hybrid 50+50 Moderate TRI",
        "er": 1.6,
        "aum": 3315,
        "riskLevel": 1,
        "exitLoad": "Tiered: 0.5% ≤15d, 0.25% ≤1M, nil after",
        "liq": "Twice weekly (Mon & Thu)",
        "minHorizon": "2 years",
        "purpose": "All-weather capital preservation using collars, covered calls, and arbitrage",
        "strategy": "India's largest SIF by AUM at ₹3,315 Cr. Conservative covered-call strategy for income generation ('FD-plus' positioning). Net equity typically below 10–15%. Collar strategy limits both upside and downside. Fell -2.16% in March 2026 vs Nifty -11.3% — strong capital protection.",
        "compMF": "Between Arbitrage & Equity Savings",
        "nfo": False,
        "navBase": False,
        "monthly": {"Oct-25": -0.34, "Nov-25": 1.24, "Dec-25": 0.95, "Jan-26": -0.83, "Feb-26": 0.77, "Mar-26": -2.16, "Apr-26": 2.28, "May-26": 0.68, "Jun-26": 1.36},
        "rsi": 2.55,
        "r1m": 0.68,
        "r3m": 0.74,
        "r6m": None,
        "r1y": None,
    },
    "arudha-hls": {
        "name": "Arudha Hybrid Long-Short",
        "amc": "Bandhan MF",
        "brand": "Arudha",
        "cat": "hybrid",
        "fm": "Manish Gunwani",
        "fmYrs": 25,
        "inception": "4 Feb 2026",
        "inceptionDate": "4 Feb 2026",
        "bench": "NIFTY 50 Hybrid Composite Debt 65:35",
        "er": 1.7,
        "aum": 212,
        "riskLevel": 2,
        "exitLoad": "0.5% within 1 month",
        "liq": "Daily purchase; redemption Mon & Thu",
        "minHorizon": "1 year",
        "purpose": "Zero net equity exposure — closest SIF substitute for a fixed deposit with LTCG advantage",
        "strategy": "Best-performing hybrid SIF in March 2026 — fell only -0.1% when Nifty dropped -11.3%. Ranked #1 of 7 hybrid SIFs for downside protection. Zero net equity — 100% fixed income and arbitrage. Manish Gunwani brings 25+ years of institutional experience.",
        "compMF": "Balanced Advantage Fund",
        "nfo": False,
        "navBase": False,
        "monthly": {"Feb-26": 0.45, "Mar-26": 0.12, "Apr-26": 0.38, "May-26": 0.22, "Jun-26": 0.78},
        "rsi": 1.17,
        "r1m": 0.22,
        "r3m": 0.71,
        "r6m": None,
        "r1y": None,
    },
    "apex-hls": {
        "name": "Apex Hybrid Long-Short",
        "amc": "Aditya Birla SL MF",
        "brand": "Apex",
        "cat": "hybrid",
        "fm": "Mahesh Patil",
        "fmYrs": 20,
        "inception": "30 Mar 2026",
        "inceptionDate": "30 Mar 2026",
        "bench": "NIFTY 50 Hybrid Composite Debt 65:35",
        "er": 1.75,
        "aum": 74,
        "riskLevel": 2,
        "exitLoad": "0.5% within 3 months",
        "liq": "Twice weekly (Mon & Wed)",
        "minHorizon": "1.5–2 years",
        "purpose": "Diversified ESF+ strategy combining arbitrage, directional equity, and special situations",
        "strategy": "ABSL's SIF combining arbitrage, directional equity (35–65%), and special situations. Launched after March 2026 crash so no drawdown stress-test data yet. Managed by CIO Mahesh Patil. +0.90% since inception in a broadly volatile market.",
        "compMF": "Balanced Advantage Fund",
        "nfo": False,
        "navBase": False,
        "monthly": {"Mar-26": 0.0, "Apr-26": 0.4, "May-26": 0.5, "Jun-26": 1.25},
        "rsi": 0.9,
        "r1m": 0.5,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
    "titanium-hls": {
        "name": "Titanium Hybrid Long-Short",
        "amc": "Tata MF",
        "brand": "Titanium",
        "cat": "hybrid",
        "fm": "Murthy Nagarajan",
        "fmYrs": 22,
        "inception": "17 Dec 2025",
        "inceptionDate": "17 Dec 2025",
        "bench": "NIFTY 50 Hybrid Composite Debt 65:35",
        "er": 1.75,
        "aum": 404,
        "riskLevel": 3,
        "exitLoad": "1% within 1 year",
        "liq": "Monthly (first working day)",
        "minHorizon": "2 years",
        "purpose": "Premium BAF-type returns across equity, debt, REITs, InvITs with long-short overlay",
        "strategy": "Dynamic hybrid across equities, debt, REITs, InvITs with tactical long-short derivatives. Monthly redemption only — lowest liquidity of hybrid SIFs. Fell -6.87% in March 2026 (ranked #5 of 7 hybrid SIFs) — higher equity sensitivity. 3M return of -1.20% includes the March drawdown.",
        "compMF": "Balanced Advantage Fund",
        "nfo": False,
        "navBase": False,
        "monthly": {"Dec-25": 0.64, "Jan-26": -1.02, "Feb-26": 1.42, "Mar-26": -6.87, "Apr-26": 5.51, "May-26": 0.55, "Jun-26": 2.05},
        "rsi": -0.19,
        "r1m": 0.55,
        "r3m": -1.2,
        "r6m": None,
        "r1y": None,
    },
    "isif-hls": {
        "name": "iSIF Hybrid Long-Short",
        "amc": "ICICI Prudential MF",
        "brand": "iSIF",
        "cat": "hybrid",
        "fm": "Rajat Chandak",
        "fmYrs": 15,
        "inception": "5 Feb 2026",
        "inceptionDate": "5 Feb 2026",
        "bench": "NIFTY 50 Hybrid Composite Debt 65:35",
        "er": 1.85,
        "aum": 616,
        "riskLevel": 5,
        "exitLoad": "1% within 1 year",
        "liq": "Daily redemption",
        "minHorizon": "2 years",
        "purpose": "BAF+ with dynamic net equity (-7.5% to 75%) — equity-like returns at lower drawdown",
        "strategy": "BAF+ strategy with dynamic net equity range from -7.5% to 75%. Covered calls, stock puts, arbitrage overlay. Fell -7.31% in March 2026 (ranked last #6 of 7 hybrid SIFs). Strong April recovery +7.45%. Since-inception -0.97% reflects launch into market peak. ICICI's 550+ company research infrastructure is a key differentiator.",
        "compMF": "Balanced Advantage Fund",
        "nfo": False,
        "navBase": False,
        "monthly": {"Feb-26": -0.59, "Mar-26": -7.31, "Apr-26": 7.45, "May-26": 0.02, "Jun-26": 2.86},
        "rsi": -0.97,
        "r1m": 0.02,
        "r3m": -0.38,
        "r6m": None,
        "r1y": None,
    },
    "qsif-els": {
        "name": "qSIF Equity Long-Short",
        "amc": "Quant MF",
        "brand": "qSIF",
        "cat": "equity",
        "fm": "Sameer Kate",
        "fmYrs": 12,
        "inception": "8 Oct 2025",
        "inceptionDate": "8 Oct 2025",
        "bench": "Nifty 500 TRI",
        "er": 2.0,
        "aum": 561,
        "riskLevel": 5,
        "exitLoad": "1% within 15 days",
        "liq": "Daily (T+3)",
        "minHorizon": "3 years",
        "purpose": "Systematic VLRT-driven all-cap long-short equity for alpha across full market cycles",
        "strategy": "India's first equity long-short SIF. VLRT (Valuation, Liquidity, Risk, Timing) framework applied to all-cap equity. 65–100% equity/arbitrage, shorts up to 25%. Fell -8.95% in March 2026 (Nifty -11.3%). Strong recovery: +13.68% in April, +2.07% in May. Since-inception +3.54%.",
        "compMF": "Flexicap Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"Oct-25": 1.36, "Nov-25": -0.23, "Dec-25": -0.58, "Jan-26": -3.32, "Feb-26": 0.82, "Mar-26": -8.95, "Apr-26": 13.68, "May-26": 2.07, "Jun-26": 2.81},
        "rsi": 3.54,
        "r1m": 2.07,
        "r3m": 5.65,
        "r6m": None,
        "r1y": None,
    },
    "dyna-els": {
        "name": "DynaSIF Equity Long-Short",
        "amc": "360 ONE MF",
        "brand": "DynaSIF",
        "cat": "equity",
        "fm": "Chirag Mehta",
        "fmYrs": 14,
        "inception": "27 Feb 2026",
        "inceptionDate": "27 Feb 2026",
        "bench": "Nifty 500 TRI",
        "er": 1.8,
        "aum": 188,
        "riskLevel": 5,
        "exitLoad": "0.5% within 3 months",
        "liq": "Daily (T+3)",
        "minHorizon": "3–4 years",
        "purpose": "Highest target-return SIF — aggressive flexicap long-short for maximum alpha",
        "strategy": "Highest target-return SIF in the universe (14–16% p.a.). Launched near market bottom, giving it a favourable entry point. Since-inception +3.23% in ~3 months. All-cap equity 80–100%, tactical shorts up to 25%. Multi-factor stock selection with quant overlay.",
        "compMF": "Flexicap Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"Feb-26": 0.0, "Mar-26": -4.39, "Apr-26": 6.59, "May-26": 1.29, "Jun-26": 2.61},
        "rsi": 3.23,
        "r1m": 1.29,
        "r3m": 3.23,
        "r6m": None,
        "r1y": None,
    },
    "arudha-els": {
        "name": "Arudha Equity Long-Short",
        "amc": "Bandhan MF",
        "brand": "Arudha",
        "cat": "equity",
        "fm": "Manish Gunwani",
        "fmYrs": 25,
        "inception": "30 Mar 2026",
        "inceptionDate": "30 Mar 2026",
        "bench": "Nifty 500 TRI",
        "er": 1.7,
        "aum": 45,
        "riskLevel": 5,
        "exitLoad": "0.5% within 1 month",
        "liq": "Daily purchase; daily redemption",
        "minHorizon": "2–3 years",
        "purpose": "Flexicap long-short targeting equity returns at nearly half the volatility",
        "strategy": "Flexicap dynamic long-short strategy. Launched post March 2026 crash at a favourable entry point. +2.55% in ~2 months. All-cap equity 80–100%, fixed income up to 20%, shorts up to 25%. Daily liquidity.",
        "compMF": "Flexicap Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"Mar-26": 0.01, "Apr-26": 3.42, "May-26": -0.85, "Jun-26": 2.25},
        "rsi": 2.55,
        "r1m": -0.85,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
    "sapphire-els": {
        "name": "Sapphire Equity Long-Short",
        "amc": "Franklin Templeton MF",
        "brand": "Sapphire",
        "cat": "equity",
        "fm": "Anand Radhakrishnan",
        "fmYrs": 24,
        "inception": "29 Apr 2026",
        "inceptionDate": "29 Apr 2026",
        "bench": "Nifty 500 TRI",
        "er": 1.9,
        "aum": 96,
        "riskLevel": 5,
        "exitLoad": "1% within 1 year",
        "liq": "Twice weekly",
        "minHorizon": "2–3 years",
        "purpose": "Concentrated quality-compounder long-short leveraging Franklin's global research network",
        "strategy": "Franklin's entry into SIF under the Sapphire brand. Very recent launch (Apr 2026). The negative since-inception return reflects early market conditions at launch. Concentrated 30–50 stock long book, selective shorts up to 25%. Franklin's global research network covers 600+ analysts across 15 countries.",
        "compMF": "Flexicap Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"Apr-26": 0.0, "May-26": -0.83, "Jun-26": 1.9},
        "rsi": -0.83,
        "r1m": -0.83,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
    "diviniti-els": {
        "name": "Diviniti Equity Long-Short",
        "amc": "ITI MF",
        "brand": "Diviniti",
        "cat": "equity",
        "fm": "Rajesh Bhatia",
        "fmYrs": 30,
        "inception": "3 Dec 2025",
        "inceptionDate": "3 Dec 2025",
        "bench": "Nifty 500 TRI",
        "er": 1.95,
        "aum": 345,
        "riskLevel": 2,
        "exitLoad": "10% of units free within 6M; 0.5% on balance",
        "liq": "Twice weekly",
        "minHorizon": "2–3 years",
        "purpose": "High-conviction flexicap long-short from ex-Franklin CIO with 30 years L-S experience",
        "strategy": "Led by Rajesh Bhatia (ex-Franklin Templeton CIO, 30 years institutional long-short). ₹1,000 face value NAV (now ₹916.9 = -8.31% since inception). Worst performer in category — hurt by mid/small cap underperformance Dec 2025–Feb 2026 and March crash. Concentrated high-conviction approach means higher single-stock risk.",
        "compMF": "Flexicap Funds",
        "nfo": False,
        "navBase": True,
        "monthly": {"Dec-25": 0.25, "Jan-26": -1.23, "Feb-26": -1.37, "Mar-26": -2.99, "Apr-26": 0.71, "May-26": -3.92, "Jun-26": 2.8},
        "rsi": -8.31,
        "r1m": -3.92,
        "r3m": -6.13,
        "r6m": None,
        "r1y": None,
    },
    "qsif-extop": {
        "name": "qSIF Equity Ex-Top 100 L-S",
        "amc": "Quant MF",
        "brand": "qSIF",
        "cat": "extop",
        "fm": "Sameer Kate",
        "fmYrs": 12,
        "inception": "13 Nov 2025",
        "inceptionDate": "13 Nov 2025",
        "bench": "Nifty Midcap 150 TRI",
        "er": 2.0,
        "aum": 170,
        "riskLevel": 5,
        "exitLoad": "1% within 15 days",
        "liq": "Daily (T+3)",
        "minHorizon": "3 years",
        "purpose": "SMID-focused systematic alpha via VLRT in the under-researched Ex-Top 100 universe",
        "strategy": "Best single-month return of any SIF: +15.38% in April 2026 after Nifty's recovery. 3M return of +8.17% leads the Ex-Top 100 category. SMID equity 65–100%, shorts up to 25%. VLRT framework applied to mid/small cap universe. Fell -7.60% in March (Nifty -11.3%) but recovered strongly.",
        "compMF": "Small & Midcap Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"Nov-25": 0.01, "Dec-25": -1.49, "Jan-26": -4.69, "Feb-26": -0.9, "Mar-26": -7.6, "Apr-26": 15.38, "May-26": 1.45, "Jun-26": 3.49},
        "rsi": 0.66,
        "r1m": 1.45,
        "r3m": 8.17,
        "r6m": None,
        "r1y": None,
    },
    "isif-extop": {
        "name": "iSIF Equity Ex-Top 100 L-S",
        "amc": "ICICI Prudential MF",
        "brand": "iSIF",
        "cat": "extop",
        "fm": "Rajat Chandak",
        "fmYrs": 15,
        "inception": "5 Feb 2026",
        "inceptionDate": "5 Feb 2026",
        "bench": "Nifty Midcap 150 TRI",
        "er": 1.85,
        "aum": 1090,
        "riskLevel": 5,
        "exitLoad": "1% within 1 year",
        "liq": "Daily redemption",
        "minHorizon": "3–4 years",
        "purpose": "Value-conscious SMID long-short using covered calls, straddles, and pair trades",
        "strategy": "Largest equity SIF by AUM at ₹1,090 Cr despite launching Feb 2026. Value-conscious long-short focused on stocks outside India's top 100. Uses covered calls, straddles, strangles, and pair trades. Fell -8.61% in March 2026 (worst in Ex-Top 100 category) but April recovery +8.87% brought it near flat. Since-inception -0.40%.",
        "compMF": "Small & Midcap Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"Feb-26": -1.2, "Mar-26": -8.61, "Apr-26": 8.87, "May-26": 1.32, "Jun-26": 2.03},
        "rsi": -0.4,
        "r1m": 1.32,
        "r3m": 0.81,
        "r6m": None,
        "r1y": None,
    },
    "dyna-aaa": {
        "name": "DynaSIF Active Asset Allocator",
        "amc": "360 ONE MF",
        "brand": "DynaSIF",
        "cat": "asset",
        "fm": "Chirag Mehta",
        "fmYrs": 14,
        "inception": "30 Mar 2026",
        "inceptionDate": "30 Mar 2026",
        "bench": "Composite: Nifty 50 + CRISIL Short-Term + Gold",
        "er": 1.8,
        "aum": 32,
        "riskLevel": 3,
        "exitLoad": "0.5% within 3 months",
        "liq": "Mondays only; 7 working days notice",
        "minHorizon": "1–1.5 years",
        "purpose": "Multi-asset dynamic rotation across equity, debt, REITs, gold, silver and InvITs",
        "strategy": "India's most diversified SIF. True multi-asset long-short strategy — debt (20–65%), equity/REITs (20–50%), commodity derivatives (0–25%). Covered calls, arbitrage, volatility trades. Least frequent redemption of any SIF (Mondays only with 7 working day notice). Since-inception +1.62%.",
        "compMF": "Multi Asset Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"Mar-26": 0.01, "Apr-26": 1.02, "May-26": 0.58, "Jun-26": 1.36},
        "rsi": 1.62,
        "r1m": 0.58,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
    "qsif-aaa": {
        "name": "qSIF Active Asset Allocator",
        "amc": "Quant MF",
        "brand": "qSIF",
        "cat": "asset",
        "fm": "Sameer Kate",
        "fmYrs": 12,
        "inception": "24 Apr 2026",
        "inceptionDate": "24 Apr 2026",
        "bench": "Composite multi-asset",
        "er": 1.95,
        "aum": 89,
        "riskLevel": 3,
        "exitLoad": "1% within 15 days",
        "liq": "Daily (T+3)",
        "minHorizon": "1–2 years",
        "purpose": "Systematic VLRT-driven multi-asset allocation with daily liquidity",
        "strategy": "Quant's dynamic multi-asset SIF. Highest 1-month return (+2.77%) of any SIF in May 2026. VLRT framework drives allocation across equity, debt, gold, silver, InvITs. Daily liquidity (rare for an asset allocator). Since inception +2.73% in ~5 weeks.",
        "compMF": "Multi Asset Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"Apr-26": -0.04, "May-26": 2.77, "Jun-26": 1.66},
        "rsi": 2.73,
        "r1m": 2.77,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
    "qsif-sr": {
        "name": "qSIF Sector Rotation L-S",
        "amc": "Quant MF",
        "brand": "qSIF",
        "cat": "sector",
        "fm": "Sameer Kate",
        "fmYrs": 12,
        "inception": "6 May 2026",
        "inceptionDate": "6 May 2026",
        "bench": "Nifty 500 TRI",
        "er": 2.0,
        "aum": 28,
        "riskLevel": 5,
        "exitLoad": "1% within 15 days",
        "liq": "Daily (T+3)",
        "minHorizon": "2–3 years",
        "purpose": "First and only sector rotation SIF — goes long outperforming sectors, short underperforming",
        "strategy": "India's only sector rotation SIF. VLRT framework used to dynamically rotate across sectors — long outperforming sectors, short laggards via derivatives. Launched May 2026 with minimal track record. Unique strategy in the SIF universe. Sameer Kate is fund manager.",
        "compMF": "Business Cycle Funds",
        "nfo": False,
        "navBase": False,
        "monthly": {"May-26": 0.65, "Jun-26": 0.89},
        "rsi": 0.65,
        "r1m": None,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
    "isif-els-nfo": {
        "name": "iSIF Equity Long-Short",
        "amc": "ICICI Prudential MF",
        "brand": "iSIF",
        "cat": "equity",
        "fm": "Rajat Chandak",
        "fmYrs": None,
        "inception": "NFO: 19 May – 2 Jun 2026",
        "inceptionDate": "NFO: 19 May – 2 Jun 2026",
        "bench": "Nifty 500 TRI",
        "er": 1.85,
        "aum": None,
        "riskLevel": 5,
        "exitLoad": "",
        "liq": None,
        "minHorizon": None,
        "purpose": "ICICI Prudential's all-cap equity long-short SIF",
        "strategy": "NFO period 19 May – 2 Jun 2026. Will invest 80–100% in equities across all cap sizes with up to 25% unhedged short via derivatives. ICICI's 550+ company research infrastructure applied to equity long-short.",
        "compMF": "Flexicap Funds",
        "nfo": True,
        "navBase": False,
        "monthly": {},
        "rsi": None,
        "r1m": None,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
    "altiva-extop-nfo": {
        "name": "Altiva Equity Ex-Top 100 L-S",
        "amc": "Edelweiss MF",
        "brand": "Altiva",
        "cat": "extop",
        "fm": "Dhawal Dalal",
        "fmYrs": None,
        "inception": "NFO: 18 May – 1 Jun 2026",
        "inceptionDate": "NFO: 18 May – 1 Jun 2026",
        "bench": "Nifty Midcap 150 TRI",
        "er": 1.85,
        "aum": None,
        "riskLevel": 5,
        "exitLoad": "",
        "liq": None,
        "minHorizon": None,
        "purpose": "Edelweiss Altiva's extension into the mid/small cap Ex-Top 100 universe",
        "strategy": "NFO period 18 May – 1 Jun 2026. Extends Altiva's proven hybrid methodology to the Ex-Top 100 mid/small cap universe.",
        "compMF": "Small & Midcap Funds",
        "nfo": True,
        "navBase": False,
        "monthly": {},
        "rsi": None,
        "r1m": None,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
    "platinum-hls-nfo": {
        "name": "Platinum Hybrid Long-Short",
        "amc": "Mirae Asset MF",
        "brand": "Platinum",
        "cat": "hybrid",
        "fm": "TBA",
        "fmYrs": None,
        "inception": "NFO: 20 May – 3 Jun 2026",
        "inceptionDate": "NFO: 20 May – 3 Jun 2026",
        "bench": "NIFTY 50 Hybrid Composite Debt 65:35",
        "er": 1.7,
        "aum": None,
        "riskLevel": 3,
        "exitLoad": "",
        "liq": None,
        "minHorizon": None,
        "purpose": "Mirae Asset's SIF leveraging its rigorous bottom-up research in a hybrid long-short structure",
        "strategy": "NFO period 20 May – 3 Jun 2026. Mirae is known for rigorous bottom-up research and strong mid-cap equity track record. Hybrid long-short structure.",
        "compMF": "Pending",
        "nfo": True,
        "navBase": False,
        "monthly": {},
        "rsi": None,
        "r1m": None,
        "r3m": None,
        "r6m": None,
        "r1y": None,
    },
}

# ================================================================
# LIVE NAV ENGINE - do not edit below this line
# ================================================================

AMFI_API = "https://www.amfiindia.com/api/sif-latest-nav?type="
_live_navs = {}
_nav_date = None
_last_updated = None
_lock = threading.Lock()


def _fetch_amfi():
    req = urllib.request.Request(AMFI_API, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.amfiindia.com/sif/latest-nav",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _map_cat(cat_str):
    c = (cat_str or "").lower()
    if "ex-top 100" in c or "ex top 100" in c: return "extop"
    if "sector rotation" in c: return "sector"
    if "active asset allocator" in c: return "asset"
    if "equity long-short" in c or "equity long short" in c: return "equity"
    return "hybrid"


def _month_key(date_str):
    try:
        parts = (date_str or "").split("-")
        if len(parts) == 3 and len(parts[2]) == 4:
            return f"{parts[1][:3]}-{parts[2][2:]}"
    except Exception:
        pass
    return None


def _pct(new_nav, old_nav):
    if old_nav and old_nav > 0:
        return round((new_nav / old_nav - 1) * 100, 2)
    return None


def _annualised(rsi, inception_str):
    if rsi is None or not inception_str:
        return None
    try:
        # Handle formats: "24-Oct-2025", "24 Oct 2025", "Oct 24, 2025"
        s = str(inception_str).strip()
        d = None
        for fmt in ("%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                d = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if not d:
            return None
        years = (datetime.now() - d).days / 365.25
        if years <= 0: return None
        return round((math.pow(1 + rsi / 100, 1 / years) - 1) * 100, 2)
    except Exception:
        return None


def refresh():
    global _live_navs, _nav_date, _last_updated, ISIN_MAP

    log.info("Refreshing AMFI data...")
    try:
        raw = _fetch_amfi()
    except Exception as e:
        log.error(f"AMFI fetch failed: {e}")
        return

    # Parse all schemes from AMFI
    all_schemes = []
    isin_lookup = {}
    for tb in raw.get("data", []):
        for cat in tb.get("categories", []):
            for g in cat.get("groups", []):
                for s in g.get("schemes", []):
                    nav = float(s.get("NetAssetValue") or 0)
                    if nav > 0 and s.get("Date"):
                        scheme = {
                            "isinPO": s.get("ISINPO", ""),
                            "isinRI": s.get("ISINRI", ""),
                            "amc":    s.get("SIFName", ""),
                            "cat_str":s.get("category", ""),
                            "name":   s.get("NavName", ""),
                            "nav":    nav,
                            "date":   s.get("Date", ""),
                        }
                        all_schemes.append(scheme)
                        if scheme["isinPO"]: isin_lookup[scheme["isinPO"]] = scheme
                        if scheme["isinRI"]: isin_lookup[scheme["isinRI"]] = scheme

    # Update NAVs for known funds + track month changes
    new_navs = {}
    latest_date = None
    for fid, isin in ISIN_MAP.items():
        rec = isin_lookup.get(isin)
        if rec:
            new_navs[isin] = {"nav": rec["nav"], "date": rec["date"]}
            if latest_date is None or rec["date"] > latest_date:
                latest_date = rec["date"]
            # Track month transitions to compute monthly returns
            f = FUND_REGISTRY.get(fid, {})
            mk = _month_key(rec["date"])
            prev_mk = _month_key(f.get("prev_date", ""))
            if mk and prev_mk and mk != prev_mk:
                prev_nav = f.get("prev_nav")
                if prev_nav and prev_nav > 0:
                    ret = _pct(rec["nav"], prev_nav)
                    f.setdefault("monthly", {})[prev_mk] = ret
                    log.info(f"Auto-computed {prev_mk} return for {fid}: {ret}%")
            f["prev_nav"] = rec["nav"]
            f["prev_date"] = rec["date"]

    # ── Fetch index fund NAVs from AMFI NAVAll.txt ──
    try:
        nav_url = "https://www.amfiindia.com/spages/NAVAll.txt"
        nav_req = urllib.request.Request(nav_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(nav_req, timeout=20) as nr:
            nav_text = nr.read().decode('utf-8', errors='ignore')
        
        # Build ISIN -> NAV lookup from NAVAll.txt
        # Format: SchemeCode;ISIN1;ISIN2;SchemeName;NAV;Date
        nav_lookup = {}
        for line in nav_text.split('\n'):
            parts = line.strip().split(';')
            if len(parts) >= 6:
                isin1, isin2 = parts[1].strip(), parts[2].strip()
                try:
                    nav_val = float(parts[4].strip())
                    nav_date_str = parts[5].strip()
                    if nav_val > 0:
                        if isin1 and isin1 != '-': nav_lookup[isin1] = (nav_val, nav_date_str)
                        if isin2 and isin2 != '-': nav_lookup[isin2] = (nav_val, nav_date_str)
                except: pass
        
        # Update each index fund's monthly returns
        for idx_name, idx_info in INDEX_FUNDS.items():
            isin = idx_info["isin"]
            rec = nav_lookup.get(isin)
            if not rec: continue
            new_nav, new_date = rec
            mk = _month_key(new_date)
            prev = _index_navs.get(idx_name, {})
            prev_mk = _month_key(prev.get("prev_date", ""))
            
            if mk and prev_mk and mk != prev_mk:
                prev_nav = prev.get("prev_nav")
                if prev_nav and prev_nav > 0:
                    ret = _pct(new_nav, prev_nav)
                    monthly = prev.get("monthly", {})
                    monthly[prev_mk] = ret
                    _index_navs[idx_name] = {**prev, "monthly": monthly, "prev_nav": new_nav, "prev_date": new_date}
                    log.info(f"Index return computed: {idx_name} {prev_mk} = {ret}%")
            else:
                if idx_name not in _index_navs:
                    _index_navs[idx_name] = {"monthly": {}, "prev_nav": new_nav, "prev_date": new_date}
                else:
                    _index_navs[idx_name]["prev_nav"] = new_nav
                    _index_navs[idx_name]["prev_date"] = new_date
        
        log.info(f"Index fund NAVs updated: {len([k for k in _index_navs if _index_navs[k].get('monthly')])} with monthly data")
    except Exception as e:
        log.warning(f"Index fund NAV fetch failed: {e}")

    # Auto-detect new funds
    known_prefixes = {}
    for fid, isin in ISIN_MAP.items():
        cat = FUND_REGISTRY.get(fid, {}).get("cat", "hybrid")
        known_prefixes[isin[:8] + "|" + cat] = fid

    for s in all_schemes:
        isin = s["isinPO"] or s["isinRI"]
        if not isin: continue
        if re.search(r"direct", s["name"], re.I): continue
        if not re.search(r"growth", s["name"], re.I): continue
        if re.search(r"idcw|dividend|payout|reinvest", s["name"], re.I): continue

        cat = _map_cat(s["cat_str"])
        key = isin[:8] + "|" + cat
        if key in known_prefixes: continue

        # NFO upgrade check
        brand = s["name"].split()[0].lower()
        nfo_fid = next(
            (fid for fid, f in FUND_REGISTRY.items()
             if f.get("nfo") and f.get("cat") == cat
             and brand in (f.get("name") or "").lower()),
            None
        )
        if nfo_fid:
            FUND_REGISTRY[nfo_fid]["nfo"] = False
            ISIN_MAP[nfo_fid] = isin
            new_navs[isin] = {"nav": s["nav"], "date": s["date"]}
            known_prefixes[key] = nfo_fid
            log.info(f"NFO went live: {nfo_fid}")
        else:
            clean = re.sub(r"\s*-?\s*(regular|direct)\s*plan?\s*-?", "", s["name"], flags=re.I)
            clean = re.sub(r"\s*-?\s*(growth|idcw|dividend)\s*(option)?\s*-?", "", clean, flags=re.I)
            clean = re.sub(r"\s{2,}", " ", clean).strip(" -")
            fid = "auto-" + re.sub(r"[^a-z0-9]+", "-", (s["amc"] or "unk").lower()) + "-" + cat
            if fid not in FUND_REGISTRY:
                FUND_REGISTRY[fid] = {
                    "name": clean or s["name"], "amc": s["amc"],
                    "brand": s["name"].split()[0], "cat": cat,
                    "nfo": False, "auto_detected": True,
                    "compMF": COMP_MF_MAP.get(cat),
                    "fm": None, "fmYrs": None, "inception": None,
                    "inceptionDate": None, "bench": None, "er": None,
                    "aum": None, "riskLevel": None, "exitLoad": None,
                    "liq": None, "minHorizon": None, "purpose": None,
                    "strategy": None, "monthly": {}, "rsi": None,
                    "r1m": None, "r3m": None, "r6m": None, "r1y": None,
                    "navBase": False,
                }
                ISIN_MAP[fid] = isin
                new_navs[isin] = {"nav": s["nav"], "date": s["date"]}
                known_prefixes[key] = fid
                log.info(f"NEW FUND AUTO-DETECTED: {clean} ({s['amc']})")

    # Recompute all returns from monthly data
    months_list = list(NIFTY.keys())
    for fid, f in FUND_REGISTRY.items():
        if f.get("nfo"): continue
        monthly = f.get("monthly") or {}
        cum = 1.0; n = 0
        for m in months_list:
            v = monthly.get(m)
            if v is not None:
                cum *= (1 + v / 100); n += 1
        if n > 0:
            f["rsi"] = round((cum - 1) * 100, 2)
        if months_list:
            f["r1m"] = monthly.get(months_list[-1])
        if len(months_list) >= 3:
            c = 1.0
            for m in months_list[-3:]:
                v = monthly.get(m)
                if v is not None: c *= (1 + v / 100)
            f["r3m"] = round((c - 1) * 100, 2)
        if len(months_list) >= 6:
            c = 1.0
            for m in months_list[-6:]:
                v = monthly.get(m)
                if v is not None: c *= (1 + v / 100)
            f["r6m"] = round((c - 1) * 100, 2)
        f["ann"] = _annualised(f.get("rsi"), f.get("inception"))

    with _lock:
        _live_navs = new_navs
        _nav_date = latest_date
        _last_updated = datetime.now().isoformat()

    log.info(f"Refresh done: {len(new_navs)} NAVs, date={latest_date}")


def _refresh_loop():
    while True:
        try:
            refresh()
        except Exception as e:
            log.error(f"Refresh loop error: {e}")
        time.sleep(1800)


# ================================================================
# API ROUTES
# ================================================================

@app.route("/api/data")
def api_data():
    with _lock:
        navs = dict(_live_navs)
        nav_date = _nav_date
        last_updated = _last_updated

    # Derive months from fund monthly data, sorted chronologically
    from datetime import datetime as _dt
    def _mk_sort(mk):
        try: return _dt.strptime(mk, '%b-%y')
        except: return _dt.min
    all_months = set()
    for f in FUND_REGISTRY.values():
        all_months.update((f.get('monthly') or {}).keys())
    months = sorted(all_months, key=_mk_sort)
    funds_out = []
    for fid, f in FUND_REGISTRY.items():
        isin = ISIN_MAP.get(fid)
        live = navs.get(isin) if isin else None
        cat = f.get("cat", "hybrid")
        funds_out.append({
            "id": fid,
            "name": f.get("name", ""),
            "amc": f.get("amc", ""),
            "brand": f.get("brand", ""),
            "cat": cat,
            "catLabel": CAT_LABELS.get(cat, cat),
            "nav": live["nav"] if live else None,
            "navDate": live["date"] if live else None,
            "navLive": bool(live),
            "navBase": f.get("navBase", False),
            "nfo": f.get("nfo", False),
            "autoDetected": f.get("auto_detected", False),
            "rsi": f.get("rsi"),
            "r1m": f.get("r1m"),
            "r3m": f.get("r3m"),
            "r6m": f.get("r6m"),
            "r1y": f.get("r1y"),
            "ann": f.get("ann"),
            "monthly": f.get("monthly") or {},
            "fm": f.get("fm"),
            "fmYrs": f.get("fmYrs"),
            "inception": f.get("inception"),
            "inceptionDate": f.get("inceptionDate"),
            "bench": f.get("bench"),
            "er": f.get("er"),
            "aum": f.get("aum"),
            "riskLevel": f.get("riskLevel"),
            "exitLoad": f.get("exitLoad"),
            "liq": f.get("liq"),
            "minHorizon": f.get("minHorizon"),
            "purpose": f.get("purpose"),
            "strategy": f.get("strategy"),
            "compMF": COMP_MF_OVERRIDE.get(fid) or f.get("compMF") or COMP_MF_MAP.get(cat),
        })

    # Compute stats server-side so frontend always shows live numbers
    live_funds = [f for f in funds_out if not f.get('nfo')]
    aum_total = sum(f.get('aum') or 0 for f in live_funds)
    rsi_vals = [f['rsi'] for f in live_funds if f.get('rsi') is not None]
    avg_rsi = round(sum(rsi_vals) / len(rsi_vals), 2) if rsi_vals else 0
    amcs = len(set(f['amc'] for f in live_funds))
    cats = len(set(f['cat'] for f in live_funds))
    nfo_count = len([f for f in funds_out if f.get('nfo')])

    # Build index monthly returns for frontend
    index_data = {}
    with _lock:
        idx_snap = dict(_index_navs)
    for idx_name, idx_info in idx_snap.items():
        index_data[idx_name] = {
            "label": INDEX_FUNDS[idx_name]["label"],
            "monthly": idx_info.get("monthly", {}),
        }

    return jsonify({
        "funds": funds_out,
        "months": months,
        "nifty": {},  # kept for compatibility
        "indices": index_data,
        "catBenchmark": CAT_BENCHMARK,
        "navDate": nav_date,
        "lastUpdated": last_updated,
        "stats": {
            "liveSIFs": len(live_funds),
            "nfoCount": nfo_count,
            "amcs": amcs,
            "aumCr": round(aum_total, 1),
            "categories": cats,
            "avgRsi": avg_rsi,
        }
    })


@app.route("/ping")
def ping():
    return "ok", 200


@app.route("/")
@app.route("/index.html")
def index():
    return send_file("index.html")


# ================================================================
# STARTUP
# ================================================================

def _compute_static_returns():
    """Compute annualised returns from registry data on startup,
    before first AMFI fetch completes."""
    from datetime import datetime as _dt2
    def _mk2(mk):
        try: return _dt2.strptime(mk, '%b-%y')
        except: return _dt2.min
    all_m = set()
    for f in FUND_REGISTRY.values():
        all_m.update((f.get('monthly') or {}).keys())
    months_list = sorted(all_m, key=_mk2)
    for fid, f in FUND_REGISTRY.items():
        if f.get('nfo'): continue
        # Compute annualised from existing rsi
        f['ann'] = _annualised(f.get('rsi'), f.get('inception'))
        # Compute 1M, 3M from monthly data
        monthly = f.get('monthly') or {}
        if months_list:
            f['r1m'] = monthly.get(months_list[-1])
        if len(months_list) >= 3:
            c = 1.0
            for m in months_list[-3:]:
                v = monthly.get(m)
                if v is not None: c *= (1 + v/100)
            f['r3m'] = round((c-1)*100, 2)
        if len(months_list) >= 6:
            c = 1.0
            for m in months_list[-6:]:
                v = monthly.get(m)
                if v is not None: c *= (1 + v/100)
            f['r6m'] = round((c-1)*100, 2)

def _startup():
    _compute_static_returns()  # instant, no network needed
    refresh()                  # fetch live NAVs from AMFI
    threading.Thread(target=_refresh_loop, daemon=True).start()


_startup()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
