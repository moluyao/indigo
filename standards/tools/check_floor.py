"""底线自动检查 v1（动效标准 v1 第 6 节）。

两层输出：
  delivery  交付技术层 T-xx：色彩元数据、响度、真峰值、帧率、流对齐、编码封装、时长/画幅规格。
            导出时可机械修复；不达标记"交付未过"，附 ffmpeg 修复命令，不把作品判为 L0。
  audience  观众可感层 B-xx：开头窗口、死时间、片尾停帧、卡顿、坏帧、黑闪、闪烁、削波……
            未过才判 L0。脚本能自动判的给 pass/fail/warn，其余标 manual 并写明所需材料。

用法:
  python check_floor.py in.mp4 [--card card.json] [--target-dur 秒] [--platform web|broadcast] [--out result.json]
card.json（评审卡，可选）字段：target_level, target_dur, platform, form, aspect, core_message, read_text
只依赖 ffmpeg/ffprobe + numpy。
"""
import argparse
import json
import os
import re
import struct
import subprocess

import numpy as np

FF = "ffmpeg"
FP = "ffprobe"
NUM = "(-?[0-9.]+)"
SP = "[ ]*"
VERSION = "craft-lib/standards/动效.md v1"


# ---------------------------------------------------------------- 基础工具
def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.stdout, p.stderr.decode("utf-8", "replace")


def probe(path):
    out, _ = run([FP, "-v", "error", "-show_entries",
                  "format=duration,format_name:stream=codec_type,codec_name,pix_fmt,width,height,"
                  "r_frame_rate,avg_frame_rate,start_time,duration,nb_frames,color_space,color_primaries,"
                  "color_transfer,color_range,sample_rate,channels", "-of", "json", path])
    return json.loads(out)


def frac(s):
    try:
        a, b = s.split("/")
        return float(a) / float(b) if float(b) else 0.0
    except Exception:
        return 0.0


def flog(path, vf=None, af=None):
    cmd = [FF, "-hide_banner", "-nostats", "-i", path]
    cmd += ["-vf", vf, "-an"] if vf else ["-af", af, "-vn"]
    cmd += ["-f", "null", "-"]
    return run(cmd)[1]


def intervals(err, key, total):
    if key == "black":
        return [(float(a), float(b)) for a, b in
                re.findall("black_start:" + NUM + SP + "black_end:" + NUM, err)]
    starts = [float(x) for x in re.findall(key + "_start:" + SP + NUM, err)]
    ends = [float(x) for x in re.findall(key + "_end:" + SP + NUM, err)]
    while len(ends) < len(starts):
        ends.append(total)
    return list(zip(starts, ends))


def overlap(a, b):
    res = []
    for s1, e1 in a:
        for s2, e2 in b:
            s, e = max(s1, s2), min(e1, e2)
            if e > s:
                res.append((round(s, 3), round(e, 3)))
    return res


def item(status, value=None, note="", **kw):
    d = {"status": status}
    if value is not None:
        d["value"] = value
    if note:
        d["note"] = note
    d.update(kw)
    return d


def q(p):
    return '"%s"' % p


def top_atoms(path, limit=64):
    """MP4 顶层 box 顺序，用于判断 faststart（moov 在 mdat 前）。"""
    order = []
    try:
        size_total = os.path.getsize(path)
        with open(path, "rb") as f:
            pos = 0
            while pos < size_total and len(order) < limit:
                f.seek(pos)
                h = f.read(8)
                if len(h) < 8:
                    break
                sz, typ = struct.unpack(">I4s", h)
                if sz == 1:
                    sz = struct.unpack(">Q", f.read(8))[0]
                elif sz == 0:
                    sz = size_total - pos
                order.append(typ.decode("latin-1"))
                if sz < 8:
                    break
                pos += sz
    except Exception:
        pass
    return order


