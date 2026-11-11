from fractions import Fraction
from .domain import union_length
from .storage import fingerprint

FORMAT='scenario-split/v1'
STRONG_KINDS=('parent_clip','transcode')
SOFT_KINDS=('similar',)
RELATION_KINDS=STRONG_KINDS+SOFT_KINDS
MODES=('keep','rebalance')

class FrozenConflict(ValueError):
    def __init__(self,conflicts):
        super().__init__('强关联把不同冻结集合连在一起')
        self.conflicts=conflicts

def _text(value,name,owner):
    if not isinstance(value,str) or not value:raise ValueError(owner+'缺少有效'+name)
    return value

def _integer(value,name,owner):
    if isinstance(value,bool) or not isinstance(value,int):raise ValueError(owner+'的'+name+'必须是整数微秒')
    return value

def load_clips(rows):
    clips={};digests={}
    for row in rows:
        cid=_text(row.get('clip_id'),'clip_id','记录')
        digest=fingerprint(row)
        if cid in clips:
            if digests[cid]!=digest:raise ValueError('clip_id内容冲突：'+cid)
            continue
        run=_text(row.get('source_run'),'source_run',cid)
        recording=_text(row.get('recording'),'recording',cid)
        start=_integer(row.get('start'),'start',cid)
        end=_integer(row.get('end'),'end',cid)
        if start>end:raise ValueError('区间倒置：'+cid)
        candidate=row.get('candidate')
        if not isinstance(candidate,bool):raise ValueError('candidate必须是布尔值：'+cid)
        clips[cid]={'source_run':run,'recording':recording,'start':start,'end':end,'candidate':candidate}
        digests[cid]=digest
    return clips

def load_relations(rows):
    relations=[];seen=set()
    for row in rows:
        rid=_text(row.get('id'),'id','关系')
        if rid in seen:raise ValueError('关系id重复：'+rid)
        left=_text(row.get('left'),'left',rid)
        right=_text(row.get('right'),'right',rid)
        kind=row.get('kind')
        if kind not in RELATION_KINDS:raise ValueError('未知关系类型：'+rid)
        if left==right:raise ValueError('关系两端相同：'+rid)
        seen.add(rid)
        relations.append({'id':rid,'left':left,'right':right,'kind':kind})
    return relations

def load_frozen(rows,splits):
    frozen={}
    for row in rows:
        cid=_text(row.get('clip_id'),'clip_id','冻结记录')
        split=row.get('split')
        if split not in splits:raise ValueError('冻结分配集合无效：'+cid)
        if cid in frozen and frozen[cid]!=split:raise ValueError('冻结分配冲突：'+cid)
        frozen[cid]=split
    return frozen

def parse_config(config):
    if not isinstance(config,dict):raise ValueError('切分配置必须是对象')
    ratios=config.get('ratios');order=config.get('order')
    if not isinstance(ratios,dict) or not ratios:raise ValueError('缺少目标比例')
    if not isinstance(order,list) or not order:raise ValueError('缺少集合顺序')
    if len(order)!=len(set(order)):raise ValueError('集合顺序重复')
    if set(order)!=set(ratios):raise ValueError('集合顺序与目标比例不一致')
    values={}
    for name in order:
        if not isinstance(name,str) or not name:raise ValueError('集合名称无效')
        ratio=ratios[name]
        if isinstance(ratio,bool) or not isinstance(ratio,(int,float)):raise ValueError('目标比例必须是数值：'+name)
        if ratio<=0:raise ValueError('目标比例必须为正：'+name)
        values[name]=Fraction(str(ratio))
    return tuple(order),values

def build_strong_graph(clips,relations):
    nodes=set(clips);adj={}
    def connect(left,right,reason):
        nodes.add(left);nodes.add(right)
        adj.setdefault(left,{}).setdefault(right,set()).add(reason)
        adj.setdefault(right,{}).setdefault(left,set()).add(reason)
    runs={}
    for cid,clip in clips.items():runs.setdefault(clip['source_run'],[]).append(cid)
    for run in sorted(runs):
        # 半开区间按起点扫描；只有 end>当前start 才是有正长度的重叠，首尾相接不算。
        active=[]
        for cid in sorted(runs[run],key=lambda item:(clips[item]['start'],clips[item]['end'],item)):
            start=clips[cid]['start']
            active=[other for other in active if clips[other]['end']>start]
            for other in active:connect(other,cid,'overlap:'+run)
            active.append(cid)
    recordings={}
    for cid,clip in clips.items():recordings.setdefault(clip['recording'],[]).append(cid)
    for recording in sorted(recordings):
        members=sorted(recordings[recording])
        for index,left in enumerate(members):
            for right in members[index+1:]:connect(left,right,'recording:'+recording)
    soft=[]
    for relation in relations:
        if relation['kind'] in STRONG_KINDS:
            connect(relation['left'],relation['right'],'relation:'+relation['kind']+':'+relation['id'])
        else:
            soft.append(dict(relation))
    graph={node:{other:sorted(reasons) for other,reasons in sorted(adj.get(node,{}).items())} for node in sorted(nodes)}
    edges=[]
    for left in sorted(nodes):
        for right,reasons in graph[left].items():
            if right>left:edges.append({'left':left,'right':right,'reasons':reasons})
    return {'nodes':sorted(nodes),'adj':graph,'soft':sorted(soft,key=lambda item:(item['id'],item['left'],item['right'])),'strong_edges':edges}

