#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
故事岛 · 调参读取器（_config.py）
================================================
零依赖（纯 python3 标准库）。被 lint_*.py 在启动时 import，
读同目录的 `调参面板.md`，把用户在 Obsidian 里写的值覆盖到脚本内默认。

★ 铁律：任何异常一律静默回退到脚本内默认值。
   配置文件缺失 / 写错 / 删空 / 填了乱七八糟的东西——都**绝不**让脚本报错或卡住，
   只是「当那一行不存在」、用脚本里写死的默认值。这样无人值守的夜间推进永远不会因为
   用户改坏一个数字而停摆。canonical 用法说明见 `08-脚本/_说明.md` §调参面板。

调参面板.md 的格式（人写的，怎么宽松怎么来）：
    一行一个 `中文键：值`（中文冒号或英文冒号都认）。
    `#` `>` `-` `|` 开头的行（标题/引用/列表/表格）一律忽略，可随便写注释。
    数字键：值里抓第一个整数（"200"、"200 字"、"约 200" 都认）；超出安全范围则忽略、用默认。
    词表键：值用 逗号/顿号/空格 分隔多个词。

本模块对外只有两个函数：num() 取数字、words() 取词表。两者都内置 try/except 兜底。
"""

import re
from pathlib import Path

_CONFIG_MD = Path(__file__).resolve().parent / "调参面板.md"


def _load_raw():
    """把调参面板.md 解析成 {中文键: 字符串值}。读不到/解析不了 → 空 dict（用默认）。"""
    try:
        text = _CONFIG_MD.read_text(encoding="utf-8")
    except Exception:
        return {}
    out = {}
    try:
        for line in text.split("\n"):
            s = line.strip()
            if not s or s[0] in "#>-|*`":      # 跳过 markdown 标题/引用/列表/表格/代码
                continue
            m = re.match(r"^([^:：]+)[:：](.*)$", s)
            if not m:
                continue
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key:
                out[key] = val
    except Exception:
        return {}
    return out


# 解析一次、全程复用。模块导入即读盘；出任何错就是空表（全用默认）。
try:
    _CFG = _load_raw()
except Exception:
    _CFG = {}


def num(key, default, lo=None, hi=None):
    """取整数配置。缺失/空/非数字/超出 [lo,hi] → 返回 default（绝不抛异常）。"""
    try:
        raw = _CFG.get(key, "")
        if not raw or not str(raw).strip():
            return default
        m = re.search(r"-?\d+", str(raw))
        if not m:
            return default
        val = int(m.group(0))
        if lo is not None and val < lo:
            return default
        if hi is not None and val > hi:
            return default
        return val
    except Exception:
        return default


def _split_words(raw):
    try:
        parts = re.split(r"[,，、;；\s]+", str(raw).strip())
        return [p for p in parts if p]
    except Exception:
        return []


def words(defaults, add_key=None, drop_key=None):
    """在 defaults 词表上：先按 drop_key 删词、再按 add_key 增词。出错 → 原样返回 defaults。

    设计：默认词表（脚本内）是权威基线；配置只做「增 / 删」两个安全动作，
    用户改坏也只是回退到这份基线，不会把闸的词表整张清空。
    """
    try:
        out = list(defaults)
        if drop_key:
            for w in _split_words(_CFG.get(drop_key, "")):
                while w in out:
                    out.remove(w)
        if add_key:
            for w in _split_words(_CFG.get(add_key, "")):
                if w and w not in out:
                    out.append(w)
        return out
    except Exception:
        return list(defaults)
