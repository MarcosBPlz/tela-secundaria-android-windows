"""Comandos de voz locais para o painel; não usa serviços de IA nem API paga.

Entende frases naturais em português, como:
  "adiciona arroz, feijão e leite"      "põe café na lista"      "preciso de pão"
  "tira o leite da lista"               "comprei o café"         "o que tem na lista?"
  "marca dentista amanhã às duas da tarde"   "reunião sexta às 9 e meia"
  "o que tenho amanhã?"                 "cancela o dentista"
"""
from __future__ import annotations

import json
import random
import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SHOPPING_FILE = DATA / "shopping.json"
AGENDA_FILE = DATA / "agenda.json"


class VoiceAssistantError(Exception):
    pass


# ----------------------------------------------------------------- utilidades

def _fold(value: str) -> str:
    """Minúsculas e sem acento, mantendo o mesmo tamanho do texto original."""
    out = []
    for ch in value:
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
        out.append((base or ch)[0].lower())
    return "".join(out)


def _read_list(path: Path) -> list[dict]:
    try:
        value = json.loads(path.read_text("utf-8")) if path.exists() else []
        return value if isinstance(value, list) else []
    except (OSError, ValueError):
        return []


def _write_list(path: Path, value: list[dict]) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")


def _pick(*options: str) -> str:
    return random.choice(options)


def _join(names: list[str]) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " e " + names[-1]


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


NUM_WORDS = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "catorze": 14, "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18,
    "dezenove": 19, "vinte": 20, "vinte e um": 21, "vinte e uma": 21, "vinte e dois": 22,
    "vinte e duas": 22, "vinte e tres": 23, "trinta": 30, "quarenta": 40, "quarenta e cinco": 45,
    "cinquenta": 50,
}
_NUM_RE = "|".join(sorted((re.escape(k) for k in NUM_WORDS), key=len, reverse=True))
_HOUR_TOKEN = rf"(\d{{1,2}}|{_NUM_RE})"


def _to_int(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    return NUM_WORDS.get(token)


# --------------------------------------------------------------- data e hora

WEEKDAYS = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}
MONTHS = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
          "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def _find_date(folded: str, today: date) -> tuple[date | None, tuple[int, int] | None]:
    for pattern, offset in ((r"\b(?:pra |para |de )?depois de amanha\b", 2),
                            (r"\b(?:pra |para |de )?amanha\b", 1), (r"\b(?:pra |para |de )?hoje\b", 0)):
        m = re.search(pattern, folded)
        if m:
            return today + timedelta(days=offset), m.span()
    m = re.search(r"\b(?:(?:na|no|pra|para|nessa|nesta|essa|esta)\s+)?(?:(proxima|proximo|que vem)\s+)?"
                  r"(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:[- ]feira)?(?:\s+que vem)?\b", folded)
    if m:
        target = WEEKDAYS[m.group(2)]
        offset = (target - today.weekday()) % 7
        if offset == 0 or m.group(1) or "que vem" in m.group(0):
            offset = offset or 7
        return today + timedelta(days=offset), m.span()
    m = re.search(rf"\b(?:(?:no\s+)?dia\s+)?(\d{{1,2}}|{_NUM_RE})\s+de\s+(" + "|".join(MONTHS) + r")\b", folded)
    if m:
        day = _to_int(m.group(1))
        try:
            found = date(today.year, MONTHS[m.group(2)], day or 0)
            if found < today:
                found = date(today.year + 1, found.month, found.day)
            return found, m.span()
        except ValueError:
            pass
    m = re.search(r"\b(?:(?:no\s+)?dia\s+)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", folded)
    if m:
        year = int(m.group(3)) if m.group(3) else today.year
        year += 2000 if year < 100 else 0
        try:
            return date(year, int(m.group(2)), int(m.group(1))), m.span()
        except ValueError:
            pass
    m = re.search(r"\b(?:no\s+)?dia\s+(\d{1,2})\b", folded)
    if m:
        try:
            found = date(today.year, today.month, int(m.group(1)))
            if found < today:
                found = date(today.year + (today.month == 12), today.month % 12 + 1, found.day)
            return found, m.span()
        except ValueError:
            pass
    return None, None


