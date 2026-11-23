"""Single source of truth for 《一直很安静》 fingerstyle guitar TAB & audio.

Concert Key: Bb Major / G Minor (1 = Bb / 6 = Gm)
Guitar Tuning: Standard (6E 5A 4D 3G 2B 1E) with Capo on 3rd fret (G/Em shapes)
Time Signature: 4/4 (16 sixteenth-note slots per measure)
Tempo: 106 BPM
Techniques: Hammer-on (H), Pull-off (P), Slide (S), Arpeggio, Harmonics (<12>),
            Palm Mute (P.M.), and Chorus II Thumb Slap (X).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

TITLE = "一直很安静"
ARTIST = "阿桑"
SUBTITLE = "《仙剑奇侠传》插曲 · 阿桑演唱 · 指弹吉他独奏六线谱（技巧编配版）"
COMPOSER = "作词：方文山   作曲：蔡如岳"
ARRANGER_INFO = "原调：1 = Bb / Gm  |  选调：G调指法 (Capo = 3品)  |  标准调弦：6E 5A 4D 3G 2B 1E"
CHORD_LEGEND = "和弦对照 (Capo 3)：G = Bb   D/F# = F/A   Em7 = Gm7   Bm7 = Dm7   Cmaj7 = Ebmaj7   Am7 = Cm7   D = F"
TECHNIQUE_LEGEND_1 = (
    "技巧图例：H = 击弦 (Hammer-on)   P = 勾弦 (Pull-off)   S = 滑音 (Slide)   "
    "波浪线 = 琶音 (Arpeggio)"
)
TECHNIQUE_LEGEND_2 = (
    "<12> = 自然泛音 (Harm.)   P.M. = 右手闷音 (Palm Mute)   X = 拍弦 (Thumb Slap)"
)

TEMPO_BPM = 106
CAPO = 3

# Standard guitar open strings (without capo): 6=E2(40), 5=A2(45), 4=D3(50), 3=G3(55), 2=B3(59), 1=E4(64)
OPEN_TUNING_NO_CAPO: Dict[int, int] = {
    6: 40,
    5: 45,
    4: 50,
    3: 55,
    2: 59,
    1: 64,
}

# Bb Major / G Minor diatonic pitch classes: Bb(10), C(0), D(2), Eb(3), F(5), G(7), A(9)
DIATONIC_PCS = {10, 0, 2, 3, 5, 7, 9}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass(frozen=True)
class NoteEvent:
    string: int  # 1..6 (1 is highest E, 6 is lowest E)
    fret: int    # TAB fret relative to Capo 3 (0 = open at capo 3)
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


def _intro_cmaj7_d(bar: int, dynamic: float, section: Optional[str] = None) -> Measure:
    """Intro motif: 1. 1_ | 1_ 7, 1_~ over Cmaj7 -> D."""
    return Measure(
        bar=bar,
        section=section,
        dynamic=dynamic,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(4, 2, "inner"), n(3, 0, "melody"), arpeggio=True),
            ev(2, 2, n(4, 0, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(3, 0, "melody")),
            ev(8, 2, n(4, 0, "bass"), n(3, 0, "melody")),
            ev(10, 2, n(4, 4, "melody")),
            ev(12, 2, n(5, 0, "inner")),
            ev(14, 2, n(3, 0, "melody")),
        ],
    )


def _verse_g_dfis(
    bar: int, dynamic: float, lyrics: Tuple[str, str, str, str, str], section: Optional[str] = None
) -> Measure:
    """Verse opening line: 3 - 5 2 | - - 3 1~ over G -> D/F#."""
    l0, l1, l2, l3, l4 = lyrics
    return Measure(
        bar=bar,
        section=section,
        dynamic=dynamic,
        chords=[(0, "G"), (8, "D/F#")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(3, 0, "inner"), n(2, 0, "melody"), lyric=l0, arpeggio=True),
            ev(2, 2, n(4, 0, "inner")),
            ev(4, 2, n(2, 3, "melody"), lyric=l1),
            ev(6, 2, n(3, 2, "melody"), lyric=l2),
            ev(8, 2, n(6, 2, "bass")),
            ev(10, 2, n(4, 0, "inner")),
            ev(12, 2, n(2, 0, "melody"), lyric=l3),
            ev(14, 2, n(3, 0, "melody"), lyric=l4),
        ],
    )


def _verse_sync_g_dfis(
    bar: int, dynamic: float, lyrics: Tuple[str, str, str, str, str]
) -> Measure:
    """Syncopated Verse line: 3 - 5 2 | - - 3. 1= over G -> D/F#."""
    l0, l1, l2, l3, l4 = lyrics
    return Measure(
        bar=bar,
        dynamic=dynamic,
        chords=[(0, "G"), (8, "D/F#")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(3, 0, "inner"), n(2, 0, "melody"), lyric=l0, arpeggio=True),
            ev(2, 2, n(4, 0, "inner")),
            ev(4, 2, n(2, 3, "melody"), lyric=l1),
            ev(6, 2, n(3, 2, "melody"), lyric=l2),
            ev(8, 2, n(6, 2, "bass")),
            ev(10, 2, n(4, 0, "inner")),
            ev(12, 3, n(2, 0, "melody"), lyric=l3),
            ev(15, 1, n(3, 0, "melody"), lyric=l4),
        ],
    )


