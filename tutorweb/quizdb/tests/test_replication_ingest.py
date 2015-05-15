import unittest

from ..replication.ingest import findMissingEntries

class TestfindMissingEntries(unittest.TestCase):
    maxDiff = None

    def asList(self, iter):
        """Convert iterator to list, but bail out"""
        out = []
        for x, y in iter:
            out.append(x)
            if len(out) > 100:
                out.append("Too many entries!")
                return out
        return out

    def asTwoLists(self, iter):
        """Convert iterator into 2 lists, one for each half"""
        out = [[], []]
        for x, y in iter:
            out[0].append(x)
            out[1].append(x)
            if len(out[0]) > 100:
                out[0].append("Too many entries!")
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

    def returnUpdates(self):
        """Can get updates returned too"""
        self.assertEqual(self.asTwoLists(findMissingEntries(
            [dict(a=1,x=2),               dict(a=3,x=9), dict(a=4,x=3), dict(a=5,x=1)],
            [              dict(a=2,x=3), dict(a=3,x=3), dict(a=3,x=8)               ],
            sortCols=['a', 'b'],
            returnUpdates=True,
        )), [
            [dict(a=1,x=2),               dict(a=3,x=9), dict(a=4,x=3), dict(a=5,x=1)],
            [None,                        dict(a=3,x=3), dict(a=3,x=8), None         ],
        ])
