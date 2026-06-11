---
created_at: '2026-06-12T00:30:39.669741'
id: 81e0653b5d7a
needs_review: true
project: database
tags:
- 数据库
- Redis
- 缓存
- 故障排查
title: Redis 缓存穿透问题解决方案
updated_at: '2026-06-12T00:33:25.504184'
---

缓存穿透是指查询一个不存在的数据，缓存和数据库都没有命中。

解决方案：
1. 布隆过滤器
2. 缓存空值
3. 接口层增加校验