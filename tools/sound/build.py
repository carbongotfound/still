"""Makes the welcome flow's sounds. Every one is synthesized here from sines, harmonics and filtered noise: nothing is
sampled or downloaded, so they're Still's own work under its MIT license.

Run: python tools/sound/build.py   (numpy, scipy, and ffmpeg built with libopus on PATH)
Writes still-ui/public/sounds/<name>.ogg (Opus, 48 kHz mono) and prints each one's length, size, true peak and loudness.
The noise comes from fixed seeds, so every run makes the same sounds. The pitched ones share D major pentatonic, so any
of them can overlap without clashing.

intro      the welcome intro, 5.2 s, timed to the UI (seconds from the start): 0.30 a spark, then a shimmer of tiny
           notes that gathers, 1.00 the companion powers on (a low, warm thum), 1.40 and 1.55 its eyes open, 1.80 to
           2.60 it stretches (a rising hum), 2.60 to 3.00 a little shake (four rattles), 3.00 to 3.80 the light blooms
           (fullest at 3.60) and rings out to the end, 3.85 a two-note chime as the wordmark lands
whoosh     a step changing
click      a button press
pop        picking something
swap       swapping a part in the look editor
surprise   "Surprise me"
jingle     the end of the welcome flow
"""
import os, subprocess, tempfile
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, lfilter, resample_poly, sosfilt

SR = 48000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "still-ui", "public", "sounds")


def note(name):
    """A note's pitch in Hz: "A4" is 440, sharps are written "F#5"."""
    step = "C C#D D#E F F#G G#A A#B ".index(name[:-1].ljust(2)) // 2
    return 440 * 2 ** ((step + 12 * int(name[-1]) - 57) / 12)


def at(dur):
    """The sample times of a sound dur seconds long."""
    return np.arange(round(dur * SR)) / SR


def fade(t, attack, t60):
    """Rises over attack seconds, then falls 60 dB every t60 seconds."""
    return np.minimum(1, t / attack) * np.exp(-6.91 * t / t60)


def sine(f, t):
    """A sine at f Hz: a number, or a curve with one value per sample for a glide."""
    return np.sin(2 * np.pi * np.cumsum(np.broadcast_to(f, t.shape)) / SR)


def ring(f, dur, partials, attack=.002):
    """A struck tone: for each (ratio, level, t60), a sine at f times ratio falling 60 dB in t60 seconds."""
    t = at(dur)
    return sum(level * sine(f * ratio, t) * fade(t, attack, t60) for ratio, level, t60 in partials if np.max(f) * ratio < 9500)


def glock(f, dur, decay):
    """A small glockenspiel bar: bright, inharmonic overtones that die first."""
    return ring(f, dur, [(1, 1, decay), (2.76, .3, decay * .35), (5.4, .1, decay * .15)])


def mallet(f, dur, decay):
    """A soft wooden mallet: a round fundamental with a short knock on top."""
    return ring(f, dur, [(1, 1, decay), (3.93, .25, decay * .16), (9.6, .04, decay * .06)], .001)


def buzz(f, cutoff, t, detune=0.):
    """A warm band-limited buzz on f (Hz, number or curve) through a soft lowpass at cutoff (Hz, number or curve),
    detuned by some cents."""
    f = np.broadcast_to(f, t.shape) * 2 ** (detune / 1200)
    cutoff = np.broadcast_to(cutoff, t.shape)
    phase = 2 * np.pi * np.cumsum(f) / SR
    out = np.zeros_like(t)
    for k in range(1, int(min(9500, 4 * cutoff.max()) / f.min()) + 1):
        out += np.sin(k * phase) / k / (1 + (k * f / cutoff) ** 4) * (k * f < 9500)
    return out


DARK = butter(2, 6000, fs=SR, output="sos")


def hiss(seed, dur):
    """Noise from a fixed seed, softened above 6 kHz so nothing made from it sounds like hiss."""
    return sosfilt(DARK, np.random.default_rng(seed).standard_normal(round(dur * SR)))