def _verse_em7_bm7_walk(bar: int, dynamic: float, lyrics: Tuple[str, str, str, str, str, str]) -> Measure:
    """Verse descending line: ~ - - 1=2= | 4_ 3_ 2_ 1_ over Em7 -> Bm7."""
    l0, l1, l2, l3, l4, l5 = lyrics
    return Measure(
        bar=bar,
        dynamic=dynamic,
        chords=[(0, "Em7"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 1, n(3, 0, "melody"), lyric=l0, link_tech="H"),
            ev(7, 1, n(3, 2, "melody"), lyric=l1),
            ev(8, 2, n(5, 2, "bass"), n(2, 1, "melody"), lyric=l2, link_tech="P"),
            ev(10, 2, n(2, 0, "melody"), lyric=l3),
            ev(12, 2, n(3, 2, "melody"), lyric=l4, link_tech="P"),
            ev(14, 2, n(3, 0, "melody"), lyric=l5),
        ],
    )


def _chorus_cmaj7_d_line1(
    bar: int, dynamic: float, *, slap: bool = False, section: Optional[str] = None
) -> Measure:
    """Chorus hook: 1' - 5_ 6_ | - - 5_ 3_ ("一直很安静") over Cmaj7 -> D."""
    slot4_notes = (n(6, 0, "slap"), n(2, 3, "melody")) if slap else (n(2, 3, "melody"),)
    slot12_notes = (n(6, 0, "slap"), n(2, 3, "melody")) if slap else (n(2, 3, "melody"),)
    return Measure(
        bar=bar,
        section=section,
        dynamic=dynamic,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(4, 2, "inner"), n(1, 3, "melody"), lyric="一", arpeggio=True),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, *slot4_notes, lyric="直"),
            ev(6, 2, n(1, 0, "melody"), lyric="很"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, *slot12_notes, lyric="安"),
            ev(14, 2, n(2, 0, "melody"), lyric="静"),
        ],
    )


def _chorus_em7_bm7_line2(
    bar: int, dynamic: float, lyrics: Tuple[str, str, str, str, str], *, slap: bool = False
) -> Measure:
    """Chorus reply: ~ - - 3_ | 4_ 3_ 2_ 1_ over Em7 -> Bm7."""
    l0, l1, l2, l3, l4 = lyrics
    slot4_notes = (n(6, 0, "slap"), n(4, 2, "inner")) if slap else (n(4, 2, "inner"),)
    if slap:
        ev12 = ev(12, 2, n(6, 0, "slap"), n(3, 2, "melody"), lyric=l3)
    else:
        ev12 = ev(12, 2, n(3, 2, "melody"), lyric=l3, link_tech="P")
    return Measure(
        bar=bar,
        dynamic=dynamic,
        chords=[(0, "Em7"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, *slot4_notes),
            ev(6, 2, n(2, 0, "melody"), lyric=l0),
            ev(8, 2, n(5, 2, "bass"), n(2, 1, "melody"), lyric=l1, link_tech="P"),
            ev(10, 2, n(2, 0, "melody"), lyric=l2),
            ev12,
            ev(14, 2, n(3, 0, "melody"), lyric=l4),
        ],
    )


