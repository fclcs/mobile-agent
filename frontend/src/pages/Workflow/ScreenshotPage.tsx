import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarDays,
  ExternalLink,
  FileCode,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  Search,
  Smartphone,
  Workflow as WorkflowIcon,
  X,
} from 'lucide-react';
import {
  workflowApi,
  type WorkflowDefinition,
  type WorkflowScreenshot,
} from '../../services/api';

function errorMessage(error: unknown): string {
  const value = error as { response?: { data?: { detail?: string } }; message?: string };
  return value.response?.data?.detail || value.message || '截图加载失败';
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

const shortPath = (p: string): string => {
  const norm = (p || '').replace(/\\/g, '/');
  const i = norm.lastIndexOf('workflow_screenshots/');
  return i >= 0 ? norm.slice(i + 'workflow_screenshots/'.length) : norm.split('/').pop() || norm;
};

export function ScreenshotPage() {
  const [screenshots, setScreenshots] = useState<WorkflowScreenshot[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [workflowId, setWorkflowId] = useState('');
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<WorkflowScreenshot | null>(null);

  const loadScreenshots = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await workflowApi.getScreenshots(workflowId || undefined) as unknown as {
        screenshots: WorkflowScreenshot[];
      };
      setScreenshots(response.screenshots);
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    void workflowApi.getWorkflows().then(response => {
      setWorkflows((response as unknown as { workflows: WorkflowDefinition[] }).workflows);
    }).catch(loadError => setError(errorMessage(loadError)));
  }, []);

  useEffect(() => {
    void loadScreenshots();
  }, [loadScreenshots]);

  const filteredScreenshots = useMemo(() => {
    const query = keyword.trim().toLowerCase();
    if (!query) return screenshots;
    return screenshots.filter(item =>
      [item.workflow_name, item.script_name, item.device_id, item.run_id]
        .some(value => value.toLowerCase().includes(query)),
    );
  }, [screenshots, keyword]);

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-[#16191C] flex items-center gap-2">
            <ImageIcon size={22} className="text-[#F2A33A]" />截图记录
          </h1>
          <p className="text-[#6B7076] text-sm mt-1">查看流程中每个脚本完成时保存的现场截图、日期和脚本信息</p>
        </div>
        <button onClick={() => void loadScreenshots()} className="flex items-center gap-2 px-4 py-2 bg-white border border-[#E6E1D8] hover:bg-slate-50 text-[#4A4F55] rounded-lg text-sm">
          <RefreshCw size={16} />刷新
        </button>
      </div>

      <div className="bg-white border border-[#E6E1D8] rounded-lg p-4 mb-5 flex flex-wrap gap-3">
        <select value={workflowId} onChange={event => setWorkflowId(event.target.value)} className="bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2 px-3 text-sm min-w-56">
          <option value="">全部流程</option>
          {workflows.map(workflow => <option key={workflow.workflow_id} value={workflow.workflow_id}>{workflow.name}</option>)}
        </select>
        <label className="relative flex-1 min-w-64">
          <Search size={16} className="absolute left-3 top-2.5 text-[#9AA0A6]" />
          <input value={keyword} onChange={event => setKeyword(event.target.value)} placeholder="搜索流程、脚本、设备或运行 ID" className="w-full bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg py-2 pl-9 pr-3 text-sm outline-none focus:border-[#F2A33A]" />
        </label>
        <span className="self-center text-sm text-[#9AA0A6]">共 {filteredScreenshots.length} 张</span>
      </div>

      {error && <div className="mb-4 bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm">{error}</div>}
      {loading ? (
        <div className="bg-white border border-[#E6E1D8] rounded-lg p-16 flex justify-center text-[#6B7076]"><Loader2 className="animate-spin mr-2" />加载截图...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4">
          {filteredScreenshots.map(item => (
            <article key={item.step_id} className="bg-white border border-[#E6E1D8] rounded-lg overflow-hidden">
              <button onClick={() => setPreview(item)} className="w-full h-80 bg-[#16191C] flex items-center justify-center overflow-hidden">
                <img src={workflowApi.getScreenshotUrl(item.step_id)} alt={`${item.workflow_name} - ${item.script_name}`} className="w-full h-full object-contain" loading="lazy" />
              </button>
              <div className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-medium text-[#16191C] flex items-center gap-2"><WorkflowIcon size={16} className="text-[#F2A33A]" />{item.workflow_name}</h2>
                    <p className="text-sm text-[#4A4F55] mt-2 flex items-center gap-2"><FileCode size={15} />第 {item.step_order} 步 · {item.script_name}</p>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded ${item.status === 'completed' ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'}`}>{item.status === 'completed' ? '已完成' : '失败'}</span>
                </div>
                <div className="mt-3 space-y-1.5 text-xs text-[#6B7076]">
                  <div className="flex items-center gap-2"><CalendarDays size={14} />{formatTime(item.captured_at)}</div>
                  <div className="flex items-center gap-2"><Smartphone size={14} />{item.device_id}</div>
                  <div className="break-all">截图文件：{shortPath(item.screenshot_path)}</div>
                </div>
                <div className="flex gap-2 mt-4">
                  <button onClick={() => setPreview(item)} className="flex-1 px-3 py-2 bg-[#F0EDE6] hover:bg-[#E6E1D8] text-[#4A4F55] rounded-lg text-sm">预览截图</button>
                  <button onClick={() => window.open(workflowApi.getScreenshotUrl(item.step_id), '_blank', 'noopener')} className="flex items-center gap-1 px-3 py-2 border border-[#E6E1D8] text-[#F2A33A] rounded-lg text-sm"><ExternalLink size={14} />原图</button>
                </div>
              </div>
            </article>
          ))}
          {filteredScreenshots.length === 0 && (
            <div className="col-span-full bg-white border border-[#E6E1D8] rounded-lg p-16 text-center text-[#9AA0A6]">
              {screenshots.length === 0 ? '暂无截图，执行一个流程后会自动显示在这里' : '没有符合筛选条件的截图'}
            </div>
          )}
        </div>
      )}

      {preview && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-5" onClick={() => setPreview(null)}>
          <div className="max-w-5xl w-full max-h-[95vh] flex flex-col" onClick={event => event.stopPropagation()}>
            <div className="bg-white rounded-t-lg px-4 py-3 flex items-center justify-between">
              <div>
                <div className="font-medium text-sm">{preview.workflow_name} · 第 {preview.step_order} 步 · {preview.script_name}</div>
                <div className="text-xs text-[#6B7076] mt-1">{formatTime(preview.captured_at)} · {preview.device_id}</div>
              </div>
              <button onClick={() => setPreview(null)} className="p-2 text-[#6B7076] hover:text-[#16191C]"><X size={20} /></button>
            </div>
            <div className="bg-[#16191C] min-h-0 flex-1 flex justify-center overflow-auto rounded-b-lg">
              <img src={workflowApi.getScreenshotUrl(preview.step_id)} alt="流程步骤原图" className="max-w-full max-h-[85vh] object-contain" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
