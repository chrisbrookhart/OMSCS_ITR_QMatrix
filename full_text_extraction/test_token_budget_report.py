"""Budget recommendations require complete comparable samples and headroom."""
import unittest
import token_budget_report as report


def observation(budget: int, output: int, source: str = 'synthetic.pdf',
                status: str = 'extracted', effort: str = 'max') -> report.Observation:
    return report.Observation(run='synthetic-run', source=source, reasoning_effort=effort,
        token_limit=budget, job_status=status, output_tokens=output,
        response_status='completed' if status == 'extracted' else 'incomplete')


class TokenBudgetTests(unittest.TestCase):
    def test_smallest_successful_budget_with_headroom_is_selected(self) -> None:
        rows = [observation(14000, 14000, status='error'), observation(24000, 21000),
                observation(36000, 22000), observation(48000, 23000)]
        self.assertEqual(report.recommend_budget(rows), 36000)

    def test_incomplete_or_absent_usage_cannot_be_recommended(self) -> None:
        self.assertIsNone(report.recommend_budget([observation(14000, 14000, status='error')]))
        self.assertIsNone(report.recommend_budget([observation(24000, 0)]))

    def test_all_sample_papers_must_be_present(self) -> None:
        rows = [observation(14000, 10000), observation(24000, 10000),
                observation(24000, 11000, source='second.pdf')]
        self.assertEqual(report.recommend_budget(rows), 24000)

    def test_historical_low_effort_does_not_affect_max_recommendation(self) -> None:
        rows = [observation(14000, 9000, effort='low'), observation(24000, 24000, status='error')]
        self.assertIsNone(report.recommend_budget(rows))

    def test_derived_headroom_is_distinguished_from_tested_budget(self) -> None:
        rows = [observation(36000, 36000, status='error'), observation(64000, 58879)]
        self.assertIsNone(report.recommend_budget(rows))
        self.assertEqual(report.recommend_budget(rows, headroom_fraction=0), 64000)
        self.assertEqual(report.provisioned_budget(rows), 80000)


if __name__ == '__main__':
    unittest.main()
