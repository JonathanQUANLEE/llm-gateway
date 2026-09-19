.PHONY: up down restart logs status mock probe test

up:            ## 启动全栈
	docker compose up -d

down:          ## 停止全栈
	docker compose down

restart:       ## 重启网关
	docker compose restart new-api

logs:          ## 跟踪网关日志（排障第一现场）
	docker compose logs -f new-api

status:        ## 容器状态
	docker compose ps

mock:          ## 启动模拟上游（联调 / 回归测试夹具）
	python scripts/mock_upstream.py

probe:         ## 渠道测活：状态码 / 延迟 / TTFT / 流式完整性
	python scripts/channel_probe.py --config scripts/channels.json

test:          ## 网关冒烟 + 故障演练（make test KEY=sk-xxx MODEL=模型名）
	python scripts/smoke_test.py --key $(KEY) --model $(MODEL)
