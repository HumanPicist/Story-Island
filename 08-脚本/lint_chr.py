#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
故事岛 · 记忆格式闸（lint_chr.py）
================================================
零依赖（纯 python3 标准库）。检查 `chr-*.md` 的**重要记忆**是否守住「覆写式纪律 + 分类字数闸」
（canonical：`01-角色/_说明.md` §重要记忆·覆写式纪律 / CLAUDE.md §4.7·3）：

    重要记忆是沉淀下来的耐久核，不是第二本日志。
    最危险的发胖＝「按天 append」：同一条弧每天往尾巴上摞一条带日期 beat。

闸怎么卡（**按字数不按行**——md 里一行可 20 字可 200 字，行无意义）：
  · 关键事件·节点 ＝ 带日期史实锚点，append-but-tight，只卡**每条字数**（史实不删，§5·3）
  · 关系变化 / 心境·弧线 ＝ **覆写式**：一对关系/一条弧只占一段、改写不 append
        → 卡**段数**（按天摞就会超）+ **每段字数**
  · 短期记忆 ＝ 滚动窗口：**每条字数 ERROR**（闸只在日结跑·那时该已压成「要点+指针」）、条数 WARN（§4.7 软性）
  · 反元词 ＝ 重要+短期记忆正文里**禁引擎记账词**（Q\d/悬置/measured…/〔意义…等，ERROR）——记忆给人读不是台账，
        同日志铁律 #2；但为记忆层裁窄：放过 指针/活跃面/降档（schema「要点+指针」里它们合法）。`>` 结算注释行不查。

字数口径：剥掉 `←` 指针尾、`[[wikilink]]`、行首 `- `、行首 `[时间戳]`、`** \` > #` 等 md 记号后的净字数。

用法：
    python3 08-脚本/lint_chr.py            # 查所有 chr-*.md
    python3 08-脚本/lint_chr.py 某角色       # 查 chr-某角色.md
    python3 08-脚本/lint_chr.py 01-角色/chr-某角色.md
    python3 08-脚本/lint_chr.py all

退出码：0 = 绿（无 ERROR）；1 = 红（有 ERROR）。WARN 不改变退出码。

设计：ERROR 卡「覆写式被破坏 / 条目膨胀」（关系变化·弧线超段数 = 在按天 append；某条超字数 = 写成小作文）——
红了回去**合并/改写**到绿（consolidate 不是 amputate：史实不删、长期默认不删、cap 设宽是故意的，
别为达标把角色的摩擦/矛盾/未完成磨成讨好的整洁条目——那是本系统最反对的收敛）。WARN 提示短期条数 / 重要记忆总量，低风险不阻断。
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
CHRDIR = VAULT / "01-角色"

# ── 规则参数（默认值在此；可在 08-脚本/调参面板.md 零门槛覆盖，写错自动回退默认）──────
#    与 01-角色/_说明.md 字数闸表 / CLAUDE.md §4.7·3 同一来源。
KEY_EVENT_ZI_MAX = CFG.num("关键事件每条字数上限", 200, lo=80, hi=600)   # 关键事件·节点 每条字数（史实锚点·过程归 日志/evt/big）
REL_COUNT_MAX    = CFG.num("关系变化段数上限", 6, lo=2, hi=30)          # 关系变化 段数（≈关系对数·覆写式不随天涨；超＝在按天 append）
REL_ZI_MAX       = CFG.num("关系变化每段字数上限", 140, lo=60, hi=500)   # 关系变化 每段字数
ARC_COUNT_MAX    = CFG.num("心境弧线条数上限", 8, lo=2, hi=30)          # 心境·弧线 条数（覆写式·一弧一段）
ARC_ZI_MAX       = CFG.num("心境弧线每条字数上限", 160, lo=60, hi=500)   # 心境·弧线 每条字数
ZHONG_TOTAL_WARN = CFG.num("重要记忆总字数提醒线", 2200, lo=800, hi=12000)  # 重要记忆 全段字数（WARN·随史增长的提醒线）
SHORT_COUNT_WARN = CFG.num("短期记忆条数提醒线", 30, lo=8, hi=120)       # 短期记忆 条数（WARN·§4.7 软性 judgment 优先）
SHORT_ZI_MAX     = CFG.num("短期记忆每条字数上限", 150, lo=60, hi=500)   # 短期记忆 每条字数（ERROR·校准自早期「要点+指针」~110–130 字）