def band(x, fc, q):
    """x through a resonant bandpass centred on fc (Hz, number or curve), unity gain at the centre. A topology-preserving
    state-variable filter, so it stays stable while the centre moves."""
    g = np.tan(np.pi * np.broadcast_to(fc, x.shape) / SR)
    k = 1 / q
    a1 = 1 / (1 + g * (g + k)); a2 = g * a1; a3 = g * a2
    out, s1, s2 = [], 0., 0.
    for xi, b1, b2, b3 in zip(x.tolist(), a1.tolist(), a2.tolist(), a3.tolist()):
        v1 = b1 * s1 + b2 * (xi - s2)
        v2 = s2 + b2 * s1 + b3 * (xi - s2)
        s1, s2 = 2 * v1 - s1, 2 * v2 - s2
        out.append(v1)
    return np.array(out) * k


def place(out, start, sound, gain):
    """Mixes sound into out at start seconds, cut off at out's end."""
    i = round(start * SR)
    sound = sound[:len(out) - i]
    out[i:i + len(sound)] += gain * sound


def room(x, t60, wet):
    """x in a soft room: a decaying noise tail, darkened above 4 kHz, mixed in at wet."""
    t = at(t60)
    tail = sosfilt(butter(2, 4000, fs=SR, output="sos"), hiss(1, t60) * np.exp(-6.91 * t / t60))
    tail[:round(.015 * SR)] = 0
    return x + wet * fftconvolve(x, tail / np.sqrt(np.sum(tail ** 2)))[:len(x)]


HIGHPASS = butter(2, 80, "high", fs=SR, output="sos")
LOWPASS = butter(4, 10000, fs=SR, output="sos")


def finish(x, fade_out):
    """Trims everything under 80 Hz and over 10 kHz and fades both ends, so nothing rumbles, hisses or clicks."""
    x = sosfilt(LOWPASS, sosfilt(HIGHPASS, x))
    i, o = round(.001 * SR), round(fade_out * SR)
    x[:i] *= np.linspace(0, 1, i)
    x[-o:] *= np.cos(np.linspace(0, np.pi / 2, o)) ** 2
    return x


