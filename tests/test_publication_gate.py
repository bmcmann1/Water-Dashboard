import datetime as dt
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('publication_gate', pathlib.Path('scripts/publication_gate.py'))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
NOW = dt.datetime(2026, 9, 29, 23, 40, tzinfo=dt.timezone.utc)


def fixture(observation_age=1, forecast_only=False):
    stamp = (NOW - dt.timedelta(hours=observation_age)).isoformat()
    nodes = {}
    for i in range(42):
        noaa = {'forecast': [{'time': NOW.isoformat(), 'value': 99}]}
        if not forecast_only and i < 20:
            noaa['observed'] = [{'time': stamp, 'value': 12.5}]
        nodes[str(i)] = {'noaa': noaa}
    return {'nodes': nodes}, {'node_count': 42}


class PublicationGateTests(unittest.TestCase):
    def test_actual_normalized_noaa_schema_passes(self):
        network, qc = fixture()
        self.assertEqual(len(gate.evaluate(network, qc, 12000, NOW)), 20)

    def test_stale_observations_do_not_pass(self):
        network, qc = fixture(observation_age=25)
        with self.assertRaisesRegex(ValueError, 'Only 0 fresh'):
            gate.evaluate(network, qc, 12000, NOW)

    def test_forecast_cannot_satisfy_observation_gate(self):
        network, qc = fixture(forecast_only=True)
        with self.assertRaisesRegex(ValueError, 'Only 0 fresh'):
            gate.evaluate(network, qc, 12000, NOW)

    def test_bad_dashboard_blocks_deploy(self):
        network, qc = fixture()
        with self.assertRaisesRegex(ValueError, 'Dashboard'):
            gate.evaluate(network, qc, 0, NOW)

    def test_missing_nodes_blocks_deploy(self):
        network, qc = fixture()
        network['nodes'].pop('0')
        with self.assertRaisesRegex(ValueError, 'Expected 42'):
            gate.evaluate(network, qc, 12000, NOW)
