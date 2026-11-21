"""共用条目对齐检查（protocol.md 流程纪律第 5 条：跨书统一说法用脚本对齐）。

从五份质量标准里抽出共用条目，列出每份标准对同一事项写的数值 / 口径和条目编号，
输出不一致处。规则：
  1. 每个事项只有一个"持有方"写阈值；其他标准只引用持有方编号。
     非持有方的行里出现该事项的阈值写法（forbidden）→ 不一致。
  2. 持有方的条目里必须出现裁决值（expect），不得残留旧值（stale）→ 否则不一致。
  3. 任何一份里该事项仍写"待统一 / 冲突 / 待建" → 不一致。
  4. 非持有方提到该事项、又没写持有方编号的行（need_ref）→ 不一致。

跳过：修订记录、附录 A（旧节号映射）、参考来源；以及句子里写"作废 / 已撤 / v1 的"的历史说明分句。

用法：python align_check.py [standards 目录]   （默认取本脚本上一级目录）
退出码 = 不一致处数（0 即对齐）。
"""
import os
import re
import sys

FILES = {
    "视觉": "视觉设计.md",
    "镜头": "镜头与叙事.md",
    "声音": "声音.md",
    "需求": "需求理解.md",
    "动效": "动效.md",
}

SKIP_HEAD = re.compile(r"修订记录|附录 A|参考来源")
HIST = re.compile(r"作废|已撤|v1 的|v1 只|原 t_找|原为|改前")
ID_RE = re.compile(r"(?:镜 |声 |需 |动效 |视觉 )?(?:[BTSM]-\d+[A-Z]?|D\d+)")

