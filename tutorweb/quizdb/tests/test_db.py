import unittest

from tutorweb.quizdb import db

class LectureGlobalSettingTest(unittest.TestCase):
    def test_equivalent(self):
        def lgs(**kwargs):
            return db.LectureGlobalSetting(lectureId=1, key="x", **kwargs)

        # Defaults are equivalent
        self.assertEqual(lgs().equivalent(lgs()), True)

        # Value is equivalent if the string matches
        self.assertEqual(lgs(value="x").equivalent(lgs(value=None)), False)
        self.assertEqual(lgs(value=None).equivalent(lgs(value="x")), False)
        self.assertEqual(lgs(value="x").equivalent(lgs(value="Y")), False)
        self.assertEqual(lgs(value="x").equivalent(lgs(value="x")), True)

        # Float params are equivalent if they're just about the same
        self.assertEqual(lgs(max=0.4).equivalent(lgs(max=None)), False)
        self.assertEqual(lgs(max=None).equivalent(lgs(max=0.4)), False)
        self.assertEqual(lgs(max=0.4).equivalent(lgs(max=0.4)), True)
        self.assertEqual(lgs(max=0.4).equivalent(lgs(max=0.4000000001)), True)
