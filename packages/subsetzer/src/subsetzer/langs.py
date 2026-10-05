"""Language code normalisation for subsetzer."""
from __future__ import annotations

import re

_LANG_MAP = {
    "aa": "aa", "aar": "aa", "ab": "ab", "abk": "ab", "af": "af", "afr": "af",
    "afrikaans": "af",
    "ak": "ak", "aka": "ak", "am": "am", "amh": "am", "ar": "ar", "ara": "ar",
    "arabic": "ar",
    "an": "an", "arg": "an", "as": "as", "asm": "as", "av": "av", "ava": "av",
    "ay": "ay", "aym": "ay", "az": "az", "aze": "az",
    "ba": "ba", "bak": "ba", "be": "be", "bel": "be", "bg": "bg", "bul": "bg",
    "bulgarian": "bg",
    "bh": "bh", "bih": "bh", "bi": "bi", "bis": "bi", "bm": "bm", "bam": "bm",
    "bn": "bn", "ben": "bn", "bengali": "bn",
    "bo": "bo", "tib": "bo", "bod": "bo", "tibetan": "bo",
    "br": "br", "bre": "br", "bs": "bs", "bos": "bs",
    "ca": "ca", "cat": "ca", "catalan": "ca",
    "ce": "ce", "che": "ce", "ch": "ch", "cha": "ch",
    "chinese": "zh-cn", "zh": "zh-cn", "zho": "zh-cn", "chi": "zh-cn",
    "zh-cn": "zh-cn", "zh-hans": "zh-cn", "zh-hant": "zh-tw", "zh-tw": "zh-tw",
    "co": "co", "cos": "co", "cr": "cr", "cre": "cr",
    "cs": "cs", "ces": "cs", "cze": "cs", "czech": "cs",
    "cv": "cv", "chv": "cv", "cy": "cy", "cym": "cy", "wel": "cy", "welsh": "cy",
    "da": "da", "dan": "da", "danish": "da",
    "de": "de", "deu": "de", "ger": "de", "german": "de",
    "dv": "dv", "div": "dv", "dz": "dz", "dzo": "dz",
    "el": "el", "ell": "el", "gre": "el", "greek": "el",
    "en": "en", "eng": "en", "english": "en",
    "eo": "eo", "epo": "eo", "es": "es", "spa": "es", "spanish": "es",
    "et": "et", "est": "et", "eu": "eu", "eus": "eu", "baq": "eu",
    "fa": "fa", "fas": "fa", "per": "fa", "persian": "fa",
    "fi": "fi", "fin": "fi", "finnish": "fi",
    "fj": "fj", "fij": "fj", "fo": "fo", "fao": "fo",
    "fr": "fr", "fra": "fr", "fre": "fr", "french": "fr",
    "fy": "fy", "fry": "fy", "ga": "ga", "gle": "ga",
    "gd": "gd", "gla": "gd", "gl": "gl", "glg": "gl",
    "gn": "gn", "grn": "gn", "gu": "gu", "guj": "gu",
    "ha": "ha", "hau": "ha", "he": "he", "heb": "he", "hebrew": "he",
    "hi": "hi", "hin": "hi", "hindi": "hi",
    "hr": "hr", "hrv": "hr", "croatian": "hr",
    "hu": "hu", "hun": "hu", "hungarian": "hu",
    "hy": "hy", "hye": "hy", "arm": "hy",
    "id": "id", "ind": "id", "indonesian": "id",
    "ie": "ie", "ile": "ie", "ig": "ig", "ibo": "ig",
    "is": "is", "isl": "is", "ice": "is",
    "it": "it", "ita": "it", "italian": "it",
    "ja": "ja", "jpn": "ja", "japanese": "ja",
    "jv": "jv", "jav": "jv",
    "ka": "ka", "kat": "ka", "geo": "ka",
    "kk": "kk", "kaz": "kk", "km": "km", "khm": "km",
    "kn": "kn", "kan": "kn", "ko": "ko", "kor": "ko", "korean": "ko",
    "ku": "ku", "kur": "ku", "ky": "ky", "kir": "ky",
    "la": "la", "lat": "la", "latin": "la",
    "lb": "lb", "ltz": "lb", "lo": "lo", "lao": "lo",
    "lt": "lt", "lit": "lt", "lv": "lv", "lav": "lv",
    "mg": "mg", "mlg": "mg", "mh": "mh", "mah": "mh",
    "mi": "mi", "mri": "mi", "mao": "mi",
    "mk": "mk", "mkd": "mk", "mac": "mk",
    "ml": "ml", "mal": "ml", "mn": "mn", "mon": "mn",
    "mr": "mr", "mar": "mr", "ms": "ms", "msa": "ms", "may": "ms",
    "mt": "mt", "mlt": "mt", "my": "my", "mya": "my", "bur": "my",
    "nb": "nb", "nob": "nb", "ne": "ne", "nep": "ne",
    "nl": "nl", "nld": "nl", "dut": "nl", "dutch": "nl",
    "nn": "nn", "nno": "nn", "no": "no", "nor": "no", "norwegian": "no",
    "oc": "oc", "oci": "oc", "oj": "oj", "oji": "oj",
    "om": "om", "orm": "om", "or": "or", "ori": "or",
    "pa": "pa", "pan": "pa", "pl": "pl", "pol": "pl", "polish": "pl",
    "ps": "ps", "pus": "ps", "pt": "pt", "por": "pt", "portuguese": "pt",
    "pt-br": "pt-br", "pt-pt": "pt",
    "qu": "qu", "que": "qu",
    "ro": "ro", "ron": "ro", "rum": "ro", "romanian": "ro",
    "ru": "ru", "rus": "ru", "russian": "ru",
    "sa": "sa", "san": "sa", "sc": "sc", "srd": "sc",
    "sd": "sd", "snd": "sd", "se": "se", "sme": "se",
    "sg": "sg", "sag": "sg", "si": "si", "sin": "si",
    "sk": "sk", "slk": "sk", "slo": "sk", "slovak": "sk",
    "sl": "sl", "slv": "sl", "slovenian": "sl",
    "so": "so", "som": "so", "sq": "sq", "sqi": "sq", "alb": "sq",
    "sr": "sr", "srp": "sr", "serbian": "sr",
    "sv": "sv", "swe": "sv", "swedish": "sv",
    "sw": "sw", "swa": "sw", "ta": "ta", "tam": "ta",
    "te": "te", "tel": "te", "tg": "tg", "tgk": "tg",
    "th": "th", "tha": "th", "thai": "th",
    "ti": "ti", "tir": "ti", "tk": "tk", "tuk": "tk",
    "tl": "tl", "tgl": "tl", "tr": "tr", "tur": "tr", "turkish": "tr",
    "tt": "tt", "tat": "tt", "ug": "ug", "uig": "ug",
    "uk": "uk", "ukr": "uk", "ukrainian": "uk",
    "ur": "ur", "urd": "ur", "uz": "uz", "uzb": "uz",
    "vi": "vi", "vie": "vi", "vietnamese": "vi",
    "vo": "vo", "vol": "vo", "wo": "wo", "wol": "wo",
    "xh": "xh", "xho": "xh", "yi": "yi", "yid": "yi",
    "yo": "yo", "yor": "yo", "za": "za", "zha": "za", "zu": "zu", "zul": "zu",
}

_CLEAN_RE = re.compile(r"[\s_-]+")


def is_known_lang(token: str) -> bool:
    if not token or not token.strip():
        return False
    t = token.strip().lower()
    if t == "auto":
        return False
    return t in _LANG_MAP or _CLEAN_RE.sub("-", t) in _LANG_MAP


def normalise_lang(token: str) -> str:
    if not token or not token.strip():
        return "auto"
    t = token.strip().lower()
    if t == "auto":
        return "auto"
    return _LANG_MAP.get(t) or _LANG_MAP.get(_CLEAN_RE.sub("-", t)) or t


def display_name(token: str) -> str:
    """Best human-readable name for a language token (code or name).

    ``"de"`` -> ``"German"``, ``"German"`` -> ``"German"``,
    ``"zh-cn"`` -> ``"Chinese"``; ``""``/``"auto"`` -> ``"auto"``.
    Unknown tokens are returned trimmed, as passed.
    """
    t = (token or "").strip()
    if not t or t.lower() == "auto":
        return "auto"
    low = t.lower()
    code = _LANG_MAP.get(low)
    if code is None:
        return t
    for name, mapped in _LANG_MAP.items():
        if len(name) > 4 and not name[0:1].isdigit() and mapped == code:
            return name.title()
    return t
