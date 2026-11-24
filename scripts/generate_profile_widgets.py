#!/usr/bin/env python3
"""Generate dynamic Code Pet and 3D Contribution City SVGs (dark & light) for a GitHub profile."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import random
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

LANG_META: dict[str, tuple[str, str]] = {
    "Python": ("#3572A5", "PY"),
    "TypeScript": ("#3178C6", "TS"),
    "JavaScript": ("#F1E05A", "JS"),
    "HTML": ("#E34C26", "5"),
    "Dart": ("#00B4AB", "DT"),
    "C++": ("#F34B7D", "C+"),
    "C": ("#555555", "C"),
    "PHP": ("#4F5D95", "PHP"),
    "Java": ("#B07219", "JV"),
    "Shell": ("#89E051", "SH"),
    "Go": ("#00ADD8", "GO"),
    "Rust": ("#DEA584", "RS"),
    "CSS": ("#663399", "CS"),
}


def http_json(url: str, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> Any:
    req_headers = {"User-Agent": "bimadji-profile-widget-generator/1.0", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_via_graphql(username: str, token: str) -> tuple[list[list[dict[str, Any]]], list[tuple[str, str]]]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                weekday
              }
            }
          }
        }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
          nodes {
            languages(first: 8, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node {
                  name
                  color
                }
              }
            }
          }
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"login": username}}).encode("utf-8")
    res = http_json(
        "https://api.github.com/graphql",
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        body=payload,
    )
    user = res["data"]["user"]
    raw_weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    weeks: list[list[dict[str, Any]]] = []
    for w in raw_weeks[-53:]:
        days = [
            {"date": d["date"], "count": int(d["contributionCount"]), "weekday": int(d["weekday"])}
            for d in w["contributionDays"]
        ]
        weeks.append(days)

    lang_sizes: dict[str, int] = {}
    lang_colors: dict[str, str] = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo.get("languages", {}).get("edges", []):
            name = edge["node"]["name"]
            color = edge["node"].get("color") or LANG_META.get(name, ("#64748B", name[:2].upper()))[0]
            lang_sizes[name] = lang_sizes.get(name, 0) + int(edge["size"])
            lang_colors[name] = color

    return weeks, select_top_languages(lang_sizes, lang_colors)


def select_top_languages(lang_scores: dict[str, int], lang_colors: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Prefer programming languages over pure markup (HTML/CSS) when 4+ languages exist."""
    markup = {"HTML", "CSS"}
    ordered = sorted(lang_scores.items(), key=lambda kv: kv[1], reverse=True)
    code_first = [kv for kv in ordered if kv[0] not in markup] + [kv for kv in ordered if kv[0] in markup]
    result: list[tuple[str, str]] = []
    for name, _ in code_first[:4]:
        color = (lang_colors or {}).get(name) or LANG_META.get(name, ("#64748B", name[:2].upper()))[0]
        result.append((name, color))
    return result