def build_measures() -> List[Measure]:
    """Return the 68 measures (M01..M68) of 《一直很安静》 with fingerstyle techniques."""
    m: List[Measure] = []

    # =========================================================================
    # [Intro] Iconic Acoustic Intro (M01 - M08)
    # =========================================================================
    # M01: Cmaj7 -> D
    m.append(_intro_cmaj7_d(1, 0.84, section="Intro"))

    # M02: G (with bell answer 5. using 1s3 grace slide)
    m.append(Measure(
        bar=2,
        dynamic=0.84,
        chords=[(0, "G")],
        events=[
            ev(0, 2, n(6, 3, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(4, 2, "inner")),
            ev(8, 2, n(4, 0, "inner")),
            ev(10, 2, n(2, 3, "melody", grace_from=1)),
            ev(12, 2, n(4, 0, "inner")),
            ev(14, 2, n(3, 0, "inner")),
        ],
    ))

    # M03: Cmaj7 -> D
    m.append(_intro_cmaj7_d(3, 0.85))

    # M04: G -> G/B
    m.append(Measure(
        bar=4,
        dynamic=0.85,
        chords=[(0, "G"), (8, "G/B")],
        events=[
            ev(0, 2, n(6, 3, "bass")),
            ev(2, 2, n(4, 0, "inner")),
            ev(4, 4, n(5, 3, "bass")),
            ev(8, 2, n(5, 2, "bass")),
            ev(10, 2, n(4, 0, "inner")),
            ev(12, 2, n(4, 2, "inner")),
            ev(14, 2, n(4, 0, "inner")),
        ],
    ))

    # M05: Cmaj7 -> D
    m.append(_intro_cmaj7_d(5, 0.86))

    # M06: Em7 -> Bm7 ((1). 1_ | 1_ 2_ 3)
    m.append(Measure(
        bar=6,
        dynamic=0.86,
        chords=[(0, "Em7"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(3, 0, "melody")),
            ev(8, 2, n(5, 2, "bass"), n(3, 0, "melody"), link_tech="H"),
            ev(10, 2, n(3, 2, "melody")),
            ev(12, 2, n(2, 0, "melody")),
            ev(14, 2, n(4, 0, "inner")),
        ],
    ))

    # M07: Am7 (4. 4_ | 4_ 3 2_~)
    m.append(Measure(
        bar=7,
        dynamic=0.86,
        chords=[(0, "Am7")],
        events=[
            ev(0, 2, n(5, 0, "bass"), n(4, 2, "inner"), n(2, 1, "melody"), arpeggio=True),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(3, 0, "inner")),
            ev(6, 2, n(2, 1, "melody")),
            ev(8, 2, n(5, 0, "bass"), n(2, 1, "melody"), link_tech="P"),
            ev(10, 2, n(2, 0, "melody")),
            ev(12, 2, n(4, 2, "inner")),
            ev(14, 2, n(3, 2, "melody")),
        ],
    ))

    # M08: Dsus4 -> D (leading into Verse I)
    m.append(Measure(
        bar=8,
        dynamic=0.85,
        chords=[(0, "Dsus4"), (8, "D")],
        events=[
            ev(0, 2, n(4, 0, "bass")),
            ev(2, 2, n(5, 0, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(4, 4, "inner")),
            ev(8, 2, n(5, 0, "bass")),
            ev(10, 2, n(4, 4, "inner")),
            ev(12, 4, n(4, 0, "bass")),
        ],
    ))

    # =========================================================================
    # [Verse I] "空荡的街景..." (M09 - M24)
    # =========================================================================
    # M09: G -> D/F# ("空荡的街景")
    m.append(_verse_g_dfis(9, 0.89, ("空", "荡", "的", "街", "景"), section="Verse I"))

    # M10: Em7 -> Bm7 ("...想找")
    m.append(Measure(
        bar=10,
        dynamic=0.88,
        chords=[(0, "Em7"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(5, 2, "bass")),
            ev(10, 2, n(4, 0, "inner")),
            ev(12, 2, n(3, 0, "melody"), lyric="想"),
            ev(14, 2, n(4, 4, "melody"), lyric="找"),
        ],
    ))

    # M11: Cmaj7 -> D ("个人...放")
    m.append(Measure(
        bar=11,
        dynamic=0.89,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(3, 0, "melody"), lyric="个", arpeggio=True),
            ev(2, 2, n(3, 0, "melody"), lyric="人"),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(5, 3, "inner")),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(5, 0, "inner")),
            ev(12, 2, n(4, 0, "inner")),
            ev(14, 2, n(2, 1, "melody"), lyric="放"),
        ],
    ))

    # M12: Dsus4 -> D ("感情")
    m.append(Measure(
        bar=12,
        dynamic=0.88,
        chords=[(0, "Dsus4"), (8, "D")],
        events=[
            ev(0, 2, n(4, 0, "bass"), n(2, 0, "melody"), lyric="感", arpeggio=True),
            ev(2, 2, n(5, 0, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(3, 2, "melody"), lyric="情"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(5, 0, "inner")),
            ev(12, 2, n(4, 4, "inner")),
            ev(14, 2, n(4, 0, "inner")),
        ],
    ))

    # M13: G -> D/F# ("做这种决定")
    m.append(_verse_g_dfis(13, 0.89, ("做", "这", "种", "决", "定")))

    # M14: Em7 -> Bm7 ("是寂寞")
    m.append(Measure(
        bar=14,
        dynamic=0.89,
        chords=[(0, "Em7"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(5, 2, "bass")),
            ev(10, 2, n(4, 0, "melody"), lyric="是"),
            ev(12, 2, n(3, 0, "melody"), lyric="寂", link_tech="H"),
            ev(14, 2, n(3, 2, "melody"), lyric="寞"),
        ],
    ))

    # M15: Cmaj7 -> D ("与我为邻")
    m.append(Measure(
        bar=15,
        dynamic=0.89,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(3, 0, "melody"), arpeggio=True),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(5, 3, "inner")),
            ev(6, 1, n(3, 0, "melody"), lyric="与"),
            ev(7, 1, n(3, 0, "melody"), lyric="我"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(5, 0, "inner")),
            ev(12, 2, n(4, 4, "melody"), lyric="为"),
            ev(14, 2, n(3, 0, "melody"), lyric="邻"),
        ],
    ))

    # M16: G (Phrase cadence fill, page 1 break)
    m.append(Measure(
        bar=16,
        dynamic=0.87,
        chords=[(0, "G")],
        events=[
            ev(0, 2, n(6, 3, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(6, 3, "bass")),
            ev(10, 2, n(4, 2, "inner")),
            ev(12, 4, n(4, 0, "inner")),
        ],
    ))

    # M17: G -> D/F# ("我们的爱情")
    m.append(_verse_g_dfis(17, 0.90, ("我", "们", "的", "爱", "情")))

    # M18: Em7 -> Bm7 ("像你")
    m.append(Measure(
        bar=18,
        dynamic=0.90,
        chords=[(0, "Em7"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(5, 2, "bass")),
            ev(10, 2, n(4, 0, "inner")),
            ev(12, 2, n(3, 0, "melody"), lyric="像"),
            ev(14, 1, n(3, 0, "melody"), lyric="你", link_tech="H"),
            ev(15, 1, n(3, 2, "melody")),
        ],
    ))

    # M19: Cmaj7 -> D ("路过的风景")
    m.append(Measure(
        bar=19,
        dynamic=0.92,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(4, 2, "inner"), n(1, 0, "melody"), lyric="路", arpeggio=True),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(1, 0, "melody"), lyric="过"),
            ev(6, 2, n(1, 0, "melody"), lyric="的"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 3, n(2, 3, "melody"), lyric="风"),
            ev(15, 1, n(2, 0, "melody"), lyric="景"),
        ],
    ))

    # M20: G (3_ 4_ 3_ 2_ vocal sigh)
    m.append(Measure(
        bar=20,
        dynamic=0.89,
        chords=[(0, "G")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(2, 0, "melody")),
            ev(2, 2, n(2, 1, "melody"), link_tech="P"),
            ev(4, 2, n(2, 0, "melody")),
            ev(6, 2, n(3, 2, "melody")),
            ev(8, 2, n(6, 3, "bass")),
            ev(10, 2, n(4, 0, "inner")),
            ev(12, 2, n(5, 2, "inner")),
            ev(14, 2, n(4, 0, "inner")),
        ],
    ))

    # M21: G -> D/F# ("一直在进行")
    m.append(_verse_sync_g_dfis(21, 0.90, ("一", "直", "在", "进", "行")))

    # M22: Em7 -> Bm7 ("脚步却从来不")
    m.append(_verse_em7_bm7_walk(22, 0.90, ("脚", "步", "却", "从", "来", "不")))

    # M23: Cmaj7 -> Am7 ("会为我而")
    m.append(Measure(
        bar=23,
        dynamic=0.90,
        chords=[(0, "Cmaj7"), (8, "Am7")],
        events=[
            ev(0, 2, n(5, 3, "bass")),
            ev(2, 2, n(3, 0, "melody"), lyric="会"),
            ev(4, 2, n(4, 4, "melody"), lyric="为"),
            ev(6, 2, n(5, 3, "inner")),
            ev(8, 2, n(5, 0, "bass")),
            ev(10, 2, n(4, 2, "inner")),
            ev(12, 2, n(3, 0, "melody"), lyric="我"),
            ev(14, 2, n(3, 0, "melody"), lyric="而"),
        ],
    ))

    # M24: Dsus4 -> D ("停" half-cadence on 2)
    m.append(Measure(
        bar=24,
        dynamic=0.91,
        chords=[(0, "Dsus4"), (8, "D")],
        events=[
            ev(0, 2, n(4, 0, "bass")),
            ev(2, 2, n(5, 0, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(3, 2, "melody"), lyric="停"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(5, 0, "inner")),
            ev(12, 2, n(4, 4, "inner")),
            ev(14, 2, n(4, 0, "inner")),
        ],
    ))

    # =========================================================================
    # [Chorus I] "给你的爱一直很安静..." (M25 - M34)
    # =========================================================================
    # M25: G -> G/B (Pickup "给你的爱")
    m.append(Measure(
        bar=25,
        section="Chorus I",
        dynamic=0.93,
        chords=[(0, "G"), (8, "G/B")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(4, 0, "inner"), n(2, 0, "melody"), arpeggio=True),
            ev(2, 2, n(4, 0, "inner")),
            ev(4, 2, n(3, 0, "inner")),
            ev(6, 2, n(4, 0, "inner")),
            ev(8, 2, n(5, 2, "bass"), n(2, 0, "melody"), lyric="给"),
            ev(10, 2, n(2, 3, "melody"), lyric="你"),
            ev(12, 2, n(1, 3, "melody"), lyric="的", link_tech="S"),
            ev(14, 2, n(1, 2, "melody"), lyric="爱"),
        ],
    ))

    # M26: Cmaj7 -> D ("一直很安静")
    m.append(_chorus_cmaj7_d_line1(26, 0.95, slap=False))

    # M27: Em7 -> Bm7 ("来交换你偶")
    m.append(_chorus_em7_bm7_line2(27, 0.94, ("来", "交", "换", "你", "偶"), slap=False))

    # M28: Cmaj7 -> D ("尔给的关心")
    m.append(Measure(
        bar=28,
        dynamic=0.94,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass")),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(2, 3, "melody"), lyric="尔"),
            ev(6, 2, n(2, 3, "melody"), lyric="给"),
            ev(8, 2, n(4, 0, "bass"), n(2, 3, "melody"), lyric="的"),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(3, 2, "melody"), lyric="关"),
            ev(14, 2, n(2, 0, "melody"), lyric="心"),
        ],
    ))

    # M29: G -> G/B (Pickup "明明是三")
    m.append(Measure(
        bar=29,
        dynamic=0.94,
        chords=[(0, "G"), (8, "G/B")],
        events=[
            ev(0, 2, n(6, 3, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(5, 2, "bass"), n(2, 0, "melody"), lyric="明"),
            ev(10, 2, n(2, 3, "melody"), lyric="明"),
            ev(12, 2, n(1, 3, "melody"), lyric="是"),
            ev(14, 2, n(1, 2, "melody"), lyric="三"),
        ],
    ))

    # M30: Cmaj7 -> D ("个人的电影")
    m.append(Measure(
        bar=30,
        dynamic=0.96,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(
                0, 2,
                n(5, 3, "bass"), n(4, 2, "inner"),
                n(1, 3, "melody", grace_from=2),
                lyric="个",
                arpeggio=True,
            ),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(2, 3, "melody"), lyric="人"),
            ev(6, 2, n(1, 0, "melody"), lyric="的"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(2, 3, "melody"), lyric="电"),
            ev(14, 2, n(2, 0, "melody"), lyric="影"),
        ],
    ))

    # M31: Em7 -> Bm7 ("我却始终不")
    m.append(_chorus_em7_bm7_line2(31, 0.94, ("我", "却", "始", "终", "不"), slap=False))

    # M32: Cmaj7 -> D ("能有姓")
    m.append(Measure(
        bar=32,
        dynamic=0.93,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass")),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(3, 0, "melody"), lyric="能"),
            ev(6, 2, n(4, 4, "melody"), lyric="有"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(4, 4, "inner")),
            ev(12, 2, n(3, 0, "melody"), lyric="姓"),
            ev(14, 2, n(3, 0, "melody")),
        ],
    ))

    # M33: Dsus4 -> D (suspended cadence)
    m.append(Measure(
        bar=33,
        dynamic=0.92,
        chords=[(0, "Dsus4"), (8, "D")],
        events=[
            ev(0, 2, n(4, 0, "bass")),
            ev(2, 2, n(5, 0, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(3, 2, "melody")),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(5, 0, "inner")),
            ev(12, 2, n(4, 4, "inner")),
            ev(14, 2, n(3, 0, "melody"), lyric="名"),
        ],
    ))

    # M34: G ("名" + Natural Bell Harmonics <12>)
    m.append(Measure(
        bar=34,
        dynamic=0.88,
        chords=[(0, "G")],
        events=[
            ev(0, 2, n(6, 3, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(4, 12, "inner", harmonic=True)),
            ev(10, 2, n(3, 12, "melody", harmonic=True)),
            ev(12, 4, n(2, 12, "melody", harmonic=True)),
        ],
    ))

    # =========================================================================
    # [Interlude] Palm-Muted Pulse & Lyrical Crescendo (M35 - M42)
    # M35..M38: Palm Muted bass & inner accompaniment (P.M.), opening in M39
    # =========================================================================
    # M35: G (3 3_ 4_~ 2 7_~)
    m.append(Measure(
        bar=35,
        section="Interlude",
        dynamic=0.88,
        chords=[(0, "G")],
        events=[
            ev(0, 2, n(6, 3, "bass", palm_mute=True), n(2, 0, "melody")),
            ev(2, 2, n(4, 0, "inner", palm_mute=True)),
            ev(4, 2, n(2, 0, "melody")),
            ev(6, 2, n(2, 1, "melody")),
            ev(8, 2, n(6, 3, "bass", palm_mute=True)),
            ev(10, 2, n(3, 2, "melody")),
            ev(12, 2, n(4, 0, "inner", palm_mute=True)),
            ev(14, 2, n(1, 2, "melody")),
        ],
    ))

    # M36: D (7_ 5 2_~ 4 2_)
    m.append(Measure(
        bar=36,
        dynamic=0.89,
        chords=[(0, "D")],
        events=[
            ev(0, 2, n(4, 0, "bass", palm_mute=True)),
            ev(2, 2, n(2, 3, "melody")),
            ev(4, 2, n(3, 2, "inner", palm_mute=True)),
            ev(6, 2, n(3, 2, "melody")),
            ev(8, 2, n(4, 0, "bass", palm_mute=True)),
            ev(10, 2, n(2, 1, "melody")),
            ev(12, 2, n(4, 4, "inner", palm_mute=True)),
            ev(14, 2, n(3, 2, "melody")),
        ],
    ))

    # M37: G (3 3_ 2_~ 4 5_)
    m.append(Measure(
        bar=37,
        dynamic=0.90,
        chords=[(0, "G")],
        events=[
            ev(0, 2, n(6, 3, "bass", palm_mute=True), n(2, 0, "melody")),
            ev(2, 2, n(4, 0, "inner", palm_mute=True)),
            ev(4, 2, n(2, 0, "melody")),
            ev(6, 2, n(3, 2, "melody")),
            ev(8, 2, n(6, 3, "bass", palm_mute=True)),
            ev(10, 2, n(2, 1, "melody")),
            ev(12, 2, n(4, 0, "inner", palm_mute=True)),
            ev(14, 2, n(2, 3, "melody")),
        ],
    ))

    # M38: D/F# (5 2_ 5_~ 5. end of P.M. span)
    m.append(Measure(
        bar=38,
        dynamic=0.90,
        chords=[(0, "D/F#")],
        events=[
            ev(0, 2, n(6, 2, "bass", palm_mute=True), n(2, 3, "melody")),
            ev(2, 2, n(4, 0, "inner", palm_mute=True)),
            ev(4, 2, n(3, 2, "melody")),
            ev(6, 2, n(2, 3, "melody")),
            ev(8, 2, n(6, 2, "bass", palm_mute=True)),
            ev(10, 2, n(2, 3, "melody")),
            ev(12, 2, n(4, 0, "inner", palm_mute=True)),
            ev(14, 2, n(5, 0, "inner", palm_mute=True)),
        ],
    ))

    # M39: Am7 (open cresc.: 5_ 4 5_~ 4 1'_)
    m.append(Measure(
        bar=39,
        dynamic=0.92,
        chords=[(0, "Am7")],
        events=[
            ev(0, 2, n(5, 0, "bass"), n(2, 3, "melody"), arpeggio=True),
            ev(2, 2, n(2, 1, "melody")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(2, 3, "melody")),
            ev(8, 2, n(5, 0, "bass")),
            ev(10, 2, n(2, 1, "melody")),
            ev(12, 2, n(4, 2, "inner")),
            ev(14, 2, n(1, 3, "melody")),
        ],
    ))

    # M40: G -> Cmaj7 (4 3_ 4 1 5,_ 1_)
    m.append(Measure(
        bar=40,
        dynamic=0.92,
        chords=[(0, "G"), (8, "Cmaj7")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(2, 1, "melody")),
            ev(2, 2, n(4, 0, "inner")),
            ev(4, 2, n(2, 0, "melody"), link_tech="H"),
            ev(6, 2, n(2, 1, "melody")),
            ev(8, 2, n(5, 3, "bass"), n(4, 2, "inner")),
            ev(10, 2, n(3, 0, "melody")),
            ev(12, 2, n(4, 0, "melody")),
            ev(14, 2, n(3, 0, "melody")),
        ],
    ))

    # M41: G (3 3_ 3_ 3_ 2)
    m.append(Measure(
        bar=41,
        dynamic=0.91,
        chords=[(0, "G")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(3, 0, "inner"), n(2, 0, "melody"), arpeggio=True),
            ev(2, 2, n(4, 0, "inner")),
            ev(4, 2, n(3, 0, "inner")),
            ev(6, 2, n(3, 0, "inner"), n(2, 0, "melody")),
            ev(8, 2, n(6, 3, "bass")),
            ev(10, 2, n(3, 0, "inner"), n(2, 0, "melody")),
            ev(12, 2, n(4, 0, "inner")),
            ev(14, 2, n(3, 2, "melody")),
        ],
    ))

    # M42: D (interlude turnaround)
    m.append(Measure(
        bar=42,
        dynamic=0.90,
        chords=[(0, "D")],
        events=[
            ev(0, 2, n(4, 0, "bass")),
            ev(2, 2, n(5, 0, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(4, 4, "inner")),
            ev(8, 4, n(4, 0, "bass")),
            ev(12, 4, n(5, 0, "inner")),
        ],
    ))

    # =========================================================================
    # [Verse II] "你说爱像云..." (M43 - M50)
    # =========================================================================
    # M43: G -> D/F# ("你说爱像云")
    m.append(_verse_g_dfis(43, 0.90, ("你", "说", "爱", "像", "云"), section="Verse II"))

    # M44: Em7 -> Bm7 ("要自在")
    m.append(Measure(
        bar=44,
        dynamic=0.90,
        chords=[(0, "Em7"), (8, "Bm7")],
        events=[
            ev(0, 2, n(6, 0, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(5, 2, "bass")),
            ev(10, 2, n(3, 0, "melody"), lyric="要", link_tech="H"),
            ev(12, 2, n(3, 2, "melody"), lyric="自", link_tech="P"),
            ev(14, 2, n(3, 0, "melody"), lyric="在"),
        ],
    ))

    # M45: Cmaj7 -> D ("飘浮才美丽")
    m.append(Measure(
        bar=45,
        dynamic=0.92,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass"), n(4, 2, "inner"), n(1, 0, "melody"), lyric="飘", arpeggio=True),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(1, 0, "melody"), lyric="浮"),
            ev(6, 2, n(1, 0, "melody"), lyric="才"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 3, n(2, 3, "melody"), lyric="美"),
            ev(15, 1, n(2, 0, "melody"), lyric="丽"),
        ],
    ))

    # M46: G (lyrical resonance fill)
    m.append(Measure(
        bar=46,
        dynamic=0.89,
        chords=[(0, "G")],
        events=[
            ev(0, 2, n(6, 3, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(6, 3, "bass")),
            ev(10, 2, n(4, 0, "inner")),
            ev(12, 2, n(3, 0, "inner")),
            ev(14, 2, n(4, 0, "inner")),
        ],
    ))

    # M47: G -> D/F# ("我终于相信")
    m.append(_verse_sync_g_dfis(47, 0.91, ("我", "终", "于", "相", "信")))

    # M48: Em7 -> Bm7 ("分手的理由有")
    m.append(_verse_em7_bm7_walk(48, 0.91, ("分", "手", "的", "理", "由", "有")))

    # M49: Cmaj7 -> D ("时候很动")
    m.append(Measure(
        bar=49,
        dynamic=0.92,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass")),
            ev(2, 2, n(3, 0, "melody"), lyric="时"),
            ev(4, 2, n(4, 4, "melody"), lyric="候"),
            ev(6, 2, n(5, 3, "inner")),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(4, 4, "inner")),
            ev(12, 2, n(3, 0, "melody"), lyric="很"),
            ev(14, 2, n(3, 2, "melody"), lyric="动"),
        ],
    ))

    # M50: G -> G/B ("听" + Pickup "给你的爱")
    m.append(Measure(
        bar=50,
        dynamic=0.93,
        chords=[(0, "G"), (8, "G/B")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(3, 0, "melody"), lyric="听", arpeggio=True),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(5, 2, "bass"), n(2, 0, "melody"), lyric="给"),
            ev(10, 2, n(2, 3, "melody"), lyric="你"),
            ev(12, 2, n(1, 3, "melody"), lyric="的"),
            ev(14, 2, n(1, 2, "melody"), lyric="爱"),
        ],
    ))

    # =========================================================================
    # [Chorus II & Outro] High-Energy Groove w/ Thumb Slap (X) (M51 - M68)
    # =========================================================================
    # M51: Cmaj7 -> D ("一直很安静")
    m.append(_chorus_cmaj7_d_line1(51, 0.97, slap=True, section="Chorus II & Outro"))

    # M52: Em7 -> Bm7 ("来交换你偶")
    m.append(_chorus_em7_bm7_line2(52, 0.96, ("来", "交", "换", "你", "偶"), slap=True))

    # M53: Cmaj7 -> D ("尔给的关心")
    m.append(Measure(
        bar=53,
        dynamic=0.96,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass")),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(2, 3, "melody"), lyric="尔"),
            ev(6, 2, n(2, 3, "melody"), lyric="给"),
            ev(8, 2, n(4, 0, "bass"), n(2, 3, "melody"), lyric="的"),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(6, 0, "slap"), n(3, 2, "melody"), lyric="关"),
            ev(14, 2, n(2, 0, "melody"), lyric="心"),
        ],
    ))

    # M54: G -> G/B (Pickup "明明是三")
    m.append(Measure(
        bar=54,
        dynamic=0.96,
        chords=[(0, "G"), (8, "G/B")],
        events=[
            ev(0, 2, n(6, 3, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(4, 0, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(5, 2, "bass"), n(2, 0, "melody"), lyric="明"),
            ev(10, 2, n(2, 3, "melody"), lyric="明"),
            ev(12, 2, n(6, 0, "slap"), n(1, 3, "melody"), lyric="是"),
            ev(14, 2, n(1, 2, "melody"), lyric="三"),
        ],
    ))

    # M55: Cmaj7 -> D ("个人的电影")
    m.append(Measure(
        bar=55,
        dynamic=0.98,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(
                0, 2,
                n(5, 3, "bass"), n(4, 2, "inner"),
                n(1, 3, "melody", grace_from=2),
                lyric="个",
                arpeggio=True,
            ),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(2, 3, "melody"), lyric="人"),
            ev(6, 2, n(1, 0, "melody"), lyric="的"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(6, 0, "slap"), n(2, 3, "melody"), lyric="电"),
            ev(14, 2, n(2, 0, "melody"), lyric="影"),
        ],
    ))

    # M56: Em7 -> Bm7 ("我却始终不")
    m.append(_chorus_em7_bm7_line2(56, 0.97, ("我", "却", "始", "终", "不"), slap=True))

    # M57: Cmaj7 -> D ("能有姓")
    m.append(Measure(
        bar=57,
        dynamic=0.96,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass")),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(3, 0, "melody"), lyric="能"),
            ev(6, 2, n(4, 4, "melody"), lyric="有"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(4, 4, "inner")),
            ev(12, 2, n(6, 0, "slap"), n(3, 0, "melody"), lyric="姓"),
            ev(14, 2, n(3, 2, "melody")),
        ],
    ))

    # M58: G -> G/B ("名" + Pickup "给你的爱")
    m.append(Measure(
        bar=58,
        dynamic=0.97,
        chords=[(0, "G"), (8, "G/B")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(3, 0, "melody"), lyric="名", arpeggio=True),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(4, 0, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(5, 2, "bass"), n(2, 0, "melody"), lyric="给"),
            ev(10, 2, n(2, 3, "melody"), lyric="你"),
            ev(12, 2, n(6, 0, "slap"), n(1, 3, "melody"), lyric="的"),
            ev(14, 2, n(1, 2, "melody"), lyric="爱"),
        ],
    ))

    # M59: Cmaj7 -> D ("一直很安静")
    m.append(_chorus_cmaj7_d_line1(59, 0.98, slap=True))

    # M60: Em7 -> Bm7 ("我从一开始")
    m.append(_chorus_em7_bm7_line2(60, 0.98, ("我", "从", "一", "开", "始"), slap=True))

    # M61: Cmaj7 -> D ("就下定决心" high leap to G4)
    m.append(Measure(
        bar=61,
        dynamic=0.99,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass")),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(6, 0, "slap"), n(2, 3, "melody"), lyric="就"),
            ev(6, 2, n(2, 3, "melody"), lyric="下"),
            ev(8, 2, n(4, 0, "bass"), n(2, 3, "melody"), lyric="定"),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(6, 0, "slap"), n(1, 0, "melody"), lyric="决"),
            ev(14, 2, n(2, 3, "melody"), lyric="心"),
        ],
    ))

    # M62: G -> G/B ("心" 5->3 pull-off + Pickup "以为自己")
    m.append(Measure(
        bar=62,
        dynamic=0.99,
        chords=[(0, "G"), (8, "G/B")],
        events=[
            ev(0, 2, n(6, 3, "bass"), n(2, 3, "melody"), link_tech="P"),
            ev(2, 2, n(2, 0, "melody")),
            ev(4, 2, n(6, 0, "slap"), n(4, 0, "inner")),
            ev(6, 2, n(3, 0, "inner")),
            ev(8, 2, n(5, 2, "bass"), n(2, 0, "melody"), lyric="以"),
            ev(10, 2, n(2, 3, "melody"), lyric="为"),
            ev(12, 2, n(6, 0, "slap"), n(1, 3, "melody"), lyric="自"),
            ev(14, 2, n(1, 2, "melody"), lyric="己"),
        ],
    ))

    # M63: Cmaj7 -> D (Climax: "要的是曾经" 3' -> 2'. 5= -> 3_ 3_)
    m.append(Measure(
        bar=63,
        dynamic=1.00,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(
                0, 2,
                n(6, 8, "bass"), n(3, 0, "inner"), n(2, 0, "inner"),
                n(1, 7, "melody", grace_from=5),
                lyric="要",
                arpeggio=True,
            ),
            ev(2, 2, n(3, 0, "inner")),
            ev(4, 3, n(6, 0, "slap"), n(1, 5, "melody"), lyric="的"),
            ev(7, 1, n(2, 3, "melody"), lyric="是"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(3, 2, "inner")),
            ev(12, 2, n(6, 0, "slap"), n(2, 0, "melody"), lyric="曾"),
            ev(14, 2, n(2, 0, "melody"), lyric="经"),
        ],
    ))

    # M64: Em7 -> Bm7 ("却发现爱一")
    m.append(_chorus_em7_bm7_line2(64, 0.98, ("却", "发", "现", "爱", "一"), slap=True))

    # M65: Cmaj7 -> D ("定要有")
    m.append(Measure(
        bar=65,
        dynamic=0.95,
        chords=[(0, "Cmaj7"), (8, "D")],
        events=[
            ev(0, 2, n(5, 3, "bass")),
            ev(2, 2, n(4, 2, "inner")),
            ev(4, 2, n(3, 0, "melody"), lyric="定"),
            ev(6, 2, n(4, 4, "melody"), lyric="要"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(4, 4, "inner")),
            ev(12, 2, n(3, 0, "melody"), lyric="有"),
            ev(14, 2, n(3, 0, "melody")),
        ],
    ))

    # M66: Dsus4 -> D ("回音" resolving cadence)
    m.append(Measure(
        bar=66,
        dynamic=0.92,
        chords=[(0, "Dsus4"), (8, "D")],
        events=[
            ev(0, 2, n(4, 0, "bass")),
            ev(2, 2, n(5, 0, "inner")),
            ev(4, 2, n(4, 2, "inner")),
            ev(6, 2, n(3, 2, "melody"), lyric="回"),
            ev(8, 2, n(4, 0, "bass")),
            ev(10, 2, n(5, 0, "inner")),
            ev(12, 2, n(4, 4, "inner")),
            ev(14, 2, n(3, 0, "melody"), lyric="音"),
        ],
    ))

    # M67: G -> Cmaj7 (Outro bell harmonics)
    m.append(Measure(
        bar=67,
        dynamic=0.88,
        chords=[(0, "G"), (8, "Cmaj7")],
        events=[
            ev(0, 2, n(6, 3, "bass")),
            ev(2, 2, n(5, 2, "inner")),
            ev(4, 2, n(4, 0, "inner")),
            ev(6, 2, n(5, 2, "inner")),
            ev(8, 2, n(5, 3, "bass")),
            ev(10, 2, n(3, 12, "melody", harmonic=True)),
            ev(12, 2, n(2, 12, "inner", harmonic=True)),
            ev(14, 2, n(1, 12, "melody", harmonic=True)),
        ],
    ))

    # M68: G Final Whole-Note Rolled Chord
    m.append(Measure(
        bar=68,
        dynamic=0.85,
        chords=[(0, "G")],
        events=[
            ev(
                0,
                16,
                n(6, 3, "bass"),
                n(5, 2, "inner"),
                n(4, 0, "inner"),
                n(3, 0, "inner"),
                n(2, 0, "inner"),
                n(1, 3, "melody"),
                fermata=True,
                arpeggio=True,
            ),
        ],
    ))

    return m


VALID_DURS = {1, 2, 3, 4, 6, 8, 12, 16}


def validate_score(measures: Optional[List[Measure]] = None) -> Dict[str, int]:
    """Validate meter, string exclusivity, fret span <= 3, key, voice-leading, and techniques."""
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

    if len(measures) != 68:
        errors.append(f"Expected 68 measures (M01..M68), got {len(measures)}")

    active_melody_midi: Optional[int] = None

    for idx, meas in enumerate(measures):
        expected_bar = idx + 1
        if meas.bar != expected_bar:
            errors.append(f"Measure index mismatch: expected bar {expected_bar}, got {meas.bar}")

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
                elif (
                    meas.bar <= 67
                    and active_melody_midi is not None
                    and nt.role in ("bass", "inner")
                    and nt.concert_midi > active_melody_midi
                ):
                    errors.append(
                        f"M{meas.bar:02d} slot {e.slot}: voice crossing {nt.role} "
                        f"({nt.string},{nt.fret})={nt.concert_midi} > active melody {active_melody_midi}"
                    )
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
    print(f"OK: {len(ms)} measures (M01..M68), {total_notes} events/notes validated cleanly.")
    print("Techniques:", counts)
