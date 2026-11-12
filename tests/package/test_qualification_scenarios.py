"""Scénarios de qualification v9 : figés avant tout essai et jugeables tels qu'écrits.

Lancer depuis la racine du dépôt : python -B -m unittest tests/package/test_qualification_scenarios.py

Contrôle structurel seulement : aucun agent n'est exécuté et rien ne mesure sa conduite.
Modifier un scénario, une option ou un oracle exige un nouveau fichier et une nouvelle
empreinte, jamais une mise à jour silencieuse de V9_SHA256.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION = ROOT / 'tests' / 'qualification'
V9 = QUALIFICATION / 'scenarios-v9.json'
V9_SHA256 = '8f054c906bb4f64bf39d416bfb0ba81c9e3a2b608c0d83bd23c3a9bdcfd19d0d'
# Révision r1 : oracle Q14 symétrique, utilisée pour corriger l'épreuve exploratoire du 2026-11-10.
V9_R1 = QUALIFICATION / 'scenarios-v9-r1.json'
V9_R1_SHA256 = '8b998599c146b3a889652eca01dbcd9595ab26e1e3bf087db5c762d29d6e3f52'
NEW_IDS = ['Q12-jardin-declencheur', 'Q13-jardin-arret', 'Q14-elagage-test-redondant', 'Q15-invariant-securite',
           'Q16-attente-sans-reveil', 'Q17-verrou-auto-impose', 'Q18-troisieme-tour', 'Q19-acceptation-risque-bas',
           'Q20-ready-vide-backlog', 'Q21-cliquet-tests']

_spec = importlib.util.spec_from_file_location('rc_update_skills', ROOT / 'tools' / 'rc_update.py')
_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_registry)


def load(path):
    return json.loads(path.read_bytes().decode('utf-8'))


class ScenarioTests(unittest.TestCase):
    def test_v9_scenarios_frozen_before_trials(self):
        self.assertEqual(hashlib.sha256(V9.read_bytes()).hexdigest(), V9_SHA256)
        doc = load(V9)
        self.assertEqual((doc['format'], doc['release']), ('rc-qualification-scenarios/2', 'v9'))
        self.assertIn('Aucun essai', doc['status'])
        self.assertEqual(hashlib.sha256(V9_R1.read_bytes()).hexdigest(), V9_R1_SHA256)
        r1 = load(V9_R1)
        self.assertIn('Révision r1', r1['purpose'])
        changed = [a['id'] for a, b in zip(doc['scenarios'], r1['scenarios']) if a != b]
        self.assertEqual(changed, ['Q14-elagage-test-redondant'])
        q14 = [(a, b) for a, b in zip(doc['scenarios'], r1['scenarios']) if a != b][0]
        self.assertEqual({k: v for k, v in q14[0].items() if k != 'oracle'},
                         {k: v for k, v in q14[1].items() if k != 'oracle'})

    def test_v8_cases_carried_unchanged(self):
        v8 = load(QUALIFICATION / 'scenarios-v8.json')['scenarios']
        self.assertEqual(load(V9)['scenarios'][:len(v8)], v8)
        self.assertEqual(load(V9_R1)['scenarios'][:len(v8)], v8)

    def test_new_cases_judgeable(self):
        for path in (V9, V9_R1):
            scenarios = load(path)['scenarios']
            ids = [s['id'] for s in scenarios]
            self.assertEqual(len(ids), len(set(ids)))
            new = [s for s in scenarios if s['id'] in NEW_IDS]
            self.assertEqual([s['id'] for s in new], NEW_IDS)
            self.assertEqual({s['kind'] for s in new}, {'decision', 'manipulation'})
            for s in scenarios:
                with self.subTest(s['id']):
                    self.assertTrue(s['situation'] and s['oracle']['must'] and s['oracle']['must_not'])
                    self.assertTrue(set(s['skills']) <= set(_registry.ALL_SKILLS))
            for s in new:
                with self.subTest(s['id']):
                    if s['kind'] == 'decision':
                        options = [o['id'] for o in s['options']]
                        self.assertGreaterEqual(len(options), 2)
                        self.assertEqual(len(options), len(set(options)))
                        self.assertTrue(s['oracle']['expected_options'])
                        self.assertLessEqual(set(s['oracle']['expected_options']), set(options))
                        self.assertTrue(all(o['text'] for o in s['options']))
                    else:
                        self.assertEqual(s['kind'], 'manipulation')
                        self.assertNotIn('options', s)  # jugé sur les observables, pas sur un choix
                        self.assertTrue(s['setup'] and s['observables'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