def group_flat_days_into_weeks(flat_days: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    sorted_days = sorted(flat_days, key=lambda x: x["date"])
    weeks: list[list[dict[str, Any]]] = []
    current_week: list[dict[str, Any]] = []
    for item in sorted_days:
        d_obj = dt.date.fromisoformat(item["date"])
        weekday_sun0 = (d_obj.weekday() + 1) % 7  # Sun=0 .. Sat=6
        if weekday_sun0 == 0 and current_week:
            weeks.append(current_week)
            current_week = []
        current_week.append({"date": item["date"], "count": int(item["count"]), "weekday": weekday_sun0})
    if current_week:
        weeks.append(current_week)
    return weeks[-53:]


def score_repos_languages(repos: list[dict[str, Any]]) -> dict[str, int]:
    lang_weights: dict[str, int] = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        lang = repo.get("language")
        if lang:
            bounded_kb = min(max(int(repo.get("size") or 1), 1), 600)
            lang_weights[lang] = lang_weights.get(lang, 0) + 1000 + bounded_kb
    return lang_weights


def fetch_public_fallback(username: str) -> tuple[list[list[dict[str, Any]]], list[tuple[str, str]]]:
    contrib_data = http_json(f"https://github-contributions-api.jogruber.de/v4/{urllib.parse.quote(username)}?y=last")
    weeks = group_flat_days_into_weeks(contrib_data.get("contributions", []))

    repos = http_json(f"https://api.github.com/users/{urllib.parse.quote(username)}/repos?per_page=100&sort=updated")
    return weeks, select_top_languages(score_repos_languages(repos))


def load_from_files(contribs_file: Path, repos_file: Path | None) -> tuple[list[list[dict[str, Any]]], list[tuple[str, str]]]:
    raw = json.loads(contribs_file.read_text(encoding="utf-8"))
    weeks = group_flat_days_into_weeks(raw.get("contributions", []))

    top_langs: list[tuple[str, str]] = []
    if repos_file and repos_file.exists():
        repos = json.loads(repos_file.read_text(encoding="utf-8"))
        top_langs = select_top_languages(score_repos_languages(repos))
    return weeks, top_langs


def compute_metrics(weeks: list[list[dict[str, Any]]]) -> dict[str, Any]:
    all_days = [d for w in weeks for d in w]
    # Trailing 365 days for headline annual totals
    trailing_days = all_days[-365:] if len(all_days) > 365 else all_days
    total_contributions = sum(d["count"] for d in all_days)
    active_days = sum(1 for d in all_days if d["count"] > 0)
    busiest_day = max((d["count"] for d in all_days), default=0)

    eval_weeks = weeks[-52:] if len(weeks) > 52 else weeks
    week_totals = [sum(d["count"] for d in w) for w in eval_weeks]
    active_weeks = sum(1 for total in week_totals if total > 0)

    # Consecutive active weeks (allow current incomplete week to carry streak from prior week)
    streak = 0
    idx = len(week_totals) - 1
    if idx >= 0 and week_totals[idx] == 0 and len(eval_weeks[idx]) < 7:
        idx -= 1
    while idx >= 0 and week_totals[idx] > 0:
        streak += 1
        idx -= 1

    recent_14d = sum(d["count"] for d in trailing_days[-14:])
    if recent_14d == 0:
        stage = "resting"
    elif active_weeks >= 45 or total_contributions >= 1200:
        stage = "vivid"
    elif active_weeks >= 26 or total_contributions >= 700:
        stage = "active"
    elif total_contributions >= 100 or active_weeks >= 5:
        stage = "young"
    else:
        stage = "hatchling"

    return {
        "total": total_contributions,
        "active_days": active_days,
        "busiest_day": busiest_day,
        "active_weeks": active_weeks,
        "streak_weeks": streak,
        "stage": stage,
    }


def render_language_icon(name: str, x: float, y: float, color: str) -> str:
    """Render a crisp 14x14 mini emblem inside each language pill."""
    _, code = LANG_META.get(name, (color, name[:2].upper()))
    text_fill = "#081018" if name in {"JavaScript", "Shell", "Dart"} else "#FFFFFF"
    font_size = "7.5" if len(code) <= 2 else "6.2"
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="15" height="15" rx="3.5" fill="{color}"/>'
        f'<text x="{x + 7.5:.1f}" y="{y + 10.3:.1f}" text-anchor="middle" '
        f'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
        f'font-size="{font_size}" font-weight="800" fill="{text_fill}">{html.escape(code)}</text>'
    )


