import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Col,
  Input,
  Row,
  Select,
  Slider,
  Switch,
  Tag,
  Typography,
  App as AntApp,
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
const { Text, Paragraph } = Typography;

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
  private playing = false;
  private pending: Float32Array<ArrayBuffer>[] = [];
  private pendingSamples = 0;
  /** Hold ~350ms before starting to reduce underruns when RTF > 1. */
  private minStartSec = 0.35;
  readonly chunks: Float32Array<ArrayBuffer>[] = [];

  start(sampleRate: number) {
    this.stop();
    this.sampleRate = sampleRate;
    this.ctx = new AudioContext({ sampleRate });
    void this.ctx.resume();
    this.nextTime = 0;
    this.playing = false;
    this.pending = [];
    this.pendingSamples = 0;
    this.chunks.length = 0;
  }

  private copySamples(samples: Float32Array): Float32Array<ArrayBuffer> {
    const out = new Float32Array(samples.length);
    out.set(samples);
    return out;
  }

  private schedule(copy: Float32Array<ArrayBuffer>) {
    const ctx = this.ctx;
    if (!ctx || !copy.length) return;
    if (ctx.state === "suspended") void ctx.resume();
    const buf = ctx.createBuffer(1, copy.length, this.sampleRate);
    buf.copyToChannel(copy, 0);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    if (!this.playing) {
      this.nextTime = ctx.currentTime + 0.05;
      this.playing = true;
    }
    const startAt = Math.max(this.nextTime, ctx.currentTime + 0.02);
    src.start(startAt);
    this.nextTime = startAt + buf.duration;
  }

  private flushPending() {
    if (!this.pending.length) return;
    for (const c of this.pending) this.schedule(c);
    this.pending = [];
    this.pendingSamples = 0;
  }

  push(samples: Float32Array) {
    if (!samples.length) return;
    const copy = this.copySamples(samples);
    this.chunks.push(copy);
    if (!this.ctx) return;

    if (!this.playing) {
      this.pending.push(copy);
      this.pendingSamples += copy.length;
      const minSamples = Math.floor(this.sampleRate * this.minStartSec);
      if (this.pendingSamples >= minSamples) this.flushPending();
      return;
    }
    this.schedule(copy);
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

  /** Flush any held preroll and wait until scheduled audio finishes. */
  async drain(timeoutMs = 120_000): Promise<void> {
    this.flushPending();
    const ctx = this.ctx;
    if (!ctx || !this.playing) return;
    const deadline = performance.now() + timeoutMs;
    while (ctx.state !== "closed" && ctx.currentTime + 0.03 < this.nextTime) {
      if (performance.now() > deadline) break;
      await new Promise((r) => setTimeout(r, 40));
    }
    await new Promise((r) => setTimeout(r, 60));
  }

  stop() {
    try {
      void this.ctx?.close();
    } catch {
      /* ignore */
    }
    this.ctx = null;
    this.nextTime = 0;
    this.playing = false;
    this.pending = [];
    this.pendingSamples = 0;
  }
}

