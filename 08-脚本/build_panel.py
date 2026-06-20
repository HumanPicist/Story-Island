#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
故事岛 · 面板生成器
扫描整座岛的 .md 仓库，生成一张自包含的 HTML 总览面板。
零依赖（纯 python3 标准库）。解析全部在本机磁盘完成，不依赖任何会话/网络。

用法：
    python3 08-脚本/build_panel.py
产物：
    07-面板/故事岛-面板.html   （单文件、离线、双击即可在浏览器打开）

Live 机制：见 CLAUDE.md §4.1 —— 每次「推进」写回 _state 后跑一次本脚本，面板即与世界同步。
"""

import os, re, html, glob, datetime, sys
from pathlib import Path

sys.dont_write_bytecode = True   # 不写 __pycache__（无害的字节码缓存）

VAULT   = Path(__file__).resolve().parent.parent
OUT     = VAULT / "07-面板" / "故事岛-面板.html"
PREVIEW = VAULT / "07-面板" / "面板预览.md"   # Obsidian 内嵌预览页（srcdoc 内联，随推进自动重建）
UNIT    = "天"   # 周期量词·默认「天」；main() 从 _state 的「周期量词」读（史诗世界可为 年/纪元/回合…），仅用于合成显示

# ----------------------------------------------------------------------------
# 解析工具
# ----------------------------------------------------------------------------

def read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""

def split_frontmatter(text):
    """返回 (meta:dict, body:str)。极简 YAML 子集解析，够本仓库用。"""
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end].strip("\n")
            body = text[end+4:]
            meta = parse_yaml_block(fm)
    return meta, body.lstrip("\n")

def parse_yaml_block(fm):
    meta, cur = {}, None
    for line in fm.split("\n"):
        if not line.strip():
            continue
        # 缩进的列表项，归到当前 key
        m = re.match(r"^\s+-\s*(.*)$", line)
        if m and cur is not None:
            if not isinstance(meta.get(cur), list):
                meta[cur] = []
            meta[cur].append(strip_scalar(m.group(1)))
            continue
        m = re.match(r"^([^:\s][^:]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1).strip(), m.group(2).strip()
            cur = key
            if val == "":
                meta[key] = ""            # 可能后跟多行列表
            elif val.startswith("["):
                meta[key] = parse_inline_list(val)
            else:
                meta[key] = strip_scalar(val)
    return meta

def parse_inline_list(val):
    inner = val.strip().lstrip("[").rstrip("]").strip()
    if not inner:
        return []
    parts = re.findall(r'"[^"]*"|\'[^\']*\'|[^,]+', inner)
    return [strip_scalar(p.strip()) for p in parts if p.strip()]

def strip_scalar(s):
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return s

PREFIXES = ("fact-", "chr-", "day-", "evt-", "big-", "dev-")

def clean_links(s):
    """去掉 wikilink / 加粗 / 引用号，给纯展示用。"""
    if not isinstance(s, str):
        s = str(s)
    def repl(m):
        t = m.group(1)
        if "|" in t:
            t = t.split("|", 1)[1]
        for pre in PREFIXES:
            if t.startswith(pre):
                t = t[len(pre):]
        return t
    s = re.sub(r"\[\[([^\]]+)\]\]", repl, s)
    s = s.replace("**", "").replace("　", " ")
    s = re.sub(r"^\s*>\s?", "", s)
    return s.strip()

def esc(s):
    return html.escape(clean_links(s))

def sections(body):
    """把正文按 '## ' 二级标题切块，返回 [(title, lines[])]。标题前的内容归到 ('', lines)。"""
    out, title, buf = [], "", []
    for line in body.split("\n"):
        if line.startswith("## ") and not line.startswith("### "):
            out.append((title, buf)); title, buf = line[3:].strip(), []
        else:
            buf.append(line)
    out.append((title, buf))
    return out

def get_section(body, name):
    for t, lines in sections(body):
        if t.replace("　", " ").strip().startswith(name):
            return "\n".join(lines).strip()
    return ""

# ----------------------------------------------------------------------------
# 各对象加载
# ----------------------------------------------------------------------------

def load_state():
    meta, body = split_frontmatter(read(VAULT / "_state.md"))
    # 氛围句：## 当前世界时间 段落里、加粗时间行之后的第一段散文
    atmo = ""
    sec = get_section(body, "当前世界时间")
    for ln in sec.split("\n"):
        ln = ln.strip()
        if not ln or ln.startswith("**") or ln.startswith(">"):
            continue
        atmo = clean_links(ln); break

    def bullets(name):
        txt = get_section(body, name)
        items = []
        for ln in txt.split("\n"):
            ln = ln.rstrip()
            m = re.match(r"^\s*-\s+(.*)$", ln)
            if m:
                items.append(m.group(1).strip())
        return items

    snap_raw = bullets("在场快照")
    snapshot = []
    for it in snap_raw:
        m = re.match(r"^\*\*(.+?)\*\*\s*[—-]+\s*(.*)$", it)
        if m:
            snapshot.append((m.group(1).strip(), m.group(2).strip()))
        else:
            snapshot.append((clean_links(it), ""))

    def plain(name):
        txt = get_section(body, name)
        txt = re.sub(r"^\s*[（(].*?[)）]\s*$", "", txt, flags=re.M).strip()
        return txt

    return {
        "meta": meta,
        "atmosphere": atmo,
        "snapshot": snapshot,
        "threads": [clean_links(x) for x in bullets("悬念与进行中的线索")],
        "interventions": [clean_links(x) for x in bullets("未结干预")] or ([] if not plain("未结干预") else []),
        "intervention_text": plain("未结干预"),
        "pending_text": plain("待裁决"),
    }

def load_characters():
    chars = []
    for fp in sorted(glob.glob(str(VAULT / "01-角色" / "chr-*.md"))):
        meta, body = split_frontmatter(read(fp))
        stem = Path(fp).stem.replace("chr-", "")
        setting = get_section(body, "角色设定") or get_section(body, "人物设定")   # 回退兼容旧"人物设定"
        mm = re.search(r"\*\*核心动机\*\*[：:]\s*(.+)", setting)
        motive = clean_links(mm.group(1)) if mm else ""
        # 最近一条短期记忆
        short = get_section(body, "短期记忆")
        last_mem = ""
        for ln in short.split("\n"):
            m = re.match(r"^\s*-\s+(.*)$", ln)
            if m:
                last_mem = clean_links(m.group(1))
        aliases = meta.get("别名", []) or []
        if isinstance(aliases, str):
            aliases = [aliases] if aliases else []
        chars.append({
            "stem": stem,
            "name": meta.get("名称") or stem,
            "aliases": aliases,
            "status": meta.get("状态", ""),
            "loc": clean_links(meta.get("位置", "")),
            "motive": motive,
            "last_mem": last_mem,
            "updated": clean_links(meta.get("更新于", "")),
        })
    return chars

def latest_day():
    days = [f for f in glob.glob(str(VAULT / "02-日志" / "*.md")) if Path(f).name != "_说明.md"]
    best, best_n = None, -1
    for fp in days:
        meta, body = split_frontmatter(read(fp))
        try:
            n = int(str(meta.get("周期", meta.get("天数", 0))))
        except Exception:
            n = 0
        if n >= best_n:
            best, best_n = (meta, body, fp), n
    return best

BEAT_RE = re.compile(r"^\s*-\s*(\d{1,2}:\d{2})\s*〔(.+?)〕(.*)$")

def load_timeline(day):
    """取最近 3 个小时段，每段内的场景节拍（〔〕开头的行）。"""
    if not day:
        return []
    meta, body, fp = day
    blocks = []
    for title, lines in sections(body):
        if not re.match(r"^\d{1,2}:\d{2}", title.strip()):
            continue
        beats = []
        for ln in lines:
            m = BEAT_RE.match(ln)
            if m:
                t = m.group(1)
                summary = m.group(2).strip()
                tail = clean_links(m.group(3).strip())
                if tail and len(summary) < 60:
                    summary = summary + " " + tail
                beats.append((t, clean_links(summary)))
        beats.sort(key=lambda x: x[0])
        if beats:
            blocks.append((title.replace("　", " · "), beats))
    return blocks[-3:]

def load_timeline_global(n=3):
    """跨天取全局最近 n 个小时段（解决新一天还没小时块时的空窗）。"""
    rows = []
    for fp in [f for f in glob.glob(str(VAULT / "02-日志" / "*.md")) if Path(f).name != "_说明.md"]:
        meta, body = split_frontmatter(read(fp))
        try:
            dn = int(str(meta.get("周期", meta.get("天数", 0))))
        except Exception:
            dn = 0
        order = 0
        for title, lines in sections(body):
            if not re.match(r"^\d{1,2}:\d{2}", title.strip()):
                continue
            beats = []
            for ln in lines:
                m = BEAT_RE.match(ln)
                if m:
                    t = m.group(1)
                    summary = m.group(2).strip()
                    tail = clean_links(m.group(3).strip())
                    if tail and len(summary) < 60:
                        summary = summary + " " + tail
                    beats.append((t, clean_links(summary)))
            beats.sort(key=lambda x: x[0])
            if beats:
                rows.append((dn, order, f"第{dn}天 · " + title.replace("　", " · "), beats))
                order += 1
    rows.sort(key=lambda r: (r[0], r[1]))
    return [(title, beats) for _dn, _o, title, beats in rows[-n:]]

def load_dice(day):
    if not day:
        return []
    meta = day[0]
    d = meta.get("骰点", []) or []
    if isinstance(d, str):
        d = [d]
    out = []
    for s in d:
        s = clean_links(s)
        label = s.split("→")[0].strip()
        out.append((label, s))
    return out

def load_facts():
    facts = []
    for fp in sorted(glob.glob(str(VAULT / "03-动态事实" / "fact-*.md"))):
        if fp.endswith("-归档.md"):
            continue  # 动态事实归档面（旧进度时间线）不进面板，只活跃面渲染（宪法附录F）
        meta, body = split_frontmatter(read(fp))
        cur = get_section(body, "当前状态")
        first = ""
        for ln in cur.split("\n"):
            if ln.strip():
                first = clean_links(ln); break
        # 最近一条进度
        prog = get_section(body, "进度时间线")
        last_prog = ""
        for ln in prog.split("\n"):
            m = re.match(r"^\s*-\s+(.*)$", ln)
            if m:
                last_prog = clean_links(m.group(1))
        facts.append({
            "name": meta.get("名称") or Path(fp).stem,
            "sub": meta.get("子类", ""),
            "status": meta.get("状态", ""),
            "updated": clean_links(meta.get("更新于", "")),
            "summary": first,
            "last_prog": last_prog,
        })
    return facts

def load_bigs():
    bigs = []
    for fp in sorted(glob.glob(str(VAULT / "05-大事件" / "big-*.md"))):
        meta, _ = split_frontmatter(read(fp))
        bigs.append({
            "title": meta.get("标题") or Path(fp).stem,
            "time": clean_links(meta.get("时间", "")),
            "impact": clean_links(meta.get("影响", "")),
        })
    return bigs

def load_chronicle():
    _, body = split_frontmatter(read(VAULT / "06-编年史" / "编年史.md"))
    secs = [(t, "\n".join(l).strip()) for t, l in sections(body) if t.strip()]
    if not secs:
        return None
    title, txt = secs[-1]
    paras = [clean_links(p.strip()) for p in txt.split("\n") if p.strip() and not p.strip().startswith(">")]
    return {"title": clean_links(title), "paras": paras}

def load_daily_story():
    """最近一篇每日故事（06-编年史/每日故事/第N天-故事.md）。仅供面板展示，不进推进。"""
    best, best_n = None, -1
    for fp in glob.glob(str(VAULT / "06-编年史" / "每日故事" / "*.md")):
        if Path(fp).name.startswith("_"):
            continue
        meta, body = split_frontmatter(read(fp))
        n = None
        try:
            n = int(str(meta.get("周期", meta.get("天数", ""))))
        except Exception:
            n = None
        if n is None:
            mm = re.search(r"第(\d+)", Path(fp).stem)
            n = int(mm.group(1)) if mm else 0
        if n >= best_n:
            best, best_n = (n, body), n
    if not best:
        return None
    n, body = best
    title = f"第{n}{UNIT} · 每日故事"
    paras = []
    for ln in body.split("\n"):
        s = ln.strip()
        if not s or s.startswith(">"):
            continue
        if re.match(r"^[-*_]{3,}$", s):      # 跳过分隔线（---/***/___）
            continue
        if s.startswith("#"):
            h = s.lstrip("#").strip()
            if h:
                title = clean_links(h)
            continue
        paras.append(clean_links(s))
    return {"title": title, "day": n, "paras": paras}

# ----------------------------------------------------------------------------
# 渲染
# ----------------------------------------------------------------------------

STATUS_COLOR = {"活跃": "#5fc77e", "离场": "#8a93a3", "失踪": "#e0a64a", "死亡": "#d6584f", "": "#8a93a3"}
SUB_COLOR = {"任务": "#c98bdb", "场景": "#6fb1e0", "道具": "#e0a64a", "物品": "#e0a64a",
             "图鉴": "#5fc77e", "地图": "#6fb1e0", "其它": "#8a93a3", "": "#8a93a3"}

def match_snapshot(char, snapshot):
    cands = [char["stem"], char["name"]] + list(char["aliases"])
    for bold, desc in snapshot:
        if any(c and c in bold for c in cands):
            return desc
    return ""

def render(data):
    s   = data["state"]
    m   = s["meta"]
    day = m.get("当前周期", m.get("当前天数", "?"))
    date= m.get("当前日期", "")
    clk = m.get("当前时刻", "")

    # 角色卡
    cards = []
    for c in data["chars"]:
        now = match_snapshot(c, s["snapshot"]) or c["last_mem"]
        color = STATUS_COLOR.get(c["status"], "#8a93a3")
        alias = ("　" + " / ".join(esc(a) for a in c["aliases"])) if c["aliases"] else ""
        cards.append(f"""
        <div class="card char">
          <div class="char-head">
            <span class="char-name">{esc(c['name'])}</span>
            <span class="alias">{alias}</span>
            <span class="badge" style="--c:{color}">{esc(c['status'])}</span>
          </div>
          <div class="char-loc">📍 {esc(c['loc']) or '—'}</div>
          <div class="char-now">{esc(now) or '—'}</div>
          <div class="char-motive"><span class="lbl">核心动机</span>{esc(c['motive']) or '—'}</div>
        </div>""")

    # 时间线
    tl = []
    for title, beats in data["timeline"]:
        rows = "".join(
            f'<div class="beat"><span class="t">{esc(t)}</span><span class="b">{esc(b)}</span></div>'
            for t, b in beats)
        tl.append(f'<div class="tl-block"><div class="tl-title">{esc(title)}</div>{rows}</div>')

    # 悬念
    threads = "".join(f'<li>{esc(x)}</li>' for x in s["threads"]) or "<li class='muted'>（无）</li>"

    # 动态事实
    facts = []
    for f in data["facts"]:
        col = SUB_COLOR.get(f["sub"], "#8a93a3")
        facts.append(f"""
        <div class="card fact">
          <div class="fact-head">
            <span class="chip" style="--c:{col}">{esc(f['sub']) or '事实'}</span>
            <span class="fact-name">{esc(f['name'])}</span>
            <span class="fact-status">{esc(f['status'])}</span>
          </div>
          <div class="fact-sum">{esc(f['summary'])}</div>
          <div class="fact-prog"><span class="lbl">最近</span>{esc(f['last_prog']) or '—'}</div>
        </div>""")

    # 骰点
    dice = "".join(
        f'<span class="die" title="{esc(full)}">{esc(label)}</span>'
        for label, full in data["dice"]) or "<span class='muted'>（无）</span>"

    # 大事件
    if data["bigs"]:
        bigs = "".join(
            f'<div class="big"><div class="big-t">{esc(b["title"])}</div>'
            f'<div class="big-meta">{esc(b["time"])} · {esc(b["impact"])}</div></div>'
            for b in data["bigs"])
    else:
        bigs = '<div class="muted">尚无 big- 大事件。重头事件见下方时间线与悬念。</div>'

    # 编年史
    ch = data["chronicle"]
    if ch:
        paras = "".join(f"<p>{esc(p)}</p>" for p in ch["paras"])
        chronicle = f'<div class="ch-title">{esc(ch["title"])}</div><div class="ch-body clamp">{paras}</div><button class="more" onclick="this.previousElementSibling.classList.toggle(\'clamp\');this.textContent=this.previousElementSibling.classList.contains(\'clamp\')?\'展开 ▾\':\'收起 ▴\'">展开 ▾</button>'
    else:
        chronicle = '<div class="muted">（编年史尚未起笔）</div>'

    # 最近每日故事（折叠）
    ds = data.get("daily")
    if ds and ds["paras"]:
        full = "".join(f"<p>{esc(p)}</p>" for p in ds["paras"])
        preview = esc((" ".join(ds["paras"]))[:110]) + "…"
        daily = (f'<div class="ch-title">{esc(ds["title"])}</div>'
                 f'<div class="daily-prev">{preview}</div>'
                 f'<details class="daily-det"><summary>展开全文 ▾</summary><div class="ch-body">{full}</div></details>')
    else:
        daily = '<div class="muted">（还没有每日故事——每天日结后生成）</div>'

    present = "、".join(esc(clean_links(x)) for x in (m.get("出场角色") if isinstance(m.get("出场角色"), list) else m.get("出场人物") if isinstance(m.get("出场人物"), list) else []))
    gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    pending = s["pending_text"].strip()
    pending_html = ""
    if pending and "无" not in pending[:6]:
        pending_html = f'<div class="alert">⚖️ 待裁决：{esc(pending)}</div>'
    interv = s["intervention_text"].strip()
    interv_html = ""
    if interv and "无" not in interv[:6]:
        interv_html = f'<div class="alert soft">🪶 未结干预：{esc(interv)}</div>'

    return TEMPLATE.format(
        day=esc(str(day)), unit=esc(UNIT), date=esc(str(date)), clk=esc(str(clk)),
        atmo=esc(s["atmosphere"]),
        present=present or "—",
        cards="".join(cards),
        timeline="".join(tl) or "<div class='muted'>（暂无最近事件）</div>",
        threads=threads,
        facts="".join(facts) or "<div class='muted'>（暂无进行中的动态事实）</div>",
        dice=dice,
        bigs=bigs,
        chronicle=chronicle,
        daily=daily,
        alerts=pending_html + interv_html,
        gen_time=gen_time,
    )

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>故事岛 · 总览面板</title>
<style>
:root{{
  --sky1:#1a2235; --sky2:#2c2740; --sky3:#5a3b4d; --sky4:#a85a3c;
  --ink:#ece6da; --ink2:#b9b2a4; --muted:#7e8597;
  --surface:rgba(20,24,38,.62); --surface2:rgba(30,35,52,.55);
  --line:rgba(255,255,255,.09); --accent:#e0a64a;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
  color:var(--ink);background:linear-gradient(160deg,var(--sky1) 0%,var(--sky2) 38%,var(--sky3) 72%,var(--sky4) 130%);
  background-attachment:fixed;min-height:100vh;line-height:1.6;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:26px 20px 60px}}
a{{color:var(--accent)}}
.muted{{color:var(--muted);font-size:13px}}
.lbl{{display:inline-block;color:var(--muted);font-size:11px;letter-spacing:.5px;margin-right:6px;
  border:1px solid var(--line);border-radius:5px;padding:0 5px;vertical-align:1px}}

/* hero */
.hero{{display:flex;flex-wrap:wrap;align-items:flex-end;gap:6px 18px;
  border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:6px}}
.hero .day{{font-size:13px;letter-spacing:3px;color:var(--accent);text-transform:uppercase}}
.hero .clock{{font-size:46px;font-weight:700;letter-spacing:1px;line-height:1.05;margin:2px 0}}
.hero .date{{font-size:15px;color:var(--ink2);margin-bottom:6px}}
.hero .present{{font-size:13px;color:var(--ink2);margin-left:auto;text-align:right;max-width:48%}}
.atmo{{font-size:15px;color:var(--ink2);font-style:italic;margin:14px 0 4px;
  border-left:3px solid var(--accent);padding:4px 0 4px 14px}}
.alert{{margin-top:12px;padding:10px 14px;border-radius:9px;background:rgba(214,88,79,.16);
  border:1px solid rgba(214,88,79,.4);font-size:14px}}
.alert.soft{{background:rgba(224,166,74,.13);border-color:rgba(224,166,74,.35)}}

h2.sec{{font-size:14px;letter-spacing:2px;color:var(--ink2);font-weight:600;
  margin:34px 0 14px;display:flex;align-items:center;gap:10px}}
h2.sec::before{{content:"";width:5px;height:16px;border-radius:3px;background:var(--accent);display:inline-block}}

.grid{{display:grid;gap:14px}}
.cols{{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:15px 16px;
  backdrop-filter:blur(7px)}}

/* character */
.char-head{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:7px}}
.char-name{{font-size:18px;font-weight:700}}
.alias{{font-size:12px;color:var(--muted)}}
.badge{{margin-left:auto;font-size:12px;color:#10131c;background:var(--c);
  padding:1px 9px;border-radius:20px;font-weight:600}}
.char-loc{{font-size:12.5px;color:var(--ink2);margin-bottom:8px}}
.char-now{{font-size:14px;color:var(--ink);margin-bottom:10px}}
.char-motive{{font-size:12.5px;color:var(--ink2);border-top:1px dashed var(--line);padding-top:8px}}

/* timeline */
.tl-block{{margin-bottom:16px}}
.tl-title{{font-size:12.5px;color:var(--accent);font-weight:600;letter-spacing:1px;margin-bottom:7px}}
.beat{{display:flex;gap:12px;padding:3px 0;align-items:baseline}}
.beat .t{{flex:0 0 46px;font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}}
.beat .b{{font-size:14px;color:var(--ink)}}
.tl-wrap{{border-left:2px solid var(--line);padding-left:16px;margin-left:4px}}

/* threads */
ul.threads{{margin:0;padding-left:0;list-style:none}}
ul.threads li{{position:relative;padding:8px 0 8px 22px;border-bottom:1px solid var(--line);font-size:14px}}
ul.threads li:last-child{{border-bottom:none}}
ul.threads li::before{{content:"◆";position:absolute;left:2px;color:var(--accent);font-size:11px;top:11px}}

/* facts */
.fact-head{{display:flex;align-items:center;gap:9px;margin-bottom:7px;flex-wrap:wrap}}
.chip{{font-size:11px;color:#10131c;background:var(--c);padding:1px 8px;border-radius:6px;font-weight:600}}
.fact-name{{font-weight:600;font-size:15px}}
.fact-status{{margin-left:auto;font-size:12px;color:var(--accent)}}
.fact-sum{{font-size:13.5px;color:var(--ink2);margin-bottom:9px}}
.fact-prog{{font-size:12.5px;color:var(--ink2);border-top:1px dashed var(--line);padding-top:8px}}

/* dice */
.dice{{display:flex;flex-wrap:wrap;gap:7px}}
.die{{font-size:12px;background:var(--surface2);border:1px solid var(--line);border-radius:7px;
  padding:3px 9px;color:var(--ink2);font-variant-numeric:tabular-nums;cursor:default}}

/* big / chronicle */
.big{{padding:9px 0;border-bottom:1px solid var(--line)}}
.big:last-child{{border-bottom:none}}
.big-t{{font-weight:600}}
.big-meta{{font-size:12.5px;color:var(--ink2)}}
.ch-title{{color:var(--accent);font-weight:600;letter-spacing:1px;margin-bottom:8px}}
.ch-body p{{margin:0 0 10px;font-size:14px;color:var(--ink2)}}
.ch-body.clamp{{max-height:108px;overflow:hidden;
  -webkit-mask-image:linear-gradient(180deg,#000 60%,transparent);mask-image:linear-gradient(180deg,#000 60%,transparent)}}
.more{{background:none;border:1px solid var(--line);color:var(--ink2);border-radius:7px;
  padding:3px 12px;font-size:12px;cursor:pointer;margin-top:4px}}
.more:hover{{border-color:var(--accent);color:var(--accent)}}
.daily-prev{{font-size:14px;color:var(--ink2);margin-bottom:8px}}
.daily-det summary{{cursor:pointer;color:var(--accent);font-size:13px;width:max-content}}
.daily-det[open] summary{{margin-bottom:8px}}
.daily-det .ch-body p{{margin:0 0 10px;font-size:14px;color:var(--ink2)}}

footer{{margin-top:42px;padding-top:16px;border-top:1px solid var(--line);
  font-size:12px;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}}
@media(max-width:560px){{.hero .present{{max-width:100%;margin-left:0;text-align:left}}.hero .clock{{font-size:38px}}}}
</style></head>
<body><div class="wrap">

  <div class="hero">
    <div>
      <div class="day">第 {day} {unit}</div>
      <div class="clock">{clk}</div>
      <div class="date">{date}</div>
    </div>
    <div class="present">在场<br>{present}</div>
  </div>
  <div class="atmo">{atmo}</div>
  {alerts}

  <h2 class="sec">在场角色</h2>
  <div class="grid cols">{cards}</div>

  <h2 class="sec">最近事件</h2>
  <div class="card tl-wrap">{timeline}</div>

  <h2 class="sec">悬念与进行中的线</h2>
  <div class="card"><ul class="threads">{threads}</ul></div>

  <h2 class="sec">最近 · 每日故事</h2>
  <div class="card">{daily}</div>

  <h2 class="sec">动态事实</h2>
  <div class="grid cols">{facts}</div>

  <h2 class="sec">大事件</h2>
  <div class="card">{bigs}</div>

  <h2 class="sec">编年史</h2>
  <div class="card">{chronicle}</div>

  <h2 class="sec">最近骰点</h2>
  <div class="card dice">{dice}</div>

  <footer>
    <span>故事岛 · 总览面板（只读快照）</span>
    <span>生成于 {gen_time} · 推进后自动重建</span>
  </footer>
</div></body></html>"""