# 事项定义 -------------------------------------------------------------------
# holder: (文件键, 持有条目的标题正则)   block 取到下一个同级条目为止
# key: 判定"这一行在说这件事"的正则
# forbidden: 非持有方行里不得出现的阈值写法
# allow: 该行命中 allow 时不计（别的事项，恰好用到同样的数字）
# expect / stale: 持有方条目里必须有 / 不得有
# need_ref: 非持有方行命中 key 且是表格行或条目行时，必须出现的持有方编号写法
ITEMS = [
    dict(
        name="须读字高",
        holder=("视觉", r"^\*\*B-01 "),
        key=r"字高|到达视角|必读细节|最小必读高度",
        forbidden=r"\b(?:22|24|27|34|36|48)\s*px|H/40|0\.5°|0\.033S|短边 2\.5%|1\.13%|3 mm",
        allow=r"钩子|封面|ε|h = 36|镜 B-11|两轮评审",
        expect=[r"< ?36 px", r"36–48 px", r"48 px", r"偏小", r"观看距离", r"tan"],
        stale=[r"≥ 36 px（动态）"],
        need_ref=r"视觉 B-01|B-01",
    ),
    dict(
        name="侧边距",
        holder=("视觉", r"^\*\*B-06 "),
        key=r"侧边|左右(?:安全)?距离|离左右边|左右物理边|左右边",
        forbidden=r"0\.065S|W/15|4\.5 mm|\b70 px|\b72 px|每边 5%|1/15",
        allow=r"钩子|镜 B-11",
        expect=[r"W/15", r"72 px"],
        stale=[r"0\.065S", r"70 px"],
        need_ref=r"视觉 B-06",
    ),
    dict(
        name="读速与停留",
        holder=("视觉", r"^\*\*B-15 "),
        key=r"停留|读速|字/秒|字/s",
        forbidden=r"3\.5|t_找|字/秒|÷ ?4–6|0\.5 s \+",
        allow=r"r₀|6\.5 字/s|τ_f|R 公式|一位 ?(?:按 ?)?9 字/秒|设计静止",
        expect=[r"0\.5 s \+ n ÷ 3\.5", r"待实验"],
        stale=[r"t_找 = 0\.2", r"取更长者", r"取最长"],
        need_ref=r"视觉 B-15",
    ),
    dict(
        name="对比度",
        holder=("视觉", r"^\*\*B-03 "),
        key=r"对比度|大号字",
        forbidden=r"4\.5:1|\b3:1|CSS px|18\.7",
        allow=r"x$",
        expect=[r"4\.5:1", r"3:1", r"CSS px"],
        stale=[],
        need_ref=r"视觉 B-03",
    ),
    dict(
        name="闪烁",
        holder=("视觉", r"^\*\*B-17 "),
        key=r"闪烁|红闪",
        forbidden=r"> ?3 次|0\.006|25%|341×256|347|369 px|0\.10，|≥ 0\.8|> 0\.2",
        allow=r"x$",
        expect=[r"0\.006", r"341×256", r"0\.2", r"R/\(R ?\+ ?G ?\+ ?B\)", r"观看距离"],
        stale=[],
        need_ref=r"视觉 B-17",
    ),
    dict(
        name="遮挡与重叠",
        holder=("视觉", r"^\*\*B-07 "),
        key=r"遮挡与重叠|静止遮挡",
        forbidden=r"重叠面积为 0（底线）",
        allow=r"x$",
        expect=[r"B-01、B-03"],
        stale=[],
        need_ref=r"视觉 B-07",
    ),
    dict(
        name="被裁",
        holder=("视觉", r"^\*\*B-05 "),
        key=r"被裁与溢出|静止裁切|静止状态下的裁切",
        forbidden=r"W·\(1 −",
        allow=r"x$",
        expect=[r"W·\(1 −"],
        stale=[],
        need_ref=r"视觉 B-05",
    ),
    dict(
        name="空白占位",
        holder=("视觉", r"^\*\*B-08 "),
        key=r"占位与半成品|空白占位",
        forbidden=r"Lorem",
        allow=r"x$",
        expect=[r"内部稿", r"作品论点"],
        stale=[],
        need_ref=r"视觉 B-08",
    ),
    dict(
        name="样稿内容口径",
        holder=("视觉", r"^## 5\. 样稿内容口径"),
        key=r"样稿内容口径",
        forbidden=r"x^",
        allow=r"x$",
        expect=[r"事实不编", r"不算编造", r"留空"],
        stale=[],
        need_ref=r"视觉(?:标准)? ?(?:第 ?5 节|§5)",
        sec_check=True,
    ),
    dict(
        name="决定类口径",
        holder=("需求", r"^\*\*需 B-06 "),
        key=r"决定类",
        forbidden=r"价格、时间、地点",
        allow=r"x$",
        expect=[r"白跑一趟", r"价格、时间、地点、报名或预约方式、联系方式、优惠条件、上线日期"],
        stale=[],
        need_ref=r"需 B-06|需求理解(?:标准)? ?B-06",
    ),
    dict(
        name="声画同步",
        holder=("声音", r"^\*\*声 B-07 "),
        key=r"声画同步|可见发声|声音领先",
        forbidden=r"45 ms|125 ms|1\.35 帧",
        allow=r"x$",
        expect=[r"45 ms", r"125 ms", r"BT\.1359", r"L = max"],
        stale=[],
        need_ref=r"声 B-07",
    ),
    dict(
        name="平台响度与真峰值",
        holder=("声音", r"^\| 声 T-01 "),
        key=r"响度|真峰值|dBTP|LUFS",
        forbidden=r"LUFS|-?−?\d+ dBTP|> ?1 LU|1 LU 待实验",
        allow=r"相邻段落|段落差|4 LU|6 LU|M-0|交付响度（实测日期）",
        expect=[r"平台实测", r"不写具体数"],
        stale=[],
        need_ref=r"声 T-0[12]",
    ),
    dict(
        name="第二层默认登记表位置",
        holder=(None, None),
        key=r"第二层默认登记表|登记表",
        forbidden=r"待建|建议位置",
        allow=r"示例替换表|替换表",
        expect=[],
        stale=[],
        need_ref=r"standards/第二层默认登记表\.md|第二层默认登记表",
    ),
]

OPEN_ISSUE = re.compile(r"待统一|\*\*冲突\*\*|仍有分歧|不裁决")


def load(root):
    docs = {}
    for k, fn in FILES.items():
        with open(os.path.join(root, fn), encoding="utf-8") as f:
            docs[k] = f.read().split("\n")
    return docs


def live_lines(lines):
    """逐行给出 (行号, 去掉历史分句后的文本, 当前条目编号)，跳过不检查的节。"""
    skip = False
    cur = ""
    for i, ln in enumerate(lines, 1):
        if ln.startswith("#"):
            skip = bool(SKIP_HEAD.search(ln))
            m = ID_RE.search(ln)
            cur = m.group(0) if m else ln.strip("# ").split(" ")[0]
            continue
        if skip:
            continue
        if ln.startswith("**"):
            m = ID_RE.search(ln[:20])
            if m:
                cur = m.group(0)
        parts = re.split(r"(?<=[。；])", ln)
        txt = "".join(p for p in parts if not HIST.search(p))
        rid = cur
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            m = ID_RE.fullmatch(cells[0]) if cells else None
            if m:
                rid = cells[0]
        yield i, txt, rid


