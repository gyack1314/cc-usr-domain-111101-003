# 数据约定

clip_id稳定；recording标识物理录制，source_run标识连续源；start/end为整数微秒半开区间。关系表可包含不在候选清单的桥接记录，候选之外可参与连通但不参与分配计量。parent_clip和transcode是强边，similar是软边。冻结分配允许train、validation、test。

样本为合成资料，包含正常、缺失、冲突等记录；这些现象用于保留业务数据原貌，读取成功不代表领域结果有效。所有计算原语位于datapack/domain.py；调用者负责组合、约束和最终验证。
