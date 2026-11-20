import { useCallback, useEffect, useState } from 'react';
import {
  ShieldCheck, Activity, RefreshCw, AlertTriangle, CheckCircle2, XCircle,
  Clock, Settings2, Loader2, ChevronDown, ChevronRight, Sparkles, Globe,
  Key, Bot, Eye, Zap, Save, X, BookOpen,
} from 'lucide-react';
import { rescueApi, type RescueRun } from '../../services/api';

interface RescueSettings {
  enabled: number;
  provider: string;
  base_url: string;
  model_name: string;
  vision_model: string;
  vision_base_url?: string;
  vision_disable_thinking?: number;
  max_seconds: number;
  max_vision_calls: number;
  api_key_configured: boolean;
  vision_api_key_configured?: boolean;
  vision_configured?: boolean;
  offline?: boolean;
}

interface SkillItem {
  name: string;
  file: string;
  description: string;
  chars: number;
  updated_at: string;
}

const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  resolved: { label: '已救回', cls: 'text-emerald-600 bg-emerald-50' },
  failed: { label: '未救回', cls: 'text-red-600 bg-red-50' },
  timeout: { label: '超时', cls: 'text-amber-600 bg-amber-50' },
  busy: { label: '设备忙', cls: 'text-amber-600 bg-amber-50' },
  error: { label: '异常', cls: 'text-red-600 bg-red-50' },
  running: { label: '进行中', cls: 'text-[#F2A33A] bg-[#FDF1DC]' },
  disabled: { label: '未启用', cls: 'text-[#6B7076] bg-[#F0EDE6]' },
};

