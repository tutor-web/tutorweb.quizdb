import unittest

from ..replication.ingest import findMatchingEntries

#class TestFindMatchingEntries(unittest.TestCase):
#    maxDiff = None
#
#    def asList(self, iter):
#        """Convert iterator to list, but bail out"""
#        out = []
#        for x in iter:
#            out.append(x)
#            if len(out) > 100:
#                out.append("Too many entries!")
#                return out
#        return out
#
#    def test_EmptyEntries(self):
#        """Empty lists generate no results"""
#        self.assertEqual(
#            self.asList(findMatchingEntries(iter([]), iter([]), ['colA', 'colB'])),
#            [],
#        )
#        self.assertEqual(
#            self.asList(findMatchingEntries(iter([dict(colA=2, colB=3)]), iter([]), ['colA', 'colB'])),
#            [],
#        )
#        self.assertEqual(
#            self.asList(findMatchingEntries(iter([]), iter([dict(colA=3, colB=5)]), ['colA', 'colB'])),
#            [],
#        )
#
#    def test_multipleColumns(self):
#        """Can sort by multiple columns"""
#        self.assertEqual(
#            self.asList(findMatchingEntries(iter([
#                dict(colA=1, colB=1, colC=3, entry="a"),
#                dict(colA=1, colB=2, colC=4, entry="b"),
#                dict(colA=1, colB=3, colC=2, entry="c"),
#                dict(colA=2, colB=1, colC=1, entry="d"),
#                dict(colA=2, colB=2, colC=4, entry="e"),
#                dict(colA=2, colB=3, colC=8, entry="f"),
#            ]), iter([
#                dict(colA=1, colB=2, colC=4, entry="A"),
#                dict(colA=1, colB=2, colC=5, entry="B"),
#                dict(colA=1, colB=6, colC=1, entry="C"),
#                dict(colA=2, colB=2, colC=4, entry="D"),
#                dict(colA=2, colB=2, colC=8, entry="E"),
#                dict(colA=2, colB=3, colC=8, entry="F"),
#            ]),['colA', 'colB', 'colC'])),
#            [
#                (dict(colA=1, colB=2, colC=4, entry="b"), dict(colA=1, colB=2, colC=4, entry="A")),
#                (dict(colA=2, colB=2, colC=4, entry="e"), dict(colA=2, colB=2, colC=4, entry="D")),
#                (dict(colA=2, colB=3, colC=8, entry="f"), dict(colA=2, colB=3, colC=8, entry="F")),
#            ],
#        )
#
#    def test_repeatedEntries(self):
#        """Repeated entries are ignored"""
#        self.assertEqual(
#            self.asList(findMatchingEntries(iter([
#                dict(col=1, entry="a"),
#                dict(col=2, entry="b"),
#                dict(col=4, entry="c"),
#                dict(col=5, entry="d"),
#                dict(col=8, entry="e"),
#                dict(col=8, entry="f"),
#                dict(col=8, entry="g"),
#                dict(col=9, entry="h"),
#            ]), iter([
#                dict(col=2, entry="A"),
#                dict(col=4, entry="B"),
#                dict(col=6, entry="C"),
#                dict(col=8, entry="D"),
#            ]),['col'])),
#            [
#                (dict(col=2, entry="b"), dict(col=2, entry="A")),
#                (dict(col=4, entry="c"), dict(col=4, entry="B")),
#                (dict(col=8, entry="e"), dict(col=8, entry="D")),
#            ],
#        )
