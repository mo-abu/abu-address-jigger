"""
Address Jigger
Generates address variants using character-level and word-level transformations.
"""

import sys, csv, io, random, re, os, subprocess
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QFrame, QSpinBox, QStatusBar, QMessageBox,
    QGridLayout, QComboBox, QAbstractItemView, QLineEdit,
    QTabWidget, QTextEdit, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont


# ══════════════════════════════════════════════════════════════════════════════
#  JIG ENGINE
# ══════════════════════════════════════════════════════════════════════════════

ROAD_TYPES = {
    r'\bRoad\b':     ['Rd', 'Rd.', 'Rodd', 'Road'],
    r'\bStreet\b':   ['St', 'St.', 'Streeet', 'Strret'],
    r'\bDrive\b':    ['Dr', 'Dr.', 'Drivve', 'Drlve'],
    r'\bClose\b':    ['Cls', 'CIose', 'Clos'],
    r'\bLane\b':     ['Ln', 'Ln.', 'Laane'],
    r'\bAvenue\b':   ['Ave', 'Ave.', 'Avnue'],
    r'\bPlace\b':    ['PIace', 'PIce', 'Plce'],
    r'\bWay\b':      ['Wy', 'Waay'],
    r'\bCourt\b':    ['Crt', 'Courrt'],
    r'\bGardens\b':  ['Gdns', 'Garddns'],
    r'\bTerrace\b':  ['Tce', 'Terrrace'],
    r'\bGrove\b':    ['Grv', 'Groovve'],
    r'\bCrescent\b': ['Cres', 'Crescnt'],
    r'\bSquare\b':   ['Sq', 'Squaare'],
    r'\bRise\b':     ['Rse', 'Riise'],
    r'\bPark\b':     ['Pk', 'Paark'],
    r'\bHill\b':     ['HiII', 'Hlll'],
    r'\bView\b':     ['Vw', 'Veiw'],
    r'\bWalk\b':     ['WIk', 'Waalk'],
    r'\bBoulevard\b':['Blvd','Blvd.','Boulvard'],
    r'\bHighway\b':['Hwy','Highwy'],
    r'\bBypass\b':['Byps','By-pass'],
    r'\bJunction\b':['Jct','Jnctn'],
}

# Character substitutions — visually ambiguous or doubled
CHAR_SUBS = [
    ('l', 'I'),   # lowercase l  →  uppercase I
        ('i', 'I'),   # lowercase i  →  uppercase I
    ('W', 'VV'),  # W            →  VV
    ('rn', 'm'),  # rn           →  m  (classic confusable)
    ('m', 'rn'),
        ('cl','d'),
    ('g','q'),
    ('q','g'),
]

# Generic city transforms applied when city isn't in the lookup table
_GENERIC_CITY_OPS = ['double_vowel', 'drop_interior', 'swap_char', 'lowercase', 'ocr_city']

# NOTE: No real city names or real addresses anywhere in this file.
CITY_VARIANTS: dict[str, list[str]] = {}   # populated at runtime — intentionally empty


NUM_PREFIXES = [
    lambda n: f'No.{n}',
    lambda n: f'No. {n}',
    lambda n: f'No.{n}',        # weighted
    lambda n: f'No. {n}',       # weighted
    lambda n: f'Number.{n}',
    lambda n: f'Number {n}',
]


# ── character / word helpers ──────────────────────────────────────────────────

def _double_vowel(word: str) -> str:
    idxs = [i for i, c in enumerate(word) if c.lower() in 'aeiou' and i > 0]
    if not idxs:
        return word
    i = random.choice(idxs)
    return word[:i] + word[i] + word[i:]


def _double_consonant(word: str) -> str:
    idxs = [i for i, c in enumerate(word) if c.lower() in 'bcdfghjklmnpqrstvwxyz' and i > 0]
    if not idxs:
        return word
    i = random.choice(idxs)
    return word[:i] + word[i] + word[i:]


def _drop_interior(word: str) -> str:
    if len(word) <= 4:
        return word
    idxs = list(range(2, len(word) - 1))
    i = random.choice(idxs)
    return word[:i] + word[i + 1:]