export function RescuePage() {
  const [health, setHealth] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [settings, setSettings] = useState<RescueSettings | null>(null);
  const [runs, setRuns] = useState<RescueRun[]>([]);
  const [skills, setSkills] = useState<{ active: SkillItem[]; drafts: SkillItem[] }>({ active: [], drafts: [] });
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, RescueRun>>({});
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pageToast, setPageToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const [provider, setProvider] = useState('openai');
  const [baseUrl, setBaseUrl] = useState('');
  const [modelName, setModelName] = useState('');
  const [visionModel, setVisionModel] = useState('');
  const [visionBaseUrl, setVisionBaseUrl] = useState('');
  const [visionApiKey, setVisionApiKey] = useState('');
  const [showVisionApiKey, setShowVisionApiKey] = useState(false);
  const [visionDisableThinking, setVisionDisableThinking] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [testing, setTesting] = useState<'op' | 'vision' | null>(null);
  const [testResult, setTestResult] = useState<{ target: 'op' | 'vision'; ok: boolean; text: string } | null>(null);
  const [maxSeconds, setMaxSeconds] = useState(150);
  const [maxVision, setMaxVision] = useState(3);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [h, s, cfg, r, sk] = await Promise.all([
        rescueApi.getHealth().catch(() => ({ ok: false, enabled: false, detail: '救援服务未运行' })),
        rescueApi.getStats(),
        rescueApi.getSettings(),
        rescueApi.getRuns({ limit: 30 }),
        rescueApi.getSkills(),
      ]);
      setHealth(h);
      setStats(s);
      setSettings(cfg);
      setRuns(r.items || []);
      setSkills({ active: sk.active || [], drafts: sk.drafts || [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (pageToast) {
      const timer = setTimeout(() => setPageToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [pageToast]);

  const openModal = () => {
    if (settings) {
      setProvider(settings.provider || 'openai');
      setBaseUrl(settings.base_url || '');
      setModelName(settings.model_name || '');
      setVisionModel(settings.vision_model || '');
      setVisionBaseUrl(settings.vision_base_url || '');
      setVisionDisableThinking(Boolean(settings.vision_disable_thinking));
      setMaxSeconds(settings.max_seconds || 150);
      setMaxVision(settings.max_vision_calls || 3);
    }
    setApiKey('');
    setVisionApiKey('');
    setShowApiKey(false);
    setShowVisionApiKey(false);
    setTestResult(null);
    setIsModalOpen(true);
  };

  const saveSettings = async (patch: Record<string, any>) => {
    setSaving(true);
    try {
      const updated = await rescueApi.updateSettings(patch);
      setSettings(updated);
      return true;
    } catch (err: any) {
      setPageToast({ type: 'error', text: err?.response?.data?.detail || '保存失败' });
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleSaveModel = async () => {
    const payload: Record<string, any> = {
      provider,
      base_url: baseUrl,
      model_name: modelName,
      vision_model: visionModel,
      vision_base_url: visionBaseUrl,
      vision_disable_thinking: visionDisableThinking ? 1 : 0,
      max_seconds: maxSeconds,
      max_vision_calls: maxVision,
    };
    if (apiKey) payload.api_key = apiKey;
    if (visionApiKey) payload.vision_api_key = visionApiKey;
    if (await saveSettings(payload)) {
      setPageToast({ type: 'success', text: '救援模型已更新' });
      setIsModalOpen(false);
      setApiKey('');
      setVisionApiKey('');
      refresh();
    }
  };

  const testModel = async (target: 'op' | 'vision') => {
    if (!settings) return;
    setTesting(target);
    setTestResult(null);
    try {
      const payload: Record<string, any> = { target };
      if (target === 'op') {
        Object.assign(payload, { provider, base_url: baseUrl, model_name: modelName });
        if (apiKey) payload.api_key = apiKey;
      } else {
        Object.assign(payload, {
          vision_base_url: visionBaseUrl,
          vision_model: visionModel,
          vision_disable_thinking: visionDisableThinking ? 1 : 0,
        });
        if (visionApiKey) payload.vision_api_key = visionApiKey;
      }
      const result = await rescueApi.testSettings(payload);
      setTestResult({ target, ok: Boolean(result.success), text: result.message || (result.success ? '连接成功' : '连接失败') });
    } catch (err: any) {
      setTestResult({ target, ok: false, text: err?.response?.data?.detail || '测试失败（救援服务不可用？）' });
    } finally {
      setTesting(null);
    }
  };

  const toggleEnabled = async () => {
    if (!settings) return;
    const next = settings.enabled ? 0 : 1;
    if (await saveSettings({ enabled: next })) {
      setPageToast({ type: next ? 'success' : 'error', text: next ? '救援已启用' : '救援已停用' });
      refresh();
    }
  };

  const promote = async (name: string) => {
    try {
      await rescueApi.promoteSkill(name);
      setPageToast({ type: 'success', text: `已提升技能 ${name}` });
      refresh();
    } catch (err: any) {
      setPageToast({ type: 'error', text: err?.response?.data?.detail || '提升失败' });
    }
  };

  const toggleRun = async (runId: string) => {
    if (expanded === runId) {
      setExpanded(null);
      return;
    }
    setExpanded(runId);
    if (!detail[runId]) {
      try {
        const full = await rescueApi.getRun(runId);
        setDetail((prev) => ({ ...prev, [runId]: full }));
      } catch {
        /* 详情拉取失败不影响列表 */
      }
    }
  };

  const online = health?.ok;
  const enabled = Boolean(settings?.enabled);
  const modelReady = Boolean(settings?.api_key_configured);
  const rate = stats?.success_rate == null ? '—' : `${Math.round(stats.success_rate * 100)}%`;

  return (
    <div className="h-full overflow-y-auto p-6">
      {pageToast && (
        <div className={`fixed top-4 right-4 z-[60] px-4 py-2 rounded-lg text-sm text-white shadow-lg ${pageToast.type === 'success' ? 'bg-emerald-500' : 'bg-red-500'}`}>
          {pageToast.text}
        </div>
      )}

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-[#16191C] flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-[#F2A33A]" />
            脚本救援
          </h1>
          <p className="text-[#6B7076] text-sm mt-1">
            脚本卡住时由救援 Agent 接管现场，修好之后脚本接着跑（记时间、翻页都不重来）
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm">
            <span className={`w-2 h-2 rounded-full ${online ? 'bg-emerald-500' : 'bg-[#9AA0A6]'}`} />
            <span className="text-[#6B7076]">{online ? '服务在线' : '服务未运行'}</span>
          </div>
          <button
            onClick={toggleEnabled}
            disabled={saving || !online}
            className={`px-4 py-2 rounded-lg text-sm flex items-center gap-2 transition-all duration-200 disabled:opacity-50 ${
              enabled ? 'bg-[#F2A33A] text-white hover:bg-[#C97F1E]' : 'bg-white border border-[#E6E1D8] text-[#6B7076]'
            }`}
          >
            {enabled ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
            {enabled ? '救援已启用' : '救援已停用'}
          </button>
          <button
            onClick={refresh}
            className="p-2 bg-white border border-[#E6E1D8] rounded-lg text-[#6B7076] hover:text-[#F2A33A] transition-all duration-200"
            title="刷新"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {!online && (
        <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
          </div>
          <div>
            <h3 className="font-medium text-amber-800 mb-1">救援服务未运行</h3>
            <p className="text-amber-700 text-sm">
              脚本会按原逻辑失败退出，不受影响。启动：<code className="font-mono">systemctl start oag-rescue</code>
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[
          { icon: <Activity className="w-4 h-4 text-[#F2A33A]" />, label: '今日救援', value: stats?.today_total ?? 0 },
          { icon: <CheckCircle2 className="w-4 h-4 text-emerald-600" />, label: '今日救回', value: stats?.today_resolved ?? 0 },
          { icon: <Sparkles className="w-4 h-4 text-amber-600" />, label: '成功率', value: rate },
          { icon: <Clock className="w-4 h-4 text-[#6B7076]" />, label: '平均耗时', value: stats?.avg_seconds ? `${stats.avg_seconds}s` : '—' },
        ].map((item) => (
          <div key={item.label} className="bg-white border border-[#E6E1D8] rounded-lg p-4">
            <div className="flex items-center gap-2 text-[#6B7076] text-xs">
              {item.icon}
              {item.label}
            </div>
            <div className="text-2xl font-semibold text-[#16191C] mt-1">{item.value}</div>
          </div>
        ))}
      </div>

      <div className="bg-white border border-[#E6E1D8] rounded-lg p-4 mb-6">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 bg-[#FDF1DC] rounded-lg flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-[#F2A33A]" />
            </div>
            <div>
              <h3 className="text-[#16191C] font-medium text-sm">救援模型</h3>
              <p className="text-[#9AA0A6] text-xs mt-0.5">
                {modelReady ? `操作：${settings?.model_name || '未命名模型'}` : '尚未配置，救援不会启动'}
              </p>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#6B7076] mt-2">
                <span className="flex items-center gap-1"><Globe className="w-3.5 h-3.5" />{settings?.base_url || '—'}</span>
                <span className="flex items-center gap-1 font-mono"><Key className="w-3.5 h-3.5" />{modelReady ? '••••••••' : '未配置'}</span>
                <span className="flex items-center gap-1">
                  <Eye className="w-3.5 h-3.5" />
                  {settings?.vision_configured
                    ? `视觉：${settings.vision_model}（独立）`
                    : `视觉：${settings?.vision_model || '与操作模型共用'}`}
                </span>
                {settings?.vision_configured && settings?.vision_base_url && (
                  <span className="flex items-center gap-1 font-mono text-[#9AA0A6]"><Globe className="w-3.5 h-3.5" />{settings.vision_base_url}</span>
                )}
                <span className="flex items-center gap-1"><Zap className="w-3.5 h-3.5" />上限：{settings?.max_seconds}s / {settings?.max_vision_calls} 次视觉</span>
              </div>
            </div>
          </div>
          <button
            onClick={openModal}
            className="px-3 py-1.5 bg-[#F2A33A] hover:bg-[#C97F1E] text-white rounded-lg text-sm flex items-center gap-1.5 transition-all duration-200"
          >
            <Settings2 className="w-4 h-4" />
            更换模型
          </button>
        </div>
      </div>

      <div className="bg-white border border-[#E6E1D8] rounded-lg mb-6">
        <div className="px-4 py-3 border-b border-[#E6E1D8] flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-[#F2A33A]" />
          <h3 className="text-[#16191C] font-medium text-sm">救援技能</h3>
          <span className="text-[#9AA0A6] text-xs">{skills.active.length} 个正式 · {skills.drafts.length} 个候选</span>
        </div>
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          {skills.active.map((skill) => (
            <div key={`a-${skill.name}`} className="border border-[#E6E1D8] rounded-lg p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-[#16191C]">{skill.name}</span>
                <span className="px-1.5 py-0.5 bg-emerald-50 text-emerald-600 text-[10px] rounded">正式</span>
              </div>
              <p className="text-xs text-[#6B7076] mt-1">{skill.description || '（无描述）'}</p>
            </div>
          ))}
          {skills.drafts.map((skill) => (
            <div key={`d-${skill.name}`} className="border border-dashed border-amber-300 bg-amber-50/40 rounded-lg p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-[#16191C]">{skill.name}</span>
                <button
                  onClick={() => promote(skill.name)}
                  className="px-1.5 py-0.5 bg-white border border-amber-300 text-amber-700 text-[10px] rounded hover:bg-amber-100"
                >
                  提升为正式
                </button>
              </div>
              <p className="text-xs text-[#7A5C33] mt-1">{skill.description || '（兜底成功自动生成）'}</p>
            </div>
          ))}
          {skills.active.length === 0 && skills.drafts.length === 0 && (
            <p className="text-xs text-[#9AA0A6]">技能目录为空，检查 /opt/oag-rescue/skills</p>
          )}
        </div>
      </div>

      <div className="bg-white border border-[#E6E1D8] rounded-lg">
        <div className="px-4 py-3 border-b border-[#E6E1D8] flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#F2A33A]" />
          <h3 className="text-[#16191C] font-medium text-sm">救援记录</h3>
        </div>
        {runs.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-[#9AA0A6]">还没有救援记录</p>
        ) : (
          <div className="divide-y divide-[#F0EDE6]">
            {runs.map((run) => {
              const style = STATUS_STYLE[run.status] || STATUS_STYLE.error;
              const open = expanded === run.rescue_id;
              const full = detail[run.rescue_id];
              return (
                <div key={run.rescue_id}>
                  <button
                    onClick={() => toggleRun(run.rescue_id)}
                    className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-[#F7F5F1]"
                  >
                    {open ? <ChevronDown className="w-4 h-4 text-[#9AA0A6]" /> : <ChevronRight className="w-4 h-4 text-[#9AA0A6]" />}
                    <span className={`px-2 py-0.5 rounded text-xs ${style.cls}`}>{style.label}</span>
                    <span className="text-sm text-[#16191C] font-medium">{run.app || run.script_name || '—'}</span>
                    <span className="text-xs text-[#6B7076]">{run.device_id}</span>
                    <span className="text-xs text-[#9AA0A6]">{run.handler || '—'}</span>
                    <span className="flex-1 text-xs text-[#9AA0A6] truncate">{run.evidence || run.error}</span>
                    <span className="text-xs text-[#9AA0A6] shrink-0">{run.created_at?.replace('T', ' ')}</span>
                  </button>
                  {open && (
                    <div className="px-12 pb-4">
                      {run.goal && <p className="text-xs text-[#6B7076] mb-2">脚本交回目标：{run.goal}</p>}
                      <div className="space-y-1.5">
                        {(full?.steps || []).map((step) => (
                          <div key={step.seq} className="flex items-start gap-2 text-xs">
                            <span className="text-[#9AA0A6] w-6 shrink-0">{step.seq}</span>
                            <span className="px-1.5 py-0.5 rounded bg-[#F0EDE6] text-[#6B7076] shrink-0">{step.phase}</span>
                            <span className={step.ok === 0 ? 'text-red-600' : 'text-[#16191C]'}>{step.detail}</span>
                            {step.screenshot && (
                              <a
                                href={rescueApi.screenshotUrl(step.screenshot)}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[#F2A33A] shrink-0"
                              >
                                截图
                              </a>
                            )}
                          </div>
                        ))}
                        {!full && <span className="text-xs text-[#9AA0A6]">加载中…</span>}
                      </div>
                      {Object.keys(run.state_patch || {}).length > 0 && (
                        <p className="text-xs text-[#6B7076] mt-2">
                          回传给脚本：{JSON.stringify(run.state_patch)}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E6E1D8]">
              <h3 className="text-[#16191C] font-medium">救援模型配置</h3>
              <button onClick={() => setIsModalOpen(false)} className="text-[#9AA0A6] hover:text-[#16191C]">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-5 max-h-[70vh] overflow-y-auto">
              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-[#16191C]">操作模型（接管现场）</h4>
                    <p className="text-[11px] text-[#9AA0A6]">PhoneAgent 用它恢复界面，通常固定一家供应商</p>
                  </div>
                  <button
                    onClick={() => testModel('op')}
                    disabled={testing !== null}
                    className="px-3 py-1.5 border border-[#E6E1D8] rounded-lg text-xs text-[#F2A33A] hover:bg-[#F7F5F1] disabled:opacity-50 flex items-center gap-1"
                  >
                    {testing === 'op' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                    测试连接
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-[#6B7076] mb-1">接口类型</label>
                    <select
                      value={provider}
                      onChange={(e) => setProvider(e.target.value)}
                      className="w-full px-3 py-2 border border-[#E6E1D8] rounded-lg text-sm"
                    >
                      <option value="openai">OpenAI 兼容</option>
                      <option value="anthropic">Anthropic</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-[#6B7076] mb-1">操作模型</label>
                    <input
                      value={modelName}
                      onChange={(e) => setModelName(e.target.value)}
                      placeholder="autoglm-phone"
                      className="w-full px-3 py-2 border border-[#E6E1D8] rounded-lg text-sm font-mono"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-[#6B7076] mb-1">Base URL</label>
                  <input
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="https://open.bigmodel.cn/api/paas/v4"
                    className="w-full px-3 py-2 border border-[#E6E1D8] rounded-lg text-sm font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[#6B7076] mb-1">API Key</label>
                  <div className="relative">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder={settings?.api_key_configured ? '已配置，留空保持不变' : '粘贴 API Key'}
                      className="w-full px-3 py-2 pr-9 border border-[#E6E1D8] rounded-lg text-sm font-mono"
                    />
                    <button
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9AA0A6]"
                      type="button"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                {testResult?.target === 'op' && (
                  <p className={`text-xs ${testResult.ok ? 'text-emerald-600' : 'text-red-600'}`}>{testResult.text}</p>
                )}
              </section>

              <div className="border-t border-[#E6E1D8]" />

              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-[#16191C]">视觉模型（截图识别，独立）</h4>
                    <p className="text-[11px] text-[#9AA0A6]">三项都填才启用；留空则沿用操作模型的 Base URL / Key</p>
                  </div>
                  <button
                    onClick={() => testModel('vision')}
                    disabled={testing !== null}
                    className="px-3 py-1.5 border border-[#E6E1D8] rounded-lg text-xs text-[#F2A33A] hover:bg-[#F7F5F1] disabled:opacity-50 flex items-center gap-1"
                  >
                    {testing === 'vision' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                    测试连接
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-[#6B7076] mb-1">视觉模型</label>
                    <input
                      value={visionModel}
                      onChange={(e) => setVisionModel(e.target.value)}
                      placeholder="留空则用操作模型"
                      className="w-full px-3 py-2 border border-[#E6E1D8] rounded-lg text-sm font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[#6B7076] mb-1">视觉 Base URL</label>
                    <input
                      value={visionBaseUrl}
                      onChange={(e) => setVisionBaseUrl(e.target.value)}
                      placeholder="留空则用操作模型"
                      className="w-full px-3 py-2 border border-[#E6E1D8] rounded-lg text-sm font-mono"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-[#6B7076] mb-1">视觉 API Key</label>
                  <div className="relative">
                    <input
                      type={showVisionApiKey ? 'text' : 'password'}
                      value={visionApiKey}
                      onChange={(e) => setVisionApiKey(e.target.value)}
                      placeholder={settings?.vision_api_key_configured ? '已配置，留空保持不变' : '留空则用操作模型的 Key'}
                      className="w-full px-3 py-2 pr-9 border border-[#E6E1D8] rounded-lg text-sm font-mono"
                    />
                    <button
                      onClick={() => setShowVisionApiKey(!showVisionApiKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9AA0A6]"
                      type="button"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <label className="flex items-center gap-2 text-xs text-[#6B7076]">
                  <input
                    type="checkbox"
                    checked={visionDisableThinking}
                    onChange={(e) => setVisionDisableThinking(e.target.checked)}
                    className="rounded border-[#E6E1D8]"
                  />
                  关闭思考模式（思考型模型可能直接报 400，测试会自动去掉该参数重试）
                </label>
                {testResult?.target === 'vision' && (
                  <p className={`text-xs ${testResult.ok ? 'text-emerald-600' : 'text-red-600'}`}>{testResult.text}</p>
                )}
              </section>

              <div className="border-t border-[#E6E1D8]" />

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-[#6B7076] mb-1">单次救援上限（秒）</label>
                  <input
                    type="number"
                    value={maxSeconds}
                    onChange={(e) => setMaxSeconds(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-[#E6E1D8] rounded-lg text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[#6B7076] mb-1">视觉判定次数</label>
                  <input
                    type="number"
                    value={maxVision}
                    onChange={(e) => setMaxVision(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-[#E6E1D8] rounded-lg text-sm"
                  />
                </div>
              </div>
            </div>
            <div className="px-5 py-3 border-t border-[#E6E1D8] flex justify-end gap-2">
              <button
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 border border-[#E6E1D8] rounded-lg text-sm text-[#6B7076]"
              >
                取消
              </button>
              <button
                onClick={handleSaveModel}
                disabled={saving}
                className="px-4 py-2 bg-[#F2A33A] hover:bg-[#C97F1E] text-white rounded-lg text-sm flex items-center gap-2 disabled:opacity-50"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}