"""Single source of truth for 《Call of Silence》 fingerstyle guitar TAB & audio.

Concert Key: A Major / F# Minor (1 = A / 6 = F#m)
Guitar Tuning: Standard (6E 5A 4D 3G 2B 1E) with Capo on 2nd fret (G/Em shapes)
Time Signature: 4/4 (16 sixteenth-note slots per measure)
Tempo: 72 BPM
Techniques: Hammer-on (H), Pull-off (P), Slide (S), Arpeggio, Harmonics (<12>),
            Palm Mute (P.M.), and Chorus Thumb Slap (X).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

TITLE = "Call of Silence"
SUBTITLE = "《进击的巨人》第二季插曲 · 指弹吉他独奏六线谱"
COMPOSER = "泽野弘之 (Hiroyuki Sawano)"
ARRANGER_INFO = "原调：1 = A / F#m  |  选调：G调指法 (Capo = 2品)  |  标准调弦：6E 5A 4D 3G 2B 1E"
CHORD_LEGEND = "和弦对照 (Capo 2)：Cmaj7 = Dmaj7   D = E   Em = F#m   G = A   Am7 = Bm7   Bm7 = C#m7"
TECHNIQUE_LEGEND_1 = (
    "技巧图例：H = 击弦 (Hammer-on)   P = 勾弦 (Pull-off)   S = 滑音 (Slide)   "
    "波浪线 = 琶音 (Arpeggio)"
)
TECHNIQUE_LEGEND_2 = (
    "<12> = 自然泛音 (Harm.)   P.M. = 右手闷音 (Palm Mute)   X = 拍弦 (Thumb Slap)"
)

TEMPO_BPM = 72
CAPO = 2

# Standard guitar open strings (without capo): 6=E2(40), 5=A2(45), 4=D3(50), 3=G3(55), 2=B3(59), 1=E4(64)
OPEN_TUNING_NO_CAPO: Dict[int, int] = {
    6: 40,
    5: 45,
    4: 50,
    3: 55,
    2: 59,
    1: 64,
}

# A Major / F# Minor diatonic pitch classes: A(9), B(11), C#(1), D(2), E(4), F#(6), G#(8)
DIATONIC_PCS = {9, 11, 1, 2, 4, 6, 8}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass(frozen=True)
class NoteEvent:
    string: int  # 1..6 (1 is highest E, 6 is lowest E)
    fret: int    # TAB fret relative to Capo 2 (0 = open at capo 2)
    role: str = "melody"  # "melody" | "bass" | "inner" | "slap"
    harmonic: bool = False
    grace_from: Optional[int] = None
    palm_mute: bool = False

    @property
    def concert_midi(self) -> int:
        return OPEN_TUNING_NO_CAPO[self.string] + CAPO + self.fret

    @property
    def written_midi(self) -> int:
        """Written pitch before capo (for LilyPond TabStaff fret computation)."""
        return OPEN_TUNING_NO_CAPO[self.string] + self.fret

    @property
    def pitch_name(self) -> str:
        m = self.concert_midi
        return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


@dataclass
class BeatEvent:
    slot: int       # 0..15 in 16th-note units
    dur: int        # duration in 16th-note units (1, 2, 3, 4, 6, 8, 12, 16)
    notes: Tuple[NoteEvent, ...] = ()
    rest: bool = False
    lyric: Optional[str] = None
    fermata: bool = False
    arpeggio: bool = False
    link_tech: Optional[str] = None  # "H" | "P" | "S"


@dataclass
class Measure:
    bar: int
    events: List[BeatEvent]
    chords: List[Tuple[int, str]] = field(default_factory=list)
    section: Optional[str] = None
    is_pickup: bool = False
    dynamic: float = 1.0  # relative velocity multiplier for musical phrasing


def n(
    string: int,
    fret: int,
    role: str = "melody",
    *,
    harmonic: bool = False,
    grace_from: Optional[int] = None,
    palm_mute: bool = False,
) -> NoteEvent:
    return NoteEvent(
        string=string,
        fret=fret,
        role=role,
        harmonic=harmonic,
        grace_from=grace_from,
        palm_mute=palm_mute,
    )


def ev(
    slot: int,
    dur: int,
    *notes: NoteEvent,
    rest: bool = False,
    lyric: Optional[str] = None,
    fermata: bool = False,
    arpeggio: bool = False,
    link_tech: Optional[str] = None,
) -> BeatEvent:
    return BeatEvent(
        slot=slot,
        dur=dur,
        notes=notes,
        rest=rest,
        lyric=lyric,
        fermata=fermata,
        arpeggio=arpeggio,
        link_tech=link_tech,
    )


def build_measures() -> List[Measure]:
    """Return the verified 45 measures (M00 pickup + M01..M44) with fingerstyle techniques."""
    m: List[Measure] = []

    # =========================================================================
    # [Intro] Iconic Piano Theme (M00 pickup - M09)
    # =========================================================================
    m.append(Measure(
        bar=0,
        is_pickup=True,
        section="Intro",
        dynamic=0.84,
        events=[
            ev(12, 2, n(1, 0, "melody"), link_tech="H"),
            ev(14, 2, n(1, 3, "melody")),
        ],
    ))

    # M01: Cmaj7 -> D
    m.append(Measure(
        bar=1,
        dynamic=0.86,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(
                0, 2,
                n(6, 8, "bass"), n(3, 0, "inner"), n(2, 0, "inner"),
                n(1, 7, "melody", grace_from=5),
                arpeggio=True,
            ),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(2, 0, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(4, 0, "bass"), n(3, 2, "inner"), n(1, 5, "melody")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(1, 2, "melody"), link_tech="H"),
            ev(14, 2, n(1, 3, "melody")),
        ],
    ))

    # M02: Em9 -> Bm7
    m.append(Measure(
        bar=2,
        dynamic=0.86,
        chords=[(0, "Em9"), (12, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(2, 7, "inner"), n(1, 5, "melody"), arpeggio=True),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(2, 0, "inner")),
            ev(10, 2, n(3, 0, "inner")),
            ev(12, 2, n(6, 7, "bass"), n(1, 10, "melody", grace_from=7)),
            ev(14, 2, n(2, 7, "melody")),
        ],
    ))

    # M03: Cmaj7 -> D
    m.append(Measure(
        bar=3,
        dynamic=0.86,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(4, 2, "inner"), n(1, 0, "melody"), arpeggio=True),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(2, 0, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(4, 0, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(1, 0, "melody")),
            ev(14, 2, n(1, 5, "melody")),
        ],
    ))

    # M04: Em -> pickup
    m.append(Measure(
        bar=4,
        dynamic=0.85,
        chords=[(0, "Em")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 2, "melody"), link_tech="H"),
            ev(2, 2, n(1, 3, "melody")),
            ev(4, 2, n(5, 2, "inner")),
            ev(6, 2, n(4, 2, "inner")),
            ev(8, 2, n(3, 0, "inner")),
            ev(10, 2, n(2, 0, "inner")),
            ev(12, 2, n(1, 0, "melody"), link_tech="H"),
            ev(14, 2, n(1, 3, "melody")),
        ],
    ))

    # M05: Cmaj7 -> D (repeat of M01)
    m.append(Measure(
        bar=5,
        dynamic=0.88,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(
                0, 2,
                n(6, 8, "bass"), n(3, 0, "inner"), n(2, 0, "inner"),
                n(1, 7, "melody", grace_from=5),
                arpeggio=True,
            ),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(2, 0, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(4, 0, "bass"), n(3, 2, "inner"), n(1, 5, "melody")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(1, 2, "melody"), link_tech="H"),
            ev(14, 2, n(1, 3, "melody")),
        ],
    ))

    # M06: Am7 -> Em -> Bm7
    m.append(Measure(
        bar=6,
        dynamic=0.88,
        chords=[(0, "Am7"), (4, "Em"), (12, "Bm7")],
        events=[
            ev(0, 2, n(5, 0, "bass"), n(1, 5, "melody")),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(6, 0, "bass"), n(1, 3, "melody")),
            ev(6, 2, n(4, 2, "inner")),
            ev(8, 2, n(3, 0, "inner")),
            ev(10, 2, n(2, 0, "inner")),
            ev(12, 2, n(6, 7, "bass"), n(1, 10, "melody", grace_from=7)),
            ev(14, 2, n(1, 5, "melody")),
        ],
    ))

    # M07: Cmaj7 -> D
    m.append(Measure(
        bar=7,
        dynamic=0.88,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(1, 3, "melody")),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(3, 0, "inner")),
            ev(6, 2, n(2, 0, "inner")),
            ev(8, 2, n(4, 0, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(1, 0, "melody")),
            ev(14, 2, n(1, 5, "melody")),
        ],
    ))

    # M08: Em9
    m.append(Measure(
        bar=8,
        dynamic=0.84,
        chords=[(0, "Em9")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 5, "melody"), link_tech="P"),
            ev(2, 2, n(1, 3, "melody")),
            ev(4, 2, n(5, 2, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(4, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(2, 0, "inner")),
            ev(12, 2, n(1, 0, "melody")),
            ev(14, 2, n(3, 0, "inner")),
        ],
    ))

    # M09: Em9 -> Bell Harmonics -> Vocal Pickup "Don't you"
    m.append(Measure(
        bar=9,
        dynamic=0.84,
        chords=[(0, "Em9")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 2, "melody")),
            ev(2, 2, n(2, 12, "inner", harmonic=True)),
            ev(4, 2, n(1, 12, "melody", harmonic=True)),
            ev(6, 2, n(3, 12, "inner", harmonic=True)),
            ev(8, 4, n(4, 12, "bass", harmonic=True)),
            ev(12, 2, n(1, 0, "melody"), lyric="Don't"),
            ev(14, 2, n(1, 7, "melody"), lyric="you"),
        ],
    ))

    # =========================================================================
    # [Verse] "Don't you think about me enough?..." (M10 - M17)
    # =========================================================================
    # M10: Cmaj7 -> D
    m.append(Measure(
        bar=10,
        section="Verse",
        dynamic=0.90,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(6, 8, "bass"), n(1, 7, "melody", grace_from=5), lyric="think"),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 1, n(2, 0, "inner")),
            ev(5, 1, n(2, 8, "melody"), lyric="a-"),
            ev(6, 2, n(1, 7, "melody"), lyric="-bout"),
            ev(8, 2, n(4, 0, "bass"), n(1, 5, "melody"), lyric="me"),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(5, 0, "bass"), n(2, 3, "melody"), lyric="e-"),
            ev(14, 2, n(1, 0, "melody")),
        ],
    ))

    # M11: Em9 -> Pickup "I've been"
    m.append(Measure(
        bar=11,
        dynamic=0.90,
        chords=[(0, "Em9")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 0, "melody"), lyric="-nough"),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(1, 2, "melody")),
            ev(6, 2, n(2, 0, "inner")),
            ev(8, 2, n(4, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(3, 0, "inner")),
            ev(12, 2, n(1, 0, "melody"), lyric="I've"),
            ev(14, 2, n(1, 7, "melody"), lyric="been"),
        ],
    ))

    # M12: Cmaj7 -> D
    m.append(Measure(
        bar=12,
        dynamic=0.91,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(6, 8, "bass"), n(1, 7, "melody"), lyric="burn-"),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 1, n(2, 0, "inner")),
            ev(5, 1, n(2, 8, "melody"), lyric="-ing"),
            ev(6, 1, n(1, 7, "melody")),
            ev(7, 1, n(2, 7, "melody"), lyric="my"),
            ev(8, 1, n(4, 0, "bass"), n(1, 5, "melody"), lyric="heart", link_tech="P"),
            ev(9, 3, n(1, 2, "melody")),
            ev(12, 2, n(5, 0, "bass"), n(2, 3, "melody")),
            ev(14, 1, n(1, 3, "melody")),
            ev(15, 1, n(1, 7, "melody"), lyric="out"),
        ],
    ))

    # M13: Em9 -> Pickup "I've got"
    m.append(Measure(
        bar=13,
        dynamic=0.90,
        chords=[(0, "Em9")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 7, "melody")),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(1, 2, "melody"), link_tech="P"),
            ev(6, 2, n(1, 0, "melody")),
            ev(8, 2, n(5, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(2, 0, "inner")),
            ev(12, 2, n(1, 0, "melody"), lyric="I've"),
            ev(14, 2, n(1, 7, "melody"), lyric="got"),
        ],
    ))

    # M14: Cmaj7 -> D
    m.append(Measure(
        bar=14,
        dynamic=0.92,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(6, 8, "bass"), n(1, 7, "melody"), lyric="to face"),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 1, n(2, 0, "inner")),
            ev(5, 1, n(2, 8, "melody"), lyric="need"),
            ev(6, 1, n(1, 7, "melody")),
            ev(7, 1, n(2, 7, "melody"), lyric="to"),
            ev(8, 1, n(4, 0, "bass"), n(1, 5, "melody"), lyric="tell", link_tech="P"),
            ev(9, 3, n(1, 2, "melody")),
            ev(12, 2, n(5, 0, "bass"), n(2, 3, "melody")),
            ev(14, 1, n(1, 3, "melody"), lyric="you"),
            ev(15, 1, n(2, 3, "melody")),
        ],
    ))

    # M15: Em9 -> Pickup "I"
    m.append(Measure(
        bar=15,
        dynamic=0.90,
        chords=[(0, "Em9")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(2, 3, "melody")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(1, 0, "melody")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(4, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(2, 0, "inner")),
            ev(12, 2, n(1, 0, "melody")),
            ev(14, 2, n(2, 3, "melody"), lyric="I"),
        ],
    ))

    # M16: Cmaj7 -> D
    m.append(Measure(
        bar=16,
        dynamic=0.91,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(2, 3, "melody"), lyric="won't"),
            ev(2, 2, n(1, 0, "melody"), lyric="run"),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(4, 0, "bass"), n(3, 2, "inner")),
            ev(10, 2, n(5, 0, "bass")),
            ev(12, 2, n(1, 5, "melody"), lyric="be-cause"),
            ev(14, 1, n(1, 3, "melody"), lyric="I'm", link_tech="H"),
            ev(15, 1, n(1, 5, "melody"), lyric="re-"),
        ],
    ))

    # M17: Em -> Verse ending Harmonics
    m.append(Measure(
        bar=17,
        dynamic=0.89,
        chords=[(0, "Em")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 5, "melody"), lyric="re-"),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(1, 2, "melody"), lyric="-ti-"),
            ev(6, 1, n(1, 3, "melody"), lyric="-cent", link_tech="P"),
            ev(7, 1, n(1, 0, "melody")),
            ev(8, 2, n(4, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(2, 12, "inner", harmonic=True)),
            ev(12, 2, n(6, 0, "bass"), n(1, 0, "melody")),
            ev(14, 2, n(3, 12, "inner", harmonic=True)),
        ],
    ))

    # =========================================================================
    # [Interlude] Sawano Signature Arpeggio Build (M18 - M27)
    # M18..M22: Palm Muted bass & inner accompaniment (P.M.), opening in M23
    # =========================================================================
    # M18: Cmaj7 -> Am7
    m.append(Measure(
        bar=18,
        section="Interlude",
        dynamic=0.88,
        chords=[(0, "Cmaj7"), (12, "Am7")],
        events=[
            ev(0, 2, n(5, 3, "bass", palm_mute=True), n(1, 0, "melody")),
            ev(2, 1, n(1, 5, "melody")),
            ev(3, 1, n(1, 2, "melody")),
            ev(4, 2, n(3, 0, "inner", palm_mute=True)),
            ev(6, 1, n(1, 7, "melody")),
            ev(7, 1, n(2, 7, "melody")),
            ev(8, 2, n(6, 8, "bass", palm_mute=True), n(2, 8, "melody")),
            ev(10, 1, n(1, 7, "melody")),
            ev(11, 1, n(2, 8, "melody")),
            ev(12, 2, n(5, 0, "bass", palm_mute=True), n(2, 5, "melody")),
            ev(14, 1, n(1, 7, "melody")),
            ev(15, 1, n(2, 8, "melody")),
        ],
    ))

    # M19: G -> Bm7
    m.append(Measure(
        bar=19,
        dynamic=0.90,
        chords=[(0, "G"), (12, "Bm7")],
        events=[
            ev(0, 2, n(6, 3, "bass", palm_mute=True), n(1, 3, "melody")),
            ev(2, 1, n(1, 7, "melody")),
            ev(3, 1, n(1, 5, "melody")),
            ev(4, 2, n(4, 0, "bass", palm_mute=True)),
            ev(6, 1, n(1, 7, "melody")),
            ev(7, 1, n(1, 5, "melody")),
            ev(8, 2, n(3, 0, "inner", palm_mute=True), n(1, 7, "melody")),
            ev(10, 1, n(1, 10, "melody")),
            ev(11, 1, n(1, 7, "melody")),
            ev(12, 1, n(5, 2, "bass", palm_mute=True), n(2, 3, "melody")),
            ev(13, 1, n(1, 2, "melody")),
            ev(14, 1, n(2, 0, "inner", palm_mute=True)),
            ev(15, 1, n(1, 7, "melody")),
        ],
    ))

    # M20: Am7 -> C
    m.append(Measure(
        bar=20,
        dynamic=0.92,
        chords=[(0, "Am7"), (12, "C")],
        events=[
            ev(0, 2, n(5, 0, "bass", palm_mute=True), n(3, 9, "melody")),
            ev(2, 1, n(2, 12, "melody")),
            ev(3, 2, n(1, 12, "melody")),
            ev(5, 1, n(3, 9, "melody")),
            ev(6, 1, n(2, 12, "melody")),
            ev(7, 2, n(1, 12, "melody")),
            ev(9, 1, n(3, 9, "melody")),
            ev(10, 1, n(2, 12, "melody")),
            ev(11, 1, n(1, 10, "melody")),
            ev(12, 1, n(6, 8, "bass", palm_mute=True)),
            ev(13, 1, n(1, 8, "melody")),
            ev(14, 1, n(1, 7, "melody")),
            ev(15, 1, n(2, 10, "melody")),
        ],
    ))

    # M21: G -> Bm7
    m.append(Measure(
        bar=21,
        dynamic=0.92,
        chords=[(0, "G"), (12, "Bm7")],
        events=[
            ev(0, 2, n(6, 3, "bass", palm_mute=True), n(1, 5, "melody")),
            ev(2, 1, n(1, 7, "melody")),
            ev(3, 1, n(1, 5, "melody")),
            ev(4, 2, n(4, 0, "bass", palm_mute=True)),
            ev(6, 1, n(1, 7, "melody")),
            ev(7, 1, n(1, 5, "melody")),
            ev(8, 2, n(3, 0, "inner", palm_mute=True), n(1, 7, "melody")),
            ev(10, 1, n(1, 10, "melody")),
            ev(11, 1, n(1, 7, "melody")),
            ev(12, 1, n(5, 2, "bass", palm_mute=True), n(2, 3, "melody")),
            ev(13, 1, n(1, 2, "melody")),
            ev(14, 1, n(2, 0, "inner", palm_mute=True)),
            ev(15, 1, n(1, 3, "melody")),
        ],
    ))

    # M22: Cmaj7 -> Am7
    m.append(Measure(
        bar=22,
        dynamic=0.94,
        chords=[(0, "Cmaj7"), (12, "Am7")],
        events=[
            ev(0, 2, n(5, 3, "bass", palm_mute=True), n(1, 0, "melody")),
            ev(2, 1, n(1, 5, "melody")),
            ev(3, 1, n(1, 0, "melody")),
            ev(4, 2, n(3, 0, "inner", palm_mute=True)),
            ev(6, 1, n(1, 7, "melody")),
            ev(7, 1, n(2, 8, "melody")),
            ev(8, 2, n(6, 8, "bass", palm_mute=True), n(2, 8, "melody")),
            ev(10, 1, n(1, 7, "melody")),
            ev(11, 1, n(2, 8, "melody")),
            ev(12, 2, n(5, 0, "bass", palm_mute=True), n(1, 0, "melody")),
            ev(14, 1, n(1, 7, "melody")),
            ev(15, 1, n(2, 8, "melody")),
        ],
    ))

    # M23: G -> Bm7 (unmuted open build)
    m.append(Measure(
        bar=23,
        dynamic=0.96,
        chords=[(0, "G"), (12, "Bm7")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(1, 3, "melody")),
            ev(2, 1, n(1, 7, "melody")),
            ev(3, 1, n(1, 5, "melody")),
            ev(4, 2, n(4, 0, "bass")),
            ev(6, 1, n(1, 7, "melody")),
            ev(7, 1, n(1, 5, "melody")),
            ev(8, 2, n(3, 0, "inner"), n(1, 7, "melody")),
            ev(10, 1, n(1, 10, "melody")),
            ev(11, 1, n(1, 7, "melody")),
            ev(12, 1, n(5, 2, "bass"), n(2, 3, "melody")),
            ev(13, 1, n(1, 2, "melody")),
            ev(14, 1, n(2, 0, "inner")),
            ev(15, 1, n(2, 3, "melody")),
        ],
    ))

    # M24: D ostinato build
    m.append(Measure(
        bar=24,
        dynamic=0.97,
        chords=[(0, "D")],
        events=[
            ev(0, 2, n(4, 0, "bass"), n(3, 7, "melody")),
            ev(2, 1, n(2, 10, "melody")),
            ev(3, 2, n(1, 10, "melody")),
            ev(5, 1, n(3, 7, "melody")),
            ev(6, 1, n(2, 10, "melody")),
            ev(7, 1, n(1, 10, "melody")),
            ev(8, 1, n(5, 0, "bass")),
            ev(9, 1, n(3, 7, "melody")),
            ev(10, 1, n(2, 10, "melody")),
            ev(11, 1, n(1, 10, "melody")),
            ev(12, 1, n(4, 0, "bass"), n(3, 9, "melody")),
            ev(13, 1, n(3, 7, "melody")),
            ev(14, 1, n(2, 10, "melody")),
            ev(15, 1, n(1, 10, "melody")),
        ],
    ))

    # M25: D/F# ostinato build
    m.append(Measure(
        bar=25,
        dynamic=0.99,
        chords=[(0, "D/F#")],
        events=[
            ev(0, 2, n(5, 0, "bass"), n(3, 7, "melody")),
            ev(2, 1, n(2, 10, "melody")),
            ev(3, 2, n(1, 10, "melody")),
            ev(5, 1, n(3, 7, "melody")),
            ev(6, 1, n(2, 10, "melody")),
            ev(7, 1, n(1, 10, "melody")),
            ev(8, 1, n(5, 0, "bass")),
            ev(9, 1, n(3, 7, "melody")),
            ev(10, 1, n(2, 10, "melody")),
            ev(11, 1, n(1, 10, "melody")),
            ev(12, 1, n(4, 0, "bass"), n(3, 9, "melody")),
            ev(13, 1, n(3, 7, "melody")),
            ev(14, 1, n(2, 10, "melody")),
            ev(15, 1, n(1, 10, "melody")),
        ],
    ))

    # M26: G -> D climax build
    m.append(Measure(
        bar=26,
        dynamic=1.00,
        chords=[(0, "G"), (12, "D")],
        events=[
            ev(0, 2, n(3, 0, "bass")),
            ev(2, 1, n(2, 10, "melody")),
            ev(3, 2, n(1, 10, "melody")),
            ev(5, 1, n(3, 7, "melody")),
            ev(6, 1, n(2, 10, "melody")),
            ev(7, 2, n(1, 10, "melody")),
            ev(9, 1, n(3, 7, "melody")),
            ev(10, 1, n(2, 10, "melody")),
            ev(11, 1, n(1, 10, "melody")),
            ev(12, 1, n(4, 0, "bass"), n(3, 9, "melody")),
            ev(13, 1, n(3, 7, "melody")),
            ev(14, 1, n(2, 10, "melody")),
            ev(15, 1, n(1, 10, "melody")),
        ],
    ))

    # M27: D dramatic stop (rolled chord) + Chorus pickup "You will" (timed slide 7\5)
    m.append(Measure(
        bar=27,
        dynamic=0.95,
        chords=[(0, "D")],
        events=[
            ev(
                0, 6,
                n(5, 0, "bass"), n(4, 0, "inner"), n(3, 2, "inner"), n(2, 3, "inner"), n(1, 5, "melody"),
                arpeggio=True,
            ),
            ev(6, 6, rest=True),
            ev(12, 2, n(1, 7, "melody"), lyric="You", link_tech="S"),
            ev(14, 2, n(1, 5, "melody"), lyric="will"),
        ],
    ))

    # =========================================================================
    # [Chorus I] "You will know you're reborn tonight..." (M28 - M35)
    # =========================================================================
    # M28: Cmaj7 -> D
    m.append(Measure(
        bar=28,
        section="Chorus I",
        dynamic=0.98,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(3, 0, "inner"), n(1, 5, "melody"), lyric="know", arpeggio=True),
            ev(2, 2, n(4, 2, "inner"), n(1, 3, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 3, "melody"), lyric="you're"),
            ev(6, 2, n(2, 3, "melody"), lyric="re-"),
            ev(8, 2, n(4, 0, "bass"), n(1, 3, "melody"), lyric="-born"),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(6, 0, "slap"), n(5, 0, "bass"), n(1, 2, "melody"), lyric="to-", link_tech="H"),
            ev(14, 2, n(1, 3, "melody"), lyric="-night"),
        ],
    ))

    # M29: Em -> Am7 -> Pickup "Must be"
    m.append(Measure(
        bar=29,
        dynamic=0.96,
        chords=[(0, "Em"), (6, "Am7")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 0, "melody")),
            ev(2, 1, n(5, 2, "inner"), n(2, 0, "inner")),
            ev(3, 1, n(1, 0, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 3, "melody")),
            ev(6, 1, n(5, 0, "bass")),
            ev(7, 1, n(1, 0, "melody")),
            ev(8, 2, n(4, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(5, 0, "bass"), n(1, 0, "melody")),
            ev(12, 2, n(6, 0, "bass"), n(1, 7, "melody"), lyric="Must", link_tech="P"),
            ev(14, 2, n(1, 5, "melody"), lyric="be"),
        ],
    ))

    # M30: Cmaj7 -> D
    m.append(Measure(
        bar=30,
        dynamic=0.98,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(1, 5, "melody"), lyric="rag-"),
            ev(2, 2, n(4, 2, "inner"), n(1, 3, "melody"), lyric="-ged"),
            ev(4, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(2, 3, "melody"), lyric="but"),
            ev(6, 2, n(1, 7, "melody"), lyric="I'll"),
            ev(8, 2, n(4, 0, "bass"), n(1, 5, "melody"), lyric="stay"),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(6, 0, "slap"), n(5, 0, "bass"), n(1, 7, "melody"), lyric="by"),
            ev(14, 2, n(1, 3, "melody"), lyric="your"),
        ],
    ))

    # M31: Em -> Am7 -> Pickup "Even if"
    m.append(Measure(
        bar=31,
        dynamic=0.97,
        chords=[(0, "Em"), (6, "Am7")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 0, "melody"), lyric="side"),
            ev(2, 1, n(5, 2, "inner"), n(2, 0, "inner")),
            ev(3, 1, n(1, 0, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 3, "melody")),
            ev(6, 1, n(5, 0, "bass")),
            ev(7, 1, n(1, 0, "melody")),
            ev(8, 2, n(4, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(5, 0, "bass"), n(1, 0, "melody")),
            ev(12, 2, n(6, 0, "bass"), n(1, 7, "melody"), lyric="E-ven", link_tech="P"),
            ev(14, 2, n(1, 5, "melody"), lyric="if"),
        ],
    ))

    # M32: Cmaj7 -> D
    m.append(Measure(
        bar=32,
        dynamic=1.00,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(3, 0, "inner"), n(1, 5, "melody"), lyric="my", arpeggio=True),
            ev(2, 2, n(4, 2, "inner"), n(1, 3, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 3, "melody"), lyric="bo-"),
            ev(6, 2, n(1, 10, "melody", grace_from=8), lyric="-dy's"),
            ev(8, 2, n(4, 0, "bass"), n(1, 10, "melody"), lyric="bleached"),
            ev(10, 2, n(5, 0, "bass"), n(1, 10, "melody"), lyric="to"),
            ev(12, 2, n(6, 0, "slap"), n(4, 0, "bass"), n(1, 5, "melody"), lyric="the"),
            ev(14, 2, n(1, 3, "melody"), lyric="bones"),
        ],
    ))

    # M33: Em -> Am7 -> Pickup "I don't want to" (0h3p0)
    m.append(Measure(
        bar=33,
        dynamic=0.98,
        chords=[(0, "Em"), (6, "Am7")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 0, "melody")),
            ev(2, 1, n(5, 2, "inner"), n(2, 0, "inner")),
            ev(3, 1, n(1, 0, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 3, "melody")),
            ev(6, 1, n(5, 0, "bass")),
            ev(7, 1, n(1, 0, "melody")),
            ev(8, 2, n(4, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(5, 0, "bass"), n(1, 0, "melody")),
            ev(12, 1, n(6, 0, "bass"), n(1, 0, "melody"), lyric="I"),
            ev(13, 1, n(1, 0, "melody"), lyric="don't", link_tech="H"),
            ev(14, 1, n(1, 3, "melody"), lyric="want", link_tech="P"),
            ev(15, 1, n(1, 0, "melody"), lyric="to"),
        ],
    ))

    # M34: Cmaj7 -> D (timed slide 5/7)
    m.append(Measure(
        bar=34,
        dynamic=0.98,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(1, 5, "melody"), lyric="go"),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 5, "melody"), lyric="through"),
            ev(6, 2, n(1, 3, "melody"), lyric="that"),
            ev(8, 2, n(4, 0, "bass"), n(1, 5, "melody"), lyric="e-", link_tech="S"),
            ev(10, 2, n(1, 7, "melody"), lyric="-ver"),
            ev(12, 2, n(6, 0, "slap"), n(5, 0, "bass"), n(1, 5, "melody"), lyric="a-"),
            ev(14, 2, n(1, 5, "melody")),
        ],
    ))

    # M35: Em -> Bm7 -> Pickup "So cry no"
    m.append(Measure(
        bar=35,
        dynamic=0.98,
        chords=[(0, "Em"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 5, "melody"), lyric="-gain"),
            ev(2, 2, n(5, 2, "inner"), n(1, 3, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(4, 2, "inner"), n(1, 0, "melody")),
            ev(6, 2, n(2, 0, "inner")),
            ev(8, 2, n(5, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(1, 3, "melody"), lyric="So"),
            ev(12, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 2, "melody"), lyric="cry"),
            ev(14, 1, n(2, 0, "inner")),
            ev(15, 1, n(1, 0, "melody"), lyric="no"),
        ],
    ))

    # =========================================================================
    # [Chorus II & Outro] "So cry no more, oh my beloved..." (M36 - M44)
    # =========================================================================
    # M36: Cmaj7 -> D
    m.append(Measure(
        bar=36,
        section="Chorus II & Outro",
        dynamic=1.02,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(3, 0, "inner"), n(1, 0, "melody"), lyric="more", arpeggio=True),
            ev(2, 2, n(3, 0, "inner"), n(2, 3, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(4, 2, "inner"), n(2, 1, "melody")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(4, 0, "bass"), n(1, 5, "melody"), lyric="oh"),
            ev(10, 2, n(5, 0, "bass"), n(1, 3, "melody"), lyric="my"),
            ev(12, 2, n(6, 0, "slap"), n(4, 0, "bass"), n(1, 2, "melody"), lyric="be-"),
            ev(14, 2, n(2, 3, "melody"), lyric="-lo-"),
        ],
    ))

    # M37: Em -> Bm7 -> Pickup "Go ahead"
    m.append(Measure(
        bar=37,
        dynamic=1.01,
        chords=[(0, "Em"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 0, "melody"), lyric="-ved"),
            ev(2, 2, n(5, 2, "inner"), n(2, 0, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(4, 2, "inner"), n(1, 0, "melody")),
            ev(6, 2, n(1, 2, "melody")),
            ev(8, 2, n(5, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(1, 3, "melody"), lyric="Go"),
            ev(12, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 2, "melody"), lyric="a-"),
            ev(14, 1, n(2, 0, "inner")),
            ev(15, 1, n(1, 0, "melody"), lyric="-head"),
        ],
    ))

    # M38: Cmaj7 -> D
    m.append(Measure(
        bar=38,
        dynamic=1.02,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(1, 0, "melody")),
            ev(2, 2, n(3, 0, "inner"), n(2, 3, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(4, 2, "inner"), n(2, 1, "melody")),
            ev(6, 1, n(1, 0, "melody"), lyric="be", link_tech="H"),
            ev(7, 1, n(1, 2, "melody"), lyric="proud"),
            ev(8, 2, n(4, 0, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(5, 0, "bass"), n(1, 0, "melody"), lyric="and"),
            ev(12, 2, n(6, 0, "slap"), n(4, 0, "bass"), n(2, 3, "melody"), lyric="fight"),
            ev(14, 1, n(1, 5, "melody"), lyric="it", link_tech="P"),
            ev(15, 1, n(1, 3, "melody"), lyric="out"),
        ],
    ))

    # M39: Em -> Bm7 -> Pickup "You are the"
    m.append(Measure(
        bar=39,
        dynamic=1.01,
        chords=[(0, "Em"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 3, "melody")),
            ev(2, 2, n(5, 2, "inner"), n(2, 0, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(4, 2, "inner"), n(1, 0, "melody")),
            ev(6, 2, n(1, 2, "melody")),
            ev(8, 2, n(5, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(1, 3, "melody"), lyric="You"),
            ev(12, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 2, "melody"), lyric="are"),
            ev(14, 1, n(2, 0, "inner")),
            ev(15, 1, n(1, 0, "melody"), lyric="the"),
        ],
    ))

    # M40: Cmaj7 -> D
    m.append(Measure(
        bar=40,
        dynamic=1.02,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(3, 0, "inner"), n(1, 0, "melody"), lyric="one", arpeggio=True),
            ev(2, 2, n(3, 0, "inner"), n(2, 3, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(4, 2, "inner"), n(2, 1, "melody")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(4, 0, "bass"), n(1, 5, "melody"), lyric="a"),
            ev(10, 2, n(5, 0, "bass"), n(1, 3, "melody"), lyric="ri-"),
            ev(12, 2, n(6, 0, "slap"), n(4, 0, "bass"), n(1, 2, "melody"), lyric="-sing"),
            ev(14, 2, n(2, 3, "melody")),
        ],
    ))

    # M41: Em -> Bm7 -> Climax Pickup "You guide"
    m.append(Measure(
        bar=41,
        dynamic=1.02,
        chords=[(0, "Em"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 0, "melody"), lyric="star"),
            ev(2, 2, n(5, 2, "inner"), n(2, 0, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(4, 2, "inner"), n(1, 0, "melody")),
            ev(6, 2, n(1, 2, "melody")),
            ev(8, 2, n(5, 2, "bass"), n(1, 2, "melody")),
            ev(10, 2, n(1, 3, "melody")),
            ev(12, 2, n(6, 0, "slap"), n(3, 0, "inner"), n(1, 2, "melody")),
            ev(14, 1, n(1, 3, "melody"), lyric="You", link_tech="H"),
            ev(15, 1, n(1, 5, "melody"), lyric="guide"),
        ],
    ))

    # M42: Cmaj7 -> D
    m.append(Measure(
        bar=42,
        dynamic=1.00,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(1, 5, "melody")),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(4, 2, "inner"), n(2, 1, "melody")),
            ev(6, 2, n(1, 7, "melody", grace_from=5), lyric="us"),
            ev(8, 2, n(4, 0, "bass"), n(1, 7, "melody"), lyric="far"),
            ev(10, 2, n(5, 0, "bass"), n(1, 0, "melody")),
            ev(12, 2, n(6, 0, "slap"), n(4, 0, "bass"), n(2, 3, "melody")),
            ev(14, 1, n(1, 3, "melody"), lyric="to", link_tech="P"),
            ev(15, 1, n(1, 2, "melody")),
        ],
    ))

    # M43: Em -> Em9 closing harp arpeggio & harmonics
    m.append(Measure(
        bar=43,
        dynamic=0.90,
        chords=[(0, "Em"), (8, "Em9")],
        events=[
            ev(0, 2, n(6, 0, "bass"), n(1, 2, "melody"), lyric="home"),
            ev(2, 2, n(5, 2, "inner"), n(2, 0, "inner")),
            ev(4, 2, n(4, 2, "inner"), n(1, 0, "melody")),
            ev(6, 2, n(1, 2, "melody")),
            ev(8, 2, n(3, 12, "melody", harmonic=True)),
            ev(10, 2, n(2, 12, "inner", harmonic=True)),
            ev(12, 2, n(6, 0, "bass"), n(2, 8, "inner"), n(1, 7, "melody"), arpeggio=True),
            ev(14, 2, n(1, 12, "melody", harmonic=True)),
        ],
    ))

    # M44: Em Final Whole-Note Rolled Chord
    m.append(Measure(
        bar=44,
        dynamic=0.86,
        chords=[(0, "Em")],
        events=[
            ev(
                0,
                16,
                n(6, 0, "bass"),
                n(5, 2, "inner"),
                n(4, 2, "inner"),
                n(3, 0, "inner"),
                n(2, 0, "inner"),
                n(1, 0, "melody"),
                fermata=True,
                arpeggio=True,
            ),
        ],
    ))

    return m


VALID_DURS = {1, 2, 3, 4, 6, 8, 12, 16}


def validate_score(measures: Optional[List[Measure]] = None) -> Dict[str, int]:
    """Validate meter, string exclusivity, fret span <= 3, key, voice-leading, and all fingerstyle techniques."""
    if measures is None:
        measures = build_measures()

    errors: List[str] = []
    tech_counts: Dict[str, int] = {
        "H": 0,
        "P": 0,
        "S": 0,
        "arpeggio": 0,
        "harmonic": 0,
        "palm_mute": 0,
        "slap": 0,
    }

    if len(measures) != 45:
        errors.append(f"Expected 45 measures (M00..M44), got {len(measures)}")

    active_melody_midi: Optional[int] = None

    for idx, meas in enumerate(measures):
        if meas.bar != idx:
            errors.append(f"Measure index mismatch: expected bar {idx}, got {meas.bar}")

        if idx == 0:
            expected_start, expected_end, expected_sum = 12, 16, 4
        else:
            expected_start, expected_end, expected_sum = 0, 16, 16

        cursor = expected_start
        dur_sum = 0
        for ev_idx, e in enumerate(meas.events):
            if e.slot != cursor:
                errors.append(f"M{meas.bar:02d}: expected slot {cursor}, got {e.slot}")
            if e.dur not in VALID_DURS:
                errors.append(f"M{meas.bar:02d} slot {e.slot}: invalid LilyPond duration {e.dur}")
            cursor += e.dur
            dur_sum += e.dur

            if e.rest:
                active_melody_midi = None
                if e.notes:
                    errors.append(f"M{meas.bar:02d} slot {e.slot}: rest event has notes")
                if e.arpeggio or e.link_tech:
                    errors.append(f"M{meas.bar:02d} slot {e.slot}: rest cannot have arpeggio/link_tech")
                continue

            if not e.notes:
                errors.append(f"M{meas.bar:02d} slot {e.slot}: non-rest event has no notes")
                continue

            if e.arpeggio:
                tech_counts["arpeggio"] += 1
                if len(e.notes) < 2:
                    errors.append(f"M{meas.bar:02d} slot {e.slot}: arpeggio requires >=2 notes")

            strings = [nt.string for nt in e.notes]
            if len(strings) != len(set(strings)):
                errors.append(f"M{meas.bar:02d} slot {e.slot}: duplicate strings {strings}")

            pitched_notes = [nt for nt in e.notes if nt.role != "slap"]
            mel_notes = [nt for nt in pitched_notes if nt.role == "melody"]
            if mel_notes:
                if any(nt.harmonic for nt in mel_notes):
                    active_melody_midi = None
                else:
                    active_melody_midi = max(nt.concert_midi for nt in mel_notes)

            if meas.bar < 44 and active_melody_midi is not None:
                for nt in pitched_notes:
                    if nt.role in ("bass", "inner") and not nt.harmonic and nt.concert_midi > active_melody_midi:
                        errors.append(
                            f"M{meas.bar:02d} slot {e.slot}: voice crossing — {nt.role} "
                            f"({nt.string},{nt.fret}) {nt.pitch_name} ({nt.concert_midi}) > "
                            f"melody ({active_melody_midi})"
                        )
            for nt in e.notes:
                if nt.string not in OPEN_TUNING_NO_CAPO:
                    errors.append(f"M{meas.bar:02d} slot {e.slot}: invalid string {nt.string}")
                if nt.role == "slap":
                    tech_counts["slap"] += 1
                    continue
                if not (0 <= nt.fret <= 15):
                    errors.append(f"M{meas.bar:02d} slot {e.slot}: fret out of range {nt.fret}")
                pc = nt.concert_midi % 12
                if pc not in DIATONIC_PCS:
                    errors.append(
                        f"M{meas.bar:02d} slot {e.slot}: non-diatonic note ({nt.string}, {nt.fret}) = {nt.pitch_name}"
                    )
                if nt.harmonic:
                    tech_counts["harmonic"] += 1
                    if nt.fret != 12:
                        errors.append(f"M{meas.bar:02d} slot {e.slot}: natural harmonic expects fret 12, got {nt.fret}")
                if nt.palm_mute:
                    tech_counts["palm_mute"] += 1
                if nt.grace_from is not None:
                    tech_counts["S"] += 1
                    if not (1 <= nt.grace_from <= 15):
                        errors.append(f"M{meas.bar:02d} slot {e.slot}: invalid grace_from {nt.grace_from}")
                    grace_midi = OPEN_TUNING_NO_CAPO[nt.string] + CAPO + nt.grace_from
                    if (grace_midi % 12) not in DIATONIC_PCS:
                        errors.append(f"M{meas.bar:02d} slot {e.slot}: non-diatonic grace_from {nt.grace_from}")
                    if abs(nt.fret - nt.grace_from) > 3 or nt.fret == nt.grace_from:
                        errors.append(f"M{meas.bar:02d} slot {e.slot}: invalid grace slide {nt.grace_from}->{nt.fret}")

            fretted = [nt.fret for nt in pitched_notes if nt.fret > 0 and not nt.harmonic]
            if fretted and (max(fretted) - min(fretted) > 3):
                errors.append(f"M{meas.bar:02d} slot {e.slot}: fret span > 3 ({fretted})")

            if e.link_tech is not None:
                if e.link_tech not in ("H", "P", "S"):
                    errors.append(f"M{meas.bar:02d} slot {e.slot}: invalid link_tech {e.link_tech}")
                else:
                    tech_counts[e.link_tech] += 1
                    if ev_idx + 1 >= len(meas.events):
                        errors.append(f"M{meas.bar:02d} slot {e.slot}: link_tech at end of measure")
                    else:
                        nxt = meas.events[ev_idx + 1]
                        mel_cur = [nt for nt in pitched_notes if nt.role == "melody"]
                        if not mel_cur:
                            errors.append(f"M{meas.bar:02d} slot {e.slot}: link_tech needs melody note")
                        else:
                            s = mel_cur[0].string
                            f0 = mel_cur[0].fret
                            nxt_match = [nt for nt in nxt.notes if nt.string == s and nt.role != "slap"]
                            if not nxt_match:
                                errors.append(
                                    f"M{meas.bar:02d} slot {e.slot}: next event missing string {s} for {e.link_tech}"
                                )
                            else:
                                df = nxt_match[0].fret - f0
                                if e.link_tech == "H" and not (1 <= df <= 3):
                                    errors.append(f"M{meas.bar:02d} slot {e.slot}: H delta {df} not in 1..3")
                                elif e.link_tech == "P" and not (-3 <= df <= -1):
                                    errors.append(f"M{meas.bar:02d} slot {e.slot}: P delta {df} not in -3..-1")
                                elif e.link_tech == "S" and df == 0:
                                    errors.append(f"M{meas.bar:02d} slot {e.slot}: S delta cannot be 0")

        if cursor != expected_end or dur_sum != expected_sum:
            errors.append(
                f"M{meas.bar:02d}: expected coverage [{expected_start}..{expected_end}) sum={expected_sum}, got end={cursor} sum={dur_sum}"
            )

    for k, v in tech_counts.items():
        if v < 1:
            errors.append(f"Expected >=1 occurrence of technique '{k}', got {v}")

    if errors:
        raise ValueError("Score validation failed:\n  " + "\n  ".join(errors))
    return tech_counts


if __name__ == "__main__":
    ms = build_measures()
    counts = validate_score(ms)
    total_notes = sum(len(e.notes) for meas in ms for e in meas.events)
    print(f"OK: {len(ms)} measures (M00..M44), {total_notes} events/notes validated cleanly.")
    print("Techniques:", counts)
