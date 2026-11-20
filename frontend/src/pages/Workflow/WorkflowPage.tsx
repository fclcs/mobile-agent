import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  Check,
  CheckCircle2,
  Clock3,
  FileCode,
  Image as ImageIcon,
  Loader2,
  Pencil,
  Play,
  Plus,
  SkipForward,
  Smartphone,
  Square,
  Trash2,
  Workflow as WorkflowIcon,
  XCircle,
} from 'lucide-react';
import {
  deviceApi,
  rescueApi,
  scriptApi,
  workflowApi,
  type RescueRun,
  type WorkflowDefinition,
  type WorkflowRun,
  type WorkflowRunStep,
} from '../../services/api';
import type { Script } from '../../stores/agentStore';
import type { Device } from '../../stores/deviceStore';

const terminalStatuses = new Set(['completed', 'partial', 'failed', 'cancelled']);
const activeStatuses = new Set(['pending', 'executing']);

function errorMessage(error: unknown): string {
  const value = error as { response?: { data?: { detail?: string } }; message?: string };
  return value.response?.data?.detail || value.message || '操作失败';
}

function formatTime(value?: string): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-';
}

function StepStatus({ status }: { status: WorkflowRunStep['status'] | 'partial' }) {
  const config = {
    pending: { label: '等待', className: 'bg-slate-100 text-slate-500', icon: <Clock3 size={14} /> },
    executing: { label: '执行中', className: 'bg-blue-50 text-blue-600', icon: <Loader2 size={14} className="animate-spin" /> },
    completed: { label: '已完成', className: 'bg-green-50 text-green-600', icon: <CheckCircle2 size={14} /> },
    failed: { label: '失败', className: 'bg-red-50 text-red-600', icon: <XCircle size={14} /> },
    partial: { label: '部分完成', className: 'bg-amber-50 text-amber-600', icon: <SkipForward size={14} /> },
    skipped: { label: '已跳过', className: 'bg-amber-50 text-amber-600', icon: <SkipForward size={14} /> },
    cancelled: { label: '已中断', className: 'bg-slate-100 text-slate-500', icon: <XCircle size={14} /> },
  }[status];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs ${config.className}`}>
      {config.icon}{config.label}
    </span>
  );
}

function RunStatus({ status }: { status: WorkflowRun['status'] }) {
  const config: Record<WorkflowRun['status'], { label: string; className: string }> = {
    pending: { label: '等待中', className: 'bg-slate-100 text-slate-500' },
    executing: { label: '执行中', className: 'bg-blue-50 text-blue-600' },
    completed: { label: '已完成', className: 'bg-green-50 text-green-600' },
    partial: { label: '部分完成', className: 'bg-amber-50 text-amber-600' },
    failed: { label: '失败', className: 'bg-red-50 text-red-600' },
    cancelled: { label: '已中断', className: 'bg-slate-100 text-slate-500' },
  };
  const item = config[status];
  return (
    <span className={`px-2 py-0.5 rounded text-xs whitespace-nowrap ${item.className}`}>
      {item.label}
    </span>
  );
}


export function WorkflowPage() {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState('');
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [runDetail, setRunDetail] = useState<WorkflowRun | null>(null);
  const [rescueByStep, setRescueByStep] = useState<Record<string, RescueRun[]>>({});
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<string[]>([]);
  const [allRuns, setAllRuns] = useState<WorkflowRun[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formScripts, setFormScripts] = useState<Script[]>([]);
  const [formContinueOnError, setFormContinueOnError] = useState(false);
  const [formStepTimeoutMinutes, setFormStepTimeoutMinutes] = useState('0');
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [interruptingRunId, setInterruptingRunId] = useState<string | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const selectedWorkflow = workflows.find(item => item.workflow_id === selectedWorkflowId) || null;
  const connectedDevices = devices.filter(item => item.status === 'connected');
  const busyDeviceIds = useMemo(
    () => new Set(
      allRuns
        .filter(run => !terminalStatuses.has(run.status))
        .map(run => run.device_id),
    ),
    [allRuns],
  );
  const hasActiveRuns = runs.some(run => !terminalStatuses.has(run.status));
  // 只有已结束（完成/部分完成/失败/已中断）的记录可以被删除。
  const deletableRuns = useMemo(
    () => runs.filter(run => terminalStatuses.has(run.status)),
    [runs],
  );
  const allDeletableSelected = deletableRuns.length > 0
    && deletableRuns.every(run => selectedRunIds.has(run.run_id));

  const loadWorkflows = useCallback(async () => {
    const response = await workflowApi.getWorkflows() as unknown as { workflows: WorkflowDefinition[] };
    setWorkflows(response.workflows);
    setSelectedWorkflowId(current => {
      if (response.workflows.some(item => item.workflow_id === current)) return current;
      return response.workflows[0]?.workflow_id || '';
    });
  }, []);

  const loadRuns = useCallback(async (workflowId: string) => {
    if (!workflowId) {
      setRuns([]);
      setSelectedRunId('');
      return;
    }
    const response = await workflowApi.getRuns(workflowId) as unknown as { runs: WorkflowRun[] };
    setRuns(response.runs);
    setSelectedRunId(current => {
      if (response.runs.some(item => item.run_id === current)) return current;
      return response.runs[0]?.run_id || '';
    });
  }, []);

  const loadAllRuns = useCallback(async () => {
    const response = await workflowApi.getRuns() as unknown as { runs: WorkflowRun[] };
    setAllRuns(response.runs);
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const [scriptResponse, deviceResponse] = await Promise.all([
          scriptApi.getScripts(),
          deviceApi.getDevices(),
          loadAllRuns(),
        ]);
        setScripts((scriptResponse as unknown as { scripts: Script[] }).scripts);
        const deviceList = (deviceResponse as unknown as { devices: Device[] }).devices;
        setDevices(deviceList);
        setSelectedDeviceIds(
          deviceList.filter(item => item.status === 'connected').map(item => item.device_id),
        );
        await loadWorkflows();
      } catch (loadError) {
        setError(errorMessage(loadError));
      }
    }
    void initialize();
  }, [loadWorkflows, loadAllRuns]);

  // 选中的手机必须在当前在线列表中；执行中的手机自动取消选择。
  useEffect(() => {
    setSelectedDeviceIds(current => current.filter(
      deviceId => !busyDeviceIds.has(deviceId)
        && connectedDevices.some(device => device.device_id === deviceId),
    ));
  }, [busyDeviceIds, devices]);

  // 有流程在跑时刷新历史记录和忙碌状态。
  useEffect(() => {
    if (!hasActiveRuns && busyDeviceIds.size === 0) return;
    const timer = setInterval(() => {
      if (selectedWorkflowId) void loadRuns(selectedWorkflowId);
      void loadAllRuns();
    }, 2000);
    return () => clearInterval(timer);
  }, [hasActiveRuns, busyDeviceIds.size, selectedWorkflowId, loadRuns, loadAllRuns]);

  useEffect(() => {
    void loadRuns(selectedWorkflowId).catch(loadError => setError(errorMessage(loadError)));
  }, [selectedWorkflowId, loadRuns]);

  // 列表刷新后清掉已不存在/已变为运行中的选中项，避免批量删除误删。
  useEffect(() => {
    setSelectedRunIds(current => {
      if (current.size === 0) return current;
      const allowed = new Set(runs.map(run => run.run_id));
      const next = new Set([...current].filter(id => allowed.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [runs]);

  useEffect(() => {
    if (!selectedRunId) {
      setRunDetail(null);
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function pollRun() {
      try {
        const detail = await workflowApi.getRun(selectedRunId) as unknown as WorkflowRun;
        if (!active) return;
        setRunDetail(detail);
        try {
          // 救援记录挂在步骤下面；救援服务没开时这里静默跳过，不影响流程页。
          const rescue = await rescueApi.getRuns({ run_id: selectedRunId, limit: 100 });
          if (!active) return;
          const grouped: Record<string, RescueRun[]> = {};
          for (const item of rescue.items || []) {
            (grouped[item.step_id] ||= []).push(item);
          }
          setRescueByStep(grouped);
        } catch {
          /* ignore */
        }
        if (!terminalStatuses.has(detail.status)) {
          timer = setTimeout(() => void pollRun(), 1500);
        } else {
          void loadRuns(selectedWorkflowId);
        }
      } catch (pollError) {
        if (active) setError(errorMessage(pollError));
      }
    }

    void pollRun();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [selectedRunId, selectedWorkflowId, loadRuns]);

  const availableScripts = useMemo(() => {
    const selectedIds = new Set(formScripts.map(item => item.script_id));
    return scripts.filter(item => !selectedIds.has(item.script_id));
  }, [scripts, formScripts]);

  function openCreate() {
    setEditingId(null);
    setFormName('');
    setFormDescription('');
    setFormScripts([]);
    setFormContinueOnError(false);
    setFormStepTimeoutMinutes('0');
    setEditorOpen(true);
  }

  function openEdit(workflow: WorkflowDefinition) {
    setEditingId(workflow.workflow_id);
    setFormName(workflow.name);
    setFormDescription(workflow.description);
    setFormScripts(
      workflow.script_ids
        .map(id => scripts.find(script => script.script_id === id))
        .filter((script): script is Script => Boolean(script)),
    );
    setFormContinueOnError(Boolean(workflow.continue_on_error));
    setFormStepTimeoutMinutes(String(Math.round((workflow.step_timeout || 0) / 60)));
    setEditorOpen(true);
  }

  function moveScript(index: number, direction: -1 | 1) {
    setFormScripts(current => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function saveWorkflow() {
    if (!formName.trim() || formScripts.length === 0) {
      setError('请填写流程名称，并至少选择一个脚本');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const timeoutMinutes = Math.max(0, Math.min(1440, Number(formStepTimeoutMinutes) || 0));
      const data = {
        name: formName.trim(),
        description: formDescription.trim(),
        script_ids: formScripts.map(item => item.script_id),
        continue_on_error: formContinueOnError,
        step_timeout: Math.round(timeoutMinutes * 60),
      };
      const saved = editingId
        ? await workflowApi.updateWorkflow(editingId, data) as unknown as WorkflowDefinition
        : await workflowApi.createWorkflow(data) as unknown as WorkflowDefinition;
      await loadWorkflows();
      setSelectedWorkflowId(saved.workflow_id);
      setEditorOpen(false);
      setNotice(editingId ? '流程已更新' : '流程已创建');
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  async function removeWorkflow(workflow: WorkflowDefinition) {
    if (!window.confirm(`确定删除流程“${workflow.name}”吗？历史执行记录和截图会保留。`)) return;
    try {
      await workflowApi.deleteWorkflow(workflow.workflow_id);
      await loadWorkflows();
      setNotice('流程已删除，历史记录和截图仍保留');
    } catch (deleteError) {
      setError(errorMessage(deleteError));
    }
  }

  async function startWorkflow() {
    if (!selectedWorkflow || selectedDeviceIds.length === 0) {
      setError('请选择要执行的流程和至少一台在线手机');
      return;
    }
    setStarting(true);
    setError('');
    try {
      const response = await workflowApi.executeWorkflow(
        selectedWorkflow.workflow_id,
        selectedDeviceIds,
      ) as unknown as { run_ids: string[] };
      await loadRuns(selectedWorkflow.workflow_id);
      await loadAllRuns();
      setSelectedRunId(response.run_ids[0] || '');
      setNotice(`已在 ${response.run_ids.length} 台手机上启动流程，各手机独立执行、互不影响`);
    } catch (startError) {
      setError(errorMessage(startError));
    } finally {
      setStarting(false);
    }
  }

  function toggleDevice(deviceId: string) {
    setSelectedDeviceIds(current => (
      current.includes(deviceId)
        ? current.filter(item => item !== deviceId)
        : [...current, deviceId]
    ));
  }

  function selectAllOnline() {
    setSelectedDeviceIds(
      connectedDevices
        .filter(device => !busyDeviceIds.has(device.device_id))
        .map(device => device.device_id),
    );
  }

  function toggleRunSelection(runId: string) {
    setSelectedRunIds(current => {
      const next = new Set(current);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  }

  function toggleSelectAllRuns() {
    setSelectedRunIds(allDeletableSelected
      ? new Set()
      : new Set(deletableRuns.map(run => run.run_id)));
  }

  async function interruptRun(run: WorkflowRun) {
    if (!activeStatuses.has(run.status)) return;
    const label = `${run.device_name || run.device_id} · ${formatTime(run.created_at)}`;
    if (!window.confirm(`确定中断「${label}」这条流程执行吗？\n记录会标记为「已中断」，后续步骤跳过，手机立即恢复可用（已产生的截图保留）。`)) return;
    setInterruptingRunId(run.run_id);
    setError('');
    setNotice('');
    try {
      await workflowApi.cancelRun(run.run_id);
      await loadRuns(selectedWorkflowId);
      await loadAllRuns();
      if (selectedRunId === run.run_id) {
        const detail = await workflowApi.getRun(run.run_id) as unknown as WorkflowRun;
        setRunDetail(detail);
      }
      setNotice('已中断该执行记录，后续步骤已跳过');
    } catch (interruptError) {
      setError(errorMessage(interruptError));
    } finally {
      setInterruptingRunId(null);
    }
  }

  async function removeRun(run: WorkflowRun) {
    if (!terminalStatuses.has(run.status)) {
      setError('运行中的执行记录请先中断，再删除');
      return;
    }
    const label = `${run.device_name || run.device_id} · ${formatTime(run.created_at)}`;
    if (!window.confirm(`确定删除「${label}」这条执行记录吗？\n步骤日志和截图会一起删除，且不可恢复。`)) return;
    setDeletingRunId(run.run_id);
    setError('');
    setNotice('');
    try {
      await workflowApi.deleteRun(run.run_id);
      setSelectedRunIds(current => {
        if (!current.has(run.run_id)) return current;
        const next = new Set(current);
        next.delete(run.run_id);
        return next;
      });
      if (selectedRunId === run.run_id) {
        setSelectedRunId('');
        setRunDetail(null);
      }
      await loadRuns(selectedWorkflowId);
      await loadAllRuns();
      setNotice('执行记录已删除');
    } catch (deleteError) {
      setError(errorMessage(deleteError));
    } finally {
      setDeletingRunId(null);
    }
  }

  async function removeSelectedRuns() {
    const runIds = Array.from(selectedRunIds);
    if (runIds.length === 0) return;
    if (!window.confirm(`确定删除选中的 ${runIds.length} 条执行记录吗？\n步骤日志和截图会一起删除，且不可恢复。`)) return;
    setBatchDeleting(true);
    setError('');
    setNotice('');
    try {
      await workflowApi.batchDeleteRuns(runIds);
      if (runIds.includes(selectedRunId)) {
        setSelectedRunId('');
        setRunDetail(null);
      }
      setSelectedRunIds(new Set());
      await loadRuns(selectedWorkflowId);
      await loadAllRuns();
      setNotice(`已删除 ${runIds.length} 条执行记录`);
    } catch (deleteError) {
      setError(errorMessage(deleteError));
    } finally {
      setBatchDeleting(false);
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-[#16191C] flex items-center gap-2">
            <WorkflowIcon size={22} className="text-[#F2A33A]" />流程管理
          </h1>
          <p className="text-[#6B7076] text-sm mt-1">选择多个脚本并排序，可同时选择多台手机分别独立执行同一流程，逐步保存截图</p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-[#F2A33A] hover:bg-[#C97F1E] text-white rounded-lg text-sm">
          <Plus size={16} />新建流程
        </button>
      </div>

      {(error || notice) && (
        <div className={`mb-4 px-4 py-3 rounded-lg text-sm flex justify-between ${error ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-700'}`}>
          <span>{error || notice}</span>
          <button onClick={() => { setError(''); setNotice(''); }}>关闭</button>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <section className="bg-white border border-[#E6E1D8] rounded-lg p-4">
          <h2 className="font-medium text-[#16191C] mb-3">已保存流程（{workflows.length}）</h2>
          <div className="space-y-2">
            {workflows.map(workflow => (
              <div key={workflow.workflow_id} className={`border rounded-lg p-3 cursor-pointer ${selectedWorkflowId === workflow.workflow_id ? 'border-[#F2A33A] bg-[#FBF6EC]' : 'border-[#E6E1D8] hover:bg-slate-50'}`} onClick={() => setSelectedWorkflowId(workflow.workflow_id)}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium text-sm text-[#16191C]">{workflow.name}</div>
                    <div className="text-xs text-[#6B7076] mt-1">{workflow.scripts.length} 个脚本</div>
                  </div>
                  <div className="flex gap-1">
                    <button title="编辑流程" onClick={event => { event.stopPropagation(); openEdit(workflow); }} className="p-1.5 text-[#6B7076] hover:text-[#F2A33A]"><Pencil size={14} /></button>
                    <button title="删除流程" onClick={event => { event.stopPropagation(); void removeWorkflow(workflow); }} className="p-1.5 text-[#6B7076] hover:text-red-500"><Trash2 size={14} /></button>
                  </div>
                </div>
              </div>
            ))}
            {workflows.length === 0 && <div className="text-center text-sm text-[#9AA0A6] py-10">还没有流程，请先新建</div>}
          </div>
        </section>

        <section className="xl:col-span-2 space-y-5">
          {selectedWorkflow ? (
            <>
              <div className="bg-white border border-[#E6E1D8] rounded-lg p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="font-semibold text-[#16191C]">{selectedWorkflow.name}</h2>
                    <p className="text-sm text-[#6B7076] mt-1">{selectedWorkflow.description || '暂无说明'}</p>
                  </div>
                  <button disabled={starting || selectedDeviceIds.length === 0} onClick={() => void startWorkflow()} className="flex items-center gap-2 px-4 py-2 bg-[#3FB950] hover:bg-[#2E9E45] disabled:bg-slate-300 text-white rounded-lg text-sm">
                    {starting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                    一键执行（{selectedDeviceIds.length} 台）
                  </button>
                </div>

                <div className="mt-4 border border-[#E6E1D8] rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-[#16191C] flex items-center gap-1.5">
                      <Smartphone size={14} className="text-[#6B7076]" />
                      选择执行手机（已选 {selectedDeviceIds.length} / 在线 {connectedDevices.length}）
                    </span>
                    <div className="flex gap-2">
                      <button onClick={selectAllOnline} className="text-xs text-[#F2A33A] hover:underline">全选在线</button>
                      <button onClick={() => setSelectedDeviceIds([])} className="text-xs text-[#6B7076] hover:underline">清空</button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {connectedDevices.map(device => {
                      const busy = busyDeviceIds.has(device.device_id);
                      const checked = selectedDeviceIds.includes(device.device_id);
                      return (
                        <button
                          key={device.device_id}
                          disabled={busy}
                          onClick={() => toggleDevice(device.device_id)}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm border transition-colors ${
                            busy
                              ? 'border-amber-200 bg-amber-50 text-amber-600 cursor-not-allowed'
                              : checked
                                ? 'border-[#F2A33A] bg-[#FBF6EC] text-[#F2A33A]'
                                : 'border-[#E6E1D8] text-[#4A4F55] hover:bg-slate-50'
                          }`}
                          title={busy ? '该手机正在执行其他流程' : device.device_id}
                        >
                          <span className={`w-4 h-4 rounded border flex items-center justify-center ${checked && !busy ? 'bg-[#F2A33A] border-[#F2A33A]' : 'border-[#D6D2C9] bg-white'}`}>
                            {checked && !busy && <Check size={11} className="text-white" />}
                          </span>
                          <span className="font-medium">{device.name || device.model || device.device_id}</span>
                          {device.group_name && <span className="text-xs text-[#9AA0A6]">[{device.group_name}]</span>}
                          {busy && <span className="text-xs">执行中</span>}
                        </button>
                      );
                    })}
                    {connectedDevices.length === 0 && (
                      <span className="text-sm text-[#9AA0A6]">没有在线手机，请先在“手机管理”中连接</span>
                    )}
                  </div>
                </div>

                <div className="mt-4 space-y-2">
                  {selectedWorkflow.scripts.map((script, index) => (
                    <div key={`${script.script_id}-${index}`} className="flex items-center gap-3 bg-[#F7F5F1] rounded-lg px-3 py-2 text-sm">
                      <span className="w-6 h-6 rounded-full bg-[#FDF1DC] text-[#F2A33A] flex items-center justify-center text-xs">{index + 1}</span>
                      <FileCode size={15} className="text-[#6B7076]" />
                      <span>{script.name}</span>
                      <span className="text-xs text-[#9AA0A6]">{script.platform}</span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-[#9AA0A6] mt-3">
                  {selectedWorkflow.continue_on_error
                    ? `错误后跳过该脚本、继续执行后面的脚本；单脚本超时 ${selectedWorkflow.step_timeout > 0 ? `${Math.round(selectedWorkflow.step_timeout / 60)} 分钟` : '不限'}。`
                    : '错误后停止；任一脚本失败即终止整个流程，剩余步骤标记为已跳过。'}
                </p>
              </div>

              <div className="bg-white border border-[#E6E1D8] rounded-lg p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <h2 className="font-medium text-[#16191C]">
                    执行历史
                    {runs.length > 0 && <span className="text-xs text-[#9AA0A6] ml-2">共 {runs.length} 条</span>}
                  </h2>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={toggleSelectAllRuns}
                      disabled={deletableRuns.length === 0 || batchDeleting}
                      className="text-xs text-[#F2A33A] hover:underline disabled:text-[#D6D2C9] disabled:no-underline disabled:cursor-not-allowed"
                      title="只能勾选已结束的执行记录"
                    >
                      {allDeletableSelected ? '取消全选' : `全选（${deletableRuns.length}）`}
                    </button>
                    <button
                      onClick={() => void removeSelectedRuns()}
                      disabled={selectedRunIds.size === 0 || batchDeleting}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg bg-red-50 text-red-600 hover:bg-red-100 disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
                    >
                      {batchDeleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                      批量删除{selectedRunIds.size > 0 ? `（${selectedRunIds.size}）` : ''}
                    </button>
                  </div>
                </div>

                <div className="border border-[#E6E1D8] rounded-lg divide-y divide-[#F0EDE6]">
                  {runs.map(run => {
                    const active = activeStatuses.has(run.status);
                    const checked = selectedRunIds.has(run.run_id);
                    return (
                      <div
                        key={run.run_id}
                        className={`flex items-center gap-3 px-3 py-2 ${selectedRunId === run.run_id ? 'bg-[#FBF6EC]' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!terminalStatuses.has(run.status) || batchDeleting}
                          onChange={() => toggleRunSelection(run.run_id)}
                          title={active ? '运行中的记录不能删除，请先中断' : '选择这条执行记录'}
                          className="w-4 h-4 accent-[#F2A33A] disabled:opacity-40 disabled:cursor-not-allowed"
                        />
                        <button onClick={() => setSelectedRunId(run.run_id)} className="flex-1 min-w-0 text-left">
                          <div className="text-sm text-[#16191C] truncate">
                            {run.batch_id ? '批量 · ' : ''}{run.device_name || run.device_id} · {formatTime(run.created_at)}
                          </div>
                          <div className="text-xs text-[#9AA0A6] truncate">
                            {run.workflow_name} · 进度 {run.current_step}/{run.total_steps}
                            {run.error ? ` · ${run.error}` : ''}
                          </div>
                        </button>
                        <RunStatus status={run.status} />
                        {active && (
                          <button
                            onClick={() => void interruptRun(run)}
                            disabled={interruptingRunId !== null}
                            className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border border-amber-200 text-amber-600 hover:bg-amber-50 disabled:opacity-50 disabled:cursor-not-allowed"
                            title="中断该执行（结束当前脚本，后续步骤跳过）"
                          >
                            {interruptingRunId === run.run_id
                              ? <Loader2 size={13} className="animate-spin" />
                              : <Square size={13} />}
                            {interruptingRunId === run.run_id ? '中断中' : '中断'}
                          </button>
                        )}
                        {!active && (
                          <button
                            onClick={() => void removeRun(run)}
                            disabled={deletingRunId !== null || batchDeleting}
                            className="p-1.5 text-[#9AA0A6] hover:text-red-500 hover:bg-red-50 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed"
                            title="删除该执行记录"
                          >
                            {deletingRunId === run.run_id
                              ? <Loader2 size={14} className="animate-spin" />
                              : <Trash2 size={14} />}
                          </button>
                        )}
                      </div>
                    );
                  })}
                  {runs.length === 0 && (
                    <div className="py-10 text-center text-sm text-[#9AA0A6]">暂无执行记录，点击上方“一键执行”开始</div>
                  )}
                </div>

                {runDetail && (
                  <div>
                    <div className="flex items-center justify-between mb-3 text-sm">
                      <span className="text-[#6B7076]">设备：{runDetail.device_name || runDetail.device_id}（{runDetail.device_id}） · 进度 {runDetail.current_step}/{runDetail.total_steps}</span>
                      <StepStatus status={runDetail.status} />
                    </div>
                    {runDetail.error && <div className="mb-3 bg-red-50 text-red-600 text-sm rounded-lg p-3">{runDetail.error}</div>}
                    <div className="space-y-3">
                      {runDetail.steps.map(step => (
                        <div key={step.step_id} className="border border-[#E6E1D8] rounded-lg p-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="font-medium text-sm">第 {step.step_order} 步 · {step.script_name}</div>
                            <StepStatus status={step.status} />
                          </div>
                          <div className="text-xs text-[#9AA0A6] mt-1">开始：{formatTime(step.started_at)} · 完成：{formatTime(step.completed_at)}</div>
                          {(rescueByStep[step.step_id] || []).length > 0 && (
                            <div className="mt-2 bg-[#FBF6EC] border border-[#F9E5C2] rounded-lg p-2 space-y-1">
                              <div className="text-xs text-[#F2A33A] font-medium">脚本救援 · {rescueByStep[step.step_id].length} 次</div>
                              {rescueByStep[step.step_id].map(item => (
                                <div key={item.rescue_id} className="text-xs flex items-center gap-2">
                                  <span className={item.resolved ? 'text-emerald-600' : 'text-red-600'}>
                                    {item.resolved ? '已救回' : item.status === 'running' ? '进行中' : '未救回'}
                                  </span>
                                  <span className="text-[#6B7076]">{item.handler || '-'}</span>
                                  <span className="text-[#16191C] truncate">{item.evidence || item.error}</span>
                                  <span className="text-[#9AA0A6] shrink-0">{formatTime(item.created_at)}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {step.error && <div className="mt-2 text-sm text-red-600">{step.error}</div>}
                          {step.output && (
                            <details className="mt-2">
                              <summary className="cursor-pointer text-xs text-[#6B7076]">查看脚本日志</summary>
                              <pre className="mt-2 max-h-64 overflow-auto bg-[#16191C] text-slate-200 rounded-lg p-3 text-xs whitespace-pre-wrap">{step.output}</pre>
                            </details>
                          )}
                          {step.screenshot_path && (
                            <div className="mt-3 flex items-start gap-3 bg-[#F7F5F1] rounded-lg p-3">
                              <button onClick={() => window.open(workflowApi.getScreenshotUrl(step.step_id), '_blank', 'noopener')} className="w-28 shrink-0 bg-slate-200 rounded overflow-hidden">
                                <img src={workflowApi.getScreenshotUrl(step.step_id)} alt={`${step.script_name}完成后截图`} className="w-full h-40 object-contain" />
                              </button>
                              <div className="text-xs text-[#6B7076] min-w-0">
                                <div className="flex items-center gap-1 text-[#16191C] mb-2"><ImageIcon size={14} />步骤完成截图</div>
                                <div>拍摄时间：{formatTime(step.captured_at)}</div>
                                <div className="mt-1 break-all">本地路径：{step.screenshot_path}</div>
                                <button onClick={() => window.open(workflowApi.getScreenshotUrl(step.step_id), '_blank', 'noopener')} className="text-[#F2A33A] mt-2">打开原图</button>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="bg-white border border-[#E6E1D8] rounded-lg p-16 text-center text-[#9AA0A6]">新建流程后，在这里选择手机并执行</div>
          )}
        </section>
      </div>

      {editorOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-5 w-full max-w-2xl mx-4 shadow-lg max-h-[90vh] overflow-auto">
            <h2 className="text-lg font-semibold mb-4">{editingId ? '编辑流程' : '新建流程'}</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">流程名称</label>
                <input value={formName} onChange={event => setFormName(event.target.value)} placeholder="例如：网盘批量转存" className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2 px-3 text-sm outline-none focus:border-[#F2A33A]" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">流程说明</label>
                <textarea value={formDescription} onChange={event => setFormDescription(event.target.value)} rows={2} className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2 px-3 text-sm outline-none focus:border-[#F2A33A]" />
              </div>
              <div className="bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg px-3 py-2">
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                  <span className="text-sm text-[#4A4F55]">脚本出错时</span>
                  <label className="flex items-center gap-2 text-sm text-[#4A4F55] cursor-pointer">
                    <input
                      type="radio"
                      name="error-policy"
                      checked={!formContinueOnError}
                      onChange={() => setFormContinueOnError(false)}
                      className="w-3.5 h-3.5 border-[#E6E1D8] bg-[#F7F5F1] text-[#F2A33A] focus:ring-[#F2A33A]"
                    />
                    错误后停止
                  </label>
                  <label className="flex items-center gap-2 text-sm text-[#4A4F55] cursor-pointer">
                    <input
                      type="radio"
                      name="error-policy"
                      checked={formContinueOnError}
                      onChange={() => setFormContinueOnError(true)}
                      className="w-3.5 h-3.5 border-[#E6E1D8] bg-[#F7F5F1] text-[#F2A33A] focus:ring-[#F2A33A]"
                    />
                    错误后跳过错误脚本，后续继续其他脚本
                  </label>
                  <label className="flex items-center gap-2 text-sm text-[#4A4F55]">
                    单脚本超时
                  <input
                    type="number"
                    min={0}
                    max={1440}
                    value={formStepTimeoutMinutes}
                    onChange={event => setFormStepTimeoutMinutes(event.target.value)}
                    className="w-20 bg-white border border-[#E6E1D8] rounded-md py-1 px-2 text-sm outline-none focus:border-[#F2A33A]"
                  />
                  分钟（0 = 不限）
                </label>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <h3 className="text-sm font-medium mb-2">可选脚本（{availableScripts.length}）</h3>
                  <div className="border border-[#E6E1D8] rounded-lg max-h-72 overflow-auto">
                    {availableScripts.map(script => (
                      <button key={script.script_id} onClick={() => setFormScripts(current => [...current, script])} className="w-full text-left px-3 py-2 border-b last:border-b-0 border-[#F0EDE6] hover:bg-[#FBF6EC]">
                        <div className="text-sm">{script.name}</div>
                        <div className="text-xs text-[#9AA0A6]">{script.platform}</div>
                      </button>
                    ))}
                    {availableScripts.length === 0 && <div className="p-4 text-center text-xs text-[#9AA0A6]">所有脚本均已加入</div>}
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-medium mb-2">执行顺序（{formScripts.length}）</h3>
                  <div className="space-y-2 max-h-72 overflow-auto">
                    {formScripts.map((script, index) => (
                      <div key={script.script_id} className="flex items-center gap-2 border border-[#E6E1D8] rounded-lg p-2">
                        <span className="w-5 text-xs text-[#F2A33A]">{index + 1}</span>
                        <span className="flex-1 text-sm truncate">{script.name}</span>
                        <button disabled={index === 0} onClick={() => moveScript(index, -1)} className="p-1 disabled:text-slate-300"><ArrowUp size={14} /></button>
                        <button disabled={index === formScripts.length - 1} onClick={() => moveScript(index, 1)} className="p-1 disabled:text-slate-300"><ArrowDown size={14} /></button>
                        <button onClick={() => setFormScripts(current => current.filter(item => item.script_id !== script.script_id))} className="p-1 text-[#9AA0A6] hover:text-red-500"><Trash2 size={14} /></button>
                      </div>
                    ))}
                    {formScripts.length === 0 && <div className="p-4 text-center text-xs text-[#9AA0A6] border border-dashed rounded-lg">从左侧点击脚本加入</div>}
                  </div>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setEditorOpen(false)} className="px-4 py-2 bg-[#F0EDE6] text-[#6B7076] rounded-lg text-sm">取消</button>
              <button disabled={saving} onClick={() => void saveWorkflow()} className="px-4 py-2 bg-[#F2A33A] disabled:bg-slate-300 text-white rounded-lg text-sm">{saving ? '保存中...' : '保存流程'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
