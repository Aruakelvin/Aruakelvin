"""Output renderers: terminal table, JSON, CSV, Markdown and a standalone HTML report."""

from __future__ import annotations

import csv
import html
import io
import json
import shutil
from collections.abc import Sequence
from datetime import datetime, timezone

from .models import Opportunity

COLUMNS = [
    ("#", lambda i, o: str(i)),
    ("Chain", lambda i, o: o.chain),
    ("Protocol", lambda i, o: o.protocol),
    ("Market", lambda i, o: o.market),
    ("Type", lambda i, o: o.category.value),
    ("TVL", lambda i, o: usd(o.tvl_usd)),
    ("Base%", lambda i, o: pct(o.base_apr)),
    ("Reward%", lambda i, o: pct(o.reward_apr)),
    ("Total%", lambda i, o: pct(o.total_apr)),
    ("Rewards/day", lambda i, o: usd(o.est_daily_rewards_usd)),
    ("Reward tokens", lambda i, o: ",".join(r.symbol for r in o.reward_tokens[:3]) or "-"),
    ("Score", lambda i, o: f"{o.score:.1f}"),
    ("Ends", lambda i, o: ends(o)),
    ("Flags", lambda i, o: ",".join(f for f in o.flags if f != "stable") or "-"),
    ("Src", lambda i, o: o.source),
]


def ends(o: Opportunity) -> str:
    """Time left on the reward campaign, e.g. '10d', '<1d', '3d ↻2' (renewed twice)."""
    left = o.days_left()
    if left is None:
        return "-"
    s = "ended" if left <= 0 else "<1d" if left < 1 else f"{left:.0f}d"
    r = o.extra.get("renewals")
    return f"{s} ↻{r}" if r else s


def usd(v: float | None) -> str:
    if v is None:
        return "-"
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"${v / div:.2f}{suf}"
    return f"${v:.0f}"


def pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}"


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"


def table(opps: Sequence[Opportunity], width: int | None = None) -> str:
    if not opps:
        return "No opportunities matched."
    width = width or shutil.get_terminal_size((200, 40)).columns
    rows = [[fn(i, o) for _, fn in COLUMNS] for i, o in enumerate(opps, 1)]
    headers = [h for h, _ in COLUMNS]
    widths = [max(len(h), *(len(r[c]) for r in rows)) for c, h in enumerate(headers)]
    # Shrink the widest free-text columns until the table fits.
    shrinkable = [headers.index(h) for h in ("Market", "Reward tokens", "Flags", "Protocol")]
    while sum(widths) + 2 * (len(widths) - 1) > width and any(widths[c] > 10 for c in shrinkable):
        c = max(shrinkable, key=lambda k: widths[k])
        widths[c] -= 1
    right = {"#", "TVL", "Base%", "Reward%", "Total%", "Rewards/day", "Score"}

    def fmt(cells: list[str]) -> str:
        out = []
        for c, cell in enumerate(cells):
            cell = _truncate(cell, widths[c])
            out.append(cell.rjust(widths[c]) if headers[c] in right else cell.ljust(widths[c]))
        return "  ".join(out).rstrip()

    lines = [fmt(headers), "  ".join("-" * w for w in widths)]
    lines += [fmt(r) for r in rows]
    return "\n".join(lines)


def to_json(opps: Sequence[Opportunity], meta: dict | None = None) -> str:
    return json.dumps({"meta": meta or {}, "opportunities": [o.to_dict() for o in opps]}, indent=2, default=str)


CSV_FIELDS = ["chain", "protocol", "market", "category", "tvl_usd", "base_apr", "reward_apr", "total_apr",
              "days_left", "renewals",
              "est_daily_rewards_usd", "apr_30d_mean", "reward_tokens", "score", "flags", "source", "url"]