# 反元词（ERROR）：记忆是给人读的，不是引擎台账——引擎记账词不许进记忆正文。
# 与日志格式铁律 #2（lint_day.py SYSTEM_WORDS）同口径，但**为记忆层裁窄**：
#   放过 指针 / 活跃面 / 降档——它们在记忆里是合法词（短期记忆 schema 就叫「要点+指针」）。
# 默认词表在此；可在调参面板.md 用「记忆·额外禁词 / 记忆·豁免词」零门槛增删（基线不会被清空）。
META_WORDS = CFG.words([
    "悬置", "measured", "declared", "grounded",
    "红线守界", "红线守旧界", "未兑现", "钟仍在",
    "〔意义", "〔清楚的新状态", "〔设定级",
], add_key="记忆·额外禁词", drop_key="记忆·豁免词")
META_REGEX = [r"Q\d"]                    # Q6悬置 之类的问题编号
# ───────────────────────────────────────────────────────────────────────


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def resolve_targets(arg):
    if arg in (None, "", "all", "latest"):
        return sorted(glob.glob(str(CHRDIR / "chr-*.md")))
    if str(arg).endswith(".md"):
        p = Path(arg)
        return [str(p if p.is_absolute() else VAULT / arg)]
    cand = CHRDIR / f"chr-{arg}.md"
    if cand.exists():
        return [str(cand)]
    return [str(CHRDIR / f"{arg}.md")]


def count_zi(text):
    """净字数：剥指针尾 / wikilink / 行首列表记号 / 行首时间戳 / md 记号 / 空白。"""
    t = text.split("←")[0]                       # 指针尾不算字
    t = re.sub(r"\[\[[^\]]*\]\]", "", t)          # wikilink 是指针不是散文
    t = re.sub(r"(?m)^\s*[-*]+\s*", "", t)        # 每行行首列表记号
    t = re.sub(r"^\s*\[[^\]]*\]\s*", "", t)       # 条目行首 [第N天…] 时间戳
    t = re.sub(r"[*`>#\[\]]", "", t)              # 残余 md 记号
    t = re.sub(r"\s+", "", t)                     # 空白
    return len(t)


def h2_range(lines, contains):
    """返回 (heading_idx, end_idx_exclusive)；end 为下一个 `## ` 或 EOF。找不到返回 None。"""
    start = None
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith("## ") and not s.startswith("### ") and contains in s:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("## ") and not s.startswith("### "):
            end = j
            break
    return (start, end)


def h3_subs(lines, start, end):
    """重要记忆段内的 `### ` 子段列表 + lead 区间。"""
    subs, cur = [], None
    first_h3 = end
    for i in range(start + 1, end):
        s = lines[i].strip()
        if s.startswith("### "):
            if first_h3 == end:
                first_h3 = i
            if cur:
                cur["end"] = i
                subs.append(cur)
            cur = {"title": s[4:].strip(), "head": i, "start": i + 1, "end": end}
    if cur:
        subs.append(cur)
    lead = (start + 1, first_h3)
    return subs, lead


def entries(lines, cstart, cend):
    """把 [cstart,cend) 内的顶层 `- ` 条目分块（缩进续行/子条目折进本条）。"""
    out, cur = [], None
    for i in range(cstart, cend):
        l = lines[i]
        if re.match(r"^-\s", l):
            if cur:
                out.append(cur)
            cur = {"no": i + 1, "lines": [l]}
        elif cur is not None:
            if l.strip() == "":
                out.append(cur)
                cur = None
            elif re.match(r"^\s+\S", l):
                cur["lines"].append(l)
            else:
                out.append(cur)
                cur = None
    if cur:
        out.append(cur)
    return out


