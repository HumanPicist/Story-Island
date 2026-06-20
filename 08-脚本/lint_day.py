#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
故事岛 · 日志格式闸（lint_day.py）
================================================
零依赖（纯 python3 标准库）。检查日志容器（`周期-第N天.md`，史诗如 `纪元-第N纪.md`；glob `02-日志/*.md` 除 `_说明`）的**正文**是否守住「日志格式铁律」
（canonical：`02-日志/_说明.md` §格式铁律 / CLAUDE.md §4.1 推进流程）：

    日志正文是给人读的故事，不是给引擎读的状态台账。

它只看正文（frontmatter 里的 `骰点:` 是骰值的合法归宿，不查；今日延伸尾块按较松规则查）。

用法：
    python3 08-脚本/lint_day.py            # 查最新一天
    python3 08-脚本/lint_day.py 第5天        # 指定某天
    python3 08-脚本/lint_day.py 5
    python3 08-脚本/lint_day.py 02-日志/day-第5天.md
    python3 08-脚本/lint_day.py all         # 全部日志容器巡检（盘点用）

退出码：0 = 绿（无 ERROR）；1 = 红（有 ERROR）。WARN 不改变退出码。

设计：ERROR 卡正文漂移（内联骰值 / 系统元词 / 整点小结膨胀）——这是「又出现掷骰和系统用语」
要根治的东西，红了就该回去改干净再继续推进；WARN 提示尾块（今日延伸）偏离基线，低风险、不阻断。
范式＝格式铁律 #1–#3 本身：骰点全在 frontmatter，正文全是动作、对白、感官细节。
（新世界起初没有任何 day；第一天就照模板与铁律写，机器判定一律以本脚本绿为准。）
"""

import re, sys, glob
from pathlib import Path

sys.dont_write_bytecode = True   # 不在 08-脚本/ 生成 __pycache__
try:
    import _config as CFG        # 同目录 08-脚本/_config.py：读「调参面板.md」覆盖默认
except Exception:                # 读取器缺失/出错也不影响——全部回退脚本内默认值
    class _Shim:
        def num(self, k, d, lo=None, hi=None): return d
        def words(self, d, add_key=None, drop_key=None): return list(d)
    CFG = _Shim()

VAULT  = Path(__file__).resolve().parent.parent
LOGDIR = VAULT / "02-日志"

# ── 规则参数（默认值在此；可在 08-脚本/调参面板.md 零门槛覆盖，写错自动回退默认）──────
# A·内联骰值：正文里任何骰值/裁决记号（完整骰点该住 frontmatter 的 `骰点:`）。正则属进阶项，改它请直接编辑本脚本。
DICE_REGEX = [
    r"掷骰", r"D\d+\s*=", r"（\s*D\d", r"骰点\s*=", r"行为\s*=\s*\d",
]
# B·系统/元词：引擎自己的裁决与追踪语，绝不进 day 正文（要表达"意义"，用角色的感受与动作写）
# 默认词表在此；可在调参面板.md 用「日志·额外禁词 / 日志·豁免词」零门槛增删（基线不会被清空）。
SYSTEM_WORDS = CFG.words([
    "登记进", "指针", "悬置", "未兑现", "measured", "declared", "grounded",
    "〔意义", "〔清楚的新状态", "〔设定级", "红线守旧界", "钟仍在", "降档", "活跃面",
], add_key="日志·额外禁词", drop_key="日志·豁免词")
SYSTEM_REGEX = [r"\bQ\d"]               # Q6 悬置 之类的问题编号
# C·整点小结：每个整点收口只写「一句话现场快照」，不逐角色列状态、不挂子条目
HOURLY_PROSE_MAX = CFG.num("整点小结字数上限", 120, lo=40, hi=400)   # 〔整点…〕之后正文字数上限，超过即非"一句话"
# D/E·今日延伸尾块（WARN）：基线里「动态事实更新」是裸链、「悬念」是一行
THREAD_LINE_MAX  = CFG.num("日志悬念行字数上限", 280, lo=80, hi=800)  # 悬念行字数上限（防 per-角色台账膨胀）
# ───────────────────────────────────────────────────────────────────────


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def latest_day_path():
    best, bn = None, -1
    for fp in glob.glob(str(LOGDIR / "*.md")):
        if Path(fp).name == "_说明.md":
            continue
        m = re.search(r"第(\d+)", Path(fp).stem)
        n = int(m.group(1)) if m else 0
        if n >= bn:
            best, bn = fp, n
    return best


def resolve_targets(arg):
    if arg in (None, "", "latest"):
        p = latest_day_path()
        return [p] if p else []
    if arg == "all":
        def _n(f):
            mm = re.search(r"第(\d+)", Path(f).stem)
            return int(mm.group(1)) if mm else 0
        files = [f for f in glob.glob(str(LOGDIR / "*.md")) if Path(f).name != "_说明.md"]
        return sorted(files, key=_n)
    if str(arg).endswith(".md"):
        p = Path(arg)
        return [str(p if p.is_absolute() else VAULT / arg)]
    m = re.search(r"(\d+)", str(arg))
    if m:
        hits = [f for f in glob.glob(str(LOGDIR / "*.md"))
                if Path(f).name != "_说明.md" and re.search(rf"第{m.group(1)}\D", Path(f).stem + " ")]
        return hits[:1] or [str(LOGDIR / f"day-第{m.group(1)}天.md")]
    return [str(LOGDIR / str(arg))]


def split_regions(text):
    """返回 (lines, body_start, tail_start)。body=正文叙事；tail=今日延伸尾块。"""
    lines = text.split("\n")
    body_start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i + 1
                break
    tail_start = len(lines)
    for i in range(body_start, len(lines)):
        s = lines[i].lstrip()
        if s.startswith("#") and "今日延伸" in s:
            tail_start = i
            break
    return lines, body_start, tail_start


def lint_text(text):
    """返回 issues 列表：(lineno, severity, code, msg, snippet)。lineno 为 1 基文件行号。"""
    lines, body_start, tail_start = split_regions(text)
    issues = []

    def snip(s):
        s = s.strip()
        return s if len(s) <= 64 else s[:62] + "…"

    # ── 正文叙事（body_start .. tail_start）：A/B/C ──
    for idx in range(body_start, tail_start):
        ln = lines[idx]
        no = idx + 1
        # A·内联骰值
        for pat in DICE_REGEX:
            if re.search(pat, ln):
                issues.append((no, "ERROR", "DICE", "正文出现骰值/裁决记号（骰点只住 frontmatter）", snip(ln)))
                break
        # B·系统/元词
        hit = next((w for w in SYSTEM_WORDS if w in ln), None)
        if not hit:
            for rx in SYSTEM_REGEX:
                if re.search(rx, ln):
                    hit = rx
                    break
        if hit:
            issues.append((no, "ERROR", "SYS", f"正文出现系统/元词「{hit}」（引擎追踪语不进正文）", snip(ln)))
        # C·整点小结
        if "整点" in ln and ln.lstrip().startswith("-"):
            prose = ln.split("〕", 1)[1] if "〕" in ln else ln
            if len(prose.strip()) > HOURLY_PROSE_MAX:
                issues.append((no, "ERROR", "HOUR_LONG",
                               f"整点收口超一句话（正文 {len(prose.strip())} 字 > {HOURLY_PROSE_MAX}）——压成一句现场快照",
                               snip(ln)))
            # 整点 beat 不该挂逐角色子条目
            j = idx + 1
            while j < tail_start:
                nxt = lines[j]
                if nxt.strip() == "":
                    j += 1
                    continue
                if re.match(r"^\s{2,}-\s", nxt):
                    issues.append((j + 1, "ERROR", "HOUR_ENUM",
                                   "整点收口下挂了子条目（逐角色状态是 _state 的活儿，日志不列第二遍）",
                                   snip(nxt)))
                break

    # ── 今日延伸尾块（tail_start ..）：D/E（WARN）──
    for idx in range(tail_start, len(lines)):
        ln = lines[idx].strip()
        no = idx + 1
        if ln.startswith("- 动态事实更新") and ("（" in ln or "(" in ln):
            issues.append((no, "WARN", "TAIL_DF",
                           "「动态事实更新」带了括号注释（基线为裸链；细节归 fact-* 页）", snip(ln)))
        if ln.startswith("- 悬念推进"):
            issues.append((no, "WARN", "TAIL_LABEL",
                           "尾块用了「悬念推进」（基线为「悬念」一行；状态归 _state）", snip(ln)))
        if (ln.startswith("- 悬念") and len(ln) > THREAD_LINE_MAX):
            issues.append((no, "WARN", "TAIL_LONG",
                           f"「悬念」行过长（{len(ln)} 字 > {THREAD_LINE_MAX}）——压回一行，别铺成 per-角色台账", snip(ln)))

    return issues


def lint_file(path):
    text = read(path)
    if not text:
        return path, None
    return path, lint_text(text)


def check_paths(targets, emit=print):
    """巡检多份 day 文件；打印报告；返回 (total_err, total_warn)。"""
    tot_e = tot_w = 0
    for p in targets:
        name = Path(p).name
        _, issues = lint_file(p)
        if issues is None:
            emit(f"[闸] ⚠️ 找不到或读不出：{p}")
            continue
        errs = [i for i in issues if i[1] == "ERROR"]
        warns = [i for i in issues if i[1] == "WARN"]
        tot_e += len(errs)
        tot_w += len(warns)
        if not issues:
            emit(f"[闸] ✅ {name} 正文干净（守住格式铁律 #1–#3）")
            continue
        emit(f"[闸] {'❌' if errs else '⚠️'} {name}：{len(errs)} ERROR / {len(warns)} WARN")
        for no, sev, code, msg, sp in sorted(issues):
            mark = "❌" if sev == "ERROR" else "⚠️"
            emit(f"      {mark} L{no} [{code}] {msg}")
            emit(f"          ↳ {sp}")
    if tot_e:
        emit(f"[闸] 红：{tot_e} 处 ERROR——回正文按行号改干净、重跑到绿，再写 _state / 跑 build_panel。铁律见 02-日志/_说明.md §格式铁律。")
    elif tot_w:
        emit(f"[闸] 绿（有 {tot_w} 处 WARN，建议顺手收尾，不阻断推进）。")
    return tot_e, tot_w


def check_latest(emit=print):
    p = latest_day_path()
    if not p:
        emit("[闸] 没有日志容器（02-日志/ 下的 周期-* / day-* 等）可查。")
        return 0, 0
    return check_paths([p], emit=emit)


def main(argv):
    arg = argv[1] if len(argv) > 1 else None
    targets = resolve_targets(arg)
    if not targets:
        print("[闸] 没有目标可查。")
        return 0
    err, _warn = check_paths(targets)
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
