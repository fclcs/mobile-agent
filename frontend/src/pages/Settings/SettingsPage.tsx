import { useEffect, useState } from 'react';
import { Settings, Server, Key, Globe, Plus, Trash2, Edit2, Check, Save, X, Bot, Zap, Eye, EyeOff } from 'lucide-react';
import { useModelConfigStore, type ModelConfig } from '../../stores/modelConfigStore';
import { modelConfigApi, visionModelApi } from '../../services/api';

export function SettingsPage() {
  const { configs, fetchConfigs, createConfig, updateConfig, deleteConfig } = useModelConfigStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<ModelConfig | null>(null);
  
  const [name, setName] = useState('');
  const [provider, setProvider] = useState<'openai' | 'anthropic'>('openai');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('');
  const [disableThinking, setDisableThinking] = useState(false);

  // 视觉模型（脚本截图识别）——独立一套配置，和上面的操作模型完全分开。
  const [visionModelName, setVisionModelName] = useState('');
  const [visionBaseUrl, setVisionBaseUrl] = useState('');
  const [visionApiKey, setVisionApiKey] = useState('');
  const [visionDisableThinking, setVisionDisableThinking] = useState(false);
  const [visionKeyConfigured, setVisionKeyConfigured] = useState(false);
  const [visionConfigured, setVisionConfigured] = useState(false);
  const [visionLoading, setVisionLoading] = useState(false);
  const [visionSaving, setVisionSaving] = useState(false);
  const [visionTesting, setVisionTesting] = useState(false);
  const [visionShowKey, setVisionShowKey] = useState(false);
  const [isDefault, setIsDefault] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [pageToast, setPageToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [cardTestId, setCardTestId] = useState<string | null>(null);

  const loadVisionConfig = async () => {
    setVisionLoading(true);
    try {
      const cfg: any = await visionModelApi.get();
      setVisionModelName(cfg?.model_name || '');
      setVisionBaseUrl(cfg?.base_url || '');
      setVisionDisableThinking(Boolean(cfg?.disable_thinking));
      setVisionKeyConfigured(Boolean(cfg?.api_key_configured));
      setVisionConfigured(Boolean(cfg?.configured));
      setVisionApiKey('');
    } catch {
      /* 读取失败时保持空白，不影响操作模型配置 */
    } finally {
      setVisionLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigs();
    loadVisionConfig();
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  useEffect(() => {
    if (pageToast) {
      const timer = setTimeout(() => setPageToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [pageToast]);

  const handleTestConnection = async () => {
    if (testLoading) return;
    setTestLoading(true);
    try {
      // 编辑已有配置且密钥留空时，用服务端保存的真实密钥测试。
      const res: any = editingConfig && !apiKey
        ? await modelConfigApi.testSavedConfig(editingConfig.config_id)
        : await modelConfigApi.testConfig({
            name: name || 'test',
            provider,
            base_url: baseUrl || undefined,
            api_key: apiKey,
            model_name: modelName,
            disable_thinking: disableThinking,
            is_default: false,
          });
      setTestLoading(false);
      if (res.success) {
        setToast({ type: 'success', text: `连接成功 (${res.response_time_ms}ms)` });
      } else {
        setToast({ type: 'error', text: res.message });
      }
    } catch (err: any) {
      setTestLoading(false);
      setToast({ type: 'error', text: err?.response?.data?.detail || '网络请求失败' });
    }
  };

  const handleCardTestConnection = async (config: ModelConfig) => {
    if (cardTestId) return;
    setCardTestId(config.config_id);
    try {
      const res: any = await modelConfigApi.testSavedConfig(config.config_id);
      setCardTestId(null);
      setPageToast({
        type: res.success ? 'success' : 'error',
        text: res.success ? `连接成功 (${res.response_time_ms}ms)` : res.message,
      });
    } catch (err: any) {
      setCardTestId(null);
      setPageToast({ type: 'error', text: err?.response?.data?.detail || '网络请求失败' });
    }
  };

  const resetForm = () => {
    setName('');
    setProvider('openai');
    setBaseUrl('');
    setApiKey('');
    setModelName('');
    setDisableThinking(false);
    setIsDefault(false);
    setShowApiKey(false);
    setToast(null);
    setTestLoading(false);
    setEditingConfig(null);
  };

  const handleOpenModal = (config?: ModelConfig) => {
    if (config) {
      setEditingConfig(config);
      setName(config.name);
      setProvider(config.provider);
      setBaseUrl(config.base_url || '');
      // 后端只返回掩码；这里留空表示保持原密钥，避免把“******”写回数据库。
      setApiKey('');
      setModelName(config.model_name);
      setDisableThinking(Boolean(config.disable_thinking));
      setIsDefault(config.is_default);
    } else {
      resetForm();
    }
    setToast(null);
    setTestLoading(false);
    setIsModalOpen(true);
  };

  const handleSubmit = async () => {
    if (!editingConfig && !apiKey.trim()) {
      setToast({ type: 'error', text: '新建配置必须填写 API Key' });
      return;
    }
    const data: any = {
      name,
      provider,
      base_url: baseUrl || undefined,
      model_name: modelName,
      disable_thinking: disableThinking,
      is_default: isDefault,
    };
    // 编辑时留空表示沿用原密钥；只有真正填写了新密钥才提交 api_key。
    if (!editingConfig || apiKey.trim()) {
      data.api_key = apiKey.trim();
    }

    try {
      if (editingConfig) {
        await updateConfig(editingConfig.config_id, data);
      } else {
        await createConfig(data as any);
      }
      setIsModalOpen(false);
      resetForm();
    } catch (error) {
      console.error('Failed to save model config:', error);
    }
  };

  const visionPayload = (): Record<string, any> => {
    const data: Record<string, any> = {
      model_name: visionModelName.trim(),
      base_url: visionBaseUrl.trim(),
      disable_thinking: visionDisableThinking,
    };
    // 留空表示沿用已保存的密钥（后端收到空串不会覆盖）。
    if (visionApiKey.trim()) data.api_key = visionApiKey.trim();
    return data;
  };

  const handleSaveVision = async () => {
    if (visionSaving) return;
    setVisionSaving(true);
    try {
      const cfg: any = await visionModelApi.update(visionPayload());
      setVisionConfigured(Boolean(cfg?.configured));
      setVisionKeyConfigured(Boolean(cfg?.api_key_configured));
      setVisionApiKey('');
      setPageToast({ type: 'success', text: '视觉模型配置已保存（对新的流程运行生效）' });
    } catch (err: any) {
      setPageToast({ type: 'error', text: err?.response?.data?.detail || '保存失败' });
    } finally {
      setVisionSaving(false);
    }
  };

  const handleTestVision = async () => {
    if (visionTesting) return;
    setVisionTesting(true);
    try {
      const res: any = await visionModelApi.test(visionPayload());
      setPageToast({
        type: res.success ? 'success' : 'error',
        text: res.success ? `视觉模型连接成功${res.response_time_ms ? ` (${res.response_time_ms}ms)` : ''}` : res.message,
      });
    } catch (err: any) {
      setPageToast({ type: 'error', text: err?.response?.data?.detail || '网络请求失败' });
    } finally {
      setVisionTesting(false);
    }
  };

  return (
    <div className="animate-fade-in">
      {pageToast && (
        <div className={`mb-4 p-3 rounded-lg flex items-center gap-2 text-sm ${
          pageToast.type === 'success'
            ? 'bg-green-50 border border-green-200 text-green-700'
            : 'bg-red-50 border border-red-200 text-red-700'
        }`}>
          {pageToast.type === 'success' ? <Check className="w-4 h-4 shrink-0" /> : <X className="w-4 h-4 shrink-0" />}
          {pageToast.text}
        </div>
      )}

      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-[#16191C] flex items-center gap-2">
            <Settings className="w-5 h-5 text-[#F2A33A]" />
            模型配置
          </h1>
          <p className="text-[#6B7076] text-sm mt-1">操作模型（手机 PhoneAgent）与脚本视觉识别模型分开配置，互不影响</p>
        </div>
        <button
          onClick={() => handleOpenModal()}
          className="px-4 py-2 bg-[#F2A33A] hover:bg-[#C97F1E] text-white rounded-lg flex items-center gap-2 transition-all duration-200"
        >
          <Plus className="w-4 h-4" />
          新增模型配置
        </button>
      </div>

      <div className="mb-6 p-4 bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
          <Zap className="w-4 h-4 text-amber-600" />
        </div>
        <div>
          <h3 className="font-medium text-amber-800 mb-1">重要提示</h3>
          <p className="text-amber-700 text-sm">
            当前项目基于 <span className="font-semibold">VLM 视觉大模型</span> 驱动的 Phone Agent。
            请确保配置支持视觉能力的模型（如 GPT-4V、Claude 3.5 Sonnet 等），否则将无法正常使用智能体功能。
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {configs.map((config) => (
          <div
            key={config.config_id}
            className="bg-white border border-[#E6E1D8] rounded-lg p-4 hover:border-[#F2A33A] hover:shadow-md transition-all duration-200 relative"
          >
            {config.is_default && (
              <div className="absolute top-2 right-2 px-2 py-0.5 bg-[#F2A33A] text-white text-xs font-medium rounded flex items-center gap-1">
                <Check className="w-3 h-3" />
                默认
              </div>
            )}
            
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className={`w-10 h-10 ${config.provider === 'openai' ? 'bg-[#FDF1DC]' : 'bg-[#FCEEDC]'} rounded-lg flex items-center justify-center shrink-0`}>
                  {config.provider === 'openai' ? <Bot className="w-5 h-5 text-[#F2A33A]" /> : <Zap className="w-5 h-5 text-[#E0A02F]" />}
                </div>
                <div>
                  <h3 className="text-[#16191C] font-medium text-sm">{config.name}</h3>
                  <p className="text-[#9AA0A6] text-xs uppercase">{config.provider}</p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleCardTestConnection(config)}
                  disabled={cardTestId !== null}
                  className="p-1.5 text-[#3FB950] hover:bg-[#E3F5E7] rounded-lg transition-all duration-200 disabled:opacity-50"
                  title="测试连接"
                >
                  {cardTestId === config.config_id ? (
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  ) : (
                    <Zap className="w-4 h-4" />
                  )}
                </button>
                <button
                  onClick={() => handleOpenModal(config)}
                  className="p-1.5 text-[#9AA0A6] hover:text-[#F2A33A] hover:bg-[#FDF1DC] rounded-lg transition-all duration-200"
                  title="编辑"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => {
                    if (confirm('确定要删除此模型配置吗？')) {
                      deleteConfig(config.config_id);
                    }
                  }}
                  className="p-1.5 text-[#9AA0A6] hover:text-[#E5484D] hover:bg-[#FBEAE8] rounded-lg transition-all duration-200"
                  title="删除"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="space-y-1.5 text-xs">
              <div className="flex items-center gap-2">
                <Server className="w-3.5 h-3.5 text-[#9AA0A6] shrink-0" />
                <span className="text-[#9AA0A6] shrink-0 w-10">操作:</span>
                <span className="text-[#16191C] truncate">{config.model_name}</span>
              </div>
              <div className="flex items-center gap-2">
                <Zap className="w-3.5 h-3.5 text-[#9AA0A6] shrink-0" />
                <span className="text-[#9AA0A6] shrink-0 w-10">思考:</span>
                <span className={config.disable_thinking ? 'text-[#F2A33A]' : 'text-[#16191C]'}>
                  {config.disable_thinking ? '已关闭' : '开启'}
                </span>
              </div>
              {config.base_url && (
                <div className="flex items-center gap-2">
                  <Globe className="w-3.5 h-3.5 text-[#9AA0A6] shrink-0" />
                  <span className="text-[#9AA0A6] shrink-0 w-10">地址:</span>
                  <span className="text-[#16191C] truncate">{config.base_url}</span>
                </div>
              )}
              <div className="flex items-center gap-2">
                <Key className="w-3.5 h-3.5 text-[#9AA0A6] shrink-0" />
                <span className="text-[#9AA0A6] shrink-0 w-10">API Key:</span>
                <span className="text-[#6B7076] font-mono">••••••••</span>
              </div>
            </div>
          </div>
        ))}

        {configs.length === 0 && (
          <div className="col-span-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-16 flex flex-col items-center justify-center text-center">
            <Server className="w-12 h-12 text-[#9AA0A6] mb-3" />
            <h3 className="text-[#16191C] text-base font-medium mb-1.5">暂无模型配置</h3>
            <p className="text-[#6B7076] text-sm">创建一个模型配置以开始使用 Agent</p>
          </div>
        )}
      </div>

      <div className="mt-6 bg-white border border-[#E6E1D8] rounded-lg p-5">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 bg-[#F1EDFB] rounded-lg flex items-center justify-center shrink-0">
              <Eye className="w-5 h-5 text-[#7C6BD6]" />
            </div>
            <div>
              <h3 className="text-[#16191C] font-medium text-sm">视觉模型（脚本视觉识别 · 独立）</h3>
              <p className="text-[#9AA0A6] text-xs mt-0.5">
                {visionConfigured
                  ? `已启用独立配置：${visionModelName || '未命名模型'}`
                  : '三项填齐才启用；留空则沿用操作模型的 Base URL / Key（旧方式）'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleTestVision}
              disabled={visionTesting || visionLoading}
              className="px-3 py-2 rounded-lg text-sm bg-[#F0EDE6] border border-[#E6E1D8] text-[#6B7076] hover:bg-[#E6E1D8] disabled:opacity-50 flex items-center gap-1.5"
            >
              {visionTesting ? (
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : <Zap className="w-4 h-4" />}
              {visionTesting ? '测试中...' : '测试连接'}
            </button>
            <button
              onClick={handleSaveVision}
              disabled={visionSaving || visionLoading}
              className="px-3 py-2 rounded-lg text-sm bg-[#F2A33A] hover:bg-[#C97F1E] text-white disabled:opacity-50 flex items-center gap-1.5"
            >
              <Save className="w-4 h-4" />
              {visionSaving ? '保存中...' : '保存'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-[#6B7076] text-sm mb-2">视觉模型名称</label>
            <input
              type="text"
              value={visionModelName}
              onChange={(e) => setVisionModelName(e.target.value)}
              className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2.5 px-3 text-[#16191C] text-sm placeholder-[#9AA0A6] focus:outline-none focus:border-[#F2A33A] focus:ring-1 focus:ring-[#F2A33A] transition-all duration-200"
              placeholder="例如: glm-4v-plus / glm-5.3-flash"
            />
          </div>
          <div>
            <label className="block text-[#6B7076] text-sm mb-2">视觉 Base URL</label>
            <input
              type="text"
              value={visionBaseUrl}
              onChange={(e) => setVisionBaseUrl(e.target.value)}
              className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2.5 px-3 text-[#16191C] text-sm placeholder-[#9AA0A6] focus:outline-none focus:border-[#F2A33A] focus:ring-1 focus:ring-[#F2A33A] transition-all duration-200"
              placeholder="例如: https://ark.cn-beijing.volces.com/api/plan/v3"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 items-end">
          <div>
            <label className="block text-[#6B7076] text-sm mb-2">视觉 API Key</label>
            <div className="relative">
              <input
                type={visionShowKey ? 'text' : 'password'}
                value={visionApiKey}
                onChange={(e) => setVisionApiKey(e.target.value)}
                className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2.5 pl-3 pr-10 text-[#16191C] text-sm placeholder-[#9AA0A6] focus:outline-none focus:border-[#F2A33A] focus:ring-1 focus:ring-[#F2A33A] transition-all duration-200"
                placeholder={visionKeyConfigured ? '已配置，留空保持不变' : '粘贴视觉模型 API Key'}
              />
              <button
                type="button"
                onClick={() => setVisionShowKey(!visionShowKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#9AA0A6] hover:text-[#16191C] transition-all duration-200"
              >
                {visionShowKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-[#16191C] pb-2.5">
            <input
              type="checkbox"
              checked={visionDisableThinking}
              onChange={(e) => setVisionDisableThinking(e.target.checked)}
              className="w-4 h-4 rounded border-[#E6E1D8]"
            />
            关闭思考模式
            <span className="text-[#9AA0A6] text-xs">（思考模型若报 400，测试会自动去掉该参数重试）</span>
          </label>
        </div>

        <p className="text-[#9AA0A6] text-xs mt-3">
          脚本里的广告/遮挡/页面识别用它；模型名、Base URL、Key 三项齐全才对新的流程运行生效，任一项为空就回到操作模型那套。
        </p>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white border border-[#E6E1D8] rounded-lg w-full max-w-lg shadow-lg">
            <div className="flex items-center justify-between p-5 border-b border-[#F0EDE6]">
              <h2 className="text-base font-semibold text-[#16191C]">
                {editingConfig ? '编辑模型配置' : '新增模型配置'}
              </h2>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1.5 hover:bg-[#F0EDE6] rounded-lg transition-all duration-200"
              >
                <X className="w-4 h-4 text-[#6B7076]" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#6B7076] text-sm mb-2">配置名称</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2.5 px-3 text-[#16191C] text-sm placeholder-[#9AA0A6] focus:outline-none focus:border-[#F2A33A] focus:ring-1 focus:ring-[#F2A33A] transition-all duration-200"
                    placeholder="例如: GPT-4o"
                  />
                </div>
                <div>
                  <label className="block text-[#6B7076] text-sm mb-2">Provider</label>
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value as any)}
                    className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2.5 px-3 text-[#16191C] text-sm focus:outline-none focus:border-[#F2A33A] focus:ring-1 focus:ring-[#F2A33A] transition-all duration-200"
                  >
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-[#6B7076] text-sm mb-2">
                  操作模型 <span className="text-[#E5484D]">*</span>
                </label>
                <input
                  type="text"
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2.5 px-3 text-[#16191C] text-sm placeholder-[#9AA0A6] focus:outline-none focus:border-[#F2A33A] focus:ring-1 focus:ring-[#F2A33A] transition-all duration-200"
                  placeholder="例如: autoglm-phone"
                />
                <p className="text-[#9AA0A6] text-xs mt-1.5">
                  手机操作与脚本执行决策使用此模型；默认绑定智谱 AutoGLM-Phone（限时免费），更换后对新的流程运行生效。
                </p>
              </div>

              <div>
                <label className="block text-[#6B7076] text-sm mb-2">
                  API Base URL <span className="text-[#E5484D]">*</span>
                </label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2.5 px-3 text-[#16191C] text-sm placeholder-[#9AA0A6] focus:outline-none focus:border-[#F2A33A] focus:ring-1 focus:ring-[#F2A33A] transition-all duration-200"
                  placeholder="例如: https://api.openai.com/v1"
                />
              </div>

              <div>
                <label className="block text-[#6B7076] text-sm mb-2">
                  API Key {!editingConfig && <span className="text-[#E5484D]">*</span>}
                </label>
                <div className="relative">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2.5 pl-3 pr-10 text-[#16191C] text-sm placeholder-[#9AA0A6] focus:outline-none focus:border-[#F2A33A] focus:ring-1 focus:ring-[#F2A33A] transition-all duration-200"
                    placeholder={editingConfig ? '留空则保持现有密钥不变' : '输入您的 API Key'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#9AA0A6] hover:text-[#16191C] transition-all duration-200"
                  >
                    {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="flex items-start gap-3 py-2">
                <button
                  onClick={() => setDisableThinking(!disableThinking)}
                  className={`mt-0.5 w-10 h-5 rounded-full transition-all duration-200 relative shrink-0 ${disableThinking ? 'bg-[#F2A33A]' : 'bg-[#E6E1D8]'}`}
                >
                  <div className={`absolute top-1 w-3 h-3 bg-white rounded-full transition-all duration-200 ${disableThinking ? 'left-6' : 'left-1'}`} />
                </button>
                <div>
                  <span className="text-[#16191C] text-sm">关闭思考模式</span>
                  <p className="text-[#9AA0A6] text-xs mt-1">
                    带思考/推理模式的模型（如 GLM-5.3-flash、DeepSeek-R1 等）请打开。打开后请求会带
                    <code className="mx-1 text-[#6B7076]">enable_thinking=false</code>，
                    否则模型会把全部输出额度用于推理，正文为空，视觉识别会失败。
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3 py-2">
                <button
                  onClick={() => setIsDefault(!isDefault)}
                  className={`w-10 h-5 rounded-full transition-all duration-200 relative ${isDefault ? 'bg-[#F2A33A]' : 'bg-[#E6E1D8]'}`}
                >
                  <div className={`absolute top-1 w-3 h-3 bg-white rounded-full transition-all duration-200 ${isDefault ? 'left-6' : 'left-1'}`} />
                </button>
                <span className="text-[#16191C] text-sm">设置为默认配置</span>
              </div>
            </div>

            {toast && (
              <div className={`mx-5 mb-3 p-2.5 rounded-lg flex items-center gap-2 text-sm ${
                toast.type === 'success'
                  ? 'bg-[#E3F5E7] border border-[#C3E9CC] text-[#1F7A34]'
                  : 'bg-[#F8DAD7] border border-[#EFC2BE] text-[#8E2A2D]'
              }`}>
                {toast.type === 'success' ? <Check className="w-4 h-4 shrink-0" /> : <X className="w-4 h-4 shrink-0" />}
                {toast.text}
              </div>
            )}
            <div className="flex gap-2 p-5 pt-0">
              <button
                onClick={handleTestConnection}
                disabled={!name || !baseUrl || !modelName || testLoading || (!editingConfig && !apiKey)}
                className="px-3 py-2 rounded-lg flex items-center justify-center gap-2 text-sm bg-[#F0EDE6] border border-[#E6E1D8] text-[#6B7076] hover:bg-[#E6E1D8] disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
              >
                {testLoading ? (
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : null}
                {testLoading ? '测试中...' : '测试连接'}
              </button>
              <button
                onClick={() => setIsModalOpen(false)}
                className="flex-1 px-4 py-2 bg-[#F0EDE6] hover:bg-[#E6E1D8] text-[#6B7076] rounded-lg text-sm font-medium transition-all duration-200"
              >
                取消
              </button>
              <button
                onClick={handleSubmit}
                disabled={!name || !baseUrl || !modelName || (!editingConfig && !apiKey)}
                className="flex-1 px-4 py-2 bg-[#F2A33A] hover:bg-[#C97F1E] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all duration-200"
              >
                <Save className="w-4 h-4" />
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}