from .split import FORMAT,build_strong_graph,find_components,load_clips,load_frozen,load_relations,parse_config
from .storage import fingerprint

def validate_assignment(clips_rows,relations_rows,frozen_rows,config,document):
    """独立复验分配文件：全部输入指纹、强关联（含桥接传递）、冻结约束、重复与覆盖。"""
    violations=[]
    def fail(check,detail):violations.append({'check':check,'detail':detail})
    clips=load_clips(clips_rows);relations=load_relations(relations_rows)
    order,_ratios=parse_config(config)
    frozen=load_frozen(frozen_rows,set(order))
    candidates={cid for cid,clip in clips.items() if clip['candidate']}
    if not isinstance(document,dict):
        fail('format','分配文件必须是对象');return violations
    if document.get('format')!=FORMAT:fail('format','格式标识不匹配')
    if fingerprint(document.get('config'))!=fingerprint(config):fail('config-mismatch','配置与分配文件记录不一致')
    inputs=document.get('inputs')
    if not isinstance(inputs,dict):
        fail('input-mismatch','缺少输入指纹');inputs={}
    for name,rows in (('clips',clips_rows),('relations',relations_rows),('frozen',frozen_rows)):
        if inputs.get(name)!=fingerprint(rows):fail('input-mismatch','输入指纹不一致：'+name)
    splits=document.get('splits')
    if not isinstance(splits,dict):
        fail('splits','缺少切分结果');splits={}
    if set(splits)!=set(order):fail('splits','集合名称与配置不一致')
    assignment={};seen=set()
    for name in order:
        members=splits.get(name)
        if not isinstance(members,list):
            fail('splits','集合成员必须是数组：'+name);continue
        for cid in members:
            if not isinstance(cid,str):
                fail('member-type','集合成员必须是字符串：'+name);continue
            if cid in seen:
                fail('duplicate-member','成员重复出现：'+cid);continue
            seen.add(cid)
            if cid not in candidates:
                fail('non-candidate-member','非候选记录出现在分配：'+cid);continue
            assignment[cid]=name
    for cid in sorted(candidates-set(seen)):fail('missing-member','候选记录未分配：'+cid)
    for cid in sorted(frozen):
        if cid in candidates and assignment.get(cid)!=frozen[cid]:fail('frozen-mismatch','冻结分配被改变：'+cid)
    graph=build_strong_graph(clips,relations)
    for edge in graph['strong_edges']:
        left,right=edge['left'],edge['right']
        if left in candidates and right in candidates and left in assignment and right in assignment and assignment[left]!=assignment[right]:
            fail('strong-edge','强关联跨集合：'+left+' 与 '+right+'（'+edge['reasons'][0]+'）')
    # 逐边检查无法覆盖“经非候选桥接记录的传递”，因此必须按全图分量复核。
    for members in find_components(graph['nodes'],graph['adj']):
        parts={}
        for cid in members:
            if cid in candidates and cid in assignment:parts.setdefault(assignment[cid],[]).append(cid)
        if len(parts)>1:
            fail('strong-component','强关联分量被拆分：'+','.join(members))
    return violations
