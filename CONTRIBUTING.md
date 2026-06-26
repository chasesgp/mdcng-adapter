# 贡献规范

## Git 提交信息规范

本项目提交信息统一使用以下格式：

```text
<type>: 中文说明
```

示例：

```text
feat: 添加 Grok 响应清洗逻辑
fix: 修复 SSE 内容合并异常
docs: 更新 Docker 部署说明
ci: 添加多架构镜像构建流程
```

### type 类型

| type | 说明 |
|---|---|
| `feat` | 新功能 |
| `fix` | 缺陷修复 |
| `docs` | 文档变更 |
| `style` | 代码格式调整，不影响逻辑 |
| `refactor` | 重构，不新增功能也不修复缺陷 |
| `perf` | 性能优化 |
| `test` | 测试相关变更 |
| `build` | 构建系统或依赖变更 |
| `ci` | CI/CD 流程变更 |
| `chore` | 其他维护性变更 |
| `revert` | 回退提交 |

### 规则要求

- `type` 使用小写英文。
- 冒号后保留一个空格。
- 说明必须使用中文，简洁描述本次提交目的。
- 不使用英文句号结尾。
- 不使用 scope，保持格式为 `<type>: 中文说明`。

### 推荐写法

```text
feat: 添加健康检查接口
fix: 修复上游响应解析失败问题
docs: 补充 GitHub Actions 镜像说明
test: 增加 SSE 聚合单元测试
```

### 不推荐写法

```text
feat(adapter): add health check
Fix: 修复 bug
update code
docs: update README.
```
