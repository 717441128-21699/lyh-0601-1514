---
access_count: 2
created_at: '2026-06-12T00:30:15.566796'
id: 28ff201db4cf
last_accessed: '2026-06-12T01:03:21.916556'
links:
- 'K8s 官方文档: https://kubernetes.io/docs/'
project: k8s
review_note: 对照最新K8s 1.29文档核对，内容依然有效，部分参数建议补充
reviewer: 李运维
tags:
- 运维
- kubernetes
- 故障排查
ticket_links:
- https://jira.example.com/browse/DEV-1234
title: Kubernetes Pod 启动失败排查指南
updated_at: '2026-06-12T01:55:18.346408'
---

## 基本信息

- **项目**: k8s
- **标签**: `运维`, `kubernetes`, `故障排查`
- **创建时间**: 2026-06-12T00:30:15
- **更新时间**: 2026-06-12T01:55:18
- **访问次数**: 2
- **最近访问**: 2026-06-12T01:03:21
- **负责人**: 👤 李运维
- **复审备注**: 📝 对照最新K8s 1.29文档核对，内容依然有效，部分参数建议补充

### 关联工单

- [https://jira.example.com/browse/DEV-1234](https://jira.example.com/browse/DEV-1234)

### 参考链接

- K8s 官方文档: https://kubernetes.io/docs/

---

## 常见原因

1. 镜像拉取失败
   - 检查镜像地址是否正确
   - 检查网络连接
   - 检查 imagePullSecret

2. 资源不足
   - 检查节点资源
   - 检查 requests/limits 设置

3. 配置错误
   - 检查 ConfigMap/Secret 是否存在
   - 检查环境变量配置