# ---------------------------------------------------------------- 画面
def srgb_lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def video_frames(path, w, h):
    cmd = [FF, "-v", "error", "-i", path, "-vf", "scale=%d:%d:flags=area" % (w, h),
           "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    out, _ = run(cmd)
    arr = np.frombuffer(out, np.uint8)
    n = arr.size // (w * h * 3)
    return arr[: n * w * h * 3].reshape(n, h, w, 3)


def zigzag(seq, thr):
    ext = [(0, seq[0])]
    d = 0
    for i in range(1, len(seq)):
        v = seq[i]
        li, lv = ext[-1]
        if d == 0:
            if abs(v - lv) >= thr:
                d = 1 if v > lv else -1
                ext.append((i, v))
        elif d == 1:
            if v >= lv:
                ext[-1] = (i, v)
            elif lv - v >= thr:
                d = -1
                ext.append((i, v))
        else:
            if v <= lv:
                ext[-1] = (i, v)
            elif v - lv >= thr:
                d = 1
                ext.append((i, v))
    return ext


def flash_check(frames, fps, grid=6):
    """WCAG 2.3.1 近似：grid x grid 区块平均相对亮度 zigzag；幅度 >=0.1 且暗态 <0.8 计一次转变，
    两次转变 = 一次闪烁；1 s 滑窗 > 3 次未过。红闪：任一态 R/(R+G+B) >= 0.8。"""
    n, h, w, _ = frames.shape
    bh, bw = h // grid, w // grid
    win = int(round(fps))
    worst = {"general_max_per_s": 0.0, "red_max_per_s": 0.0, "t_general": None, "t_red": None}
    for gy in range(grid):
        for gx in range(grid):
            blk = frames[:, gy * bh:(gy + 1) * bh, gx * bw:(gx + 1) * bw, :].astype(np.float32)
            rgb = blk.reshape(n, -1, 3).mean(axis=1)
            lin = srgb_lin(rgb)
            L = 0.2126 * lin[:, 0] + 0.7152 * lin[:, 1] + 0.0722 * lin[:, 2]
            redr = rgb[:, 0] / np.maximum(rgb.sum(axis=1), 1e-6)
            ext = zigzag(L, 0.1)
            gen_t, red_t = [], []
            for k in range(1, len(ext)):
                (i0, v0), (i1, v1) = ext[k - 1], ext[k]
                if min(v0, v1) < 0.8:
                    gen_t.append(i1)
                    if redr[i0] >= 0.8 or redr[i1] >= 0.8:
                        red_t.append(i1)
            for key, tl, tk in (("general_max_per_s", gen_t, "t_general"), ("red_max_per_s", red_t, "t_red")):
                tl = np.array(tl)
                for s in tl:
                    cnt = int(((tl >= s) & (tl < s + win)).sum()) / 2.0
                    if cnt > worst[key]:
                        worst[key] = cnt
                        worst[tk] = round(s / fps, 2)
    return worst


def frame_diffs(frames):
    y = (0.299 * frames[..., 0] + 0.587 * frames[..., 1] + 0.114 * frames[..., 2]).astype(np.float32)
    d1 = np.abs(np.diff(y, axis=0)).mean(axis=(1, 2))   # d1[i] = |y[i+1]-y[i]|
    d2 = np.abs(y[2:] - y[:-2]).mean(axis=(1, 2))       # d2[i] = |y[i+2]-y[i]|
    return y, d1, d2


# ---------------------------------------------------------------- 声音
def audio_samples(path, sr=48000, ch=2):
    out, _ = run([FF, "-v", "error", "-i", path, "-vn", "-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-"])
    x = np.frombuffer(out, np.float32)
    x = x[: x.size // ch * ch].reshape(-1, ch)
    return x, sr


def rms_db(x):
    return float(20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12))


def onsets(mono, sr, hop_s=0.01, jump_db=12.0, floor_db=-40.0):
    hop = int(hop_s * sr)
    n = mono.size // hop
    if n < 6:
        return []
    fr = mono[: n * hop].reshape(n, hop).astype(np.float64)
    e = 10 * np.log10((fr ** 2).mean(axis=1) + 1e-12)
    res = []
    for j in range(5, n):
        if e[j] > floor_db and e[j] - e[j - 5:j].max() >= jump_db:
            if not res or j * hop_s - res[-1] > 0.08:
                res.append(round(j * hop_s, 3))
    return res


def loudnorm_measure(path, I, TP, LRA):
    err = flog(path, af="loudnorm=I=%s:TP=%s:LRA=%s:print_format=json" % (I, TP, LRA))
    m = re.findall(r"\{[^{}]*\}", err, re.S)
    if not m:
        return None
    try:
        return json.loads(m[-1])
    except Exception:
        return None


# ---------------------------------------------------------------- 评审卡
def load_card(card_path, target_dur, platform):
    card = {}
    if card_path:
        with open(card_path, encoding="utf-8") as f:
            card = json.load(f)
        card["_source"] = "评审卡"
    else:
        card["_source"] = "无评审卡（目标时长/平台取命令行参数或默认）"
    if target_dur:
        card["target_dur"] = target_dur
    plat = str(card.get("platform", platform or "web"))
    card["_loud_target"] = -23.0 if plat.lower() in ("broadcast", "广播", "电视") else -14.0
    return card


# ---------------------------------------------------------------- 交付技术层
def delivery_layer(path, info, card, audio):
    T = {}
    dur = float(info["format"]["duration"])
    vs = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    aus = [s for s in info["streams"] if s["codec_type"] == "audio"]
    fps = frac(vs["r_frame_rate"])
    base, ext = os.path.splitext(path)
    out_path = base + "_fixed" + ext

    # T-01 色彩元数据（原 B-32）
    cm = {k: vs.get(k) for k in ("color_space", "color_primaries", "color_transfer", "color_range")}
    miss = [k for k, v in cm.items() if not v or v == "unknown"]
    bad = [k for k in ("color_space", "color_primaries", "color_transfer") if cm.get(k) and cm[k] not in ("bt709", "unknown")]
    T["T-01"] = item("fail" if (miss or bad) else "pass", cm,
                     ("缺失: %s " % miss if miss else "") + ("非 BT.709: %s" % bad if bad else ""),
                     was="B-32", auto_fix=True)

    # T-04 恒定帧率（原 B-07）
    vfr = vs["r_frame_rate"] != vs["avg_frame_rate"]
    T["T-04"] = item("fail" if vfr else "pass", [vs["r_frame_rate"], vs["avg_frame_rate"]], was="B-07", auto_fix=True)

    # T-06 编码与封装
    atoms = top_atoms(path)
    faststart = ("moov" in atoms and "mdat" in atoms and atoms.index("moov") < atoms.index("mdat"))
    enc = {"vcodec": vs.get("codec_name"), "pix_fmt": vs.get("pix_fmt"),
           "acodec": aus[0].get("codec_name") if aus else None,
           "sample_rate": aus[0].get("sample_rate") if aus else None,
           "faststart": faststart}
    enc_bad = []
    if enc["vcodec"] not in ("h264", "hevc"):
        enc_bad.append("视频编码非 H.264/HEVC")
    if enc["pix_fmt"] not in ("yuv420p",):
        enc_bad.append("像素格式非 yuv420p")
    if aus and enc["acodec"] != "aac":
        enc_bad.append("音频编码非 AAC")
    if aus and str(enc["sample_rate"]) not in ("44100", "48000"):
        enc_bad.append("采样率非 44.1/48 kHz")
    if not faststart:
        enc_bad.append("moov 不在文件头（未 faststart，网页/平台首播慢）")
    T["T-06"] = item("fail" if enc_bad else "pass", enc, "；".join(enc_bad), auto_fix=True)

    # T-05 音视频流对齐（原 B-21）
    if aus:
        a = aus[0]
        dv = abs(float(vs.get("start_time", 0)) - float(a.get("start_time", 0)))
        dd = abs(float(vs.get("duration", dur)) - float(a.get("duration", dur)))
        fr = 1.0 / fps
        ok = dv <= fr + 1e-6 and dd <= fr + 1e-6
        T["T-05"] = item("pass" if ok else "fail", {"start_diff_s": round(dv, 4), "dur_diff_s": round(dd, 4)},
                         "阈值 1 帧 = %.4f s" % fr, was="B-21", auto_fix=True)
    else:
        T["T-05"] = item("n/a", None, "无音轨", was="B-21")

    # T-02 / T-03 响度与真峰值（原 B-25 / B-26）
    ln = None
    tgt = card["_loud_target"]
    if aus:
        err = flog(path, af="ebur128=peak=true")
        summ = err[err.rfind("Summary:"):]
        I = re.search("I:" + SP + NUM + " LUFS", summ)
        TP = re.search("True peak:[^P]*Peak:" + SP + NUM, summ, re.S)
        LRA = re.search("LRA:" + SP + NUM + " LU", summ)
        I = float(I.group(1)) if I else None
        TP = float(TP.group(1)) if TP else None
        audio["I"], audio["TP"] = I, TP
        audio["LRA"] = float(LRA.group(1)) if LRA else None
        S = [float(x) for x in re.findall("S:" + SP + NUM + " ", err[: err.rfind("Summary:")])]
        S = np.array([s for s in S if s > -70])
        if S.size:
            audio["S_p10_p90"] = [round(float(np.percentile(S, 10)), 1), round(float(np.percentile(S, 90)), 1)]
        T["T-02"] = item("pass" if I is not None and tgt - 1 <= I <= tgt + 1 else "fail", I,
                         "目标 %.0f±1 LUFS（%s）" % (tgt, "广播 EBU R128" if tgt < -20 else "网络平台起点值"),
                         was="B-25", auto_fix=True)
        T["T-03"] = item("pass" if TP is not None and TP <= -1.0 else "fail", TP, "阈值 -1 dBTP",
                         was="B-26", auto_fix=True)
        if T["T-02"]["status"] == "fail" or T["T-03"]["status"] == "fail":
            gain = tgt - I if I is not None else 0.0
            if TP is not None and TP + gain <= -1.2:
                af = "volume=%+.1fdB" % gain
                how = "纯增益 %+.1f dB（增益后真峰值约 %.1f dBTP，不需限幅）" % (gain, TP + gain)
            else:
                ln = loudnorm_measure(path, tgt, -1.5, 11)
                if ln:
                    af = ("loudnorm=I=%.0f:TP=-1.5:LRA=11:measured_I=%s:measured_TP=%s:measured_LRA=%s:"
                          "measured_thresh=%s:offset=%s:linear=true" % (tgt, ln["input_i"], ln["input_tp"],
                                                                          ln["input_lra"], ln["input_thresh"],
                                                                          ln["target_offset"]))
                else:
                    af = "loudnorm=I=%.0f:TP=-1.5:LRA=11" % tgt
                how = "两遍 loudnorm（线性模式，已代入第一遍测量值）"
            audio["fix_af"] = af
            audio["fix_how"] = how
    else:
        T["T-02"] = item("n/a", None, "无音轨", was="B-25")
        T["T-03"] = item("n/a", None, "无音轨", was="B-26")

    # T-07 时长（原 B-01）
    td = card.get("target_dur")
    if td:
        T["T-07"] = item("pass" if dur <= float(td) else "fail", round(dur, 3), "目标 ≤ %.1f s" % float(td),
                         was="B-01", auto_fix=False)
    else:
        T["T-07"] = item("manual", round(dur, 3), "无评审卡目标时长，仅报实测", was="B-01", auto_fix=False)

    # T-08 画幅/分辨率与评审卡
    asp = card.get("aspect")
    real = "%dx%d" % (vs["width"], vs["height"])
    if asp:
        want = str(asp).replace("×", "x").replace(":", "x")
        try:
            a_, b_ = [float(v) for v in want.split("x")]
            ok = abs(a_ / b_ - vs["width"] / vs["height"]) < 0.01
        except Exception:
            ok = None
        T["T-08"] = item("pass" if ok else ("fail" if ok is False else "manual"), real, "评审卡画幅 %s" % asp,
                         auto_fix=False)
    else:
        T["T-08"] = item("manual", real, "无评审卡画幅，仅报实测", auto_fix=False)

    # 修复命令
    fixes = {}
    reenc_v = vfr or enc["vcodec"] not in ("h264", "hevc") or enc["pix_fmt"] != "yuv420p"
    color_bad = T["T-01"]["status"] == "fail"
    vpart, apart = [], []
    if reenc_v:
        vf = "fps=%s" % vs["r_frame_rate"] if vfr else None
        vpart = (["-vf", vf] if vf else []) + ["-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
                                                "-colorspace", "bt709", "-color_primaries", "bt709",
                                                "-color_trc", "bt709", "-color_range", "tv"]
    elif color_bad:
        bsf = "h264_metadata" if enc["vcodec"] == "h264" else "hevc_metadata"
        vpart = ["-c:v", "copy", "-bsf:v",
                 "%s=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0" % bsf]
    else:
        vpart = ["-c:v", "copy"]
    need_a = aus and ("fix_af" in audio or T["T-05"]["status"] == "fail" or
                      enc["acodec"] != "aac" or str(enc["sample_rate"]) not in ("44100", "48000"))
    if aus:
        if need_a:
            afs = []
            if T["T-05"]["status"] == "fail":
                afs.append("aresample=async=1:first_pts=0")
            if "fix_af" in audio:
                afs.append(audio["fix_af"])
            apart = (["-af", ",".join(afs)] if afs else []) + ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        else:
            apart = ["-c:a", "copy"]
    tail = (["-shortest"] if aus and T["T-05"]["status"] == "fail" else []) + ["-movflags", "+faststart"]

    def cmd(parts):
        out = [FF, "-i", q(path)] + parts + [q(out_path)]
        return " ".join(p if (p.startswith('"') or " " not in p) else q(p) for p in out)

    if color_bad:
        fixes["T-01"] = ("重编码时写入 BT.709 标签" if reenc_v else "无损改写码流色彩标签（不重编码）")
    if "fix_af" in audio:
        fixes["T-02/T-03"] = audio["fix_how"]
    if vfr:
        fixes["T-04"] = "重编码为恒定 %s fps" % vs["r_frame_rate"]
    if T["T-05"]["status"] == "fail":
        fixes["T-05"] = "音频重采样对齐起点 + -shortest 截齐"
    if enc_bad:
        fixes["T-06"] = "；".join(enc_bad) + " → 见合并命令（含 +faststart）"
    fails = [k for k, v in T.items() if v["status"] == "fail"]
    fix_all = cmd(vpart + apart + tail) if fails else None
    return {
        "status": "交付未过" if fails else "交付通过",
        "fails": fails,
        "auto_fixable": all(T[k].get("auto_fix") for k in fails) if fails else True,
        "not_auto_fixable": [k for k in fails if not T[k].get("auto_fix")],
        "fix_notes": fixes,
        "fix_all": fix_all,
        "fix_note": "合并为一条命令：视频能 copy 就 copy，响度两遍 loudnorm 已代入实测；修复后重跑本脚本复测。",
        "checks": T,
    }, dur, fps, vs, aus


# ---------------------------------------------------------------- 观众可感层
MANUAL = {
    "B-10": "边界穿帮：硬切取切点 ±10 帧；软转场取过渡区间的起/中/止三帧 + 最糊一帧（见 meta.boundaries）",
    "B-11": "三秒注视测试（独立评审看单帧）",
    "B-12": "联系表人工指主焦点",
    "B-13": "OCR + 人工校对错字/事实（须读与可略读文字都查）",
    "B-14": "停留够读（时序文字）：须读文字事件表，落定帧→退场开始帧 ≥ 字数÷9 字/s 且 ≥ 5/6 s",
    "B-14P": "读负荷（常驻文字/动态海报，标准 1.7）：首轮核心 ≤ 7 字/s×片长，总须读 ≤ 7 字/s×片长×2",
    "B-15": "字幕行长：需字幕文件",
    "B-16": "文字对比度（须读 ≥4.5:1 / 大字 ≥3:1；可略读 ≥3:1）：需文字 bbox",
    "B-17": "安全区 + 平台界面蒙版：需文字 bbox",
    "B-18": "最小字高（须读 ≥ 短边 2.5%，可略读 ≥ 1.8%）：需 OCR bbox",
    "B-20": "转场抢文字：依赖 B-14 事件表 × meta.boundaries",
    "B-22": "可见发声同步：人工找撞击/口型帧（需能听）",
    "B-23": "音效落点：冲击音效瞬态（meta.audio_onsets）vs 画面落点帧",
    "B-24": "内容错位：需 ASR 词级时间戳 × 画面事件",
    "B-27": "人声可懂：需 ASR + 配音稿（评审卡未给稿时用 ASR 置信度）",
    "B-28": "错读：人工听专名/数字/多音字（需能听）",
    "B-30": "底噪：耳机人工听（meta.noise_floor_p5_dBFS 供参考）",
    "B-33": "色带/糊块：100% 放大抽帧 + 手机实机",
    "B-34": "同类元素一致：联系表人工",
    "B-35": "混入低清素材：人工",
    "B-36": "复述测试：独立评审，对照评审卡核心信息",
    "B-37": "事实与图表：逐条核来源",
    "B-38": "有结论：人工",
    "B-39": "预警项说明：评审后打开制作者说明",
    "B-40": "静态遮挡/裁切：须读文字或主焦点被压、被画框裁切（可略读被压记预警）",
    "B-41": "过渡态可见不可读：文字先于衬底出现、半透明叠底等，统计持续帧数",
}


def audience_layer(path, delivery, dur, fps, aus, audio, card):
    R, meta = {}, {}
    vs_w, vs_h = None, None
    info_v = probe(path)
    v = [s for s in info_v["streams"] if s["codec_type"] == "video"][0]
    W, H = v["width"], v["height"]
    sw, sh = (96, 54) if W >= H else (54, 96)
    fr = video_frames(path, sw, sh)
    y, d1, d2 = frame_diffs(fr)
    n = len(fr)
    t = lambda i: round(i / fps, 3)

    blk_err = flog(path, vf="blackdetect=d=0.02:pix_th=0.10")
    blacks = intervals(blk_err, "black", dur)
    frz_err = flog(path, vf="freezedetect=n=0.003:d=0.5")
    freezes = intervals(frz_err, "freeze", dur)
    meta["black_intervals"] = blacks
    meta["freeze_intervals_0.5s"] = [(round(a, 2), round(b, 2)) for a, b in freezes]

    # B-02 开头窗口：首个"有内容"帧时刻
    std0 = float(y[0].std())
    first = None
    for i in range(n):
        if y[i].std() >= 4 or np.abs(y[i] - y[0]).mean() >= 2:
            first = i
            break
    tf = t(first) if first is not None else None
    meta["first_frame_luma_std"] = round(std0, 2)
    meta["t_first_content"] = tf
    if tf is None or tf > 1.0:
        R["B-02"] = item("fail", tf, "开头窗口：> 1.0 s 仍无内容（起点值）")
    elif tf > 0.5:
        R["B-02"] = item("warn", tf, "开头窗口：0.5–1.0 s 才出现内容，需人工判断是否有意")
    else:
        R["B-02"] = item("pass", tf, "开头窗口：首个有内容帧 %.2f s（≤0.5 s 通过，起点值）" % tf)

    f0 = [f for f in freezes if f[0] < 0.05 and f[1] - f[0] >= 1.0]
    R["B-03"] = item("fail" if f0 else "pass", f0 or None, "freezedetect n=0.003，从 0 开始 ≥1 s")

    # 切点（硬）与软边界
    cuts = []
    for i in range(len(d1)):
        nb = np.concatenate([d1[max(0, i - 3):i], d1[i + 1:i + 4]])
        if d1[i] > 12 and d1[i] > 3 * (np.median(nb) if nb.size else 0) + 1:
            cuts.append(i + 1)
    k = max(1, int(round(fps * 0.5)))
    dk = np.zeros(n)
    if n > k:
        dk[k:] = np.abs(y[k:] - y[:-k]).mean(axis=(1, 2))
    med = float(np.median(dk[k:])) if n > k else 0.0
    soft = []
    thr = max(6.0, 2.5 * med)
    i = k
    while i < n:
        if dk[i] >= thr and dk[i] == dk[max(k, i - k):min(n, i + k)].max():
            tc = t(i - k // 2)
            if all(abs(tc - t(c)) > 0.6 for c in cuts) and (not soft or tc - soft[-1]["t"] > 1.0):
                # 过渡区间：中心两侧帧差高于基线的连续帧
                base = max(0.3, 2 * float(np.median(d1)))
                a = b = i - k // 2
                while a > 0 and d1[a - 1] > base:
                    a -= 1
                while b < len(d1) - 1 and d1[b] > base:
                    b += 1
                soft.append({"t": tc, "start": t(a), "end": t(b + 1), "score": round(float(dk[i]), 1)})
            i += k
        else:
            i += 1
    meta["boundaries"] = [{"t": t(c), "type": "hard"} for c in cuts] + \
                         [dict(type="soft", **s) for s in soft]
    meta["boundaries"].sort(key=lambda b: b["t"])
    meta["cut_count_hard"] = len(cuts)
    meta["boundary_count_soft"] = len(soft)

    # 声音样本与瞬态（用于 B-09 冲击帧豁免、B-23）
    mono = None
    if aus:
        x, sr = audio_samples(path)
        mono = x.mean(axis=1)
        ons = onsets(mono, sr)
        meta["audio_onsets"] = ons[:80]
    else:
        ons = []

    # B-09 孤立突变帧，带冲击帧豁免口径
    glitches, impacts = [], []
    for i in range(1, n - 1):
        a_, b_, c_ = d1[i - 1], d1[i], d2[i - 1]
        if a_ > 6 and b_ > 6 and c_ < 0.35 * min(a_, b_):
            ti = t(i)
            near = [o for o in ons if abs(ti - o) <= 0.25]
            if near:
                o = min(near, key=lambda z: abs(ti - z))
                # 正值 = 声音先于画面；>45 ms 交给 B-23 人工听
                impacts.append({"t": ti, "onset": o, "audio_lead_ms": int(round((ti - o) * 1000))})
            else:
                glitches.append(ti)
    if glitches:
        R["B-09"] = item("warn", {"glitch": glitches[:30], "impact": impacts[:30]},
                         "孤立突变帧且无同步声音瞬态，需抽帧人工确认是否渲染瑕疵")
    elif impacts:
        R["B-09"] = item("pass", {"impact": impacts[:30]},
                         "突变帧 ±0.25 s 内有声音瞬态 → 冲击帧候选，按豁免口径记录（人工一眼确认是落点元素）；"
                         "audio_lead_ms 超出 +45/-125 ms 的转 B-23 人工听")
    else:
        R["B-09"] = item("pass")

    # B-08 运动中单帧冻结
    stutters = []
    for i in range(2, len(d1) - 1):
        if d1[i] < 0.02 and d1[i - 1] > 0.8 and d1[i + 1] > 0.8:
            stutters.append(t(i + 1))
    R["B-08"] = item("fail" if len(stutters) >= 2 else "pass", stutters[:30] or None,
                     "连续运动中单帧冻结 %d 次（>=2 未过）" % len(stutters))

    # B-19 边界附近黑闪（硬切与软边界都算）
    bts = [b["t"] for b in meta["boundaries"]]
    nearb = [bk for bk in blacks if any(abs(bk[0] - bt) < 0.5 or abs(bk[1] - bt) < 0.5 for bt in bts)
             and bk[0] > 0.05 and bk[1] < dur - 0.05]
    R["B-19"] = item("warn" if nearb else "pass", nearb or None, "边界附近有黑场，需确认是否有意" if nearb else "")

    # B-31 闪烁
    fl = flash_check(fr, fps)
    R["B-31"] = item("fail" if (fl["general_max_per_s"] > 3 or fl["red_max_per_s"] > 3) else "pass", fl,
                     "6x6 区块近似，超标需专用工具复核")

    # 预警统计
    per_s = [round(float(d1[int(s * fps):int((s + 1) * fps)].mean()), 2)
             for s in range(int(np.ceil(len(d1) / fps))) if d1[int(s * fps):int((s + 1) * fps)].size]
    arr = np.array(per_s)
    meta["warn_motion_energy_per_s"] = per_s
    meta["warn_motion_energy_cv"] = round(float(arr.std() / (arr.mean() + 1e-6)), 2)
    meta["warn_still_frame_ratio"] = round(float((d1 < 0.01).mean()), 3)
    meta["warn_avg_segment_s"] = round(dur / (len(meta["boundaries"]) + 1), 2)

    # 声音相关
    if aus:
        sil = intervals(flog(path, af="silencedetect=n=-50dB:d=0.5"), "silence", dur)
        meta["silence_intervals_-50dB_0.5s"] = [(round(a, 2), round(b, 2)) for a, b in sil]
        # B-05 片尾：黑∩静 > 0.5 未过；停帧∩静（任意底色）> 2.0 未过，0.5–2.0 预警
        tail_b = [o for o in overlap(blacks, sil) if o[1] >= dur - 0.1 and o[1] - o[0] > 0.5]
        tail_f = [o for o in overlap(freezes, sil) if o[1] >= dur - 0.1 and o[1] - o[0] > 0.5]
        lf = max([o[1] - o[0] for o in tail_f], default=0)
        if tail_b:
            R["B-05"] = item("fail", tail_b, "片尾黑场 ∩ 静音 > 0.5 s")
        elif lf > 2.0:
            R["B-05"] = item("fail", tail_f, "片尾停帧 ∩ 静音 > 2.0 s（非黑停帧，起点值）")
        elif lf > 0.5:
            R["B-05"] = item("warn", tail_f, "片尾停帧 ∩ 静音 %.2f s（0.5–2.0 s 预警；若末屏须读文字需要这段时间，记有意）" % lf)
        else:
            R["B-05"] = item("pass")
        # B-04 死时间：冻结 ∩ 静音（片尾除外）；绝对上限 3 s
        dead = [o for o in overlap(freezes, sil) if o[1] - o[0] >= 1.0 and o[1] < dur - 0.1]
        longf = [(round(a, 2), round(b, 2)) for a, b in freezes if b - a >= 3.0 and b < dur - 0.1]
        if any(o[1] - o[0] >= 3.0 for o in dead):
            R["B-04"] = item("fail", dead, "冻结 ∩ 静音 ≥ 3 s（绝对上限）")
        elif dead or longf:
            R["B-04"] = item("warn", {"freeze_and_silence": dead, "freeze_ge_3s": longf},
                             "候选；正式判定需 ASR（冻结 ∩ 无新词 > max(2×平均事件间隔) 或 > 3 s）")
        else:
            R["B-04"] = item("manual", None, "无冻结∩静音 ≥1 s；冻结 ≥3 s 也无。正式判定仍需 ASR 事件表")
        # B-06 音乐硬断
        last = mono[-int(0.05 * sr):]
        prev = mono[-int(1.05 * sr):-int(0.05 * sr)]
        e_last, e_prev = rms_db(last), rms_db(prev)
        hard = e_last > -35 and e_last > e_prev - 6
        R["B-06"] = item("warn" if hard else "pass", {"last50ms_dB": round(e_last, 1), "prev1s_dB": round(e_prev, 1)},
                         "末 50 ms 仍有电平且未衰减，疑似硬断，需人工听末 3 s" if hard else "末端已衰减")
        # B-29 削波 / 首尾咔哒 / 词内短静音
        clip_runs = 0
        for c in range(x.shape[1]):
            m = (np.abs(x[:, c]) >= 0.999).astype(np.int8)
            if m.any():
                dm = np.diff(np.concatenate([[0], m, [0]]))
                st, en = np.where(dm == 1)[0], np.where(dm == -1)[0]
                clip_runs += int(((en - st) >= 3).sum())
        edge = {"first_abs": round(float(np.abs(x[0]).max()), 4), "last_abs": round(float(np.abs(x[-1]).max()), 4)}
        sil15 = intervals(flog(path, af="silencedetect=n=-50dB:d=0.15"), "silence", dur)
        short = [(round(a, 2), round(b, 2)) for a, b in sil15 if b - a < 0.4 and a > 0.05 and b < dur - 0.05]
        edgey = edge["first_abs"] > 0.05 or edge["last_abs"] > 0.05
        st_ = "fail" if clip_runs >= 10 else ("warn" if (clip_runs or edgey or short) else "pass")
        R["B-29"] = item(st_, {"clip_runs_ge3": clip_runs, "edge": edge, "short_silences_0.15-0.4s": short[:20]},
                         "削波 = 连续 ≥3 样本 ≥ 满幅 0.999；≥10 段未过。设计的瞬态不再计入。短静音需对 ASR 判是否在词内")
        win = int(0.1 * sr)
        rms = np.array([rms_db(mono[i:i + win]) for i in range(0, len(mono) - win, win)])
        meta["noise_floor_p5_dBFS"] = round(float(np.percentile(rms, 5)), 1)
        meta["loudness_LRA"] = audio.get("LRA")
        meta["shortterm_S_p10_p90"] = audio.get("S_p10_p90")
    else:
        for kk in ("B-04", "B-05", "B-06", "B-29"):
            R[kk] = item("n/a", None, "无音轨")

    for kk, vv in MANUAL.items():
        R.setdefault(kk, item("manual", None, vv))
    R = dict(sorted(R.items()))
    fails = [kk for kk, vv in R.items() if vv["status"] == "fail"]
    return {
        "status": "未过（判 L0）" if fails else "自动项通过（人工项待评审）",
        "auto_fail": fails,
        "warn": [kk for kk, vv in R.items() if vv["status"] == "warn"],
        "manual": [kk for kk, vv in R.items() if vv["status"] == "manual"],
        "checks": R,
    }, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp4")
    ap.add_argument("--card", default=None, help="评审卡 JSON")
    ap.add_argument("--target-dur", type=float, default=None)
    ap.add_argument("--platform", default=None, help="web | broadcast（评审卡 platform 优先）")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    card = load_card(a.card, a.target_dur, a.platform)
    info = probe(a.mp4)
    audio = {}
    deliv, dur, fps, vs, aus = delivery_layer(a.mp4, info, card, audio)
    aud, meta = audience_layer(a.mp4, deliv, dur, fps, aus, audio, card)
    meta.update({"file": a.mp4, "duration": round(dur, 3), "width": vs["width"], "height": vs["height"],
                 "fps": vs["r_frame_rate"], "has_audio": bool(aus)})
    res = {"standard": VERSION, "card": {k: v for k, v in card.items()},
           "delivery": deliv, "audience": aud, "meta": meta}
    s = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(s)
    print(json.dumps({"delivery": deliv["status"], "delivery_fails": deliv["fails"],
                      "audience": aud["status"], "audience_fail": aud["auto_fail"], "audience_warn": aud["warn"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