def render_code_pet_svg(
    username: str,
    metrics: dict[str, Any],
    top_langs: list[tuple[str, str]],
    mode: str = "dark",
) -> str:
    is_dark = mode == "dark"
    stage = metrics["stage"]
    total = metrics["total"]
    active_weeks = metrics["active_weeks"]
    streak = min(metrics["streak_weeks"], 13)

    if not top_langs:
        top_langs = [("Python", "#3572A5"), ("TypeScript", "#3178C6"), ("HTML", "#E34C26"), ("Dart", "#00B4AB")]

    # Theme palette (WCAG AA compliant in both dark & light modes)
    if is_dark:
        card_bg = "#0B0F14"
        card_stroke = "#1E293B"
        hab_c0, hab_c1, hab_c2 = "#14425A", "#0B2433", "#061219"
        floor_fill = "#050E14"
        hud_text = "#7EE7D6"
        pill_bg, pill_stroke, pill_fg = "#14532D", "#22C55E", "#86EFAC"
        if stage == "resting":
            pill_bg, pill_stroke, pill_fg = "#1E293B", "#64748B", "#CBD5E1"
        elif stage == "vivid":
            pill_bg, pill_stroke, pill_fg = "#3B0764", "#C084FC", "#F3E8FF"
        chip_bg = "#081520"
        title_num = "#F8FAFC"
        sub_main = "#94A3B8"
        sub_dim = "#64748B"
        seg_empty = "#1E293B"
        seg_fill = "#34D399"
        shadow_fill = "#020609"
    else:
        card_bg = "#F8FAFC"
        card_stroke = "#CBD5E1"
        hab_c0, hab_c1, hab_c2 = "#E0F2FE", "#BAE6FD", "#DBEAFE"
        floor_fill = "#CBD5E1"
        hud_text = "#0F5257"
        pill_bg, pill_stroke, pill_fg = "#DCFCE7", "#16A34A", "#14532D"
        if stage == "resting":
            pill_bg, pill_stroke, pill_fg = "#E2E8F0", "#64748B", "#334155"
        elif stage == "vivid":
            pill_bg, pill_stroke, pill_fg = "#F3E8FF", "#9333EA", "#581C87"
        chip_bg = "#FFFFFF"
        title_num = "#0F172A"
        sub_main = "#334155"
        sub_dim = "#475569"
        seg_empty = "#E2E8F0"
        seg_fill = "#059669"
        shadow_fill = "#64748B"

    # Deterministic ambient particles
    rng = random.Random(f"code-pet-{username}")
    particles: list[str] = []
    p_colors = ["#FDE68A", "#A7F3D0", "#7DD3FC"] if is_dark else ["#0284C7", "#059669", "#D97706"]
    p_opacity = "0.75" if is_dark else "0.35"
    for _ in range(14):
        px = rng.randint(60, 820)
        py = rng.randint(52, 285)
        if 345 <= px <= 535 and 105 <= py <= 275:
            continue
        pr = rng.uniform(1.5, 3.1)
        pc = rng.choice(p_colors)
        delay = rng.uniform(-6.0, 0.0)
        dur = rng.uniform(5.2, 8.6)
        particles.append(
            f'<circle cx="{px}" cy="{py}" r="{pr:.1f}" fill="{pc}" opacity="{p_opacity}" '
            f'class="pet-fly" style="animation-delay:{delay:.1f}s;animation-duration:{dur:.1f}s"/>'
        )

    # Pet colors accented by user's top languages
    accent_a = top_langs[0][1] if len(top_langs) > 0 else "#E34C26"
    accent_b = top_langs[1][1] if len(top_langs) > 1 else "#3572A5"
    accent_c = top_langs[2][1] if len(top_langs) > 2 else "#3178C6"
    accent_d = top_langs[3][1] if len(top_langs) > 3 else "#00B4AB"

    # Expressive face based on stage
    if stage == "resting":
        eyes_svg = (
            '<path d="M407 196 Q417 204 427 196" fill="none" stroke="#1E293B" stroke-width="3.2" stroke-linecap="round"/>'
            '<path d="M453 196 Q463 204 473 196" fill="none" stroke="#1E293B" stroke-width="3.2" stroke-linecap="round"/>'
            '<path d="M433 213 Q440 217 447 213" fill="none" stroke="#1E293B" stroke-width="2.6" stroke-linecap="round"/>'
            '<text x="492" y="146" font-family="ui-monospace,monospace" font-size="15" font-weight="700" fill="#93C5FD" class="pet-zzz">z</text>'
            '<text x="508" y="128" font-family="ui-monospace,monospace" font-size="19" font-weight="700" fill="#BFDBFE" class="pet-zzz" style="animation-delay:-1.2s">Z</text>'
        )
        motion_class = "pet-breathe"
    else:
        eyes_svg = (
            '<g class="pet-blink">'
            '<ellipse cx="417" cy="193" rx="11.5" ry="13.5" fill="#FFFFFF"/>'
            '<circle cx="419" cy="195" r="7.2" fill="#0F172A"/>'
            '<circle cx="422" cy="191" r="2.7" fill="#FFFFFF"/>'
            '<ellipse cx="463" cy="193" rx="11.5" ry="13.5" fill="#FFFFFF"/>'
            '<circle cx="461" cy="195" r="7.2" fill="#0F172A"/>'
            '<circle cx="464" cy="191" r="2.7" fill="#FFFFFF"/>'
            '</g>'
            '<path d="M431 211 Q440 221 449 211" fill="none" stroke="#18181B" stroke-width="3.2" stroke-linecap="round"/>'
        )
        motion_class = "pet-hop"

    vivid_halo = ""
    if stage in {"active", "vivid"}:
        vivid_halo = (
            '<circle cx="440" cy="196" r="82" fill="none" stroke="url(#pet-aura)" '
            'stroke-width="2.5" stroke-dasharray="8 6" opacity="0.55" class="pet-spin"/>'
        )

    # Language pill layout centered at x=440, y=300
    pill_specs: list[tuple[str, str, float]] = []
    for lname, lcolor in top_langs[:4]:
        w = max(78.0, 38.0 + len(lname) * 7.6)
        pill_specs.append((lname, lcolor, w))
    gap = 10.0
    total_pills_w = sum(p[2] for p in pill_specs) + gap * (len(pill_specs) - 1)
    cursor_x = 440.0 - total_pills_w / 2.0
    pills_svg: list[str] = []
    for lname, lcolor, pw in pill_specs:
        text_col = "#F1F5F9" if is_dark else "#0F172A"
        pills_svg.append(
            f'<g transform="translate({cursor_x:.1f}, 296)">'
            f'<rect width="{pw:.1f}" height="27" rx="13.5" fill="{chip_bg}" fill-opacity="0.88" '
            f'stroke="{lcolor}" stroke-opacity="0.65" stroke-width="1.2"/>'
            f'{render_language_icon(lname, 8.0, 6.0, lcolor)}'
            f'<text x="29" y="17.8" font-family="-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif" '
            f'font-size="12" font-weight="700" fill="{text_col}">{html.escape(lname)}</text>'
            f'</g>'
        )
        cursor_x += pw + gap

    # 13-week streak meter on bottom-right
    seg_w, seg_h, seg_gap = 19.0, 12.0, 5.5
    seg_start_x = 848.0 - (13 * seg_w + 12 * seg_gap)
    segs_svg: list[str] = []
    for i in range(13):
        sx = seg_start_x + i * (seg_w + seg_gap)
        fill = seg_fill if i < streak else seg_empty
        segs_svg.append(f'<rect x="{sx:.1f}" y="388" width="{seg_w}" height="{seg_h}" rx="3.5" fill="{fill}"/>')

    weeks_goal_text = (
        f"{active_weeks}/52 active weeks · vivid unlocked"
        if stage == "vivid"
        else f"{active_weeks}/52 active weeks to go vivid"
    )
    aria = f"{username}'s code pet: {stage}, {total} contributions this year, {streak} of 13 week streak"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="880" height="456" viewBox="0 0 880 456" role="img" aria-label="{html.escape(aria)}">
  <defs>
    <radialGradient id="pet-hab" cx="50%" cy="42%" r="72%">
      <stop offset="0%" stop-color="{hab_c0}"/>
      <stop offset="62%" stop-color="{hab_c1}"/>
      <stop offset="100%" stop-color="{hab_c2}"/>
    </radialGradient>
    <radialGradient id="pet-body" cx="36%" cy="28%" r="78%">
      <stop offset="0%" stop-color="#FF9A76"/>
      <stop offset="52%" stop-color="#F05936"/>
      <stop offset="100%" stop-color="#B83227"/>
    </radialGradient>
    <radialGradient id="pet-belly" cx="50%" cy="45%" r="65%">
      <stop offset="0%" stop-color="#FDBA9A" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="#F05936" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="pet-aura" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{accent_a}"/>
      <stop offset="50%" stop-color="{accent_b}"/>
      <stop offset="100%" stop-color="{accent_d}"/>
    </linearGradient>
    <clipPath id="pet-stage">
      <rect x="20" y="18" width="840" height="320" rx="20"/>
    </clipPath>
    <style>
      .pet-hop {{ animation: petHop 1.75s cubic-bezier(.28,.82,.42,1) infinite; transform-box: fill-box; transform-origin: center bottom; }}
      .pet-breathe {{ animation: petBreathe 3.8s ease-in-out infinite; transform-box: fill-box; transform-origin: center bottom; }}
      .pet-shadow {{ animation: petShadow 1.75s cubic-bezier(.28,.82,.42,1) infinite; transform-box: fill-box; transform-origin: center; }}
      .pet-blink {{ animation: petBlink 4.6s steps(1) infinite; transform-box: fill-box; transform-origin: center; }}
      .pet-fly {{ animation: petFly 6.4s ease-in-out infinite; }}
      .pet-zzz {{ animation: petZzz 3.2s ease-in-out infinite; }}
      .pet-spin {{ animation: petSpin 18s linear infinite; transform-box: fill-box; transform-origin: center; }}
      @keyframes petHop {{
        0%, 100% {{ transform: translateY(0) scale(1, 1); }}
        34% {{ transform: translateY(-15px) scale(0.97, 1.04); }}
        58% {{ transform: translateY(0) scale(1.05, 0.95); }}
      }}
      @keyframes petBreathe {{
        0%, 100% {{ transform: scale(1, 1); }}
        50% {{ transform: scale(1.03, 0.97); }}
      }}
      @keyframes petShadow {{
        0%, 100% {{ transform: scaleX(1); opacity: 0.34; }}
        34% {{ transform: scaleX(0.78); opacity: 0.18; }}
      }}
      @keyframes petBlink {{
        0%, 94%, 100% {{ transform: scaleY(1); }}
        96% {{ transform: scaleY(0.1); }}
      }}
      @keyframes petFly {{
        0%, 100% {{ transform: translate(0, 0); }}
        50% {{ transform: translate(7px, -14px); }}
      }}
      @keyframes petZzz {{
        0%, 100% {{ transform: translate(0, 0); opacity: 0.85; }}
        50% {{ transform: translate(5px, -9px); opacity: 0.35; }}
      }}
      @keyframes petSpin {{
        to {{ transform: rotate(360deg); }}
      }}
      @media (prefers-reduced-motion: reduce) {{
        * {{ animation: none !important; }}
      }}
    </style>
  </defs>

  <rect x="0.5" y="0.5" width="879" height="455" rx="22" fill="{card_bg}" stroke="{card_stroke}"/>

  <g clip-path="url(#pet-stage)">
    <rect x="20" y="18" width="840" height="320" fill="url(#pet-hab)"/>
    <ellipse cx="440" cy="356" rx="470" ry="74" fill="{floor_fill}" opacity="0.72"/>
    {"".join(particles)}

    <text x="46" y="54" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="12" font-weight="700" letter-spacing="2.2" fill="{hud_text}">CODE PET · @{html.escape(username.upper())}</text>
    <g transform="translate(766, 35)">
      <rect width="72" height="26" rx="13" fill="{pill_bg}" stroke="{pill_stroke}" stroke-opacity="0.65"/>
      <text x="36" y="17" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="10.5" font-weight="800" letter-spacing="1.2" fill="{pill_fg}">{stage.upper()}</text>
    </g>

    {vivid_halo}
    <ellipse cx="440" cy="272" rx="58" ry="10.5" fill="{shadow_fill}" opacity="0.34" class="pet-shadow"/>

    <g class="{motion_class}">
      <!-- Ears -->
      <path d="M392 152 C384 114, 414 112, 420 144 Z" fill="url(#pet-body)"/>
      <path d="M397 146 C393 125, 411 124, 414 142 Z" fill="{accent_b}" opacity="0.65"/>
      <path d="M488 152 C496 114, 466 112, 460 144 Z" fill="url(#pet-body)"/>
      <path d="M483 146 C487 125, 469 124, 466 142 Z" fill="{accent_b}" opacity="0.65"/>

      <!-- Feet -->
      <ellipse cx="414" cy="259" rx="15" ry="8.5" fill="#B83227"/>
      <ellipse cx="466" cy="259" rx="15" ry="8.5" fill="#B83227"/>

      <!-- Main rounded body -->
      <rect x="376" y="136" width="128" height="122" rx="58" fill="url(#pet-body)"/>
      <ellipse cx="440" cy="218" rx="44" ry="34" fill="url(#pet-belly)"/>
      <ellipse cx="412" cy="156" rx="18" ry="7" transform="rotate(-18 412 156)" fill="#FFFFFF" opacity="0.22"/>

      <!-- Rosy cheeks & language-tinted spots -->
      <ellipse cx="399" cy="208" rx="9.5" ry="5.5" fill="#FB7185" opacity="0.55"/>
      <ellipse cx="481" cy="208" rx="9.5" ry="5.5" fill="#FB7185" opacity="0.55"/>
      <circle cx="392" cy="220" r="5.2" fill="{accent_d}" opacity="0.88"/>
      <circle cx="487" cy="183" r="5.2" fill="{accent_c}" opacity="0.88"/>
      <circle cx="478" cy="225" r="3.8" fill="{accent_b}" opacity="0.85"/>

      {eyes_svg}
    </g>

    {"".join(pills_svg)}
  </g>

  <!-- Bottom telemetry bar -->
  <text x="32" y="396" font-family="Georgia,'Times New Roman',serif" font-style="italic" font-size="38" font-weight="700" fill="{title_num}">{total}</text>
  <text x="{44 + len(str(total)) * 22}" y="394" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="14.5" font-weight="500" fill="{sub_main}">contributions this year · {stage}</text>
  <text x="32" y="424" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="12" fill="{sub_dim}">{html.escape(weeks_goal_text)}</text>

  <text x="{seg_start_x:.1f}" y="376" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="11" font-weight="700" letter-spacing="1.6" fill="{sub_main}">STREAK {streak}/13 WEEKS</text>
  {"".join(segs_svg)}

  <text x="848" y="428" text-anchor="end" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="11" fill="{sub_dim}">@{html.escape(username)}</text>
