fsatts — 本地多模型 TTS 插件服务
===============================

1. 模型
   - 完整包通常已含 Melo（44.1k / 可选 8k）。
   - 多说话人模型（zh-ll / aishell3 / fanchen / theresa / eula）体积大，默认可不打包；
     需要时用 uv run python scripts/download_models.py --id zh-ll 等下载到 models/。
   - 也可设置 TTS_MODELS_ROOT 指向外部模型目录。

2. 启动
   Windows:  run.bat
   Linux:    chmod +x fsatts run.sh && ./run.sh

3. 默认监听 0.0.0.0:19658（本机: http://127.0.0.1:19658）
   健康检查: GET /api/health  （兼容别名 GET /health）
   模型列表: GET /api/models
   说话人:   GET /api/speakers?model_id=...
   合成:     POST /api/tts  JSON {"text":"...","speed":1.0,"sid":0,"model_id":"..."}
   流式:     WS   /ws/tts

4. 环境变量见 config.example.env（含 TTS_ENGINE_POOL_SIZE / TTS_MAX_INFLIGHT 等并发调优）

5. 防火墙：若其他机器要访问，放行 TCP 19658；注意安全（默认 CORS=*）。
