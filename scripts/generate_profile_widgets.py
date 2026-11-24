#!/usr/bin/env python3
"""Generate unified Dark Teal / Aurora Code Pet and 3D Contribution City SVGs for a GitHub profile."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import random
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

LANG_CODES: dict[str, str] = {
    "Python": "PY",
    "TypeScript": "TS",
    "JavaScript": "JS",
    "HTML": "5",
    "Dart": "DT",
    "C++": "C+",
    "C": "C",
    "PHP": "PHP",
    "Java": "JV",
    "Shell": "SH",
    "Go": "GO",
    "Rust": "RS",
    "CSS": "CS",
}


def http_json(url: str, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> Any:
    req_headers = {"User-Agent": "bimadji-profile-widget-generator/2.0", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def select_top_languages(lang_scores: dict[str, int]) -> list[str]:
    """Prefer programming languages over pure markup (HTML/CSS) when 4+ languages exist."""
    markup = {"HTML", "CSS"}
    ordered = sorted(lang_scores.items(), key=lambda kv: kv[1], reverse=True)
    code_first = [kv[0] for kv in ordered if kv[0] not in markup] + [kv[0] for kv in ordered if kv[0] in markup]
    return code_first[:4]


def fetch_via_graphql(username: str, token: str) -> tuple[list[list[dict[str, Any]]], list[str]]:
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
    for repo in user["repositories"]["nodes"]:
        for edge in repo.get("languages", {}).get("edges", []):
            name = edge["node"]["name"]
            lang_sizes[name] = lang_sizes.get(name, 0) + int(edge["size"])

    return weeks, select_top_languages(lang_sizes)


def group_flat_days_into_weeks(flat_days: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    sorted_days = sorted(flat_days, key=lambda x: x["date"])
    weeks: list[list[dict[str, Any]]] = []
    current_week: list[dict[str, Any]] = []
    for item in sorted_days:
        d_obj = dt.date.fromisoformat(item["date"])
        weekday_sun0 = (d_obj.weekday() + 1) % 7
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


def fetch_public_fallback(username: str) -> tuple[list[list[dict[str, Any]]], list[str]]:
    contrib_data = http_json(f"https://github-contributions-api.jogruber.de/v4/{urllib.parse.quote(username)}?y=last")
    weeks = group_flat_days_into_weeks(contrib_data.get("contributions", []))
    repos = http_json(f"https://api.github.com/users/{urllib.parse.quote(username)}/repos?per_page=100&sort=updated")
    return weeks, select_top_languages(score_repos_languages(repos))


def load_from_files(contribs_file: Path, repos_file: Path | None) -> tuple[list[list[dict[str, Any]]], list[str]]:
    raw = json.loads(contribs_file.read_text(encoding="utf-8"))
    weeks = group_flat_days_into_weeks(raw.get("contributions", []))
    top_langs: list[str] = []
    if repos_file and repos_file.exists():
        repos = json.loads(repos_file.read_text(encoding="utf-8"))
        top_langs = select_top_languages(score_repos_languages(repos))
    return weeks, top_langs


def compute_metrics(weeks: list[list[dict[str, Any]]]) -> dict[str, Any]:
    all_days = [d for w in weeks for d in w]
    trailing_days = all_days[-365:] if len(all_days) > 365 else all_days
    total_contributions = sum(d["count"] for d in all_days)
    active_days = sum(1 for d in all_days if d["count"] > 0)
    busiest_day = max((d["count"] for d in all_days), default=0)

    eval_weeks = weeks[-52:] if len(weeks) > 52 else weeks
    week_totals = [sum(d["count"] for d in w) for w in eval_weeks]
    active_weeks = sum(1 for total in week_totals if total > 0)

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


def render_language_icon(name: str, x: float, y: float, badge_fill: str) -> str:
    code = LANG_CODES.get(name, name[:2].upper())
    font_size = "7.5" if len(code) <= 2 else "6.2"
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="15" height="15" rx="3.5" fill="{badge_fill}"/>'
        f'<text x="{x + 7.5:.1f}" y="{y + 10.3:.1f}" text-anchor="middle" '
        f'font-family="SFMono-Regular,Menlo,Consolas,monospace" '
        f'font-size="{font_size}" font-weight="800" fill="#042422">{html.escape(code)}</text>'
    )


def render_code_pet_svg(
    username: str,
    metrics: dict[str, Any],
    top_langs: list[str],
    mode: str = "dark",
) -> str:
    """Render Code Pet in the unified Dark Teal / Aurora design system."""
    stage = metrics["stage"]
    total = metrics["total"]
    active_weeks = metrics["active_weeks"]
    streak = min(metrics["streak_weeks"], 13)
    border_opacity = "0.38" if mode == "dark" else "0.58"

    if not top_langs:
        top_langs = ["Python", "TypeScript", "Dart", "C++"]

    pill_bg, pill_stroke, pill_fg = "#0D3B38", "#2DD4BF", "#5EEAD4"
    if stage == "resting":
        pill_bg, pill_stroke, pill_fg = "#102B31", "#67A8A1", "#88B8B2"

    # Deterministic aurora fireflies
    rng = random.Random(f"aurora-pet-{username}")
    particles: list[str] = []
    p_colors = ["#5EEAD4", "#2DD4BF", "#99F6E4", "#FCD34D"]
    for _ in range(14):
        px = rng.randint(64, 1136)
        py = rng.randint(52, 275)
        if 480 <= px <= 720 and 95 <= py <= 275:
            continue
        pr = rng.uniform(1.6, 3.2)
        pc = rng.choice(p_colors)
        delay = rng.uniform(-6.0, 0.0)
        dur = rng.uniform(5.2, 8.6)
        particles.append(
            f'<circle cx="{px}" cy="{py}" r="{pr:.1f}" fill="{pc}" opacity="0.72" '
            f'class="pet-fly" style="animation-delay:{delay:.1f}s;animation-duration:{dur:.1f}s"/>'
        )

    if stage == "resting":
        eyes_svg = (
            '<path d="M567 188 Q577 196 587 188" fill="none" stroke="#042422" stroke-width="3.2" stroke-linecap="round"/>'
            '<path d="M613 188 Q623 196 633 188" fill="none" stroke="#042422" stroke-width="3.2" stroke-linecap="round"/>'
            '<path d="M593 205 Q600 209 607 205" fill="none" stroke="#042422" stroke-width="2.6" stroke-linecap="round"/>'
            '<text x="654" y="138" font-family="SFMono-Regular,Menlo,monospace" font-size="15" font-weight="700" fill="#5EEAD4" class="pet-zzz">z</text>'
            '<text x="670" y="120" font-family="SFMono-Regular,Menlo,monospace" font-size="19" font-weight="700" fill="#99F6E4" class="pet-zzz" style="animation-delay:-1.2s">Z</text>'
        )
        motion_class = "pet-breathe"
    else:
        eyes_svg = (
            '<g class="pet-blink">'
            '<ellipse cx="577" cy="185" rx="11.5" ry="13.5" fill="#ECFDF5"/>'
            '<circle cx="579" cy="187" r="7.2" fill="#042422"/>'
            '<circle cx="582" cy="183" r="2.7" fill="#FFFFFF"/>'
            '<ellipse cx="623" cy="185" rx="11.5" ry="13.5" fill="#ECFDF5"/>'
            '<circle cx="621" cy="187" r="7.2" fill="#042422"/>'
            '<circle cx="624" cy="183" r="2.7" fill="#FFFFFF"/>'
            '</g>'
            '<path d="M591 203 Q600 213 609 203" fill="none" stroke="#042422" stroke-width="3.2" stroke-linecap="round"/>'
        )
        motion_class = "pet-hop"

    vivid_halo = ""
    if stage in {"active", "vivid"}:
        vivid_halo = (
            '<circle cx="600" cy="188" r="84" fill="none" stroke="#5EEAD4" '
            'stroke-width="2" stroke-dasharray="8 6" opacity="0.5" class="pet-spin"/>'
        )

    # Unified Aurora language pills centered at x=600, y=286
    teal_shades = ["#5EEAD4", "#2DD4BF", "#14B8A6", "#99F6E4"]
    pill_specs: list[tuple[str, str, float]] = []
    for i, lname in enumerate(top_langs[:4]):
        w = max(82.0, 40.0 + len(lname) * 7.6)
        pill_specs.append((lname, teal_shades[i % len(teal_shades)], w))
    gap = 10.0
    total_pills_w = sum(p[2] for p in pill_specs) + gap * (len(pill_specs) - 1)
    cursor_x = 600.0 - total_pills_w / 2.0
    pills_svg: list[str] = []
    for lname, lshade, pw in pill_specs:
        pills_svg.append(
            f'<g transform="translate({cursor_x:.1f}, 286)">'
            f'<rect width="{pw:.1f}" height="27" rx="13.5" fill="#08171B" fill-opacity="0.9" '
            f'stroke="#2DD4BF" stroke-opacity="0.45" stroke-width="1.2"/>'
            f'{render_language_icon(lname, 8.0, 6.0, lshade)}'
            f'<text x="29" y="17.8" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif" '
            f'font-size="12" font-weight="700" fill="#ECFDF5">{html.escape(lname)}</text>'
            f'</g>'
        )
        cursor_x += pw + gap

    # 13-week streak meter on bottom-right
    seg_w, seg_h, seg_gap = 20.0, 12.0, 6.0
    seg_start_x = 1136.0 - (13 * seg_w + 12 * seg_gap)
    segs_svg: list[str] = []
    for i in range(13):
        sx = seg_start_x + i * (seg_w + seg_gap)
        if i < streak:
            segs_svg.append(f'<rect x="{sx:.1f}" y="382" width="{seg_w}" height="{seg_h}" rx="3.5" fill="#2DD4BF"/>')
        else:
            segs_svg.append(
                f'<rect x="{sx:.1f}" y="382" width="{seg_w}" height="{seg_h}" rx="3.5" '
                f'fill="#0D2329" stroke="#2DD4BF" stroke-opacity="0.18"/>'
            )

    weeks_goal_text = (
        f"{active_weeks}/52 active weeks · vivid unlocked"
        if stage == "vivid"
        else f"{active_weeks}/52 active weeks to go vivid"
    )
    aria = f"{username}'s code pet: {stage}, {total} contributions this year, {streak} of 13 week streak"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="440" viewBox="0 0 1200 440" role="img" aria-label="{html.escape(aria)}">
  <defs>
    <linearGradient id="stage" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#061519"/>
      <stop offset="52%" stop-color="#0B2429"/>
      <stop offset="100%" stop-color="#051216"/>
    </linearGradient>
    <radialGradient id="pet-hab" cx="50%" cy="42%" r="68%">
      <stop offset="0%" stop-color="#113B42"/>
      <stop offset="60%" stop-color="#0A2328"/>
      <stop offset="100%" stop-color="#07161A"/>
    </radialGradient>
    <radialGradient id="pet-body" cx="36%" cy="28%" r="78%">
      <stop offset="0%" stop-color="#99F6E4"/>
      <stop offset="48%" stop-color="#2DD4BF"/>
      <stop offset="100%" stop-color="#0D9488"/>
    </radialGradient>
    <radialGradient id="pet-belly" cx="50%" cy="45%" r="65%">
      <stop offset="0%" stop-color="#ECFDF5" stop-opacity="0.78"/>
      <stop offset="100%" stop-color="#2DD4BF" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="pet-stage">
      <rect x="40" y="22" width="1120" height="310" rx="14"/>
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
        0%, 100% {{ transform: scaleX(1); opacity: 0.42; }}
        34% {{ transform: scaleX(0.78); opacity: 0.2; }}
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

  <rect width="1200" height="440" rx="16" fill="url(#stage)"/>

  <g clip-path="url(#pet-stage)">
    <rect x="40" y="22" width="1120" height="310" fill="url(#pet-hab)"/>
    <ellipse cx="600" cy="350" rx="600" ry="72" fill="#041013" opacity="0.78"/>
    {"".join(particles)}

    <text x="68" y="56" font-family="SFMono-Regular,Menlo,Consolas,monospace" font-size="11.5" font-weight="700" letter-spacing="2.2" fill="#5EEAD4">CODE PET &#183; @{html.escape(username.upper())}</text>
    <g transform="translate(1060, 38)">
      <rect width="74" height="24" rx="12" fill="{pill_bg}" stroke="{pill_stroke}" stroke-opacity="0.6"/>
      <text x="37" y="16" text-anchor="middle" font-family="SFMono-Regular,Menlo,Consolas,monospace" font-size="10" font-weight="800" letter-spacing="1.2" fill="{pill_fg}">{stage.upper()}</text>
    </g>

    {vivid_halo}
    <ellipse cx="600" cy="264" rx="58" ry="10.5" fill="#02080A" opacity="0.42" class="pet-shadow"/>

    <g class="{motion_class}">
      <!-- Ears -->
      <path d="M552 144 C544 106, 574 104, 580 136 Z" fill="url(#pet-body)"/>
      <path d="M557 138 C553 117, 571 116, 574 134 Z" fill="#0F766E" opacity="0.75"/>
      <path d="M648 144 C656 106, 626 104, 620 136 Z" fill="url(#pet-body)"/>
      <path d="M643 138 C647 117, 629 116, 626 134 Z" fill="#0F766E" opacity="0.75"/>

      <!-- Feet -->
      <ellipse cx="574" cy="251" rx="15" ry="8.5" fill="#0F766E"/>
      <ellipse cx="626" cy="251" rx="15" ry="8.5" fill="#0F766E"/>

      <!-- Main aurora spirit body -->
      <rect x="536" y="128" width="128" height="122" rx="58" fill="url(#pet-body)"/>
      <ellipse cx="600" cy="210" rx="44" ry="34" fill="url(#pet-belly)"/>
      <ellipse cx="572" cy="148" rx="18" ry="7" transform="rotate(-18 572 148)" fill="#FFFFFF" opacity="0.34"/>

      <!-- Warm amber cheeks & bioluminescent spots -->
      <ellipse cx="559" cy="200" rx="9.5" ry="5.5" fill="#FCD34D" opacity="0.52"/>
      <ellipse cx="641" cy="200" rx="9.5" ry="5.5" fill="#FCD34D" opacity="0.52"/>
      <circle cx="552" cy="212" r="4.8" fill="#ECFDF5" opacity="0.75"/>
      <circle cx="647" cy="175" r="4.8" fill="#ECFDF5" opacity="0.75"/>
      <circle cx="638" cy="217" r="3.6" fill="#0F766E" opacity="0.65"/>

      {eyes_svg}
    </g>

    {"".join(pills_svg)}
  </g>
  <rect x="40" y="22" width="1120" height="310" rx="14" fill="none" stroke="#2DD4BF" stroke-opacity="0.22"/>

  <!-- Bottom telemetry bar -->
  <text x="64" y="388" font-family="Georgia,'Times New Roman',serif" font-style="italic" font-size="38" font-weight="700" fill="#ECFDF5">{total}</text>
  <text x="{76 + len(str(total)) * 22}" y="386" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif" font-size="14.5" font-weight="500" fill="#88B8B2">contributions this year &#183; {stage}</text>
  <text x="64" y="415" font-family="SFMono-Regular,Menlo,Consolas,monospace" font-size="11.5" fill="#67A8A1">{html.escape(weeks_goal_text)}</text>

  <text x="{seg_start_x:.1f}" y="369" font-family="SFMono-Regular,Menlo,Consolas,monospace" font-size="10.5" font-weight="700" letter-spacing="1.6" fill="#5EEAD4">STREAK {streak}/13 WEEKS</text>
  {"".join(segs_svg)}

  <text x="1136" y="416" text-anchor="end" font-family="SFMono-Regular,Menlo,Consolas,monospace" font-size="10.5" letter-spacing="1.4" fill="#67A8A1">@{html.escape(username.upper())}</text>
  <rect x="0.5" y="0.5" width="1199" height="439" rx="15.5" fill="none" stroke="#2DD4BF" stroke-opacity="{border_opacity}"/>
</svg>
"""