# ----------------------------------------------------------------------------
# Obsidian 内嵌预览页（面板预览.md）
# ----------------------------------------------------------------------------
# 为什么不是 iframe：Obsidian 阅读视图用 DOMPurify 过滤 HTML——
#   · FORBID_TAGS:["style"]           → <style> 块被删
#   · 默认 ALLOWED_URI_REGEXP         → iframe src 的 app:// / data:// 被删（只放行 http(s)）
#   · srcdoc 不在放行属性表            → 被删
# 所以本地 html 无法用 iframe 内嵌。能存活的是：普通标签 + 内联 style="" 属性。
# 于是这里把面板「原生重渲染」成只用内联样式的 HTML，直接写进笔记，阅读视图即渲染。
# 约束：不能有空行（空行会终止 Markdown 里的 HTML 块），故整段最后压掉空行。

CARD = ("background:rgba(20,24,38,.66);border:1px solid rgba(255,255,255,.12);"
        "border-radius:12px;padding:13px 15px")
SECTITLE = ("border-left:4px solid #e0a64a;padding-left:9px;font-size:14px;font-weight:600;"
            "color:#cdc6b8;letter-spacing:2px;margin:26px 0 12px")
GRID = "display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr))"
LBL  = ("color:#7e8597;font-size:11px;border:1px solid rgba(255,255,255,.12);"
        "border-radius:5px;padding:0 5px;margin-right:6px")
