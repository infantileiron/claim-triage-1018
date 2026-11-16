# gb-3106 多币种折算验证

运行环境：Python 3.11 + `backend/requirements.txt`（另需 `httpx`、`fakeredis` 仅测试用）。

```bash
# 在任意空目录执行，避免脚本目录被当作模块搜索路径
cd /tmp && PYTHONPATH=/workspace/backend python \
  /workspace/test-artifacts/gb-3106/test_fx_unit.py
PYTHONPATH=/workspace/backend python /workspace/test-artifacts/gb-3106/test_api.py
PYTHONPATH=/workspace/backend python /workspace/test-artifacts/gb-3106/test_race_worker.py
node /workspace/test-artifacts/gb-3106/test_pages.mjs
```

| 文件 | 覆盖 |
|---|---|
| `test_fx_unit.py` | 生效区间边界、中间币种链路、多路径矛盾、缺汇率、无汇率簿、旧样本 CNY、区间交叠、循环汇率、非法值 |
| `test_api.py` | 角色权限、草稿增删改与校验、发布门禁、发布后不可变、样本币种/日期校验、训练冻结整本簿、逐票 conversions、导出、补发历史汇率不影响已受理版本、重试沿用受理依据、多路径失败证据、发布竞争、审计 |
| `test_race_worker.py` | 发布在受理事务中途提交的确定性交错、整本簿不混用、worker 持久化与产物、重试评分一致、旧库幂等升级回填 CNY |
| `test_pages.mjs` | 五个页面在带外币/失败/校验错误状态下的渲染烟测 |

SQLite 无法覆盖 MySQL 行锁语义；发布/受理并发的不变量由 `test_race_worker.py` 的确定性交错断言，部署环境为 MySQL 8 + `lock_settings`/锁定读。