def _swap_chars(text: str, rng: random.Random) -> str:
    """Apply one character-level substitution, skipping the No./Number prefix."""
    subs = CHAR_SUBS.copy()
    rng.shuffle(subs)
    # Avoid mangling the numeric prefix itself
    pm = re.match(r'^(No\.?\s*[\d][\d\-]*\s*|Number\.?\s*[\d][\d\-]*\s*)', text, re.IGNORECASE)
    offset = pm.end() if pm else 0
    suffix = text[offset:]
    for src, dst in subs:
        positions = [i for i in range(len(suffix) - len(src) + 1)
                     if suffix[i:i + len(src)] == src]
        if positions:
            p = rng.choice(positions)
            return text[:offset] + suffix[:p] + dst + suffix[p + len(src):]
    return text


# ── address-level jig steps ───────────────────────────────────────────────────

def _apply_number_prefix(address: str, rng: random.Random) -> str:
    """Replace a leading house number with a 'No.' style prefix."""
    # Standard: "12 Some Street"
    m = re.match(r'^(\d[\d\-]*[a-zA-Z]?)\s+(.*)', address)
    if m:
        prefix = rng.choice(NUM_PREFIXES)(m.group(1))
        return f'{prefix} {m.group(2)}'
    # "Unit 5, ..."
    m2 = re.match(r'^(Unit)\s+(\d+)(.*)', address, re.IGNORECASE)
    if m2:
        unit = rng.choice([m2.group(1).upper(), 'UNlT', m2.group(1)])
        no   = rng.choice([f'no. {m2.group(2)}', f'no.{m2.group(2)}', m2.group(2)])
        return f'{unit} {no}{m2.group(3)}'
    # "Flat 3, ..."
    m3 = re.match(r'^(Flat|Apartment|Apt)\s+(\w+)(.*)', address, re.IGNORECASE)
    if m3:
        return f'{m3.group(1)} {m3.group(2)}{m3.group(3)}'
    return address


def _apply_road_type(address: str, rng: random.Random) -> str:
    """Abbreviate or mangle the road-type suffix."""
    for pattern, variants in ROAD_TYPES.items():
        if re.search(pattern, address, re.IGNORECASE):
            replacement = rng.choice(variants)
            return re.sub(pattern, replacement, address, count=1, flags=re.IGNORECASE)
    return address


def _apply_word_mangle(address: str, rng: random.Random) -> str:
    """Subtly misspell one non-trivial word in the address."""
    words = address.split()
    # Exclude: pure digits/punctuation, short words, the No. prefix token
    skip = re.compile(r'^(No\.|Number\.?|[\d\-\.]+)$', re.IGNORECASE)
    candidates = [i for i, w in enumerate(words) if len(w) > 3 and not skip.match(w)]
    if not candidates:
        return address
    idx = rng.choice(candidates)
    op  = rng.choice(['double_vowel', 'double_consonant', 'drop_interior'])
    if op == 'double_vowel':
        words[idx] = _double_vowel(words[idx])
    elif op == 'double_consonant':
        words[idx] = _double_consonant(words[idx])
    else:
        words[idx] = _drop_interior(words[idx])
    return ' '.join(words)


def _apply_char_swap(address: str, rng: random.Random) -> str:
    return _swap_chars(address, rng)

def _merge_words(address, rng):
    w=address.split()
    if len(w)<2: return address
    i=rng.randint(0,len(w)-2)
    w[i]=w[i]+w[i+1]
    del w[i+1]
    protected = {"flat","apartment","apt","unit","suite","building","bldg"}
    if i < len(w)-1 and w[i].lower() in protected:
        return address
    return " ".join(w)

def _punctuation_variant(address,rng):
    return rng.choice([
        lambda s:s.replace(" "," - ",1),
        lambda s:s.replace(" ",", ",1),
        lambda s:s.replace(" "," / ",1)
    ])(address)

def _direction_variant(address,rng):
    for a,b in {"North":"N","South":"S","East":"E","West":"W"}.items():
        if a in address:
            return address.replace(a,b)
    return address


