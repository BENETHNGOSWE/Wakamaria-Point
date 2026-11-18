import unittest
from datetime import datetime, timezone, timedelta
from wakamaria.goal_scores import regulation_score
from wakamaria.rules import evaluate

K = datetime(2026,11,17,19,45,tzinfo=timezone.utc)
NOW = K + timedelta(hours=3)
def payload():
    return {'matchStatus':'FINISHED','kickoffUtc':'2026-11-17T19:45:00Z', 'homeTeamFtScore':'1','awayTeamFtScore':'1','homeTeamScore':'1','awayTeamScore':'1'}

class ScoreTest(unittest.TestCase):
    def test_valid_score_and_zero(self):
        self.assertEqual(regulation_score(payload(),NOW),(1,1))
        p=payload();p.update(homeTeamFtScore='0',awayTeamFtScore='0',homeTeamScore='0',awayTeamScore='0')
        self.assertEqual(regulation_score(p,NOW),(0,0))
    def test_five_example_predictions(self):
        for h, a, tip, outcome in [(2,3,'12','Win'),(1,1,'Under 2.5','Win'),
                                   (3,0,'1X','Win'),(1,1,'Over 2.5','Lose'),(1,1,'12','Lose')]:
            p=payload();p.update(homeTeamFtScore=str(h),awayTeamFtScore=str(a),homeTeamScore=str(h),awayTeamScore=str(a))
            self.assertEqual(evaluate(tip,*regulation_score(p,NOW)),outcome)

    def test_status_and_time(self):
        for status in ['LIVE','AFTER_ET','AFTER_PEN','AWARDED','POSTPONED','CANCELLED']:
            p=payload();p['matchStatus']=status;self.assertIsNone(regulation_score(p,NOW))
        self.assertIsNone(regulation_score(payload(),K+timedelta(minutes=119)))
        self.assertIsNone(regulation_score(payload(),datetime(2026,11,18)))
    def test_inconsistent_missing_extra_and_invalid(self):
        for changes in ({'homeTeamScore':'0'},{'homeTeamFtScore':None},{'homeTeamFtScore':True},
                        {'homeTeamExtraScore':'0'},{'awayTeamPenaltyScore':'1'},
                        {'matchPeriod':'EXTRA_TIME'},{'homeTeamHtScore':'3'},{'awayTeamFtScore':'-1'}):
            p=payload();p.update(changes);self.assertIsNone(regulation_score(p,NOW))

if __name__ == '__main__': unittest.main()