def intro():
    out = np.zeros(round(5.2 * SR))
    # 0.30: a spark, then a shimmer of tiny high notes that gathers (more of them, higher, louder) until it powers on
    place(out, .30, ring(note("A7"), .2, [(1, 1, .06), (1.5, .25, .03)]), .35)
    place(out, .30, band(hiss(11, .02), 5000, 1) * fade(at(.02), .0005, .006), .3)
    sparkle = [note(n) for n in ("D6", "E6", "F#6", "A6", "B6", "D7", "E7", "F#7", "A7")]
    rng = np.random.default_rng(5)
    for i in range(36):
        p = np.sqrt((i + rng.random()) / 36)
        place(out, .34 + .64 * p, ring(sparkle[min(8, int(p * 7) + rng.integers(0, 3))], .3, [(1, 1, .2)]), .03 + .1 * p)
    t = at(.7)
    place(out, .30, band(hiss(12, .7), 3000 * (7 / 3) ** (t / .7), 2) * (t / .7) ** 2 * np.minimum(1, (.7 - t) / .03), .04)
    # 1.00: it powers on, a low thum that settles from a little above D3
    t = at(1.6)
    f = note("D3") * (1 + .4 * np.exp(-t / .03))
    place(out, 1.0, (sine(f, t) + .3 * sine(2 * f, t) + .1 * sine(3 * f, t)) * fade(t, .004, 1.1), .25)
    # 1.40 and 1.55: its eyes open, two little upward blips
    for start, low, high in ((1.40, "A5", "E6"), (1.55, "B5", "F#6")):
        t = at(.1)
        f = note(low) * (note(high) / note(low)) ** np.minimum(1, t / .035)
        place(out, start, (sine(f, t) + .2 * sine(2 * f, t)) * fade(t, .003, .09), .2)
    # 1.80 to 2.60: a stretch, a hum that rises D3 to A3 and opens up like "mmm-aah"
    t = at(.85)
    s = np.minimum(1, t / .75)
    ease = s * s * (3 - 2 * s)
    f = note("D3") * (note("A3") / note("D3")) ** ease * (1 + .012 * s * np.sin(2 * np.pi * 5.5 * t))
    place(out, 1.80, buzz(f, 300 + 1700 * ease, t) * s ** 1.5 * np.minimum(1, (.85 - t) / .1), .14)
    # 2.60 to 3.00: a little shake, four rattles stepping up toward the bloom
    for i, n in enumerate(("A4", "B4", "D5", "E5")):
        t = at(.12)
        place(out, 2.60 + .1 * i, band(hiss(20 + i, .12), 3200, 1.5) * np.abs(np.sin(2 * np.pi * 38 * t)) * fade(t, .004, .09), .3)
        place(out, 2.60 + .1 * i, mallet(note(n), .25, .25), .26)
    # 3.00 to 3.80: the light blooms, a D add9 chord and a rush of air swelling to 3.60, then ringing out
    t = at(2.2)
    rise = np.minimum(1, t / .6)
    swell = np.where(t < .6, rise ** 2, np.exp(-6.91 * (t - .6) / 2.4))
    cutoff = np.where(t < .6, 400 + 2800 * rise ** 2, 1200 + 2000 * np.exp(-(t - .6) / .5))
    pad = sum(buzz(note(n), cutoff, t, d) for n in ("D4", "A4", "D5", "E5", "F#5", "A5") for d in (-6, 6))
    place(out, 3.0, pad * swell, .06)
    t = at(.9)
    rise = np.minimum(1, t / .6)
    place(out, 3.0, band(hiss(30, .9), 600 * (5000 / 600) ** rise, 1.2) * np.where(t < .6, rise ** 3, np.exp(-6.91 * (t - .6) / .25)), .16)
    t = at(1.6)
    place(out, 3.6, (sine(note("D3"), t) + .3 * sine(note("D4"), t)) * fade(t, .02, 1.5), .25)
    # 3.85: the wordmark lands, A5 then D6
    place(out, 3.85, glock(note("A5"), 1.4, 1.6), .22)
    place(out, 4.03, glock(note("D6"), 1.2, 1.6), .26)
    return finish(room(out, 1.8, .3), .5)


def whoosh():
    t = at(.35)
    p = t / .35
    fc = 450 * 4.5 ** np.sin(np.pi * p)
    x = band(hiss(40, .35), fc, 1.4) + .4 * band(hiss(41, .35), 2 * fc, 2)
    return finish(x * p ** 1.2 * (1 - p) ** 2, .03)


def click():
    t = at(.04)
    tick = band(hiss(50, .04), 3800, 1.2) * fade(t, .0003, .004)
    return finish(ring(note("D6"), .04, [(1, 1, .025), (2.4, .35, .01)], .0005) + .5 * tick, .01)


def pop():
    t = at(.12)
    f = note("D4") * 3 ** np.minimum(1, t / .045)
    return finish((sine(f, t) + .15 * sine(2 * f, t)) * fade(t, .001, .1), .02)


def swap():
    t = at(.15)
    flick = band(hiss(60, .15), 1200 * 3.5 ** np.minimum(1, t / .06), 2) * fade(t, .002, .05)
    f = note("E5") * (note("A5") / note("E5")) ** np.minimum(1, t / .025)
    return finish((sine(f, t) + .25 * sine(2 * f, t)) * fade(t, .002, .12) + .5 * flick, .02)