MUTED = "color:#7e8597;font-size:13px"

def render_native(data):
    """把面板渲染成 Obsidian 阅读视图能直接显示的内联样式 HTML（无 <style>、无 iframe）。"""
    s = data["state"]; m = s["meta"]
    day  = esc(str(m.get("当前周期", m.get("当前天数", "?"))))
    date = esc(str(m.get("当前日期", "")))
    clk  = esc(str(m.get("当前时刻", "")))
    present = "、".join(esc(clean_links(x)) for x in
                       (m.get("出场角色") if isinstance(m.get("出场角色"), list) else m.get("出场人物") if isinstance(m.get("出场人物"), list) else [])) or "—"

    H = []
    # background-color 作实底（即便 DOMPurify 删掉渐变也保证深色底、浅色字可读）；渐变作锦上添花
    H.append('<div style="background-color:#1f2536;'
             'background-image:linear-gradient(160deg,#1a2235 0%,#2c2740 40%,#5a3b4d 78%,#a85a3c 130%);'
             'color:#ece6da;line-height:1.6;padding:22px 20px;border-radius:14px;border:1px solid rgba(255,255,255,.1)">')

    # hero
    H.append('<div style="display:flex;flex-wrap:wrap;align-items:flex-end;gap:4px 18px;'
             'border-bottom:1px solid rgba(255,255,255,.12);padding-bottom:14px">'
             f'<div><div style="font-size:12px;letter-spacing:3px;color:#e0a64a">第 {day} {UNIT}</div>'
             f'<div style="font-size:40px;font-weight:700;line-height:1.05">{clk}</div>'
             f'<div style="font-size:14px;color:#b9b2a4">{date}</div></div>'
             f'<div style="margin-left:auto;text-align:right;font-size:12px;color:#b9b2a4;max-width:52%">在场<br>{present}</div></div>')

    if s["atmosphere"]:
        H.append('<div style="font-style:italic;color:#b9b2a4;border-left:3px solid #e0a64a;'
                 f'padding:4px 0 4px 12px;margin:14px 0 4px">{esc(s["atmosphere"])}</div>')

    # alerts
    pend = s["pending_text"].strip()
    if pend and "无" not in pend[:6]:
        H.append('<div style="margin-top:10px;padding:9px 13px;border-radius:9px;background:rgba(214,88,79,.16);'
                 f'border:1px solid rgba(214,88,79,.4);font-size:13px">⚖️ 待裁决：{esc(pend)}</div>')
    interv = s["intervention_text"].strip()
    if interv and "无" not in interv[:6]:
        H.append('<div style="margin-top:10px;padding:9px 13px;border-radius:9px;background:rgba(224,166,74,.13);'
                 f'border:1px solid rgba(224,166,74,.35);font-size:13px">🪶 未结干预：{esc(interv)}</div>')

    # 在场角色
    H.append(f'<div style="{SECTITLE}">在场角色</div>')
    cards = []
    for c in data["chars"]:
        now = match_snapshot(c, s["snapshot"]) or c["last_mem"]
        col = STATUS_COLOR.get(c["status"], "#8a93a3")
        alias = ("　" + " / ".join(esc(a) for a in c["aliases"])) if c["aliases"] else ""
        cards.append(
            f'<div style="{CARD}">'
            '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">'
            f'<span style="font-size:17px;font-weight:700">{esc(c["name"])}</span>'
            f'<span style="font-size:12px;color:#7e8597">{alias}</span>'
            f'<span style="margin-left:auto;background:{col};color:#10131c;padding:1px 9px;border-radius:20px;font-size:12px;font-weight:600">{esc(c["status"])}</span></div>'
            f'<div style="font-size:12.5px;color:#b9b2a4;margin-bottom:7px">📍 {esc(c["loc"]) or "—"}</div>'
            f'<div style="font-size:13.5px;margin-bottom:9px">{esc(now) or "—"}</div>'
            f'<div style="font-size:12.5px;color:#b9b2a4;border-top:1px dashed rgba(255,255,255,.12);padding-top:7px">'
            f'<span style="{LBL}">核心动机</span>{esc(c["motive"]) or "—"}</div></div>')
    cards_html = "".join(cards) or f'<span style="{MUTED}">（无在场角色）</span>'
    H.append(f'<div style="{GRID}">{cards_html}</div>')

    # 最近事件
    H.append(f'<div style="{SECTITLE}">最近事件</div>')
    tl = []
    for title, beats in data["timeline"]:
        rows = "".join(
            '<div style="display:flex;gap:10px;padding:3px 0">'
            f'<span style="flex:0 0 46px;color:#7e8597;font-size:12.5px">{esc(t)}</span>'
            f'<span style="font-size:13.5px">{esc(b)}</span></div>'
            for t, b in beats)
        tl.append('<div style="margin-bottom:13px">'
                  f'<div style="color:#e0a64a;font-size:12.5px;font-weight:600;letter-spacing:1px;margin-bottom:5px">{esc(title)}</div>{rows}</div>')
    tl_html = "".join(tl) or f'<span style="{MUTED}">（暂无最近事件）</span>'
    H.append(f'<div style="{CARD};border-left:2px solid rgba(255,255,255,.12)">{tl_html}</div>')

    # 悬念与进行中的线
    H.append(f'<div style="{SECTITLE}">悬念与进行中的线</div>')
    th = "".join(
        '<div style="position:relative;padding:7px 0 7px 20px;border-bottom:1px solid rgba(255,255,255,.1);font-size:13.5px">'
        f'<span style="position:absolute;left:0;color:#e0a64a">◆</span>{esc(x)}</div>'
        for x in s["threads"]) or f'<span style="{MUTED}">（无）</span>'
    H.append(f'<div style="{CARD}">{th}</div>')

    # 最近 · 每日故事（折叠）
    H.append(f'<div style="{SECTITLE}">最近 · 每日故事</div>')
    ds = data.get("daily")
    if ds and ds["paras"]:
        full = "".join(f'<p style="margin:0 0 9px;font-size:13.5px;color:#b9b2a4">{esc(p)}</p>' for p in ds["paras"])
        preview = esc((" ".join(ds["paras"]))[:110]) + "…"
        daily = (f'<div style="color:#e0a64a;font-weight:600;letter-spacing:1px;margin-bottom:6px">{esc(ds["title"])}</div>'
                 f'<div style="font-size:13.5px;color:#b9b2a4;margin-bottom:6px">{preview}</div>'
                 f'<details><summary style="cursor:pointer;color:#e0a64a;font-size:13px">展开全文 ▾</summary>'
                 f'<div style="margin-top:8px">{full}</div></details>')
    else:
        daily = f'<span style="{MUTED}">（还没有每日故事——每天日结后生成）</span>'
    H.append(f'<div style="{CARD}">{daily}</div>')

    # 动态事实
    H.append(f'<div style="{SECTITLE}">动态事实</div>')
    fcards = []
    for f in data["facts"]:
        col = SUB_COLOR.get(f["sub"], "#8a93a3")
        fcards.append(
            f'<div style="{CARD}">'
            '<div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:6px">'
            f'<span style="background:{col};color:#10131c;padding:1px 8px;border-radius:6px;font-size:11px;font-weight:600">{esc(f["sub"]) or "事实"}</span>'
            f'<span style="font-weight:600;font-size:15px">{esc(f["name"])}</span>'
            f'<span style="margin-left:auto;font-size:12px;color:#e0a64a">{esc(f["status"])}</span></div>'
            f'<div style="font-size:13px;color:#b9b2a4;margin-bottom:8px">{esc(f["summary"])}</div>'
            f'<div style="font-size:12.5px;color:#b9b2a4;border-top:1px dashed rgba(255,255,255,.12);padding-top:7px">'
            f'<span style="{LBL}">最近</span>{esc(f["last_prog"]) or "—"}</div></div>')
    fcards_html = "".join(fcards) or f'<span style="{MUTED}">（暂无进行中的动态事实）</span>'
    H.append(f'<div style="{GRID}">{fcards_html}</div>')

    # 大事件
    H.append(f'<div style="{SECTITLE}">大事件</div>')
    if data["bigs"]:
        bigs = "".join(
            '<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.1)">'
            f'<div style="font-weight:600">{esc(b["title"])}</div>'
            f'<div style="font-size:12.5px;color:#b9b2a4">{esc(b["time"])} · {esc(b["impact"])}</div></div>'
            for b in data["bigs"])
    else:
        bigs = f'<span style="{MUTED}">尚无 big- 大事件。重头事件见上方时间线与悬念。</span>'
    H.append(f'<div style="{CARD}">{bigs}</div>')

    # 编年史
    H.append(f'<div style="{SECTITLE}">编年史</div>')
    ch = data["chronicle"]
    if ch:
        paras = "".join(f'<p style="margin:0 0 9px;font-size:13.5px;color:#b9b2a4">{esc(p)}</p>' for p in ch["paras"])
        chronicle = f'<div style="color:#e0a64a;font-weight:600;letter-spacing:1px;margin-bottom:8px">{esc(ch["title"])}</div>{paras}'
    else:
        chronicle = f'<span style="{MUTED}">（编年史尚未起笔）</span>'
    H.append(f'<div style="{CARD}">{chronicle}</div>')

    # 最近骰点
    H.append(f'<div style="{SECTITLE}">最近骰点</div>')
    dice = "".join(
        f'<span title="{esc(full)}" style="display:inline-block;font-size:12px;background:rgba(30,35,52,.6);'
        f'border:1px solid rgba(255,255,255,.12);border-radius:7px;padding:3px 9px;margin:0 6px 6px 0;color:#b9b2a4">{esc(label)}</span>'
        for label, full in data["dice"]) or f'<span style="{MUTED}">（无）</span>'
    H.append(f'<div style="{CARD}">{dice}</div>')

    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    H.append('<div style="margin-top:20px;padding-top:12px;border-top:1px solid rgba(255,255,255,.12);'
             f'font-size:12px;color:#7e8597">故事岛 · 总览面板（只读快照）· 生成于 {gen} · 推进后自动重建</div>')

    H.append('</div>')
    body = "".join(H)
    # 兜底：去掉任何空行（Markdown 中空行会截断 HTML 块）
    body = re.sub(r"[\r\n]+", " ", body)
    return body, gen