def find_components(nodes,adj):
    remaining=set(nodes);components=[]
    while remaining:
        seed=min(remaining);remaining.discard(seed);stack=[seed];members=[]
        while stack:
            node=stack.pop();members.append(node)
            for other in sorted(adj.get(node,{}),reverse=True):
                if other in remaining:
                    remaining.discard(other);stack.append(other)
        components.append(sorted(members))
    components.sort(key=lambda item:item[0])
    return components

def component_duration(members,clips):
    intervals={}
    for cid in members:
        clip=clips.get(cid)
        if clip is None or not clip['candidate']:continue
        intervals.setdefault(clip['source_run'],[]).append((clip['start'],clip['end']))
    return sum(union_length(intervals[run]) for run in sorted(intervals))

def _conflict_path(members,adj,frozen):
    labels={member:frozen[member] for member in members if member in frozen}
    best=None
    for source in sorted(labels):
        queue=[source];visited={source};paths={source:[source]}
        while queue:
            node=queue.pop(0)
            for other in sorted(adj.get(node,{})):
                if other in visited:continue
                visited.add(other);paths[other]=paths[node]+[other];queue.append(other)
                if other in labels and labels[other]!=labels[source]:
                    candidate=paths[other]
                    if best is None or (len(candidate),candidate)<(len(best),best):best=candidate
    if best is None:return {'path':[],'path_edges':[]}
    edges=[{'left':left,'right':right,'reason':adj[left][right][0]} for left,right in zip(best,best[1:])]
    return {'path':best,'path_edges':edges}

def plan_split(clips_rows,relations_rows,frozen_rows,config,previous=None,mode='keep'):
    if mode not in MODES:raise ValueError('未知分配模式：'+str(mode))
    order,ratios=parse_config(config)
    clips=load_clips(clips_rows);relations=load_relations(relations_rows);frozen=load_frozen(frozen_rows,set(order))
    graph=build_strong_graph(clips,relations)
    components=[]
    for members in find_components(graph['nodes'],graph['adj']):
        candidates=sorted(cid for cid in members if cid in clips and clips[cid]['candidate'])
        if not candidates:continue
        labels={cid:frozen[cid] for cid in members if cid in frozen}
        components.append({'members':members,'candidates':candidates,'bridges':sorted(set(members)-set(candidates)),'duration':component_duration(members,clips),'labels':labels,'key':candidates[0],'frozen':None,'split':None})
    conflicts=[]
    for component in components:
        if len(set(component['labels'].values()))>1:
            conflicts.append({'component':component['members'],'frozen':component['labels'],**_conflict_path(component['members'],graph['adj'],frozen)})
    if conflicts:raise FrozenConflict(conflicts)
    clean_previous={}
    if previous:
        for cid,split in previous.items():
            if isinstance(cid,str) and split in order:clean_previous[cid]=split
    assignment={};current={name:0 for name in order};pool=[]
    def place(component,split):
        component['split']=split
        for cid in component['candidates']:assignment[cid]=split
        current[split]+=component['duration']
    for component in components:
        labels=set(component['labels'].values())
        if labels:
            component['frozen']=labels.pop();place(component,component['frozen'])
        elif mode=='keep':
            votes={clean_previous[cid] for cid in component['candidates'] if cid in clean_previous}
            if len(votes)==1:place(component,votes.pop())
            else:pool.append(component)
        else:
            pool.append(component)
    total=sum(component['duration'] for component in components)
    ratio_total=sum(ratios.values())
    target={name:Fraction(total)*ratios[name]/ratio_total for name in order}
    # 分量按总时长降序、最小clip_id升序处理；每步选当前目标缺口最大的集合，缺口相同按配置顺序。
    for component in sorted(pool,key=lambda item:(-item['duration'],item['key'])):
        chosen=None;gap=None
        for name in order:
            current_gap=target[name]-current[name]
            if gap is None or current_gap>gap:chosen=name;gap=current_gap
        place(component,chosen)
    moves=[];removed=[];corrections=[]
    for cid in sorted(clean_previous):
        if cid not in assignment:
            if cid not in frozen:removed.append(cid)
        elif assignment[cid]!=clean_previous[cid]:
            item={'clip_id':cid,'from':clean_previous[cid],'to':assignment[cid]}
            (corrections if cid in frozen else moves).append(item)
    warnings=[]
    for relation in graph['soft']:
        left,right=relation['left'],relation['right']
        if left in assignment and right in assignment and assignment[left]!=assignment[right]:
            warnings.append({'kind':'similar-crosses-split','relation':relation['id'],'left':left,'right':right,'left_split':assignment[left],'right_split':assignment[right]})
    warnings.sort(key=lambda item:(item['relation'],item['left'],item['right']))
    active_frozen=set()
    for component in components:active_frozen.update(component['labels'])
    inactive=sorted(cid for cid in frozen if cid not in active_frozen)
    durations={name:current[name] for name in order}
    document={
        'format':FORMAT,
        'config':config,
        'inputs':{'clips':fingerprint(clips_rows),'relations':fingerprint(relations_rows),'frozen':fingerprint(frozen_rows)},
        'splits':{name:sorted(cid for cid in assignment if assignment[cid]==name) for name in order},
        'components':[{'members':component['candidates'],'bridges':component['bridges'],'duration':component['duration'],'frozen':component['frozen'],'split':component['split']} for component in sorted(components,key=lambda item:item['key'])],
        'durations':durations,
    }
    return {'mode':mode,'document':document,'assignment':dict(sorted(assignment.items())),'moves':moves,'removed':removed,'frozen_corrections':corrections,'inactive_frozen':inactive,'warnings':warnings,'durations':durations,'components':document['components']}