def surprise():
    out = np.zeros(round(.7 * SR))
    for i, n in enumerate(("D5", "F#5", "A5", "D6", "F#6")):
        place(out, .05 * i, glock(note(n), .5, .35), .4)
    t = at(.3)
    place(out, 0, band(hiss(70, .3), 900 * (5000 / 900) ** (t / .3), 1.5) * np.sin(np.pi * t / .3), .15)
    rng = np.random.default_rng(7)
    for i in range(7):
        place(out, .22 + .04 * i + .02 * rng.random(), ring(note(rng.choice(["D7", "E7", "F#7", "A7"])), .2, [(1, 1, .12)]), .1 - .01 * i)
    return finish(room(out, .6, .2), .08)


def jingle():
    out = np.zeros(round(1.4 * SR))
    for i, n in enumerate(("A4", "D5", "F#5", "A5")):
        place(out, .09 * i, mallet(note(n), .6, .45), .5 + .1 * i)
    place(out, .38, glock(note("D6"), 1.0, 1.2), .6)
    t = at(1.0)
    place(out, .38, sum(buzz(note(n), 1600, t, d) for n in ("D5", "F#5", "A5") for d in (-5, 5)) * fade(t, .04, 1.0), .05)
    rng = np.random.default_rng(9)
    for i in range(6):
        place(out, .45 + .07 * i + .03 * rng.random(), ring(note(rng.choice(["D7", "F#7", "A7"])), .25, [(1, 1, .15)]), .08)
    return finish(room(out, 1.0, .25), .2)


SOUNDS = {  # name: (how it's made, momentary loudness at its loudest in LUFS, true-peak ceiling in dBTP, Opus kbps)
    "intro": (intro, -21, -3, 64),
    "jingle": (jingle, -22, -3, 64),
    "whoosh": (whoosh, -31, -9, 64),
    "click": (click, -36, -9, 48),
    "pop": (pop, -31, -9, 48),
    "swap": (swap, -31, -9, 48),
    "surprise": (surprise, -27, -9, 48),
}

# ITU-R BS.1770 K-weighting at 48 kHz: a high shelf, then a highpass
K_WEIGHT = [([1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, .73248077421585]),
            ([1, -2, 1], [1, -1.99004745483398, .99007225036621])]


def loudness(x):
    """Momentary loudness at its loudest, in LUFS (K-weighted, 400 ms windows). A shorter sound counts as a 400 ms
    window holding it."""
    for b, a in K_WEIGHT:
        x = lfilter(b, a, x)
    win = round(.4 * SR)
    energy = np.concatenate([[0], np.cumsum(np.pad(x, (0, max(0, win - len(x)))) ** 2)])
    return -.691 + 10 * np.log10(np.max(energy[win:] - energy[:-win]) / win)


def peak(x):
    """True peak in dBTP: the sample peak of x at four times the rate, which catches peaks between samples."""
    return 20 * np.log10(np.max(np.abs(resample_poly(x, 4, 1))))


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, (make, target, ceiling, kbps) in SOUNDS.items():
            x = make()
            x *= 10 ** (min(target - loudness(x), ceiling - 1 - peak(x)) / 20)  # 1 dB to spare for the codec
            wav, ogg = os.path.join(tmp, name + ".wav"), os.path.join(OUT, name + ".ogg")
            wavfile.write(wav, SR, x.astype(np.float32))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libopus", "-b:a", f"{kbps}k", "-application", "audio",
                            "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact", ogg], check=True)
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", ogg, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                                 check=True, capture_output=True).stdout
            y = np.frombuffer(raw, np.float32).astype(float)
            total += os.path.getsize(ogg)
            print(f"{name:9} {len(y) / SR:5.2f} s {os.path.getsize(ogg) / 1024:5.1f} KB   peak {peak(y):5.1f} dBTP   loudest {loudness(y):5.1f} LUFS")
            assert peak(y) <= ceiling, f"{name} peaks over {ceiling} dBTP"
    print(f"total {total / 1024:.1f} KB")
    assert total < 500 * 1024, "the sounds should stay under 500 KB"


if __name__ == "__main__":
    main()