def _normalize_unit_spacing(address: str) -> str:
    patterns = [
        r'\b(Flat|Apartment|Apt|Unit|Suite|Building|Bldg)\s*([A-Za-z0-9]+)'
    ]
    for pattern in patterns:
        address = re.sub(
            pattern,
            lambda m: f"{m.group(1)} {m.group(2)}",
            address,
            flags=re.IGNORECASE
        )
    return re.sub(r'\s+', ' ', address).strip()


TRANSFORMS = [
    _apply_number_prefix,
    _apply_road_type,
    _apply_word_mangle,
    _apply_char_swap,
    _punctuation_variant,
    _direction_variant,
]


def _ocr_city(city:str,rng):
    reps=[('W','VV'),('w','vv'),('l','I'),('i','I')]
    out=city
    applied=0
    for a,b in reps:
        if a in out and rng.random()<0.7:
            out=out.replace(a,b,1)
            applied+=1
    return out if applied else city

def _apply_city_jig(city: str, rng: random.Random) -> str:
    key = city.strip().lower()
    if key in CITY_VARIANTS and CITY_VARIANTS[key]:
        return rng.choice(CITY_VARIANTS[key])
    # Generic fallback
    op = rng.choice(_GENERIC_CITY_OPS)
    if op == 'double_vowel':
        return _double_vowel(city)
    elif op == 'drop_interior':
        return _drop_interior(city)
    elif op == 'swap_char':
        return _swap_chars(city, rng)
    elif op == 'lowercase':
        return city.lower()
    elif op == 'ocr_city':
        return _ocr_city(city, rng)
    return city


# ── public API ────────────────────────────────────────────────────────────────

def jig_address(address: str, city: str, intensity: int,
                seed: int | None = None) -> tuple[str, str]:
    """
    Return (jigged_address, jigged_city).
    intensity: 1 = subtle, 2 = moderate, 3 = aggressive
    """
    rng = random.Random(seed if seed is not None else random.getrandbits(32))

    addr = address.strip()
    cty = city.strip()

    if intensity == 1:
        transform_count = rng.randint(1, 2)
    elif intensity == 2:
        transform_count = rng.randint(2, 4)
    else:
        transform_count = rng.randint(4, 6)

    for fn in rng.sample(TRANSFORMS, min(transform_count, len(TRANSFORMS))):
        try:
            addr = fn(addr, rng)
        except Exception:
            pass

    for _ in range(rng.randint(1,3)):
        cty = _apply_city_jig(cty, rng)

    addr = _normalize_unit_spacing(addr)

    return addr, cty


def generate_variants(address: str, city: str, postcode: str,
                      count: int, intensity: int) -> list[dict]:
    """Generate `count` unique jig variants for an address."""
    results, seen = [], set()
    attempts = 0
    while len(results) < count and attempts < count * 50:
        attempts += 1
        ja, jc = jig_address(address, city, intensity,
                              seed=random.getrandbits(32))
        key = (ja, jc)
        if key not in seen and ja != address:
            seen.add(key)
            results.append({'address': ja, 'city': jc, 'postcode': postcode})
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  STYLE
# ══════════════════════════════════════════════════════════════════════════════

BG0      = '#0b0b0d'
BG1      = '#111115'
BG2      = '#16161b'
BORDER   = '#222228'
BORDER_A = '#2e2e38'
ACCENT   = '#4f8cff'
ACCENT_D = '#3d73d9'
ACCENT_B = '#79a8ff'
TEXT     = '#dddbd8'
TEXT_DIM = '#9ea7b8'
TEXT_MUT = '#7d8699'
RED      = '#e05555'