export default function App() {
  const { message } = AntApp.useApp();

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

  // Revoke prior blob URLs only — never stop the stream player here.
  // Stopping on audioUrl change closed AudioContext as soon as synthesis
  // finished, cutting off audio that was still scheduled ahead of currentTime.
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  useEffect(() => {
    const player = playerRef.current;
    return () => {
      player.stop();
      abortRef.current?.abort();
    };
  }, []);

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
    // Keep AudioContext alive until scheduled buffers finish.
    await player.drain();
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
        <div className="brand">
          <span className="brand-icon" aria-hidden>
            <SoundOutlined />
          </span>
          <div>
            <h1 className="brand-title">fsatts 本地 TTS</h1>
            <div className="sub">中英混合 · 模型切换 · 高并发插件服务（端口 19658）</div>
          </div>
        </div>
        <div className="header-meta">
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
        </div>
      </header>

      <Row gutter={[18, 18]} className="app-main" align="stretch">
        <Col xs={24} lg={15} xl={16}>
          <Card title="合成" bordered={false} className="panel" loading={loading}>
            <div className="panel-stack">
              <Paragraph className="intro" type="secondary">
                切换模型或说话人不会自动合成；确认参数后点击「开始合成」。当前可选模型均支持中英混合。
              </Paragraph>

              <Row gutter={[16, 14]}>
                <Col xs={24} md={12}>
                  <div className="field">
                    <div className="field-label">
                      <span className="field-label-text">模型</span>
                    </div>
                    <div className="field-control">
                      <Select
                        showSearch
                        style={{ width: "100%" }}
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
                    </div>
                    {currentModel ? (
                      <div className="model-meta">
                        <Tag color="green">{langLabel(currentModel.lang)}</Tag>
                        {currentModel.supports_stream === false ? (
                          <Tag>不支持流式</Tag>
                        ) : (
                          <Tag color="blue">支持流式</Tag>
                        )}
                        <span className="meta-desc">
                          {currentModel.description}
                          {currentModel.expected_sample_rate
                            ? ` · ${currentModel.expected_sample_rate} Hz`
                            : ""}
                          {` · ${currentModel.num_speakers} 说话人`}
                        </span>
                      </div>
                    ) : null}
                  </div>
                </Col>
                <Col xs={24} md={12}>
                  <div className="field">
                    <div className="field-label">
                      <span className="field-label-text">说话人</span>
                    </div>
                    <div className="field-control">
                      <Select
                        showSearch
                        style={{ width: "100%" }}
                        value={sid}
                        onChange={onSpeakerChange}
                        optionFilterProp="label"
                        options={speakers.map((s) => ({
                          value: s.sid,
                          label: `${s.name} (sid=${s.sid})${s.note ? ` · ${s.note}` : ""}`,
                        }))}
                        placeholder="选择说话人"
                      />
                    </div>
                  </div>
                </Col>
              </Row>

              <Row gutter={[16, 14]} className="config-row">
                <Col xs={24} md={12}>
                  <div className="field">
                    <div className="field-label">
                      <span className="field-label-text">边合成边播放</span>
                    </div>
                    <div className="field-control">
                      <Switch
                        checked={streamPlay && canStream}
                        disabled={!canStream || busy}
                        onChange={setStreamPlay}
                        checkedChildren="开"
                        unCheckedChildren="关"
                      />
                    </div>
                    <p className="field-hint">
                      {canStream
                        ? streamPlay
                          ? "开启后通过 WebSocket 流式合成并实时播放"
                          : "关闭后完整合成再播放 WAV"
                        : "当前模型不支持流式，开关已禁用"}
                    </p>
                  </div>
                </Col>
                <Col xs={24} md={12}>
                  <div className="field">
                    <div className="field-label">
                      <span className="field-label-text">推理后端</span>
                    </div>
                    <div className="field-control">
                      <Select
                        style={{ width: "100%" }}
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
                  </div>
                </Col>
              </Row>

              <div className="field">
                <div className="field-label">
                  <span className="field-label-text">语速</span>
                  <span className="field-label-extra">{speed.toFixed(2)}× · 0.5 – 2.0</span>
                </div>
                <Slider
                  min={0.5}
                  max={2}
                  step={0.05}
                  value={speed}
                  onChange={setSpeed}
                  tooltip={{ formatter: (v) => `${Number(v).toFixed(2)}×` }}
                  marks={{ 0.5: "0.5", 1: "1.0", 1.5: "1.5", 2: "2.0" }}
                />
              </div>

              <div className="field">
                <div className="field-label">
                  <span className="field-label-text">文本</span>
                </div>
                <TextArea
                  rows={6}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  maxLength={2000}
                  showCount
                  placeholder="输入中文、英文或中英混合文本"
                />
              </div>

              <div className="action-row">
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
                {progress != null && busy ? (
                  <Text type="secondary">进度 {(progress * 100).toFixed(0)}%</Text>
                ) : null}
              </div>

              <div className="audio-box">
                {audioUrl ? (
                  <audio ref={audioRef} controls src={audioUrl} />
                ) : (
                  <div className="audio-empty">合成结果将在此播放</div>
                )}
              </div>

              {Object.keys(metrics).length > 0 ? (
                <div className="metrics">
                  {Object.entries(metrics).map(([k, v]) => (
                    <div className="metric" key={k}>
                      <div className="k">{k}</div>
                      <div className="v">{v}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </Card>
        </Col>

        <Col xs={24} lg={9} xl={8}>
          <Card title="服务状态" bordered={false} className="panel" loading={loading}>
            <div className="status-stack">
              <div className="status-block">
                <div className="status-label">当前模型</div>
                <div className="status-value">
                  {status?.model_name || status?.model_id || "-"}
                  {currentModel?.lang ? (
                    <>
                      {" "}
                      <Tag color="green">{langLabel(currentModel.lang)}</Tag>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="status-block">
                <div className="status-label">采样率 / 说话人数</div>
                <div className="status-value">
                  {status?.sample_rate ?? "-"} Hz · {status?.num_speakers ?? "-"} 人
                </div>
              </div>

              <hr className="status-divider" />

              <div className="status-block">
                <div className="status-label">并发</div>
                <p className="status-note">
                  引擎池大小 <b>{conc?.pool_size ?? "-"}</b>，最大在途请求{" "}
                  <b>{conc?.max_inflight ?? "-"}</b>。可用环境变量 <code>TTS_ENGINE_POOL_SIZE</code>{" "}
                  / <code>TTS_MAX_INFLIGHT</code> 调整；队列满时返回 503。
                </p>
              </div>

              <hr className="status-divider" />

              <div className="status-block">
                <div className="status-label">可用模型（已下载）</div>
                <div className="model-tags">
                  {readyModels.map((m) => (
                    <Tag key={m.id} color={m.id === modelId ? "blue" : "success"}>
                      {m.name} · {langLabel(m.lang)}
                    </Tag>
                  ))}
                  {!readyModels.length ? <Text type="secondary">暂无</Text> : null}
                </div>
              </div>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
