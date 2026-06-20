#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
故事岛 · _state 格式闸（lint_state.py）
================================================
零依赖（纯 python3 标准库）。与 `02-日志/lint_day.py` 对称：日志闸守「正文不写引擎台账」，
本闸守「`_state` 是快照、不是存档」（canonical：CLAUDE.md 附录A `_state` 说明 / §4.1·11）：

    _state 只写「下一窗口推进需要的最小现状」。同一 beat 不在
    「当前态 / 在场快照 / 悬念」里写第二遍；逐时细节归 `day-*`。

它的命门是**逐时回放**——把刚写完的 `day-*` 又按窗口（甚至按角色）抄进 `_state`，
于是一个 beat 被复述 4–7 次，文件越长越像历史账。本闸用「时间戳密度」抓这个动作：
快照只该引用极少几个钟点；一段里塞了一长串 `HH:MM`，就是把日志搬进来了。

用法：
    python3 08-脚本/lint_state.py            # 查 _state.md
    python3 08-脚本/lint_state.py _state.md  # 指定文件

退出码：0 = 绿（无 ERROR）；1 = 红（有 ERROR）。WARN 不改变退出码。

ERROR（卡住、必须改）= 逐时回放：当前态/在场快照里时间戳成串——这是要根治的复发动作。
WARN（提示、不阻断）= 体量：条目超长 / 整体膨胀 / 最近推进字段过长——顺手压实即可。
设计取舍：ERROR 只押在「回放」这个最不会误判的信号上；体量类一律 WARN，宁可漏报不误杀。
"""

import re, sys
from pathlib import Path

sys.dont_write_bytecode = True   # 不在 08-脚本/ 生成 __pycache__
try:
    import _config as CFG        # 同目录 08-脚本/_config.py：读「调参面板.md」覆盖默认
except Exception:                # 读取器缺失/出错也不影响——全部回退脚本内默认值
    class _Shim:
        def num(self, k, d, lo=None, hi=None): return d
        def words(self, d, add_key=None, drop_key=None): return list(d)
    CFG = _Shim()

VAULT = Path(__file__).resolve().parent.parent
STATE = VAULT / "_state.md"

# ── 规则参数（默认值在此；可在 08-脚本/调参面板.md 零门槛覆盖，写错自动回退默认）──────
# A·逐时回放（ERROR）：快照里单段/单条的 HH:MM 时间戳数量上限，超过＝把 day 日志搬进来了
CURTIME_TS_MAX     = CFG.num("当前态时间戳上限", 5, lo=2, hi=20)        # 「当前世界时间」区单行时间戳上限
SNAPSHOT_TS_MAX    = CFG.num("在场快照时间戳上限", 3, lo=1, hi=12)       # 「在场快照」每条角色 bullet 内时间戳上限
# B·体量（WARN）：条目与整体字数/行数，软上限、judgment 优先
SNAPSHOT_CHARS_MAX = CFG.num("在场快照每条字数上限", 280, lo=80, hi=1000)   # 在场快照每条字数（≤约2行）
THREAD_CHARS_MAX   = CFG.num("活跃悬念每条字数上限", 300, lo=80, hi=1000)   # 活跃悬念每条字数（≤约2–3行）
RECENT_FIELD_MAX   = CFG.num("最近推进字数上限", 300, lo=80, hi=1000)       # frontmatter「最近推进」字数（一句窗口提要）
BODY_LINES_MAX     = CFG.num("快照正文行数上限", 46, lo=20, hi=400)       # 正文总行数（防整体膨胀）
BODY_CHARS_MAX     = CFG.num("快照正文字数上限", 5000, lo=1500, hi=40000) # 正文总字数
# ───────────────────────────────────────────────────────────────────────

TS = re.compile(r"\d{1,2}:\d{2}")          # HH:MM 时间戳
H2 = re.compile(r"^\s*##\s+(.*?)\s*$")     # 二级标题
BULLET = re.compile(r"^\s*-\s+\*\*")       # 「- **题目**」式条目


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def split_front(text):
    """返回 (front_lines, body_lines, body_offset)。body_offset 为正文首行的 1 基文件行号。"""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[1:i], lines[i + 1:], i + 2
    return [], lines, 1


def snip(s):
    s = s.strip()
    return s if len(s) <= 64 else s[:62] + "…"


def lint_text(text):
    """返回 issues 列表：(lineno, severity, code, msg, snippet)。"""
    front, body, body_off = split_front(text)
    issues = []

    # ── frontmatter：最近推进字段长度（WARN）──
    for i, ln in enumerate(front):
        m = re.match(r"\s*最近推进\s*:\s*(.*)$", ln)
        if m:
            val = m.group(1).strip().strip('"').strip("'")
            if len(val) > RECENT_FIELD_MAX:
                issues.append((i + 2, "WARN", "FRONT_LONG",
                               f"frontmatter「最近推进」过长（{len(val)} 字 > {RECENT_FIELD_MAX}）——收成一句窗口提要，逐时归 day-*",
                               snip(val)))
            break

    # ── 正文：按 ## 分区，逐区查回放与体量 ──
    section = ""
    for j, ln in enumerate(body):
        no = body_off + j
        h = H2.match(ln)
        if h:
            section = h.group(1)
            continue

        ts_n = len(TS.findall(ln))

        # A·逐时回放（ERROR）
        if "当前世界时间" in section and ts_n > CURTIME_TS_MAX:
            issues.append((no, "ERROR", "TS_REPLAY",
                           f"「当前态」单段塞了 {ts_n} 个时间戳（>{CURTIME_TS_MAX}）——这是把 day 日志逐时搬进来了，只留现状、逐时归 day-*",
                           snip(ln)))
        if "在场快照" in section and BULLET.match(ln) and ts_n > SNAPSHOT_TS_MAX:
            issues.append((no, "ERROR", "TS_REPLAY",
                           f"在场快照单条塞了 {ts_n} 个时间戳（>{SNAPSHOT_TS_MAX}）——快照只记当前位置+状态，别按角色回放整窗口",
                           snip(ln)))

        # B·体量（WARN）
        if "在场快照" in section and BULLET.match(ln) and len(ln.strip()) > SNAPSHOT_CHARS_MAX:
            issues.append((no, "WARN", "SNAP_LONG",
                           f"在场快照单条过长（{len(ln.strip())} 字 > {SNAPSHOT_CHARS_MAX}）——压到 ≤约2行（当前位置+状态）",
                           snip(ln)))
        if section.startswith("悬念") and BULLET.match(ln) and len(ln.strip()) > THREAD_CHARS_MAX:
            issues.append((no, "WARN", "THREAD_LONG",
                           f"悬念单条过长（{len(ln.strip())} 字 > {THREAD_CHARS_MAX}）——压到 ≤约2–3行，过程细节归 fact-*/day-*",
                           snip(ln)))

    # ── 整体膨胀（WARN）──
    body_nonblank = [l for l in body if l.strip()]
    body_chars = sum(len(l) for l in body)
    if len(body) > BODY_LINES_MAX:
        issues.append((body_off, "WARN", "BODY_BLOAT",
                       f"正文 {len(body)} 行（>{BODY_LINES_MAX}）——_state 是快照不是存档，整体偏胖，复查是否在回放窗口",
                       f"{len(body_nonblank)} 非空行 / {body_chars} 字"))
    elif body_chars > BODY_CHARS_MAX:
        issues.append((body_off, "WARN", "BODY_BLOAT",
                       f"正文 {body_chars} 字（>{BODY_CHARS_MAX}）——整体偏胖，复查是否在回放窗口",
                       f"{len(body_nonblank)} 非空行"))

    return issues


def check(path=STATE, emit=print):
    text = read(path)
    name = Path(path).name
    if not text:
        emit(f"[_state闸] ⚠️ 找不到或读不出：{path}")
        return 0, 0
    issues = lint_text(text)
    errs = [i for i in issues if i[1] == "ERROR"]
    warns = [i for i in issues if i[1] == "WARN"]
    if not issues:
        emit(f"[_state闸] ✅ {name} 是快照（无逐时回放、体量在界内）")
        return 0, 0
    emit(f"[_state闸] {'❌' if errs else '⚠️'} {name}：{len(errs)} ERROR / {len(warns)} WARN")
    for no, sev, code, msg, sp in sorted(issues):
        mark = "❌" if sev == "ERROR" else "⚠️"
        emit(f"      {mark} L{no} [{code}] {msg}")
        emit(f"          ↳ {sp}")
    if errs:
        emit("[_state闸] 红：有逐时回放——回 _state 按行号就地压实（同一 beat 只写一遍、逐时归 day-*），重跑到绿再继续。canonical：CLAUDE.md 附录A `_state` / §4.1·11。")
    else:
        emit("[_state闸] 绿（有 WARN：体量偏胖，建议顺手压实，不阻断）。")
    return len(errs), len(warns)


def main(argv):
    arg = argv[1] if len(argv) > 1 else None
    path = STATE
    if arg:
        p = Path(arg)
        path = p if p.is_absolute() else VAULT / arg
    err, _ = check(path)
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