QSS = f"""
/* ── base ── */
QMainWindow, QWidget {{
    background: {BG0};
    color: {TEXT};
    font-family: 'Segoe UI';
    font-size: 14px;
}}

/* ── tabs ── */
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {BORDER};
    background: {BG0};
}}
QTabBar {{
    background: {BG1};
    border-bottom: 1px solid {BORDER};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 14px 28px;
    font-size: 11px;
    letter-spacing: 0px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
    background: {BG2};
}}

/* ── buttons ── */
QPushButton {{
    background: {BG2};
    color: {TEXT};
    border: 1px solid {BORDER_A};
    border-radius: 8px;
    padding: 12px 20px;
    letter-spacing: 0.5px;
}}
QPushButton:hover {{
    background: #1c1c24;
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton:pressed {{
    background: {BG1};
}}
QPushButton#primary {{
    background: {ACCENT};
    color: #ffffff;
    font-weight: 700;
    font-size: 13px;
    border: none;
    letter-spacing: 1px;
}}
QPushButton#primary:hover {{
    background: {ACCENT_B};
}}
QPushButton#primary:pressed {{
    background: {ACCENT_D};
}}
QPushButton#danger {{
    border-color: {RED};
    color: {RED};
}}
QPushButton#danger:hover {{
    background: #1e1010;
}}

/* ── tables ── */
QTableWidget {{
    background: {BG0};
    alternate-background-color: {BG1};
    gridline-color: {BORDER};
    color: {TEXT};
    border: none;
    border-top: 1px solid {BORDER};
    selection-background-color: #0e2a1a;
    selection-color: {ACCENT};
    outline: none;
}}
QTableWidget::item {{
    padding: 4px 10px;
    border: none;
}}
QTableWidget::item:selected {{
    background: #0e2a1a;
    color: {ACCENT};
}}
QHeaderView::section {{
    background: {BG1};
    color: {TEXT_DIM};
    font-size: 10px;
    letter-spacing: 0px;
    padding: 7px 10px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
}}
QHeaderView::section:last {{
    border-right: none;
}}

/* ── inputs ── */
QSpinBox, QComboBox, QLineEdit {{
    background: {BG1};
    color: {TEXT};
    border: 1px solid {BORDER_A};
    border-radius: 8px;
    padding: 10px 14px;
    selection-background-color: #0e2a1a;
    selection-color: {ACCENT};
}}
QSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
    border-color: {ACCENT};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {BG2};
    border: none;
    width: 16px;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
    subcontrol-origin: padding;
    subcontrol-position: right center;
}}
QComboBox QAbstractItemView {{
    background: {BG2};
    color: {TEXT};
    selection-background-color: #0e2a1a;
    selection-color: {ACCENT};
    border: 1px solid {BORDER_A};
    outline: none;
}}

/* ── text edit ── */
QTextEdit {{
    background: {BG1};
    color: {ACCENT};
    border: none;
    border-top: 1px solid {BORDER};
    font-family: 'Consolas', monospace;
    font-size: 14px;
    padding: 12px 16px;
}}

/* ── scrollbars ── */
QScrollBar:vertical {{
    background: {BG0};
    width: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_A};
    border-radius: 2px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 5px; background: {BG0}; }}
QScrollBar::handle:horizontal {{ background: {BORDER_A}; border-radius: 2px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── status bar ── */
QStatusBar {{
    background: {BG1};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
    font-size: 11px;
    padding: 0 8px;
}}

/* ── labels ── */
QLabel#accent {{
    color: {ACCENT};
    font-size: 10px;
    letter-spacing: 1px;
}}
QLabel#muted {{
    color: {TEXT_MUT};
    font-size: 11px;
}}

/* ── separators ── */
QFrame#vsep {{
    background: {BORDER};
    min-width: 1px;
    max-width: 1px;
}}
QFrame#hsep {{
    background: {BORDER};
    min-height: 1px;
    max-height: 1px;
}}
"""


# ══════════════════════════════════════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _vsep():
    f = QFrame(); f.setObjectName('vsep'); f.setFrameShape(QFrame.VLine)
    return f

def _hsep():
    f = QFrame(); f.setObjectName('hsep'); f.setFrameShape(QFrame.HLine)
    return f

def _label(text, obj='', style=''):
    lbl = QLabel(text)
    if obj:  lbl.setObjectName(obj)
    if style: lbl.setStyleSheet(style)
    return lbl

def _btn(text, obj='', fixed_w=0):
    b = QPushButton(text)
    if obj: b.setObjectName(obj)
    if fixed_w: b.setFixedWidth(fixed_w)
    return b

def _table(cols: list[str]) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(True)
    t.setFocusPolicy(Qt.NoFocus)
    return t

