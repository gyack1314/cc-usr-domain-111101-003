import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CliTests(unittest.TestCase):
    def test_real_inspection(self):
        result=subprocess.run([sys.executable,'-m','datapack.cli','inspect','samples'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['files'])
    def test_invalid_path_is_failure(self):
        result=subprocess.run([sys.executable,'-m','datapack.cli','inspect','missing-directory'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,'')

class CliSplitTests(unittest.TestCase):
    def run_cli(self,args):
        return subprocess.run([sys.executable,'-m','datapack.cli',*args],cwd=ROOT,capture_output=True,text=True)
    def test_roundtrip_and_idempotent_revision(self):
        with tempfile.TemporaryDirectory() as d:
            store=str(Path(d)/'s.sqlite3')
            first=self.run_cli(['split','samples','--store',store])
            self.assertEqual(first.returncode,0,first.stderr)
            doc=json.loads(first.stdout)
            self.assertTrue(doc['committed']);self.assertEqual(doc['revision'],1)
            self.assertEqual(doc['splits']['train'],['c1','c2','c3','c4'])
            self.assertEqual(doc['warnings'][0]['relation'],'x3')
            second=self.run_cli(['split','samples','--store',store])
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual(json.loads(second.stdout)['revision'],1)
            verify=self.run_cli(['verify','samples','--store',store])
            self.assertEqual(verify.returncode,0,verify.stderr)
            self.assertTrue(json.loads(verify.stdout)['valid'])
    def test_frozen_conflict_blocks_new_version(self):
        with tempfile.TemporaryDirectory() as d:
            store=str(Path(d)/'s.sqlite3')
            ok=self.run_cli(['split','samples','--store',store])
            self.assertEqual(ok.returncode,0,ok.stderr)
            bad=self.run_cli(['split','samples','--store',store,'--frozen','examples/conflicting-freeze.json'])
            self.assertEqual(bad.returncode,3,bad.stderr)
            report=json.loads(bad.stdout)
            self.assertEqual(report['error'],'frozen-conflict')
            self.assertEqual(report['conflicts'][0]['path'],['c1','c2','bridge','c4'])
            verify=self.run_cli(['verify','samples','--store',store])
            self.assertEqual(verify.returncode,0,verify.stderr)
            result=json.loads(verify.stdout)
            self.assertTrue(result['valid']);self.assertEqual(result['revision'],1)
    def test_verify_rejects_tampered_revision(self):
        from datapack.storage import RevisionStore
        with tempfile.TemporaryDirectory() as d:
            store=str(Path(d)/'s.sqlite3')
            self.run_cli(['split','samples','--store',store])
            database=RevisionStore(Path(store));latest=database.latest('scenario-split')
            value=json.loads(json.dumps(latest['value']))
            value['splits']['train']=['c1','c2','c3']
            value['splits']['test']=['c4','c5']
            database.put('scenario-split',latest['revision'],value)
            verify=self.run_cli(['verify','samples','--store',store])
            self.assertEqual(verify.returncode,2)
            result=json.loads(verify.stdout)
            self.assertFalse(result['valid'])
            self.assertIn('strong-component',{item['check'] for item in result['violations']})
    def test_dry_run_does_not_commit(self):
        with tempfile.TemporaryDirectory() as d:
            store=str(Path(d)/'s.sqlite3')
            dry=self.run_cli(['split','samples','--store',store,'--dry-run'])
            self.assertEqual(dry.returncode,0,dry.stderr)
            self.assertFalse(json.loads(dry.stdout)['committed'])
            verify=self.run_cli(['verify','samples','--store',store])
            self.assertEqual(verify.returncode,2)