def to_csv(opps: Sequence[Opportunity]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for o in opps:
        d = o.to_dict()
        d["reward_tokens"] = ";".join(r.symbol for r in o.reward_tokens)
        d["flags"] = ";".join(o.flags)
        w.writerow({k: d.get(k) for k in CSV_FIELDS})
    return buf.getvalue()


def to_markdown(opps: Sequence[Opportunity]) -> str:
    headers = [h for h, _ in COLUMNS if h != "#"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for i, o in enumerate(opps, 1):
        cells = [fn(i, o).replace("|", "/") for h, fn in COLUMNS if h != "#"]
        if o.url:
            cells[2] = f"[{cells[2]}]({o.url})"
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def summary_table(rows: list[dict], by: str) -> str:
    if not rows:
        return "No data."
    headers = [by.capitalize(), "Markets", "TVL", "Rewards/day", "TVL-wtd reward%", "Best market"]
    body = [[r[by], str(r["markets"]), usd(r["tvl_usd"]), usd(r["daily_rewards_usd"]),
             pct(r["tvl_weighted_reward_apr"]), _truncate(r["best_market"] or "-", 60)] for r in rows]
    widths = [max(len(h), *(len(b[c]) for b in body)) for c, h in enumerate(headers)]
    fmt = lambda cells: "  ".join(  # noqa: E731
        (c.rjust(widths[i]) if 0 < i < 5 else c.ljust(widths[i])) for i, c in enumerate(cells)
    ).rstrip()
    return "\n".join([fmt(headers), "  ".join("-" * w for w in widths), *(fmt(b) for b in body)])


def to_html(opps: Sequence[Opportunity], summary_rows: list[dict] | None = None, meta: dict | None = None) -> str:
    """Self-contained, sortable, filterable HTML report (no external assets)."""
    meta = meta or {}
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data = json.dumps([o.to_dict() for o in opps], default=str).replace("</", "<\\/")
    summary_html = ""
    if summary_rows:
        trs = "".join(
            f"<tr><td>{html.escape(str(r['chain']))}</td><td class=n>{r['markets']}</td>"
            f"<td class=n>{usd(r['tvl_usd'])}</td><td class=n>{usd(r['daily_rewards_usd'])}</td>"
            f"<td class=n>{pct(r['tvl_weighted_reward_apr'])}</td></tr>"
            for r in summary_rows
        )
        summary_html = (
            "<h2>By chain</h2><table class=sum><thead><tr><th>Chain</th><th>Markets</th><th>TVL</th>"
            f"<th>Rewards/day</th><th>TVL-wtd reward %</th></tr></thead><tbody>{trs}</tbody></table>"
        )
    errors = meta.get("errors") or {}
    err_html = "".join(f"<p class=err>Source <b>{html.escape(k)}</b> failed: {html.escape(v)}</p>"
                       for k, v in errors.items())
    return _HTML.replace("__GENERATED__", generated).replace("__DATA__", data) \
        .replace("__SUMMARY__", summary_html).replace("__ERRORS__", err_html) \
        .replace("__COUNT__", str(len(opps)))


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Incentive Scan</title>
<style>
:root{--bg:#fff;--fg:#1b1f24;--mut:#667085;--line:#e4e7ec;--acc:#2f6fed;--warn:#b54708;--hl:#f5f8ff}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e6e8eb;--mut:#98a2b3;--line:#272b33;--acc:#6e9bff;--warn:#f79009;--hl:#161b26}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1400px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.mut{color:var(--mut)}.err{color:var(--warn)}
.ctl{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
input,select{background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font:inherit}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%}th,td{padding:6px 10px;border-bottom:1px solid var(--line);white-space:nowrap;text-align:left}
th{position:sticky;top:0;background:var(--bg);cursor:pointer;user-select:none;font-weight:600}
tr:hover td{background:var(--hl)}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:10px;border:1px solid var(--line);margin-right:3px;color:var(--mut)}
.tag.r{color:var(--warn);border-color:var(--warn)}a{color:var(--acc);text-decoration:none}
table.sum{width:auto}
</style></head><body><main>
<h1>Cross-chain incentive scan</h1>
<div class=mut>Generated __GENERATED__ · __COUNT__ markets · values as reported by each source; not financial advice</div>
__ERRORS__
<div class=ctl>
<input id=q placeholder="Search market, token, protocol…" size=32>
<select id=chain><option value="">All chains</option></select>
<select id=cat><option value="">All types</option></select>
<input id=tvl type=number placeholder="Min TVL $" min=0 step=10000>
<label class=mut><input id=safe type=checkbox> hide outliers / low TVL</label>
</div>
<div class=wrap><table id=t><thead><tr>
<th data-k=chain>Chain</th><th data-k=protocol>Protocol</th><th data-k=market>Market</th><th data-k=category>Type</th>
<th class=n data-k=tvl_usd>TVL</th><th class=n data-k=base_apr>Base %</th><th class=n data-k=reward_apr>Reward %</th>
<th class=n data-k=total_apr>Total %</th><th class=n data-k=est_daily_rewards_usd>Rewards/day</th><th>Reward tokens</th>
<th class=n data-k=days_left>Ends</th><th class=n data-k=score>Score</th><th>Flags</th><th data-k=source>Source</th></tr></thead><tbody></tbody></table></div>
__SUMMARY__
</main><script>
const D=__DATA__;const $=s=>document.querySelector(s);
const usd=v=>v==null?'-':Math.abs(v)>=1e9?'$'+(v/1e9).toFixed(2)+'B':Math.abs(v)>=1e6?'$'+(v/1e6).toFixed(2)+'M':Math.abs(v)>=1e3?'$'+(v/1e3).toFixed(1)+'K':'$'+v.toFixed(0);
const pc=v=>v==null?'-':v.toFixed(2);const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let sk='score',sd=-1;
for(const [id,k] of [['#chain','chain'],['#cat','category']]){[...new Set(D.map(o=>o[k]))].sort().forEach(v=>$(id).insertAdjacentHTML('beforeend',`<option>${esc(v)}</option>`))}
const risky=new Set(['apr_outlier','low_tvl','net_negative','tvl_drop','ending_soon']);
function render(){const q=$('#q').value.toLowerCase(),c=$('#chain').value,t=$('#cat').value,m=+$('#tvl').value||0,s=$('#safe').checked;
const rows=D.filter(o=>(!c||o.chain===c)&&(!t||o.category===t)&&(o.tvl_usd||0)>=m&&(!s||!o.flags.some(f=>risky.has(f)))&&
(!q||[o.market,o.protocol,o.chain,...o.tokens,...o.reward_tokens.map(r=>r.symbol)].join(' ').toLowerCase().includes(q)))
.sort((a,b)=>{const x=a[sk],y=b[sk];return (typeof x==='string'?String(x).localeCompare(y):((x??-1e18)-(y??-1e18)))*sd});
$('#t tbody').innerHTML=rows.slice(0,1000).map(o=>`<tr><td>${esc(o.chain)}</td><td>${esc(o.protocol)}</td>
<td>${o.url?`<a href="${esc(o.url)}" target=_blank rel=noopener>${esc(o.market)}</a>`:esc(o.market)}</td><td>${esc(o.category)}</td>
<td class=n>${usd(o.tvl_usd)}</td><td class=n>${pc(o.base_apr)}</td><td class=n>${pc(o.reward_apr)}</td><td class=n>${pc(o.total_apr)}</td>
<td class=n>${usd(o.est_daily_rewards_usd)}</td><td>${esc(o.reward_tokens.slice(0,3).map(r=>r.symbol).join(', '))}</td>
<td class=n>${o.days_left==null?'-':o.days_left<=0?'ended':o.days_left<1?'&lt;1d':Math.round(o.days_left)+'d'}${o.renewals?' ↻'+o.renewals:''}</td><td class=n>${o.score.toFixed(1)}</td><td>${o.flags.map(f=>`<span class="tag${risky.has(f)?' r':''}">${esc(f)}</span>`).join('')}</td><td>${esc(o.source)}</td></tr>`).join('')}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;sd=sk===k?-sd:-1;sk=k;render()});
['#q','#chain','#cat','#tvl','#safe'].forEach(id=>$(id).addEventListener('input',render));render();
</script></body></html>
"""
