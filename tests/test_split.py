import json
import unittest
from pathlib import Path
from datapack.records import load_rows
from datapack.split import FrozenConflict,build_strong_graph,component_duration,find_components,load_clips,load_relations,plan_split
from datapack.storage import fingerprint

ROOT=Path(__file__).resolve().parents[1]
CONFIG={'ratios':{'train':7,'validation':2,'test':1},'order':['train','validation','test']}

def sample():
    return load_rows(ROOT/'samples/clips.json'),load_rows(ROOT/'samples/relations.json'),load_rows(ROOT/'samples/frozen.json'),CONFIG

def clip(clip_id,run,recording,start,end,candidate=True):
    return {'clip_id':clip_id,'source_run':run,'recording':recording,'start':start,'end':end,'candidate':candidate}

class StructureTests(unittest.TestCase):
    def test_sample_components_and_duration(self):
        clips,relations,_frozen,_config=sample()
        graph=build_strong_graph(load_clips(clips),load_relations(relations))
        components=find_components(graph['nodes'],graph['adj'])
        self.assertEqual(components,[['bridge','c1','c2','c4'],['c3'],['c5'],['c6']])
        durations={component[0]:component_duration(component,load_clips(clips)) for component in components}
        self.assertEqual(durations,{'bridge':27,'c3':5,'c5':7,'c6':13})
    def test_touching_intervals_do_not_overlap(self):
        rows=[clip('t1','run','rec1',0,5),clip('t2','run','rec2',5,10)]
        graph=build_strong_graph(load_clips(rows),[])
        self.assertEqual(find_components(graph['nodes'],graph['adj']),[['t1'],['t2']])
    def test_positive_overlap_merges_same_run(self):
        rows=[clip('t1','run','rec1',0,6),clip('t2','run','rec2',5,10)]
        graph=build_strong_graph(load_clips(rows),[])
        self.assertEqual(find_components(graph['nodes'],graph['adj']),[['t1','t2']])
    def test_same_recording_is_strong(self):
        rows=[clip('t1','run1','same',0,5),clip('t2','run2','same',100,105)]
        graph=build_strong_graph(load_clips(rows),[])
        self.assertEqual(find_components(graph['nodes'],graph['adj']),[['t1','t2']])
    def test_similar_edge_is_soft_only(self):
        clips,relations,_frozen,_config=sample()
        graph=build_strong_graph(load_clips(clips),load_relations(relations))
        components=find_components(graph['nodes'],graph['adj'])
        self.assertTrue(any(component==['c3'] for component in components))
        self.assertFalse(any(set(component)=={'c3','c5'} for component in components))
        self.assertEqual([relation['id'] for relation in graph['soft']],['x3'])
    def test_bridge_makes_transitive_strong_component(self):
        clips,relations,_frozen,_config=sample()
        graph=build_strong_graph(load_clips(clips),load_relations(relations))
        components=find_components(graph['nodes'],graph['adj'])
        self.assertEqual(components[0],['bridge','c1','c2','c4'])

class PlanTests(unittest.TestCase):
    def test_sample_assignment_and_soft_warning(self):
        clips,relations,frozen,config=sample()
        plan=plan_split(clips,relations,frozen,config)
        self.assertEqual(plan['document']['splits'],{'train':['c1','c2','c3','c4'],'validation':['c6'],'test':['c5']})
        self.assertEqual(plan['durations'],{'train':32,'validation':13,'test':7})
        self.assertEqual(plan['moves'],[])
        self.assertEqual(len(plan['warnings']),1)
        self.assertEqual(plan['warnings'][0]['relation'],'x3')
        self.assertEqual(plan['warnings'][0]['left_split'],'train')
        self.assertEqual(plan['warnings'][0]['right_split'],'test')
    def test_repeat_and_keep_rerun_are_identical(self):
        clips,relations,frozen,config=sample()
        first=plan_split(clips,relations,frozen,config)
        again=plan_split(clips,relations,frozen,config,previous=first['assignment'],mode='keep')
        self.assertEqual(fingerprint(first['document']),fingerprint(again['document']))
        self.assertEqual(again['moves'],[])
    def test_keep_and_rebalance_return_separate_moves(self):
        flat=[clip('a','ra','pa',0,10),clip('b','rb','pb',0,10),clip('c','rc','pc',0,10)]
        local={'ratios':{'train':2,'validation':1,'test':1},'order':['train','validation','test']}
        previous={'a':'train','b':'train'}
        keep=plan_split(flat,[],[],local,previous=previous,mode='keep')
        self.assertEqual(keep['assignment'],{'a':'train','b':'train','c':'validation'})
        self.assertEqual(keep['moves'],[])
        rebalance=plan_split(flat,[],[],local,previous=previous,mode='rebalance')
        self.assertEqual(rebalance['assignment'],{'a':'train','b':'validation','c':'test'})
        # 迁移清单只列已有分配发生变化的 b；c 是新增记录，不算迁移。
        self.assertEqual(rebalance['moves'],[{'clip_id':'b','from':'train','to':'validation'}])
        self.assertNotEqual(keep['assignment'],rebalance['assignment'])
    def test_frozen_members_never_move(self):
        flat=[clip('a','ra','pa',0,10),clip('b','rb','pb',0,10)]
        local={'ratios':{'train':2,'validation':1,'test':1},'order':['train','validation','test']}
        frozen=[{'clip_id':'a','split':'train'}]
        plan=plan_split(flat,[],frozen,local,previous={'a':'validation','b':'train'},mode='rebalance')
        self.assertEqual(plan['assignment']['a'],'train')
        self.assertNotIn('a',[item['clip_id'] for item in plan['moves']])
        self.assertEqual(plan['frozen_corrections'],[{'clip_id':'a','from':'validation','to':'train'}])
        self.assertIn({'clip_id':'b','from':'train','to':'validation'},plan['moves'])
    def test_transitive_frozen_conflict_reports_shortest_path(self):
        clips,relations,_frozen,_config=sample()
        conflict=load_rows(ROOT/'examples/conflicting-freeze.json')
        with self.assertRaises(FrozenConflict) as raised:
            plan_split(clips,relations,conflict,CONFIG)
        error=raised.exception
        self.assertIsInstance(error,ValueError)
        self.assertEqual(error.conflicts[0]['frozen'],{'c1':'train','c4':'test'})
        self.assertEqual(error.conflicts[0]['path'],['c1','c2','bridge','c4'])
        self.assertIn('bridge',error.conflicts[0]['component'])
        self.assertEqual([edge['reason'] for edge in error.conflicts[0]['path_edges']],['overlap:r1','relation:parent_clip:x1','relation:transcode:x2'])
    def test_invalid_configs_are_rejected(self):
        flat=[clip('a','ra','pa',0,10)]
        with self.assertRaises(ValueError):plan_split(flat,[],[],{'ratios':{'train':1,'validation':1},'order':['train']})
        with self.assertRaises(ValueError):plan_split(flat,[],[],{'ratios':{'train':0},'order':['train']})
        with self.assertRaises(ValueError):plan_split(flat,[],[{'clip_id':'a','split':'holdout'}],{'ratios':{'train':1},'order':['train']})

if __name__=='__main__':unittest.main()
