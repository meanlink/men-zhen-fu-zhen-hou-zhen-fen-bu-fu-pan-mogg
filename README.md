# 门诊复诊候诊分布复盘

面向东栖连锁门诊运营组的候诊复盘工作台，用于把预约、签到和叫号记录整理成可解释的候诊时长分布，支持科室复核与报告归档。

## 真实场景

东栖连锁门诊在每晚 18:30 由运营专员从预约台导出 CSV，再把签到时间和叫号时间抄入共享表。运营组需要识别哪个科室时段发生了超阈值等待，并让科室负责人给出复核意见。旧流程有三个痛点，跨表合并容易丢失签到时间，平均值掩盖午后长尾，复核结论无法追溯到具体样本。

上游输入是预约系统的预约、签到、叫号事件。本项目替代人工拼表、统计和复核归档这一段。下游消费者是门诊运营主管和各科室负责人，他们使用归档报告调整下一周复诊排班。

## 主要功能

- 候诊样本的预约、签到、叫号和完成状态流转
- 科室时段阈值与容量维护
- 候诊时长分布、P50、P90、MAD 和异常样本计算
- 超过科室阈值自动进入科室复核
- 缺签到或叫号的报告拒绝发布
- 未到诊核销由分析专员发起，另一位复核人员确认或驳回。新报告保留核销排除快照。
- 候诊改善追踪以报告中的异常样本为依据，记录实施措施并用同窗口的后续 P90 验收。
- 临时容量按支援窗口审批、发放加号并保留台账。超阈值候诊可进入科室分流，叫号后记录处置耗时。
- JWT 三角色权限、审计日志、Redis 限流和 worker 心跳

## 快速启动

```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec backend python scripts/seed_demo.py --with-expansion --with-operations
```

访问 <http://localhost:18240>。

## 演示账号

| 账号 | 密码 | 角色 | 主要动作 |
|---|---|---|---|
| analyst | demo123 | 分析专员 | 维护样本、发起核销、生成报告、立项改善、发放临时加号、登记候诊超时 |
| reviewer | demo123 | 科室复核员 | 决定核销、复核报告、验收改善、审批加号、确认候诊分流 |
| admin | demo123 | 运营管理员 | 管理时段、归档报告、登记改善实施、申请和收回加号 |

## 扩展演示

1. 分析专员在「候诊样本」找到 `OP-1120-11`，发起核销并填写预约台或签到记录的核对依据。
2. 科室复核员在「未到诊核销」确认或驳回。待复核期间暂停补录事件，驳回后可恢复补录。已确认的预约作为独立记录留存，从新报告的候诊统计中排除。
3. 在「复盘报告」为呼吸内科午后复诊重新生成报告，查看排除记录。旧报告继续保留自己的样本统计和发布条件。
4. 分析专员可从含异常样本的已复核报告创建改善事项。扩展 seed 预置一条「呼吸内科加开窗 · 长尾基线」改善事项，基线 P90 为 49 分钟，目标为 35 分钟。
5. 运营管理员在「候诊改善追踪」登记实施日期 `2026-11-17` 和执行说明。
6. 科室复核员选择「改善复测」作为验收报告。其 P90 为 27.6 分钟，较基线下降 21.4 分钟。基线和对照均需至少 3 条有效样本，对照须在实施日期之后且来自同科室、同名同起止时间的窗口。

## 临时容量与候诊处置演示

1. 运营管理员在「临时容量」查看 seed 中心内科 2026 年 11 月 20 日的申请。支援医生在 15:00–16:00 使用 3 号诊室，可补发 2 个号。
2. 科室复核员审批该批次，分析专员发放 `OPS-1120-01`，预约时间填 `15:05`。台账显示已发 1 个、剩余 1 个，样本编号可直接打开候诊样本。
3. 在候诊样本补录 `15:07` 签到。在「候诊处置台」登记 `15:36` 的现场观察。后端按签到到观察的完整分钟计算，29 分钟达到心内科 25 分钟阈值。
4. 科室复核员记录分流意见，例如安排改到 2 号诊室优先叫号。也可解除处置，恢复普通叫号登记。
5. 分析专员通过「前往样本叫号」写入 `15:43`。样本和处置结果同时保存，处置台显示观察后 7 分钟叫号，新报告按实际签到到叫号统计 36 分钟候诊。
6. 运营管理员可收回剩余 1 个号。已发预约和审批意见继续留在台账。

临时容量批次记录额外诊室及支援人员对应的号源。预约时间须在批次起止范围内，结束时刻归入下一窗口。旧样本入口继续用于补录已发生的事件，临时加号台账只登记经审批发放的号源。页面使用诊区本地时间，审批和申请审计时间由服务器记录。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Nginx + 原生 HTML/CSS/ES modules 风格 JavaScript |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy |
| 数据库 | PostgreSQL 16 |
| 异步支撑 | Redis 7 + Python worker 心跳 |
| 部署 | Docker Compose，恰好 5 个服务 |

## 目录

- `backend/src/models.py` 领域模型与状态枚举
- `backend/src/services/analytics.py` 候诊分布、分位数、MAD 算法
- `backend/src/services/workflow.py` 主流程和异常规则
- `backend/src/services/attendance.py` 预约核销、角色分离与报表口径
- `backend/src/services/improvements.py` 基线、实施和候诊复测验收规则
- `frontend/src/app.js` 页面路由和业务交互
- `frontend/src/followup.js` 核销与改善页面、样本和报告入口
- `backend/src/capacity_models.py` 与 `backend/src/recovery_models.py` 加号批次、发放记录和候诊处置
- `backend/src/operations_schemas.py` 运营工作流输入及回执
- `backend/src/services/capacity.py` 批次审批、加号发放及收回
- `backend/src/services/recovery.py` 超时阈值、分流与叫号结果
- `frontend/src/capacity.js` 与 `frontend/src/recovery.js` 临时容量台账和候诊处置台
- `test-artifacts/gb-1041/min35/` 扩展验收、源码清单和截图

## 共享枚举出现位置

- 样本状态 `booked / checked_in / called / completed / needs_review` 出现在 `backend/src/models.py`、`backend/src/schemas.py`、`frontend/src/app.js`。
- 报告状态 `draft / under_review / reviewed / archived` 出现在 `backend/src/models.py`、`backend/src/schemas.py`、`frontend/src/app.js`。
- 用户角色 `analyst / department_reviewer / operations_admin` 出现在 `backend/src/models.py`、`backend/src/auth.py`、`frontend/src/app.js`。

- 核销原因 `no_show / cancelled`、核销状态 `pending / confirmed / rejected`、改善状态 `planned / implemented / evaluated` 出现在 `backend/src/models.py`、`backend/src/schemas.py`、`frontend/src/followup.js`，改善结果 `met / missed` 由后端根据 P90 派生。

- 加号批次 `proposed / approved / rejected / closed` 出现在 `backend/src/capacity_models.py`、`backend/src/operations_schemas.py`、`frontend/src/capacity.js`。
- 处置状态 `pending / prioritized / dismissed / recovered` 出现在 `backend/src/recovery_models.py`、`backend/src/operations_schemas.py`、`frontend/src/recovery.js`。

## 环境变量

`.env.example` 提供端口、数据库、Redis 和 JWT 配置。数据库端口为 17740，后端端口为 19240，前端端口为 18240。独立验收栈可用 `CLINIC_DB_VOLUME`、`CLINIC_REDIS_VOLUME`、`CLINIC_SHARED_VOLUME` 指定自己的卷名。旧库启动时会通过现有 `init_db` 创建缺少的领域表。

## 许可证

内部评审样例，按 MIT 许可证使用。
