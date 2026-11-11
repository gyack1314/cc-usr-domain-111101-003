import copy
import unittest
from pathlib import Path
from datapack.records import load_rows
from datapack.split import plan_split
from datapack.splitcheck import validate_assignment

ROOT=Path(__file__).resolve().parents[1]
CONFIG={'ratios':{'train':7,'validation':2,'test':1},'order':['train','validation','test']}

class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.clips=load_rows(ROOT/'samples/clips.json')
        self.relations=load_rows(ROOT/'samples/relations.json')
        self.frozen=load_rows(ROOT/'samples/frozen.json')
        self.document=plan_split(self.clips,self.relations,self.frozen,CONFIG)['document']
    def validate(self,document):
        return validate_assignment(self.clips,self.relations,self.frozen,CONFIG,document)
    def tamper(self):
        return copy.deepcopy(self.document)
    def checks(self,violations):
        return {violation['check'] for violation in violations}
    def test_valid_assignment_passes(self):
        self.assertEqual(self.validate(self.document),[])
    def test_bridge_mediated_split_is_detected_by_component_check(self):
        document=self.tamper()
        document['splits']['train']=['c1','c2','c3']
        document['splits']['test']=['c4','c5']
        violations=self.validate(document)
        self.assertIn('strong-component',self.checks(violations))
        self.assertIn('c4',','.join(item['detail'] for item in violations))
    def test_direct_strong_edge_is_detected(self):
        document=self.tamper()
        document['splits']['train']=['c1','c3','c4']
        document['splits']['test']=['c2','c5']
        self.assertIn('strong-edge',self.checks(self.validate(document)))
    def test_frozen_mismatch_is_detected(self):
        document=self.tamper()
        document['splits']['train']=['c2','c3','c4']
        document['splits']['test']=['c1','c5']
        self.assertIn('frozen-mismatch',self.checks(self.validate(document)))
    def test_duplicate_member_is_detected(self):
        document=self.tamper()
        document['splits']['train'].append('c6')
        self.assertIn('duplicate-member',self.checks(self.validate(document)))
    def test_missing_candidate_is_detected(self):
        document=self.tamper()
        document['splits']['train']=['c1','c2','c4']
        self.assertIn('missing-member',self.checks(self.validate(document)))
    def test_non_candidate_member_is_detected(self):
        document=self.tamper()
        document['splits']['train'].append('bridge')
        self.assertIn('non-candidate-member',self.checks(self.validate(document)))
    def test_input_fingerprint_is_detected(self):
        document=self.tamper()
        document['inputs']['clips']='0'*64
        self.assertIn('input-mismatch',self.checks(self.validate(document)))
        document=self.tamper()
        document['inputs']['frozen']='0'*64
        self.assertIn('input-mismatch',self.checks(self.validate(document)))
    def test_config_mismatch_is_detected(self):
        document=self.tamper()
        document['config']['ratios']['train']=8
        self.assertIn('config-mismatch',self.checks(self.validate(document)))
    def test_unknown_split_name_is_detected(self):
        document=self.tamper()
        document['splits']['holdout']=[]
        self.assertIn('splits',self.checks(self.validate(document)))
    def test_non_object_document_is_detected(self):
        self.assertIn('format',self.checks(self.validate([])))

if __name__=='__main__':unittest.main()
