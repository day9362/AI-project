# VC-TestOS 后端

制造业均热片测试平台的后端。当前完成的是运行总览：机台、统计、告警、WebSocket，以及 Redis 登录会话。

接口形状以 `front_design/docs/backend-api.md` 为准，前缀 `/api/v1`。

## 目录

- `api/` 路由。`api/overview` 是运行总览，`api/test_plan` 留给测试方案
- `service/` 业务逻辑、集群同步、定时任务要调用的规则
- `repo/` 数据库访问
- `models/orm` SQLAlchemy 表，`models/dto` 请求和响应，`models/entity` 领域对象
- `tasks/` 定时任务和告警归因触发任务

## 启动

需要本机 PostgreSQL 和 Redis。可以用项目里的 `docker-compose.yml`：

```bash
docker compose up -d
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --port 8000
```

初始账号：

- `limingyuan` / `changeme`，角色 `test`
- `admin` / `changeme`，角色 `admin`

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"username\":\"limingyuan\",\"password\":\"changeme\"}"
```

之后请求带 `Authorization: Bearer <token>`。注销是 `POST /api/v1/auth/logout`，会话存在 Redis，注销即删除。

数据库为空时会写入一份和运行总览演示一致的机台、告警和测试记录。集群同步默认开着；`cluster.simuoss.cn` 连不上时任务会退避，不会清掉本地数据。
