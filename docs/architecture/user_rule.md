你好，我们需要继续进行 Python FastAPI 项目的“多用户与权限隔离改造”任务。

【项目背景】
这是一个报告生成系统，正在从单用户模式向多用户模式迁移。我们使用 JWT (Bearer Token) 进行身份认证。
项目路径：/root/zzp/langextract-main/generate_report_test

【核心设计原则】
- 身份识别：严禁使用请求体中的 agentUserId，必须解析 Header 中的 JWT Token (sub 字段) 获取当前用户 ID。
- 数据隔离：所有数据库查询必须带上 user_id 过滤条件；文件操作应通过数据库映射或分用户目录隔离。
- 架构模式：采用“逻辑集中(auth_utils/dependencies)，引用分散(Router Depends)”的 FastAPI 最佳实践。

【参考文档】
- 总体设计与最佳实践：user_auth_plan.md
- 改造任务清单与现状：user_multi_user_gap_plan.md

【接下来的任务】
请读取 user_multi_user_gap_plan.md，继续按计划改造剩余的接口（如报告导入、合并、生成、LLM配置等），确保所有接口都强制校验用户身份并实现数据隔离。请优先处理“写操作”相关的接口改造。