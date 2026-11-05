#!/usr/bin/env python3
"""Video -> Transkript (Whisper) -> Claude waehlt Highlights -> FFmpeg schneidet 9:16 Clips mit Untertiteln."""
import argparse, json, os, shutil, subprocess, re
from pathlib import Path

MODEL = "claude-sonnet-5-5"

def transcribe(video, lang, size):
    from faster_whisper import WhisperModel
    model = WhisperModel(size, compute_type="int8")
    segs, _ = model.transcribe(str(video), language=lang, word_timestamps=True, vad_filter=True)
    out = []
    for s in segs:
        out.append({"start": s.start, "end": s.end, "text": s.text.strip(),
                    "words": [{"w": w.word.strip(), "s": w.start, "e": w.end} for w in s.words]})
    return out

def pick_clips(segments, n, lo, hi, lang):
    transcript = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)
    prompt = f"""Du bist Editor fuer TikTok/Instagram Reels. Waehle aus dem Transkript die {n} besten
Clips ({lo}-{hi} Sekunden). Kriterien: starker Hook in den ersten 3 Sekunden, in sich abgeschlossen,
emotional/ueberraschend/nuetzlich. Schneide an Satzgrenzen (nutze die Zeitstempel).
Sprache fuer Titel/Caption: {lang}.
Antworte NUR mit JSON: [{{"start":float,"end":float,"title":str,"caption":str,"hashtags":[str],"score":1-10}}]

Transkript:
{transcript}"""
    text = ask_claude(prompt)
    return json.loads(re.search(r"\[.*\]", text, re.S).group(0))

def ask_claude(prompt):
    """Mit ANTHROPIC_API_KEY ueber die API, sonst ueber das lokale `claude`-CLI (Abo)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        r = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=4000,
                                                  messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    if shutil.which("claude"):
        r = subprocess.run(["claude", "-p"], input=prompt, capture_output=True, text=True, check=True)
        return r.stdout
    raise SystemExit("Weder ANTHROPIC_API_KEY gesetzt noch `claude`-CLI gefunden.")

def ass_time(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def write_ass(path, words, offset, group=3):
    hdr = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n"
           "Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BorderStyle,Outline,Shadow,Alignment,MarginV\n"
           "Style: Default,Arial,84,&H00FFFFFF,&H00000000,1,6,0,2,520\n\n[Events]\n"
           "Format: Layer,Start,End,Style,Text\n")
    lines = []
    for i in range(0, len(words), group):
        g = words[i:i + group]
        txt = " ".join(w["w"] for w in g).upper()
        lines.append(f"Dialogue: 0,{ass_time(g[0]['s']-offset)},{ass_time(g[-1]['e']-offset)},Default,{txt}")
    Path(path).write_text(hdr + "\n".join(lines), encoding="utf-8")

def cut(video, clip, segments, out_dir, idx, mode):
    st, en = clip["start"], clip["end"]
    words = [w for s in segments for w in s["words"] if w["s"] >= st and w["e"] <= en]
    ass = out_dir / f"clip{idx}.ass"
    write_ass(ass, words, st)
    if mode == "blur":  # ganzes Bild, unscharfer Hintergrund
        vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,")
    else:  # center-crop
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
    vf += f"ass={ass.name}"
    out = out_dir / f"clip{idx}.mp4"
    subprocess.run(["ffmpeg", "-y", "-ss", str(st), "-to", str(en), "-i", str(Path(video).resolve()),
                    "-filter_complex" if mode == "blur" else "-vf", vf,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", out.name],
                   check=True, cwd=out_dir)
    return out

def process(video, out, n=5, lo=20, hi=60, lang="de", whisper="small", mode="crop"):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    segs = transcribe(video, lang, whisper)
    (out / "transcript.json").write_text(json.dumps(segs, ensure_ascii=False, indent=1))
    clips = pick_clips(segs, n, lo, hi, lang)
    meta = []
    for i, c in enumerate(sorted(clips, key=lambda c: -c.get("score", 0)), 1):
        f = cut(video, c, segs, out, i, mode)
        meta.append({**c, "file": f.name})
        print(f"✓ {f.name}: {c['title']}", flush=True)
    (out / "captions.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("--out", default="out")
    ap.add_argument("--n", type=int, default=5); ap.add_argument("--min", type=int, default=20)
    ap.add_argument("--max", type=int, default=60); ap.add_argument("--lang", default="de")
    ap.add_argument("--whisper", default="small"); ap.add_argument("--mode", choices=["crop", "blur"], default="crop")
    a = ap.parse_args()
    process(a.video, a.out, a.n, a.min, a.max, a.lang, a.whisper, a.mode)

if __name__ == "__main__":
    main()
