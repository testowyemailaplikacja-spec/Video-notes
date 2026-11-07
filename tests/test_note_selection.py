"""Exact behavior regression for fast, source-only note quote selection.

The reference deliberately retains the original slow greedy scoring rule.
No source media, ASR model, network requests or user transcripts are used.
"""
from __future__ import annotations

import random
import unittest
from collections import Counter

from videonotes.notes import _select, _tokens


def _original_select(group: list[dict], limit: int) -> list[dict]:
    """Unoptimized pre-change reference, kept only in tests."""
    if len(group) <= limit:
        return group
    counts = Counter(token for row in group for token in _tokens(row["text"]))
    chosen = {0, len(group) - 1}
    while len(chosen) < limit:
        def score(i: int) -> tuple[float, int]:
            terms = _tokens(group[i]["text"])
            lexical = sum(counts[w] for w in terms) / max(len(terms), 1)
            distance = min(abs(group[i]["start_ms"] - group[j]["start_ms"])
                           for j in chosen)
            return (lexical + min(distance / 60_000, 10), distance)
        chosen.add(max((i for i in range(len(group)) if i not in chosen), key=score))
    return [group[i] for i in sorted(chosen)]


class SourceQuoteSelectionTest(unittest.TestCase):
    def test_equivalent_to_original_scoring_across_windows_languages_and_ties(self):
        rng = random.Random(20261107)
        phrases = (
            "router sieć DHCP", "NAT VLAN trunk port", "BGP and the next hop",
            "tcp udp TCP", "Ala ma kota", "źródło ąęółż", "",
            "i a oraz tak to", "samotność to nie instrukcja",
            "2000 4000 6000", "A więc chodzi o adres routera",
            "serwer i klient dhcp", "?", "# [test](x)", "80 80 80",
        )
        for n in (3, 4, 5, 9, 19, 80, 151):
            for trial in range(6):
                times = []
                current = 0
                for i in range(n):
                    current += rng.choice((0, 0, 70, 1500, 30_000, 120_000))
                    times.append(current)
                rows = [{"id": f"s{i:05d}", "start_ms": times[i],
                         "text": rng.choice(phrases) + (" DHCP" if trial == 2 else "")}
                        for i in range(n)]
                for limit in (2, 3, 4, 6, 10, 20):
                    with self.subTest(n=n, trial=trial, limit=limit):
                        expected = [row["id"] for row in _original_select(rows, limit)]
                        actual = [row["id"] for row in _select(rows, limit)]
                        self.assertEqual(actual, expected)
                        self.assertEqual(actual, sorted(actual))
        self.assertIs(_select(rows, len(rows)), rows)

    def test_fifty_thousand_segments_returns_source_only_and_does_not_mutate(self):
        words = (
            "router", "switch", "adresowanie", "dhcp", "vlan", "firewall",
            "nauka", "bezpieczeństwo", "pakiety", "sieć",
        )
        rows = [{"id": f"seg-{i:06d}", "start_ms": i * 30,
                 "text": f"{words[i % len(words)]} {words[(i * 7) % len(words)]} wykład"}
                for i in range(50_000)]
        first, middle, last = rows[0].copy(), rows[25_000].copy(), rows[-1].copy()
        selected = _select(rows, 20)
        self.assertEqual(len(selected), 20)
        self.assertIs(selected[0], rows[0])
        self.assertIs(selected[-1], rows[-1])
        self.assertEqual(len({row["id"] for row in selected}), 20)
        self.assertTrue(all(selected[i]["start_ms"] < selected[i + 1]["start_ms"]
                            for i in range(19)))
        self.assertEqual(rows[0], first)
        self.assertEqual(rows[25_000], middle)
        self.assertEqual(rows[-1], last)
        self.assertTrue(all(row in rows for row in selected))


if __name__ == "__main__":
    unittest.main()