def _find_time(folded: str) -> tuple[str | None, tuple[int, int] | None]:
    m = re.search(r"\b(?:as\s+|ao\s+|a\s+)?meio[- ]dia(?:\s+e\s+meia)?\b", folded)
    if m:
        return ("12:30" if "meia" in m.group(0)[6:] else "12:00"), m.span()
    m = re.search(r"\b(?:as\s+|a\s+)?meia[- ]noite\b", folded)
    if m:
        return "00:00", m.span()
    patterns = [
        rf"\b(?:as|a|pras|para as|pelas)\s+{_HOUR_TOKEN}(?:\s*(?:horas?|h|:)\s*(\d{{2}})?)?"
        rf"(?:\s+e\s+(meia|quinze|trinta|quarenta e cinco|\d{{1,2}}))?(?:\s+(?:horas?|h))?"
        r"(?:\s+(?:da|de)\s+(manha|tarde|noite|madrugada))?",
        rf"\b(\d{{1,2}})\s*(?:horas?|h|:)\s*(\d{{2}})?(?:\s+(?:da|de)\s+(manha|tarde|noite|madrugada))?\b",
        rf"\b{_HOUR_TOKEN}\s+horas?(?:\s+e\s+(meia|\d{{1,2}}))?(?:\s+(?:da|de)\s+(manha|tarde|noite|madrugada))?\b",
        rf"\b{_HOUR_TOKEN}(?:\s+e\s+(meia|quinze|trinta|\d{{1,2}}))?\s+(?:da|de)\s+(manha|tarde|noite|madrugada)\b",
    ]
    for i, pattern in enumerate(patterns):
        m = re.search(pattern, folded)
        if not m:
            continue
        groups = m.groups()
        hour = _to_int(groups[0])
        minute, period = 0, None
        if i == 0:
            minute_txt, extra, period = groups[1], groups[2], groups[3]
            if minute_txt:
                minute = int(minute_txt)
            elif extra:
                minute = 30 if extra == "meia" else (_to_int(extra) or 0)
        elif i == 1:
            minute, period = int(groups[1] or 0), groups[2]
        else:
            extra, period = groups[1], groups[2]
            if extra:
                minute = 30 if extra == "meia" else (_to_int(extra) or 0)
        if hour is None or hour > 23 or minute > 59:
            continue
        if period in ("tarde", "noite") and hour < 12:
            hour += 12
        if period == "madrugada" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}", m.span()
    return None, None


def _blank(text: str, span: tuple[int, int] | None) -> str:
    if not span:
        return text
    return text[:span[0]] + " " * (span[1] - span[0]) + text[span[1]:]


def _date_label(day: date, today: date) -> str:
    if day == today:
        return "hoje"
    if day == today + timedelta(days=1):
        return "amanhã"
    names = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    if 1 < (day - today).days < 7:
        return names[day.weekday()]
    return day.strftime("%d/%m")


def _time_label(hhmm: str) -> str:
    h, m = hhmm.split(":")
    return f"{int(h)}h" if m == "00" else f"{int(h)}h{m}"


# ------------------------------------------------------------------- textos

FILLER = (r"^(?:(?:ei|oi|ola|ok|entao|e ai|beleza|por favor|pfv|voce pode|vc pode|pode|consegue|"
          r"da pra|quero que voce|quero que|eu quero|quero|queria|me faz um favor|faz um favor|"
          r"faca|faz|me|ai|so)\b[\s,]*)+")

SHOP_ADD = (r"\b(?:adiciona\w*|adicione|coloca\w*|coloque|bota\w*|bote|poe|por|pode por|inclu\w*|"
            r"acrescent\w*|anota\w*|anote|compra(?!s)\w*|preciso(?: de)?|precisa(?: de)?|precisamos(?: de)?|"
            r"falta(?:ndo)?|acabou|acabaram|lembra de comprar|lembrar de comprar)\b")
SHOP_REMOVE = r"\b(?:remov\w*|exclu\w*|apag\w*|tir[ae]\w*|tira|risca\w*|deleta\w*|limpa)\b"
SHOP_DONE = r"\b(?:comprei|ja comprei|ja peguei|peguei|marca(?:r)? como comprad[oa]|ja tenho)\b"
SHOP_WORDS = r"\b(?:lista|listinha|compras?|mercado|supermercado|feira)\b"

AGENDA_ADD = (r"\b(?:agend\w*|marc\w*|anota\w*|anote|cria\w*|crie|lembra\w*|lembrete|"
              r"adiciona\w*|adicione|coloca\w*|bota\w*|poe|inclu\w*|salva\w*)\b")
AGENDA_REMOVE = r"\b(?:cancel\w*|desmarc\w*|remov\w*|exclu\w*|apag\w*|tir[ae]\w*|tira|deleta\w*)\b"
AGENDA_WORDS = (r"\b(?:agenda|compromissos?|evento|reuniao|consulta|dentista|medico|lembrete|"
                r"aniversario|horario|encontro|call|meet)\b")