def holder_block(lines, pat):
    """持有条目的文本块：表格行取一行；粗体条目取到下一个粗体条目或标题；节标题取到下一个同级标题。"""
    rx = re.compile(pat)
    for i, ln in enumerate(lines):
        if not rx.search(ln):
            continue
        if ln.startswith("|"):
            return ln, i + 1
        out = [ln]
        for ln2 in lines[i + 1:]:
            if ln.startswith("## "):
                if ln2.startswith("## ") or ln2.startswith("# "):
                    break
            else:
                if ln2.startswith("#") or (ln2.startswith("**") and ID_RE.search(ln2[:20])):
                    break
            out.append(ln2)
        return chr(10).join(out), i + 1
    return None, None


def first_value(txt, forbidden):
    return ", ".join(sorted(set(m.group(0) for m in re.finditer(forbidden, txt))))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs = load(root)
    issues = []
    print("# 共用条目对齐检查\n")
    for it in ITEMS:
        hk, hpat = it["holder"]
        print(f"## {it['name']}  （持有方：{hk + ' ' + hpat.strip('^*|\\ ') if hk else '登记表文件'}）")
        # 持有方
        if hk:
            blk, ln = holder_block(docs[hk], hpat)
            if blk is None:
                issues.append((it["name"], hk, "-", "持有条目不存在"))
                print(f"- [持有方] {hk}：找不到持有条目")
            else:
                live = "".join(p for p in re.split(r"(?<=[。；）])", blk) if not HIST.search(p))
                miss = [e for e in it["expect"] if not re.search(e, blk)]
                left = [s for s in it["stale"] if re.search(s, live)]
                vals = first_value(blk, it["forbidden"]) if it["forbidden"] != "x^" else ""
                print(f"- [持有方] {hk} 第 {ln} 行：{vals or '（口径条）'}")
                for e in miss:
                    issues.append((it["name"], hk, ln, f"持有条目缺裁决值 /{e}/"))
                for s in left:
                    issues.append((it["name"], hk, ln, f"持有条目残留旧值 /{s}/"))
        else:
            p = os.path.join(root, "第二层默认登记表.md")
            ok = os.path.exists(p)
            print(f"- [持有方] standards/第二层默认登记表.md：{'存在' if ok else '不存在'}")
            if not ok:
                issues.append((it["name"], "-", "-", "登记表文件不存在"))
        # 各标准
        key = re.compile(it["key"])
        forb = re.compile(it["forbidden"])
        allow = re.compile(it["allow"])
        need = re.compile(it["need_ref"])
        for fk, lines in docs.items():
            hblk_lines = set()
            if hk == fk:
                blk, ln = holder_block(lines, hpat)
                if blk:
                    hblk_lines = set(range(ln, ln + blk.count("\n") + 1))
            for i, txt, rid in live_lines(lines):
                if not key.search(txt):
                    continue
                if i in hblk_lines:
                    continue
                if OPEN_ISSUE.search(txt):
                    issues.append((it["name"], fk, i, f"仍写待统一/冲突（{rid}）"))
                    print(f"- {fk} {rid} 第 {i} 行：仍写待统一/冲突")
                    continue
                if allow.search(txt):
                    continue
                if hk is None or fk != hk:
                    if forb.search(txt):
                        v = first_value(txt, it["forbidden"])
                        issues.append((it["name"], fk, i, f"非持有方写了阈值 {v}（{rid}）"))
                        print(f"- {fk} {rid} 第 {i} 行：写了 {v}")
                        continue
                    if (txt.startswith("|") or txt.startswith("**") or txt.startswith("- 阈值")) and not need.search(txt) and hk is not None:
                        # 只查 S 表 / 对应表 / 条目行；持有方自己的其他行不查
                        if re.search(r"^\| *(?:[镜声需] )?S-\d+|^\| *(?:事项|[^|]*\|)", txt) and re.search(it["key"], txt.split("|")[1] if txt.startswith("|") and txt.count("|") > 2 else txt):
                            issues.append((it["name"], fk, i, f"提到本事项但没写持有方编号（{rid}）"))
                            print(f"- {fk} {rid} 第 {i} 行：未引用持有方")
                            continue
                    print(f"- {fk} {rid} 第 {i} 行：引用 / 提及")
        if it.get("sec_check"):
            for fk, lines in docs.items():
                if fk == hk:
                    continue
                blk, ln = holder_block(lines, r"^## 5\. 样稿内容口径")
                if blk and not need.search(blk):
                    issues.append((it["name"], fk, ln, "第 5 节没有写明引用视觉标准第 5 节"))
                if blk and re.search(r"价格、时间、地点", blk):
                    issues.append((it["name"], fk, ln, "第 5 节自写决定类清单（应引用需 B-06）"))
        print()
    print(f"# 不一致处：{len(issues)}\n")
    for n, f, ln, msg in issues:
        print(f"- [{n}] {f} 第 {ln} 行：{msg}")
    return len(issues)


if __name__ == "__main__":
    sys.exit(min(main(), 255))