def _set_col_stretch(table: QTableWidget, *stretch_cols):
    hh = table.horizontalHeader()
    for i in range(table.columnCount()):
        if i in stretch_cols:
            hh.setSectionResizeMode(i, QHeaderView.Stretch)
        else:
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)

def _cell(text: str, color: str = '') -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    if color:
        item.setForeground(QColor(color))
    return item


# ══════════════════════════════════════════════════════════════════════════════
#  STAT PILL
# ══════════════════════════════════════════════════════════════════════════════

class StatPill(QWidget):
    def __init__(self, label: str):
        super().__init__()
        self.setFixedWidth(140)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(1)
        self._val = QLabel('0')
        self._val.setStyleSheet(
            f'color:{ACCENT}; font-size:20px; font-weight:bold;'
            f' font-family:Consolas; letter-spacing:1px;'
        )
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(
            f'color:{TEXT_MUT}; font-size:9px; letter-spacing:2px;'
        )
        layout.addWidget(self._val)
        layout.addWidget(self._lbl)
        self.setStyleSheet(f'border-left: 1px solid {BORDER};')

    def set(self, v): self._val.setText(str(v))
    def reset(self):  self._val.setText('0')


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════

class AddressJigger(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Address Jigger')
        self.resize(1700, 1050)
        self.setMinimumSize(1300, 800)
        self.source_rows: list[dict] = []
        self.jigged_rows: list[dict] = []
        self._build_ui()
        self._try_load_default()

    # ── build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._header())
        vbox.addWidget(self._toolbar())
        vbox.addWidget(_hsep())
        vbox.addWidget(self._tabs(), 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.tabs.setCurrentIndex(0)
        self._msg('Ready — load a CSV or drag one in.')

    # ── header ────────────────────────────────────────────────────────────────

    def _header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(50)
        w.setStyleSheet(f'background:{BG1}; border-bottom:1px solid {BORDER};')
        h = QHBoxLayout(w)
        h.setContentsMargins(20, 0, 0, 0)
        h.setSpacing(0)

        logo = _label('ADDRESS  JIGGER', style=(
            f'color:{ACCENT}; font-size:13px; font-weight:bold; letter-spacing:5px;'
        ))
        h.addWidget(logo)
        h.addStretch()

        self.pill_total    = StatPill('LOADED')
        self.pill_jigged   = StatPill('PROCESSED')
        self.pill_variants = StatPill('VARIANTS')
        for p in (self.pill_total, self.pill_jigged, self.pill_variants):
            h.addWidget(p)

        return w

    # ── toolbar ───────────────────────────────────────────────────────────────

    def _toolbar(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(52)
        w.setStyleSheet(f'background:{BG0};')
        h = QHBoxLayout(w)
        h.setContentsMargins(14, 0, 14, 0)
        h.setSpacing(6)

        self.btn_load = _btn('⬆  LOAD CSV')
        self.btn_load.clicked.connect(self.load_csv)
        h.addWidget(self.btn_load)

        h.addWidget(_vsep())

        # Variants
        h.addWidget(_label('Variants per address', style=f'color:{TEXT_DIM}; font-size:12px;'))
        self.spin_variants = QSpinBox()
        self.spin_variants.setRange(1, 20)
        self.spin_variants.setValue(1)
        self.spin_variants.setFixedWidth(58)
        self.spin_variants.setToolTip('Number of jig variants to generate per address')
        h.addWidget(self.spin_variants)

        h.addWidget(_vsep())

        # Intensity
        h.addWidget(_label('Transformation strength', style=f'color:{TEXT_DIM}; font-size:12px;'))
        self.combo_intensity = QComboBox()
        self.combo_intensity.addItems(['1  —  SUBTLE (1–2 changes)', '2  —  MODERATE (2–4 changes)', '3  —  AGGRESSIVE (4–6 changes)'])
        self.combo_intensity.setCurrentIndex(0)
        self.combo_intensity.setFixedWidth(180)
        self.combo_intensity.setToolTip(
            'Controls how many transformations are applied per address\n\n'
            'Subtle: 1–2 changes\n'
            'Moderate: 2–4 changes\n'
            'Aggressive: 4–6 changes'
        )
        h.addWidget(self.combo_intensity)

        h.addStretch()

        self.btn_jig = _btn('⚡  JIG ALL', 'primary', 160)
        self.btn_jig.clicked.connect(self.jig_all)
        h.addWidget(self.btn_jig)

        h.addWidget(_vsep())

        self.btn_export = _btn('⬇  EXPORT CSV')
        self.btn_export.clicked.connect(self.export_csv)
        h.addWidget(self.btn_export)

        self.btn_copy = _btn('⎘  COPY')
        self.btn_copy.clicked.connect(self.copy_all)
        h.addWidget(self.btn_copy)

        h.addWidget(_vsep())

        self.btn_clear = _btn('✕  CLEAR', 'danger')
        self.btn_clear.clicked.connect(self.clear_all)
        h.addWidget(self.btn_clear)

        return w

    # ── tabs ──────────────────────────────────────────────────────────────────

    def _tabs(self) -> QTabWidget:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._tab_source(), 'SOURCE')
        self.tabs.addTab(self._tab_output(), 'OUTPUT')
        self.tabs.addTab(self._tab_preview(), 'SINGLE EDIT')
        return self.tabs

    # ── source tab ────────────────────────────────────────────────────────────

    def _tab_source(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # sub-header
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet(f'background:{BG1}; border-bottom:1px solid {BORDER};')
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(16, 0, 16, 0)
        bh.addWidget(_label('SOURCE ADDRESSES', 'accent'))
        bh.addStretch()
        hint = _label('Supports CSV with columns: Name, Address, Postcode, City  (comma or semicolon delimited)', 'muted')
        bh.addWidget(hint)
        v.addWidget(bar)

        self.source_table = _table(['NAME', 'ADDRESS', 'POSTCODE', 'CITY'])
        _set_col_stretch(self.source_table, 1)
        v.addWidget(self.source_table, 1)
        return w

    # ── output tab ────────────────────────────────────────────────────────────

    def _tab_output(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet(f'background:{BG1}; border-bottom:1px solid {BORDER};')
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(16, 0, 16, 0)
        bh.addWidget(_label('JIGGED OUTPUT', 'accent'))
        bh.addStretch()
        hint = _label('Green fields = transformed values', 'muted')
        bh.addWidget(hint)
        v.addWidget(bar)

        self.output_table = _table([
            'LABEL', 'JIG ADDRESS', 'JIG CITY', 'POSTCODE',
            'SOURCE NAME', 'SOURCE ADDRESS'
        ])
        _set_col_stretch(self.output_table, 1, 5)
        v.addWidget(self.output_table, 1)
        return w

    # ── preview tab ───────────────────────────────────────────────────────────

    def _tab_preview(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # sub-header
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet(f'background:{BG1}; border-bottom:1px solid {BORDER};')
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(16, 0, 16, 0)
        bh.addWidget(_label('SINGLE ADDRESS EDITOR', 'accent'))
        v.addWidget(bar)

        # form
        form_wrap = QWidget()
        form_wrap.setStyleSheet(f'background:{BG0};')
        form_wrap.setFixedHeight(190)
        grid = QGridLayout(form_wrap)
        grid.setContentsMargins(24, 18, 24, 18)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        lbl_style = f'color:{TEXT_DIM}; font-size:10px; letter-spacing:2px;'

        grid.addWidget(_label('ADDRESS', style=lbl_style),  0, 0)
        self.prev_addr = QLineEdit()
        self.prev_addr.setPlaceholderText('e.g.  123 Jig Street')
        grid.addWidget(self.prev_addr, 0, 1)

        grid.addWidget(_label('CITY', style=lbl_style), 0, 2)
        self.prev_city = QLineEdit()
        self.prev_city.setPlaceholderText('e.g.  Jigton')
        grid.addWidget(self.prev_city, 0, 3)

        grid.addWidget(_label('POSTCODE', style=lbl_style), 1, 0)
        self.prev_pc = QLineEdit()
        self.prev_pc.setPlaceholderText('e.g.  JG1 1AB')
        grid.addWidget(self.prev_pc, 1, 1)

        grid.addWidget(_label('VARIANTS', style=lbl_style), 1, 2)
        self.prev_spin = QSpinBox()
        self.prev_spin.setRange(1, 20)
        self.prev_spin.setValue(1)
        grid.addWidget(self.prev_spin, 1, 3)

        btn_prev = _btn('⚡  GENERATE VARIANTS', 'primary')
        btn_prev.setFixedWidth(200)
        btn_prev.clicked.connect(self._run_preview)
        grid.addWidget(btn_prev, 2, 0, 1, 2)

        btn_copy_prev = _btn('⎘  COPY RESULTS')
        btn_copy_prev.clicked.connect(self._copy_preview)
        grid.addWidget(btn_copy_prev, 2, 2)

        v.addWidget(form_wrap)
        v.addWidget(_hsep())

        self.prev_output = QTextEdit()
        self.prev_output.setReadOnly(True)
        self.prev_output.setPlaceholderText(
            'Intensity Levels:\n'
            '• Subtle = 1–2 transformations\n'
            '• Moderate = 2–4 transformations\n'
            '• Aggressive = 4–6 transformations\n\n'
            'Enter an address above and press GENERATE VARIANTS'
        )
        v.addWidget(self.prev_output, 1)
        return w

    # ── data loading ──────────────────────────────────────────────────────────

    def _try_load_default(self):
        for candidate in [
            Path('Addresses.csv'),
            Path(__file__).parent / 'Addresses.csv',
        ]:
            if candidate.exists():
                self._load_file(str(candidate))
                return
        self._msg('No default CSV found — use LOAD CSV to import.')

    def load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load CSV', '', 'CSV Files (*.csv);;All Files (*)'
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        try:
            with open(path, newline='', encoding='utf-8-sig') as f:
                sample = f.read(4096); f.seek(0)
                delim  = ';' if sample.count(';') > sample.count(',') else ','
                rows   = list(csv.DictReader(f, delimiter=delim))
            self._ingest(rows, Path(path).name)
        except Exception as exc:
            QMessageBox.critical(self, 'Load Error', str(exc))

    def _ingest(self, rows: list[dict], fname: str):
        if not rows:
            self._msg('CSV appears to be empty.'); return

        keys = list(rows[0].keys())

        def _col(*hints):
            for h in hints:
                for k in keys:
                    if h.lower() in k.lower(): return k
            return None

        c_name = _col('name', 'profile', 'holder')
        c_addr = _col('address', 'addr', 'street')
        c_pc   = _col('postcode', 'zip', 'postal')
        c_city = _col('city', 'town', 'county')

        self.source_rows = []
        for r in rows:
            addr = r.get(c_addr, '').strip() if c_addr else ''
            if not addr: continue
            self.source_rows.append({
                'name':     (r.get(c_name, '') or '').strip() if c_name else '',
                'address':  addr,
                'postcode': (r.get(c_pc,   '') or '').strip() if c_pc   else '',
                'city':     (r.get(c_city,  '') or '').strip() if c_city else '',
            })

        self._render_source()
        self.pill_total.set(len(self.source_rows))
        self._msg(f'Loaded {len(self.source_rows)} addresses from {fname}')

    def _render_source(self):
        t = self.source_table
        t.setRowCount(len(self.source_rows))
        for i, r in enumerate(self.source_rows):
            t.setItem(i, 0, _cell(r['name']))
            t.setItem(i, 1, _cell(r['address']))
            t.setItem(i, 2, _cell(r['postcode']))
            t.setItem(i, 3, _cell(r['city']))

    # ── jig ───────────────────────────────────────────────────────────────────

    def jig_all(self):
        if not self.source_rows:
            QMessageBox.warning(self, 'No Data', 'Load a CSV first.'); return

        n         = self.spin_variants.value()
        intensity = self.combo_intensity.currentIndex() + 1

        self.jigged_rows = []
        for r in self.source_rows:
            variants = generate_variants(
                r['address'], r['city'], r['postcode'], n, intensity
            )
            for vi, v in enumerate(variants, 1):
                name = r['name'] or 'ENTRY'
                self.jigged_rows.append({
                    'label':          f'{name.upper()} — V{vi:02d}',
                    'address':        v['address'],
                    'city':           v['city'],
                    'postcode':       v['postcode'],
                    'source_name':    r['name'],
                    'source_address': r['address'],
                })

        self._render_output()
        self.tabs.setCurrentIndex(1)
        self.pill_jigged.set(len(self.source_rows))
        self.pill_variants.set(len(self.jigged_rows))
        mode_name = ['Subtle','Moderate','Aggressive'][intensity - 1]
        mode_range = ['1–2','2–4','4–6'][intensity - 1]
        self._msg(
            f'Generated {len(self.jigged_rows)} variants '
            f'from {len(self.source_rows)} addresses '
            f'using {mode_name} mode ({mode_range} transformations, {n} per address)'
        )

    def _render_output(self):
        t = self.output_table
        t.setRowCount(len(self.jigged_rows))
        for i, r in enumerate(self.jigged_rows):
            t.setItem(i, 0, _cell(r['label']))
            t.setItem(i, 1, _cell(r['address'],        ACCENT))
            t.setItem(i, 2, _cell(r['city'],           ACCENT))
            t.setItem(i, 3, _cell(r['postcode']))
            t.setItem(i, 4, _cell(r['source_name'],    TEXT_DIM))
            t.setItem(i, 5, _cell(r['source_address'], TEXT_DIM))

    # ── export / copy ─────────────────────────────────────────────────────────

    def export_csv(self):
        if not self.jigged_rows:
            QMessageBox.warning(self, 'No Output', 'Run JIG ALL first.'); return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export CSV', 'jigged_output.csv', 'CSV Files (*.csv)'
        )
        if not path: return
        fields = ['label', 'address', 'city', 'postcode', 'source_name', 'source_address']
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader(); w.writerows(self.jigged_rows)
        try:
            os.startfile(path)
        except Exception:
            try:
                subprocess.Popen([path])
            except Exception:
                pass
        self._msg(f'Exported {len(self.jigged_rows)} rows → {Path(path).name}')

    def copy_all(self):
        if not self.jigged_rows:
            self._msg('Nothing to copy — run JIG ALL first.'); return
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=['label', 'address', 'city', 'postcode'])
        w.writeheader()
        for r in self.jigged_rows:
            w.writerow({k: r[k] for k in ['label', 'address', 'city', 'postcode']})
        QApplication.clipboard().setText(buf.getvalue())
        self._msg(f'Copied {len(self.jigged_rows)} rows to clipboard.')

    def clear_all(self):
        self.source_rows = []
        self.jigged_rows = []
        self.source_table.setRowCount(0)
        self.output_table.setRowCount(0)
        for p in (self.pill_total, self.pill_jigged, self.pill_variants):
            p.reset()
        self.prev_output.clear()
        self._msg('Cleared.')

    # ── preview ───────────────────────────────────────────────────────────────

    def _run_preview(self):
        addr = self.prev_addr.text().strip()
        city = self.prev_city.text().strip()
        pc   = self.prev_pc.text().strip()
        n    = self.prev_spin.value()
        intensity = self.combo_intensity.currentIndex() + 1

        if not addr:
            self.prev_output.setPlainText(
                'Enter an address above.\n\nExample:\n'
                '  123 Jig Street  /  Jigton  /  JG1 1AB'
            )
            return

        variants = generate_variants(addr, city, pc, n, intensity)
        pad      = max(len(addr), 40)
        lines    = [
            f'  {"ORIGINAL":<10}  {addr:<{pad}}  {city}  {pc}',
            f'  {"─" * (pad + 30)}',
        ]
        for i, v in enumerate(variants, 1):
            lines.append(
                f'  {f"JIG {i:02d}":<10}  {v["address"]:<{pad}}  {v["city"]}  {v["postcode"]}'
            )
        self.prev_output.setPlainText('\n'.join(lines))

    def _copy_preview(self):
        text = self.prev_output.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self._msg('Preview copied to clipboard.')

    # ── util ──────────────────────────────────────────────────────────────────

    def _msg(self, text: str):
        self.status_bar.showMessage(text)


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(QSS)
    win = AddressJigger()
    win.show()
    sys.exit(app.exec_())