def snip(s):
    s = s.strip()
    return s if len(s) <= 64 else s[:62] + "…"


def lint_text(text):
    lines = text.split("\n")
    issues = []

    def scan_meta(lo, hi):
        """[lo,hi) 范围内逐行查引擎元词（ERROR）；跳过空行/标题/`>` 结算注释行。"""
        for idx in range(lo, hi):
            ln = lines[idx]
            s = ln.strip()
            if not s or s.startswith("#") or s.startswith(">"):
                continue
            hit = next((w for w in META_WORDS if w in ln), None)
            if not hit:
                for rx in META_REGEX:
                    if re.search(rx, ln):
                        hit = rx
                        break
            if hit:
                issues.append((idx + 1, "ERROR", "META",
                               f"记忆正文出现引擎元词「{hit}」——记忆给人读不是台账，用角色的感受/动作写（同日志铁律 #2）",
                               snip(ln)))

    # ── 重要记忆 ──
    zr = h2_range(lines, "重要记忆")
    if zr is None:
        issues.append((1, "WARN", "NO_ZHONG", "找不到「## 重要记忆」段（结构未对齐，闸无从查）", ""))
    else:
        z_start, z_end = zr
        scan_meta(z_start + 1, z_end)                # 反元词·覆盖重要记忆全段
        subs, (lead_s, lead_e) = h3_subs(lines, z_start, z_end)
        titles = [s["title"] for s in subs]

        # 总量（WARN）
        total = count_zi("\n".join(lines[z_start + 1:z_end]))
        if total > ZHONG_TOTAL_WARN:
            issues.append((z_start + 1, "WARN", "ZHONG_TOTAL",
                           f"重要记忆全段 {total} 字 > {ZHONG_TOTAL_WARN}——多半是关键事件随史增长，"
                           f"该考虑把久远锚点压紧或后续走归档（仿动态事实）", snip(lines[z_start])))

        # 三子段结构对齐（缺＝WARN）
        def has(kw):
            return any(kw in t for t in titles)
        for kw, label in (("关键事件", "关键事件·节点"), ("关系变化", "关系变化"), ("心境", "心境·态度演变（弧线）")):
            if not has(kw) and not (kw == "心境" and has("弧线")):
                issues.append((z_start + 1, "WARN", "NO_SUB",
                               f"重要记忆缺子段「{label}」（结构未对齐·态度项可能混在别段里）", ""))

        # 逐子段字数 / 段数闸
        for s in subs:
            t = s["title"]
            es = entries(lines, s["start"], s["end"])
            if "关键事件" in t:
                for e in es:
                    n = count_zi("\n".join(e["lines"]))
                    if n > KEY_EVENT_ZI_MAX:
                        issues.append((e["no"], "ERROR", "KE_LONG",
                                       f"关键事件·节点单条 {n} 字 > {KEY_EVENT_ZI_MAX}——压成史实锚点，"
                                       f"过程细节归 日志/evt/big（回链）", snip(e["lines"][0])))
            elif "关系变化" in t:
                if len(es) > REL_COUNT_MAX:
                    issues.append((s["head"] + 1, "ERROR", "REL_MANY",
                                   f"关系变化 {len(es)} 段 > {REL_COUNT_MAX}——覆写式应一对关系一段，"
                                   f"多半是在按天 append；合并到每对关系一段当前态", snip(lines[s["head"]])))
                for e in es:
                    n = count_zi("\n".join(e["lines"]))
                    if n > REL_ZI_MAX:
                        issues.append((e["no"], "ERROR", "REL_LONG",
                                       f"关系变化单段 {n} 字 > {REL_ZI_MAX}——改写成当前关系态，别堆过程",
                                       snip(e["lines"][0])))
            elif "心境" in t or "弧线" in t:
                if len(es) > ARC_COUNT_MAX:
                    issues.append((s["head"] + 1, "ERROR", "ARC_MANY",
                                   f"心境·弧线 {len(es)} 条 > {ARC_COUNT_MAX}——覆写式应一条弧一段，"
                                   f"按天摞 beat 就会超；合并同弧、改写当前态", snip(lines[s["head"]])))
                for e in es:
                    n = count_zi("\n".join(e["lines"]))
                    if n > ARC_ZI_MAX:
                        issues.append((e["no"], "ERROR", "ARC_LONG",
                                       f"心境·弧线单条 {n} 字 > {ARC_ZI_MAX}——一条常驻线+两三个 pivot，别写成小作文",
                                       snip(e["lines"][0])))

    # ── 短期记忆：每条字数 ERROR / 条数 WARN ──
    # 闸只在日结跑（CLAUDE.md §4.7·3，C·精简短期之后）；那时短期该已压成「要点+指针」，
    # 故字数可上 ERROR——报红＝这次日结没把某条压到位，正是要抓的。条数仍按 §4.7 软性走 WARN。
    sr = h2_range(lines, "短期记忆")
    if sr is not None:
        s_start, s_end = sr
        scan_meta(s_start + 1, s_end)                # 反元词·覆盖短期记忆全段
        es = entries(lines, s_start + 1, s_end)
        es = [e for e in es if not e["lines"][0].strip().startswith("- >")]  # 跳过开头说明性引述行
        if len(es) > SHORT_COUNT_WARN:
            issues.append((s_start + 1, "WARN", "SHORT_MANY",
                           f"短期记忆 {len(es)} 条 > {SHORT_COUNT_WARN}（日结前尖峰正常；日结时按滚动窗口压）",
                           snip(lines[s_start])))
        for e in es:
            n = count_zi("\n".join(e["lines"]))
            if n > SHORT_ZI_MAX:
                issues.append((e["no"], "ERROR", "SHORT_LONG",
                               f"短期记忆单条 {n} 字 > {SHORT_ZI_MAX}——压成「要点+指针」，过程交日志",
                               snip(e["lines"][0])))

    return issues


