import { useEffect, useState } from 'react';
import {
  Smartphone,
  Power,
  Monitor,
  Wifi,
  AlertCircle,
  CheckCircle,
  Loader2,
  RefreshCw,
  Zap,
  Plus,
  Pencil,
  Trash2,
  Tag,
  X,
} from 'lucide-react';
import { useDeviceStore, type Device } from '../../stores/deviceStore';
import { DeviceDetailDrawer } from '../../components/DeviceDetailDrawer';

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { bg: string; text: string; label: string; dot: string }> = {
    connected: { bg: 'bg-emerald-50', text: 'text-emerald-600', label: '在线', dot: 'bg-emerald-500 animate-pulse' },
    disconnected: { bg: 'bg-slate-100', text: 'text-slate-500', label: '离线', dot: 'bg-slate-400' },
    busy: { bg: 'bg-amber-50', text: 'text-amber-600', label: '测试中', dot: 'bg-amber-500 animate-pulse' },
    error: { bg: 'bg-red-50', text: 'text-red-600', label: '错误', dot: 'bg-red-500 animate-pulse' },
  };

  const c = config[status] || config.disconnected;

  return (
    <div className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-medium border ${c.bg} ${c.text} border-current/20`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </div>
  );
}

function ConnectionBadge({ type, ip }: { type?: string; ip?: string }) {
  if (type === 'usb') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-blue-50 text-blue-600 border border-blue-100">
        <Zap size={10} /> USB
      </span>
    );
  }
  if (type === 'tcpip') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-emerald-50 text-emerald-600 border border-emerald-100">
        <Wifi size={10} /> TCP/IP
        {ip && <span className="font-mono opacity-70">{ip}</span>}
      </span>
    );
  }
  return null;
}

interface DeviceForm {
  device_id: string;
  name: string;
  remark: string;
  group_name: string;
}

const emptyForm: DeviceForm = { device_id: '', name: '', remark: '', group_name: '' };

export function DevicePage() {
  const {
    devices,
    fetchDevices,
    connectDevice,
    disconnectDevice,
    enableWireless,
    registerDevice,
    updateDevice,
    deleteDevice,
    enablingWirelessDeviceId,
    openDrawer,
    error,
    success,
    clearMessages,
  } = useDeviceStore();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [form, setForm] = useState<DeviceForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    fetchDevices();
  }, []);

  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => clearMessages(), 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success, clearMessages]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchDevices();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchDevices]);

  const getPlatformColor = (platform: string) => {
    switch (platform) {
      case 'android':
        return '#3FB950';
      case 'ios':
        return '#2C3238';
      case 'harmonyos':
        return '#E89C38';
      default:
        return '#6B7076';
    }
  };

  function openCreate() {
    setEditingDevice(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  }

  function openEdit(device: Device) {
    setEditingDevice(device);
    setForm({
      device_id: device.device_id,
      name: device.name || '',
      remark: device.remark || '',
      group_name: device.group_name || '',
    });
    setFormError('');
    setModalOpen(true);
  }

  async function submitForm() {
    if (!form.device_id.trim()) {
      setFormError('请填写设备 serial（如 10.0.0.11:5555）');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      const payload = {
        name: form.name.trim() || undefined,
        remark: form.remark.trim(),
        group_name: form.group_name.trim(),
      };
      const ok = editingDevice
        ? await updateDevice(editingDevice.device_id, payload)
        : await registerDevice({ device_id: form.device_id.trim(), ...payload });
      if (ok) setModalOpen(false);
    } finally {
      setSaving(false);
    }
  }

  async function removeDevice(device: Device) {
    if (!window.confirm(`确定从登记表移除“${device.name || device.device_id}”吗？删除后若该手机再次在线会被自动登记。`)) return;
    await deleteDevice(device.device_id);
  }

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Smartphone size={20} className="text-indigo-500" />
            <span className="text-sm font-medium text-indigo-500">设备管理</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">手机管理</h1>
          <p className="text-slate-500 mt-1 flex items-center gap-2">
            在线 {devices.filter((d) => d.status === 'connected').length} 台 · 已登记 {devices.length} 台
            <span className="flex items-center gap-1 text-xs text-emerald-600">
              <RefreshCw size={12} className="animate-spin" />
              自动刷新
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => void fetchDevices()} className="btn btn-secondary" title="刷新设备">
            <RefreshCw size={16} />
          </button>
          <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-[#F2A33A] hover:bg-[#C97F1E] text-white rounded-lg text-sm">
            <Plus size={16} />添加手机
          </button>
        </div>
      </div>

      {error && (
        <div
          className="mb-4 p-4 rounded-xl flex items-center gap-3 border"
          style={{
            background: 'rgba(239, 68, 68, 0.05)',
            borderColor: 'rgba(239, 68, 68, 0.15)',
          }}
        >
          <AlertCircle size={18} className="text-red-500 flex-shrink-0" />
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {success && (
        <div
          className="mb-4 p-4 rounded-xl flex items-center gap-3 border"
          style={{
            background: 'rgba(34, 197, 94, 0.05)',
            borderColor: 'rgba(34, 197, 94, 0.15)',
          }}
        >
          <CheckCircle size={18} className="text-emerald-500 flex-shrink-0" />
          <p className="text-sm text-emerald-700">{success}</p>
        </div>
      )}

      {enablingWirelessDeviceId && (
        <div
          className="mb-4 p-4 rounded-xl flex items-center gap-3 border"
          style={{
            background: 'rgba(59, 130, 246, 0.05)',
            borderColor: 'rgba(59, 130, 246, 0.15)',
          }}
        >
          <Loader2 size={18} className="text-blue-500 animate-spin flex-shrink-0" />
          <p className="text-sm text-blue-700">
            正在为设备{' '}
            {devices.find((d) => d.device_id === enablingWirelessDeviceId)?.name ||
              enablingWirelessDeviceId}{' '}
            开启无线连接...
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {devices.map((device) => (
          <div
            key={device.device_id}
            className="rounded-xl p-5 transition-all duration-300 hover:scale-[1.02]"
            style={{
              background: '#ffffff',
              border: '1px solid #E6E1D8',
              boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
              opacity: device.status === 'connected' ? 1 : 0.92,
            }}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
                  style={{
                    background: `${getPlatformColor(device.platform)}10`,
                    border: `1px solid ${getPlatformColor(device.platform)}20`,
                  }}
                >
                  <Smartphone
                    size={24}
                    style={{ color: getPlatformColor(device.platform) }}
                  />
                </div>
                <div className="min-w-0">
                  <h3 className="text-slate-900 font-semibold truncate">{device.name}</h3>
                  <p className="text-xs font-mono text-slate-500 mt-0.5 truncate" title={device.device_id}>
                    {device.device_id}
                  </p>
                </div>
              </div>
              <StatusBadge status={device.status} />
            </div>

            {device.remark && (
              <p className="text-xs text-slate-500 mb-2 line-clamp-2" title={device.remark}>
                {device.remark}
              </p>
            )}

            <div className="flex flex-wrap gap-2 mb-3">
              {device.os_version && (
                <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                  {device.os_version}
                </span>
              )}
              {device.screen_width && device.screen_height && (
                <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                  {device.screen_width}x{device.screen_height}
                </span>
              )}
              {device.group_name && (
                <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-indigo-50 text-indigo-600 border border-indigo-100">
                  <Tag size={10} />{device.group_name}
                </span>
              )}
              <ConnectionBadge type={device.connection_type} ip={device.ip} />
            </div>

            {device.status !== 'connected' && device.last_seen_at && (
              <p className="text-xs text-slate-400 mb-3">最后在线：{device.last_seen_at.replace('T', ' ')}</p>
            )}

            <div className="flex gap-2 pt-3 border-t border-slate-200" style={{ borderColor: '#E6E1D8' }}>
              {device.status === 'disconnected' ? (
                <button
                  onClick={() => connectDevice(device.device_id)}
                  className="flex-1 btn btn-success"
                  title="重新连接"
                >
                  <Power size={14} />
                  连接
                </button>
              ) : device.status === 'busy' ? (
                <button disabled className="flex-1 btn" style={{ background: '#E0A02F15', color: '#E0A02F', border: '1px solid #E0A02F25' }}>
                  <Loader2 size={14} className="animate-spin" />
                  测试中
                </button>
              ) : (
                <>
                  {device.connection_type !== 'tcpip' && (
                    <button
                      onClick={() => enableWireless(device.device_id)}
                      disabled={enablingWirelessDeviceId === device.device_id}
                      className="flex-1 btn btn-primary"
                      title={enablingWirelessDeviceId === device.device_id ? '开启中...' : '开启无线'}
                    >
                      <Wifi size={14} />
                    </button>
                  )}
                  {device.connection_type === 'tcpip' && (
                    <button
                      onClick={() => disconnectDevice(device.device_id)}
                      className="flex-1 btn btn-danger"
                      title="断开连接"
                    >
                      <Power size={14} />
                    </button>
                  )}
                </>
              )}
              <button onClick={() => openEdit(device)} className="flex-1 btn btn-secondary" title="编辑名称/备注/分组">
                <Pencil size={14} />
              </button>
              <button
                onClick={() => void removeDevice(device)}
                disabled={device.status === 'connected'}
                className="flex-1 btn btn-secondary disabled:opacity-40"
                title={device.status === 'connected' ? '在线设备请先断开连接再删除' : '从登记表移除'}
              >
                <Trash2 size={14} />
              </button>
              <button
                onClick={() => openDrawer(device)}
                className="flex-1 btn btn-secondary"
                title="设备详情"
              >
                <Monitor size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {devices.length === 0 && (
        <div
          className="text-center py-24 rounded-xl"
          style={{
            background: '#ffffff',
            border: '1px solid #E6E1D8',
          }}
        >
          <Smartphone size={56} className="mx-auto mb-4 text-slate-300" />
          <h3 className="text-slate-900 text-lg font-medium mb-2">暂无设备</h3>
          <p className="text-slate-500 text-sm">连接手机后会自动登记；也可以点击“添加手机”手动登记离线设备</p>
        </div>
      )}

      {modalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-5 w-full max-w-md mx-4 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">{editingDevice ? '编辑手机信息' : '添加手机'}</h2>
              <button onClick={() => setModalOpen(false)} className="p-1 text-slate-400 hover:text-slate-700" aria-label="关闭">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">设备 serial</label>
                <input
                  value={form.device_id}
                  disabled={Boolean(editingDevice)}
                  onChange={(event) => setForm({ ...form, device_id: event.target.value })}
                  placeholder="如 10.0.0.11:5555 或 USB 序列号"
                  className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2 px-3 text-sm outline-none focus:border-[#F2A33A] disabled:text-slate-400"
                />
                <p className="text-xs text-slate-400 mt-1">在线设备会自动登记，这里用于登记暂时离线的手机</p>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">名称</label>
                <input
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  placeholder="如：手机1"
                  className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2 px-3 text-sm outline-none focus:border-[#F2A33A]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">备注</label>
                <textarea
                  value={form.remark}
                  onChange={(event) => setForm({ ...form, remark: event.target.value })}
                  rows={2}
                  placeholder="如：阅读专用 / 主力测试机"
                  className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2 px-3 text-sm outline-none focus:border-[#F2A33A]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">分组</label>
                <input
                  value={form.group_name}
                  onChange={(event) => setForm({ ...form, group_name: event.target.value })}
                  placeholder="如：拉新组"
                  className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2 px-3 text-sm outline-none focus:border-[#F2A33A]"
                />
              </div>
              {formError && <p className="text-sm text-red-600">{formError}</p>}
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setModalOpen(false)} className="px-4 py-2 bg-[#F0EDE6] text-[#6B7076] rounded-lg text-sm">取消</button>
              <button
                disabled={saving}
                onClick={() => void submitForm()}
                className="px-4 py-2 bg-[#F2A33A] disabled:bg-slate-300 text-white rounded-lg text-sm"
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      <DeviceDetailDrawer />
    </div>
  );
}