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
  Switch,
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
  float32ToWavBlob,
  synthesizeStreamWs,
  synthesizeWav,
  switchModel,
  switchProvider,
  type ModelInfo,
  type Speaker,
  type StatusPayload,
} from "./api";

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

const SAMPLE = "欢迎使用本地中英混合语音合成。Hello from fsatts — Chinese and English mixed TTS.";

function langLabel(lang?: string): string {
  if (lang === "zh+en" || lang === "zh-en") return "中英混合";
  if (lang === "zh") return "仅中文";
  if (lang === "en") return "仅英文";
  return lang || "未知语言";
}

function modelOptionLabel(m: ModelInfo): string {
  return `${m.name} · ${langLabel(m.lang)}`;
}

/** Schedule PCM chunks on AudioContext for near-realtime playback. */
class StreamPlayer {
  private ctx: AudioContext | null = null;
  private nextTime = 0;
  private sampleRate = 24000;
  readonly chunks: Float32Array[] = [];

  start(sampleRate: number) {
    this.stop();
    this.sampleRate = sampleRate;
    this.ctx = new AudioContext({ sampleRate });
    this.nextTime = this.ctx.currentTime + 0.05;
    this.chunks.length = 0;
  }

  push(samples: Float32Array) {
    if (!samples.length) return;
    const copy = new Float32Array(samples);
    this.chunks.push(copy);
    if (!this.ctx) return;
    const buf = this.ctx.createBuffer(1, copy.length, this.sampleRate);
    buf.copyToChannel(copy, 0);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);
    const startAt = Math.max(this.nextTime, this.ctx.currentTime + 0.01);
    src.start(startAt);
    this.nextTime = startAt + buf.duration;
  }

  concat(): Float32Array {
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const out = new Float32Array(total);
    let o = 0;
    for (const c of this.chunks) {
      out.set(c, o);
      o += c.length;
    }
    return out;
  }

  stop() {
    try {
      void this.ctx?.close();
    } catch {
      /* ignore */
    }
    this.ctx = null;
  }
}

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
  const [streamPlay, setStreamPlay] = useState(true);
  const [progress, setProgress] = useState<number | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Record<string, string>>({});
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const switchGen = useRef(0);
  const sidRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const playerRef = useRef(new StreamPlayer());

  const applyStatus = useCallback((s: StatusPayload, opts?: { resetSid?: boolean }) => {
    setStatus(s);
    const nextModels = s.models || [];
    setModels(nextModels);
    const ready = nextModels.filter((m) => m.ready);
    const preferred = s.model_id || "melo-zh-en-44k";
    const nextModelId = ready.some((m) => m.id === preferred)
      ? preferred
      : ready[0]?.id || preferred;
    setModelId(nextModelId);
    setSpeakers(s.speakers || []);
    if (opts?.resetSid) {
      sidRef.current = 0;
      setSid(0);
    } else {
      const ids = new Set((s.speakers || []).map((sp) => sp.sid));
      const keep = ids.has(sidRef.current) ? sidRef.current : (s.speakers?.[0]?.sid ?? 0);
      sidRef.current = keep;
      setSid(keep);
    }
    setProvider((s.provider as "cpu" | "cuda") || "cpu");
    setLoading(false);
  }, []);

  const refresh = useCallback(
    async (opts?: { resetSid?: boolean }) => {
      const s = await fetchStatus();
      applyStatus(s, opts);
      return s;
    },
    [applyStatus],
  );

  useEffect(() => {
    refresh({ resetSid: true }).catch((e) => {
      message.error(`无法连接服务: ${e.message}`);
      setLoading(false);
    });
  }, [refresh, message]);

  useEffect(() => {
    const player = playerRef.current;
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      player.stop();
      abortRef.current?.abort();
    };
  }, [audioUrl]);

  const readyModels = useMemo(() => models.filter((m) => m.ready), [models]);
  const currentModel =
    readyModels.find((m) => m.id === modelId) || models.find((m) => m.id === modelId);
  const canStream = Boolean(
    currentModel?.supports_stream ?? status?.supports_stream ?? status?.streaming ?? true,
  );

  useEffect(() => {
    if (!canStream && streamPlay) setStreamPlay(false);
  }, [canStream, streamPlay]);

  const onModelChange = async (next: string) => {
    if (next === modelId) return;
    const gen = ++switchGen.current;
    setSwitching(true);
    setModelId(next);
    sidRef.current = 0;
    setSid(0);
    try {
      const sp = await fetchSpeakers(next);
      if (gen !== switchGen.current) return;
      setSpeakers(sp.speakers || []);
      if (sp.ready) {
        await switchModel(next, true);
        if (gen !== switchGen.current) return;
        message.success(`已切换模型：${next}`);
      } else {
        message.warning("该模型尚未下载，请先完成下载后再选择。");
      }
      const s = await fetchStatus();
      if (gen !== switchGen.current) return;
      setStatus(s);
      setModels(s.models || []);
      const keepSpeakers = sp.speakers || s.speakers || [];
      setSpeakers(keepSpeakers);
      sidRef.current = 0;
      setSid(0);
    } catch (e) {
      message.error(`切换模型失败: ${(e as Error).message}`);
    } finally {
      if (gen === switchGen.current) setSwitching(false);
    }
  };

  const onSpeakerChange = (next: number) => {
    sidRef.current = next;
    setSid(next);
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

  const setResultUrl = (url: string | null) => {
    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });
  };

  const doSynthBatch = async () => {
    const { blob, headers } = await synthesizeWav({
      text: text.trim(),
      speed,
      sid: sidRef.current,
      model_id: modelId,
      provider,
    });
    const url = URL.createObjectURL(blob);
    setResultUrl(url);
    setMetrics({
      耗时: headers["X-Elapsed-Ms"] ? `${headers["X-Elapsed-Ms"]} ms` : "-",
      音频: headers["X-Audio-Duration"] ? `${headers["X-Audio-Duration"]} s` : "-",
      RTF: headers["X-RTF"] || "-",
      采样率: headers["X-Sample-Rate"] || "-",
      模型: headers["X-Model-Id"] || modelId,
      说话人: headers["X-Sid"] || String(sidRef.current),
      模式: "完整合成后播放",
    });
    requestAnimationFrame(() => {
      audioRef.current?.play().catch(() => undefined);
    });
  };

  const doSynthStream = async () => {
    const ac = new AbortController();
    abortRef.current = ac;
    const player = playerRef.current;
    let sampleRate = 24000;
    setProgress(0);
    const end = await synthesizeStreamWs(
      {
        text: text.trim(),
        speed,
        sid: sidRef.current,
        model_id: modelId,
        provider,
      },
      {
        onMeta: (meta) => {
          sampleRate = Number(meta.sample_rate || 24000);
          player.start(sampleRate);
        },
        onChunk: (samples) => player.push(samples),
        onProgress: (p) => setProgress(p),
      },
      ac.signal,
    );
    const all = player.concat();
    const blob = float32ToWavBlob(all, sampleRate);
    const url = URL.createObjectURL(blob);
    setResultUrl(url);
    setMetrics({
      耗时: end.elapsed_ms != null ? `${end.elapsed_ms} ms` : "-",
      音频: end.audio_duration != null ? `${Number(end.audio_duration).toFixed(3)} s` : "-",
      RTF: end.rtf != null ? String(end.rtf) : "-",
      采样率: String(end.sample_rate || sampleRate),
      模型: String(end.model_id || modelId),
      说话人: String(end.sid ?? sidRef.current),
      模式: "边合成边播放",
    });
    setProgress(1);
  };

  const doSynth = async () => {
    const t = text.trim();
    if (!t) {
      message.warning("请输入文本");
      return;
    }
    setBusy(true);
    setProgress(null);
    try {
      if (streamPlay && canStream) {
        await doSynthStream();
      } else {
        await doSynthBatch();
      }
      message.success("合成完成");
      refresh().catch(() => undefined);
    } catch (e) {
      message.error(`合成失败: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      abortRef.current = null;
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
          <div className="sub">中英混合 · 模型切换 · 高并发插件服务（端口 19658）</div>
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
              切换模型或说话人不会自动合成；确认参数后点击「开始合成」。当前可选模型均支持中英混合。
            </Paragraph>
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <Row gutter={[16, 12]}>
                <Col xs={24} md={12}>
                  <Text strong>模型</Text>
                  <Select
                    showSearch
                    style={{ width: "100%", marginTop: 6 }}
                    value={readyModels.some((m) => m.id === modelId) ? modelId : undefined}
                    loading={switching}
                    optionFilterProp="label"
                    onChange={onModelChange}
                    placeholder={readyModels.length ? "选择已下载模型" : "暂无已下载模型"}
                    options={readyModels.map((m) => ({
                      value: m.id,
                      label: modelOptionLabel(m),
                    }))}
                    notFoundContent="没有已下载的模型"
                  />
                  {currentModel && (
                    <div className="hint" style={{ marginTop: 6 }}>
                      <Tag color="green">{langLabel(currentModel.lang)}</Tag>
                      {currentModel.supports_stream === false ? (
                        <Tag color="default">不支持流式</Tag>
                      ) : (
                        <Tag color="blue">支持流式</Tag>
                      )}
                      {currentModel.description}
                      {currentModel.expected_sample_rate
                        ? ` · ${currentModel.expected_sample_rate} Hz`
                        : ""}
                      {` · ${currentModel.num_speakers} 说话人`}
                    </div>
                  )}
                </Col>
                <Col xs={24} md={12}>
                  <Text strong>说话人</Text>
                  <Select
                    showSearch
                    style={{ width: "100%", marginTop: 6 }}
                    value={sid}
                    onChange={onSpeakerChange}
                    optionFilterProp="label"
                    options={speakers.map((s) => ({
                      value: s.sid,
                      label: `${s.name} (sid=${s.sid})${s.note ? ` · ${s.note}` : ""}`,
                    }))}
                    placeholder="选择说话人"
                  />
                </Col>
              </Row>

              <Row gutter={[16, 12]}>
                <Col xs={24} md={12}>
                  <Flex justify="space-between" align="center">
                    <Text strong>边合成边播放</Text>
                    <Switch
                      checked={streamPlay && canStream}
                      disabled={!canStream || busy}
                      onChange={setStreamPlay}
                      checkedChildren="开"
                      unCheckedChildren="关"
                    />
                  </Flex>
                  <div className="hint" style={{ marginTop: 4 }}>
                    {canStream
                      ? streamPlay
                        ? "开启：通过 WebSocket 流式合成并实时播放"
                        : "关闭：完整合成后再播放 WAV"
                      : "当前模型不支持流式，已禁用该开关"}
                  </div>
                </Col>
                <Col xs={24} md={12}>
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
                </Col>
              </Row>

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
                {progress != null && busy && (
                  <Text type="secondary">进度 {(progress * 100).toFixed(0)}%</Text>
                )}
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
                  {currentModel?.lang ? (
                    <>
                      {" "}
                      <Tag color="green">{langLabel(currentModel.lang)}</Tag>
                    </>
                  ) : null}
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
                  引擎池大小 <b>{conc?.pool_size}</b>，最大在途请求 <b>{conc?.max_inflight}</b>
                  。环境变量 <code>TTS_ENGINE_POOL_SIZE</code> / <code>TTS_MAX_INFLIGHT</code>{" "}
                  可调。队列满时返回 503。
                </Paragraph>
              </div>
              <Divider style={{ margin: "4px 0" }} />
              <div>
                <Text type="secondary">可用模型（已下载）</Text>
                <div className="stat-row" style={{ marginTop: 8 }}>
                  {readyModels.map((m) => (
                    <Tag
                      key={m.id}
                      color={m.id === modelId ? "blue" : "success"}
                      style={{ marginBottom: 4 }}
                    >
                      {m.name} · {langLabel(m.lang)}
                    </Tag>
                  ))}
                  {!readyModels.length && <Text type="secondary">暂无</Text>}
                </div>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
