import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from .scheduling import scheduled_periods, streak, successful


class SchedulingTests(unittest.TestCase):
    def test_daily_selected_days(self):
        start=date(2026,11,28)  # Saturday
        self.assertEqual(list(scheduled_periods(start,7,'daily',{'weekdays':[5,0]})),[(start,start,1),(start+timedelta(days=2),start+timedelta(days=2),1)])

    def test_weekly_clipped(self):
        rows=list(scheduled_periods(date(2026,11,26),5,'weekly',{'occurrences':3}))
        self.assertEqual(rows,[(date(2026,11,26),date(2026,11,27),2),(date(2026,11,28),date(2026,11,30),3)])

    def test_monthly_leap(self):
        rows=list(scheduled_periods(date(2028,2,28),4,'monthly',{'occurrences':5}))
        self.assertEqual(rows,[(date(2028,2,28),date(2028,2,29),2),(date(2028,3,1),date(2028,3,2),2)])

    def test_flexible_one_rest_preserves_not_increments(self):
        start=date(2026,11,28)
        def rows(policy):
            return [(start+timedelta(days=i),start+timedelta(days=i),ok,policy,'daily') for i,ok in enumerate([True,False,True,False,True])]
        self.assertEqual(streak(rows('flexible')[:3],start+timedelta(days=3)),(2,2))
        self.assertEqual(streak(rows('flexible'),start+timedelta(days=5)),(1,2))
        self.assertEqual(streak(rows('strict'),start+timedelta(days=5)),(1,1))

    def test_open_period_not_failure(self):
        day=date(2026,11,28)
        rows=[(day,day,True,'strict','daily'),(day+timedelta(days=1),day+timedelta(days=1),False,'strict','daily')]
        self.assertEqual(streak(rows,day+timedelta(days=1)),(1,1))
        self.assertEqual(streak(rows,day+timedelta(days=2)),(0,1))

    def test_goal_semantics(self):
        version=SimpleNamespace(goal_type='count',comparison='lte',target_value=Decimal('2'))
        self.assertTrue(successful(version,SimpleNamespace(numeric_delta=Decimal('0'))))
        self.assertFalse(successful(version,SimpleNamespace(numeric_delta=Decimal('3'))))
        version=SimpleNamespace(goal_type='binary',binary_success=False)
        self.assertTrue(successful(version,SimpleNamespace(binary_value=False)))
        self.assertFalse(successful(version,SimpleNamespace(binary_value=True)))