QUERY = (r"\b(?:o que|oque|quais|qual|tem algo|tenho algo|lista(?:r)?|mostra\w*|le|leia|fala|"
         r"me diz|diz|ver|o que tem|tenho)\b")


def _strip_edges(text: str) -> str:
    text = re.sub(r"^[\s,.;:!?-]+|[\s,.;:!?-]+$", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text


def _clean_item(raw: str) -> str:
    """Tira artigos e palavras de ligação do começo/fim de um produto."""
    text = _strip_edges(raw)
    for _ in range(3):
        folded = _fold(text)
        m = re.match(r"^(?:o|a|os|as|um|uma|uns|umas|de|do|da|dos|das|mais|tambem|ai|ae)\s+", folded)
        if m:
            text = text[m.end():]
            continue
        m = re.search(r"\s+(?:tambem|ai|ae|por favor|pfv|pra mim|pra gente|ok|valeu)$", _fold(text))
        if m:
            text = text[:m.start()]
            continue
        break
    return _strip_edges(text)[:80]


def _split_items(raw: str) -> list[str]:
    parts = re.split(r",|;|\s+e\s+|\s+mais\s+", raw)
    items, seen = [], set()
    for part in parts:
        name = _clean_item(part)
        key = _fold(name)
        if name and key not in seen and len(key) > 1:
            seen.add(key)
            items.append(name)
    return items


def _items_after(original: str, folded: str, verb_pattern: str) -> str:
    m = re.search(verb_pattern, folded)
    rest = original[m.end():] if m else original
    rest_f = _fold(rest)
    cut = re.search(r"\b(?:(?:na|da|pra|para|a|à|no|do|em)\s+(?:minha\s+|nossa\s+|a\s+)?)?"
                    r"(?:lista|listinha)(?:\s+de\s+compras?)?\b|\b(?:(?:no|do|pro|para o)\s+)?(?:mercado|supermercado)\b",
                    rest_f)
    if cut:
        tail = rest[cut.end():]
        rest = rest[:cut.start()] + (" " + tail if not _fold(tail).strip().startswith(("por favor", "pfv")) else "")
    return rest


# ------------------------------------------------------------- lista de compras

def _shopping_add(names: list[str]) -> str:
    items = _read_list(SHOPPING_FILE)
    existing = {_fold(str(i.get("text", ""))): i for i in items}
    added, already = [], []
    for name in names:
        current = existing.get(_fold(name))
        if current and not current.get("done"):
            already.append(name)
            continue
        if current:  # estava riscado: volta pra lista
            current["done"] = False
            added.append(name)
            continue
        entry = {"id": str(time.time_ns()), "text": name, "done": False}
        items.append(entry)
        existing[_fold(name)] = entry
        added.append(name)
        time.sleep(0.001)
    if added:
        _write_list(SHOPPING_FILE, items)
    if added and not already:
        return _pick(f"Feito! {_cap(_join(added))} na lista.", f"Anotado: {_join(added)}.",
                     f"Pronto, {_join(added)} na lista.", f"Beleza, coloquei {_join(added)}.")
    if added:
        return f"Coloquei {_join(added)}. {_cap(_join(already))} já tava lá."
    return _pick(f"{_cap(_join(already))} já tá na lista.", f"Já tem {_join(already)} na lista.")


def _match_items(items: list[dict], name: str) -> list[dict]:
    key = _fold(name)
    exact = [i for i in items if _fold(str(i.get("text", ""))) == key]
    if exact:
        return exact
    return [i for i in items if key and (key in _fold(str(i.get("text", ""))) or _fold(str(i.get("text", ""))) in key)]


def _shopping_remove(names: list[str], mark_done: bool = False) -> str:
    items = _read_list(SHOPPING_FILE)
    if not items:
        return "A lista já tá vazia."
    if not mark_done and any(re.fullmatch(r"(?:tudo|todos?|todas?|a lista|lista toda|a lista toda)", _fold(n)) for n in names):
        _write_list(SHOPPING_FILE, [])
        return _pick("Pronto, lista zerada.", "Limpei a lista toda.")
    done, missing = [], []
    for name in names:
        hits = _match_items(items, name)
        if not hits:
            missing.append(name)
            continue
        target = hits[0]
        done.append(str(target.get("text")))
        if mark_done:
            target["done"] = True
        else:
            items = [i for i in items if i.get("id") != target.get("id")]
    if done:
        _write_list(SHOPPING_FILE, items)
    if not done:
        return f"Não achei {_join(missing)} na lista."
    msg = (_pick(f"Boa! Risquei {_join(done)}.", f"Show, {_join(done)} riscado.") if mark_done
           else _pick(f"Tirei {_join(done)}.", f"Pronto, {_join(done)} saiu da lista.", f"Feito, sem {_join(done)}."))
    return msg + (f" Não achei {_join(missing)}." if missing else "")


def _shopping_read() -> str:
    names = [str(i.get("text", "")) for i in _read_list(SHOPPING_FILE) if not i.get("done")]
    if not names:
        return _pick("A lista tá vazia.", "Nada na lista por enquanto.")
    if len(names) > 8:
        return f"Tem {len(names)} itens: {_join(names[:8])} e mais alguns."
    return f"Na lista: {_join(names)}."


# --------------------------------------------------------------------- agenda

def _agenda_title(original: str, folded: str, spans: list[tuple[int, int]]) -> str:
    text = original
    for span in spans:
        text = _blank(text, span)
    f = _fold(text)
    m = re.search(AGENDA_ADD, f)
    if m:
        text, f = text[m.end():], f[m.end():]
    # tira "na agenda", "um compromisso", "pra mim" etc.
    for pattern in (r"\b(?:na|da|pra|para a|a|minha)\s+agenda\b", r"^\s*(?:na|a)?\s*agenda\b",
                    r"\b(?:um|uma|o|a)\s+(?:compromisso|evento|lembrete)\s*(?:de|do|da|pra|para)?\b",
                    r"^\s*(?:compromisso|evento|lembrete)\s*(?:de|do|da|pra|para)?\b",
                    r"\b(?:pra mim|por favor|pfv)\b", r"^\s*(?:que|de|pra|para|um|uma|o|a)\b",
                    r"\b(?:para|pra|no|na|em|as|a|dia|de|do|da)\s*$"):
        for _ in range(2):
            mm = re.search(pattern, f)
            if mm:
                text = text[:mm.start()] + " " * (mm.end() - mm.start()) + text[mm.end():]
                f = _fold(text)
    title = _strip_edges(text)
    return _cap(title)[:120]


def _agenda_add(original: str, folded: str, now: datetime) -> str:
    today = now.date()
    found_date, dspan = _find_date(folded, today)
    found_time, tspan = _find_time(folded)
    title = _agenda_title(original, folded, [s for s in (dspan, tspan) if s])
    if not title:
        return "Beleza, mas qual é o compromisso? Fala tipo: dentista amanhã às 14h."
    if not found_time:
        return f"Que horas é {title.lower()}? Fala junto, tipo: {title.lower()} amanhã às 10."
    if not found_date:
        found_date = today
        if found_time <= now.strftime("%H:%M"):
            found_date = today + timedelta(days=1)
    items = _read_list(AGENDA_FILE)
    items.append({"id": str(time.time_ns()), "date": found_date.isoformat(), "time": found_time, "text": title})
    _write_list(AGENDA_FILE, items)
    when = f"{_date_label(found_date, today)} às {_time_label(found_time)}"
    return _pick(f"Marcado: {title.lower()} {when}.", f"Feito! {title} {when}.", f"Anotei {title.lower()} {when}.")


def _agenda_read(folded: str, today: date) -> str:
    day, _ = _find_date(folded, today)
    day = day or today
    events = sorted((e for e in _read_list(AGENDA_FILE) if e.get("date") == day.isoformat()),
                    key=lambda e: e.get("time", ""))
    label = _date_label(day, today)
    if not events:
        return _pick(f"Nada marcado pra {label}.", f"Agenda livre {label}.")
    parts = [f"{e.get('text', '').lower()} às {_time_label(e.get('time', '00:00'))}" for e in events]
    return f"{_cap(label)} tem {_join(parts)}."


def _agenda_remove(original: str, folded: str, today: date) -> str:
    found_date, dspan = _find_date(folded, today)
    found_time, tspan = _find_time(folded)
    m = re.search(AGENDA_REMOVE, folded)
    text = original[m.end():] if m else original
    offset = m.end() if m else 0
    for span in (dspan, tspan):
        if span and span[0] >= offset:
            text = _blank(text, (span[0] - offset, span[1] - offset))
    f = _fold(text)
    f = re.sub(r"\b(?:da|na|a)\s+agenda\b|\b(?:o|a|um|uma)\s+(?:compromisso|evento)\b|^\s*(?:o|a|os|as)\b", " ", f)
    key = _strip_edges(re.sub(r"\s+", " ", f))
    items = _read_list(AGENDA_FILE)
    upcoming = [e for e in items if e.get("date", "") >= today.isoformat()]
    hits = [e for e in upcoming if (not key or key in _fold(str(e.get("text", ""))))
            and (not found_date or e.get("date") == found_date.isoformat())
            and (not found_time or e.get("time") == found_time)]
    if not hits:
        return "Não achei esse compromisso na agenda."
    if len(hits) > 1 and not key:
        return "Tem mais de um, qual deles? Fala o nome."
    target = sorted(hits, key=lambda e: (e.get("date", ""), e.get("time", "")))[0]
    _write_list(AGENDA_FILE, [e for e in items if e.get("id") != target.get("id")])
    when = _date_label(date.fromisoformat(target["date"]), today)
    return _pick(f"Desmarcado: {str(target.get('text')).lower()} de {when}.",
                 f"Pronto, cancelei {str(target.get('text')).lower()}.")


# ------------------------------------------------------------------ roteador

def _reply(text: str) -> str:
    original = re.sub(r"\s+", " ", str(text or "")).strip()[:300]
    folded = _fold(original)
    m = re.match(FILLER, folded)
    if m and m.end() < len(folded):
        original, folded = original[m.end():], folded[m.end():]
    original, folded = original.strip(), folded.strip()
    if not folded:
        raise VoiceAssistantError("Não peguei. Fala de novo?")

    now = datetime.now().astimezone()
    today = now.date()

    if re.search(r"\b(?:ajuda|comandos|o que voce (?:sabe|consegue) fazer)\b", folded):
        return "Fala tipo: põe café na lista, tira o leite, o que tem na lista, ou marca dentista amanhã às 14."
    if re.fullmatch(r"(?:obrigad[oa]|valeu|vlw|brigad[oa]|tchau)\W*", folded):
        return _pick("Tamo junto!", "De nada!", "Valeu!")

    has_shop_word = bool(re.search(SHOP_WORDS, folded))
    has_agenda_word = bool(re.search(AGENDA_WORDS, folded))
    has_time = _find_time(folded)[0] is not None
    has_date = _find_date(folded, today)[0] is not None
    is_query = bool(re.search(QUERY, folded))

    # ---- agenda ("minha agenda", "na agenda" é substantivo, não o verbo agendar)
    verbs = re.sub(r"\b(?:minha|na|da|a|sua|tua|qual|qual a|qual e a|pra|para a)\s+agenda\b|^agenda\??$", " ", folded)
    if re.fullmatch(r"(?:minha |a )?agenda\W*", folded):
        return _agenda_read(folded, today)
    if re.search(r"\b(?:cancel\w*|desmarc\w*)\b", folded) and not has_shop_word:
        return _agenda_remove(original, folded, today)
    agenda_context = has_agenda_word or ((has_time or has_date) and not has_shop_word)
    if agenda_context:
        if re.search(AGENDA_REMOVE, verbs) and not re.search(r"\b(?:marc\w*|agend\w*)\b", verbs[:12]):
            return _agenda_remove(original, folded, today)
        adding = bool(re.search(AGENDA_ADD, verbs)) or has_time
        if is_query and not has_time and not re.search(r"\b(?:agend\w*|marc\w*|anota\w*|cria\w*|lembra\w*)\b", verbs):
            return _agenda_read(folded, today)
        if adding:
            return _agenda_add(original, folded, now)
        if is_query or has_date:
            return _agenda_read(folded, today)

    # ---- lista de compras
    if re.search(SHOP_DONE, folded):
        rest = original[re.search(SHOP_DONE, folded).end():]
        names = _split_items(_items_after(rest, _fold(rest), r"^"))
        return _shopping_remove(names, mark_done=True) if names else "Comprou o quê?"
    if re.search(SHOP_REMOVE, folded):
        rest = _items_after(original, folded, SHOP_REMOVE)
        names = _split_items(rest)
        if not names and re.search(r"\b(?:limpa|apaga|zera)\w*\b", folded) and has_shop_word:
            names = ["tudo"]
        return _shopping_remove(names) if names else "Tirar o quê da lista?"
    if is_query and has_shop_word and not re.search(SHOP_ADD, folded):
        return _shopping_read()
    if re.search(SHOP_ADD, folded):
        rest = _items_after(original, folded, SHOP_ADD)
        names = _split_items(rest)
        return _shopping_add(names) if names else "Beleza, mas o que eu coloco na lista?"
    if has_shop_word:
        # "lista: arroz e feijão" ou "na lista arroz"
        rest = _items_after(original, folded, r"^")
        names = _split_items(rest)
        return _shopping_add(names) if names else _shopping_read()

    return _pick("Não saquei. Tenta tipo: põe arroz na lista.",
                 "Hmm, não entendi. Posso mexer na lista e na agenda.")


def process_voice_command(text: str, previous_response_id: str | None = None) -> dict:
    del previous_response_id
    return {"reply": _reply(text), "response_id": None, "actions": []}
