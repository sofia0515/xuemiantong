
## 第一阶段：模型工厂

### 目标

创建统一的模型实例，把模型创建逻辑从业务代码中抽离出来，做到换模型只需改配置、加模型只需注册工厂，方便后续扩展。

### 完成内容

1. **配置中心（）**
   - 使用 `pydantic-settings` 定义 `Settings` 类，统一管理模型配置：
     `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`DEEPSEEK_TEMPERATURE`、`DEEPSEEK_MAX_TOKENS`。
   - 通过 `python-dotenv` 自动加载 `.env`，配置项缺失时启动即报错，避免运行期才发现问题。
   - 全局导出单例 `settings`，其他模块统一引用，不重复读取环境变量。

2. **模型工厂()**
   - `LlmFactory`：模型构建函数类型别名，统一工厂函数签名。
   - `_build_deepseek_model()`：基于 `ChatOpenAI` 对接 DeepSeek 的 OpenAI 兼容接口。
   - `_PROVIDERS_FACTORY`：provider 到构建函数的注册表，新增模型只需追加一项。
   - `get_chat_model(provider="deepseek")`：对外统一入口，校验 provider 合法性并返回模型实例。
   - 未配置 `DEEPSEEK_API_KEY` 时抛出 `ValueError`，提前暴露配置问题。

### 关键设计

- **依赖倒置**：业务只依赖 `get_chat_model()`，不关心具体模型供应商。
- **可扩展**：新增供应商 = 新增一个构建函数 + 在注册表里加一行。
- **配置外置**：模型名、温度、最大 token 等均可通过环境变量调整，无需改代码。