def lint_file(path):
    text = read(path)
    if not text:
        return path, None
    return path, lint_text(text)


def check_paths(targets, emit=print):
    tot_e = tot_w = 0
    for p in targets:
        name = Path(p).name
        _, issues = lint_file(p)
        if issues is None:
            emit(f"[记忆闸] ⚠️ 找不到或读不出：{p}")
            continue
        errs = [i for i in issues if i[1] == "ERROR"]
        warns = [i for i in issues if i[1] == "WARN"]
        tot_e += len(errs)
        tot_w += len(warns)
        if not issues:
            emit(f"[记忆闸] ✅ {name} 重要记忆守住覆写式 + 字数闸")
            continue
        emit(f"[记忆闸] {'❌' if errs else '⚠️'} {name}：{len(errs)} ERROR / {len(warns)} WARN")
        for no, sev, code, msg, sp in sorted(issues):
            mark = "❌" if sev == "ERROR" else "⚠️"
            emit(f"        {mark} L{no} [{code}] {msg}")
            if sp:
                emit(f"            ↳ {sp}")
    if tot_e:
        emit(f"[记忆闸] 红：{tot_e} 处 ERROR——回去**合并/改写**到绿（史实不删、长期不删），再写 _state。"
             f"纪律见 01-角色/_说明.md §重要记忆·覆写式纪律。")
    elif tot_w:
        emit(f"[记忆闸] 绿（有 {tot_w} 处 WARN，日结时顺手收，不阻断）。")
    return tot_e, tot_w


def main(argv):
    arg = argv[1] if len(argv) > 1 else None
    targets = resolve_targets(arg)
    if not targets:
        print("[记忆闸] 没有 chr-*.md 可查。")
        return 0
    err, _warn = check_paths(targets)
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
