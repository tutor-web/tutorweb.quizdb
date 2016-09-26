from zope.testing.loggingsupport import InstalledHandler

from .base import IntegrationTestCase, FunctionalTestCase

class LogErrorViewTest(IntegrationTestCase):
    def setUp(self):
        """Set up a class ready for testing"""
        self.loghandlers = dict(
            errorlog=InstalledHandler('tutorweb.quizdb.browser')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def test_logging(self):
        view = self.layer['portal'].unrestrictedTraverse('@@quizdb-logerror')

        # Log something
        self.assertEqual(view.asDict(dict(parp="yes", peep="no")), dict(
            logged=True,
        ))
        self.assertEqual(self.logs('errorlog'), [
            'Clientside error (user: "test-user") (user-agent: "unknown"):\n{ \'parp\': \'yes\', \'peep\': \'no\'}'
        ])
