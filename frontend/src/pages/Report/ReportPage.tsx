import { useEffect, useState } from 'react';
import { FileText, Download, Trash2, Loader2, CheckSquare, Square, X } from 'lucide-react';
import { useReportStore } from '../../stores/reportStore';
import type { Report } from '../../stores/reportStore';
import { ConfirmDialog } from '../../components/ConfirmDialog';

export function ReportPage() {
  const { reports, fetchReports, deleteReport, downloadReport, batchDeleteReports } = useReportStore();
  const [loadingReportId, setLoadingReportId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [batchDeleting, setBatchDeleting] = useState(false);

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === reports.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(reports.map(r => r.report_id)));
    }
  };

  const handleBatchDelete = () => {
    setConfirmOpen(true);
  };

  const handleConfirmDelete = async () => {
    setConfirmOpen(false);
    setBatchDeleting(true);
    try {
      await batchDeleteReports(Array.from(selectedIds));
      setSelectedIds(new Set());
    } catch (error) {
      console.error('Batch delete failed:', error);
    } finally {
      setBatchDeleting(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const getPlatformText = (platform: string) => {
    const platformMap: Record<string, string> = {
      android: 'Android',
      ios: 'iOS',
      harmonyos: 'HarmonyOS',
    };
    return platformMap[platform] || platform;
  };

  const getStatusText = (status: string) => {
    const statusMap: Record<string, string> = {
      pending: '等待生成',
      executing: '生成中',
      completed: '已完成',
      failed: '生成失败',
    };
    return statusMap[status] || status;
  };

  const handleDownload = async (report: Report) => {
    setLoadingReportId(report.report_id);
    try {
      await downloadReport(report.report_id);
    } finally {
      setLoadingReportId(null);
    }
  };

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-[#16191C] flex items-center gap-2">
            <FileText className="w-5 h-5 text-[#F2A33A]" />
            报告管理
          </h1>
          <p className="text-[#6B7076] text-sm mt-1">查看和管理测试报告</p>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-center justify-between">
          <span className="text-[#F2A33A] font-medium">已选择 {selectedIds.size} 项</span>
          <div className="flex gap-2">
            <button
              onClick={handleBatchDelete}
              disabled={batchDeleting}
              title={batchDeleting ? '删除中' : '批量删除'}
              className="px-3 py-1.5 bg-[#E5484D] hover:bg-[#C93B3F] disabled:opacity-50 text-white text-xs font-medium rounded-lg flex items-center gap-1.5 transition-colors duration-200"
            >
              {batchDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              批量删除
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="px-3 py-1.5 bg-[#F0EDE6] hover:bg-[#E6E1D8] text-[#6B7076] text-xs font-medium rounded-lg flex items-center gap-1.5 transition-colors duration-200"
            >
              <X className="w-3.5 h-3.5" />
              取消选择
            </button>
          </div>
        </div>
      )}

      {/* Select All Header */}
      {reports.length > 0 && (
        <div className="flex items-center gap-3 mb-3">
          <button onClick={toggleSelectAll} className="text-[#9AA0A6] hover:text-[#F2A33A] transition-colors duration-200">
            {selectedIds.size === reports.length ? (
              <CheckSquare className="w-4 h-4 text-[#F2A33A]" />
            ) : (
              <Square className="w-4 h-4" />
            )}
          </button>
          <span className="text-[#6B7076] text-xs">全选 ({reports.length})</span>
        </div>
      )}

      {/* Report Cards */}
      <div className="space-y-3">
        {reports.map((report) => (
          <div
            key={report.report_id}
            className="bg-white border border-[#E6E1D8] rounded-lg p-4 hover:border-[#F2A33A] hover:shadow-md transition-all duration-200"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <button onClick={() => toggleSelect(report.report_id)} className="mt-0.5 text-[#9AA0A6] hover:text-[#F2A33A] transition-colors duration-200">
                  {selectedIds.has(report.report_id) ? (
                    <CheckSquare className="w-4 h-4 text-[#F2A33A]" />
                  ) : (
                    <Square className="w-4 h-4" />
                  )}
                </button>
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <h3 className="text-[#16191C] font-medium text-sm">{report.name}</h3>
                    <span className={`px-2.5 py-1 text-xs rounded-full ${
                      report.status === 'completed' ? 'bg-green-100 text-green-600' :
                      report.status === 'executing' ? 'bg-blue-100 text-blue-600' :
                      report.status === 'failed' ? 'bg-red-100 text-red-600' :
                      'bg-gray-100 text-gray-500'
                    }`}>
                      {getStatusText(report.status)}
                    </span>
                  </div>
                  <p className="text-[#6B7076] text-xs">任务: {report.task_name} · {getPlatformText(report.platform)} · {new Date(report.created_at).toLocaleString()}</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4">
                {/* Stats */}
                <div className="flex items-center gap-4">
                  {report.total_steps !== undefined && (
                    <div className="text-center">
                      <p className="text-lg font-semibold text-[#16191C]">{report.total_steps}</p>
                      <p className="text-xs text-[#9AA0A6]">总用例</p>
                    </div>
                  )}
                  {report.passed_steps !== undefined && (
                    <div className="text-center">
                      <p className="text-lg font-semibold text-[#3FB950]">{report.passed_steps}</p>
                      <p className="text-xs text-[#9AA0A6]">通过</p>
                    </div>
                  )}
                  {report.failed_steps !== undefined && (
                    <div className="text-center">
                      <p className="text-lg font-semibold text-[#E5484D]">{report.failed_steps}</p>
                      <p className="text-xs text-[#9AA0A6]">失败</p>
                    </div>
                  )}
                  {report.total_steps !== undefined && report.total_steps > 0 && (
                    <div className="text-center">
                      <p className="text-lg font-semibold text-[#F2A33A]">
                        {Math.round(((report.passed_steps ?? 0) / report.total_steps) * 100)}%
                      </p>
                      <p className="text-xs text-[#9AA0A6]">通过率</p>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1.5 ml-4 pl-4 border-l border-[#E6E1D8]">
                  <button
                    onClick={() => handleDownload(report)}
                    disabled={loadingReportId === report.report_id || report.status !== 'completed'}
                    className="px-3 py-1.5 bg-[#F2A33A] hover:bg-[#C97F1E] disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium rounded-lg flex items-center gap-1.5 transition-all duration-200"
                    title="下载"
                  >
                    {loadingReportId === report.report_id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Download className="w-3.5 h-3.5" />
                    )}
                    下载报告
                  </button>
                  <button
                    onClick={() => deleteReport(report.report_id)}
                    className="px-3 py-1.5 bg-[#F0EDE6] hover:bg-[#E6E1D8] text-[#6B7076] text-xs font-medium rounded-lg flex items-center gap-1.5 transition-all duration-200"
                    title="删除"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}

        {reports.length === 0 && (
          <div className="text-center py-16 bg-[#F7F5F1] border border-[#E6E1D8] rounded-lg">
            <FileText className="w-12 h-12 text-[#9AA0A6] mx-auto mb-3" />
            <h3 className="text-[#16191C] text-base font-medium mb-1.5">暂无报告</h3>
            <p className="text-[#6B7076] text-sm">执行任务后将自动生成报告</p>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="批量删除报告"
        message={`确定要删除 ${selectedIds.size} 个报告吗？此操作不可撤销。`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleConfirmDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
