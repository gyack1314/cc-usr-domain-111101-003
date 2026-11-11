# 防数据泄漏的场景集合分组与锁定切分数据包

场景片段及关联边登记工具，已有源区间计量和显式关系检查。 数据文件位于samples，字段和边界见docs/domain.md，持久目录接口见docs/storage.md。

## 本地运行

Python 3.11以上，仅依赖标准库，无需真实账号或外部数据服务。

```bash
python -m datapack.cli inspect samples
python -m datapack.cli split samples --store state/splits.sqlite3
python -m datapack.cli verify samples --store state/splits.sqlite3
python -m unittest discover -s tests -v
python -m compileall -q datapack tests
```

第一条命令检查已有资料，第二条按强关联分量生成并版本化提交防泄漏切分，第三条独立复验已提交版本，第四条运行读取、内容存储、领域原语与切分检查，第五条构建Python字节码。冻结冲突演练见`docs/split.md`。

## 容器

```bash
docker build -t local-datapack .
docker run --rm --network none local-datapack
docker run --rm --network none local-datapack python -m unittest discover -s tests -v
```

应用没有必须常驻的服务，入口和库可在同一容器离线运行。state和output是本地工作目录，已排除出Git。样本文件只读，修订目录使用独立SQLite文件，旧版本可继续查询。

## 目录

datapack/storage.py提供摘要、原子文件与修订目录；datapack/records.py提供文件读取及重复主键分类；datapack/domain.py提供当前领域原语；datapack/split.py按强关联分量做防泄漏切分并支持保留/重平衡两种模式；datapack/splitcheck.py是独立复验器；tests验证这些行为。数据加工结果不由资料检查命令自动生成。切分规则、版本化分配文件与退出码见docs/split.md。
