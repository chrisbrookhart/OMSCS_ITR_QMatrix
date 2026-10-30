"""Deterministic pacing checks without sleeping or sending API requests."""
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock

import admission
import pipeline
import test_extract as fixtures


class RequestPacerTests(unittest.TestCase):
    def test_large_paper_requests_are_spaced_with_reserve(self) -> None:
        pacer = admission.RequestPacer(2_000_000, clock=lambda: 0.0)
        self.assertEqual([pacer.reserve_delay(80_000) for _ in range(4)], [0, 3, 6, 9])

    def test_concurrent_reservations_do_not_overlap(self) -> None:
        pacer = admission.RequestPacer(2_000_000, clock=lambda: 0.0)
        with ThreadPoolExecutor(max_workers=8) as executor:
            delays = list(executor.map(pacer.reserve_delay, [80_000] * 8))
        self.assertEqual(sorted(delays), [3 * index for index in range(8)])

    def test_idle_time_does_not_accumulate_a_burst(self) -> None:
        clock = Mock(side_effect=[0.0, 0.0, 100.0, 100.0])
        pacer = admission.RequestPacer(2_000_000, clock=clock)
        self.assertEqual(pacer.reserve_delay(80_000), 0)
        self.assertEqual(pacer.reserve_delay(80_000), 0)
        self.assertEqual(pacer.reserve_delay(80_000), 3)

    def test_estimate_covers_output_ceiling_and_long_inputs(self) -> None:
        settings = fixtures.settings().model_copy(update={'max_output_tokens': 80000})
        self.assertEqual(admission.estimated_request_tokens(settings, 'short'), 80000)
        self.assertGreater(admission.estimated_request_tokens(settings, 'x' * 300000), 100000)

    def test_invalid_limits_and_reservations_fail_explicitly(self) -> None:
        with self.assertRaises(ValueError):
            admission.RequestPacer(0)
        with self.assertRaises(ValueError):
            admission.RequestPacer(2_000_000).reserve_delay(0)

    def test_high_concurrency_requires_pacing(self) -> None:
        with self.assertRaisesRegex(ValueError, 'explicit tokens_per_minute'):
            pipeline.resolve_token_rate(None, None, 110)
        self.assertEqual(pipeline.resolve_token_rate(2_000_000, None, 110), 2_000_000)


if __name__ == '__main__':
    unittest.main()
