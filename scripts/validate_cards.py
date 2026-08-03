#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка карточек каталога перед публикацией.

Автоматизирует список «Самопроверка перед публикацией» из docs/card-structure.md:
обязательные поля, допустимые этажи и коды задач, границы размера компании,
уникальность id, ссылочная целостность FULL и COMPOSITE.

Зависимостей нет — только стандартная библиотека Python 3.8+.

Использование:

    python3 scripts/validate_cards.py examples/card.json
    python3 scripts/validate_cards.py catalog.json --quiet

Входной файл — либо массив карточек, либо объект вида

    {"ITEMS": [...], "FULL": {...}, "COMPOSITE": {...}}

Ключи, начинающиеся с подчёркивания, игнорируются: они служат комментариями.

Код возврата: 0 — ошибок нет, 1 — есть ошибки, 2 — файл не прочитан.
"""

import argparse
import json
import sys

FLOORS = ("conf", "govconf", "serv", "tech", "host")
TASKS = ("acc", "trade", "hr", "mfg", "doc", "group", "gov")

REQUIRED = (
    "r", "k", "id", "c", "f", "min", "max",
    "w", "simple", "d", "g", "b", "dep", "its", "st",
)
OPTIONAL = ("ed", "partner", "note", "cv", "legacy")

# поле -> (мин. длина, макс. длина) для строк
STR_LIMITS = {
    "c": (2, 40),
    "f": (3, 60),
    "w": (10, 200),
    "simple": (40, 700),
    "d": (20, 700),
    "dep": (3, 60),
    "its": (2, 40),
    "st": (3, 60),
}

# поле -> (мин. пунктов, макс. пунктов) для списков
LIST_LIMITS = {
    "g": (1, 4),
    "b": (1, 3),
}

EDITION_REQUIRED = ("n", "sc", "t", "d", "y", "n2")
EDITION_LIST_LIMITS = {"y": (1, 4), "n2": (1, 3)}

# этажи, которые не привязаны к задаче и красятся нейтральным серым
NEUTRAL_FLOORS = ("tech", "host")


class Report:
    """Собирает ошибки и предупреждения с указанием карточки."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, where, message):
        self.errors.append("%s: %s" % (where, message))

    def warn(self, where, message):
        self.warnings.append("%s: %s" % (where, message))

    @property
    def ok(self):
        return not self.errors