PREVIEW_NOTE = """---
类型: 说明
名称: 面板预览
cssclasses:
  - panel-wide
---

# 故事岛 · 面板预览

> 本页是全部「面板」（可视化）的单一汇总预览。默认只有**故事发展面板**（下方内联 HTML，切**阅读视图**看）。
> 由 `build_panel.py` **每次推进自动重建**，正文勿手改（会被覆盖）。高保真双击 [[故事岛-面板.html]] 用浏览器打开。
>
> 新增派生面板：在下面「派生面板嵌入区」按 `## <emoji> <名>面板` + 空行 + `![[<名>.svg]]` 加一段（详见 `07-面板/_说明.md` 派生面板节）。

## 📊 故事发展面板（总览）

__PANEL__

<!-- 派生面板嵌入区（默认空）：每张派生面板在此加「## 标题」+空行+「![[<名>.svg]]」+空行 -->
"""

def write_preview(data):
    body, _gen = render_native(data)
    note = PREVIEW_NOTE.replace("__PANEL__", body)
    PREVIEW.write_text(note, encoding="utf-8")


# ----------------------------------------------------------------------------
def flag_log_gate(day_err, state_err, meta, log_path=None):
    """选项A·安全网落痕：把格式闸结果写一行进 _log.md（无人值守时控制台会滚走，_log 你每次会读）。

    - 有 ERROR → 顶部刷新**唯一一条** `- ⚠️闸·…` 标记（同条刷新、不堆叠）。
    - 无 ERROR → 移除残留标记（**自清**，改绿后下次推进自动消失）。
    只增删 `- ⚠️闸·` 标记行；正常 `- 20xx` 史实条目一行不碰（不违 §5·3、不计入 _log 十条账）。
    """
    log = Path(log_path) if log_path else (VAULT / "_log.md")
    if not log.exists():
        return False
    lines = log.read_text(encoding="utf-8").split("\n")
    kept = [l for l in lines if not l.lstrip().startswith("- ⚠️闸·")]
    changed = len(kept) != len(lines)
    if day_err or state_err:
        from datetime import date
        parts = []
        if day_err:
            parts.append(f"日志 {day_err}")
        if state_err:
            parts.append(f"_state {state_err}")
        flag = (f"- ⚠️闸·{date.today().isoformat()}（现实）· build_panel 安全网逮到 ERROR："
                f"{' / '.join(parts)}（世界内 第{meta.get('当前周期',meta.get('当前天数','?'))}{UNIT} {meta.get('当前时刻','')}）"
                f"——上次写时漏跑了格式闸，回去按行号改干净 / 就地压实（§4.1·7 日志 · §4.1·11 _state）；改绿后本行自动消失。")
        ins = next((i for i, l in enumerate(kept) if l.lstrip().startswith("- 20")), None)
        if ins is None:
            kept.append(flag)
        else:
            kept.insert(ins, flag)
        changed = True
    if changed:
        log.write_text("\n".join(kept), encoding="utf-8")
        print("[闸] 已在 _log 顶部留一条自清 ⚠️闸 标记（无人值守可见）。"
              if (day_err or state_err) else "[闸] _log 残留闸标记已清。")
    return changed