</svg>
"""


def render_contribution_city_svg(
    username: str,
    weeks: list[list[dict[str, Any]]],
    metrics: dict[str, Any],
    mode: str = "dark",
) -> str:
    is_dark = mode == "dark"
    total = metrics["total"]
    active_days = metrics["active_days"]
    busiest = max(metrics["busiest_day"], 1)

    if is_dark:
        bg_0, bg_1, bg_2 = "#042F2E", "#115E59", "#042F2E"
        border_col, border_op = "#2DD4BF", "0.52"
        kicker_col = "#5EEAD4"
        num_col = "#ECFDF5"
        label_col = "#99F6E4"
        meta_col = "#5EEAD4"
        glow_col, glow_op = "#2DD4BF", "0.22"
        # (top_face, left_face, right_face) across 5 intensity tiers
        palette = [
            ("#1B6F69", "#155B56", "#104844"),
            ("#229B8B", "#1B7E71", "#156359"),
            ("#2CC0AC", "#239C8B", "#1B7B6E"),
            ("#43DEC8", "#32B8A5", "#259182"),
            ("#7CF7E4", "#55D6C2", "#3AA998"),
        ]
    else:
        bg_0, bg_1, bg_2 = "#F0FDFA", "#CCFBF1", "#E6FFFA"
        border_col, border_op = "#0D9488", "0.35"
        kicker_col = "#0F766E"
        num_col = "#042F2E"
        label_col = "#115E59"
        meta_col = "#0F766E"
        glow_col, glow_op = "#14B8A6", "0.18"
        palette = [
            ("#B2E8DF", "#94D6CB", "#7AC2B6"),
            ("#5EEAD4", "#38C9B4", "#26A693"),
            ("#2DD4BF", "#14B8A6", "#0D9488"),
            ("#14B8A6", "#0D9488", "#0F766E"),
            ("#0D9488", "#0F766E", "#115E59"),
        ]

    # Build dense 53x7 matrix (pad missing weekday slots with 0)
    padded_weeks = weeks[-53:]
    grid: list[tuple[int, int, int]] = []
    for w_idx, w_days in enumerate(padded_weeks):
        by_day = {int(d["weekday"]): int(d["count"]) for d in w_days}
        max_day = max(by_day.keys()) if w_idx == len(padded_weeks) - 1 and by_day else 6
        for d_idx in range(7):
            if w_idx == len(padded_weeks) - 1 and d_idx > max_day:
                continue
            grid.append((w_idx, d_idx, by_day.get(d_idx, 0)))

    # Strict painter's order: smaller (w + d) has higher screen elevation (further back)
    grid.sort(key=lambda item: (item[0] + item[1], item[0], item[1]))

    dx = 8.35
    dy = 4.82
    x0 = 350.0
    y0 = 104.0

    prisms: list[str] = []
    for w_idx, d_idx, count in grid:
        bx = x0 + (w_idx - d_idx) * dx
        by = y0 + (w_idx + d_idx) * dy

        if count <= 0:
            h = 2.6
            tier = 0
        else:
            ratio = count / busiest
            h = 8.0 + 88.0 * (0.35 * math.sqrt(ratio) + 0.65 * ratio)
            if ratio < 0.15:
                tier = 1
            elif ratio < 0.38:
                tier = 2
            elif ratio < 0.68:
                tier = 3
            else:
                tier = 4

        c_top, c_left, c_right = palette[tier]
        ty = by - h

        # Top diamond: N -> E -> S -> W
        top_pts = f"{bx:.2f},{ty - dy:.2f} {bx + dx:.2f},{ty:.2f} {bx:.2f},{ty + dy:.2f} {bx - dx:.2f},{ty:.2f}"
        # Left face: W_top -> S_top -> S_base -> W_base
        left_pts = f"{bx - dx:.2f},{ty:.2f} {bx:.2f},{ty + dy:.2f} {bx:.2f},{by + dy:.2f} {bx - dx:.2f},{by:.2f}"
        # Right face: S_top -> E_top -> E_base -> S_base
        right_pts = f"{bx:.2f},{ty + dy:.2f} {bx + dx:.2f},{ty:.2f} {bx + dx:.2f},{by:.2f} {bx:.2f},{by + dy:.2f}"

        stroke_attr = f' stroke="{bg_0}" stroke-width="0.35" stroke-opacity="0.45"' if count == 0 else ""
        prisms.append(
            f'<g>'
            f'<polygon points="{left_pts}" fill="{c_left}"/>'
            f'<polygon points="{right_pts}" fill="{c_right}"/>'
            f'<polygon points="{top_pts}" fill="{c_top}"{stroke_attr}/>'
            f'</g>'
        )

    aria = f"{username} 3D contribution city: {total} contributions in the last year across {active_days} active days, busiest day {metrics['busiest_day']}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="880" height="428" viewBox="0 0 880 428" role="img" aria-label="{html.escape(aria)}">
  <defs>
    <linearGradient id="city-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{bg_0}"/>
      <stop offset="54%" stop-color="{bg_1}"/>
      <stop offset="100%" stop-color="{bg_2}"/>
    </linearGradient>
    <radialGradient id="city-downtown-glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{glow_col}" stop-opacity="{glow_op}"/>
      <stop offset="100%" stop-color="{glow_col}" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect x="0.5" y="0.5" width="879" height="427" rx="20" fill="url(#city-bg)" stroke="{border_col}" stroke-opacity="{border_op}"/>
  <ellipse cx="690" cy="320" rx="185" ry="95" fill="url(#city-downtown-glow)"/>

  <g>
    {"".join(prisms)}
  </g>

  <!-- Left architectural summary -->
  <text x="36" y="54" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="11.5" font-weight="700" letter-spacing="2.2" fill="{kicker_col}">CONTRIBUTION CITY</text>
  <text x="36" y="94" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="36" font-weight="800" fill="{num_col}">{total}</text>
  <text x="36" y="116" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="13" font-weight="600" fill="{label_col}">contributions in the last year</text>

  <text x="36" y="152" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="12.5" font-weight="600" fill="{label_col}">{active_days} active days</text>
  <text x="36" y="174" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="12.5" font-weight="600" fill="{label_col}">Busiest day: {metrics['busiest_day']}</text>

  <text x="36" y="382" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="11.5" font-weight="600" fill="{meta_col}" opacity="0.88">@{html.escape(username)}</text>
  <text x="36" y="401" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="10.5" fill="{meta_col}" opacity="0.68">53-week isometric skyline · auto-updated</text>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GitHub profile Code Pet & Contribution City SVGs.")
    parser.add_argument("--username", default="bimadji", help="GitHub username")
    parser.add_argument("--output-dir", default="assets", help="Output directory for SVG files")
    parser.add_argument("--contribs-file", default="", help="Optional local contributions JSON file")
    parser.add_argument("--repos-file", default="", help="Optional local repos JSON file")
    parser.add_argument(
        "--langs",
        default="",
        help="Optional comma-separated top languages override (e.g. HTML,Python,TypeScript,Dart)",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if args.contribs_file:
        weeks, top_langs = load_from_files(
            Path(args.contribs_file),
            Path(args.repos_file) if args.repos_file else None,
        )
    elif token:
        try:
            weeks, top_langs = fetch_via_graphql(args.username, token)
        except Exception:
            weeks, top_langs = fetch_public_fallback(args.username)
    else:
        weeks, top_langs = fetch_public_fallback(args.username)

    if args.langs:
        names = [x.strip() for x in args.langs.split(",") if x.strip()]
        top_langs = [(n, LANG_META.get(n, ("#64748B", n[:2].upper()))[0]) for n in names[:4]]

    metrics = compute_metrics(weeks)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for mode in ("dark", "light"):
        pet_svg = render_code_pet_svg(args.username, metrics, top_langs, mode=mode)
        (out_dir / f"code-pet-{mode}.svg").write_text(pet_svg, encoding="utf-8")

        city_svg = render_contribution_city_svg(args.username, weeks, metrics, mode=mode)
        (out_dir / f"contribution-city-{mode}.svg").write_text(city_svg, encoding="utf-8")

    print(
        f"Generated widgets for @{args.username}: "
        f"total={metrics['total']}, active_days={metrics['active_days']}, "
        f"busiest={metrics['busiest_day']}, active_weeks={metrics['active_weeks']}, "
        f"streak={metrics['streak_weeks']}, stage={metrics['stage']}, "
        f"langs={[x[0] for x in top_langs]}"
    )


if __name__ == "__main__":
    main()
