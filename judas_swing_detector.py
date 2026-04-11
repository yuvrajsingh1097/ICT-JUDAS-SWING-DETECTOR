"""
ICT Judas Swing Detector
========================
Detects fake liquidity raids (Judas Swings) at London & New York session opens.

ICT Concept:
  At session open, price makes a DECEPTIVE move (the "Judas") to grab liquidity
  above/below the previous session's high/low — then REVERSES violently in the
  TRUE direction for the session.

  Pattern:
    1. Identify Previous Session High/Low (Asia range for London; London range for NY)
    2. At session open, price BREAKS above/below that range (the raid)
    3. Within N candles it REVERSES and closes back INSIDE the range
    4. That's the Judas Swing — a trap entry signal

Author : Your Name
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.gridspec as gridspec
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────
LONDON_OPEN_HOUR  = 8    # UTC
NY_OPEN_HOUR      = 13   # UTC
ASIA_START_HOUR   = 0
LONDON_START_HOUR = 8
NY_START_HOUR     = 13

RAID_REVERSAL_CANDLES = 4   # must reverse within this many candles
MIN_RAID_PIPS         = 3   # minimum wick beyond range to count as raid (pips)
PIP                   = 0.0001

# ─────────────────────────────────────────────────────────
#  1. GENERATE REALISTIC EURUSD 15M DATA
# ─────────────────────────────────────────────────────────
def generate_15m_data(days=5, seed=7):
    np.random.seed(seed)
    periods = days * 24 * 4          # 15-min candles per day
    dates   = pd.date_range("2024-03-04 00:00", periods=periods, freq="15min")

    price = 1.0850
    opens, highs, lows, closes = [], [], [], []

    for i, ts in enumerate(dates):
        hour = ts.hour

        # Session-based volatility + drift
        if LONDON_OPEN_HOUR <= hour < NY_OPEN_HOUR:
            vol, drift = 0.0014, np.random.choice([-1, 1]) * 0.00004
        elif NY_OPEN_HOUR <= hour < 20:
            vol, drift = 0.0016, np.random.choice([-1, 1]) * 0.00005
        else:
            vol, drift = 0.0006, 0.0

        # Judas spike injection at session opens (first 1-2 candles)
        is_london_open = (ts.hour == LONDON_OPEN_HOUR and ts.minute < 30)
        is_ny_open     = (ts.hour == NY_OPEN_HOUR     and ts.minute < 30)

        if is_london_open and np.random.rand() < 0.6:
            spike_dir = np.random.choice([-1, 1])
            spike     = spike_dir * np.random.uniform(0.0008, 0.0025)
        elif is_ny_open and np.random.rand() < 0.55:
            spike_dir = np.random.choice([-1, 1])
            spike     = spike_dir * np.random.uniform(0.0010, 0.0030)
        else:
            spike_dir, spike = 0, 0

        o  = price
        c  = o + np.random.normal(drift, vol * 0.4) - spike * 0.7
        h  = max(o, c) + abs(np.random.normal(0, vol * 0.3)) + max(0,  spike)
        l  = min(o, c) - abs(np.random.normal(0, vol * 0.3)) + min(0,  spike)

        opens.append(round(o, 5))
        highs.append(round(h, 5))
        lows.append(round(l, 5))
        closes.append(round(c, 5))
        price = c

    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=dates)


# ─────────────────────────────────────────────────────────
#  2. BUILD SESSION RANGES
# ─────────────────────────────────────────────────────────
def get_session_ranges(df):
    """Return Asia and London range (high/low) for each UTC date."""
    ranges = {}
    for date, day_df in df.groupby(df.index.date):
        asia   = day_df[(day_df.index.hour >= ASIA_START_HOUR)   & (day_df.index.hour < LONDON_START_HOUR)]
        london = day_df[(day_df.index.hour >= LONDON_START_HOUR) & (day_df.index.hour < NY_START_HOUR)]
        ranges[date] = {
            "asia_high"  : asia["high"].max()   if not asia.empty   else np.nan,
            "asia_low"   : asia["low"].min()    if not asia.empty   else np.nan,
            "london_high": london["high"].max() if not london.empty else np.nan,
            "london_low" : london["low"].min()  if not london.empty else np.nan,
        }
    return ranges


# ─────────────────────────────────────────────────────────
#  3. DETECT JUDAS SWINGS
# ─────────────────────────────────────────────────────────
def detect_judas_swings(df, session_ranges):
    judas_events = []

    dates = sorted(session_ranges.keys())

    for date in dates:
        sr   = session_ranges[date]
        day_df = df[df.index.date == date]

        # ── London open Judas (raids Asia range) ──
        london_candles = day_df[(day_df.index.hour >= LONDON_OPEN_HOUR) &
                                (day_df.index.hour <  LONDON_OPEN_HOUR + 2)]

        asia_high = sr["asia_high"]
        asia_low  = sr["asia_low"]

        for i in range(len(london_candles) - RAID_REVERSAL_CANDLES):
            row = london_candles.iloc[i]

            # Bullish Judas: spike BELOW asia low then reverses UP
            if (not np.isnan(asia_low) and
                    row["low"] < asia_low - MIN_RAID_PIPS * PIP and
                    row["close"] > asia_low):
                raid_pips = round((asia_low - row["low"]) / PIP, 1)
                judas_events.append({
                    "time"       : row.name,
                    "session"    : "London",
                    "type"       : "Bullish Judas",
                    "range_level": asia_low,
                    "spike_low"  : row["low"],
                    "spike_high" : row["high"],
                    "raid_pips"  : raid_pips,
                    "bias"       : "LONG",
                    "open"       : row["open"],
                    "close"      : row["close"],
                })

            # Bearish Judas: spike ABOVE asia high then reverses DOWN
            if (not np.isnan(asia_high) and
                    row["high"] > asia_high + MIN_RAID_PIPS * PIP and
                    row["close"] < asia_high):
                raid_pips = round((row["high"] - asia_high) / PIP, 1)
                judas_events.append({
                    "time"       : row.name,
                    "session"    : "London",
                    "type"       : "Bearish Judas",
                    "range_level": asia_high,
                    "spike_low"  : row["low"],
                    "spike_high" : row["high"],
                    "raid_pips"  : raid_pips,
                    "bias"       : "SHORT",
                    "open"       : row["open"],
                    "close"      : row["close"],
                })

        # ── NY open Judas (raids London range) ──
        ny_candles = day_df[(day_df.index.hour >= NY_OPEN_HOUR) &
                            (day_df.index.hour <  NY_OPEN_HOUR + 2)]

        lon_high = sr["london_high"]
        lon_low  = sr["london_low"]

        for i in range(len(ny_candles) - RAID_REVERSAL_CANDLES):
            row = ny_candles.iloc[i]

            if (not np.isnan(lon_low) and
                    row["low"] < lon_low - MIN_RAID_PIPS * PIP and
                    row["close"] > lon_low):
                raid_pips = round((lon_low - row["low"]) / PIP, 1)
                judas_events.append({
                    "time"       : row.name,
                    "session"    : "NY",
                    "type"       : "Bullish Judas",
                    "range_level": lon_low,
                    "spike_low"  : row["low"],
                    "spike_high" : row["high"],
                    "raid_pips"  : raid_pips,
                    "bias"       : "LONG",
                    "open"       : row["open"],
                    "close"      : row["close"],
                })

            if (not np.isnan(lon_high) and
                    row["high"] > lon_high + MIN_RAID_PIPS * PIP and
                    row["close"] < lon_high):
                raid_pips = round((row["high"] - lon_high) / PIP, 1)
                judas_events.append({
                    "time"       : row.name,
                    "session"    : "NY",
                    "type"       : "Bearish Judas",
                    "range_level": lon_high,
                    "spike_low"  : row["low"],
                    "spike_high" : row["high"],
                    "raid_pips"  : raid_pips,
                    "bias"       : "SHORT",
                    "open"       : row["open"],
                    "close"      : row["close"],
                })

    return pd.DataFrame(judas_events)


# ─────────────────────────────────────────────────────────
#  4. PLOT
# ─────────────────────────────────────────────────────────
def plot_judas(df, judas_df, session_ranges, plot_day="2024-03-05"):
    day_df = df[df.index.date == pd.Timestamp(plot_day).date()]
    sr     = session_ranges[pd.Timestamp(plot_day).date()]
    day_judas = judas_df[judas_df["time"].dt.date == pd.Timestamp(plot_day).date()] \
                if not judas_df.empty else pd.DataFrame()

    fig = plt.figure(figsize=(18, 9))
    fig.patch.set_facecolor("#0d1117")

    gs  = gridspec.GridSpec(2, 1, height_ratios=[4, 1], hspace=0.08)
    ax  = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax)

    for a in [ax, ax2]:
        a.set_facecolor("#0d1117")
        for sp in a.spines.values():
            sp.set_edgecolor("#30363d")

    x_map = {ts: i for i, ts in enumerate(day_df.index)}
    xs    = np.arange(len(day_df))

    # ── Session backgrounds ──
    session_colors = {
        "Asia"  : "#1a2433",
        "London": "#1a2820",
        "NY"    : "#2a1a1a",
        "Close" : "#1a1a2a",
    }
    for i, (ts, _) in enumerate(day_df.iterrows()):
        h = ts.hour
        if h < LONDON_START_HOUR:
            col = session_colors["Asia"]
        elif h < NY_START_HOUR:
            col = session_colors["London"]
        elif h < 20:
            col = session_colors["NY"]
        else:
            col = session_colors["Close"]
        ax.axvspan(i - 0.5, i + 0.5, color=col, alpha=0.5, zorder=0)

    # ── Asia range band ──
    if not np.isnan(sr["asia_high"]) and not np.isnan(sr["asia_low"]):
        ax.axhline(sr["asia_high"], color="#5090d0", lw=1.1, ls="--", alpha=0.8, zorder=1)
        ax.axhline(sr["asia_low"],  color="#5090d0", lw=1.1, ls="--", alpha=0.8, zorder=1)
        ax.fill_between(xs, sr["asia_low"], sr["asia_high"],
                        color="#5090d0", alpha=0.06, zorder=1)
        ax.text(1, sr["asia_high"] + 0.00005, "Asia High", color="#5090d0",
                fontsize=8, va="bottom")
        ax.text(1, sr["asia_low"]  - 0.00008, "Asia Low",  color="#5090d0",
                fontsize=8, va="top")

    # ── London range band ──
    if not np.isnan(sr["london_high"]) and not np.isnan(sr["london_low"]):
        ax.axhline(sr["london_high"], color="#f0a040", lw=1.1, ls="--", alpha=0.7, zorder=1)
        ax.axhline(sr["london_low"],  color="#f0a040", lw=1.1, ls="--", alpha=0.7, zorder=1)
        ax.text(len(day_df) - 2, sr["london_high"] + 0.00005,
                "London High", color="#f0a040", fontsize=8, va="bottom", ha="right")
        ax.text(len(day_df) - 2, sr["london_low"]  - 0.00008,
                "London Low",  color="#f0a040", fontsize=8, va="top",    ha="right")

    # ── Candlesticks ──
    for i, (ts, row) in enumerate(day_df.iterrows()):
        bull = row["close"] >= row["open"]
        body_col  = "#26a69a" if bull else "#ef5350"
        wick_col  = "#1a7a74" if bull else "#b03030"
        ax.plot([i, i], [row["low"], row["high"]], color=wick_col, lw=0.9, zorder=3)
        bot = min(row["open"], row["close"])
        h   = max(abs(row["close"] - row["open"]), 0.000025)
        rect = mpatches.FancyBboxPatch(
            (i - 0.3, bot), 0.6, h,
            boxstyle="square,pad=0", color=body_col, zorder=4
        )
        ax.add_patch(rect)

    # ── Judas swing markers ──
    for _, ev in day_judas.iterrows():
        xi = x_map.get(ev["time"])
        if xi is None:
            continue
        is_bull = ev["bias"] == "LONG"
        marker_y = ev["spike_low"] - 0.00015 if is_bull else ev["spike_high"] + 0.00015
        ax.annotate(
            f"⚡ {ev['session']}\n{ev['type']}\n{ev['raid_pips']}p raid",
            xy=(xi, ev["spike_low"] if is_bull else ev["spike_high"]),
            xytext=(xi, marker_y),
            color="#ffe066" if is_bull else "#ff6b6b",
            fontsize=7.5, fontweight="bold", ha="center",
            arrowprops=dict(arrowstyle="-|>", color="#ffe066" if is_bull else "#ff6b6b",
                            lw=1.2),
            zorder=6
        )
        ax.scatter(xi, ev["spike_low"] if is_bull else ev["spike_high"],
                   marker="v" if is_bull else "^",
                   color="#ffe066" if is_bull else "#ff6b6b",
                   s=80, zorder=7)

    # ── Session open verticals ──
    for i, (ts, _) in enumerate(day_df.iterrows()):
        if ts.hour == LONDON_OPEN_HOUR and ts.minute == 0:
            ax.axvline(i, color="#4caf50", lw=1.5, ls=":", alpha=0.9, zorder=2)
            ax.text(i + 0.3, ax.get_ylim()[1] if ax.get_ylim()[1] else day_df["high"].max(),
                    "London Open", color="#4caf50", fontsize=8, va="top", rotation=90)
        if ts.hour == NY_OPEN_HOUR and ts.minute == 0:
            ax.axvline(i, color="#ff9800", lw=1.5, ls=":", alpha=0.9, zorder=2)
            ax.text(i + 0.3, ax.get_ylim()[1] if ax.get_ylim()[1] else day_df["high"].max(),
                    "NY Open", color="#ff9800", fontsize=8, va="top", rotation=90)

    # ── Bottom panel: session tag ──
    session_tag_colors = {"Asia": "#5090d0", "London": "#4caf50", "NY": "#ff9800", "Close": "#888888"}
    prev_session = None
    for i, (ts, _) in enumerate(day_df.iterrows()):
        h = ts.hour
        if h < LONDON_START_HOUR:           sess = "Asia"
        elif h < NY_START_HOUR:             sess = "London"
        elif h < 20:                        sess = "NY"
        else:                               sess = "Close"
        ax2.bar(i, 1, color=session_tag_colors[sess], width=1.0, align="center", alpha=0.7)
        if sess != prev_session:
            ax2.text(i + 0.5, 0.5, sess, color="white", fontsize=7,
                     va="center", ha="left", fontweight="bold")
        prev_session = sess

    ax2.set_ylim(0, 1)
    ax2.set_yticks([])
    ax2.set_ylabel("Session", color="#8b949e", fontsize=8)

    # ── X-axis ──
    tick_step = max(1, len(day_df) // 12)
    xticks  = xs[::tick_step]
    xlabels = [day_df.index[i].strftime("%H:%M") for i in xticks]
    ax2.set_xticks(xticks)
    ax2.set_xticklabels(xlabels, rotation=30, ha="right", color="#8b949e", fontsize=8)
    ax.tick_params(labelbottom=False, colors="#8b949e")
    ax.yaxis.set_tick_params(colors="#8b949e", labelsize=8)
    ax.yaxis.set_major_formatter(plt.FormatStrFormatter("%.4f"))
    ax.grid(color="#21262d", ls="--", lw=0.5, zorder=0)

    # ── Title ──
    ax.set_title(f"ICT Judas Swing Detector  —  EUR/USD 15M  |  {plot_day}",
                 color="#e6edf3", fontsize=14, fontweight="bold", pad=12)

    # ── Legend ──
    handles = [
        mlines.Line2D([], [], color="#5090d0", ls="--", label="Asia Range"),
        mlines.Line2D([], [], color="#f0a040", ls="--", label="London Range"),
        mpatches.Patch(color="#ffe066", label="Bullish Judas (Long Bias)"),
        mpatches.Patch(color="#ff6b6b", label="Bearish Judas (Short Bias)"),
    ]
    ax.legend(handles=handles, facecolor="#161b22", edgecolor="#30363d",
              labelcolor="#e6edf3", fontsize=8, loc="upper right")

    plt.tight_layout()
    plt.savefig("output.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.show()
    print("✅  Chart saved → output.png")


# ─────────────────────────────────────────────────────────
#  5. SUMMARY
# ─────────────────────────────────────────────────────────
def print_summary(judas_df):
    print("\n" + "=" * 60)
    print("  ICT Judas Swing Detector — Results")
    print("=" * 60)
    if judas_df.empty:
        print("  No Judas Swings detected.")
        return
    total   = len(judas_df)
    bull    = len(judas_df[judas_df["bias"] == "LONG"])
    bear    = len(judas_df[judas_df["bias"] == "SHORT"])
    london  = len(judas_df[judas_df["session"] == "London"])
    ny      = len(judas_df[judas_df["session"] == "NY"])
    print(f"  Total Judas Swings detected : {total}")
    print(f"  Bullish (Long Bias)         : {bull}")
    print(f"  Bearish (Short Bias)        : {bear}")
    print(f"  London Session              : {london}")
    print(f"  NY Session                  : {ny}")
    print(f"\n  Avg Raid Size               : {judas_df['raid_pips'].mean():.1f} pips")
    print(f"  Max Raid Size               : {judas_df['raid_pips'].max():.1f} pips")
    print()
    print(judas_df[["time", "session", "type", "raid_pips", "bias"]].to_string(index=False))
    print("=" * 60)


# ─────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("📊  Generating EUR/USD 15M data (5 days)...")
    df = generate_15m_data(days=6, seed=7)

    print("🔍  Building session ranges...")
    session_ranges = get_session_ranges(df)

    print("⚡  Detecting Judas Swing patterns...")
    judas_df = detect_judas_swings(df, session_ranges)

    print_summary(judas_df)

    # Plot one specific day
    plot_day = "2024-03-05"
    print(f"\n🎨  Plotting {plot_day}...")
    plot_judas(df, judas_df, session_ranges, plot_day=plot_day)