def main():
    global UNIT
    state = load_state()
    UNIT = state["meta"].get("周期量词", "天") or "天"
    day = latest_day()
    data = {
        "state": state,
        "chars": load_characters(),
        "timeline": load_timeline_global(),
        "dice": load_dice(day),
        "facts": load_facts(),
        "bigs": load_bigs(),
        "chronicle": load_chronicle(),
        "daily": load_daily_story(),
    }
    html_doc = render(data)
    OUT.write_text(html_doc, encoding="utf-8")
    write_preview(data)
    # 顺带重建派生面板（每张是独立零依赖 build_<名>.py）。模板默认无派生面板，元组留空待填。
    # 新增派生面板时把模块名加进下面元组（详见 07-面板/_说明.md 派生面板节）。报错不阻断面板/推进。
    for _mod in ():
        try:
            __import__(_mod).main()
        except Exception as e:
            print(f"[面板] {_mod} 跳过（不阻断）：{e}")
    print(f"[面板] 已生成 → {OUT}")
    print(f"[面板] 原生内嵌预览 → {PREVIEW}")
    print(f"[面板] 第{data['state']['meta'].get('当前周期',data['state']['meta'].get('当前天数','?'))}{UNIT} "
          f"{data['state']['meta'].get('当前时刻','')} · "
          f"角色 {len(data['chars'])} · 动态事实 {len(data['facts'])} · "
          f"骰点 {len(data['dice'])} · 时间线段 {len(data['timeline'])}")
    # 两道格式闸（安全网·冗余）：每次推进各再跑一遍，把违规大声打出来。
    # 真正的写时闸在 CLAUDE.md §4.1·7（日志）/ §4.1·11（_state）——写完即跑；这里兜底无人值守时漏跑。
    # 报错不阻断面板/推进（无人值守时也至少留下一行可见的红/绿判定）。
    day_err = state_err = 0
    try:
        sys.path.insert(0, str(VAULT / "08-脚本"))   # lint_day/lint_state 现都住 08-脚本/
        import lint_day
        day_err, _w = lint_day.check_latest()
        if day_err:
            print(f"[闸] ❗最新一天日志有 {day_err} 处 ERROR——正文漂了，回去按行号改干净（见上）。")
    except Exception as e:
        print(f"[闸] 日志 lint 跳过（不阻断）：{e}")
    try:
        sys.path.insert(0, str(VAULT / "08-脚本"))
        import lint_state
        state_err, _w = lint_state.check()
        if state_err:
            print(f"[闸] ❗_state 有 {state_err} 处 ERROR——逐时回放了，回去就地压实（见上）。")
    except Exception as e:
        print(f"[闸] _state lint 跳过（不阻断）：{e}")
    # 选项A·安全网落痕：把闸结果落进 _log（红→刷新自清标记，绿→清掉）。报错不阻断。
    try:
        flag_log_gate(day_err, state_err, data["state"]["meta"])
    except Exception as e:
        print(f"[闸] _log 标记跳过（不阻断）：{e}")

if __name__ == "__main__":
    main()
