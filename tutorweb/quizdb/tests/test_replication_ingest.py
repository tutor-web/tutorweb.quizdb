import unittest

from ..replication.ingest import findMissingEntries

# TODO: def findMissingEntries(dataRawEntries, dbQuery, sortCols=[], ignoreCols=[], idMap={}):
class TestfindMissingEntries(unittest.TestCase):
    maxDiff = None

    def asList(self, iter):
        """Convert iterator to list, but bail out"""
        out = []
        for x in iter:
            out.append(x)
            if len(out) > 100:
                out.append("Too many entries!")
                return out
        return out

    def test_emptyData(self):
        """No data generates no results"""
        self.assertEqual(self.asList(findMissingEntries(
            [],
            [],
            sortCols=['a', 'b']
        )), [])

        self.assertEqual(self.asList(findMissingEntries(
            [],
            [dict(a=1,b=2), dict(a=1,b=3)],
            sortCols=['a', 'b']
        )), [])

    def test_ignoreCols(self):
        """Ignore cols don't appear in output"""
        self.assertEqual(self.asList(findMissingEntries(
            [dict(a=1,b=2,c=3)],
            [],
            sortCols=['a', 'b'],
        )), [dict(a=1,b=2,c=3),])

        self.assertEqual(self.asList(findMissingEntries(
            [dict(a=1,b=2,c=3)],
            [],
            sortCols=['a', 'b'],
            ignoreCols=['c'],
        )), [dict(a=1,b=2)])

    def test_dataMerging(self):
        """Missing data is noticed"""
        # Extra data at beginning and end
        self.assertEqual(self.asList(findMissingEntries(
            [dict(a=1,b=2,c=3), dict(a=1,b=3,c=3),                    dict(a=1,b=5,c=3), dict(a=2,b=1,c=3), dict(a=2,b=2,c=3)],
            [                                      dict(a=1,b=4,c=3), dict(a=1,b=5,c=3),                                     ],
            sortCols=['a', 'b'],
        )), [dict(a=1,b=2,c=3), dict(a=1,b=3,c=3),                                       dict(a=2,b=1,c=3), dict(a=2,b=2,c=3)])

        # Data interleaved
        self.assertEqual(self.asList(findMissingEntries(
            [dict(a=1,b=2,c=3),                                       dict(a=2,b=1,c=3), dict(a=4,b=1,c=3)                   ],
            [                   dict(a=1,b=4,c=3), dict(a=1,b=5,c=3),                                       dict(a=4,b=4,c=3)],
            sortCols=['a', 'b'],
        )), [dict(a=1,b=2,c=3),                                       dict(a=2,b=1,c=3), dict(a=4,b=1,c=3)                   ])

    def test_sortCols(self):
        """Matching sortCols are ignored"""
        self.assertEqual(self.asList(findMissingEntries(
            [dict(a=1,b=2,c=3), dict(a=1,b=3,c=3)],
            [dict(a=1,b=2,c=5), dict(a=1,b=3,c=6)],
            sortCols=['a', 'b'],
        )), [])
        self.assertEqual(self.asList(findMissingEntries(
            [dict(a=1,b=2,c=3), dict(a=1,b=3,c=3)],
            [dict(a=1,b=2,c=3), ],
            sortCols=['a'],
        )), [])
