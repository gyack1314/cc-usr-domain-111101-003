import argparse
import json
import sys
from pathlib import Path
from .records import inspect_bundle,load_rows
from .split import FrozenConflict,plan_split
from .splitcheck import validate_assignment
from .storage import RevisionStore,confined,read_json

def _inputs(bundle,config,frozen):
    root=Path(bundle)
    clips=load_rows(confined(root,'clips.json'))
    relations=load_rows(confined(root,'relations.json'))
    frozen_path=Path(frozen) if frozen else confined(root,'frozen.json')
    frozen_rows=load_rows(frozen_path)
    config_path=Path(config) if config else confined(root,'split-config.json')
    return clips,relations,frozen_rows,read_json(config_path)

def _previous(latest):
    if not latest or not isinstance(latest.get('value'),dict):return None
    splits=latest['value'].get('splits')
    if not isinstance(splits,dict):return None
    previous={}
    for name,members in splits.items():
        if not isinstance(members,list):continue
        for clip in members:
            if isinstance(clip,str) and clip not in previous:previous[clip]=name
    return previous

def _run_split(args):
    clips,relations,frozen,config=_inputs(args.bundle,args.config,args.frozen)
    store=RevisionStore(args.store);latest=store.latest(args.stream)
    plan=plan_split(clips,relations,frozen,config,previous=_previous(latest),mode=args.mode)
    violations=validate_assignment(clips,relations,frozen,config,plan['document'])
    summary={'mode':args.mode,'moves':plan['moves'],'removed':plan['removed'],'frozen_corrections':plan['frozen_corrections'],'inactive_frozen':plan['inactive_frozen'],'warnings':plan['warnings'],'durations':plan['durations'],'splits':plan['document']['splits']}
    if violations:
        print(json.dumps({'error':'validation-failed','violations':violations},ensure_ascii=False,indent=2))
        return 2
    expected=latest['revision'] if latest else 0
    if args.dry_run:
        summary['committed']=False;summary['revision']=expected
        print(json.dumps(summary,ensure_ascii=False,indent=2));return 0
    revision=store.put(args.stream,expected,plan['document'])
    summary['committed']=True;summary['revision']=revision
    print(json.dumps(summary,ensure_ascii=False,indent=2));return 0

def _run_verify(args):
    clips,relations,frozen,config=_inputs(args.bundle,args.config,args.frozen)
    store=RevisionStore(args.store)
    if args.revision is None:
        entry=store.latest(args.stream)
        if entry is None:raise KeyError('没有可用分配')
    else:
        entry=store.get(args.stream,args.revision);entry['revision']=args.revision
    violations=validate_assignment(clips,relations,frozen,config,entry['value'])
    print(json.dumps({'valid':not violations,'violations':violations,'revision':entry['revision'],'digest':entry['digest']},ensure_ascii=False,indent=2))
    return 0 if not violations else 2

def main():
    parser=argparse.ArgumentParser(description='数据包内容检查与防泄漏切分')
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('inspect');p.add_argument('bundle',type=Path)
    p=commands.add_parser('catalog');p.add_argument('database',type=Path);p.add_argument('stream')
    p=commands.add_parser('split')
    p.add_argument('bundle',type=Path);p.add_argument('--config',type=Path);p.add_argument('--frozen',type=Path)
    p.add_argument('--store',type=Path,required=True);p.add_argument('--stream',default='scenario-split')
    p.add_argument('--mode',choices=('keep','rebalance'),default='keep');p.add_argument('--dry-run',action='store_true')
    p=commands.add_parser('verify')
    p.add_argument('bundle',type=Path);p.add_argument('--config',type=Path);p.add_argument('--frozen',type=Path)
    p.add_argument('--store',type=Path,required=True);p.add_argument('--stream',default='scenario-split')
    p.add_argument('--revision',type=int)
    args=parser.parse_args()
    try:
        if args.command=='inspect':value=inspect_bundle(args.bundle)
        elif args.command=='catalog':value=RevisionStore(args.database).latest(args.stream)
        elif args.command=='split':return _run_split(args)
        else:return _run_verify(args)
        print(json.dumps(value,ensure_ascii=False,indent=2));return 0
    except FrozenConflict as error:
        print(json.dumps({'error':'frozen-conflict','conflicts':error.conflicts},ensure_ascii=False,indent=2));return 3
    except (ValueError,KeyError,OSError):
        print('输入资料或目录无效，请检查路径及字段说明',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
