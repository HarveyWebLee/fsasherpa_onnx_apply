fsatts — 本地 TTS 插件服务
========================

1. 模型：
   - 完整安装包通常已含 models/（如 vits-melo-tts-zh_en、可选 8k）。
   - 若 models/ 为空，请自行放入模型，或设置 TTS_MODELS_ROOT 指向外部目录：
     - models/vits-melo-tts-zh_en/     (44.1k)
     - models/vits-melo-tts-zh_en-8k/  (可选 8k)

2. 启动：
   Windows:  run.bat
   Linux:    chmod +x fsatts run.sh && ./run.sh

3. 默认监听 0.0.0.0:19658 （本机浏览器: http://127.0.0.1:19658）
   健康检查: GET /api/health
   合成:     POST /api/tts   JSON {"text":"...","speed":1.0,"sid":0}
   流式:     WS   /ws/tts

4. 环境变量见 config.example.env

5. 防火墙：若其他机器要访问，请放行 TCP 19658，并注意安全（默认 CORS=*）。