def strip_comments(obj):
    """Убирает служебные ключи, начинающиеся с подчёркивания."""
    if isinstance(obj, dict):
        return {k: strip_comments(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [strip_comments(v) for v in obj]
    return obj


def check_id(card, where, rep):
    value = card.get("id")
    if not isinstance(value, str) or not value:
        rep.error(where, "поле id обязательно и должно быть строкой")
        return
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    if set(value) - allowed:
        rep.error(where, "id «%s»: только строчная латиница, цифры и подчёркивание" % value)
    if not 2 <= len(value) <= 24:
        rep.error(where, "id «%s»: длина должна быть от 2 до 24 знаков" % value)


def check_floor_and_tasks(card, where, rep):
    floor = card.get("r")
    if floor not in FLOORS:
        rep.error(where, "поле r: «%s» не входит в %s" % (floor, ", ".join(FLOORS)))

    tasks = card.get("k")
    if not isinstance(tasks, str) or not tasks:
        rep.error(where, "поле k обязательно и должно быть строкой")
        return

    if tasks != "all":
        for code in tasks.split(","):
            if code != code.strip():
                rep.error(where, "поле k: коды задач перечисляются без пробелов")
            if code.strip() not in TASKS:
                rep.error(where, "поле k: неизвестный код задачи «%s»" % code.strip())

    if floor in NEUTRAL_FLOORS:
        if tasks != "all":
            rep.warn(where, "этаж %s не привязан к задаче — обычно ставится k:\"all\"" % floor)
        if card.get("cv") != "ck":
            rep.warn(where, "этаж %s обычно красится нейтральным серым — cv:\"ck\"" % floor)


def check_size_range(card, where, rep):
    lo, hi = card.get("min"), card.get("max")
    for name, value in (("min", lo), ("max", hi)):
        if not isinstance(value, int) or isinstance(value, bool):
            rep.error(where, "поле %s должно быть целым числом" % name)
            return
        if not 1 <= value <= 10000:
            rep.error(where, "поле %s: значение %s вне диапазона 1..10000" % (name, value))
    if lo > hi:
        rep.error(where, "min (%s) больше max (%s)" % (lo, hi))


def check_strings(card, where, rep):
    for field, (lo, hi) in STR_LIMITS.items():
        value = card.get(field)
        if not isinstance(value, str):
            rep.error(where, "поле %s должно быть строкой" % field)
            continue
        text = value.strip()
        if not lo <= len(text) <= hi:
            rep.error(where, "поле %s: длина %s знаков, ожидается %s..%s" % (field, len(text), lo, hi))
    if isinstance(card.get("f"), str) and card["f"].strip().endswith("."):
        rep.error(where, "поле f: подзаголовок пишется без точки в конце")


def check_lists(card, where, rep, limits=LIST_LIMITS):
    for field, (lo, hi) in limits.items():
        value = card.get(field)
        if not isinstance(value, list):
            rep.error(where, "поле %s должно быть массивом строк" % field)
            continue
        if not lo <= len(value) <= hi:
            rep.error(where, "поле %s: %s пунктов, ожидается %s..%s" % (field, len(value), lo, hi))
        for item in value:
            if not isinstance(item, str) or not item.strip():
                rep.error(where, "поле %s: пункты должны быть непустыми строками" % field)


def check_editions(card, where, rep):
    editions = card.get("ed")
    if editions is None:
        return
    if not isinstance(editions, list):
        rep.error(where, "поле ed должно быть массивом редакций")
        return
    if len(editions) < 2:
        rep.error(where, "поле ed: одна редакция не заводится — либо две и больше, либо поля нет")
    for i, edition in enumerate(editions, 1):
        sub = "%s → редакция %s" % (where, i)
        if not isinstance(edition, dict):
            rep.error(sub, "редакция должна быть объектом")
            continue
        for field in EDITION_REQUIRED:
            if field not in edition:
                rep.error(sub, "нет обязательного поля %s" % field)
        check_lists(edition, sub, rep, EDITION_LIST_LIMITS)


def check_unknown_fields(card, where, rep):
    known = set(REQUIRED) | set(OPTIONAL)
    for field in sorted(set(card) - known):
        rep.warn(where, "неизвестное поле «%s» — опечатка?" % field)


def check_card(card, index, rep):
    where = "карточка #%s" % index
    if not isinstance(card, dict):
        rep.error(where, "карточка должна быть объектом")
        return
    if isinstance(card.get("id"), str) and card["id"]:
        where = "карточка «%s»" % card["id"]

    for field in REQUIRED:
        if field not in card:
            rep.error(where, "нет обязательного поля %s" % field)

    check_id(card, where, rep)
    check_floor_and_tasks(card, where, rep)
    check_size_range(card, where, rep)
    check_strings(card, where, rep)
    check_lists(card, where, rep)
    check_editions(card, where, rep)
    check_unknown_fields(card, where, rep)

    if card.get("legacy") not in (None, 1):
        rep.error(where, "поле legacy принимает только значение 1")


def check_catalog(items, full, composite, rep):
    """Проверки, которые видны только на всём каталоге целиком."""
    seen = {}
    for i, card in enumerate(items, 1):
        if not isinstance(card, dict):
            continue
        cid = card.get("id")
        if not isinstance(cid, str) or not cid:
            continue
        if cid in seen:
            rep.error("карточка «%s»" % cid, "id уже занят карточкой #%s" % seen[cid])
        else:
            seen[cid] = i

    for cid in sorted(full or {}):
        if cid not in seen:
            rep.error("FULL", "полное название задано для несуществующей карточки «%s»" % cid)

    for name, ids in sorted((composite or {}).items()):
        if not isinstance(ids, list):
            rep.error("COMPOSITE", "набор «%s» должен быть списком id" % name)
            continue
        for cid in ids:
            if cid not in seen:
                rep.error("COMPOSITE", "набор «%s» ссылается на несуществующий id «%s»" % (name, cid))

    return seen


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = strip_comments(json.load(handle))

    if isinstance(data, list):
        return data, {}, {}
    if isinstance(data, dict):
        if "ITEMS" in data:
            return data.get("ITEMS") or [], data.get("FULL") or {}, data.get("COMPOSITE") or {}
        return [data], {}, {}
    raise ValueError("ожидается массив карточек или объект с ключом ITEMS")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Проверяет карточки каталога 1С перед публикацией.",
    )
    parser.add_argument("path", help="JSON с карточками: массив либо объект с ITEMS/FULL/COMPOSITE")
    parser.add_argument("-q", "--quiet", action="store_true", help="не показывать предупреждения")
    args = parser.parse_args(argv)

    try:
        items, full, composite = load(args.path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("Не удалось прочитать %s: %s" % (args.path, exc), file=sys.stderr)
        return 2

    rep = Report()
    for i, card in enumerate(items, 1):
        check_card(card, i, rep)
    ids = check_catalog(items, full, composite, rep)

    if rep.warnings and not args.quiet:
        print("Предупреждения:")
        for line in rep.warnings:
            print("  ~ %s" % line)
        print()

    if rep.errors:
        print("Ошибки:")
        for line in rep.errors:
            print("  ! %s" % line)
        print()
        print("Проверено карточек: %s. Ошибок: %s." % (len(items), len(rep.errors)))
        return 1

    print("Проверено карточек: %s, уникальных id: %s. Ошибок нет." % (len(items), len(ids)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
