#!/usr/bin/env python
"""Render eval HTML outputs with headless Chromium (Playwright).

Usage:
  python render.py runs/deepseek-raw            # renders T1/T2/T3 html found in that dir
  python render.py runs/claude-raw --only T2

Outputs (same dir): T1.png | T2.mp4 T2.sheet.jpg | T3.mp4 T3.sheet.jpg | render.json
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
SPEC = {
    "T1": {"w": 1080, "h": 2340},
    "T2": {"w": 1920, "h": 1080, "dur": 10000},
    "T3": {"w": 1920, "h": 1080, "dur": 15000},
}
FPS = 30


# ---------------------------------------------------------------- bootstrap
def playwright_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


def ensure_playwright():
    if playwright_ok():
        return
    if os.environ.get("EVAL_RENDER_IN_VENV"):
        sys.exit("error: playwright still unavailable inside .venv")
    py = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        print("installing playwright into", VENV, file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
        subprocess.check_call([str(py), "-m", "pip", "install", "-q", "playwright"])
        subprocess.check_call([str(py), "-m", "playwright", "install", "chromium"])
    env = dict(os.environ, EVAL_RENDER_IN_VENV="1")
    sys.exit(subprocess.call([str(py), str(Path(__file__).resolve())] + sys.argv[1:], env=env))


# ---------------------------------------------------------------- helpers
def find_html(d, task):
    exact = d / f"{task}.html"
    if exact.exists():
        return exact
    c = sorted(p for p in d.glob("*.html") if re.match(rf"{task}(\b|[_\-.])", p.name, re.I))
    return c[0] if c else None


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        sys.exit("error: ffmpeg not found in PATH")
    return exe


def run_ff(args):
    r = subprocess.run([ffmpeg(), "-y", "-loglevel", "error"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + r.stderr[-1500:])


def make_sheet(mp4, sheet, seconds):
    cols = 5
    rows = max(1, -(-seconds // cols))
    run_ff(["-i", str(mp4), "-vf",
            f"select='not(mod(n\\,{FPS}))',scale=384:-1,tile={cols}x{rows}:padding=4:color=gray",
            "-frames:v", "1", "-q:v", "3", str(sheet)])


def wait_frames(page, n=2):
    page.evaluate("""n => new Promise(r => { const f = k => k ? requestAnimationFrame(() => f(k-1)) : r(); f(n); })""", n)


def new_page(browser, task, info, **ctx_kw):
    s = SPEC[task]
    ctx = browser.new_context(viewport={"width": s["w"], "height": s["h"]}, device_scale_factor=1, **ctx_kw)
    page = ctx.new_page()
    page.on("console", lambda m: info["console_errors"].append(m.text[:500]) if m.type == "error" else None)
    page.on("pageerror", lambda e: info["page_errors"].append(str(e)[:500]))
    page.on("request", lambda r: info["external_requests"].append(r.url[:300])
            if not r.url.startswith(("file:", "data:", "blob:", "about:")) else None)
    return ctx, page


def page_size(page):
    return page.evaluate("() => ({scrollW: document.documentElement.scrollWidth, scrollH: document.documentElement.scrollHeight})")


# ---------------------------------------------------------------- renderers
def render_t1(browser, html, d, info):
    ctx, page = new_page(browser, "T1", info)
    page.goto(html.as_uri(), wait_until="load", timeout=30000)
    page.wait_for_timeout(1500)
    info["doc_size"] = page_size(page)
    out = d / "T1.png"
    page.screenshot(path=str(out), full_page=False)
    info["outputs"] = [out.name]
    ctx.close()


def render_seek(browser, task, html, d, info):
    dur = SPEC[task]["dur"]
    ctx, page = new_page(browser, task, info)
    page.goto(html.as_uri(), wait_until="load", timeout=30000)
    page.wait_for_timeout(800)
    info["doc_size"] = page_size(page)
    has = page.evaluate("() => typeof window.__seek === 'function'")
    info["has_seek"] = has
    if not has:
        ctx.close()
        return False

    def seek(ms):
        page.evaluate("ms => { const r = window.__seek(ms); return (r && typeof r.then === 'function') ? r.then(() => 0) : 0; }", ms)
        wait_frames(page, 2)

    # determinism probe: seek(t) twice with something in between, compare pixels
    probe_ms = min(5000, dur // 2)
    try:
        seek(probe_ms); a = hashlib.md5(page.screenshot()).hexdigest()
        seek(1000); seek(probe_ms); b = hashlib.md5(page.screenshot()).hexdigest()
        page.wait_for_timeout(600); c = hashlib.md5(page.screenshot()).hexdigest()
        info["seek_repeatable"] = a == b
        info["seek_frozen_after_600ms"] = b == c
    except Exception as e:
        info["seek_errors"].append(f"probe: {e}"[:500])

    n = dur * FPS // 1000
    tmp = Path(tempfile.mkdtemp(prefix=f"eval_{task}_"))
    failed = 0
    t0 = time.time()
    try:
        for i in range(n):
            ms = round(i * 1000 / FPS)
            try:
                seek(ms)
            except Exception as e:
                failed += 1
                if len(info["seek_errors"]) < 10:
                    info["seek_errors"].append(f"{ms}ms: {e}"[:500])
            page.screenshot(path=str(tmp / f"f{i:05d}.png"))
        info["frames"] = n
        info["seek_failed_frames"] = failed
        info["capture_s"] = round(time.time() - t0, 1)
        mp4 = d / f"{task}.mp4"
        run_ff(["-framerate", str(FPS), "-i", str(tmp / "f%05d.png"), "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", str(mp4)])
    finally:
        ctx.close()
        shutil.rmtree(tmp, ignore_errors=True)
    sheet = d / f"{task}.sheet.jpg"
    make_sheet(mp4, sheet, dur // 1000)
    info["outputs"] = [mp4.name, sheet.name]
    return True


def render_realtime(browser, task, html, d, info):
    dur = SPEC[task]["dur"]
    s = SPEC[task]
    tmp = Path(tempfile.mkdtemp(prefix=f"eval_{task}_rec_"))
    ctx, page = new_page(browser, task, info, record_video_dir=str(tmp),
                         record_video_size={"width": s["w"], "height": s["h"]})
    t_open = time.time()
    page.goto(html.as_uri(), wait_until="load", timeout=30000)
    lead = time.time() - t_open
    page.wait_for_timeout(dur + 300)
    video = page.video
    ctx.close()
    src = Path(video.path())
    mp4 = d / f"{task}.mp4"
    try:
        run_ff(["-ss", f"{lead:.2f}", "-i", str(src), "-t", f"{dur/1000:.2f}", "-r", str(FPS),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(mp4)])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sheet = d / f"{task}.sheet.jpg"
    make_sheet(mp4, sheet, dur // 1000)
    info["mode"] = "realtime_fallback"
    info["outputs"] = [mp4.name, sheet.name]


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--only", nargs="*", choices=list(SPEC))
    ap.add_argument("--set", default="r1", choices=["r1", "r2", "r3"], help="task spec set: r1 (round 1) or r2 (round 2)")
    a = ap.parse_args()
    if a.set == "r2":
        SPEC.update({"T1": {"w": 1080, "h": 1350}, "T2": {"w": 1920, "h": 1080, "dur": 20000}, "T3": {"w": 1920, "h": 1080, "dur": 8000}})
    if a.set == "r3":
        SPEC.update({"T1": {"w": 1080, "h": 1350}, "T2": {"w": 1920, "h": 1080, "dur": 15000}, "T3": {"w": 1080, "h": 1920, "dur": 6000}})
    ensure_playwright()
    from playwright.sync_api import sync_playwright

    d = Path(a.run_dir).resolve()
    rj = d / "render.json"
    report = json.loads(rj.read_text(encoding="utf-8")) if rj.exists() else {}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-gpu-vsync"])
        for task in (a.only or list(SPEC)):
            html = find_html(d, task)
            if not html:
                print(f"[{task}] no html, skip")
                continue
            info = {"html": html.name, "mode": "screenshot" if task == "T1" else "seek",
                    "console_errors": [], "page_errors": [], "external_requests": [], "seek_errors": [],
                    "rendered_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            t0 = time.time()
            try:
                if task == "T1":
                    render_t1(browser, html, d, info)
                elif not render_seek(browser, task, html, d, info):
                    info["note"] = "window.__seek missing; recorded in real time"
                    render_realtime(browser, task, html, d, info)
                info["ok"] = True
            except Exception as e:
                info["ok"] = False
                info["error"] = f"{type(e).__name__}: {e}"[:1500]
                if task != "T1" and info.get("mode") == "seek" and "outputs" not in info:
                    try:
                        info["note"] = "seek rendering failed; recorded in real time"
                        render_realtime(browser, task, html, d, info)
                        info["ok"] = True
                    except Exception as e2:
                        info["fallback_error"] = f"{type(e2).__name__}: {e2}"[:1500]
            info["render_s"] = round(time.time() - t0, 1)
            report[task] = info
            rj.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{task}] ok={info['ok']} mode={info['mode']} outputs={info.get('outputs')} "
                  f"page_errors={len(info['page_errors'])}")
        browser.close()


if __name__ == "__main__":
    main()
