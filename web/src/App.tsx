import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Flex,
  Input,
  Row,
  Select,
  Slider,
  Space,
  Tag,
  Typography,
  App as AntApp,
  theme,
} from "antd";
import {
  CloudServerOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SoundOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  fetchSpeakers,
  fetchStatus,
  synthesizeWav,
  switchModel,
  switchProvider,
  type ModelInfo,
  type Speaker,
  type StatusPayload,
} from "./api";

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

const SAMPLE =
  "欢迎使用本地多模型语音合成。Hello from fsatts — Chinese and English mixed TTS.";

export default function App() {
  const { message } = AntApp.useApp();
  const { token } = theme.useToken();

  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelId, setModelId] = useState<string>("melo-zh-en-44k");
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [sid, setSid] = useState(0);
  const [speed, setSpeed] = useState(1.0);
  const [provider, setProvider] = useState<"cpu" | "cuda">("cpu");
  const [text, setText] = useState(SAMPLE);
  const [busy, setBusy] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Record<string, string>>({});
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const switchGen = useRef(0);

  const refresh = useCallback(async () => {
    const s = await fetchStatus();
    setStatus(s);
    setModels(s.models || []);
    setModelId(s.model_id || "melo-zh-en-44k");
    setSpeakers(s.speakers || []);
    setSid(0);
    setProvider((s.provider as "cpu" | "cuda") || "cpu");
    setLoading(false);
    return s;
  }, []);

  useEffect(() => {
    refresh().catch((e) => {
      message.error(`无法连接服务: ${e.message}`);
      setLoading(false);
    });
  }, [refresh, message]);

  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const readyModels = useMemo(
    () => models.filter((m) => m.ready),
    [models]
  );
  const currentModel = models.find((m) => m.id === modelId);

  const onModelChange = async (next: string) => {
    if (next === modelId) return;
    const gen = ++switchGen.current;
    setSwitching(true);
    setModelId(next);
    setSid(0);
    // Responsive speaker list — do NOT auto-synthesize
    try {
      const sp = await fetchSpeakers(next);
      if (gen !== switchGen.current) return;
      setSpeakers(sp.speakers || []);
      if (sp.ready) {
        await switchModel(next, true);
        if (gen !== switchGen.current) return;
        message.success(`已切换模型：${next}`);
      } else {
        message.warning("该模型尚未下载，合成时会失败。请先运行下载脚本。");
      }
      const s = await fetchStatus();
      if (gen !== switchGen.current) return;
      setStatus(s);
      setModels(s.models || []);
    } catch (e) {
      message.error(`切换模型失败: ${(e as Error).message}`);
    } finally {
      if (gen === switchGen.current) setSwitching(false);
    }
  };

  const onSpeakerChange = (next: number) => {
    setSid(next);
    // No auto TTS — responsive UI only
  };

  const onProviderChange = async (next: "cpu" | "cuda") => {
    setProvider(next);
    try {
      await switchProvider(next, true);
      message.success(`推理后端：${next}`);
      await refresh();
    } catch (e) {
      message.error(`切换失败: ${(e as Error).message}`);
      setProvider(status?.provider === "cuda" ? "cuda" : "cpu");
    }
  };

  const doSynth = async () => {
    const t = text.trim();
    if (!t) {
      message.warning("请输入文本");
      return;
    }
    setBusy(true);
    try {
      const { blob, headers } = await synthesizeWav({
        text: t,
        speed,
        sid,
        model_id: modelId,
        provider,
      });
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);
      setMetrics({
        耗时: headers["X-Elapsed-Ms"] ? `${headers["X-Elapsed-Ms"]} ms` : "-",
        音频: headers["X-Audio-Duration"]
          ? `${headers["X-Audio-Duration"]} s`
          : "-",
        RTF: headers["X-RTF"] || "-",
        采样率: headers["X-Sample-Rate"] || "-",
        模型: headers["X-Model-Id"] || modelId,
        说话人: headers["X-Sid"] || String(sid),
      });
      requestAnimationFrame(() => {
        audioRef.current?.play().catch(() => undefined);
      });
      message.success("合成完成");
      refresh().catch(() => undefined);
    } catch (e) {
      message.error(`合成失败: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const conc = status?.concurrency;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <Title level={2} style={{ margin: 0 }}>
            <SoundOutlined style={{ color: token.colorPrimary, marginRight: 8 }} />
            fsatts 本地 TTS
          </Title>
          <div className="sub">
            多模型 · 说话人切换 · 高并发插件服务（端口 19658）
          </div>
        </div>
        <Space wrap>
          <Tag icon={<CloudServerOutlined />} color={status?.model_ready ? "success" : "warning"}>
            {status?.model_ready ? "模型就绪" : "模型未就绪"}
          </Tag>
          <Tag icon={<ThunderboltOutlined />} color="blue">
            inflight {conc?.inflight ?? 0}/{conc?.max_inflight ?? 64}
          </Tag>
          <Tag color="processing">pool {conc?.pool_size ?? "-"}</Tag>
          <Button icon={<ReloadOutlined />} onClick={() => refresh()} loading={loading}>
            刷新
          </Button>
        </Space>
      </header>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={15}>
          <Card title="合成" bordered={false} className="panel" loading={loading}>
            <Paragraph type="secondary" style={{ marginTop: 0 }}>
              切换模型或说话人不会自动合成，确认参数后点击「开始合成」。
            </Paragraph>
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <div>
                <Text strong>模型</Text>
                <Select
                  showSearch
                  style={{ width: "100%", marginTop: 6 }}
                  value={modelId}
                  loading={switching}
                  optionFilterProp="label"
                  onChange={onModelChange}
                  options={models.map((m) => ({
                    value: m.id,
                    label: `${m.name}${m.ready ? "" : "（未下载）"}`,
                    disabled: false,
                  }))}
                />
                {currentModel && (
                  <div className="hint" style={{ marginTop: 6 }}>
                    {currentModel.description}
                    {currentModel.expected_sample_rate
                      ? ` · ${currentModel.expected_sample_rate} Hz`
                      : ""}
                    {` · ${currentModel.num_speakers} 说话人`}
                    {!currentModel.ready && currentModel.missing?.length
                      ? ` · 缺失文件请下载`
                      : ""}
                  </div>
                )}
              </div>

              <div>
                <Text strong>说话人</Text>
                <Select
                  showSearch
                  style={{ width: "100%", marginTop: 6 }}
                  value={sid}
                  onChange={onSpeakerChange}
                  optionFilterProp="label"
                  options={speakers.map((s) => ({
                    value: s.sid,
                    label: `${s.name} (sid=${s.sid})`,
                  }))}
                  placeholder="选择说话人"
                />
              </div>

              <div>
                <Flex justify="space-between" align="center">
                  <Text strong>语速 {speed.toFixed(2)}×</Text>
                  <Text type="secondary">0.5 – 2.0</Text>
                </Flex>
                <Slider
                  min={0.5}
                  max={2}
                  step={0.05}
                  value={speed}
                  onChange={setSpeed}
                  marks={{ 0.5: "0.5", 1: "1.0", 1.5: "1.5", 2: "2.0" }}
                />
              </div>

              <div>
                <Text strong>推理后端</Text>
                <Select
                  style={{ width: "100%", marginTop: 6 }}
                  value={provider}
                  onChange={onProviderChange}
                  options={[
                    { value: "cpu", label: "CPU" },
                    {
                      value: "cuda",
                      label: status?.cuda_available ? "CUDA" : "CUDA（不可用）",
                      disabled: !status?.cuda_available,
                    },
                  ]}
                />
              </div>

              <div>
                <Text strong>文本</Text>
                <TextArea
                  rows={6}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  maxLength={2000}
                  showCount
                  style={{ marginTop: 6 }}
                  placeholder="输入中文、英文或中英混合文本"
                />
              </div>

              <Flex gap={12} wrap="wrap" align="center">
                <Button
                  type="primary"
                  size="large"
                  icon={<PlayCircleOutlined />}
                  loading={busy}
                  disabled={switching || !readyModels.length}
                  onClick={doSynth}
                >
                  开始合成
                </Button>
              </Flex>

              <div className="audio-box">
                {audioUrl ? (
                  <audio ref={audioRef} controls src={audioUrl} />
                ) : (
                  <Alert type="info" showIcon message="合成结果将在此播放" />
                )}
              </div>

              {Object.keys(metrics).length > 0 && (
                <div className="metrics">
                  {Object.entries(metrics).map(([k, v]) => (
                    <div className="metric" key={k}>
                      <div className="k">{k}</div>
                      <div className="v">{v}</div>
                    </div>
                  ))}
                </div>
              )}
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={9}>
          <Card title="服务状态" bordered={false} className="panel" loading={loading}>
            <Space direction="vertical" style={{ width: "100%" }} size="middle">
              <div>
                <Text type="secondary">当前模型</Text>
                <div>
                  <Text strong>{status?.model_name || status?.model_id || "-"}</Text>
                </div>
              </div>
              <div>
                <Text type="secondary">采样率 / 说话人数</Text>
                <div>
                  {status?.sample_rate ?? "-"} Hz · {status?.num_speakers ?? "-"} 人
                </div>
              </div>
              <Divider style={{ margin: "4px 0" }} />
              <div>
                <Text type="secondary">并发</Text>
                <Paragraph className="hint" style={{ marginBottom: 0 }}>
                  引擎池大小 <b>{conc?.pool_size}</b>，最大在途请求{" "}
                  <b>{conc?.max_inflight}</b>。环境变量{" "}
                  <code>TTS_ENGINE_POOL_SIZE</code> / <code>TTS_MAX_INFLIGHT</code>{" "}
                  可调。队列满时返回 503。
                </Paragraph>
              </div>
              <Divider style={{ margin: "4px 0" }} />
              <div>
                <Text type="secondary">已注册模型</Text>
                <div className="stat-row" style={{ marginTop: 8 }}>
                  {models.map((m) => (
                    <Tag
                      key={m.id}
                      color={m.ready ? (m.id === modelId ? "blue" : "success") : "default"}
                      style={{ marginBottom: 4 }}
                    >
                      {m.name}
                      {!m.ready ? " · 未下载" : ""}
                    </Tag>
                  ))}
                </div>
              </div>
              <Alert
                type="info"
                showIcon
                message="下载模型"
                description={
                  <span>
                    <code>uv run python scripts/download_models.py --list</code>
                    <br />
                    <code>uv run python scripts/download_models.py --bundle</code>
                    <br />
                    <code>uv run python scripts/download_models.py --id theresa</code>
                  </span>
                }
              />
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