def render_contribution_city_svg(
    username: str,
    weeks: list[list[dict[str, Any]]],
    metrics: dict[str, Any],
    mode: str = "dark",
) -> str:
    """Render 3D Contribution City in the exact same 1200px Dark Teal / Aurora system."""
    total = metrics["total"]
    active_days = metrics["active_days"]
    busiest = max(metrics["busiest_day"], 1)
    border_opacity = "0.38" if mode == "dark" else "0.58"

    palette = [
        ("#134E4A", "#0F3F3C", "#0B2F2D"),
        ("#1F8A7D", "#186E64", "#12544C"),
        ("#28B5A2", "#1F9182", "#176F64"),
        ("#3ED8C3", "#2EB09E", "#22897B"),
        ("#7CF7E4", "#52D4C0", "#38A897"),
    ]

    padded_weeks = weeks[-53:]
    grid: list[tuple[int, int, int]] = []
    for w_idx, w_days in enumerate(padded_weeks):
        by_day = {int(d["weekday"]): int(d["count"]) for d in w_days}
        max_day = max(by_day.keys()) if w_idx == len(padded_weeks) - 1 and by_day else 6
        for d_idx in range(7):
            if w_idx == len(padded_weeks) - 1 and d_idx > max_day:
                continue
            grid.append((w_idx, d_idx, by_day.get(d_idx, 0)))

    grid.sort(key=lambda item: (item[0] + item[1], item[0], item[1]))

    dx = 10.6
    dy = 6.1
    x0 = 470.0
    y0 = 86.0

    prisms: list[str] = []
    for w_idx, d_idx, count in grid:
        bx = x0 + (w_idx - d_idx) * dx
        by = y0 + (w_idx + d_idx) * dy

        if count <= 0:
            h = 3.0
            tier = 0
        else:
            ratio = count / busiest
            h = 10.0 + 96.0 * (0.35 * math.sqrt(ratio) + 0.65 * ratio)
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

        top_pts = f"{bx:.2f},{ty - dy:.2f} {bx + dx:.2f},{ty:.2f} {bx:.2f},{ty + dy:.2f} {bx - dx:.2f},{ty:.2f}"
        left_pts = f"{bx - dx:.2f},{ty:.2f} {bx:.2f},{ty + dy:.2f} {bx:.2f},{by + dy:.2f} {bx - dx:.2f},{by:.2f}"
        right_pts = f"{bx:.2f},{ty + dy:.2f} {bx + dx:.2f},{ty:.2f} {bx + dx:.2f},{by:.2f} {bx:.2f},{by + dy:.2f}"

        stroke_attr = ' stroke="#061519" stroke-width="0.45" stroke-opacity="0.55"' if count == 0 else ""
        prisms.append(
            f'<g>'
            f'<polygon points="{left_pts}" fill="{c_left}"/>'
            f'<polygon points="{right_pts}" fill="{c_right}"/>'
            f'<polygon points="{top_pts}" fill="{c_top}"{stroke_attr}/>'
            f'</g>'
        )

    aria = f"{username} 3D contribution city: {total} contributions in the last year across {active_days} active days, busiest day {metrics['busiest_day']}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="460" viewBox="0 0 1200 460" role="img" aria-label="{html.escape(aria)}">
  <defs>
    <linearGradient id="stage" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#061519"/>
      <stop offset="52%" stop-color="#0B2429"/>
      <stop offset="100%" stop-color="#051216"/>
    </linearGradient>
    <radialGradient id="city-downtown-glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#2DD4BF" stop-opacity="0.20"/>
      <stop offset="100%" stop-color="#2DD4BF" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="1200" height="460" rx="16" fill="url(#stage)"/>
  <ellipse cx="920" cy="340" rx="240" ry="115" fill="url(#city-downtown-glow)"/>

  <g>
    {"".join(prisms)}
  </g>

  <!-- Left architectural summary -->
  <text x="64" y="68" font-family="SFMono-Regular,Menlo,Consolas,monospace" font-size="11.5" font-weight="700" letter-spacing="2.2" fill="#5EEAD4">CONTRIBUTION CITY</text>
  <text x="64" y="118" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif" font-size="44" font-weight="800" fill="#ECFDF5">{total}</text>
  <text x="64" y="144" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif" font-size="14" font-weight="500" fill="#D5F5EE">contributions in the last year</text>

  <rect x="64" y="168" width="210" height="68" rx="12" fill="#0B1E23" stroke="#2DD4BF" stroke-opacity="0.22"/>
  <text x="82" y="196" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif" font-size="13" font-weight="600" fill="#ECFDF5">{active_days} active days</text>
  <text x="82" y="220" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif" font-size="13" font-weight="600" fill="#5EEAD4">Busiest day: {metrics['busiest_day']}</text>

  <text x="64" y="396" font-family="SFMono-Regular,Menlo,Consolas,monospace" font-size="11.5" font-weight="700" letter-spacing="1.4" fill="#5EEAD4">@{html.escape(username.upper())}</text>
  <text x="64" y="416" font-family="SFMono-Regular,Menlo,Consolas,monospace" font-size="10.5" letter-spacing="1.4" fill="#67A8A1">53-WEEK ISOMETRIC SKYLINE &#183; AUTO-UPDATED</text>

  <rect x="0.5" y="0.5" width="1199" height="459" rx="15.5" fill="none" stroke="#2DD4BF" stroke-opacity="{border_opacity}"/>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GitHub profile Code Pet & Contribution City SVGs.")
    parser.add_argument("--username", default="bimadji", help="GitHub username")
    parser.add_argument("--output-dir", default="assets", help="Output directory for SVG files")
    parser.add_argument("--contribs-file", default="", help="Optional local contributions JSON file")
    parser.add_argument("--repos-file", default="", help="Optional local repos JSON file")
    parser.add_argument("--langs", default="", help="Optional comma-separated top languages override")
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
        top_langs = [x.strip() for x in args.langs.split(",") if x.strip()][:4]

    metrics = compute_metrics(weeks)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for mode in ("dark", "light"):
        pet_svg = render_code_pet_svg(args.username, metrics, top_langs, mode=mode)
        (out_dir / f"code-pet-{mode}.svg").write_text(pet_svg, encoding="utf-8")

        city_svg = render_contribution_city_svg(args.username, weeks, metrics, mode=mode)
        (out_dir / f"contribution-city-{mode}.svg").write_text(city_svg, encoding="utf-8")

    print(
        f"Generated Aurora widgets for @{args.username}: "
        f"total={metrics['total']}, active_days={metrics['active_days']}, "
        f"busiest={metrics['busiest_day']}, active_weeks={metrics['active_weeks']}, "
        f"streak={metrics['streak_weeks']}, stage={metrics['stage']}, "
        f"langs={top_langs}"
    )


if __name__ == "__main__":
    main()
