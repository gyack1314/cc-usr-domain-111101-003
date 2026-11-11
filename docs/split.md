# 防泄漏切分

切分单位是强关联连通分量，不是单个片段。`datapack/split.py` 负责分组、冻结检查与确定性分配，`datapack/splitcheck.py` 是独立复验器，`datapack/cli.py` 负责读取资料、版本化提交与复验。仍只使用标准库，输入字段约定见 `docs/domain.md`。

## 强关联与软提示

以下三类关系建立强边，强边两端的候选记录不得进入不同集合：

1. 同一 `source_run` 且半开区间 `[start,end)` 存在**正长度**重叠（`end==start` 的首尾相接不算）。
2. 同一 `recording`，即同一物理录制的不同转码。
3. 关系表中 `parent_clip` 与 `transcode` 两类显式关系。

强关联具有传递性。关系表允许引用不在候选清单中的记录（包括 `candidate:false` 的桥接记录和只出现在关系表中的标识），它们参与连通、冻结继承与冲突定位，但不参与分配计量，也不会出现在 `splits` 中。强边的具体原因记录在图上：`overlap:<source_run>`、`recording:<recording>`、`relation:<kind>:<id>`。

`similar` 只是感知指纹相近的软提示，**永不并组**。若软边两端的候选记录落入不同集合，仅在结果的 `warnings` 中给出 `similar-crosses-split`，供人工复核。

## 分量时长

每个含候选记录的分量，按 `source_run` 分组取区间并集长度后求和（复用 `domain.union_length`），同一来源上互相重叠的裁剪不会重复加权；非候选桥接记录的区间不计入。

## 冻结与冲突

冻结记录（`frozen.json`）为整个分量锁定集合：

- 分量内全部冻结标签一致时，候选成员整体进入该集合。
- 同一分量出现两个不同冻结集合时抛出 `FrozenConflict`，拒绝产出新版本。冲突条目给出涉及分量、全部冻结成员、以及两个不同集合冻结成员之间的**最短路径**（BFS，平局按标识字典序）和路径上每条强边的原因。冲突不能靠删除桥接记录掩盖：桥接节点始终保留在图中，冲突因此一定可见。
- 没有候选记录的冻结标识列入 `inactive_frozen`，仅作提示。

## 确定性分配

无冻结分量按配置比例分配。目标时长 = 全部候选分量总时长 × 比例（用 `Fraction` 精确比较，不引入浮点平局）：

1. 冻结分量先按锁定集合就位。
2. 未冻结分量按总时长降序、最小候选 `clip_id` 升序处理。
3. 每步选当前 `目标时长-已放置时长` 缺口最大的集合；缺口相同按配置 `order` 顺序。

相同输入必然产生相同分配文件；文档不含时间戳、随机数或版本号，可安全重复提交（内容未变时 `RevisionStore.put` 幂等返回同一修订号）。

## 保留与重平衡

`mode='keep'`：未冻结分量若其候选成员的旧分配完全一致，整体保留原集合，其余分量再按缺口分配；旧分配互相矛盾的分量（典型就是曾经泄漏的切分）无法保留，进入缺口分配后自动并组。

`mode='rebalance'`：忽略全部未冻结旧分配，只保留冻结约束，重新做缺口分配。

两种模式分别返回自己的 `moves`（`clip_id/from/to`），仅统计旧版本中存在且集合确实变化的记录；新增记录不算迁移。冻结成员永不进入 `moves`；若冻结表纠正了旧分配，列入单独的 `frozen_corrections`。不再是候选的旧成员列入 `removed`。

## 版本化分配文件

通过 `RevisionStore`（见 `docs/storage.md`）以流和修订号保存，文档结构：

```json
{
  "format": "scenario-split/v1",
  "config": {"ratios": {}, "order": []},
  "inputs": {"clips": "sha256", "relations": "sha256", "frozen": "sha256"},
  "splits": {"train": [], "validation": [], "test": []},
  "components": [{"members": [], "bridges": [], "duration": 0, "frozen": null, "split": ""}],
  "durations": {"train": 0, "validation": 0, "test": 0}
}
```

提交前先由隔离验证器复验，任何失败都不写入，上一版可用分配保持不变。

## 隔离验证器

`splitcheck.validate_assignment(clips, relations, frozen, config, document)` 从原始输入重新建图，不相信分配函数的成功标志，检查：

- 三个输入文件与 `config` 的内容指纹是否与文档记录一致；
- `splits` 的集合名是否与配置一致、是否有重复成员、是否覆盖全部且仅候选记录；
- 每条冻结记录的分配是否与冻结表一致；
- 每条候选两端的强边是否同集合（`strong-edge`）；
- 按全图（含非候选桥接）复核每个分量是否整体同集合（`strong-component`）——逐边检查无法发现经桥接记录的传递性泄漏，因此两者都做。

返回违规列表，空列表即通过。

## 命令行

```bash
python -m datapack.cli split samples --config samples/split-config.json --store state/splits.sqlite3
python -m datapack.cli split samples --store state/splits.sqlite3 --mode rebalance
python -m datapack.cli split samples --store state/splits.sqlite3 --dry-run
python -m datapack.cli verify samples --store state/splits.sqlite3
python -m datapack.cli verify samples --store state/splits.sqlite3 --revision 1
python -m datapack.cli split samples --store state/splits.sqlite3 --frozen examples/conflicting-freeze.json
```

`--frozen` 可替换冻结文件用于演练；`split-config.json` 不登记在 `bundle.json` 中。退出码：`0` 成功；`2` 输入无效或复验失败（不提交）；`3` 冻结冲突（不提交，stdout 输出冲突与最短路径）。
